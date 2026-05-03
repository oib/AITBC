from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlmodel import Session, SQLModel, create_engine, select, Field, text
from sqlalchemy import Column, String, Integer, Float, Text, Index, MetaData, Table

from .metrics import metrics_registry


mempool_metadata = MetaData()


class MempoolEntry(SQLModel, table=True):
    __tablename__ = "mempool"
    __table_args__ = {"metadata": mempool_metadata}
    
    chain_id: str = Field(primary_key=True)
    tx_hash: str = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))
    fee: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    size_bytes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    received_at: float = Field(sa_column=Column(Float, nullable=False))
    
    __table_args__ = (
        Index('idx_mempool_fee', 'fee', postgresql_ops={'fee': 'DESC'}),
    )


@dataclass(frozen=True)
class PendingTransaction:
    tx_hash: str
    content: Dict[str, Any]
    received_at: float
    fee: int = 0
    size_bytes: int = 0


def compute_tx_hash(tx: Dict[str, Any]) -> str:
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return f"0x{digest}"


def _estimate_size(tx: Dict[str, Any]) -> int:
    return len(json.dumps(tx, separators=(",", ":")).encode())


class InMemoryMempool:
    """In-memory mempool with fee-based prioritization and size limits."""

    def __init__(self, max_size: int = 10_000, min_fee: int = 0, chain_id: str = None) -> None:
        from .config import settings
        self._lock = Lock()
        self._transactions: Dict[str, Dict[str, PendingTransaction]] = {}
        self._max_size = max_size
        self._min_fee = min_fee
        self.chain_id = chain_id or settings.chain_id

    def _get_chain_transactions(self, chain_id: str) -> Dict[str, PendingTransaction]:
        return self._transactions.setdefault(chain_id, {})

    def _total_size(self) -> int:
        return sum(len(chain_txs) for chain_txs in self._transactions.values())

    def add(self, tx: Dict[str, Any], chain_id: str = None) -> str:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        tx_hash = compute_tx_hash(tx)
        size_bytes = _estimate_size(tx)
        entry = PendingTransaction(
            tx_hash=tx_hash, content=tx, received_at=time.time(),
            fee=fee, size_bytes=size_bytes
        )
        with self._lock:
            chain_transactions = self._get_chain_transactions(chain_id)
            if tx_hash in chain_transactions:
                return tx_hash  # duplicate
            if len(chain_transactions) >= self._max_size:
                self._evict_lowest_fee(chain_id)
            chain_transactions[tx_hash] = entry
            metrics_registry.set_gauge("mempool_size", float(self._total_size()))
            metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
        return tx_hash

    def list_transactions(self, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return list(self._get_chain_transactions(chain_id).values())

    def drain(self, max_count: int, max_bytes: int, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        """Drain transactions for block inclusion, prioritized by fee (highest first)."""
        with self._lock:
            chain_transactions = self._get_chain_transactions(chain_id)
            sorted_txs = sorted(
                chain_transactions.values(),
                key=lambda t: (-t.fee, t.received_at)
            )
            result: List[PendingTransaction] = []
            total_bytes = 0
            for tx in sorted_txs:
                if len(result) >= max_count:
                    break
                if total_bytes + tx.size_bytes > max_bytes:
                    continue
                result.append(tx)
                total_bytes += tx.size_bytes

            for tx in result:
                del chain_transactions[tx.tx_hash]

            metrics_registry.set_gauge("mempool_size", float(self._total_size()))
            metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            return result

    def remove(self, tx_hash: str, chain_id: str = None) -> bool:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            removed = self._get_chain_transactions(chain_id).pop(tx_hash, None) is not None
            if removed:
                metrics_registry.set_gauge("mempool_size", float(self._total_size()))
            return removed

    def size(self, chain_id: str = None) -> int:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return len(self._get_chain_transactions(chain_id))

    def get_pending_transactions(self, chain_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        
        with self._lock:
            # Get transactions sorted by fee (highest first) and time
            sorted_txs = sorted(
                self._get_chain_transactions(chain_id).values(),
                key=lambda t: (-t.fee, t.received_at)
            )
            
            # Return only the content, limited by the limit parameter
            return [tx.content for tx in sorted_txs[:limit]]

    def _evict_lowest_fee(self, chain_id: str) -> None:
        """Evict the lowest-fee transaction to make room."""
        chain_transactions = self._get_chain_transactions(chain_id)
        if not chain_transactions:
            return
        lowest = min(chain_transactions.values(), key=lambda t: (t.fee, -t.received_at))
        del chain_transactions[lowest.tx_hash]
        metrics_registry.increment(f"mempool_evictions_total_{chain_id}")


class DatabaseMempool:
    """PostgreSQL-backed mempool for persistence and cross-service sharing."""

    def __init__(self, db_url: str, max_size: int = 10_000, min_fee: int = 0) -> None:
        self._db_url = db_url
        self._max_size = max_size
        self._min_fee = min_fee
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        self._lock = Lock()
        self._init_table()

    def _init_table(self) -> None:
        with self._lock:
            with Session(self._engine) as session:
                # Create table manually using raw SQL to avoid chain table conflicts
                session.exec(text("""
                    CREATE TABLE IF NOT EXISTS mempool (
                        chain_id TEXT NOT NULL,
                        tx_hash TEXT NOT NULL,
                        content TEXT NOT NULL,
                        fee INTEGER DEFAULT 0,
                        size_bytes INTEGER DEFAULT 0,
                        received_at REAL NOT NULL,
                        PRIMARY KEY (chain_id, tx_hash)
                    )
                """))
                session.exec(text("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)"))
                session.commit()

    def add(self, tx: Dict[str, Any], chain_id: str = None) -> str:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        tx_hash = compute_tx_hash(tx)
        content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        size_bytes = len(content.encode())

        with self._lock:
            with Session(self._engine) as session:
                # Check duplicate
                existing = session.exec(
                    select(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.tx_hash == tx_hash
                    )
                ).first()
                if existing:
                    return tx_hash

                # Evict if full
                count = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).count()
                if count >= self._max_size:
                    to_evict = session.exec(
                        select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                        .order_by(MempoolEntry.fee.asc(), MempoolEntry.received_at.desc())
                        .limit(1)
                    ).first()
                    if to_evict:
                        session.delete(to_evict)
                        metrics_registry.increment(f"mempool_evictions_total_{chain_id}")

                entry = MempoolEntry(
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    content=content,
                    fee=fee,
                    size_bytes=size_bytes,
                    received_at=time.time()
                )
                session.add(entry)
                session.commit()
                metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
            self._update_gauge(chain_id)
        return tx_hash

    def list_transactions(self, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                    .order_by(MempoolEntry.fee.desc(), MempoolEntry.received_at.asc())
                ).all()
        return [
            PendingTransaction(
                tx_hash=e.tx_hash, content=json.loads(e.content),
                fee=e.fee, size_bytes=e.size_bytes, received_at=e.received_at
            ) for e in entries
        ]

    def drain(self, max_count: int, max_bytes: int, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                    .order_by(MempoolEntry.fee.desc(), MempoolEntry.received_at.asc())
                ).all()

                result: List[PendingTransaction] = []
                total_bytes = 0
                hashes_to_remove: List[str] = []

                for e in entries:
                    if len(result) >= max_count:
                        break
                    if total_bytes + e.size_bytes > max_bytes:
                        continue
                    result.append(PendingTransaction(
                        tx_hash=e.tx_hash, content=json.loads(e.content),
                        fee=e.fee, size_bytes=e.size_bytes, received_at=e.received_at
                    ))
                    total_bytes += e.size_bytes
                    hashes_to_remove.append(e.tx_hash)

                if hashes_to_remove:
                    for hash_to_remove in hashes_to_remove:
                        entry = session.exec(
                            select(MempoolEntry).where(
                                MempoolEntry.chain_id == chain_id,
                                MempoolEntry.tx_hash == hash_to_remove
                            )
                        ).first()
                        if entry:
                            session.delete(entry)
                    session.commit()

                metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            self._update_gauge(chain_id)
            return result

    def remove(self, tx_hash: str, chain_id: str = None) -> bool:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entry = session.exec(
                    select(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.tx_hash == tx_hash
                    )
                ).first()
                if entry:
                    session.delete(entry)
                    session.commit()
                    removed = True
                else:
                    removed = False
            if removed:
                self._update_gauge(chain_id)
            return removed

    def size(self, chain_id: str = None) -> int:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                return session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).count()

    def get_pending_transactions(self, chain_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        
        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                    .order_by(MempoolEntry.fee.desc(), MempoolEntry.received_at.asc())
                    .limit(limit)
                ).all()
        
        return [json.loads(e.content) for e in entries]

    def _update_gauge(self, chain_id: str = None) -> None:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        count = self.size(chain_id)
        metrics_registry.set_gauge(f"mempool_size_{chain_id}", float(count))


# Singleton
_MEMPOOL: Optional[InMemoryMempool | DatabaseMempool] = None


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
