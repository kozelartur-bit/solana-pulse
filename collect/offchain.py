"""Off-chain sources: DeFiLlama and CoinGecko.

Both expose public endpoints that need no API key, which keeps the whole
project runnable with nothing but a Python install.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "solana-pulse/1.0 (+https://github.com/)"


def _get_json(url: str, timeout: float = 25.0, attempts: int = 3) -> Any:
    """GET JSON with retry/backoff. Returns None rather than raising."""
    last: Exception | None = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(1.5 * (2**attempt))
    return None


def defillama_tvl() -> dict[str, Any]:
    """Solana chain TVL plus a 7-day series for trend and anomaly detection."""
    series = _get_json("https://api.llama.fi/v2/historicalChainTvl/Solana") or []
    tvl_now = None
    change_24h_pct = None
    change_7d_pct = None
    history: list[dict[str, Any]] = []

    if isinstance(series, list) and series:
        tail = series[-31:]
        history = [{"date": p.get("date"), "tvl": p.get("tvl")} for p in tail]
        tvl_now = series[-1].get("tvl")
        if len(series) >= 2 and series[-2].get("tvl"):
            change_24h_pct = round(100.0 * (tvl_now - series[-2]["tvl"]) / series[-2]["tvl"], 2)
        if len(series) >= 8 and series[-8].get("tvl"):
            change_7d_pct = round(100.0 * (tvl_now - series[-8]["tvl"]) / series[-8]["tvl"], 2)

    return {
        "tvl_usd": round(tvl_now, 2) if tvl_now else None,
        "change_24h_pct": change_24h_pct,
        "change_7d_pct": change_7d_pct,
        "history_30d": history,
    }


def defillama_stablecoins() -> dict[str, Any]:
    """Stablecoin float sitting on Solana."""
    data = _get_json("https://stablecoins.llama.fi/stablecoinchains") or []
    if not isinstance(data, list):
        return {"total_usd": None}
    for row in data:
        if str(row.get("gecko_id", "")).lower() == "solana" or row.get("name") == "Solana":
            total = row.get("totalCirculatingUSD", {})
            if isinstance(total, dict):
                return {"total_usd": round(sum(v for v in total.values() if isinstance(v, (int, float))), 2)}
    return {"total_usd": None}


def defillama_dex_volume() -> dict[str, Any]:
    """24h and 7d DEX volume on Solana."""
    data = _get_json("https://api.llama.fi/overview/dexs/solana?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
    if not isinstance(data, dict):
        return {"volume_24h_usd": None, "volume_7d_usd": None, "change_24h_pct": None}
    return {
        "volume_24h_usd": data.get("total24h"),
        "volume_7d_usd": data.get("total7d"),
        "change_24h_pct": data.get("change_1d"),
    }


def coingecko_sol() -> dict[str, Any]:
    """SOL price, market cap and recent moves from the public (keyless) API."""
    data = _get_json(
        "https://api.coingecko.com/api/v3/coins/solana"
        "?localization=false&tickers=false&community_data=false&developer_data=false"
    )
    if not isinstance(data, dict):
        return {"price_usd": None}

    market = data.get("market_data", {}) or {}

    def usd(field: str) -> Any:
        value = market.get(field)
        return value.get("usd") if isinstance(value, dict) else None

    return {
        "price_usd": usd("current_price"),
        "market_cap_usd": usd("market_cap"),
        "volume_24h_usd": usd("total_volume"),
        "change_24h_pct": market.get("price_change_percentage_24h"),
        "change_7d_pct": market.get("price_change_percentage_7d"),
        "change_30d_pct": market.get("price_change_percentage_30d"),
        "ath_usd": usd("ath"),
        "ath_change_pct": market.get("ath_change_percentage", {}).get("usd")
        if isinstance(market.get("ath_change_percentage"), dict)
        else None,
    }


def coingecko_sol_sparkline(days: int = 30) -> list[dict[str, Any]]:
    """Daily SOL close prices, used for the chart and the z-score baseline."""
    data = _get_json(
        f"https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days={days}&interval=daily"
    )
    if not isinstance(data, dict):
        return []
    prices = data.get("prices") or []
    return [{"ts": int(p[0] / 1000), "price": round(p[1], 4)} for p in prices if isinstance(p, list) and len(p) == 2]
