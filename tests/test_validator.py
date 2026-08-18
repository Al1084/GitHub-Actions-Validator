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
