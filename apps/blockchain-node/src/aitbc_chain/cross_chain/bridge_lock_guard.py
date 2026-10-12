"""V-4 seal-path missing-data guard — dry-run mode only.

Where the bridge state root is derived from sealed BRIDGE_LOCKs, the
activation design (docs/design/bridge-state-root-grandfathering.md) will
eventually refuse a lock that carries no derivable leaf data. This hook is
the measurement stage: it classifies every lock the seal path is about to
commit exactly the way ``scripts/ops/bridge-leaf-audit.py`` does — payload
first, signed-envelope fallback for the GAP-47 block-scoped rows — and
counts what it *would* refuse at/above the operator boundary (30000).

Guarantees (pinned by tests):

- gated by ``settings.bridge_lock_guard_dryrun_enabled`` — **default off**,
  and when off the function returns before touching a single tx;
- never rejects, never mutates the tx list, never alters the block: the
  block is built exactly as before and the guard only logs and counts;
- a lock below the boundary is ``grandfathered`` — counted, never warned.
"""

from __future__ import annotations

import logging
from typing import Any

from ..metrics import metrics_registry

logger = logging.getLogger(__name__)

# Operator-chosen activation boundary (decision 2026-10-08): below it an
# underivable lock is grandfathered sealed history; at/above it the same
# shape is a missing_data defect the real guard must make impossible.
GRANDFATHER_BOUNDARY = 30000


def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = source.get(key)
        if val is not None and val != "":
            return val
    return None


def lock_derivation_source(payload: dict[str, Any], envelope: dict[str, Any]) -> str:
    """Mirrors bridge-leaf-audit.py's ``derived_leaf``: leaf data comes from
    ``payload`` first, falling back to the signed ``envelope`` body for the
    GAP-47 block-scoped rows whose payload column is empty. Returns the
    source name or ``unreadable`` when neither carries a derivable leaf."""
    tid = _pick(payload, "transfer_id")
    amount = _pick(payload, "amount")
    target = _pick(payload, "target_chain")
    if tid is None or amount is None or target is None:
        tid = tid or _pick(envelope, "transfer_id")
        amount = amount or _pick(envelope, "amount")
        target = target or _pick(envelope, "target_chain")
        if tid is None or amount is None or target is None:
            return "unreadable"
        return "envelope"
    return "payload"


def _short(tx_hash: str) -> str:
    return f"{tx_hash[:10]}…{tx_hash[-4:]}" if len(tx_hash) > 16 else tx_hash


def check_locks_dryrun(
    lock_txs: list[tuple[str, dict[str, Any], dict[str, Any]]],
    *,
    height: int,
    boundary: int = GRANDFATHER_BOUNDARY,
    chain_id: str = "",
    log: logging.Logger | None = None,
) -> dict[str, int]:
    """Classify each ``(tx_hash, payload, envelope)`` BRIDGE_LOCK the seal
    path is committing and count what the activation guard WOULD refuse.

    Returns ``{"checked": n, "derivable": n, "grandfathered": n,
    "would_refuse": n}``. Purely observational: callers ignore the result
    and the seal path continues identically either way.
    """
    out = {"checked": 0, "derivable": 0, "grandfathered": 0, "would_refuse": 0}
    log = log or logger
    for tx_hash, payload, envelope in lock_txs:
        out["checked"] += 1
        src = lock_derivation_source(payload or {}, envelope or {})
        if src != "unreadable":
            out["derivable"] += 1
            continue
        if height >= boundary:
            out["would_refuse"] += 1
            metrics_registry.increment("bridge_lock_guard_would_refuse_total")
            log.warning(
                "[V4-DRYRUN] would refuse BRIDGE_LOCK %s at height %s (>= boundary %s, chain=%s): "
                "no derivable payload/envelope leaf data",
                _short(tx_hash),
                height,
                boundary,
                chain_id,
            )
        else:
            out["grandfathered"] += 1
            metrics_registry.increment("bridge_lock_guard_grandfathered_total")
    metrics_registry.increment("bridge_lock_guard_checked_total", float(out["checked"]))
    return out


def _is_bridge_lock(tx_content: dict[str, Any]) -> bool:
    return str((tx_content or {}).get("type") or "").upper() == "BRIDGE_LOCK"


def run_guard_dryrun(
    processed_txs: list[Any], *, height: int, chain_id: str, log: logging.Logger | None = None
) -> dict[str, int] | None:
    """Flag-gated entry point for the propose path: picks the BRIDGE_LOCKs
    out of ``processed_txs`` and classifies them. ``None`` means the flag is
    off — the caller can assert no work happened."""
    from ..config import settings

    if not getattr(settings, "bridge_lock_guard_dryrun_enabled", False):
        return None
    items = [
        (tx.tx_hash, (tx.content or {}).get("payload", {}) or {}, (tx.content or {}))
        for tx in processed_txs
        if _is_bridge_lock(tx.content or {})
    ]
    return check_locks_dryrun(
        items,
        height=height,
        boundary=getattr(settings, "bridge_lock_guard_boundary", GRANDFATHER_BOUNDARY),
        chain_id=chain_id,
        log=log,
    )


def run_guard_dryrun_dicts(
    transactions: list[dict[str, Any]], *, height: int, chain_id: str, log: logging.Logger | None = None
) -> dict[str, int] | None:
    """Flag-gated entry point for the sync-import path, where transactions
    are plain dicts. The sealed ``envelope`` column stores ``dict(tx)`` —
    the whole tx body — so the tx itself is the envelope."""
    from ..config import settings

    if not getattr(settings, "bridge_lock_guard_dryrun_enabled", False):
        return None
    items = [
        (tx.get("tx_hash", ""), tx.get("payload", {}) or {}, tx)
        for tx in transactions
        if _is_bridge_lock(tx) or _is_bridge_lock(tx.get("payload", {}) or {})
    ]
    return check_locks_dryrun(
        items,
        height=height,
        boundary=getattr(settings, "bridge_lock_guard_boundary", GRANDFATHER_BOUNDARY),
        chain_id=chain_id,
        log=log,
    )
