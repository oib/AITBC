with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "r") as f:
    content = f.read()

# Update _update_gauge method in DatabaseMempool
content = content.replace(
    """def _update_gauge(self) -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]""",
    """def _update_gauge(self, chain_id: str = "ait-devnet") -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM mempool WHERE chain_id = ?", (chain_id,)).fetchone()[0]"""
)

content = content.replace(
    """metrics_registry.increment("mempool_evictions_total")""",
    """metrics_registry.increment(f"mempool_evictions_total_{chain_id}")"""
)

content = content.replace(
    """metrics_registry.increment("mempool_tx_added_total")""",
    """metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")"""
)

content = content.replace(
    """metrics_registry.increment("mempool_tx_drained_total", float(len(result)))""",
    """metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))"""
)

content = content.replace(
    """metrics_registry.set_gauge("mempool_size", float(count))""",
    """metrics_registry.set_gauge(f"mempool_size_{chain_id}", float(count))"""
)

# Update InMemoryMempool calls too
content = content.replace(
    """def add(self, tx: Dict[str, Any]) -> str:
        fee = tx.get("fee", 0)""",
    """def add(self, tx: Dict[str, Any], chain_id: str = "ait-devnet") -> str:
        fee = tx.get("fee", 0)"""
)

# We are not updating InMemoryMempool extensively, since it's meant to be replaced with DatabaseMempool in production anyway.
# We'll just leave DatabaseMempool patched properly for our use case.

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "w") as f:
    f.write(content)
