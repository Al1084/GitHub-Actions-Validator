"""Tests for gha_validator.validator: check dispatch and Finding.file path normalization."""

from __future__ import annotations

from pathlib import Path

from gha_validator import validator
from gha_validator.validator import validate_file

SAMPLE_WORKFLOW = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


def test_flags_missing_permissions(tmp_path: Path) -> None:
    workflow_file = tmp_path / "ci.yml"
    workflow_file.write_text(SAMPLE_WORKFLOW)

    findings = validate_file(workflow_file)

    assert any(f.check == "missing-permissions" for f in findings)


def test_repo_root_finds_nearest_ancestor_with_git(tmp_path, monkeypatch):
    repo = tmp_path / "myrepo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "sub" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: nested))

    assert validator.repo_root() == repo.resolve()


def test_repo_root_falls_back_to_cwd_without_git(tmp_path, monkeypatch):
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: standalone))

    assert validator.repo_root() == standalone.resolve()


def test_finding_file_is_relative_to_repo_root_not_absolute(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "repo_root", lambda: tmp_path)
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    workflow_file = workflow_dir / "ci.yml"
    workflow_file.write_text("on: push\njobs: {}\n")

    findings = validate_file(workflow_file)

    assert findings  # missing-permissions still fires
    assert findings[0].file == "workflows/ci.yml"
    assert not Path(findings[0].file).is_absolute()


def test_finding_file_falls_back_to_relative_path_outside_repo_root(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(validator, "repo_root", lambda: root)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    workflow_file = outside_dir / "ci.yml"
    workflow_file.write_text("on: push\njobs: {}\n")

    findings = validate_file(workflow_file)

    assert findings[0].file == "../outside/ci.yml"


def test_load_workflow_tags_uses_value_with_its_source_line(tmp_path):
    workflow_file = tmp_path / "ci.yml"
    workflow_file.write_text(
        "on: push\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v3\n"
    )

    workflow = validator.load_workflow(workflow_file)
    uses = workflow["jobs"]["build"]["steps"][0]["uses"]

    assert uses == "actions/checkout@v3"
    assert uses.line == 5


def test_load_workflow_line_tagging_does_not_affect_non_string_values(tmp_path):
    workflow_file = tmp_path / "ci.yml"
    workflow_file.write_text("on: push\nfail-fast: true\nmax-parallel: 4\n")

    workflow = validator.load_workflow(workflow_file)

    assert workflow["fail-fast"] is True
    assert workflow["max-parallel"] == 4


def test_malformed_yaml_produces_finding_not_crash(tmp_path: Path) -> None:
    workflow_file = tmp_path / "ci.yml"
    workflow_file.write_text("on: push\njobs: [unclosed\n")

    findings = validate_file(workflow_file)  # must not raise

    assert len(findings) == 1
    assert findings[0].check == "yaml-syntax-error"
    assert findings[0].severity == validator.Severity.ERROR
    assert "Invalid YAML" in findings[0].message


def test_non_mapping_top_level_produces_finding_not_crash(tmp_path: Path) -> None:
    workflow_file = tmp_path / "ci.yml"
    workflow_file.write_text("- just\n- a\n- list\n")

    findings = validate_file(workflow_file)  # must not raise

    assert len(findings) == 1
    assert findings[0].check == "yaml-syntax-error"
    assert findings[0].severity == validator.Severity.ERROR
    assert "mapping" in findings[0].message
    assert "list" in findings[0].message


def test_check_crash_isolated_as_finding_other_checks_still_run(tmp_path: Path) -> None:
    workflow_file = tmp_path / "ci.yml"
    # "jobs" that parses fine as YAML but isn't the dict-of-jobs every check expects -
    # exercises _iter_action_refs's `jobs.items()` call on a non-dict.
    workflow_file.write_text("on: push\njobs: not-a-mapping\n")

    findings = validate_file(workflow_file)  # must not raise

    by_check = {f.check for f in findings}
    assert "check-error" in by_check
    assert "missing-permissions" in by_check  # unaffected checks still ran
    error_findings = [f for f in findings if f.check == "check-error"]
    assert all(f.severity == validator.Severity.ERROR for f in error_findings)
    assert all("AttributeError" in f.message for f in error_findings)
