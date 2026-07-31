# Solana Pulse

An automatically updating report on the state of the Solana ecosystem —
network health, validator set, economics and market data — rendered as an
interactive dashboard, a readable Markdown brief, and machine-readable JSON.

**Zero dependencies.** No `pip install`, no API keys, no accounts. If you have
Python 3.10+, you can run it.

```bash
python main.py
open out/index.html
```

---

## What it collects

| Area | Metrics | Source |
|---|---|---|
| Network | health, TPS, average slot time, slot, block height, epoch progress | Solana JSON-RPC |
| Validators | active vs delinquent, total stake, superminority size, median commission, top 10 by stake | Solana JSON-RPC |
| Supply | circulating / total / non-circulating SOL | Solana JSON-RPC |
| Market | SOL price, market cap, 24h/7d/30d moves, distance from ATH, 30-day series | CoinGecko (keyless) |
| DeFi | TVL with 30-day history, 24h and 7d change | DeFiLlama |
| Economy | stablecoin float on Solana, DEX volume 24h/7d | DeFiLlama |

RPC methods used: `getSlot`, `getBlockTime`, `getEpochInfo`,
`getRecentPerformanceSamples`, `getVoteAccounts`, `getSupply`, `getHealth`.

## Outputs

Every run writes three files to the output directory:

- **`index.html`** — dark interactive dashboard, one self-contained file with
  inline SVG charts. No CDN, no bundler, no charting library.
- **`report.md`** — human-readable brief with tables.
- **`report.json`** — full structured data, including the raw 30-day series.

## Automation

`.github/workflows/report.yml` runs the collector every six hours, publishes
the dashboard to GitHub Pages, and archives a dated JSON snapshot under
`history/`. Six hours keeps the data current while staying comfortably inside
public RPC rate limits.

The interval is the only knob: change the cron expression and nothing else
needs touching.

## Anomaly detection

Two strategies run together, because each covers the other's blind spot.

**Absolute thresholds** for metrics with a known healthy envelope — a chain
reporting 400 TPS is unwell regardless of what last week looked like:

| Check | Trigger |
|---|---|
| Throughput | TPS below 800 |
| Slot time | average above 0.65 s |
| Delinquency | more than 5% of validators delinquent |
| Concentration | fewer than 20 validators holding a third of stake |
| Health | RPC `getHealth` returns anything but `ok` |

**Z-scores against the trailing 30-day series** for metrics where only the
deviation carries meaning. A 12% TVL move says something different in a calm
week than in a volatile one, so SOL price and TVL are scored against their own
recent distribution and flagged past 2σ.

Thresholds alone miss regime changes. Z-scores alone go quiet during a slow,
sustained decline, because the baseline drifts down with the metric. Running
both is what makes the alerting trustworthy.

## Design decisions worth explaining

**No dependencies, deliberately.** Everything is `urllib` and `json` from the
standard library. A report that needs a working `pip`, a lockfile and an API
key is a report that stops running six months from now. This one keeps working
as long as Python and the public endpoints exist.

**Partial failure beats no report.** Each source is isolated. If CoinGecko
rate-limits or an RPC node goes down, that section renders as `—`, the failure
is recorded in `collection_failures`, and everything else still publishes. A
monitoring tool that goes dark exactly when the network is under stress is
worse than useless.

**Endpoint rotation with backoff.** Public RPC endpoints rate-limit
aggressively. The client retries with exponential backoff and rotates across
three endpoints, distinguishing retryable failures (429, 5xx, timeouts) from
permanent ones.

**Charts drawn, not imported.** The SVG sparklines are generated from the data
directly. No charting library means nothing to version-bump, nothing to break,
and an HTML file that renders identically from disk, from a static host, or
from an email attachment.

## Layout

```
main.py               orchestration and CLI
collect/
  rpc.py              Solana JSON-RPC client, endpoint rotation, metrics
  offchain.py         DeFiLlama and CoinGecko
analyze/
  anomaly.py          thresholds + z-scores
render/
  html.py             dark dashboard, inline SVG
  markdown.py         readable brief
.github/workflows/
  report.yml          6-hourly build and publish
```

## Requirements

Python 3.10 or newer. Nothing else.
