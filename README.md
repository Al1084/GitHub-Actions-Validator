# gha-validator

CLI tool to validate GitHub Actions workflows. Flags actions with known published security advisories from the GitHub Advisory Database, outdated action versions, deprecated/unmaintained actions, unpinned mutable refs, and missing `permissions:` blocks.

## Install

```bash
pip install gha-validator
```

For unreleased changes on `main`, install from git instead:

```bash
pip install git+https://github.com/Al1084/GitHub-Actions-Validator.git@main
```

## Usage

```bash
gha-validate .github/workflows/*.yml
```

```
SEVERITY  CHECK                    FILE    MESSAGE
--------  -----------------------  ------  ---------------------------------------------------------------------------------------------------------------------------
INFO      outdated-action-version  ci.yml  jobs.build.steps[0]: `actions/checkout@v3` is outdated (v7.0.1 available).
WARNING   unpinned-action          ci.yml  jobs.build.steps[1]: `actions/setup-node@main` is not pinned to a version or commit SHA.
INFO      outdated-action-version  ci.yml  jobs.build.steps[2]: `actions/create-release@v1` is outdated (v1.1.4 available).
WARNING   missing-permissions      ci.yml  Workflow does not declare a top-level `permissions` block.
WARNING   deprecated-action        ci.yml  jobs.build.steps[2]: `actions/create-release` is deprecated. Archived by GitHub; use `softprops/action-gh-release` instead.
```

### Security advisories

Every pinned action is checked against the [GitHub Advisory Database](https://github.com/advisories?query=ecosystem%3Aactions)'s published `actions`-ecosystem advisories. A match is always reported at `error` severity — GitHub's own `critical`/`high`/`medium`/`low` label is included in the message, but a low-severity CVE is still a CVE, so it's never downgraded to something that gets silently ignored.

```yaml
- uses: wktk/conflibot@v1.0.0
```

```
SEVERITY  CHECK               FILE    MESSAGE
--------  ------------------  ------  --------------------------------------------------------------------------------------------------------------------------------------------------------------
ERROR     security-advisory   ci.yml  jobs.build.steps[0]: `wktk/conflibot@v1.0.0` — [GHSA-2qvg-qr73-mqxp] (critical severity) conflibot vulnerable to command injection via crafted pull request branch names under pull_request_target. fixed in 1.2.1. https://github.com/advisories/GHSA-2qvg-qr73-mqxp
```

If the pinned version can't be confirmed against the advisory's affected-version range, or no patched version has been published yet, the finding is still reported (without a `--fix`) rather than silently skipped.

### Output format

`--format table|json|github`, default `table`.

```bash
gha-validate --format json .github/workflows/*.yml
```

```json
[
  {
    "check": "outdated-action-version",
    "severity": "info",
    "message": "jobs.build.steps[0]: `actions/checkout@v3` is outdated (v7.0.1 available).",
    "file": "ci.yml",
    "line": 7,
    "fix": { "old": "actions/checkout@v3", "new": "actions/checkout@v7.0.1" }
  },
  {
    "check": "unpinned-action",
    "severity": "warning",
    "message": "jobs.build.steps[1]: `actions/setup-node@main` is not pinned to a version or commit SHA.",
    "file": "ci.yml",
    "line": 8,
    "fix": null
  }
]
```

`--format github` emits [workflow-command annotations](https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions) that GitHub renders as inline PR annotations:

```bash
gha-validate --format github .github/workflows/*.yml
```

```
::notice file=ci.yml,line=7::jobs.build.steps[0]: `actions/checkout@v3` is outdated (v7.0.1 available).
::warning file=ci.yml,line=8::jobs.build.steps[1]: `actions/setup-node@main` is not pinned to a version or commit SHA.
::notice file=ci.yml,line=9::jobs.build.steps[2]: `actions/create-release@v1` is outdated (v1.1.4 available).
::warning file=ci.yml::Workflow does not declare a top-level `permissions` block.
::warning file=ci.yml,line=9::jobs.build.steps[2]: `actions/create-release` is deprecated. Archived by GitHub; use `softprops/action-gh-release` instead.
```

### Auto-fix

`--fix` auto-bumps version pins in place for `outdated-action-version` and `security-advisory` findings, scoped to the exact flagged line (won't touch an identical string sitting in a comment or elsewhere in the file). If an action is both outdated and has an advisory on the same line, the advisory's fix wins — its minimal patched version is the smallest change that clears the CVE, versus jumping straight to the latest release.

```bash
gha-validate --fix .github/workflows/*.yml
```

```
fixed ci.yml: actions/checkout@v3 -> actions/checkout@v7.0.1
fixed ci.yml: actions/create-release@v1 -> actions/create-release@v1.1.4
```

Exit code is non-zero if any `error`-severity finding remains.

## As a GitHub Action

```yaml
- uses: Al1084/GitHub-Actions-Validator@v0.2.0
  with:
    paths: .github/workflows/*.yml  # default
    format: github                  # default; table|json|github
    fix: "false"                    # default
```

No `pip install` step needed — the action installs itself from its own pinned ref.

## As a pre-commit hook

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Al1084/GitHub-Actions-Validator
    rev: v0.2.0
    hooks:
      - id: gha-validate
```

Runs automatically against changed files under `.github/workflows/`. `language: python`, so pre-commit builds an isolated environment for it — no separate install step needed.

## Checks

- `security-advisory` — action is pinned to a version covered by a published GitHub security advisory (always `error` severity)
- `outdated-action-version` — a pinned version tag has a newer release available
- `unpinned-action` — pinned to a mutable ref (`@main`, `@master`, a branch) instead of a version or commit SHA
- `deprecated-action` — action is archived/unmaintained (seed list, growing)
- `missing-permissions` — workflow has no top-level `permissions:` block
