"""Solana JSON-RPC client built on the standard library only.

No third-party packages, no API keys. Public RPC endpoints are rate limited,
so every call goes through a retry/backoff path and the client falls back to
the next endpoint in the list when one starts refusing traffic.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

# Public endpoints, tried in order. The first is the canonical one; the rest
# exist so a single rate-limited host cannot take the whole report down.
DEFAULT_ENDPOINTS = (
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
    "https://rpc.ankr.com/solana",
)

USER_AGENT = "solana-pulse/1.0 (+https://github.com/)"


class RpcError(RuntimeError):
    """Raised when every endpoint failed for a given call."""


class SolanaRPC:
    def __init__(
        self,
        endpoints: tuple[str, ...] = DEFAULT_ENDPOINTS,
        timeout: float = 20.0,
        max_attempts: int = 4,
        base_backoff: float = 1.5,
    ) -> None:
        self.endpoints = list(endpoints)
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self._id = 0

    # ---------------------------------------------------------------- internals

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------- public

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        """Invoke an RPC method, rotating endpoints and backing off on failure."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or [],
        }

        last_error: Exception | None = None

        for attempt in range(self.max_attempts):
            endpoint = self.endpoints[attempt % len(self.endpoints)]
            try:
                data = self._post(endpoint, payload)
            except urllib.error.HTTPError as exc:
                # 429 and 5xx are worth retrying elsewhere; 4xx usually is not.
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            else:
                if "error" in data:
                    last_error = RpcError(f"{method}: {data['error']}")
                else:
                    return data.get("result")

            if attempt < self.max_attempts - 1:
                time.sleep(self.base_backoff * (2**attempt))

        raise RpcError(f"{method} failed on all endpoints: {last_error}")

    def try_call(self, method: str, params: list[Any] | None = None, default: Any = None) -> Any:
        """Same as call() but degrades to `default` instead of raising.

        The report is worth more with a hole in it than not generated at all,
        so collection never lets one dead metric abort the run.
        """
        try:
            return self.call(method, params)
        except RpcError:
            return default


# --------------------------------------------------------------------- metrics

def network_health(rpc: SolanaRPC) -> dict[str, Any]:
    """Slot, block time, epoch progress and recent throughput."""
    slot = rpc.try_call("getSlot")
    epoch = rpc.try_call("getEpochInfo") or {}
    samples = rpc.try_call("getRecentPerformanceSamples", [10]) or []
    health = rpc.try_call("getHealth", default="unknown")

    block_time = rpc.try_call("getBlockTime", [slot]) if slot else None

    tps = None
    avg_slot_time = None
    if samples:
        # Each sample covers samplePeriodSecs of wall clock.
        total_tx = sum(s.get("numTransactions", 0) for s in samples)
        total_secs = sum(s.get("samplePeriodSecs", 0) for s in samples)
        total_slots = sum(s.get("numSlots", 0) for s in samples)
        if total_secs:
            tps = round(total_tx / total_secs, 1)
        if total_slots:
            avg_slot_time = round(total_secs / total_slots, 3)

    epoch_progress = None
    if epoch.get("slotsInEpoch"):
        epoch_progress = round(
            100.0 * epoch.get("slotIndex", 0) / epoch["slotsInEpoch"], 2
        )

    return {
        "health": health,
        "slot": slot,
        "block_height": epoch.get("blockHeight"),
        "block_time_unix": block_time,
        "epoch": epoch.get("epoch"),
        "epoch_progress_pct": epoch_progress,
        "slots_in_epoch": epoch.get("slotsInEpoch"),
        "tps": tps,
        "avg_slot_time_sec": avg_slot_time,
    }


def validator_status(rpc: SolanaRPC) -> dict[str, Any]:
    """Active vs delinquent validators, stake concentration, top operators."""
    accounts = rpc.try_call("getVoteAccounts") or {}
    current = accounts.get("current", []) or []
    delinquent = accounts.get("delinquent", []) or []

    def stake_of(v: dict[str, Any]) -> int:
        return int(v.get("activatedStake", 0) or 0)

    total_stake = sum(stake_of(v) for v in current) + sum(stake_of(v) for v in delinquent)
    ranked = sorted(current, key=stake_of, reverse=True)

    def pct(value: int) -> float | None:
        return round(100.0 * value / total_stake, 2) if total_stake else None

    # Nakamoto-style concentration: how many validators hold a third of stake.
    superminority = 0
    running = 0
    for v in ranked:
        running += stake_of(v)
        superminority += 1
        if total_stake and running >= total_stake / 3:
            break

    top = [
        {
            "vote_pubkey": v.get("votePubkey"),
            "stake_sol": round(stake_of(v) / 1e9, 2),
            "stake_pct": pct(stake_of(v)),
            "commission": v.get("commission"),
        }
        for v in ranked[:10]
    ]

    commissions = [v.get("commission") for v in current if v.get("commission") is not None]

    return {
        "active_count": len(current),
        "delinquent_count": len(delinquent),
        "delinquent_pct": round(100.0 * len(delinquent) / (len(current) + len(delinquent)), 2)
        if (current or delinquent)
        else None,
        "total_stake_sol": round(total_stake / 1e9, 2) if total_stake else None,
        "superminority_count": superminority if total_stake else None,
        "median_commission": sorted(commissions)[len(commissions) // 2] if commissions else None,
        "top_validators": top,
    }


def supply(rpc: SolanaRPC) -> dict[str, Any]:
    """Circulating and total SOL supply."""
    result = rpc.try_call("getSupply", [{"excludeNonCirculatingAccountsList": True}]) or {}
    value = result.get("value", {}) if isinstance(result, dict) else {}
    circulating = value.get("circulating")
    total = value.get("total")
    return {
        "circulating_sol": round(circulating / 1e9, 2) if circulating else None,
        "total_sol": round(total / 1e9, 2) if total else None,
        "non_circulating_sol": round(value.get("nonCirculating", 0) / 1e9, 2)
        if value.get("nonCirculating")
        else None,
    }
