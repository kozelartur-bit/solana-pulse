"""Dark interactive HTML dashboard, emitted as one self-contained file.

No CDN, no build step, no external requests: the file opens from disk, from a
static host, or from an email attachment and looks identical. Charts are
inline SVG generated from the data, so there is no charting library to break.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from typing import Any

SEVERITY_COLOR = {"critical": "#ff5c5c", "warning": "#ffb648", "info": "#64b5f6"}


def _fmt_usd(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"${value / size:,.{digits}f}{unit}"
    return f"${value:,.{digits}f}"


def _fmt_num(value: Any, digits: int = 0) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:,.{digits}f}"


def _fmt_pct(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:+.2f}%"


def _delta_class(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "flat"
    return "up" if value > 0 else "down" if value < 0 else "flat"


def _sparkline(points: list[float], width: int = 560, height: int = 120) -> str:
    """Inline SVG line chart with a soft area fill."""
    clean = [p for p in points if isinstance(p, (int, float))]
    if len(clean) < 2:
        return '<p class="muted">Not enough data for a chart.</p>'

    low, high = min(clean), max(clean)
    span = (high - low) or 1.0
    step = width / (len(clean) - 1)

    coords = [
        (i * step, height - ((v - low) / span) * (height - 12) - 6)
        for i, v in enumerate(clean)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"0,{height} " + line + f" {width},{height}"

    rising = clean[-1] >= clean[0]
    stroke = "#64f0b0" if rising else "#ff7a7a"
    fill = "rgba(100,240,176,.14)" if rising else "rgba(255,122,122,.14)"

    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">'
        f'<polygon points="{area}" fill="{fill}"/>'
        f'<polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f"</svg>"
    )


def _stat(label: str, value: str, sub: str = "", delta: Any = None) -> str:
    delta_html = ""
    if delta is not None:
        delta_html = f'<span class="delta {_delta_class(delta)}">{_fmt_pct(delta)}</span>'
    sub_html = f'<div class="sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="stat"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{value} {delta_html}</div>{sub_html}</div>'
    )


def render(report: dict[str, Any]) -> str:
    net = report.get("network", {}) or {}
    val = report.get("validators", {}) or {}
    price = report.get("price", {}) or {}
    tvl = report.get("tvl", {}) or {}
    stables = report.get("stablecoins", {}) or {}
    dex = report.get("dex", {}) or {}
    sup = report.get("supply", {}) or {}
    alerts = report.get("alerts", []) or []
    generated = report.get("generated_at", "")

    # ------------------------------------------------------------- alert strip
    if alerts:
        items = "".join(
            f'<li style="border-left-color:{SEVERITY_COLOR.get(a["severity"], "#666")}">'
            f'<b>{html.escape(a["severity"].upper())}</b> {html.escape(a["message"])}</li>'
            for a in alerts
        )
        alert_block = f'<section class="card alerts"><h2>Anomalies detected</h2><ul>{items}</ul></section>'
    else:
        alert_block = (
            '<section class="card alerts ok"><h2>Anomalies detected</h2>'
            '<p class="muted">Nothing outside expected ranges in this run.</p></section>'
        )

    # ------------------------------------------------------------------ charts
    price_points = [p.get("price") for p in (report.get("price_history") or [])]
    tvl_points = [p.get("tvl") for p in (tvl.get("history_30d") or [])]

    # -------------------------------------------------------------- validators
    rows = "".join(
        f"<tr><td class='mono'>{html.escape(str(v.get('vote_pubkey', ''))[:16])}…</td>"
        f"<td>{_fmt_num(v.get('stake_sol'))}</td>"
        f"<td>{_fmt_num(v.get('stake_pct'), 2)}%</td>"
        f"<td>{_fmt_num(v.get('commission'))}%</td></tr>"
        for v in (val.get("top_validators") or [])
    )
    validator_table = (
        f"<table><thead><tr><th>Vote account</th><th>Stake (SOL)</th><th>Share</th><th>Commission</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        if rows
        else '<p class="muted">Validator data unavailable in this run.</p>'
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solana Pulse — ecosystem report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0a0b0d;--card:#111317;--line:#20242b;--fg:#e8eaed;--mid:#9aa1ab;--dim:#666d78;
  --accent:#64f0b0;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;padding:32px 20px 64px}}
.wrap{{max-width:1080px;margin:0 auto}}
header{{margin-bottom:28px}}
h1{{font-size:clamp(1.6rem,4vw,2.3rem);letter-spacing:-.03em;font-weight:600}}
.meta{{color:var(--dim);font-family:var(--mono);font-size:13px;margin-top:8px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:18px}}
h2{{font-size:1.05rem;font-weight:600;letter-spacing:-.01em;margin-bottom:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}}
.stat .label{{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}}
.stat .value{{font-size:1.5rem;font-weight:600;margin-top:6px;letter-spacing:-.02em}}
.stat .sub{{color:var(--mid);font-size:13px;margin-top:4px}}
.delta{{font-size:.85rem;font-weight:500}}
.delta.up{{color:var(--accent)}} .delta.down{{color:#ff7a7a}} .delta.flat{{color:var(--dim)}}
.spark{{width:100%;height:120px;display:block;margin-top:8px}}
.alerts ul{{list-style:none;display:grid;gap:10px}}
.alerts li{{border-left:3px solid;padding:10px 14px;background:#0d0f12;border-radius:0 8px 8px 0;font-size:14.5px}}
.alerts li b{{font-family:var(--mono);font-size:11px;letter-spacing:.08em;margin-right:8px;color:var(--mid)}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{text-align:left;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);padding-bottom:10px;border-bottom:1px solid var(--line)}}
td{{padding:9px 0;border-bottom:1px solid #171a1f}}
.mono{{font-family:var(--mono);font-size:13px;color:var(--mid)}}
.muted{{color:var(--dim);font-size:14px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
footer{{color:var(--dim);font-size:13px;margin-top:32px;font-family:var(--mono)}}
@media(max-width:760px){{.two{{grid-template-columns:1fr}}body{{padding:20px 14px 48px}}}}
</style></head><body><div class="wrap">

<header>
  <h1>Solana Pulse</h1>
  <div class="meta">Generated {html.escape(generated)} · auto-refreshing ecosystem report</div>
</header>

{alert_block}

<section class="card">
  <h2>Network</h2>
  <div class="grid">
    {_stat("Health", html.escape(str(net.get("health", "—"))))}
    {_stat("TPS", _fmt_num(net.get("tps"), 1), "10-sample average")}
    {_stat("Slot time", f'{net.get("avg_slot_time_sec", "—")}s' if net.get("avg_slot_time_sec") else "—")}
    {_stat("Slot", _fmt_num(net.get("slot")))}
    {_stat("Epoch", _fmt_num(net.get("epoch")), f'{net.get("epoch_progress_pct", "—")}% complete')}
    {_stat("Block height", _fmt_num(net.get("block_height")))}
  </div>
</section>

<div class="two">
  <section class="card">
    <h2>SOL price · 30 days</h2>
    <div class="grid">
      {_stat("Price", _fmt_usd(price.get("price_usd")), "", price.get("change_24h_pct"))}
      {_stat("Market cap", _fmt_usd(price.get("market_cap_usd"), 1))}
    </div>
    {_sparkline(price_points)}
  </section>

  <section class="card">
    <h2>TVL · 30 days</h2>
    <div class="grid">
      {_stat("TVL", _fmt_usd(tvl.get("tvl_usd"), 1), "", tvl.get("change_24h_pct"))}
      {_stat("7-day change", _fmt_pct(tvl.get("change_7d_pct")))}
    </div>
    {_sparkline(tvl_points)}
  </section>
</div>

<section class="card">
  <h2>Economy</h2>
  <div class="grid">
    {_stat("Stablecoin supply", _fmt_usd(stables.get("total_usd"), 1))}
    {_stat("DEX volume 24h", _fmt_usd(dex.get("volume_24h_usd"), 1), "", dex.get("change_24h_pct"))}
    {_stat("DEX volume 7d", _fmt_usd(dex.get("volume_7d_usd"), 1))}
    {_stat("Circulating SOL", _fmt_num(sup.get("circulating_sol")))}
    {_stat("SOL 7d", _fmt_pct(price.get("change_7d_pct")))}
    {_stat("SOL 30d", _fmt_pct(price.get("change_30d_pct")))}
  </div>
</section>

<section class="card">
  <h2>Validators</h2>
  <div class="grid" style="margin-bottom:20px">
    {_stat("Active", _fmt_num(val.get("active_count")))}
    {_stat("Delinquent", _fmt_num(val.get("delinquent_count")), f'{val.get("delinquent_pct", "—")}% of set')}
    {_stat("Superminority", _fmt_num(val.get("superminority_count")), "validators holding 1/3 of stake")}
    {_stat("Total stake", f'{_fmt_num(val.get("total_stake_sol"))} SOL')}
  </div>
  {validator_table}
</section>

<footer>
  Sources: Solana JSON-RPC · DeFiLlama · CoinGecko. No API keys required.<br>
  Raw data: <a href="report.json" style="color:var(--accent)">report.json</a> ·
  <a href="report.md" style="color:var(--accent)">report.md</a>
</footer>

</div></body></html>"""
