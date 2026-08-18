"""Apply auto-fixable Findings back to their source files (`--fix`).

Only Findings that carry a `fix` payload (currently: outdated-action-version)
are touched. Each Fix is a literal, unambiguous find/replace — no YAML
rewriting or reformatting, so the rest of the file is untouched.
"""

from __future__ import annotations

from gha_validator.checks import Finding
from gha_validator.validator import repo_root


def apply_fixes(findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Rewrite each fixable finding's source file in place, scoped to its exact line.

    Returns (remaining, applied): `remaining` is `findings` minus whatever was
    successfully written to disk (still worth reporting), `applied` is what
    was fixed.

    The replacement is deliberately scoped to `finding.line`, not a
    whole-file text search: `_iter_action_refs` only walks the structured
    `jobs.*.steps[*].uses` tree, so a whole-file `str.replace` could instead
    hit an identical string sitting in a comment or a `with:` value that was
    never the thing flagged — silently "fixing" the wrong spot while leaving
    the real one outdated. A finding with no line (only possible if a
    Finding was built without going through validator.load_workflow, e.g.
    programmatically) is skipped rather than guessed at, and a finding whose
    `fix.old` text isn't found at that line is skipped too — e.g. already
    fixed by hand, or the file changed since the scan.
    """
    root = repo_root()
    fixable_by_file: dict[str, list[Finding]] = {}
    for f in findings:
        if f.fix is not None:
            fixable_by_file.setdefault(f.file, []).append(f)

    applied: list[Finding] = []
    for file, file_findings in fixable_by_file.items():
        path = root / file
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False

        for finding in file_findings:
            if finding.line is None:
                continue
            idx = finding.line - 1
            if not (0 <= idx < len(lines)) or finding.fix.old not in lines[idx]:
                continue
            lines[idx] = lines[idx].replace(finding.fix.old, finding.fix.new, 1)
            applied.append(finding)
            changed = True

        if changed:
            path.write_text("".join(lines), encoding="utf-8")

    applied_ids = {id(f) for f in applied}
    remaining = [f for f in findings if id(f) not in applied_ids]
    return remaining, applied
