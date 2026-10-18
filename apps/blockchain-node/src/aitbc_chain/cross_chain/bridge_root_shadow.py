"""Follower-side ``bridge_state_root`` shadow check — compare-only.

``sync_block_import._derive_bridge_state_root`` trusts the root carried in
the P2P/bulk payload when one is present, so a follower stores whatever the
sender attached and never re-derives it. Equal block hashes prove the headers
agree, not that the carried root is what the locks imply — and cross-chain
proofs are built from these roots.

This hook is the measurement stage for a later enforcement decision (reject
or fork-heal on mismatch — deliberately not implemented here: a follower
that refuses a block the producer sealed can stall that follower). When
``BRIDGE_ROOT_SHADOW_CHECK`` is on it re-derives the trie root from the
sealed BRIDGE_LOCK transactions *themselves* — payload first, signed
``envelope`` fallback for the GAP-47 block-scoped rows, exactly the way
``scripts/ops/bridge-leaf-audit.py`` and ``bridge_lock_guard`` do — compares
it to the carried root, and logs + counts on disagreement.

Derivation deliberately never touches the local ``CrossChainTransfer``
table: the sealed tx data is the evidence the producer committed to, while a
follower's table may legitimately lag rows it has not processed — consulting
it would manufacture false mismatches.

Guarantees (pinned by tests):

- gated by ``settings.bridge_root_shadow_check`` — **default off**, and when
  off the entry point returns ``None`` before touching a single tx;
- never rejects, never stores a different root, never alters the block:
  import continues with the carried root exactly as before;
- blocks below ``bridge_lock_guard_boundary`` (30000) are skipped — the
  grandfathered era cannot be re-derived deterministically;
- a lock with no derivable leaf data is counted on
  ``bridge_root_shadow_underivable_total`` and contributes consensus' own
  ``unknown_lock_leaf`` fallback, so the comparison still runs;
- no exception can reach the import path: any failure is counted on
  ``bridge_root_shadow_errors_total``, logged, and swallowed.
"""

from __future__ import annotations

import logging
from typing import Any

from ..metrics import metrics_registry
from .bridge_leaf import lock_leaf_value, lock_leaf_v2_active, unknown_lock_leaf
from .bridge_lock_guard import GRANDFATHER_BOUNDARY, _dict_lock_items, _pick

logger = logging.getLogger(__name__)


def _derived_lock_leaf(tx_hash: str, payload: dict[str, Any], envelope: dict[str, Any], height: int) -> tuple[str, str]:
    """Leaf for one sealed lock, derived from the tx only (payload →
    envelope), height-aware. Mirrors ``bridge-leaf-audit.py:derived_leaf``:
    the recipient reads ``recipient`` or ``target_recipient`` (the seal
    path's key) and is required from the v2 height. Returns
    ``(leaf, source)`` where source is payload / envelope / underivable."""
    tid = _pick(payload, "transfer_id")
    amount = _pick(payload, "amount")
    target = _pick(payload, "target_chain")
    recipient = _pick(payload, "recipient", "target_recipient")
    source = "payload"
    if tid is None or amount is None or target is None or (lock_leaf_v2_active(height) and recipient is None):
        tid = tid or _pick(envelope, "transfer_id")
        amount = amount or _pick(envelope, "amount")
        target = target or _pick(envelope, "target_chain")
        recipient = recipient or _pick(envelope, "recipient", "target_recipient")
        source = "envelope"
    if tid is None or amount is None or target is None or (lock_leaf_v2_active(height) and recipient is None):
        return unknown_lock_leaf(tx_hash), "underivable"
    return lock_leaf_value(str(tid), amount, str(target), str(recipient or ""), height), source


def _derived_root(transactions: list[dict[str, Any]], *, height: int, chain_id: str, log: logging.Logger) -> tuple[str, int]:
    """Trie root implied by the sealed BRIDGE_LOCKs — empty trie root when
    the block carries none. Same key/value construction consensus uses
    (``tx_hash`` key, ``lock_leaf_value`` payload). Returns
    ``(root, underivable_count)``."""
    from ..state.merkle_patricia_trie import MerklePatriciaTrie

    trie = MerklePatriciaTrie()
    lock_items = _dict_lock_items(transactions, height=height, chain_id=chain_id, log=log)
    underivable = 0
    for tx_hash, payload, envelope in lock_items:
        leaf, source = _derived_lock_leaf(tx_hash, payload, envelope, height)
        if source == "underivable":
            underivable += 1
        trie.put(tx_hash.encode(), leaf.encode())
    return "0x" + trie.get_root().hex(), underivable


def run_shadow_check(
    block_data: dict[str, Any],
    transactions: list[dict[str, Any]] | None,
    *,
    chain_id: str,
    log: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Flag-gated entry point for the import path: re-derive the bridge
    state root and compare it with the carried one. ``None`` means the flag
    is off, the block is below the boundary, or the check itself failed —
    either way the caller proceeds with the carried root exactly as
    before."""
    from ..config import settings

    if not getattr(settings, "bridge_root_shadow_check", False):
        return None
    log = log or logger
    try:
        height = int(block_data.get("height") or 0)
        boundary = int(getattr(settings, "bridge_lock_guard_boundary", GRANDFATHER_BOUNDARY))
        if height < boundary:
            return None
        carried = str(block_data.get("bridge_state_root") or "")
        if not carried:
            return None
        derived, underivable = _derived_root(list(transactions or []), height=height, chain_id=chain_id, log=log)
        if underivable:
            metrics_registry.increment("bridge_root_shadow_underivable_total", float(underivable))
            log.warning(
                "[BRIDGE-ROOT-SHADOW] %s lock(s) underivable at height %s (chain=%s) — consensus fallback leaf used",
                underivable,
                height,
                chain_id,
            )
        metrics_registry.increment("bridge_root_shadow_checked_total")
        out = {"checked": 1, "match": 0, "mismatch": 0, "underivable": underivable}
        if derived == carried:
            out["match"] = 1
            return out
        out["mismatch"] = 1
        metrics_registry.increment("bridge_root_shadow_mismatch_total")
        log.warning(
            "[BRIDGE-ROOT-SHADOW] root mismatch at height %s (chain=%s): carried=%s derived=%s — block imported unchanged",
            height,
            chain_id,
            carried[:14],
            derived[:14],
        )
        return out
    except Exception as exc:  # noqa: BLE001 - shadow check never raises into the import path
        metrics_registry.increment("bridge_root_shadow_errors_total")
        try:
            log.warning(
                "[BRIDGE-ROOT-SHADOW] check failed at height %s (chain=%s): %s: %s",
                block_data.get("height"),
                chain_id,
                type(exc).__name__,
                exc,
            )
        except Exception:  # noqa: BLE001,S110 - a broken logger must never reach the import path
            pass
        return None
