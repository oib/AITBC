from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from threading import Lock, RLock
from typing import Any, cast
from collections.abc import Iterable

from sqlalchemy import Column, Float, Index, Integer, MetaData, Text, delete, func
from sqlmodel import Field, Session, create_engine, select, text

from .metadata import ChainBase

from .metrics import metrics_registry

mempool_metadata = MetaData()


class MempoolEntry(ChainBase, table=True):
    __tablename__ = "mempool"
    __table_args__: Any = (
        Index("idx_mempool_fee", "fee", postgresql_ops={"fee": "DESC"}),
        Index("idx_mempool_chain_fee", "chain_id", "fee"),
        Index("idx_mempool_sender_nonce", "chain_id", "sender", "nonce"),
    )

    chain_id: str = Field(primary_key=True)
    tx_hash: str = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))
    fee: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    size_bytes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    received_at: float = Field(sa_column=Column(Float, nullable=False))
    sender: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    nonce: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


@dataclass(frozen=True)
class PendingTransaction:
    tx_hash: str
    content: dict[str, Any]
    received_at: float
    fee: int = 0
    size_bytes: int = 0


def compute_tx_hash(tx: dict[str, Any]) -> str:
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return f"0x{digest}"


def _estimate_size(tx: dict[str, Any]) -> int:
    return len(json.dumps(tx, separators=(",", ":")).encode())


def _tx_slot_key(tx: dict[str, Any]) -> tuple[str, int] | None:
    """(sender, nonce) slot key for externally submitted transactions.

    Only signed transactions compete for a slot: everything reaching a public
    intake (REST or gossip) must be signed, while protocol-internal writes —
    escrow movements, bridge locks and credits — carry no top-level signature
    and a placeholder nonce the proposer rewrites at seal time. Slot
    bookkeeping on those would only collide protocol writes with each other.
    """
    if not (tx.get("signature") or tx.get("sig")):
        return None
    sender = tx.get("from") or tx.get("sender")
    nonce = tx.get("nonce")
    if not isinstance(sender, str) or not sender:
        return None
    if not isinstance(nonce, int) or isinstance(nonce, bool) or nonce < 0:
        return None
    return sender.lower(), nonce


def _tx_sender(tx: dict[str, Any]) -> str:
    return str(tx.get("from") or tx.get("sender") or "").lower()


def _tx_nonce(tx: dict[str, Any]) -> int | None:
    nonce = tx.get("nonce")
    if isinstance(nonce, int) and not isinstance(nonce, bool):
        return nonce
    return None


def _tx_cost(tx: dict[str, Any]) -> int:
    try:
        return int(tx.get("amount") or 0) + int(tx.get("fee") or 0)
    except (TypeError, ValueError):
        return 0


def _claimed_lock_hashes(tx: dict[str, Any]) -> set[str]:
    if str(tx.get("type", "")).upper() != "STAKE_RELEASE":
        return set()
    return {str(h).lower() for h in (tx.get("payload") or {}).get("lock_tx_hashes") or []}


def _reject_conflicting_stake_release(tx: dict[str, Any], pending: Iterable[tuple[str, dict[str, Any]]]) -> None:
    """Same-block double-release guard: two STAKE_RELEASEs claiming the same
    lock may coexist in the mempool because neither is in confirmed history
    yet — the proposer would drain both and the second would pass the in-block
    check too (block tx records are flushed only at commit). Keep the first,
    drop the rest; the owner can re-queue after the block seals."""
    claimed = _claimed_lock_hashes(tx)
    if not claimed:
        return
    for pending_hash, pending_tx in pending:
        if claimed & _claimed_lock_hashes(pending_tx):
            raise ValueError(f"A pending release already claims one of these locks (tx {pending_hash})")


