"""Solana Pulse — collect, analyse, render.

Run:
    python main.py                 # write into ./out
    python main.py --out public    # write somewhere else
    python main.py --quiet         # no progress output

Requires nothing but a Python 3.10+ install. No API keys, no pip install.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from analyze import anomaly
from collect import ecosystem, offchain, rpc
from render import html as html_render
from render import markdown as md_render


def _log(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


def build_report(verbose: bool = True) -> dict[str, Any]:  # type: ignore[name-defined]
    client = rpc.SolanaRPC()
    report: dict = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    # Each source is isolated: a dead endpoint costs one section, not the run.
    steps = (
        ("network", lambda: rpc.network_health(client)),
        ("validators", lambda: rpc.validator_status(client)),
        ("supply", lambda: rpc.supply(client)),
        ("fees", lambda: ecosystem.fees(client)),
        ("activity", lambda: rpc.active_addresses(client)),
        ("revenue", ecosystem.revenue),
        ("price", offchain.coingecko_sol),
        ("price_history", offchain.coingecko_sol_sparkline),
        ("tvl", offchain.defillama_tvl),
        ("stablecoins", offchain.defillama_stablecoins),
        ("dex", offchain.defillama_dex_volume),
        ("protocols", ecosystem.top_protocols),
        ("categories", ecosystem.category_breakdown),
        ("tokenized", ecosystem.tokenized_assets),
        ("roadmap", ecosystem.roadmap),
    )

    failures: list[str] = []
    for name, fn in steps:
        _log(verbose, f"  collecting {name} …")
        try:
            report[name] = fn()
        except Exception as exc:  # noqa: BLE001 - report must survive any source
            failures.append(f"{name}: {exc}")
            report[name] = {} if name != "price_history" else []
            _log(verbose, f"    ! {name} failed: {exc}")

    report["collection_failures"] = failures
    _log(verbose, "  detecting anomalies …")
    report["alerts"] = anomaly.detect(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Solana ecosystem report.")
    parser.add_argument("--out", default="out", help="output directory (default: out)")
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = parser.parse_args()

    verbose = not args.quiet
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    _log(verbose, "Solana Pulse")
    try:
        report = build_report(verbose)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1

    _log(verbose, "  rendering …")
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(md_render.render(report), encoding="utf-8")
    (out / "index.html").write_text(html_render.render(report), encoding="utf-8")

    alerts = report.get("alerts", [])
    _log(verbose, f"\nWrote {out/'index.html'}, report.md, report.json")
    _log(verbose, f"Anomalies: {len(alerts)}")
    for a in alerts:
        _log(verbose, f"  [{a['severity']}] {a['message']}")
    if report.get("collection_failures"):
        _log(verbose, f"Partial data — {len(report['collection_failures'])} source(s) failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
