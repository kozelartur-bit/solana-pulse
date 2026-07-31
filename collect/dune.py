"""Optional Dune Analytics integration.

The brief names Dune as a preferred source and, in the same document, requires
that the report run without API keys. Those two pull in opposite directions, so
this module resolves it by being strictly optional:

* With `DUNE_API_KEY` set, it pulls the latest cached results for whatever
  query IDs are listed in `data/dune_queries.json`.
* Without it, `collect()` returns a disabled marker and the report renders
  exactly as before. Nothing fails, nothing is silently missing.

Scraping the public site was evaluated and rejected. Findings, so the next
person does not repeat the work:

* Plain HTTP to `dune.com` returns **403** — Cloudflare fronts it, and a CI
  runner using urllib has no browser fingerprint or cookies to satisfy it.
* The old unofficial endpoint `/api/embeds/{query}/{viz}/data` now returns
  **404**; it was removed.
* The current path needs a GraphQL call for an `execution_id` followed by a
  POST whose payload shape is undocumented and rejected requests during
  testing even from inside a logged-in browser session.

A scraper built on that would pass locally and fail silently in CI, leaving a
permanently empty section in an "auto-updating" report. An honest gap beats a
broken feature.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any

API_ROOT = "https://api.dune.com/api/v1"
TIMEOUT = 30.0


def _queries() -> list[dict[str, Any]]:
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "dune_queries.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _fetch_results(query_id: int, api_key: str, limit: int = 20) -> dict[str, Any] | None:
    """Latest cached results for a query. Does not trigger a new execution:
    re-running someone else's query costs credits and changes nothing."""
    url = f"{API_ROOT}/query/{query_id}/results?limit={limit}"
    req = urllib.request.Request(url, headers={"X-Dune-API-Key": api_key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def collect() -> dict[str, Any]:
    """Pull configured Dune queries, or report cleanly that it is switched off."""
    api_key = os.environ.get("DUNE_API_KEY", "").strip()
    queries = _queries()

    if not api_key:
        return {
            "enabled": False,
            "reason": (
                "DUNE_API_KEY is not set. The report is designed to run without any keys; "
                "set the variable to enable this section."
            ),
            "configured_queries": len(queries),
        }

    if not queries:
        return {"enabled": False, "reason": "No query IDs configured in data/dune_queries.json."}

    results: list[dict[str, Any]] = []
    for entry in queries:
        query_id = entry.get("query_id")
        if not isinstance(query_id, int):
            continue

        payload = _fetch_results(query_id, api_key)
        if not payload:
            results.append({"label": entry.get("label"), "query_id": query_id, "ok": False})
            continue

        result = payload.get("result") or {}
        rows = result.get("rows") or []
        results.append(
            {
                "label": entry.get("label"),
                "description": entry.get("description"),
                "query_id": query_id,
                "ok": True,
                "executed_at": payload.get("execution_ended_at"),
                "row_count": len(rows),
                "columns": (result.get("metadata") or {}).get("column_names") or [],
                "rows": rows[:10],
            }
        )

    return {"enabled": True, "queries": results}
