"""Core validation orchestration: load workflow YAML and run registered checks."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from gha_validator.checks import CHECKS, Finding


class _LineStr(str):
    """A str that remembers the 1-indexed source line it was parsed from."""

    __slots__ = ("line",)


class _LineTrackingLoader(yaml.SafeLoader):
    """SafeLoader that tags every parsed string scalar with its source line.

    This lets checks (and the fixer) point at the exact `uses:` line without
    a second parsing pass. Strings built any other way (e.g. workflow dicts
    constructed directly in tests) are plain `str` with no `.line` attribute
    — consumers read it via `getattr(value, "line", None)`.
    """


def _construct_str_with_line(loader: yaml.SafeLoader, node: yaml.Node) -> _LineStr:
    tagged = _LineStr(loader.construct_scalar(node))
    tagged.line = node.start_mark.line + 1
    return tagged


_LineTrackingLoader.add_constructor("tag:yaml.org,2002:str", _construct_str_with_line)


def load_workflow(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f, Loader=_LineTrackingLoader) or {}


def repo_root() -> Path:
    """Find the nearest ancestor of the current working directory containing a `.git` directory.

    Falls back to the cwd itself if not inside a git repo, so the tool still
    works standalone (e.g. validating a single workflow file outside a checkout).
    Public (not `_`-prefixed): fixer.py resolves fixes against this same
    anchor, so Finding.file and on-disk fix targets stay consistent.
    """
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _normalize_path(path: Path) -> str:
    """Render `path` relative to the repo root, POSIX-style, so Finding.file never leaks an absolute path."""
    resolved = path.resolve()
    root = repo_root()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        try:
            return Path(os.path.relpath(resolved, root)).as_posix()
        except ValueError:
            return resolved.as_posix()  # e.g. different drive on Windows: no relative form exists


def validate_file(path: Path) -> list[Finding]:
    workflow = load_workflow(path)
    file = _normalize_path(path)
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(workflow, file))
    return findings


def validate_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(validate_file(path))
    return findings
