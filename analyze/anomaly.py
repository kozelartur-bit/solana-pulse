"""Anomaly detection over collected metrics.

Two complementary strategies:

* **Absolute thresholds** for things where the healthy range is known in
  advance — a chain reporting 400 TPS is unwell regardless of history.
* **Z-scores against the recent series** for things where only the deviation
  matters — a 12% TVL move means something different in a calm week than a
  volatile one.

Both are needed. Thresholds alone miss regime changes; z-scores alone stay
silent during a slow, sustained decline because the baseline drifts with it.
"""

from __future__ import annotations

import statistics
from typing import Any

# Absolute bounds. Chosen from Solana's normal operating envelope rather than
# from theory — these are the values at which an operator would start looking.
THRESHOLDS = {
    "tps_low": 800.0,
    "slot_time_high_sec": 0.65,
    "delinquent_pct_high": 5.0,
    "superminority_low": 20,
}

Z_ALERT = 2.0  # standard deviations before a series move is called unusual


def _z_score(value: float, series: list[float]) -> float | None:
    """Standard score of `value` against `series`. None when undefined."""
    clean = [x for x in series if isinstance(x, (int, float))]
    if len(clean) < 5:
        return None
    mean = statistics.fmean(clean)
    try:
        stdev = statistics.stdev(clean)
    except statistics.StatisticsError:
        return None
    if stdev == 0:
        return None
    return (value - mean) / stdev


def _alert(severity: str, metric: str, message: str, value: Any = None) -> dict[str, Any]:
    return {"severity": severity, "metric": metric, "message": message, "value": value}


def detect(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return alerts ordered most severe first."""
    alerts: list[dict[str, Any]] = []

    network = report.get("network", {}) or {}
    validators = report.get("validators", {}) or {}
    price = report.get("price", {}) or {}
    tvl = report.get("tvl", {}) or {}

    # ---------------------------------------------------------------- network

    if network.get("health") not in (None, "ok", "unknown"):
        alerts.append(_alert("critical", "health", f"RPC reports health: {network['health']}", network.get("health")))

    tps = network.get("tps")
    if isinstance(tps, (int, float)) and tps < THRESHOLDS["tps_low"]:
        alerts.append(
            _alert("warning", "tps", f"Throughput {tps} TPS is below the {THRESHOLDS['tps_low']:.0f} TPS floor", tps)
        )

    slot_time = network.get("avg_slot_time_sec")
    if isinstance(slot_time, (int, float)) and slot_time > THRESHOLDS["slot_time_high_sec"]:
        alerts.append(
            _alert("warning", "slot_time", f"Average slot time {slot_time}s exceeds {THRESHOLDS['slot_time_high_sec']}s", slot_time)
        )

    # ------------------------------------------------------------- validators

    delinquent = validators.get("delinquent_pct")
    if isinstance(delinquent, (int, float)) and delinquent > THRESHOLDS["delinquent_pct_high"]:
        alerts.append(
            _alert("critical", "delinquency", f"{delinquent}% of validators are delinquent", delinquent)
        )

    superminority = validators.get("superminority_count")
    if isinstance(superminority, int) and superminority < THRESHOLDS["superminority_low"]:
        alerts.append(
            _alert(
                "warning",
                "superminority",
                f"Only {superminority} validators control a third of stake — concentration risk",
                superminority,
            )
        )

    # ------------------------------------------------------------------ price

    history = report.get("price_history") or []
    closes = [p.get("price") for p in history if isinstance(p.get("price"), (int, float))]
    current_price = price.get("price_usd")
    if isinstance(current_price, (int, float)) and closes:
        z = _z_score(current_price, closes[:-1] or closes)
        if z is not None and abs(z) >= Z_ALERT:
            direction = "above" if z > 0 else "below"
            alerts.append(
                _alert(
                    "info",
                    "sol_price",
                    f"SOL is {abs(z):.1f}σ {direction} its 30-day mean",
                    round(z, 2),
                )
            )

    change_24h = price.get("change_24h_pct")
    if isinstance(change_24h, (int, float)) and abs(change_24h) >= 10:
        alerts.append(
            _alert("info", "sol_price_24h", f"SOL moved {change_24h:+.1f}% in 24h", round(change_24h, 2))
        )

    # -------------------------------------------------------------------- TVL

    tvl_series = [p.get("tvl") for p in (tvl.get("history_30d") or []) if isinstance(p.get("tvl"), (int, float))]
    if tvl.get("tvl_usd") and len(tvl_series) > 5:
        z = _z_score(tvl.get("tvl_usd"), tvl_series[:-1])
        if z is not None and abs(z) >= Z_ALERT:
            direction = "above" if z > 0 else "below"
            alerts.append(_alert("info", "tvl", f"TVL is {abs(z):.1f}σ {direction} its 30-day mean", round(z, 2)))

    change_tvl = tvl.get("change_24h_pct")
    if isinstance(change_tvl, (int, float)) and abs(change_tvl) >= 8:
        alerts.append(_alert("warning", "tvl_24h", f"TVL moved {change_tvl:+.1f}% in 24h", round(change_tvl, 2)))

    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 9))
    return alerts
