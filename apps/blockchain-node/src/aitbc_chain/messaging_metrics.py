"""MSG-6: operability metrics for the derived messaging index.

Two families, all prefixed ``aitbc_messaging_``:

- **Counters** incremented where the work happens: reads and read errors on
  the ``/rpc/messaging/*`` routes, and admission rejections bucketed by a
  coarse reason label (bounded cardinality — the raw error string may carry
  interpolated attacker text and is never a label).
- **Scrape-time gauges** computed lazily in :func:`collect_all`, called from
  the ``/metrics`` endpoint: index height, lag behind the chain head,
  message/action totals, and the *checkpoint index digest* — a SHA-256 over
  the valid envelopes up to the last full checkpoint, so two nodes' derived
  state can be compared for divergence without sharing databases.

Nothing here runs inside block import and nothing touches consensus or
``state_root``: the digest is derived state, computed at read/scrape time
and cached per (chain, checkpoint, index-head-hash).
"""

from __future__ import annotations

import hashlib
import json
import threading
import typing
from collections import OrderedDict
from typing import Any

from prometheus_client import Counter, Gauge
from sqlmodel import col, func, select

from .base_models import Block
from .logger import get_logger
from .messaging_index import (
    _asc_select,
    _bare_hash,
    _canonical,
    _env_from_row,
    _index_head,
    _iter_valid_asc,
    _mod_cache_get,
    _mod_cache_put,
    state,
)

_logger = get_logger(__name__)

#: Digest checkpoint granularity: derived state is hashed at the last full
#: multiple of this many blocks (MSG-6).
CHECKPOINT_INTERVAL = 1000

reads_total = Counter("aitbc_messaging_reads_total", "Successful /rpc/messaging/* reads", ["route"])
read_errors_total = Counter(
    "aitbc_messaging_read_errors_total", "Failed /rpc/messaging/* reads (5xx and unhandled exceptions)", ["route"]
)
read_client_errors_total = Counter(
    "aitbc_messaging_read_client_errors_total",
    "Rejected /rpc/messaging/* reads (4xx: bad cursor, bad slug, not found, rate limit)",
    ["route"],
)
rejected_total = Counter(
    "aitbc_messaging_rejected_total", "aitbc_msg envelopes refused at admission, by coarse reason", ["reason"]
)
index_height_gauge = Gauge("aitbc_messaging_index_height", "Sealed height the messaging index has read", ["chain_id"])
chain_head_gauge = Gauge("aitbc_messaging_chain_head_height", "Local chain head height", ["chain_id"])
index_lag_gauge = Gauge("aitbc_messaging_index_lag_blocks", "Chain head minus messaging index height", ["chain_id"])
messages_gauge = Gauge("aitbc_messaging_messages_total", "Valid post/reply messages in the index", ["chain_id"])
actions_gauge = Gauge("aitbc_messaging_actions_total", "Valid MSG-2 actions in the index", ["chain_id"])
checkpoint_height_gauge = Gauge("aitbc_messaging_checkpoint_height", "Latest digest checkpoint height", ["chain_id"])
digest_gauge = Gauge(
    "aitbc_messaging_index_digest",
    "Checkpoint digest of the derived messaging index (value is always 1; the digest is a label)",
    ["chain_id", "checkpoint", "digest"],
)

#: Coarse, bounded reason buckets for admission rejections. Matched as
#: substrings against the envelope_error string; first hit wins. Anything
#: unmapped lands in "other" — cardinality is fixed.
_REASON_BUCKETS: tuple[tuple[str, str], ...] = (
    ("aitbc_msg must be an object", "shape"),
    # Trailing space: "aitbc_msg.v" alone is a prefix of "aitbc_msg.value".
    ("aitbc_msg.v ", "version"),
    ("aitbc_msg.kind", "kind"),
    ("aitbc_msg.topic", "topic"),
    ("aitbc_msg.body", "body"),
    ("aitbc_msg.parent", "parent"),
    ("aitbc_msg.target", "target"),
    ("aitbc_msg.value", "value"),
    ("aitbc_msg.grantee", "grantee"),
    ("agent_address", "author"),
)


