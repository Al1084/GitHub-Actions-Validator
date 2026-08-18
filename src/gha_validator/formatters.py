"""Render Findings for different output destinations.

Each formatter takes a list[Finding] and returns the rendered string.
New formats are added here and registered in FORMATTERS so cli.py
picks them up automatically.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from gha_validator.checks import Finding, Severity


def format_table(findings: list[Finding]) -> str:
    """Render findings as an aligned plain-text table for terminal/log reading."""
    if not findings:
        return "No issues found."

    headers = ("SEVERITY", "CHECK", "FILE", "MESSAGE")
    rows = [
        (f.severity.value.upper(), f.check, Path(f.file).name, f.message) for f in findings
    ]
    widths = [max(len(header), *(len(row[i]) for row in rows)) for i, header in enumerate(headers)]

    def render(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(row, widths))

    lines = [render(headers), render(tuple("-" * w for w in widths))]
    lines.extend(render(row) for row in rows)
    return "\n".join(lines)


def format_json(findings: list[Finding]) -> str:
    """Render findings as a JSON array, for machine consumption / piping to other tools."""
    return json.dumps([dataclasses.asdict(f) for f in findings], default=str, indent=2)


_ANNOTATION_LEVELS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "notice",
}


def _escape_property(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _escape_message(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def format_github(findings: list[Finding]) -> str:
    """Render findings as GitHub Actions workflow-command annotations.

    e.g. `::warning file=ci.yml::message` — recognized natively by the
    Actions runner and surfaced as inline annotations on the PR diff and
    the job summary, without needing a separate reporting step.
    """
    lines = []
    for f in findings:
        level = _ANNOTATION_LEVELS[f.severity]
        props = f"file={_escape_property(f.file)}"
        if f.line is not None:
            props += f",line={f.line}"
        lines.append(f"::{level} {props}::{_escape_message(f.message)}")
    return "\n".join(lines)


FORMATTERS = {
    "table": format_table,
    "json": format_json,
    "github": format_github,
}
