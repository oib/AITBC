with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "r") as f:
    content = f.read()

content = content.replace(
    """CREATE TABLE IF NOT EXISTS mempool (
                    tx_hash TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    fee INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    received_at REAL NOT NULL
                )""",
    """CREATE TABLE IF NOT EXISTS mempool (
                    chain_id TEXT NOT NULL,
                    tx_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    fee INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    received_at REAL NOT NULL,
                    PRIMARY KEY (chain_id, tx_hash)
                )"""
)

content = content.replace(
    """def add(self, tx: Dict[str, Any]) -> str:""",
    """def add(self, tx: Dict[str, Any], chain_id: str = "ait-devnet") -> str:"""
)

content = content.replace(
    """row = self._conn.execute("SELECT 1 FROM mempool WHERE tx_hash = ?", (tx_hash,)).fetchone()""",
    """row = self._conn.execute("SELECT 1 FROM mempool WHERE chain_id = ? AND tx_hash = ?", (chain_id, tx_hash)).fetchone()"""
)

content = content.replace(
    """count = self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]""",
    """count = self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]"""
)

content = content.replace(
    """DELETE FROM mempool WHERE tx_hash = (
                        SELECT tx_hash FROM mempool ORDER BY fee ASC, received_at DESC LIMIT 1
                    )""",
    """DELETE FROM mempool WHERE chain_id = ? AND tx_hash = (
                        SELECT tx_hash FROM mempool WHERE chain_id = ? ORDER BY fee ASC, received_at DESC LIMIT 1
                    )"""
)

content = content.replace(
    """self._conn.execute(
                "INSERT INTO mempool (tx_hash, content, fee, size_bytes, received_at) VALUES (?, ?, ?, ?, ?)",
                (tx_hash, content, fee, size_bytes, time.time())
            )""",
    """self._conn.execute(
                "INSERT INTO mempool (chain_id, tx_hash, content, fee, size_bytes, received_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chain_id, tx_hash, content, fee, size_bytes, time.time())
            )"""
)
content = content.replace(
    """if count >= self._max_size:
                self._conn.execute(\"\"\"
                    DELETE FROM mempool WHERE chain_id = ? AND tx_hash = (
                        SELECT tx_hash FROM mempool WHERE chain_id = ? ORDER BY fee ASC, received_at DESC LIMIT 1
                    )
                \"\"\")""",
    """if count >= self._max_size:
                self._conn.execute(\"\"\"
                    DELETE FROM mempool WHERE chain_id = ? AND tx_hash = (
                        SELECT tx_hash FROM mempool WHERE chain_id = ? ORDER BY fee ASC, received_at DESC LIMIT 1
                    )
                \"\"\", (chain_id, chain_id))"""
)


content = content.replace(
    """def list_transactions(self) -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool ORDER BY fee DESC, received_at ASC"
            ).fetchall()""",
    """def list_transactions(self, chain_id: str = "ait-devnet") -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool WHERE chain_id = ? ORDER BY fee DESC, received_at ASC",
                (chain_id,)
            ).fetchall()"""
)

content = content.replace(
    """def drain(self, max_count: int, max_bytes: int) -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool ORDER BY fee DESC, received_at ASC"
            ).fetchall()""",
    """def drain(self, max_count: int, max_bytes: int, chain_id: str = "ait-devnet") -> List[PendingTransaction]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx_hash, content, fee, size_bytes, received_at FROM mempool WHERE chain_id = ? ORDER BY fee DESC, received_at ASC",
                (chain_id,)
            ).fetchall()"""
)

content = content.replace(
    """self._conn.execute(f"DELETE FROM mempool WHERE tx_hash IN ({placeholders})", hashes_to_remove)""",
    """self._conn.execute(f"DELETE FROM mempool WHERE chain_id = ? AND tx_hash IN ({placeholders})", [chain_id] + hashes_to_remove)"""
)

content = content.replace(
    """def remove(self, tx_hash: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM mempool WHERE tx_hash = ?", (tx_hash,))""",
    """def remove(self, tx_hash: str, chain_id: str = "ait-devnet") -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM mempool WHERE chain_id = ? AND tx_hash = ?", (chain_id, tx_hash))"""
)

content = content.replace(
    """def size(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]""",
    """def size(self, chain_id: str = "ait-devnet") -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "w") as f:
    f.write(content)