def reject_reason(error: str) -> str:
    for needle, label in _REASON_BUCKETS:
        if needle in error:
            return label
    return "other"


def note_admission_rejected(error: str) -> None:
    rejected_total.labels(reject_reason(error)).inc()


def note_read(route: str) -> None:
    reads_total.labels(route).inc()


def note_read_error(route: str) -> None:
    read_errors_total.labels(route).inc()


def note_read_client_error(route: str) -> None:
    read_client_errors_total.labels(route).inc()


def checkpoint_for(index_height: int) -> int:
    """Last full checkpoint at or below the index height."""
    return max(0, (index_height // CHECKPOINT_INTERVAL) * CHECKPOINT_INTERVAL)


def _digest_record(row: Any) -> dict[str, Any]:
    return {
        "tx": _bare_hash(row.tx_hash),
        "h": row.block_height,
        "s": _canonical(row.sender),
        "env": _env_from_row(row),
    }


def _block_hash_at_height(session, chain_id: str, height: int) -> str | None:
    """Hash of the block stored at ``height`` for the chain, or None."""
    row = session.exec(select(col(Block.hash)).where(col(Block.chain_id) == chain_id, col(Block.height) == height)).first()
    if row is None:
        return None
    return str(row[0] if isinstance(row, tuple) else row)


def _digest_key_hash(session, chain_id: str, checkpoint: int) -> str:
    """Cache-key component: the hash of the block AT the checkpoint height.

    Rows at or below the checkpoint can only change if a fork heals under
    it, which replaces that block and its hash — so this key survives new
    blocks above the checkpoint and misses exactly when it must. When no
    block row exists at the checkpoint height (e.g. checkpoint 0 on a
    chain whose first stored block is higher) fall back to the index head
    hash: correct, only uncached across blocks.
    """
    key_hash = _block_hash_at_height(session, chain_id, checkpoint)
    if key_hash is None:
        _, key_hash = _index_head(session, chain_id)
    return key_hash


#: Single-flight locks for cold digest scans, keyed on the full cache key.
#: Bounded like the result cache; an evicted live lock only ever causes a
#: duplicate scan, never a wrong value.
_DIGEST_FLIGHTS: OrderedDict[tuple, threading.Lock] = OrderedDict()
_DIGEST_FLIGHTS_MAX = 256
_DIGEST_FLIGHTS_GUARD = threading.Lock()


def _flight_lock(key: tuple) -> threading.Lock:
    with _DIGEST_FLIGHTS_GUARD:
        lock = _DIGEST_FLIGHTS.get(key)
        if lock is None:
            lock = threading.Lock()
            _DIGEST_FLIGHTS[key] = lock
            while len(_DIGEST_FLIGHTS) > _DIGEST_FLIGHTS_MAX:
                _DIGEST_FLIGHTS.popitem(last=False)
        else:
            _DIGEST_FLIGHTS.move_to_end(key)
    return lock


def _scan_digest(session, chain_id: str, checkpoint: int) -> str:
    digest = hashlib.sha256()
    stmt = _asc_select(chain_id)
    # Exclusive bound at the first position of the next checkpoint block:
    # every row with block_height <= checkpoint is included, nothing above.
    bound = (checkpoint + 1, "")
    count = 0
    for row in _iter_valid_asc(session, stmt, before=bound):
        record = json.dumps(_digest_record(row), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest.update(record.encode("utf-8"))
        digest.update(b"\n")
        count += 1
    result = digest.hexdigest()
    _logger.debug("messaging digest: chain=%s checkpoint=%d rows=%d digest=%s", chain_id, checkpoint, count, result[:12])
    return result


def checkpoint_digest(session, chain_id: str, checkpoint: int) -> str:
    """SHA-256 over the valid messaging envelopes sealed at or below
    ``checkpoint``, in canonical (block_height, tx_hash) order.

    Cached per (chain, checkpoint, hash-of-the-checkpoint-block) — rows
    below the checkpoint can only change if a fork healed under it, which
    replaces that block and its hash; a new block above the checkpoint
    does not. The result is a pure function of sealed rows: insertion
    order and rowids never enter.

    Cold scans are single-flight per key: concurrent scrapes share one
    computation. A failing first caller releases the lock; each waiter
    re-checks the cache and scans on its own if it is still empty.
    """
    key = ("digest", chain_id, "", checkpoint, _digest_key_hash(session, chain_id, checkpoint))
    hit = _mod_cache_get(key)
    if hit is not None:
        return typing.cast(str, hit)
    with _flight_lock(key):
        hit = _mod_cache_get(key)  # the first caller may have filled it
        if hit is not None:
            return typing.cast(str, hit)
        return typing.cast(str, _mod_cache_put(key, _scan_digest(session, chain_id, checkpoint)))


def collect_gauges(session, chain_id: str) -> dict[str, Any]:
    """Compute and publish one chain's scrape-time gauges. Returns the raw
    values for tests and the CLI stats path."""
    head = session.exec(select(func.max(col(Block.height))).where(col(Block.chain_id) == chain_id)).first()
    head_height = int(head) if head is not None else 0
    totals = state(session, chain_id)
    index_height = int(totals.get("index_height") or 0)
    checkpoint = checkpoint_for(index_height)
    digest = checkpoint_digest(session, chain_id, checkpoint)
    lag = max(0, head_height - index_height)

    index_height_gauge.labels(chain_id).set(index_height)
    chain_head_gauge.labels(chain_id).set(head_height)
    index_lag_gauge.labels(chain_id).set(lag)
    messages_gauge.labels(chain_id).set(int(totals["contract_state"]["total_messages"]))
    actions_gauge.labels(chain_id).set(int(totals["contract_state"]["total_actions"]))
    checkpoint_height_gauge.labels(chain_id).set(checkpoint)
    digest_gauge.labels(chain_id, str(checkpoint), digest).set(1)
    result: dict[str, Any] = {
        "chain_id": chain_id,
        "index_height": index_height,
        "chain_head_height": head_height,
        "index_lag_blocks": lag,
        "messages": totals["contract_state"]["total_messages"],
        "actions": totals["contract_state"]["total_actions"],
        "topics": totals["contract_state"]["total_topics"],
        "agents": totals["contract_state"]["total_agents"],
        "checkpoint_height": checkpoint,
        "checkpoint_digest": digest,
    }
    return result


def _prune_digest_labels(wanted: set[tuple[str, str, str]], chains: set[str]) -> None:
    """Remove digest label sets that are no longer wanted — a superseded
    checkpoint, or a superseded digest at the same checkpoint (leaving it
    would read as a false cross-node mismatch). Runs AFTER the new series
    are set, so the metric never goes absent during a cold scan.

    ``digest_gauge._metrics`` is the only inventory the client library
    exposes; a missing label set on remove is tolerated.
    """
    for labels in set(digest_gauge._metrics.keys()):  # noqa: SLF001 — no public API
        if labels[0] in chains and labels not in wanted:
            try:
                digest_gauge.remove(*labels)
            except KeyError:
                pass


def collect_all(supported_chains: list[str]) -> None:
    """Update scrape gauges for every supported chain. Never raises into the
    /metrics handler — a broken chain must not blank the whole exposition.

    Digest label sets are pruned to this scrape's result only after the new
    values are set; a chain that failed to collect keeps its last labels.
    """
    from .database import session_scope

    wanted: set[tuple[str, str, str]] = set()
    collected: set[str] = set()
    for chain_id in supported_chains:
        try:
            with session_scope(chain_id) as session:
                snap = collect_gauges(session, chain_id)
            wanted.add((chain_id, str(snap["checkpoint_height"]), snap["checkpoint_digest"]))
            collected.add(chain_id)
        except Exception as e:
            _logger.warning("messaging metrics: collect failed for %s: %s", chain_id, e)
    _prune_digest_labels(wanted, collected)
