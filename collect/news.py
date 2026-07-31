"""Ecosystem and developer news from primary sources.

The brief asks for "relevant Twitter accounts (e.g. for key announcements,
sentiment)". Twitter has no keyless read API, and scraping it is both fragile
and legally murky — so this reads the sources those announcements are *about*
instead: validator client releases and merged protocol proposals.

That is arguably better signal. A tweet announcing a release is downstream of
the release; reading the release directly removes a hop and cannot be
misquoted.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .offchain import _get_json

GITHUB_API = "https://api.github.com"

# Unauthenticated GitHub allows 60 requests/hour per IP. This module makes two
# per run, so a 6-hourly schedule uses under 1% of the budget.
CLIENT_REPOS = (
    ("anza-xyz/agave", "Agave"),
    ("firedancer-io/firedancer", "Firedancer"),
)


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        when = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.datetime.now(dt.timezone.utc) - when).days


def client_releases(per_repo: int = 3) -> list[dict[str, Any]]:
    """Recent validator client releases — the closest thing to a changelog
    for what actually runs the network."""
    out: list[dict[str, Any]] = []

    for repo, label in CLIENT_REPOS:
        data = _get_json(f"{GITHUB_API}/repos/{repo}/releases?per_page={per_repo}")
        if not isinstance(data, list):
            continue
        for r in data[:per_repo]:
            published = r.get("published_at")
            out.append(
                {
                    "client": label,
                    "tag": r.get("tag_name"),
                    "published_at": published,
                    "age_days": _age_days(published),
                    "prerelease": bool(r.get("prerelease")),
                    "url": r.get("html_url"),
                }
            )

    out.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    return out


def merged_simds(limit: int = 6) -> list[dict[str, Any]]:
    """Recently merged Solana Improvement Documents.

    A merged SIMD is where protocol change becomes official — earlier than a
    release, later than a rumour. Closed-but-unmerged pull requests are
    filtered out: a rejected proposal is not news of a change.
    """
    data = _get_json(
        f"{GITHUB_API}/repos/solana-foundation/solana-improvement-documents/pulls"
        "?state=closed&sort=updated&direction=desc&per_page=25"
    )
    if not isinstance(data, list):
        return []

    rows: list[dict[str, Any]] = []
    for pr in data:
        if not pr.get("merged_at"):
            continue
        rows.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "merged_at": pr.get("merged_at"),
                "age_days": _age_days(pr.get("merged_at")),
                "url": pr.get("html_url"),
            }
        )
        if len(rows) >= limit:
            break

    return rows
