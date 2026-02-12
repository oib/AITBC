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

    def __init__(self, max_size: int = 10_000, min_fee: int = 0) -> None:
        self._lock = Lock()
        self._transactions: Dict[str, PendingTransaction] = {}
        self._max_size = max_size
        self._min_fee = min_fee

    def add(self, tx: Dict[str, Any]) -> str:
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
            if tx_hash in self._transactions:
                return tx_hash  # duplicate
            if len(self._transactions) >= self._max_size:
                self._evict_lowest_fee()
            self._transactions[tx_hash] = entry
            metrics_registry.set_gauge("mempool_size", float(len(self._transactions)))
            metrics_registry.increment("mempool_tx_added_total")
        return tx_hash

    def list_transactions(self) -> List[PendingTransaction]:
        with self._lock:
            return list(self._transactions.values())

    def drain(self, max_count: int, max_bytes: int) -> List[PendingTransaction]:
        """Drain transactions for block inclusion, prioritized by fee (highest first)."""
        with self._lock:
            sorted_txs = sorted(
                self._transactions.values(),
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
                del self._transactions[tx.tx_hash]

            metrics_registry.set_gauge("mempool_size", float(len(self._transactions)))
            metrics_registry.increment("mempool_tx_drained_total", float(len(result)))
            return result

    def remove(self, tx_hash: str) -> bool:
        with self._lock:
            removed = self._transactions.pop(tx_hash, None) is not None
            if removed:
                metrics_registry.set_gauge("mempool_size", float(len(self._transactions)))
            return removed

    def size(self) -> int:
        with self._lock:
            return len(self._transactions)

    def _evict_lowest_fee(self) -> None:
        """Evict the lowest-fee transaction to make room."""
        if not self._transactions:
            return
        lowest = min(self._transactions.values(), key=lambda t: (t.fee, -t.received_at))
        del self._transactions[lowest.tx_hash]
        metrics_registry.increment("mempool_evictions_total")


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
                    tx_hash TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    fee INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    received_at REAL NOT NULL
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)")
            self._conn.commit()

    def add(self, tx: Dict[str, Any]) -> str:
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        tx_hash = compute_tx_hash(tx)
        content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        size_bytes = len(content.encode())

        with self._lock:
            # Check duplicate
            row = self._conn.execute("SELECT 1 FROM mempool WHERE tx_hash = ?", (tx_hash,)).fetchone()
            if row:
                return tx_hash

            # Evict if full
            count = self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]
            if count >= self._max_size:
                self._conn.execute("""
                    DELETE FROM mempool WHERE tx_hash = (
                        SELECT tx_hash FROM mempool ORDER BY fee ASC, received_at DESC LIMIT 1
                    )
                """)
                metrics_registry.increment("mempool_evictions_total")

            self._conn.execute(
                "INSERT INTO mempool (tx_hash, content, fee, size_bytes, received_at) VALUES (?, ?, ?, ?, ?)",
                (tx_hash, content, fee, size_bytes, time.time())
            )
            self._conn.commit()
            metrics_registry.increment("mempool_tx_added_total")
            self._update_gauge()
        return tx_hash

    def list_transactions(self) -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool ORDER BY fee DESC, received_at ASC"
            ).fetchall()
        return [
            PendingTransaction(
                tx_hash=r[0], content=json.loads(r[1]),
                fee=r[2], size_bytes=r[3], received_at=r[4]
            ) for r in rows
        ]

    def drain(self, max_count: int, max_bytes: int) -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool ORDER BY fee DESC, received_at ASC"
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
                self._conn.execute(f"DELETE FROM mempool WHERE tx_hash IN ({placeholders})", hashes_to_remove)
                self._conn.commit()

            metrics_registry.increment("mempool_tx_drained_total", float(len(result)))
            self._update_gauge()
            return result

    def remove(self, tx_hash: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM mempool WHERE tx_hash = ?", (tx_hash,))
            self._conn.commit()
            removed = cursor.rowcount > 0
            if removed:
                self._update_gauge()
            return removed

    def size(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]

    def _update_gauge(self) -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]
        metrics_registry.set_gauge("mempool_size", float(count))


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
