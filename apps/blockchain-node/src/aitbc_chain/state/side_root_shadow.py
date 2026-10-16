"""V-3 per-block side-table root shadow computation — compare-only, never consensus.

After a block is sealed this hook computes the canonical digest of the
13 apply-written tables (the V-3 committed set), stores the fingerprint in
the node-local ``shadow_side_root`` table, logs it, and bumps observability
counters. The rules are byte-identical to ``scripts/ops/side-root-probe.py
--canonical`` — the executable reference for
``docs/design/v3-side-table-root-shadow.md``.

**What enabling it does:** the hook *creates and writes* the node-local
``shadow_side_root`` table inside the chain database after each block
commit — one row per shadowed height (chain_id, block_height, fingerprint,
per-table digests, local write time). The table is node-local bookkeeping
(like ``escrow``): it is *not* part of the committed set and is never
hashed into a block, so it cannot diverge consensus. Retention keeps the
newest ``settings.side_root_shadow_retention`` rows (default 10_000);
``settings.side_root_shadow_interval`` (default 1 = every block) thins the
per-block cost by shadowing only heights that are multiples of it.

Guarantees (enforced by construction and pinned by tests):

- gated by ``settings.side_root_shadow_enabled`` — **default off**, and when
  off the hook returns before issuing a single query;
- never touches the block header, the block hash, validation or apply;
- any failure is caught, logged as a warning and swallowed — a failing
  shadow computation can never raise into the seal path.

**v14 (shared ACT-1 activation):** ``committed_fingerprint`` is also the
source of the ``aux_state_root`` the proposer commits into the block hash at
``settings.state_transition_v14_height`` and that ``sync_block_import``
recomputes at verification. The shadow table stays observational either way —
only the fingerprint formula is shared.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlmodel import Session

from ..metrics import metrics_registry

logger = logging.getLogger(__name__)


class _DbConn(Protocol):
    """The DBAPI surface this module needs: a sqlite3 connection or the
    SQLAlchemy pool-proxied equivalent (``session.connection().connection``)."""

    def execute(self, sql: str, parameters: Any = ...) -> Any: ...
    def commit(self) -> None: ...


# The V-3 committed set (operator decision 2026-10-12): all 13 apply-written
# tables. ``account`` is the canary — already committed via state_root, it
# must always agree.
COMMITTED_TABLES: tuple[str, ...] = (
    "account",
    "bond",
    "chain_parameter",
    "chain_parameter_history",
    "edge_node_registration",
    "gpu_allocation",
    "gpu_registration",
    "ipfs_subscription",
    "liquidity_distribution",
    "liquidity_pool",
    "liquidity_stake",
    "receipt",
    "stake",
)

# Tables whose committed digest only exists under the canonicalization rules
# below (RPC writers stamp local handles/timestamps into the same tables).
CANONICALIZED_TABLES: tuple[str, ...] = (
    "gpu_allocation",
    "gpu_registration",
    "stake",
)


# Canonical rule 1: every column whose name ends in ``_at`` is a locally
# stamped wall-clock value — excluded from the committed digest.
def _is_local_stamp(col: str) -> bool:
    return col.endswith("_at")


# Canonical rule 1b: named per-table columns holding node-local handles the
# RPC writer generated (never derivable from sealed history) — excluded.
# Live fact: gpu_allocation.allocation_id differs on every host.
CANONICAL_EXCLUDED_COLUMNS: dict[str, frozenset[str]] = {
    "gpu_allocation": frozenset({"allocation_id"}),
}

# Canonical rules 2/3: 0x-prefixed identifiers are EVM-style addresses whose
# case is an encoding artifact → lowercase. ISO-8601 text with an all-zero
# fractional second part is the same instant written by different SQLite
# writers → drop the fraction. Non-zero fractions are kept: a real
# sub-second difference is real divergence.
_STAMP_FRACTION_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.0{1,9}$")


def _canonical_cell_value(value: Any) -> Any:
    if isinstance(value, str):
        if value[:2].lower() == "0x":
            return value.lower()
        return _STAMP_FRACTION_RE.sub(r"\1", value)
    return value


def _canonical_cell(value: Any) -> str:
    """One cell → a canonical string. Type-tagged so 1 != '1' != b'\\x01'."""
    if value is None:
        return "n:"
    if isinstance(value, bool):
        return "i:" + str(int(value))
    if isinstance(value, int):
        return "i:" + str(value)
    if isinstance(value, float):
        return "f:" + repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "b:" + bytes(value).hex()
    return "s:" + str(value)


DIGEST_LEN = 16


def table_digest(conn: _DbConn, table: str) -> dict[str, Any]:
    """Committed canonical digest of one table: rows, kept columns and a
    short sha256 — identical construction to side-root-probe.py --canonical."""
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    if not cols:
        return {"status": "absent"}
    excluded = CANONICAL_EXCLUDED_COLUMNS.get(table, frozenset())
    drop = lambda c: _is_local_stamp(c) or c in excluded  # noqa: E731
    keep = [c for c in cols if not drop(c)]
    skipped = [c for c in cols if drop(c)]
    quoted = ", ".join(f'"{c}"' for c in keep)
    # quoted identifiers from PRAGMA table_info over a fixed table list
    rows = conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()  # nosec
    rows = [tuple(_canonical_cell_value(v) for v in row) for row in rows]
    canonical_rows = sorted("\x1f".join(_canonical_cell(v) for v in row) for row in rows)
    h = hashlib.sha256()
    h.update(table.encode())
    h.update(b"\x00")
    h.update(",".join(keep).encode())
    h.update(b"\x00")
    for row in canonical_rows:
        h.update(row.encode())
        h.update(b"\x1e")
    return {"rows": len(rows), "digest": h.hexdigest()[:DIGEST_LEN], "skipped_cols": skipped}


def committed_fingerprint(conn: _DbConn) -> dict[str, Any]:
    """All 13 committed digests plus the set fingerprint — the same sha256
    over ``sorted(table=digest;)`` pairs the probe prints."""
    digests: dict[str, Any] = {}
    for table in COMMITTED_TABLES:
        digests[table] = table_digest(conn, table)
    h = hashlib.sha256()
    for table in sorted(digests):
        entry = digests[table]
        h.update(table.encode())
        h.update(b"=")
        h.update((entry["digest"] if "digest" in entry else entry["status"]).encode())
        h.update(b";")
    return {
        "fingerprint": h.hexdigest()[:DIGEST_LEN],
        "tables": digests,
        "requires_rules": list(CANONICALIZED_TABLES),
    }


_SHADOW_DDL = """
CREATE TABLE IF NOT EXISTS shadow_side_root (
    chain_id TEXT NOT NULL,
    block_height INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    digests TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (chain_id, block_height)
)
"""


def record_shadow(conn: _DbConn, chain_id: str, height: int, *, retention: int = 10_000) -> dict[str, Any]:
    """Compute the committed fingerprint over the live tables and persist it
    in ``shadow_side_root`` (node-local bookkeeping), then prune the table
    to the newest ``retention`` rows for this chain (``retention <= 0``
    keeps everything). Returns the stored row data plus
    ``changed``/``recomputed_differed`` flags for the caller's metrics and
    log line."""
    conn.execute(_SHADOW_DDL)
    previous = conn.execute(
        "SELECT fingerprint FROM shadow_side_root WHERE chain_id = ? AND block_height = ?",
        (chain_id, height),
    ).fetchone()
    latest = conn.execute(
        "SELECT block_height, fingerprint FROM shadow_side_root WHERE chain_id = ? ORDER BY block_height DESC LIMIT 1",
        (chain_id,),
    ).fetchone()
    result = committed_fingerprint(conn)
    fingerprint = result["fingerprint"]
    # Determinism check: recomputing a height we already shadowed must give
    # the identical fingerprint — anything else is a local divergence signal.
    recomputed_differed = previous is not None and previous[0] != fingerprint
    changed = latest is not None and latest[1] != fingerprint and previous is None
    conn.execute(
        "INSERT OR REPLACE INTO shadow_side_root (chain_id, block_height, fingerprint, digests, computed_at)"
        " VALUES (?, ?, ?, ?, datetime('now'))",
        (
            chain_id,
            height,
            fingerprint,
            json.dumps({t: d.get("digest", d.get("status")) for t, d in result["tables"].items()}),
        ),
    )
    if retention > 0:
        conn.execute(
            "DELETE FROM shadow_side_root WHERE chain_id = ? AND block_height NOT IN ("
            "SELECT block_height FROM shadow_side_root WHERE chain_id = ?"
            " ORDER BY block_height DESC LIMIT ?)",
            (chain_id, chain_id, retention),
        )
    conn.commit()
    return {
        "height": height,
        "fingerprint": fingerprint,
        "tables": result["tables"],
        "changed_from_previous": changed,
        "recomputed_differed": recomputed_differed,
    }


def on_block_sealed(session: Session, chain_id: str, height: int) -> None:
    """Post-seal hook: shadow-compute the side-table root for ``height``.

    Called after the block's own transaction has committed. When the
    ``SIDE_ROOT_SHADOW_ENABLED`` flag is off, or ``height`` is not a
    multiple of ``side_root_shadow_interval``, this returns before issuing
    any query. Any error is logged and swallowed — the shadow is
    observational and must never reach the seal path.
    """
    from ..config import settings

    if not getattr(settings, "side_root_shadow_enabled", False):
        return
    try:
        interval = int(getattr(settings, "side_root_shadow_interval", 1) or 1)
        retention = int(getattr(settings, "side_root_shadow_retention", 10_000))
    except (TypeError, ValueError):
        interval, retention = 1, 10_000
    if height % max(1, interval):
        return
    try:
        conn = session.connection().connection
        info = record_shadow(conn, chain_id, height, retention=retention)
        metrics_registry.increment("side_root_shadow_blocks_total")
        metrics_registry.set_gauge("side_root_shadow_last_height", float(height))
        if info["recomputed_differed"]:
            # Same sealed height digested twice to different values: the only
            # locally-detectable divergence. The cross-node counter from the
            # design is fed by the fleet digest-compare runs.
            metrics_registry.increment("side_root_divergence_total")
            logger.error(
                "[SIDE-ROOT-SHADOW] height %s recomputed to a different fingerprint (%s) — local divergence signal",
                height,
                info["fingerprint"],
            )
        else:
            logger.info(
                "[SIDE-ROOT-SHADOW] height=%s fingerprint=%s%s",
                height,
                info["fingerprint"],
                " (changed from previous height)" if info["changed_from_previous"] else "",
            )
    except Exception as e:  # noqa: BLE001 — shadow must never raise into the seal path
        metrics_registry.increment("side_root_shadow_errors_total")
        logger.warning("[SIDE-ROOT-SHADOW] height %s: shadow computation failed (ignored, shadow-only): %s", height, e)
