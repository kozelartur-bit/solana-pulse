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


def _sparkline(
    points: list[float],
    labels: list[str] | None = None,
    prefix: str = "$",
    width: int = 560,
    height: int = 120,
) -> str:
    """Inline SVG line chart with a soft area fill and a hover readout.

    The series is embedded as JSON on the wrapper so the page script can show
    values on hover without pulling in a charting library.
    """
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

    series = json.dumps(
        [
            {"v": round(v, 4), "l": (labels[i] if labels and i < len(labels) else "")}
            for i, v in enumerate(clean)
        ]
    )

    return (
        f'<div class="chart" data-series="{html.escape(series, quote=True)}" '
        f'data-prefix="{html.escape(prefix)}">'
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" '
        f'aria-label="{len(clean)}-point trend chart">'
        f'<polygon points="{area}" fill="{fill}"/>'
        f'<polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<line class="cursor" x1="0" y1="0" x2="0" y2="{height}" stroke="#5a6270" '
        f'stroke-width="1" stroke-dasharray="3 3" opacity="0"/>'
        f"</svg>"
        f'<div class="tip" hidden></div>'
        f"</div>"
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
    fees = report.get("fees", {}) or {}
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
    price_hist = report.get("price_history") or []
    price_points = [p.get("price") for p in price_hist]
    price_labels = [
        dt.datetime.fromtimestamp(p["ts"], dt.timezone.utc).strftime("%d %b")
        if isinstance(p.get("ts"), (int, float))
        else ""
        for p in price_hist
    ]

    tvl_hist = tvl.get("history_30d") or []
    tvl_points = [p.get("tvl") for p in tvl_hist]
    tvl_labels = [
        dt.datetime.fromtimestamp(p["date"], dt.timezone.utc).strftime("%d %b")
        if isinstance(p.get("date"), (int, float))
        else ""
        for p in tvl_hist
    ]

    # -------------------------------------------------------------------- news
    release_rows = "".join(
        f'<tr><td>{html.escape(str(r.get("client", "")))}</td>'
        f'<td class="mono"><a href="{html.escape(str(r.get("url", "")))}" target="_blank" rel="noopener">'
        f'{html.escape(str(r.get("tag", "")))}</a></td>'
        f'<td>{"pre-release" if r.get("prerelease") else "stable"}</td>'
        f'<td>{r.get("age_days")}d ago</td></tr>'
        for r in (report.get("client_releases") or [])[:6]
    )
    simd_rows = "".join(
        f'<tr><td class="mono">#{r.get("number")}</td>'
        f'<td><a href="{html.escape(str(r.get("url", "")))}" target="_blank" rel="noopener">'
        f'{html.escape(str(r.get("title", ""))[:90])}</a></td>'
        f'<td>{r.get("age_days")}d ago</td></tr>'
        for r in (report.get("merged_simds") or [])
    )
    news_note = (
        '<p class="note">Read from primary sources: the client release feeds and the SIMD '
        "repository, rather than social media. A tweet announcing a release is downstream of the "
        "release itself, and Twitter has no keyless read API anyway.</p>"
    )
    news_block = (
        '<section class="card"><h2>Ecosystem news</h2>'
        '<h3 class="sub-h">Validator client releases</h3>'
        '<table class="sortable"><thead><tr><th>Client</th><th>Release</th>'
        "<th>Channel</th><th>Age</th></tr></thead>"
        f"<tbody>{release_rows}</tbody></table>"
        '<h3 class="sub-h">Recently merged protocol proposals</h3>'
        '<table class="sortable"><thead><tr><th>SIMD</th><th>Title</th><th>Merged</th></tr></thead>'
        f"<tbody>{simd_rows}</tbody></table>"
        f"{news_note}</section>"
        if (release_rows or simd_rows)
        else ""
    )

    # -------------------------------------------------------------- validators
    rows = "".join(
        f"<tr><td class='mono'>{html.escape(str(v.get('vote_pubkey', ''))[:16])}…</td>"
        f"<td>{_fmt_num(v.get('stake_sol'))}</td>"
        f"<td>{_fmt_num(v.get('stake_pct'), 2)}%</td>"
        f"<td>{_fmt_num(v.get('commission'))}%</td></tr>"
        for v in (val.get("top_validators") or [])
    )
    validator_table = (
        f'<table class="sortable"><thead><tr><th>Vote account</th><th>Stake (SOL)</th><th>Share</th><th>Commission</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        if rows
        else '<p class="muted">Validator data unavailable in this run.</p>'
    )

    # -------------------------------------------------- activity and economics
    act = report.get("activity") or {}
    rev = report.get("revenue") or {}

    if act.get("estimate_available"):
        activity_note = (
            '<p class="note">Measured, not extrapolated. Multiplying per-block distinct payers by '
            "slots per day would assume each block has a fresh population — the repeat rate above "
            "shows it does not, and that arithmetic overstates daily actives by roughly two orders "
            "of magnitude. A true daily figure needs a full indexer, which this report deliberately "
            f"is not. {html.escape(str(act.get('method', '')))}</p>"
        )
        activity_block = f"""<section class="card">
  <h2>On-chain activity</h2>
  <div class="grid">
    {_stat("Distinct payers / block", _fmt_num(act.get("avg_unique_payers_per_block"), 1), "average across sample")}
    {_stat("Distinct in sample", _fmt_num(act.get("unique_payers_in_sample")), f'{act.get("sampled_blocks", "—")} blocks')}
    {_stat("Repeat rate", f'{act.get("repeat_rate_pct", "—")}%', "addresses seen in more than one block")}
    {_stat("Transactions / block", _fmt_num(act.get("avg_transactions_per_block"), 1))}
  </div>
  {activity_note}
</section>"""
    else:
        activity_block = ""

    revenue_block = (
        f"""<section class="card">
  <h2>Real economic value</h2>
  <div class="grid">
    {_stat("Fees 24h", _fmt_usd(rev.get("fees_24h_usd"), 0), "base + priority", rev.get("fees_change_24h_pct"))}
    {_stat("Fees 7d", _fmt_usd(rev.get("fees_7d_usd"), 0))}
    {_stat("Fees 30d", _fmt_usd(rev.get("fees_30d_usd"), 0))}
    {_stat("Revenue 24h", _fmt_usd(rev.get("revenue_24h_usd"), 0), "base fees only")}
  </div>
  <p class="note">{html.escape(str(rev.get("note", "")))} Solana REV as usually quoted also includes
  out-of-protocol MEV tips, which no keyless source publishes — read this as the in-protocol floor.</p>
</section>"""
        if rev.get("fees_24h_usd") is not None
        else ""
    )

    # ---------------------------------------------------------------- protocols
    proto_rows = "".join(
        f"<tr><td>{html.escape(str(p.get('name','')))}</td>"
        f"<td class='mono'>{html.escape(str(p.get('category','')))}</td>"
        f"<td>{_fmt_usd(p.get('tvl_usd'), 1)}</td>"
        f"<td class='{_delta_class(p.get('change_1d_pct'))}'>{_fmt_pct(p.get('change_1d_pct'))}</td>"
        f"<td class='{_delta_class(p.get('change_7d_pct'))}'>{_fmt_pct(p.get('change_7d_pct'))}</td></tr>"
        for p in (report.get("protocols") or [])
    )
    methodology_note = (
        '<p class="note">Centralised exchange and bridge custody are excluded: they hold assets '
        "on Solana but are not Solana DeFi. Protocol totals also exceed the chain TVL figure above, "
        "because DeFiLlama keeps liquid staking out of headline chain TVL to avoid double counting "
        "stake that is already represented in the validator section. Both numbers are correct; they "
        "answer different questions.</p>"
    )
    protocols_block = (
        f'<section class="card"><h2>Top DeFi protocols by TVL</h2>'
        f'<table class="sortable"><thead><tr><th>Protocol</th><th>Category</th><th>TVL</th><th>24h</th><th>7d</th></tr></thead>'
        f"<tbody>{proto_rows}</tbody></table>{methodology_note}</section>"
        if proto_rows
        else ""
    )

    # --------------------------------------------------------------- categories
    cats = report.get("categories") or []
    cat_bars = "".join(
        f'<div class="bar-row"><span class="bar-label">{html.escape(str(c.get("category","")))}</span>'
        f'<span class="bar"><i style="width:{min(100.0, c.get("share_pct") or 0):.1f}%"></i></span>'
        f'<span class="bar-val">{_fmt_usd(c.get("tvl_usd"), 1)} · {c.get("share_pct")}%</span></div>'
        for c in cats
    )
    categories_block = (
        f'<section class="card"><h2>Where TVL sits</h2><div class="bars">{cat_bars}</div></section>'
        if cat_bars
        else ""
    )

    # ---------------------------------------------------------------- tokenized
    tok = report.get("tokenized") or {}
    tok_rows = "".join(
        f"<tr><td>{html.escape(str(p.get('name','')))}</td><td>{_fmt_usd(p.get('tvl_usd'), 1)}</td></tr>"
        for p in (tok.get("protocols") or [])
    )
    tokenized_block = (
        f'<section class="card"><h2>Tokenized real-world assets</h2>'
        f'<div class="grid" style="margin-bottom:16px">{_stat("RWA on Solana", _fmt_usd(tok.get("total_usd"), 1))}</div>'
        f'<table class="sortable"><thead><tr><th>Protocol</th><th>TVL</th></tr></thead><tbody>{tok_rows}</tbody></table></section>'
        if tok_rows
        else ""
    )

    # ------------------------------------------------------------------ roadmap
    road_items = "".join(
        f'<div class="road"><div class="road-head"><b>{html.escape(str(r.get("name","")))}</b>'
        f'<span class="tag">{html.escape(str(r.get("status","")))}</span></div>'
        f'<div class="road-kind">{html.escape(str(r.get("kind","")))}</div>'
        f'<p>{html.escape(str(r.get("summary","")))}</p>'
        f'<p class="why"><b>Why it matters:</b> {html.escape(str(r.get("why_it_matters","")))}</p></div>'
        for r in (report.get("roadmap") or [])
    )
    roadmap_block = (
        f'<section class="card"><h2>Upcoming upgrades</h2><div class="roads">{road_items}</div></section>'
        if road_items
        else ""
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
.note{{color:var(--dim);font-size:12.5px;line-height:1.6;margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
td.up{{color:var(--accent)}} td.down{{color:#ff7a7a}} td.flat{{color:var(--dim)}}
.bars{{display:grid;gap:10px}}
.bar-row{{display:grid;grid-template-columns:150px 1fr 190px;gap:12px;align-items:center;font-size:13.5px}}
.bar-label{{color:var(--mid)}}
.bar{{background:#181b20;border-radius:4px;height:9px;overflow:hidden;display:block}}
.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#3fbd88);border-radius:4px}}
.bar-val{{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:right}}
.roads{{display:grid;gap:14px}}
.road{{background:#0d0f12;border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.road-head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.road-head b{{font-size:15px}}
.tag{{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);border:1px solid #2f7d5e;border-radius:99px;padding:2px 9px}}
.road-kind{{font-family:var(--mono);font-size:11.5px;color:var(--dim);margin:4px 0 8px}}
.road p{{font-size:13.5px;color:var(--mid);margin-bottom:6px}}
.road .why{{color:var(--dim);font-size:13px}}
.road .why b{{color:var(--mid)}}
.sub-h{{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);font-weight:500;margin:20px 0 10px}}
.sub-h:first-of-type{{margin-top:0}}
td a{{color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line)}}
td a:hover{{color:var(--accent);border-color:var(--accent)}}
.chart{{position:relative}}
table.sortable th{{cursor:pointer;user-select:none}}
table.sortable th:hover{{color:var(--accent)}}
table.sortable th.asc::after{{content:"  \\25B2"}}
table.sortable th.desc::after{{content:"  \\25BC"}}
.tip{{position:absolute;pointer-events:none;background:#191d23;border:1px solid var(--line);border-radius:7px;padding:6px 10px;font-family:var(--mono);font-size:12px;color:var(--fg);white-space:nowrap;transform:translate(-50%,-115%);z-index:5;box-shadow:0 4px 16px rgba(0,0,0,.5)}}
.tip b{{color:var(--accent)}}
footer{{color:var(--dim);font-size:13px;margin-top:32px;font-family:var(--mono)}}
@media(max-width:900px){{.bar-row{{grid-template-columns:110px 1fr;gap:8px}}.bar-val{{grid-column:1/-1;text-align:left}}}}
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
    {_sparkline(price_points, price_labels)}
  </section>

  <section class="card">
    <h2>TVL · 30 days</h2>
    <div class="grid">
      {_stat("TVL", _fmt_usd(tvl.get("tvl_usd"), 1), "", tvl.get("change_24h_pct"))}
      {_stat("7-day change", _fmt_pct(tvl.get("change_7d_pct")))}
    </div>
    {_sparkline(tvl_points, tvl_labels)}
  </section>
</div>

<section class="card">
  <h2>Economy</h2>
  <div class="grid">
    {_stat("Stablecoin supply", _fmt_usd(stables.get("total_usd"), 1))}
    {_stat("DEX volume 24h", _fmt_usd(dex.get("volume_24h_usd"), 1), "", dex.get("change_24h_pct"))}
    {_stat("DEX volume 7d", _fmt_usd(dex.get("volume_7d_usd"), 1))}
    {_stat("Circulating SOL", _fmt_num(sup.get("circulating_sol")))}
    {_stat("Median priority fee", _fmt_num(fees.get("median_priority_fee")), "micro-lamports / CU")}
    {_stat("p90 priority fee", _fmt_num(fees.get("p90_priority_fee")), f'{fees.get("zero_fee_share_pct", "—")}% of slots at zero')}
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

{activity_block}
{revenue_block}
{protocols_block}
{categories_block}
{tokenized_block}
{news_block}
{roadmap_block}

<footer>
  Sources: Solana JSON-RPC · DeFiLlama · CoinGecko. No API keys required.<br>
  Raw data: <a href="report.json" style="color:var(--accent)">report.json</a> ·
  <a href="report.md" style="color:var(--accent)">report.md</a>
</footer>

</div>

<script>
// Hover readout on the charts. No charting library: each wrapper carries its
// own series as JSON and the handler reads it back.
document.querySelectorAll('.chart').forEach(function (chart) {{
  var series;
  try {{ series = JSON.parse(chart.dataset.series || '[]'); }} catch (e) {{ return; }}
  if (series.length < 2) return;

  var svg = chart.querySelector('svg');
  var tip = chart.querySelector('.tip');
  var cursor = chart.querySelector('.cursor');
  var prefix = chart.dataset.prefix || '';
  var vbWidth = svg.viewBox.baseVal.width;

  function format(value) {{
    var abs = Math.abs(value);
    if (abs >= 1e9) return prefix + (value / 1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return prefix + (value / 1e6).toFixed(2) + 'M';
    if (abs >= 1e3) return prefix + (value / 1e3).toFixed(2) + 'K';
    return prefix + value.toFixed(2);
  }}

  function move(event) {{
    var rect = svg.getBoundingClientRect();
    var clientX = event.touches ? event.touches[0].clientX : event.clientX;
    var ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    var index = Math.round(ratio * (series.length - 1));
    var point = series[index];
    if (!point) return;

    tip.hidden = false;
    tip.innerHTML = (point.l ? point.l + ' &middot; ' : '') + '<b>' + format(point.v) + '</b>';
    tip.style.left = (index / (series.length - 1)) * rect.width + 'px';
    tip.style.top = rect.height + 'px';

    var x = (index / (series.length - 1)) * vbWidth;
    cursor.setAttribute('x1', x);
    cursor.setAttribute('x2', x);
    cursor.setAttribute('opacity', '1');
  }}

  function leave() {{
    tip.hidden = true;
    cursor.setAttribute('opacity', '0');
  }}

  svg.addEventListener('mousemove', move);
  svg.addEventListener('touchmove', move, {{ passive: true }});
  svg.addEventListener('mouseleave', leave);
  svg.addEventListener('touchend', leave);
}});

// Click a column header to sort. Numeric when the cell parses as a number,
// alphabetical otherwise.
document.querySelectorAll('table.sortable').forEach(function (table) {{
  var headers = table.querySelectorAll('th');
  headers.forEach(function (header, index) {{
    header.addEventListener('click', function () {{
      var body = table.tBodies[0];
      if (!body) return;
      var rows = Array.prototype.slice.call(body.rows);
      var descending = !header.classList.contains('desc');

      headers.forEach(function (h) {{ h.classList.remove('asc', 'desc'); }});
      header.classList.add(descending ? 'desc' : 'asc');

      // Cells carry formatted values ("$1.1B", "904.4M", "12d ago"), so the
      // magnitude suffix has to be honoured. Stripping it and comparing the
      // bare digits would sort $904.4M above $1.1B.
      var SCALE = {{ k: 1e3, m: 1e6, b: 1e9, t: 1e12 }};

      function keyOf(row) {{
        var cell = row.cells[index];
        var text = cell ? cell.innerText.trim() : '';
        var match = text.match(/-?[\\d,]*\\.?\\d+/);
        if (!match) return text.toLowerCase();

        var numeric = parseFloat(match[0].replace(/,/g, ''));
        if (isNaN(numeric)) return text.toLowerCase();

        var suffix = (text.charAt(text.indexOf(match[0]) + match[0].length) || '').toLowerCase();
        return SCALE[suffix] ? numeric * SCALE[suffix] : numeric;
      }}

      rows.sort(function (a, b) {{
        var ka = keyOf(a), kb = keyOf(b);
        if (ka < kb) return descending ? 1 : -1;
        if (ka > kb) return descending ? -1 : 1;
        return 0;
      }});

      rows.forEach(function (row) {{ body.appendChild(row); }});
    }});
  }});
}});
</script>
</body></html>"""
