# gha-validator

CLI tool to validate GitHub Actions workflows: outdated action versions, deprecated/unmaintained actions, missing `permissions:` blocks.

## Install

```bash
pip install gha-validator
```

## Usage

```bash
gha-validate .github/workflows/*.yml
```

```
SEVERITY  CHECK                    FILE    MESSAGE
--------  -----------------------  ------  --------------------------------------------------------------------------
INFO      outdated-action-version  ci.yml  jobs.build.steps[0]: `actions/checkout@v3` is outdated (v7.0.1 available).
WARNING   missing-permissions      ci.yml  Workflow does not declare a top-level `permissions` block.
```

Output format (`--format table|json|github`, default `table`):

```bash
gha-validate --format github .github/workflows/*.yml
```

Auto-bump outdated version pins in place (`--fix`; only affects `outdated-action-version` findings):

```bash
gha-validate --fix .github/workflows/*.yml
```

Exit code is non-zero if any `error`-severity finding remains.

## Checks

- `outdated-action-version` — a pinned version tag has a newer release available
- `unpinned-action` — pinned to a mutable ref (`@main`, `@master`, a branch) instead of a version or commit SHA
- `deprecated-action` — action is archived/unmaintained (seed list, growing)
- `missing-permissions` — workflow has no top-level `permissions:` block
