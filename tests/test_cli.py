"""End-to-end tests for the gha-validate CLI, via Click's CliRunner."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from gha_validator import checks
from gha_validator.cli import main

CI_YML = """\
on: push
permissions:
  contents: read
jobs:
  build:
    steps:
      - uses: actions/checkout@v3
"""

FIXED_CI_YML = """\
on: push
permissions:
  contents: read
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
"""


def test_fix_rewrites_outdated_pin_and_reports_it(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    workflow = tmp_path / "ci.yml"
    workflow.write_text(CI_YML)

    result = CliRunner().invoke(main, ["--fix", str(workflow)])

    assert result.exit_code == 0
    assert "fixed ci.yml: actions/checkout@v3 -> actions/checkout@v4" in result.output
    assert workflow.read_text() == FIXED_CI_YML
    assert "No issues found." in result.output


def test_without_fix_flag_leaves_file_untouched(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(checks, "get_latest_release_tag", lambda owner, repo: "v4")

    workflow = tmp_path / "ci.yml"
    workflow.write_text(CI_YML)

    result = CliRunner().invoke(main, [str(workflow)])

    assert result.exit_code == 0
    assert "fixed" not in result.output
    assert workflow.read_text() == CI_YML
    assert "outdated" in result.output
