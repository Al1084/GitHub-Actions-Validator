"""Individual check functions for GitHub Actions workflow files.

Each check takes a parsed workflow dict and the source file path, and
returns a list of Findings. New checks are added here and registered
in CHECKS so validator.py picks them up automatically.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from gha_validator.github_api import get_actions_advisories, get_latest_release_tag


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Fix:
    """A literal find/replace to apply to a Finding's source file (see fixer.apply_fixes)."""

    old: str
    new: str


@dataclass
class Finding:
    check: str
    severity: Severity
    message: str
    file: str
    line: int | None = None
    fix: Fix | None = None


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MUTABLE_REFS = {"main", "master", "latest", "dev", "develop", "head"}
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _iter_action_refs(workflow: dict[str, Any]):
    """Yield (job_id, step_index, uses_string, line) for every step-level `uses:` in the workflow.

    `line` is the 1-indexed source line of the `uses:` value when the
    workflow was loaded via validator.load_workflow (which tags string
    scalars with their origin); otherwise None (e.g. workflow dicts built
    directly, as in tests). Findings use this to scope fixes to the exact
    line rather than doing a whole-file text match, which could otherwise
    hit an identical string sitting in a comment or a `with:` value instead
    of the actual `uses:` that was flagged.
    """
    jobs = workflow.get("jobs") or {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for step_index, step in enumerate(job.get("steps") or []):
            uses = step.get("uses") if isinstance(step, dict) else None
            if uses:
                yield job_id, step_index, uses, getattr(uses, "line", None)


def _parse_action_ref(uses: str) -> tuple[str, str, str] | None:
    """Split `owner/repo[/path]@ref` into (owner, repo, ref). Returns None for local/docker refs."""
    if uses.startswith("./") or uses.startswith("docker://") or "@" not in uses:
        return None
    path, ref = uses.rsplit("@", 1)
    parts = path.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1], ref


def _parse_version(ref: str) -> tuple[int, int, int] | None:
    """Loosely parse a tag like 'v4', 'v4.1', '4.1.0-beta' into a comparable (major, minor, patch) tuple.

    GitHub Actions tags aren't reliably strict semver (many actions only
    publish major-version tags like `v4`), so this intentionally just reads
    the leading numeric segments and ignores any pre-release/build suffix.
    """
    text = ref[1:] if ref.lower().startswith("v") else ref
    match = _VERSION_RE.match(text)
    if not match:
        return None
    major, minor, patch = (int(g) if g else 0 for g in match.groups())
    return (major, minor, patch)


def check_pinned_versions(workflow: dict[str, Any], file: str) -> list[Finding]:
    """Flag actions pinned to a mutable ref (@main/@master/@latest/branch) or an outdated version tag."""
    findings: list[Finding] = []

    for job_id, step_index, uses, line in _iter_action_refs(workflow):
        parsed = _parse_action_ref(uses)
        if parsed is None:
            continue  # local action (./...) or docker:// ref: no version to check
        owner, repo, ref = parsed
        location = f"jobs.{job_id}.steps[{step_index}]"

        if _SHA_RE.match(ref.lower()):
            continue  # pinned to a commit SHA: most secure, nothing to flag

        current = _parse_version(ref)
        if ref.lower() in _MUTABLE_REFS or current is None:
            findings.append(
                Finding(
                    check="unpinned-action",
                    severity=Severity.WARNING,
                    message=f"{location}: `{owner}/{repo}@{ref}` is not pinned to a version or commit SHA.",
                    file=file,
                    line=line,
                )
            )
            continue

        latest_tag = get_latest_release_tag(owner, repo)
        if latest_tag is None:
            continue  # no releases found, or the API call failed: nothing to compare against

        latest = _parse_version(latest_tag)
        if latest is not None and latest > current:
            findings.append(
                Finding(
                    check="outdated-action-version",
                    severity=Severity.INFO,
                    message=f"{location}: `{owner}/{repo}@{ref}` is outdated ({latest_tag} available).",
                    file=file,
                    line=line,
                    fix=Fix(old=f"{owner}/{repo}@{ref}", new=f"{owner}/{repo}@{latest_tag}"),
                )
            )

    return findings


def check_missing_permissions(workflow: dict[str, Any], file: str) -> list[Finding]:
    """Warn when a workflow doesn't declare a top-level `permissions` block."""
    findings: list[Finding] = []
    if "permissions" not in workflow:
        findings.append(
            Finding(
                check="missing-permissions",
                severity=Severity.WARNING,
                message="Workflow does not declare a top-level `permissions` block.",
                file=file,
            )
        )
    return findings


# Seed list of actions known to be archived/unmaintained, keyed by "owner/repo".
# Whole-repo scope only (not version-scoped) — expand as more are confirmed.
DEPRECATED_ACTIONS: dict[str, str] = {
    "actions/create-release": "Archived by GitHub; use `softprops/action-gh-release` instead.",
    "actions/upload-release-asset": "Archived by GitHub; use `softprops/action-gh-release` instead.",
    "actions-rs/toolchain": "Unmaintained; use `dtolnay/rust-toolchain` instead.",
    "actions-rs/cargo": "Unmaintained; invoke cargo directly, or use `dtolnay/rust-toolchain` instead.",
}


