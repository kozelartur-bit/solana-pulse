"""Ecosystem depth: protocols, tokenized assets, fees and roadmap.

Everything here stays keyless. Where a source the brief mentions requires an
API key — Dune Analytics being the obvious one — the same underlying metric is
sourced from a public endpoint instead, and the substitution is documented in
the README rather than hidden.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from .offchain import _get_json


# DeFiLlama lists centralised exchange reserves and bridge custody as
# "protocols". They hold assets *on* Solana but are not Solana DeFi, and
# including them makes the numbers self-contradictory: Binance's Solana
# reserves alone exceed the chain TVL figure this report quotes elsewhere.
# Excluded so every TVL number in the report belongs to the same universe.
EXCLUDED_CATEGORIES = {"cex", "bridge", "chain", "canonical bridge", "infrastructure"}


def _is_defi(protocol: dict[str, Any]) -> bool:
    return (protocol.get("category") or "").strip().lower() not in EXCLUDED_CATEGORIES


def top_protocols(limit: int = 12) -> list[dict[str, Any]]:
    """Largest DeFi protocols on Solana by TVL, with 1d/7d momentum."""
    data = _get_json("https://api.llama.fi/protocols")
    if not isinstance(data, list):
        return []

    rows: list[dict[str, Any]] = []
    for p in data:
        chains = p.get("chains") or []
        if "Solana" not in chains or not _is_defi(p):
            continue
        chain_tvls = p.get("chainTvls") or {}
        tvl = chain_tvls.get("Solana")
        if not isinstance(tvl, (int, float)) or tvl <= 0:
            continue
        rows.append(
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "tvl_usd": round(tvl, 2),
                "change_1d_pct": p.get("change_1d"),
                "change_7d_pct": p.get("change_7d"),
            }
        )

    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    return rows[:limit]


def category_breakdown() -> list[dict[str, Any]]:
    """TVL grouped by protocol category — where the money actually sits."""
    data = _get_json("https://api.llama.fi/protocols")
    if not isinstance(data, list):
        return []

    totals: dict[str, float] = {}
    for p in data:
        if "Solana" not in (p.get("chains") or []) or not _is_defi(p):
            continue
        tvl = (p.get("chainTvls") or {}).get("Solana")
        if not isinstance(tvl, (int, float)) or tvl <= 0:
            continue
        totals[p.get("category") or "Other"] = totals.get(p.get("category") or "Other", 0.0) + tvl

    grand = sum(totals.values()) or 1.0
    rows = [
        {"category": k, "tvl_usd": round(v, 2), "share_pct": round(100.0 * v / grand, 2)}
        for k, v in totals.items()
    ]
    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    return rows[:10]


def tokenized_assets() -> dict[str, Any]:
    """Real-world assets and tokenized equities living on Solana.

    The brief calls out tokenized equity volume specifically. DeFiLlama tags
    these protocols as RWA, so the category total is the closest keyless proxy.
    """
    data = _get_json("https://api.llama.fi/protocols")
    if not isinstance(data, list):
        return {"total_usd": None, "protocols": []}

    rwa: list[dict[str, Any]] = []
    for p in data:
        if "Solana" not in (p.get("chains") or []):
            continue
        category = (p.get("category") or "").lower()
        if "rwa" not in category and "real world" not in category:
            continue
        tvl = (p.get("chainTvls") or {}).get("Solana")
        if not isinstance(tvl, (int, float)) or tvl <= 0:
            continue
        rwa.append({"name": p.get("name"), "tvl_usd": round(tvl, 2)})

    rwa.sort(key=lambda r: r["tvl_usd"], reverse=True)
    return {
        "total_usd": round(sum(r["tvl_usd"] for r in rwa), 2) if rwa else None,
        "protocols": rwa[:8],
    }


# The USDC mint. getRecentPrioritizationFees returns the *minimum* fee that
# landed in each slot, and with no accounts specified that minimum is almost
# always zero — technically correct, useless as a signal. Asking about a
# genuinely contended account instead reports what someone competing for the
# same state actually had to pay.
HOT_ACCOUNT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def fees(rpc: Any) -> dict[str, Any]:
    """Priority fee levels straight from RPC — a live congestion signal.

    getRecentPrioritizationFees returns per-slot micro-lamports per compute
    unit. The median is the honest headline; the 90th percentile shows what
    someone in a hurry is actually paying.
    """
    samples = rpc.try_call("getRecentPrioritizationFees", [[HOT_ACCOUNT]]) or []
    if not samples:
        samples = rpc.try_call("getRecentPrioritizationFees", [[]]) or []
    values = sorted(
        s.get("prioritizationFee", 0)
        for s in samples
        if isinstance(s, dict) and isinstance(s.get("prioritizationFee"), (int, float))
    )
    if not values:
        return {"median_priority_fee": None, "p90_priority_fee": None, "zero_fee_share_pct": None}

    mid = values[len(values) // 2]
    p90 = values[int(len(values) * 0.9) - 1] if len(values) >= 10 else values[-1]
    zero_share = round(100.0 * sum(1 for v in values if v == 0) / len(values), 1)

    return {
        "median_priority_fee": mid,
        "p90_priority_fee": p90,
        "zero_fee_share_pct": zero_share,
        "sample_slots": len(values),
    }


def revenue() -> dict[str, Any]:
    """Real Economic Value — what users actually pay to use the chain.

    Two figures, because they mean different things:

    * **Fees** — everything users paid, base plus priority.
    * **Revenue** — the base-fee portion, which is what accrues to the
      protocol rather than being competed away in priority auctions.

    Caveat worth stating: this does not include Jito MEV tips, which are paid
    out-of-protocol and are not in DeFiLlama's fee adapter. True Solana REV as
    the term is usually used = these fees + MEV tips, so treat this as the
    in-protocol floor rather than the whole number.
    """
    fees_data = _get_json("https://api.llama.fi/summary/fees/solana") or {}
    rev_data = _get_json("https://api.llama.fi/summary/fees/solana?dataType=dailyRevenue") or {}

    def pick(source: dict[str, Any], key: str) -> Any:
        value = source.get(key)
        return round(value, 2) if isinstance(value, (int, float)) else None

    fee_24h = pick(fees_data, "total24h")
    prev_24h = pick(fees_data, "total48hto24h")
    change = None
    if isinstance(fee_24h, (int, float)) and isinstance(prev_24h, (int, float)) and prev_24h:
        change = round(100.0 * (fee_24h - prev_24h) / prev_24h, 2)

    return {
        "fees_24h_usd": fee_24h,
        "fees_7d_usd": pick(fees_data, "total7d"),
        "fees_30d_usd": pick(fees_data, "total30d"),
        "fees_change_24h_pct": change,
        "revenue_24h_usd": pick(rev_data, "total24h"),
        "revenue_7d_usd": pick(rev_data, "total7d"),
        "note": "In-protocol fees only; excludes out-of-protocol MEV tips.",
    }


def roadmap() -> list[dict[str, Any]]:
    """Upcoming protocol upgrades.

    Curated rather than scraped: SIMD status lives in a GitHub repo of markdown
    documents with no machine-readable index, and a brittle scraper here would
    fail silently and quietly mislead. The list is versioned in
    `data/roadmap.json` and easy to amend.
    """
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "roadmap.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
