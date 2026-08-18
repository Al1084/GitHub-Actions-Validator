"""Tests for gha_validator.checks: check_pinned_versions, check_deprecated_actions, check_security_advisories."""

from __future__ import annotations

from gha_validator import checks


def _workflow(uses_list: list[str]) -> dict:
    return {"jobs": {"build": {"steps": [{"uses": uses} for uses in uses_list]}}}


def _boom(owner: str, repo: str) -> str | None:
    raise AssertionError(f"get_latest_release_tag should not be called for {owner}/{repo}")


class _FakeLineStr(str):
    """Stand-in for validator._LineStr, without importing validator into these unit tests."""

    __slots__ = ("line",)


def _uses(value: str, line: int) -> _FakeLineStr:
    tagged = _FakeLineStr(value)
    tagged.line = line
    return tagged


def test_flags_outdated_version(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@v3"]), "ci.yml")

    assert len(findings) == 1
    assert findings[0].check == "outdated-action-version"
    assert findings[0].severity == checks.Severity.INFO
    assert "actions/checkout@v3" in findings[0].message
    assert "v4" in findings[0].message
    assert findings[0].fix == checks.Fix(old="actions/checkout@v3", new="actions/checkout@v4")


def test_finding_captures_line_when_uses_value_carries_one(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(
        _workflow([_uses("actions/checkout@v3", line=7)]), "ci.yml"
    )

    assert findings[0].line == 7


def test_finding_line_is_none_without_line_info(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@v3"]), "ci.yml")

    assert findings[0].line is None


def test_mutable_ref_has_no_fix(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@main"]), "ci.yml")

    assert findings[0].fix is None


def test_allows_up_to_date_version(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@v4"]), "ci.yml")

    assert findings == []


def test_flags_mutable_ref(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@main"]), "ci.yml")

    assert len(findings) == 1
    assert findings[0].check == "unpinned-action"
    assert findings[0].severity == checks.Severity.WARNING


def test_flags_branch_ref_not_in_known_mutable_list(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@some-feature-branch"]), "ci.yml")

    assert len(findings) == 1
    assert findings[0].check == "unpinned-action"


def test_skips_sha_pinned_action(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", _boom)
    sha = "b4ffde65f46336ab88eb53be808477a3936bae11"

    findings = checks.check_pinned_versions(_workflow([f"actions/checkout@{sha}"]), "ci.yml")

    assert findings == []


def test_skips_local_and_docker_actions(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", _boom)

    findings = checks.check_pinned_versions(
        _workflow(["./local-action", "docker://alpine:3.19"]), "ci.yml"
    )

    assert findings == []


def test_no_findings_when_release_lookup_fails(monkeypatch):
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: None)

    findings = checks.check_pinned_versions(_workflow(["actions/checkout@v3"]), "ci.yml")

    assert findings == []


def test_flags_deprecated_action():
    findings = checks.check_deprecated_actions(
        _workflow(["actions/create-release@v1"]), "ci.yml"
    )

    assert len(findings) == 1
    assert findings[0].check == "deprecated-action"
    assert findings[0].severity == checks.Severity.WARNING
    assert "actions/create-release" in findings[0].message
    assert "softprops/action-gh-release" in findings[0].message


def test_allows_non_deprecated_action():
    findings = checks.check_deprecated_actions(_workflow(["actions/checkout@v4"]), "ci.yml")

    assert findings == []


def test_deprecated_check_ignores_local_and_docker_actions():
    findings = checks.check_deprecated_actions(
        _workflow(["./local-action", "docker://alpine:3.19"]), "ci.yml"
    )

    assert findings == []


def test_deprecated_check_flags_multiple_matches():
    findings = checks.check_deprecated_actions(
        _workflow(["actions-rs/toolchain@v1", "actions-rs/cargo@v1", "actions/checkout@v4"]),
        "ci.yml",
    )

    matched = {f.message.split("`")[1] for f in findings}
    assert matched == {"actions-rs/toolchain", "actions-rs/cargo"}


# --- check_security_advisories ---------------------------------------------

SAMPLE_ADVISORY = {
    "ghsa_id": "GHSA-2qvg-qr73-mqxp",
    "html_url": "https://github.com/advisories/GHSA-2qvg-qr73-mqxp",
    "summary": "conflibot vulnerable to command injection via crafted pull request branch names",
    "severity": "critical",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "actions", "name": "wktk/conflibot"},
            "vulnerable_version_range": "< 1.2.1",
            "first_patched_version": "1.2.1",
        }
    ],
}


def test_version_in_range_single_clause():
    assert checks._version_in_range((1, 0, 0), "< 1.2.1") is True
    assert checks._version_in_range((1, 2, 1), "< 1.2.1") is False


def test_version_in_range_compound_clause():
    assert checks._version_in_range((2, 30, 0), ">= 2.25.0, < 2.37.1") is True
    assert checks._version_in_range((2, 40, 0), ">= 2.25.0, < 2.37.1") is False
    assert checks._version_in_range((2, 0, 0), ">= 2.25.0, < 2.37.1") is False


def test_version_in_range_unparseable_returns_none():
    assert checks._version_in_range((1, 0, 0), "some nonsense") is None
    assert checks._version_in_range((1, 0, 0), "") is None


def test_flags_vulnerable_version_with_fix(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@v1.0.0"]), "ci.yml")

    assert len(findings) == 1
    f = findings[0]
    assert f.check == "security-advisory"
    assert f.severity == checks.Severity.ERROR
    assert "GHSA-2qvg-qr73-mqxp" in f.message
    assert "critical" in f.message
    assert f.fix == checks.Fix(old="wktk/conflibot@v1.0.0", new="wktk/conflibot@1.2.1")


def test_low_severity_advisory_still_maps_to_error(monkeypatch):
    low = {**SAMPLE_ADVISORY, "severity": "low"}
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [low])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@v1.0.0"]), "ci.yml")

    assert findings[0].severity == checks.Severity.ERROR
    assert "low" in findings[0].message


def test_allows_patched_version(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@v1.2.1"]), "ci.yml")

    assert findings == []


def test_no_patched_version_reports_without_fix(monkeypatch):
    unpatched = {
        **SAMPLE_ADVISORY,
        "vulnerabilities": [
            {
                "package": {"ecosystem": "actions", "name": "wktk/conflibot"},
                "vulnerable_version_range": ">= 1.0.0",
                "first_patched_version": None,
            }
        ],
    }
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [unpatched])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@v9.0.0"]), "ci.yml")

    assert len(findings) == 1
    assert findings[0].severity == checks.Severity.ERROR
    assert findings[0].fix is None
    assert "no patched version" in findings[0].message.lower()


def test_unparseable_range_still_reports_over_report_policy(monkeypatch):
    weird = {
        **SAMPLE_ADVISORY,
        "vulnerabilities": [
            {
                "package": {"ecosystem": "actions", "name": "wktk/conflibot"},
                "vulnerable_version_range": "unparseable garbage",
                "first_patched_version": "1.2.1",
            }
        ],
    }
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [weird])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@v1.0.0"]), "ci.yml")

    assert len(findings) == 1
    assert findings[0].severity == checks.Severity.ERROR
    assert findings[0].fix is None
    assert "could not confirm" in findings[0].message.lower()


def test_skips_sha_pinned_action_for_advisory_check(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])
    sha = "b4ffde65f46336ab88eb53be808477a3936bae11"

    findings = checks.check_security_advisories(
        _workflow([f"wktk/conflibot@{sha}"]), "ci.yml"
    )

    assert findings == []


def test_skips_mutable_ref_for_advisory_check(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])

    findings = checks.check_security_advisories(_workflow(["wktk/conflibot@main"]), "ci.yml")

    assert findings == []


def test_no_advisories_for_repo_produces_no_findings(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])

    findings = checks.check_security_advisories(_workflow(["actions/checkout@v3"]), "ci.yml")

    assert findings == []


def test_repo_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(checks, "get_actions_advisories", lambda: [SAMPLE_ADVISORY])

    findings = checks.check_security_advisories(_workflow(["WKTK/CONFLIBOT@v1.0.0"]), "ci.yml")

    assert len(findings) == 1
