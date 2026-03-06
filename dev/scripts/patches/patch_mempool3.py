with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "r") as f:
    content = f.read()

# Fix the missing chain_id parameter in _update_gauge call
content = content.replace(
    """def _update_gauge(self) -> None:""",
    """def _update_gauge(self, chain_id: str = "ait-devnet") -> None:"""
)

content = content.replace(
    """self._update_gauge()""",
    """self._update_gauge(chain_id)"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "w") as f:
    f.write(content)
