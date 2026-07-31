"""Smoke tests. Run with `python test_report.py` — no pytest, no installs.

These check the parts that break silently. Network collection is not tested
against live endpoints on purpose: a test that fails because CoinGecko is
rate-limited teaches nothing. What is tested is that the analysis and render
layers behave correctly given data, including when that data is missing.
"""

from __future__ import annotations

import json
import sys

from analyze import anomaly
from render import html as html_render
from render import markdown as md_render

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def sample_report() -> dict:
    return {
        "generated_at": "2026-08-01 00:00 UTC",
        "network": {"health": "ok", "tps": 3200.0, "avg_slot_time_sec": 0.42, "slot": 1, "epoch": 1},
        "validators": {"active_count": 700, "delinquent_count": 10, "delinquent_pct": 1.4,
                       "superminority_count": 25, "top_validators": []},
        "price": {"price_usd": 70.0, "change_24h_pct": -1.0},
        "price_history": [{"ts": 1, "price": 70.0 + i} for i in range(30)],
        "tvl": {"tvl_usd": 4.0e9, "change_24h_pct": -0.5, "history_30d": []},
        "supply": {}, "stablecoins": {}, "dex": {}, "fees": {},
        "activity": {}, "revenue": {}, "protocols": [], "categories": [],
        "tokenized": {}, "roadmap": [], "client_releases": [], "merged_simds": [],
    }


def test_healthy_report_is_quiet() -> None:
    alerts = anomaly.detect(sample_report())
    critical = [a for a in alerts if a["severity"] == "critical"]
    check("healthy metrics raise no critical alert", not critical, str(critical))


def test_thresholds_fire() -> None:
    report = sample_report()
    report["network"]["tps"] = 100.0
    report["validators"]["delinquent_pct"] = 20.0
    metrics = {a["metric"] for a in anomaly.detect(report)}
    check("low TPS is flagged", "tps" in metrics, str(metrics))
    check("high delinquency is flagged", "delinquency" in metrics, str(metrics))


def test_alerts_sorted_by_severity() -> None:
    report = sample_report()
    report["network"]["health"] = "behind"
    report["network"]["tps"] = 100.0
    alerts = anomaly.detect(report)
    order = [a["severity"] for a in alerts]
    rank = {"critical": 0, "warning": 1, "info": 2}
    check("alerts sorted most severe first", order == sorted(order, key=lambda s: rank[s]), str(order))


def test_renders_with_missing_sections() -> None:
    """The whole point of isolated collection: a hole must not crash rendering."""
    sparse = {"generated_at": "now", "alerts": []}
    try:
        page = html_render.render(sparse)
        text = md_render.render(sparse)
    except Exception as exc:  # noqa: BLE001
        check("renders when every source failed", False, repr(exc))
        return
    check("HTML renders from empty report", "<html" in page and len(page) > 1000)
    check("Markdown renders from empty report", "# Solana Pulse" in text)


def test_html_is_self_contained() -> None:
    page = html_render.render(sample_report())
    for needle in ("http://", "src=\"//", "cdn."):
        check(f"no external resource ({needle!r})", needle not in page)
    check("chart series is valid JSON", '"v":' in page or "data-series" in page)


def test_sparkline_handles_short_series() -> None:
    check("single point does not crash", "Not enough data" in html_render._sparkline([1.0]))
    check("empty series does not crash", "Not enough data" in html_render._sparkline([]))


def test_json_is_serialisable() -> None:
    try:
        json.dumps(sample_report())
    except (TypeError, ValueError) as exc:
        check("report serialises to JSON", False, repr(exc))
        return
    check("report serialises to JSON", True)


def main() -> int:
    print("Solana Pulse — smoke tests\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