def _pending_tx_rows(session: Session, chain_id: str) -> Iterable[tuple[str, dict[str, Any]]]:
    for entry in session.exec(select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)).all():
        try:
            content = json.loads(entry.content)
        except (TypeError, ValueError):
            continue
        if isinstance(content, dict):
            yield entry.tx_hash, content


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
                    raise ValueError(
                        f"mempool full ({self._max_size}): fee {fee} does not beat lowest pending fee {lowest.fee}"
                    )
                self._drop_entry(chain_id, lowest)
                metrics_registry.increment(f"mempool_evictions_total_{chain_id}")
            chain_transactions[tx_hash] = entry
            if slot is not None:
                self._slots[chain_id][slot] = tx_hash
            metrics_registry.set_gauge("mempool_size", float(self._total_size()))
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
            sorted_txs = sorted(chain_transactions.values(), key=lambda t: (-t.fee, t.tx_hash))
            result: list[PendingTransaction] = []
            total_bytes = 0
            for tx in sorted_txs:
                if len(result) >= max_count:
                    break
                if total_bytes + tx.size_bytes > max_bytes:
                    continue
                result.append(tx)
                total_bytes += tx.size_bytes

            for tx in result:
                self._drop_entry(chain_id, tx)

            metrics_registry.set_gauge("mempool_size", float(self._total_size()))
            metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            return result

    def remove(self, tx_hash: str, chain_id: str | None = None) -> bool:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            entry = self._get_chain_transactions(chain_id).get(tx_hash)
            removed = entry is not None
            if entry is not None:
                self._drop_entry(chain_id, entry)
                metrics_registry.set_gauge("mempool_size", float(self._total_size()))
            return removed

    def size(self, chain_id: str | None = None) -> int:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return len(self._get_chain_transactions(chain_id))

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
            if removed:
                metrics_registry.set_gauge("mempool_size", float(self._total_size()))
        return removed


