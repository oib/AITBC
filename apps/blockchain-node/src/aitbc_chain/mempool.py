"""Mempool implementations: in-memory pool, database pool and singleton.

Facade module for the #1860 split — the implementation is decomposed into
sibling modules (pure code motion; every name stays importable here):

- ``mempool_common`` — ``MempoolEntry``/``PendingTransaction`` model and the
  pure tx helpers (hash, slot key, drain ordering, stake-release guard)
- ``mempool_db_helpers`` — PostgreSQL advisory-lock/timeout admission helpers
- ``mempool_db_admission`` — ``_DbAdmissionMixin``: ``DatabaseMempool``
  ``add``/``batch_add`` admission and read paths
- ``mempool_db_reservations`` — ``_DbReservationMixin``: removal, the #1300
  reservation lifecycle and the remaining ``DatabaseMempool`` paths
"""

from __future__ import annotations

import hashlib as hashlib
import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass as dataclass
from threading import Lock, RLock
from typing import Any, cast as cast

from sqlalchemy import (
    BigInteger as BigInteger,
    Boolean as Boolean,
    Column as Column,
    Float as Float,
    Index as Index,
    Integer as Integer,
    MetaData as MetaData,
    Text as Text,
    bindparam as bindparam,
    delete as delete,
    event,
    func as func,
)
from sqlalchemy import select as sa_select  # noqa: F401
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION as DOUBLE_PRECISION
from sqlmodel import Field as Field, Session, create_engine, select, text

from .metadata import ChainBase as ChainBase
from .mempool_common import (
    MempoolEntry as MempoolEntry,
    PendingTransaction as PendingTransaction,
    _claimed_lock_hashes as _claimed_lock_hashes,
    _DrainCand as _DrainCand,
    _estimate_size as _estimate_size,
    _order_for_drain as _order_for_drain,
    _pending_tx_rows as _pending_tx_rows,
    _reject_conflicting_stake_release as _reject_conflicting_stake_release,
    _tx_cost as _tx_cost,
    _tx_nonce as _tx_nonce,
    _tx_sender as _tx_sender,
    _tx_slot_key as _tx_slot_key,
    compute_tx_hash as compute_tx_hash,
    mempool_metadata as mempool_metadata,
)
from .mempool_db_admission import _DbAdmissionMixin as _DbAdmissionMixin
from .mempool_db_helpers import (
    MempoolAdmissionTimeout as MempoolAdmissionTimeout,
    _apply_admission_timeouts as _apply_admission_timeouts,
    _is_admission_timeout as _is_admission_timeout,
    _normalize_lock_key as _normalize_lock_key,
    _PG_LOCK_NOT_AVAILABLE as _PG_LOCK_NOT_AVAILABLE,
    _PG_QUERY_CANCELED as _PG_QUERY_CANCELED,
    _slot_advisory_lock as _slot_advisory_lock,
    _slot_advisory_lock_by_key as _slot_advisory_lock_by_key,
    _slot_lock_key_str as _slot_lock_key_str,
)
from .mempool_db_reservations import _DbReservationMixin as _DbReservationMixin
from .metrics import (
    mempool_pending_count,
    mempool_pending_size_bytes,
    mempool_reservation_release_total as mempool_reservation_release_total,
    metrics_registry,
)

logger = logging.getLogger(__name__)


