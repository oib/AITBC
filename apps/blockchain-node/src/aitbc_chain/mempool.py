from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List

from .metrics import metrics_registry


@dataclass(frozen=True)
class PendingTransaction:
    tx_hash: str
    content: Dict[str, Any]
    received_at: float


class InMemoryMempool:
    def __init__(self) -> None:
        self._lock = Lock()
        self._transactions: Dict[str, PendingTransaction] = {}

    def add(self, tx: Dict[str, Any]) -> str:
        tx_hash = self._compute_hash(tx)
        entry = PendingTransaction(tx_hash=tx_hash, content=tx, received_at=time.time())
        with self._lock:
            self._transactions[tx_hash] = entry
            metrics_registry.set_gauge("mempool_size", float(len(self._transactions)))
        return tx_hash

    def list_transactions(self) -> List[PendingTransaction]:
        with self._lock:
            return list(self._transactions.values())

    def _compute_hash(self, tx: Dict[str, Any]) -> str:
        canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        return f"0x{digest}"


_MEMPOOL = InMemoryMempool()


def get_mempool() -> InMemoryMempool:
    return _MEMPOOL
