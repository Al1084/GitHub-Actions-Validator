"""GitHub API interactions: latest release lookups, security advisories."""

from __future__ import annotations

import functools

import requests

GITHUB_API_URL = "https://api.github.com"


@functools.lru_cache(maxsize=None)
def get_latest_release_tag(owner: str, repo: str) -> str | None:
    """Return the tag name of the latest release for an action's repo, or None if unavailable.

    Memoized per-process: a single validation run often references the same
    action from multiple steps/files, so this avoids redundant API calls
    (and unauthenticated GitHub rate-limit pressure) within one invocation.
    """
    resp = requests.get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases/latest", timeout=10
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("tag_name")
