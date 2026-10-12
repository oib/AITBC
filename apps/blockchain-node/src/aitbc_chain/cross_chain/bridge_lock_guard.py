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
  and when off the entry points return ``None`` before touching a single tx;
- never rejects, never mutates the tx list, never alters the block: the
  block is built exactly as before and the guard only logs and counts;
- a lock below the boundary is ``grandfathered`` — counted, never warned;
- no exception can reach the caller: a malformed lock (non-dict payload or
  envelope, missing ``tx_hash``, non-dict transaction/content) is counted
  on ``bridge_lock_guard_errors_total`` and skipped, and any unforeseen
  error anywhere in the hook is caught, logged with the height, counted,
  and the entry point returns ``None`` — the seal path continues
  identically either way.
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
    s = str(tx_hash)
    return f"{s[:10]}…{s[-4:]}" if len(s) > 16 else s


def _note_error(*, height: int, chain_id: str, log: logging.Logger, exc: BaseException) -> None:
    """Count + log a guard failure. A broken logger must never reach the
    seal path, so the warning itself is best-effort."""
    metrics_registry.increment("bridge_lock_guard_errors_total")
    try:
        log.warning(
            "[V4-DRYRUN] guard error at height %s (chain=%s): %s: %s — item skipped",
            height,
            chain_id,
            type(exc).__name__,
            exc,
        )
    except Exception:
        pass


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
    and the seal path continues identically either way. A malformed item is
    counted on ``bridge_lock_guard_errors_total`` and skipped; an
    unexpected failure anywhere in the loop is caught the same way — this
    function never raises.
    """
    out = {"checked": 0, "derivable": 0, "grandfathered": 0, "would_refuse": 0}
    log = log or logger
    try:
        for item in lock_txs:
            out["checked"] += 1
            try:
                tx_hash, payload, envelope = item
                if (payload is not None and not isinstance(payload, dict)) or (
                    envelope is not None and not isinstance(envelope, dict)
                ):
                    raise TypeError("non-dict payload/envelope")
                src = lock_derivation_source(payload or {}, envelope or {})
            except Exception as exc:
                _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
                continue
            if src != "unreadable":
                out["derivable"] += 1
                continue
            if height >= boundary:
                out["would_refuse"] += 1
                metrics_registry.increment("bridge_lock_guard_would_refuse_total")
                try:
                    log.warning(
                        "[V4-DRYRUN] would refuse BRIDGE_LOCK %s at height %s (>= boundary %s, chain=%s): "
                        "no derivable payload/envelope leaf data",
                        _short(tx_hash),
                        height,
                        boundary,
                        chain_id,
                    )
                except Exception as exc:
                    _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
            else:
                out["grandfathered"] += 1
                metrics_registry.increment("bridge_lock_guard_grandfathered_total")
    except Exception as exc:
        _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
    metrics_registry.increment("bridge_lock_guard_checked_total", float(out["checked"]))
    return out


def _is_bridge_lock(tx_content: dict[str, Any]) -> bool:
    return str((tx_content or {}).get("type") or "").upper() == "BRIDGE_LOCK"


def _processed_lock_items(
    processed_txs: list[Any], *, height: int, chain_id: str, log: logging.Logger
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Pull ``(tx_hash, payload, content)`` for the BRIDGE_LOCKs in the
    propose-path list. A malformed tx (missing/non-dict content or
    tx_hash, non-dict payload on a lock) is counted on
    ``bridge_lock_guard_errors_total`` and skipped — never raised."""
    items: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for tx in processed_txs:
        try:
            content = getattr(tx, "content", None)
            tx_hash = getattr(tx, "tx_hash", None)
            if not isinstance(content, dict) or not isinstance(tx_hash, str) or not tx_hash:
                raise TypeError(f"malformed processed tx (content={type(content).__name__}, tx_hash={type(tx_hash).__name__})")
            if not _is_bridge_lock(content):
                continue
            payload = content.get("payload")
            if payload is not None and not isinstance(payload, dict):
                raise TypeError("non-dict payload")
            items.append((tx_hash, payload or {}, content))
        except Exception as exc:
            _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
    return items


def _dict_lock_items(
    transactions: list[dict[str, Any]], *, height: int, chain_id: str, log: logging.Logger
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Same extraction for the sync-import path's plain-dict transactions:
    the sealed ``envelope`` column stores ``dict(tx)`` so the tx body is
    the envelope. A malformed lock (non-dict tx, non-dict payload, missing
    tx_hash) is counted on ``bridge_lock_guard_errors_total`` and skipped."""
    items: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for tx in transactions:
        try:
            if not isinstance(tx, dict):
                raise TypeError(f"non-dict transaction ({type(tx).__name__})")
            payload = tx.get("payload")
            payload_view = payload if isinstance(payload, dict) else {}
            if not (_is_bridge_lock(tx) or _is_bridge_lock(payload_view)):
                continue
            if payload is not None and not isinstance(payload, dict):
                raise TypeError("non-dict payload")
            tx_hash = tx.get("tx_hash")
            if not tx_hash:
                raise TypeError("missing tx_hash")
            items.append((str(tx_hash), payload or {}, tx))
        except Exception as exc:
            _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
    return items


def run_guard_dryrun(
    processed_txs: list[Any], *, height: int, chain_id: str, log: logging.Logger | None = None
) -> dict[str, int] | None:
    """Flag-gated entry point for the propose path: picks the BRIDGE_LOCKs
    out of ``processed_txs`` and classifies them. ``None`` means the flag
    is off *or* the guard itself failed — either way the caller proceeds
    exactly as if no hook existed."""
    from ..config import settings

    if not getattr(settings, "bridge_lock_guard_dryrun_enabled", False):
        return None
    log = log or logger
    try:
        items = _processed_lock_items(processed_txs, height=height, chain_id=chain_id, log=log)
        return check_locks_dryrun(
            items,
            height=height,
            boundary=getattr(settings, "bridge_lock_guard_boundary", GRANDFATHER_BOUNDARY),
            chain_id=chain_id,
            log=log,
        )
    except Exception as exc:
        _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
        return None


def run_guard_dryrun_dicts(
    transactions: list[dict[str, Any]], *, height: int, chain_id: str, log: logging.Logger | None = None
) -> dict[str, int] | None:
    """Flag-gated entry point for the sync-import path, where transactions
    are plain dicts. ``None`` means the flag is off *or* the guard itself
    failed — the import continues identically either way."""
    from ..config import settings

    if not getattr(settings, "bridge_lock_guard_dryrun_enabled", False):
        return None
    log = log or logger
    try:
        items = _dict_lock_items(transactions, height=height, chain_id=chain_id, log=log)
        return check_locks_dryrun(
            items,
            height=height,
            boundary=getattr(settings, "bridge_lock_guard_boundary", GRANDFATHER_BOUNDARY),
            chain_id=chain_id,
            log=log,
        )
    except Exception as exc:
        _note_error(height=height, chain_id=chain_id, log=log, exc=exc)
        return None
