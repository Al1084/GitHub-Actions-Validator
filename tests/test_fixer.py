"""Tests for gha_validator.fixer.apply_fixes."""

from __future__ import annotations

from gha_validator import fixer
from gha_validator.checks import Finding, Fix, Severity


def test_applies_fix_and_rewrites_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text("uses: actions/checkout@v3\n")

    finding = Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="outdated",
        file="ci.yml",
        line=1,
        fix=Fix(old="actions/checkout@v3", new="actions/checkout@v4"),
    )

    remaining, applied = fixer.apply_fixes([finding])

    assert applied == [finding]
    assert remaining == []
    assert workflow.read_text() == "uses: actions/checkout@v4\n"


def test_leaves_non_fixable_findings_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)

    finding = Finding(
        check="missing-permissions", severity=Severity.WARNING, message="...", file="ci.yml"
    )

    remaining, applied = fixer.apply_fixes([finding])

    assert remaining == [finding]
    assert applied == []


def test_skips_fixable_finding_with_no_line(tmp_path, monkeypatch):
    """No line to scope the edit to: refuse rather than blindly text-match the whole file."""
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text("uses: actions/checkout@v3\n")

    finding = Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="outdated",
        file="ci.yml",
        line=None,
        fix=Fix(old="actions/checkout@v3", new="actions/checkout@v4"),
    )

    remaining, applied = fixer.apply_fixes([finding])

    assert applied == []
    assert remaining == [finding]
    assert workflow.read_text() == "uses: actions/checkout@v3\n"


def test_handles_duplicate_old_refs_in_same_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n"  # line 1
        "  a:\n"  # line 2
        "    steps:\n"  # line 3
        "      - uses: actions/checkout@v3\n"  # line 4
        "  b:\n"  # line 5
        "    steps:\n"  # line 6
        "      - uses: actions/checkout@v3\n"  # line 7
    )
    findings = [
        Finding(
            check="outdated-action-version",
            severity=Severity.INFO,
            message="outdated",
            file="ci.yml",
            line=line,
            fix=Fix(old="actions/checkout@v3", new="actions/checkout@v4"),
        )
        for line in (4, 7)
    ]

    remaining, applied = fixer.apply_fixes(findings)

    assert len(applied) == 2
    assert remaining == []
    text = workflow.read_text()
    assert text.count("actions/checkout@v4") == 2
    assert "actions/checkout@v3" not in text


def test_skips_finding_whose_old_text_is_no_longer_present(tmp_path, monkeypatch):
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text("uses: actions/checkout@v4\n")  # already up to date on disk

    finding = Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="outdated",
        file="ci.yml",
        line=1,
        fix=Fix(old="actions/checkout@v3", new="actions/checkout@v4"),
    )

    remaining, applied = fixer.apply_fixes([finding])

    assert applied == []
    assert remaining == [finding]


def test_advisory_fix_wins_over_outdated_version_fix_on_same_line(tmp_path, monkeypatch):
    """An action that's both outdated (INFO, fix -> latest) and has a security
    advisory (ERROR, fix -> minimal patched version) on the same line: the
    ERROR/advisory fix must win, since it's the smaller, CVE-clearing change -
    bumping straight to latest could be a breaking major version jump.
    """
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text("uses: wktk/conflibot@v1.0.0\n")

    outdated = Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="outdated",
        file="ci.yml",
        line=1,
        fix=Fix(old="wktk/conflibot@v1.0.0", new="wktk/conflibot@v2.0.0"),
    )
    advisory = Finding(
        check="security-advisory",
        severity=Severity.ERROR,
        message="vulnerable",
        file="ci.yml",
        line=1,
        fix=Fix(old="wktk/conflibot@v1.0.0", new="wktk/conflibot@1.2.1"),
    )

    remaining, applied = fixer.apply_fixes([outdated, advisory])

    assert applied == [advisory]
    assert remaining == [outdated]
    assert workflow.read_text() == "uses: wktk/conflibot@1.2.1\n"


def test_does_not_touch_identical_text_in_a_comment_on_another_line(tmp_path, monkeypatch):
    """Regression test for the exact risk flagged: a comment earlier in the file repeats the
    same `owner/repo@ref` string as the real, flagged `uses:` line. A whole-file
    `str.replace(old, new, 1)` would hit the comment (first textual match) and leave the
    actually-flagged line untouched. Scoping to `finding.line` must fix the right one.
    """
    monkeypatch.setattr(fixer, "repo_root", lambda: tmp_path)
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "# old pin, keep for reference: uses: actions/checkout@v3\n"  # line 1 (not flagged)
        "on: push\n"  # line 2
        "jobs:\n"  # line 3
        "  build:\n"  # line 4
        "    steps:\n"  # line 5
        "      - uses: actions/checkout@v3\n"  # line 6 (the real, flagged occurrence)
    )

    finding = Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="outdated",
        file="ci.yml",
        line=6,
        fix=Fix(old="actions/checkout@v3", new="actions/checkout@v4"),
    )

    remaining, applied = fixer.apply_fixes([finding])

    lines = workflow.read_text().splitlines()
    assert applied == [finding]
    assert remaining == []
    assert "actions/checkout@v3" in lines[0]  # comment untouched
    assert lines[5] == "      - uses: actions/checkout@v4"  # real usage fixed
