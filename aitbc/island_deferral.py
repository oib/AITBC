"""DEAD-ISLAND-GOSSIP-1 (#393): deferral helper for out-of-process services.

Consumers (miner offer-publish, agent-coordinator job-submit) call
island_degraded() each cycle. It reads the local blockchain-node's
/v1/island/health and returns True only on "island-degraded". Every
failure path FAILS OPEN (returns False): connection refused, timeout,
non-200, malformed JSON — a dead or unupgraded monitor must never stall
publishing. defer_enabled reads ISLAND_DEFER_ENABLED (default OFF).
"""

from __future__ import annotations

import json
import os
import urllib.request

_DEFAULT_PORT = 8204
_TIMEOUT = 1.5


def defer_enabled() -> bool:
    return os.getenv("ISLAND_DEFER_ENABLED", "").lower() in ("1", "true", "yes")


def island_degraded(port: int = _DEFAULT_PORT, timeout: float = _TIMEOUT) -> bool:
    """True iff the local node reports island-degraded. Fail-open."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/island/health", timeout=timeout) as resp:
            if resp.status != 200:
                return False
            payload: dict[str, object] = json.loads(resp.read())
    except Exception:
        return False
    return payload.get("degraded") == "island-degraded"


def should_defer(action: str, port: int = _DEFAULT_PORT, timeout: float = _TIMEOUT) -> bool:
    """The one-line consumer call: True only when the flag is on AND the
    node reports island-degraded. Flag off is a no-op — no network read."""
    return defer_enabled() and island_degraded(port=port, timeout=timeout)
