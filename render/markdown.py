"""Human-readable Markdown report."""

from __future__ import annotations

from typing import Any

SEVERITY_ICON = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


def _usd(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"${value / size:,.{digits}f}{unit}"
    return f"${value:,.{digits}f}"


def _num(value: Any, digits: int = 0) -> str:
    return f"{value:,.{digits}f}" if isinstance(value, (int, float)) else "—"


def _pct(value: Any) -> str:
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "—"


def render(report: dict[str, Any]) -> str:
    net = report.get("network", {}) or {}
    val = report.get("validators", {}) or {}
    price = report.get("price", {}) or {}
    tvl = report.get("tvl", {}) or {}
    stables = report.get("stablecoins", {}) or {}
    dex = report.get("dex", {}) or {}
    sup = report.get("supply", {}) or {}
    alerts = report.get("alerts", []) or []

    lines: list[str] = []
    add = lines.append

    add("# Solana Pulse")
    add("")
    add(f"_Generated {report.get('generated_at', '')}_")
    add("")

    # --------------------------------------------------------------- anomalies
    add("## Anomalies")
    add("")
    if alerts:
        for a in alerts:
            icon = SEVERITY_ICON.get(a["severity"], "•")
            add(f"- {icon} **{a['severity'].upper()}** — {a['message']}")
    else:
        add("Nothing outside expected ranges in this run.")
    add("")

    # ----------------------------------------------------------------- network
    add("## Network")
    add("")
    add("| Metric | Value |")
    add("|---|---|")
    add(f"| Health | {net.get('health', '—')} |")
    add(f"| TPS (10-sample avg) | {_num(net.get('tps'), 1)} |")
    add(f"| Average slot time | {net.get('avg_slot_time_sec', '—')} s |")
    add(f"| Slot | {_num(net.get('slot'))} |")
    add(f"| Block height | {_num(net.get('block_height'))} |")
    add(f"| Epoch | {_num(net.get('epoch'))} ({net.get('epoch_progress_pct', '—')}% complete) |")
    add("")

    # ------------------------------------------------------------------ market
    add("## Market")
    add("")
    add("| Metric | Value | 24h |")
    add("|---|---|---|")
    add(f"| SOL price | {_usd(price.get('price_usd'))} | {_pct(price.get('change_24h_pct'))} |")
    add(f"| Market cap | {_usd(price.get('market_cap_usd'), 1)} | |")
    add(f"| TVL | {_usd(tvl.get('tvl_usd'), 1)} | {_pct(tvl.get('change_24h_pct'))} |")
    add(f"| Stablecoin supply | {_usd(stables.get('total_usd'), 1)} | |")
    add(f"| DEX volume 24h | {_usd(dex.get('volume_24h_usd'), 1)} | {_pct(dex.get('change_24h_pct'))} |")
    add(f"| Circulating SOL | {_num(sup.get('circulating_sol'))} | |")
    add("")
    add(f"SOL 7d: {_pct(price.get('change_7d_pct'))} · 30d: {_pct(price.get('change_30d_pct'))} · "
        f"from ATH: {_pct(price.get('ath_change_pct'))}")
    add("")

    # ---------------------------------------------------------------- activity
    act = report.get("activity") or {}
    rev = report.get("revenue") or {}

    if act.get("estimate_available"):
        add("## On-chain activity")
        add("")
        add(f"- Distinct fee payers per block: **{_num(act.get('avg_unique_payers_per_block'), 1)}**")
        add(f"- Distinct across sample: **{_num(act.get('unique_payers_in_sample'))}** "
            f"({act.get('sampled_blocks')} blocks, {act.get('sample_spacing_slots')} slots apart)")
        add(f"- Repeat rate: **{act.get('repeat_rate_pct', '—')}%** of appearances are addresses seen in more than one block")
        add(f"- Transactions per block: **{_num(act.get('avg_transactions_per_block'), 1)}**")
        add("")
        add("> Measured, not extrapolated. Multiplying per-block distinct payers by slots per day")
        add("> assumes disjoint populations; the repeat rate shows they are not, and that arithmetic")
        add("> overstates daily actives by roughly two orders of magnitude. A true daily figure needs")
        add("> a full indexer, which this report deliberately is not.")
        add("")

    if rev.get("fees_24h_usd") is not None:
        add("## Real economic value")
        add("")
        add("| Window | Fees (base + priority) | Revenue (base only) |")
        add("|---|---|---|")
        add(f"| 24h | {_usd(rev.get('fees_24h_usd'), 0)} ({_pct(rev.get('fees_change_24h_pct'))}) | {_usd(rev.get('revenue_24h_usd'), 0)} |")
        add(f"| 7d | {_usd(rev.get('fees_7d_usd'), 0)} | {_usd(rev.get('revenue_7d_usd'), 0)} |")
        add(f"| 30d | {_usd(rev.get('fees_30d_usd'), 0)} | |")
        add("")
        add("> In-protocol fees only. Solana REV as usually quoted also includes out-of-protocol")
        add("> MEV tips, which no keyless source publishes — read this as the in-protocol floor.")
        add("")

    # -------------------------------------------------------------- validators
    add("## Validators")
    add("")
    add(f"- Active: **{_num(val.get('active_count'))}**")
    add(f"- Delinquent: **{_num(val.get('delinquent_count'))}** ({val.get('delinquent_pct', '—')}% of set)")
    add(f"- Superminority: **{_num(val.get('superminority_count'))}** validators hold a third of stake")
    add(f"- Total stake: **{_num(val.get('total_stake_sol'))} SOL**")
    add(f"- Median commission: **{val.get('median_commission', '—')}%**")
    add("")

    top = val.get("top_validators") or []
    if top:
        add("### Top validators by stake")
        add("")
        add("| Vote account | Stake (SOL) | Share | Commission |")
        add("|---|---|---|---|")
        for v in top:
            add(
                f"| `{str(v.get('vote_pubkey', ''))[:20]}…` | {_num(v.get('stake_sol'))} | "
                f"{_num(v.get('stake_pct'), 2)}% | {v.get('commission', '—')}% |"
            )
        add("")

    add("---")
    add("")
    add("Sources: Solana JSON-RPC · DeFiLlama · CoinGecko. No API keys required.")

    return "\n".join(lines) + "\n"
