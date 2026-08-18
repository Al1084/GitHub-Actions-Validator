"""Tests for gha_validator.formatters: table, json, and github annotation output."""

from __future__ import annotations

import json

from gha_validator.checks import Finding, Severity
from gha_validator.formatters import FORMATTERS, format_github, format_json, format_table

FINDINGS = [
    Finding(
        check="missing-permissions",
        severity=Severity.WARNING,
        message="Workflow does not declare a top-level `permissions` block.",
        file="ci.yml",
    ),
    Finding(
        check="outdated-action-version",
        severity=Severity.INFO,
        message="jobs.build.steps[0]: `actions/checkout@v3` is outdated (v4 available).",
        file="ci.yml",
    ),
    Finding(
        check="deprecated-action",
        severity=Severity.WARNING,
        message="jobs.build.steps[1]: `actions/create-release` is deprecated. Archived by GitHub; use `softprops/action-gh-release` instead.",
        file="ci.yml",
        line=12,
    ),
]


def test_registry_exposes_all_three_formats():
    assert set(FORMATTERS) == {"table", "json", "github"}


def test_table_empty():
    assert format_table([]) == "No issues found."


def test_table_has_header_and_one_row_per_finding():
    output = format_table(FINDINGS)
    lines = output.splitlines()

    assert lines[0].split() == ["SEVERITY", "CHECK", "FILE", "MESSAGE"]
    assert len(lines) == 2 + len(FINDINGS)  # header + separator + one row each
    assert "missing-permissions" in lines[2]
    assert "outdated-action-version" in lines[3]
    assert "deprecated-action" in lines[4]


def test_json_round_trips_all_fields():
    output = format_json(FINDINGS)
    parsed = json.loads(output)

    assert len(parsed) == 3
    assert parsed[0] == {
        "check": "missing-permissions",
        "severity": "warning",
        "message": "Workflow does not declare a top-level `permissions` block.",
        "file": "ci.yml",
        "line": None,
        "fix": None,
    }
    assert parsed[2]["line"] == 12


def test_json_empty_is_empty_array():
    assert json.loads(format_json([])) == []


def test_github_maps_severity_to_annotation_level():
    output = format_github(FINDINGS)
    lines = output.splitlines()

    assert lines[0].startswith("::warning file=ci.yml::")
    assert lines[1].startswith("::notice file=ci.yml::")
    assert lines[2].startswith("::warning file=ci.yml,line=12::")


def test_github_escapes_percent_and_newlines_in_message():
    finding = Finding(
        check="x", severity=Severity.ERROR, message="100% failed\nsecond line", file="ci.yml"
    )

    output = format_github([finding])

    assert "%25" in output  # escaped '%'
    assert "%0A" in output  # escaped '\n'
    assert "\n" not in output.strip("\n")  # message newline didn't split the command


def test_github_empty_is_empty_string():
    assert format_github([]) == ""


def test_all_formatters_handle_the_same_findings_without_error():
    for formatter in FORMATTERS.values():
        assert isinstance(formatter(FINDINGS), str)