class InMemoryMempool:
    """In-memory mempool with fee-based prioritization and size limits."""

    def __init__(self, max_size: int = 10_000, min_fee: int = 0, chain_id: str | None = None) -> None:
        from .config import settings

        self._lock = Lock()
        self._transactions: dict[str, dict[str, PendingTransaction]] = {}
        # (sender, nonce) → tx_hash for signed pending entries, per chain.
        self._slots: dict[str, dict[tuple[str, int], str]] = {}
        self._max_size = max_size
        self._min_fee = min_fee
        self.chain_id = chain_id or settings.chain_id

    def _get_chain_transactions(self, chain_id: str) -> dict[str, PendingTransaction]:
        return self._transactions.setdefault(chain_id, {})

    def _total_size(self) -> int:
        return sum(len(chain_txs) for chain_txs in self._transactions.values())

    def _update_gauge(self, chain_id: str) -> None:
        """Refresh both metric surfaces for a chain after a mutation.

        The legacy registry gauge ``mempool_size`` reports the total across
        chains; the prometheus gauges are per-chain and back the MempoolFull
        alert. Lock held by caller.
        """
        chain_txs = self._get_chain_transactions(chain_id)
        metrics_registry.set_gauge("mempool_size", float(self._total_size()))
        mempool_pending_count.labels(chain_id=chain_id).set(float(len(chain_txs)))
        mempool_pending_size_bytes.labels(chain_id=chain_id).set(float(sum(t.size_bytes for t in chain_txs.values())))

    def add(
        self,
        tx: dict[str, Any],
        chain_id: str | None = None,
        tx_hash: str | None = None,
    ) -> str:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        if tx_hash is None:
            tx_hash = compute_tx_hash(tx)
        size_bytes = _estimate_size(tx)
        if size_bytes > settings.mempool_max_tx_size_bytes:
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            raise ValueError(f"transaction size {size_bytes} exceeds limit {settings.mempool_max_tx_size_bytes}")
        entry = PendingTransaction(tx_hash=tx_hash, content=tx, received_at=time.time(), fee=fee, size_bytes=size_bytes)
        with self._lock:
            return self._admit_locked(chain_id, tx, tx_hash, fee, entry)

    def _admit_locked(
        self,
        chain_id: str,
        tx: dict[str, Any],
        tx_hash: str,
        fee: int,
        entry: PendingTransaction,
    ) -> str:
        """Insert ``entry`` under ``self._lock`` with dedupe/slot/eviction rules."""
        chain_transactions = self._get_chain_transactions(chain_id)
        if tx_hash in chain_transactions:
            return tx_hash  # duplicate
        slot = _tx_slot_key(tx)
        if slot is not None:
            slots = self._slots.setdefault(chain_id, {})
            occupant_hash = slots.get(slot)
            if occupant_hash is not None and occupant_hash != tx_hash:
                occupant = chain_transactions.get(occupant_hash)
                if occupant is not None:
                    if fee <= occupant.fee:
                        metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                        raise ValueError(
                            f"nonce slot ({slot[0]}, {slot[1]}) already occupied by "
                            f"{occupant_hash} with fee {occupant.fee} >= {fee}"
                        )
                    self._drop_entry(chain_id, occupant)
                    metrics_registry.increment(f"mempool_tx_replaced_total_{chain_id}")
        _reject_conflicting_stake_release(tx, ((e.tx_hash, e.content) for e in chain_transactions.values()))
        if len(chain_transactions) >= self._max_size:
            # A full pool only makes room for a strictly better bid —
            # anything cheaper would let a fee-floor flood evict real
            # transactions it cannot outbid.
            lowest = min(chain_transactions.values(), key=lambda t: (t.fee, t.received_at, t.tx_hash))
            if fee <= lowest.fee:
                metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                raise ValueError(f"mempool full ({self._max_size}): fee {fee} does not beat lowest pending fee {lowest.fee}")
            self._drop_entry(chain_id, lowest)
            metrics_registry.increment(f"mempool_evictions_total_{chain_id}")
        chain_transactions[tx_hash] = entry
        if slot is not None:
            self._slots[chain_id][slot] = tx_hash
        self._update_gauge(chain_id)
        metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
        return tx_hash

    def list_transactions(self, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return list(self._get_chain_transactions(chain_id).values())

    def drain(self, max_count: int, max_bytes: int, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        """Drain transactions for block inclusion, prioritized by fee (highest first)."""
        with self._lock:
            chain_transactions = self._get_chain_transactions(chain_id)
            cands = []
            for tx in chain_transactions.values():
                slot = _tx_slot_key(tx.content)
                cands.append(
                    _DrainCand(
                        fee=tx.fee,
                        tx_hash=tx.tx_hash,
                        size_bytes=tx.size_bytes,
                        sender=slot[0] if slot else None,
                        nonce=slot[1] if slot else None,
                        payload=tx,
                    )
                )
            result: list[PendingTransaction] = []
            total_bytes = 0
            blocked: set[str] = set()
            for c in _order_for_drain(cands):
                if len(result) >= max_count:
                    break
                if c.sender is not None and c.sender in blocked:
                    continue
                if total_bytes + c.size_bytes > max_bytes:
                    # A head skipped for bytes must not let its later nonces drain.
                    if c.sender is not None:
                        blocked.add(c.sender)
                    continue
                result.append(c.payload)
                total_bytes += c.size_bytes

            for tx in result:
                self._drop_entry(chain_id, tx)

            self._update_gauge(chain_id)
            metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            return result

    def slot_occupant(self, chain_id: str | None, sender: str, nonce: int) -> str | None:
        """tx_hash currently holding the (sender, nonce) slot, if any."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        key = (sender or "").lower()
        with self._lock:
            return self._slots.get(chain_id, {}).get((key, nonce))

    def remove(self, tx_hash: str, chain_id: str | None = None) -> bool:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            entry = self._get_chain_transactions(chain_id).get(tx_hash)
            removed = entry is not None
            if entry is not None:
                self._drop_entry(chain_id, entry)
                self._update_gauge(chain_id)
            return removed

    def batch_remove(self, hashes: list[str], chain_id: str | None = None) -> int:
        """Parity with DatabaseMempool.batch_remove — in-memory has no
        reservations, so every hash is removable."""
        removed = 0
        for tx_hash in hashes:
            if self.remove(tx_hash, chain_id):
                removed += 1
        return removed

    def remove_superseded(self, chain_id: str, sender: str, nonce: int) -> int:
        """Drop pending entries whose (sender, nonce) slot a sealed block
        just consumed.

        A different-hash pending row at a nonce that sealed elsewhere can
        never seal — yet it keeps the slot occupied, refusing resubmits
        until TTL expiry (Refs #717). Dropping it the moment the block
        lands releases the sender's next nonce immediately. Entries at a
        lower nonce are equally dead (the nonce already moved past them).
        """
        removed = 0
        with self._lock:
            for entry in list(self._get_chain_transactions(chain_id).values()):
                # Only slot-holding (signed) entries may be swept — an
                # unsigned protocol-internal write must survive a sealed tx
                # from the same sender (#796).
                if _tx_slot_key(entry.content) is None:
                    continue
                if _tx_sender(entry.content) != sender.lower():
                    continue
                entry_nonce = _tx_nonce(entry.content)
                if entry_nonce is not None and entry_nonce <= nonce:
                    self._drop_entry(chain_id, entry)
                    removed += 1
            if removed:
                self._update_gauge(chain_id)
        return removed

    def size(self, chain_id: str | None = None) -> int:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return len(self._get_chain_transactions(chain_id))

    def pending_tx_hashes(self, chain_id: str | None = None) -> set[str]:
        """Hashes of pending entries on a chain — cheap, content-free."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return set(self._get_chain_transactions(chain_id))

    def reconcile_sealed(self, chain_id: str, sealed_tx_hashes: Iterable[str]) -> int:
        """In-memory parity stub for the DatabaseMempool reconcile — removes
        pooled rows the caller's chain-side check reports as sealed."""
        removed = 0
        for tx_hash in dict.fromkeys(sealed_tx_hashes):
            if self.remove(tx_hash, chain_id):
                removed += 1
        return removed

    def get_pending_transactions(self, chain_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id

        with self._lock:
            # Get transactions sorted by fee (highest first) and tx_hash (deterministic tiebreaker)
            sorted_txs = sorted(self._get_chain_transactions(chain_id).values(), key=lambda t: (-t.fee, t.tx_hash))

            # Return only the content, limited by the limit parameter
            return [tx.content for tx in sorted_txs[:limit]]

    def _drop_entry(self, chain_id: str, entry: PendingTransaction) -> None:
        """Remove an entry and its nonce-slot index record. Lock held by caller."""
        self._get_chain_transactions(chain_id).pop(entry.tx_hash, None)
        slot = _tx_slot_key(entry.content)
        if slot is not None:
            slots = self._slots.get(chain_id)
            if slots is not None and slots.get(slot) == entry.tx_hash:
                del slots[slot]

    def pending_cost(self, chain_id: str | None = None, sender: str = "", exclude_nonce: int | None = None) -> int:
        """Total amount+fee committed to the sender's signed pending transactions.

        Admission subtracts this from the sender's balance so an account cannot
        queue more than it can ever pay. Unsigned protocol-internal entries are
        excluded — escrow and bridge writes debit through their own paths.
        """
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        key = sender.lower()
        total = 0
        with self._lock:
            for entry in self._get_chain_transactions(chain_id).values():
                tx = entry.content
                if _tx_sender(tx) != key or not (tx.get("signature") or tx.get("sig")):
                    continue
                if exclude_nonce is not None and tx.get("nonce") == exclude_nonce:
                    continue
                total += _tx_cost(tx)
        return total

    def evict_expired(self, max_age: float) -> int:
        """Drop entries older than ``max_age`` seconds, across every chain.

        Capacity eviction only fires at max_size, which a stranded follower
        never reaches, so age is the only thing that reclaims those entries.
        """
        if max_age <= 0:
            return 0
        cutoff = time.time() - max_age
        removed = 0
        with self._lock:
            for chain_id, chain_transactions in self._transactions.items():
                stale = [h for h, t in chain_transactions.items() if t.received_at < cutoff]
                for tx_hash in stale:
                    entry = chain_transactions.get(tx_hash)
                    if entry is not None:
                        self._drop_entry(chain_id, entry)
                    metrics_registry.increment(f"mempool_evictions_total_{chain_id}")
                removed += len(stale)
                if stale:
                    self._update_gauge(chain_id)
        return removed


class DatabaseMempool(_DbAdmissionMixin, _DbReservationMixin):
    """PostgreSQL-backed mempool for persistence and cross-service sharing."""

    # Shared per-database admission lock: two pool objects on one database
    # (e.g. test doubles for separate worker processes) must serialize their
    # check-then-insert critical sections the same way the database itself
    # serializes writers. Real cross-process workers are covered by
    # _slot_advisory_lock on PostgreSQL.
    _db_locks: dict[str, RLock] = {}
    _db_locks_guard = Lock()

    def __init__(self, db_url: str, max_size: int = 10_000, min_fee: int = 0) -> None:
        self._db_url = db_url
        self._max_size = max_size
        self._min_fee = min_fee
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        self._install_sqlite_pragmas()
        with DatabaseMempool._db_locks_guard:
            self._lock = DatabaseMempool._db_locks.setdefault(db_url, RLock())
        self._init_table()

    def _install_sqlite_pragmas(self) -> None:
        """WAL + busy_timeout on pooled sqlite mempool connections (#1560).

        The production mempool URL is PostgreSQL and this is a no-op there;
        a ``sqlite:///`` URL previously got the 5s default timeout and a
        rollback journal.
        """
        if self._engine.dialect.name != "sqlite":
            return

        @event.listens_for(self._engine, "connect")
        def _apply(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
            finally:
                cursor.close()

    def _init_table(self) -> None:
        with self._lock:
            with Session(self._engine) as session:
                # node, rpc and p2p services all call init_mempool against the
                # same database at service start; two concurrent ALTERs on the
                # same relation deadlock (seen live on node2: node vs rpc on
                # ADD COLUMN). A transaction-level advisory lock serializes
                # schema setup across processes and is released automatically
                # at commit or rollback — a session-level lock would strand on
                # a pooled connection and hang the next service to start.
                if session.get_bind().dialect.name == "postgresql":
                    session.exec(text("SELECT pg_advisory_xact_lock(hashtext('aitbc_mempool_init'))"))  # type: ignore[call-overload]
                # Create table manually using raw SQL to avoid chain table conflicts
                session.exec(
                    text("""
                    CREATE TABLE IF NOT EXISTS mempool (
                        chain_id TEXT NOT NULL,
                        tx_hash TEXT NOT NULL,
                        content TEXT NOT NULL,
                        fee BIGINT DEFAULT 0,
                        size_bytes INTEGER DEFAULT 0,
                        received_at DOUBLE PRECISION NOT NULL,
                        sender TEXT,
                        nonce INTEGER,
                        signed BOOLEAN,
                        PRIMARY KEY (chain_id, tx_hash)
                    )
                """)
                )  # type: ignore[call-overload]
                session.exec(text("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)"))  # type: ignore[call-overload]
                self._ensure_slot_columns(session)
                session.exec(text("CREATE INDEX IF NOT EXISTS idx_mempool_sender_nonce ON mempool(chain_id, sender, nonce)"))  # type: ignore[call-overload]
                # #1300 P2-v2.4: owner/epoch reservation markers. Rows here
                # never own mempool state — they annotate pooled rows for the
                # duration of one proposer attempt.
                session.exec(
                    text("""
                    CREATE TABLE IF NOT EXISTS mempool_reservation (
                        chain_id TEXT NOT NULL,
                        tx_hash TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        attempt_seq INTEGER NOT NULL,
                        height INTEGER,
                        round INTEGER,
                        proposer TEXT,
                        reserved_at DOUBLE PRECISION NOT NULL,
                        expires_at DOUBLE PRECISION NOT NULL,
                        state TEXT NOT NULL DEFAULT 'reserved',
                        release_reason TEXT,
                        released_at DOUBLE PRECISION,
                        PRIMARY KEY (chain_id, tx_hash)
                    )
                """)
                )  # type: ignore[call-overload]
                session.exec(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_mempool_reservation_live "
                        "ON mempool_reservation(chain_id, state, expires_at)"
                    )
                )  # type: ignore[call-overload]
                session.commit()

    @staticmethod
    def _table_columns(session: Session) -> set[str]:
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            return {row[1] for row in session.exec(text("PRAGMA table_info(mempool)")).all()}  # type: ignore[call-overload]
        if dialect == "postgresql":
            return {
                row[0]
                for row in session.exec(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'mempool'")
                ).all()  # type: ignore[call-overload]
            }
        return set()

    def _ensure_slot_columns(self, session: Session) -> None:
        """Add sender/nonce/signed to mempool tables that predate the columns.

        The nonce-slot index needs real columns; rows written before the
        upgrade stay NULL and simply never occupy a slot — they drain or
        expire normally. ``signed`` (#796) marks slot-holding entries; NULL
        rows are treated as unsigned so a stale signed row can never be
        supersede-swept, only left to drain. A small backfill below derives
        the flag from each row's content.
        """
        existing = self._table_columns(session)
        if not existing:
            return
        # The ALTERs join the caller's transaction — committing here would
        # release the advisory lock while the migration is only half done.
        for column, ddl in (("sender", "TEXT"), ("nonce", "INTEGER"), ("signed", "BOOLEAN")):
            if column in existing:
                continue
            try:
                session.exec(text(f"ALTER TABLE mempool ADD COLUMN {column} {ddl}"))  # type: ignore[call-overload]
            except SQLAlchemyError:
                # Rolling back also releases the advisory lock and undoes
                # every ALTER in the transaction — a sender added moments
                # earlier is gone too if nonce failed. Verify all columns,
                # not just the one that errored: a writer that does not take
                # the lock (e.g. an older build) could still have added the
                # failing one meanwhile. Anything else must surface — a
                # missing column breaks every slot query from then on.
                session.rollback()
                if not {"sender", "nonce"} <= self._table_columns(session):
                    raise
        if "signed" in self._table_columns(session):
            self._backfill_signed_flag(session)

    def _backfill_signed_flag(self, session: Session) -> None:
        """Derive ``signed`` for rows written before the column existed."""
        rows = session.exec(
            select(MempoolEntry.chain_id, MempoolEntry.tx_hash, MempoolEntry.content).where(
                MempoolEntry.signed.is_(None)  # type: ignore[union-attr]
            )
        ).all()
        for chain_id, tx_hash, content in rows:
            try:
                tx = json.loads(content)
            except (TypeError, ValueError):
                continue
            session.exec(
                text("UPDATE mempool SET signed = :signed WHERE chain_id = :chain_id AND tx_hash = :tx_hash").bindparams(
                    signed=_tx_slot_key(tx) is not None, chain_id=chain_id, tx_hash=tx_hash
                )  # type: ignore[call-overload]
            )

    def _sealed_on_chain_tx_hashes(self, chain_id: str, tx_hashes: Iterable[str]) -> set[str]:
        """Hashes already sealed on chain — admission must refuse re-pooling.

        Predicate: ``Transaction.status='confirmed' AND block_height IS NOT
        NULL``. A NULL-height row is a pending writeback, not a seal, and
        does NOT refuse — that is the height_recorded edge (#1300). The
        mempool database is separate from chain.db, so the lookup runs
        through the chain session scope inside the admission critical
        section; a lookup failure fails OPEN with a warning because
        ``reconcile_sealed`` remains the sweeper for anything that slips.
        """
        hashes = [h for h in dict.fromkeys(tx_hashes) if h]
        if not hashes:
            return set()
        try:
            from .base_models import Transaction
            from .database import session_scope

            with session_scope(chain_id) as session:
                rows = session.execute(
                    select(Transaction.tx_hash).where(
                        Transaction.chain_id == chain_id,
                        Transaction.tx_hash.in_(hashes),  # type: ignore[attr-defined]
                        Transaction.status == "confirmed",
                        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                    )
                ).all()
            return {r[0] for r in rows}
        except (ImportError, SQLAlchemyError, OSError):
            logger.warning(
                "[MEMPOOL] sealed-on-chain check failed for %d hashes on %s — failing open",
                len(hashes),
                chain_id,
            )
            return set()


# Singleton
_MEMPOOL: InMemoryMempool | DatabaseMempool | None = None


def init_mempool(backend: str = "memory", db_url: str = "", max_size: int = 10_000, min_fee: int = 0) -> None:
    global _MEMPOOL
    if backend == "database" and db_url:
        _MEMPOOL = DatabaseMempool(db_url, max_size=max_size, min_fee=min_fee)
    else:
        _MEMPOOL = InMemoryMempool(max_size=max_size, min_fee=min_fee)


def get_mempool() -> InMemoryMempool | DatabaseMempool:
    global _MEMPOOL
    if _MEMPOOL is None:
        # Ghost-mempool guard (Refs #653): reaching get_mempool() before
        # init_mempool() means a process never ran the app's startup wiring —
        # a silent in-memory pool that shares nothing with the store of
        # record, exactly the duality behind mempool ghosts. Keep the
        # fallback for tests/tooling but make it loud and detectable:
        # the instance is flagged and the miss is logged once per process.
        _MEMPOOL = InMemoryMempool()
        _MEMPOOL._implicit = True  # type: ignore[attr-defined]
        logger.error(
            "get_mempool() called before init_mempool() — returning a transient in-memory pool; "
            "entries will be invisible to the configured mempool backend (ghost mempool)"
        )
    return _MEMPOOL
