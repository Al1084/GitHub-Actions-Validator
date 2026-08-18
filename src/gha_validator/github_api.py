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


@functools.lru_cache(maxsize=1)
def get_actions_advisories() -> tuple[dict, ...]:
    """Fetch every published security advisory for the 'actions' ecosystem, across all pages.

    Queried once for the whole ecosystem rather than per-action: as of
    writing this is ~55 advisories fitting in a single page, but paginated
    via the response's Link header regardless so it stays correct if that
    grows past one page. This is a small, constant number of calls no
    matter how many distinct actions a workflow pins - a per-action lookup
    would instead scale with the action count and burn through the
    unauthenticated rate limit fast.

    Raises on a failed request rather than returning an empty list, so a
    network/API problem surfaces as a visible error (validate_file's
    per-check safety net turns it into a Finding) instead of silently
    reporting zero advisories found.
    """
    advisories: list[dict] = []
    url = f"{GITHUB_API_URL}/advisories"
    params: dict[str, str] | None = {"ecosystem": "actions", "per_page": "100"}
    while url:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        advisories.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None  # the 'next' URL already carries the query params
    return tuple(advisories)
