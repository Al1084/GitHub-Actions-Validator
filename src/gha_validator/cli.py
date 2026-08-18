"""Click CLI entry point for gha-validator."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from gha_validator.fixer import apply_fixes
from gha_validator.formatters import FORMATTERS
from gha_validator.validator import validate_paths


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(sorted(FORMATTERS)),
    default="table",
    help="Output format.",
)
@click.option(
    "--fix",
    "fix",
    is_flag=True,
    default=False,
    help="Auto-bump outdated action version pins in place. Only affects outdated-action-version findings.",
)
def main(paths: tuple[Path, ...], output_format: str, fix: bool) -> None:
    """Validate GitHub Actions workflow files.

    PATHS are one or more workflow YAML files to check.
    """
    findings = validate_paths(list(paths))

    if fix:
        findings, applied = apply_fixes(findings)
        for finding in applied:
            click.echo(f"fixed {finding.file}: {finding.fix.old} -> {finding.fix.new}")

    output = FORMATTERS[output_format](findings)
    if output:
        click.echo(output)

    sys.exit(1 if any(f.severity.value == "error" for f in findings) else 0)


if __name__ == "__main__":
    main()