class DatabaseMempool:
    """PostgreSQL-backed mempool for persistence and cross-service sharing."""

    def __init__(self, db_url: str, max_size: int = 10_000, min_fee: int = 0) -> None:
        self._db_url = db_url
        self._max_size = max_size
        self._min_fee = min_fee
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        self._lock = RLock()
        self._init_table()

    def _init_table(self) -> None:
        with self._lock:
            with Session(self._engine) as session:
                # Create table manually using raw SQL to avoid chain table conflicts
                session.exec(
                    text("""
                    CREATE TABLE IF NOT EXISTS mempool (
                        chain_id TEXT NOT NULL,
                        tx_hash TEXT NOT NULL,
                        content TEXT NOT NULL,
                        fee INTEGER DEFAULT 0,
                        size_bytes INTEGER DEFAULT 0,
                        received_at REAL NOT NULL,
                        sender TEXT,
                        nonce INTEGER,
                        PRIMARY KEY (chain_id, tx_hash)
                    )
                """)
                )  # type: ignore[call-overload]
                session.exec(text("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)"))  # type: ignore[call-overload]
                self._ensure_slot_columns(session)
                session.exec(text("CREATE INDEX IF NOT EXISTS idx_mempool_sender_nonce ON mempool(chain_id, sender, nonce)"))  # type: ignore[call-overload]
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
        """Add sender/nonce to mempool tables that predate the columns.

        The nonce-slot index needs real columns; rows written before the
        upgrade stay NULL and simply never occupy a slot — they drain or
        expire normally.
        """
        existing = self._table_columns(session)
        if not existing:
            return
        for column, ddl in (("sender", "TEXT"), ("nonce", "INTEGER")):
            if column in existing:
                continue
            try:
                session.exec(text(f"ALTER TABLE mempool ADD COLUMN {column} {ddl}"))  # type: ignore[call-overload]
                session.commit()
            except Exception:
                # node, rpc and p2p services all call init_mempool — a sibling
                # may have added the column between our check and our ALTER.
                # Anything else must surface: a missing column breaks every
                # slot query from then on.
                session.rollback()
                if column not in self._table_columns(session):
                    raise

    def add(
        self,
        tx: dict[str, Any],
        chain_id: str | None = None,
        tx_hash: str | None = None,
        commit: bool = True,
    ) -> str:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        if tx_hash is None:
            tx_hash = compute_tx_hash(tx)
        content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        size_bytes = len(content.encode())
        if size_bytes > settings.mempool_max_tx_size_bytes:
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            raise ValueError(f"transaction size {size_bytes} exceeds limit {settings.mempool_max_tx_size_bytes}")

        with self._lock:
            with Session(self._engine) as session:
                # Check duplicate
                existing = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id, MempoolEntry.tx_hash == tx_hash)
                ).first()
                if existing:
                    if commit:
                        session.commit()
                    return tx_hash

                # Signed transactions compete for their (sender, nonce) slot:
                # a second occupant is admitted only as a strictly better bid,
                # replacing the first.
                slot = _tx_slot_key(tx)
                if slot is not None:
                    occupant = session.exec(
                        select(MempoolEntry).where(
                            MempoolEntry.chain_id == chain_id,
                            MempoolEntry.sender == slot[0],
                            MempoolEntry.nonce == slot[1],
                        )
                    ).first()
                    if occupant is not None and occupant.tx_hash != tx_hash:
                        if fee <= occupant.fee:
                            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                            raise ValueError(
                                f"nonce slot ({slot[0]}, {slot[1]}) already occupied by "
                                f"{occupant.tx_hash} with fee {occupant.fee} >= {fee}"
                            )
                        session.delete(occupant)
                        metrics_registry.increment(f"mempool_tx_replaced_total_{chain_id}")

                _reject_conflicting_stake_release(tx, _pending_tx_rows(session, chain_id))

                # Evict if full — but only for a newcomer that outbids the
                # floor, or a fee-floor flood could evict real transactions.
                count = session.exec(
                    select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).one()
                if count >= self._max_size:
                    to_evict = session.exec(
                        select(MempoolEntry)
                        .where(MempoolEntry.chain_id == chain_id)
                        .order_by(
                            cast(Any, MempoolEntry.fee).asc(),
                            cast(Any, MempoolEntry.received_at).asc(),
                            cast(Any, MempoolEntry.tx_hash).asc(),
                        )
                        .limit(1)
                    ).first()
                    if to_evict is None or fee <= to_evict.fee:
                        metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                        raise ValueError(
                            f"mempool full ({self._max_size}): fee {fee} does not beat lowest pending fee "
                            f"{to_evict.fee if to_evict is not None else 0}"
                        )
                    session.delete(to_evict)
                    metrics_registry.increment(f"mempool_evictions_total_{chain_id}")

                entry = MempoolEntry(
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    content=content,
                    fee=fee,
                    size_bytes=size_bytes,
                    received_at=time.time(),
                    sender=_tx_sender(tx) or None,
                    nonce=_tx_nonce(tx),
                )
                session.add(entry)
                if commit:
                    session.commit()
                metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
            self._update_gauge(chain_id)
        return tx_hash

    def batch_add(self, transactions: list[dict[str, Any]], chain_id: str | None = None) -> list[str]:
        """Add multiple transactions in a single session with a single commit."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id

        # Pre-compute all tx hashes and validate fees and sizes upfront
        tx_hashes: list[str] = []
        for tx in transactions:
            fee = tx.get("fee", 0)
            if fee < self._min_fee:
                raise ValueError(f"Fee {fee} below minimum {self._min_fee}")
            size = len(json.dumps(tx, sort_keys=True, separators=(",", ":")).encode())
            if size > settings.mempool_max_tx_size_bytes:
                raise ValueError(f"transaction size {size} exceeds limit {settings.mempool_max_tx_size_bytes}")
            tx_hashes.append(compute_tx_hash(tx))

        hashes: list[str] = []
        with self._lock:
            with Session(self._engine) as session:
                # Batch query: fetch all existing hashes in one query (N+1 → 1)
                existing_hashes: set[str] = set()
                if tx_hashes:
                    existing_rows = session.exec(
                        select(MempoolEntry.tx_hash).where(
                            MempoolEntry.chain_id == chain_id,
                            MempoolEntry.tx_hash.in_(tx_hashes),  # type: ignore[attr-defined]
                        )
                    ).all()
                    existing_hashes = set(existing_rows)

                # Fetch current count once before the loop (N+1 → 1)
                current_count = session.exec(
                    select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).one()

                for tx, tx_hash in zip(transactions, tx_hashes, strict=True):
                    # O(1) duplicate check using the pre-fetched set
                    if tx_hash in existing_hashes:
                        hashes.append(tx_hash)
                        continue

                    content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
                    size_bytes = len(content.encode())
                    fee = tx.get("fee", 0)

                    # Same nonce-slot rule as add(): a same-slot occupant is
                    # displaced only by a strictly higher fee.
                    slot = _tx_slot_key(tx)
                    if slot is not None:
                        occupant = session.exec(
                            select(MempoolEntry).where(
                                MempoolEntry.chain_id == chain_id,
                                MempoolEntry.sender == slot[0],
                                MempoolEntry.nonce == slot[1],
                            )
                        ).first()
                        if occupant is not None and occupant.tx_hash != tx_hash:
                            if fee <= occupant.fee:
                                metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                                continue
                            session.delete(occupant)
                            current_count -= 1
                            metrics_registry.increment(f"mempool_tx_replaced_total_{chain_id}")

                    # Evict if full (use in-memory count, decrement on eviction)
                    # — only when the newcomer outbids the floor.
                    if current_count >= self._max_size:
                        to_evict = session.exec(
                            select(MempoolEntry)
                            .where(MempoolEntry.chain_id == chain_id)
                            .order_by(
                                cast(Any, MempoolEntry.fee).asc(),
                                cast(Any, MempoolEntry.received_at).asc(),
                                cast(Any, MempoolEntry.tx_hash).asc(),
                            )
                            .limit(1)
                        ).first()
                        if to_evict is None or fee <= to_evict.fee:
                            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                            continue
                        session.delete(to_evict)
                        current_count -= 1
                        metrics_registry.increment(f"mempool_evictions_total_{chain_id}")

                    entry = MempoolEntry(
                        chain_id=chain_id,
                        tx_hash=tx_hash,
                        content=content,
                        fee=fee,
                        size_bytes=size_bytes,
                        received_at=time.time(),
                        sender=_tx_sender(tx) or None,
                        nonce=_tx_nonce(tx),
                    )
                    session.add(entry)
                    current_count += 1
                    existing_hashes.add(tx_hash)
                    hashes.append(tx_hash)
                    metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
                session.commit()
            self._update_gauge(chain_id)
        return hashes

    def list_transactions(self, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry)
                    .where(MempoolEntry.chain_id == chain_id)
                    .order_by(cast(Any, MempoolEntry.fee).desc(), cast(Any, MempoolEntry.received_at).asc())
                ).all()
        return [
            PendingTransaction(
                tx_hash=e.tx_hash, content=json.loads(e.content), fee=e.fee, size_bytes=e.size_bytes, received_at=e.received_at
            )
            for e in entries
        ]

    def drain(self, max_count: int, max_bytes: int, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                # Rank on the slim columns only: loading every pending row's
                # content per block is wasted memory when the pool holds
                # thousands of entries we will not include.
                entries = session.exec(
                    select(MempoolEntry.tx_hash, MempoolEntry.fee, MempoolEntry.size_bytes, MempoolEntry.received_at)
                    .where(MempoolEntry.chain_id == chain_id)
                    .order_by(cast(Any, MempoolEntry.fee).desc(), cast(Any, MempoolEntry.tx_hash).asc())
                ).all()

                picked: list[tuple[str, int, int, float]] = []
                total_bytes = 0
                for tx_hash, fee, size_bytes, received_at in entries:
                    if len(picked) >= max_count:
                        break
                    if total_bytes + size_bytes > max_bytes:
                        continue
                    picked.append((tx_hash, fee, size_bytes, received_at))
                    total_bytes += size_bytes

                result: list[PendingTransaction] = []
                if picked:
                    picked_hashes = [h for h, _, _, _ in picked]
                    content_by_hash = {
                        row[0]: row[1]
                        for row in session.exec(
                            select(MempoolEntry.tx_hash, MempoolEntry.content).where(
                                MempoolEntry.chain_id == chain_id,
                                MempoolEntry.tx_hash.in_(picked_hashes),  # type: ignore[attr-defined]
                            )
                        ).all()
                    }
                    result = [
                        PendingTransaction(
                            tx_hash=h,
                            content=json.loads(content_by_hash[h]),
                            fee=f,
                            size_bytes=s,
                            received_at=r,
                        )
                        for h, f, s, r in picked
                        if h in content_by_hash
                    ]
                    session.exec(
                        delete(MempoolEntry).where(
                            MempoolEntry.chain_id == chain_id,  # type: ignore[arg-type]
                            MempoolEntry.tx_hash.in_(picked_hashes),  # type: ignore[attr-defined]
                        )
                    )
                    session.commit()

                metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            self._update_gauge(chain_id)
            return result

    def pending_cost(self, chain_id: str | None = None, sender: str = "", exclude_nonce: int | None = None) -> int:
        """Total amount+fee committed to the sender's signed pending transactions.

        Same contract as ``InMemoryMempool.pending_cost``: only signed entries
        count, so protocol-internal writes (escrow, bridge) are not charged to
        the sender's admission budget.
        """
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                rows = session.exec(
                    select(MempoolEntry.nonce, MempoolEntry.content).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.sender == sender.lower(),
                    )
                ).all()
        total = 0
        for nonce_value, content in rows:
            if exclude_nonce is not None and nonce_value == exclude_nonce:
                continue
            try:
                tx = json.loads(content)
            except (TypeError, ValueError):
                continue
            if not isinstance(tx, dict) or not (tx.get("signature") or tx.get("sig")):
                continue
            total += _tx_cost(tx)
        return total

    def remove(self, tx_hash: str, chain_id: str | None = None, commit: bool = True) -> bool:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entry = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id, MempoolEntry.tx_hash == tx_hash)
                ).first()
                if entry:
                    session.delete(entry)
                    if commit:
                        session.commit()
                    removed = True
                else:
                    removed = False
            if removed:
                self._update_gauge(chain_id)
            return removed

    def batch_remove(self, hashes: list[str], chain_id: str | None = None) -> int:
        """Remove multiple transactions in a single session with a single commit."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        if not hashes:
            return 0

        with self._lock:
            with Session(self._engine) as session:
                result = session.exec(
                    delete(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,  # type: ignore[arg-type]
                        MempoolEntry.tx_hash.in_(hashes),  # type: ignore[attr-defined]
                    )
                )
                session.commit()
                removed = result.rowcount if result.rowcount is not None else 0
            self._update_gauge(chain_id)
        return removed

    def evict_expired(self, max_age: float) -> int:
        """Delete entries older than ``max_age`` seconds, across every chain.

        Entries here outlive the process, so a strand that a restart would have
        cleared in the in-memory backend persists until something removes it.
        """
        if max_age <= 0:
            return 0
        cutoff = time.time() - max_age
        with self._lock:
            with Session(self._engine) as session:
                stale_chains = session.exec(select(MempoolEntry.chain_id).where(MempoolEntry.received_at < cutoff)).all()
                if not stale_chains:
                    return 0
                result = session.exec(
                    delete(MempoolEntry).where(MempoolEntry.received_at < cutoff)  # type: ignore[arg-type]
                )
                session.commit()
                removed = result.rowcount if result.rowcount is not None else len(stale_chains)
            for chain_id in set(stale_chains):
                metrics_registry.increment(f"mempool_evictions_total_{chain_id}", float(stale_chains.count(chain_id)))
                self._update_gauge(chain_id)
        return removed

    def size(self, chain_id: str | None = None) -> int:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                count = session.exec(
                    select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).one()
                return count

    def get_pending_transactions(self, chain_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id

        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry)
                    .where(MempoolEntry.chain_id == chain_id)
                    .order_by(cast(Any, MempoolEntry.fee).desc(), cast(Any, MempoolEntry.tx_hash).asc())
                    .limit(limit)
                ).all()

        return [json.loads(e.content) for e in entries]

    def _update_gauge(self, chain_id: str | None = None) -> None:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        count = self.size(chain_id)
        metrics_registry.set_gauge(f"mempool_size_{chain_id}", float(count))


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
        _MEMPOOL = InMemoryMempool()
    return _MEMPOOL