def check_deprecated_actions(workflow: dict[str, Any], file: str) -> list[Finding]:
    """Flag actions known to be archived or no longer maintained (see DEPRECATED_ACTIONS)."""
    findings: list[Finding] = []

    for job_id, step_index, uses, line in _iter_action_refs(workflow):
        parsed = _parse_action_ref(uses)
        if parsed is None:
            continue  # local action (./...) or docker:// ref: not in scope
        owner, repo, _ref = parsed
        reason = DEPRECATED_ACTIONS.get(f"{owner}/{repo}")
        if reason is None:
            continue
        location = f"jobs.{job_id}.steps[{step_index}]"
        findings.append(
            Finding(
                check="deprecated-action",
                severity=Severity.WARNING,
                message=f"{location}: `{owner}/{repo}` is deprecated. {reason}",
                file=file,
                line=line,
            )
        )

    return findings


_RANGE_CLAUSE_RE = re.compile(r"^(<=|>=|<|>|=)\s*(.+)$")
_COMPARATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "=": operator.eq,
}


def _version_in_range(current: tuple[int, int, int], range_text: str) -> bool | None:
    """Check `current` against a GitHub advisory `vulnerable_version_range`.

    The range is a comma-separated list of clauses (e.g. '>= 2.25.0, <
    2.37.1') that must ALL hold. Returns True/False, or None if any clause
    doesn't parse - callers should treat None as "unknown, not cleared".
    """
    clauses = []
    for raw_clause in range_text.split(","):
        match = _RANGE_CLAUSE_RE.match(raw_clause.strip())
        if not match:
            return None
        op, version_text = match.groups()
        version = _parse_version(version_text.strip())
        if version is None:
            return None
        clauses.append((op, version))
    return all(_COMPARATORS[op](current, version) for op, version in clauses)


def check_security_advisories(workflow: dict[str, Any], file: str) -> list[Finding]:
    """Flag actions pinned to a version covered by a published GitHub security advisory.

    Every advisory finding is ERROR severity regardless of GitHub's own
    severity label (critical/high/medium/low all still mean "known CVE") -
    the label is included in the message instead. When the range can't be
    confirmed (unparseable, or a range with no upper bound - i.e. no fix
    has been published) the finding is still reported without a `fix`,
    rather than silently skipped: over-reporting is preferable to missing
    a real vulnerability.
    """
    findings: list[Finding] = []

    by_repo: dict[str, list[tuple[dict, dict]]] = {}
    for advisory in get_actions_advisories():
        for vuln in advisory.get("vulnerabilities", []):
            package = vuln.get("package") or {}
            if package.get("ecosystem") != "actions" or not package.get("name"):
                continue
            by_repo.setdefault(package["name"].lower(), []).append((advisory, vuln))

    if not by_repo:
        return findings

    for job_id, step_index, uses, line in _iter_action_refs(workflow):
        parsed = _parse_action_ref(uses)
        if parsed is None:
            continue  # local action (./...) or docker:// ref: not in scope
        owner, repo, ref = parsed
        matches = by_repo.get(f"{owner}/{repo}".lower())
        if not matches:
            continue

        if _SHA_RE.match(ref.lower()):
            continue  # no version to range-compare a commit SHA against

        current = _parse_version(ref)
        if current is None:
            continue  # mutable ref - unpinned-action already covers this

        location = f"jobs.{job_id}.steps[{step_index}]"

        for advisory, vuln in matches:
            range_text = vuln.get("vulnerable_version_range", "")
            in_range = _version_in_range(current, range_text)
            if in_range is False:
                continue  # confirmed this pinned version isn't affected

            ghsa_id = advisory.get("ghsa_id", "?")
            severity_label = advisory.get("severity", "unknown")
            summary = advisory.get("summary", "")
            url = advisory.get("html_url", "")
            patched = vuln.get("first_patched_version")

            fix = None
            if in_range is None:
                status = f"could not confirm the pinned version against the advisory's range ('{range_text}') - reporting to be safe"
            elif not patched:
                status = "no patched version has been published yet"
            else:
                status = f"fixed in {patched}"
                fix = Fix(old=f"{owner}/{repo}@{ref}", new=f"{owner}/{repo}@{patched}")

            findings.append(
                Finding(
                    check="security-advisory",
                    severity=Severity.ERROR,
                    message=(
                        f"{location}: `{owner}/{repo}@{ref}` — [{ghsa_id}] ({severity_label} severity) "
                        f"{summary}. {status}. {url}"
                    ),
                    file=file,
                    line=line,
                    fix=fix,
                )
            )

    return findings


CHECKS = [
    check_pinned_versions,
    check_missing_permissions,
    check_deprecated_actions,
    check_security_advisories,
]
