from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

from .metrics import metrics_registry


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
    """SQLite-backed mempool for persistence and cross-service sharing."""

    def __init__(self, db_path: str, max_size: int = 10_000, min_fee: int = 0) -> None:
        import sqlite3
        self._db_path = db_path
        self._max_size = max_size
        self._min_fee = min_fee
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = Lock()
        self._init_table()

    def _init_table(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS mempool (
                    chain_id TEXT NOT NULL,
                    tx_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    fee INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    received_at REAL NOT NULL,
                    PRIMARY KEY (chain_id, tx_hash)
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)")
            self._conn.commit()

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
            # Check duplicate
            row = self._conn.execute("SELECT 1 FROM mempool WHERE chain_id = ? AND tx_hash = ?", (chain_id, tx_hash)).fetchone()
            if row:
                return tx_hash

            # Evict if full
            count = self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]
            if count >= self._max_size:
                self._conn.execute("""
                    DELETE FROM mempool WHERE chain_id = ? AND tx_hash = (
                        SELECT tx_hash FROM mempool WHERE chain_id = ? ORDER BY fee ASC, received_at DESC LIMIT 1
                    )
                """, (chain_id, chain_id))
                metrics_registry.increment(f"mempool_evictions_total_{chain_id}")

            self._conn.execute(
                "INSERT INTO mempool (chain_id, tx_hash, content, fee, size_bytes, received_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chain_id, tx_hash, content, fee, size_bytes, time.time())
            )
            self._conn.commit()
            metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
            self._update_gauge(chain_id)
        return tx_hash

    def list_transactions(self, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool WHERE chain_id = ? ORDER BY fee DESC, received_at ASC",
                (chain_id,)
            ).fetchall()
        return [
            PendingTransaction(
                tx_hash=r[0], content=json.loads(r[1]),
                fee=r[2], size_bytes=r[3], received_at=r[4]
            ) for r in rows
        ]

    def drain(self, max_count: int, max_bytes: int, chain_id: str = None) -> List[PendingTransaction]:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool WHERE chain_id = ? ORDER BY fee DESC, received_at ASC",
                (chain_id,)
            ).fetchall()

            result: List[PendingTransaction] = []
            total_bytes = 0
            hashes_to_remove: List[str] = []

            for r in rows:
                if len(result) >= max_count:
                    break
                if total_bytes + r[3] > max_bytes:
                    continue
                result.append(PendingTransaction(
                    tx_hash=r[0], content=json.loads(r[1]),
                    fee=r[2], size_bytes=r[3], received_at=r[4]
                ))
                total_bytes += r[3]
                hashes_to_remove.append(r[0])

            if hashes_to_remove:
                placeholders = ",".join("?" * len(hashes_to_remove))
                self._conn.execute(f"DELETE FROM mempool WHERE chain_id = ? AND tx_hash IN ({placeholders})", [chain_id] + hashes_to_remove)
                self._conn.commit()

            metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            self._update_gauge(chain_id)
            return result

    def remove(self, tx_hash: str, chain_id: str = None) -> bool:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            cursor = self._conn.execute("DELETE FROM mempool WHERE chain_id = ? AND tx_hash = ?", (chain_id, tx_hash))
            self._conn.commit()
            removed = cursor.rowcount > 0
            if removed:
                self._update_gauge(chain_id)
            return removed

    def size(self, chain_id: str = None) -> int:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]

    def get_pending_transactions(self, chain_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        
        with self._lock:
            rows = self._conn.execute(
                "SELECT content FROM mempool WHERE chain_id = ? ORDER BY fee DESC, received_at ASC LIMIT ?",
                (chain_id, limit)
            ).fetchall()
        
        return [json.loads(row[0]) for row in rows]

    def _update_gauge(self, chain_id: str = None) -> None:
        from .config import settings
        if chain_id is None:
            chain_id = settings.chain_id
        count = self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]
        metrics_registry.set_gauge(f"mempool_size_{chain_id}", float(count))


# Singleton
_MEMPOOL: Optional[InMemoryMempool | DatabaseMempool] = None


def init_mempool(backend: str = "memory", db_path: str = "", max_size: int = 10_000, min_fee: int = 0) -> None:
    global _MEMPOOL
    if backend == "database" and db_path:
        _MEMPOOL = DatabaseMempool(db_path, max_size=max_size, min_fee=min_fee)
    else:
        _MEMPOOL = InMemoryMempool(max_size=max_size, min_fee=min_fee)


def get_mempool() -> InMemoryMempool | DatabaseMempool:
    global _MEMPOOL
    if _MEMPOOL is None:
        _MEMPOOL = InMemoryMempool()
    return _MEMPOOL
