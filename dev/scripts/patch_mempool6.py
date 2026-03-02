with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "r") as f:
    content = f.read()

# Fix InMemoryMempool methods to accept chain_id
content = content.replace(
    """    def list_transactions(self) -> List[PendingTransaction]:""",
    """    def list_transactions(self, chain_id: str = "ait-devnet") -> List[PendingTransaction]:"""
)

content = content.replace(
    """    def drain(self, max_count: int, max_bytes: int) -> List[PendingTransaction]:""",
    """    def drain(self, max_count: int, max_bytes: int, chain_id: str = "ait-devnet") -> List[PendingTransaction]:"""
)

content = content.replace(
    """    def remove(self, tx_hash: str) -> bool:""",
    """    def remove(self, tx_hash: str, chain_id: str = "ait-devnet") -> bool:"""
)

content = content.replace(
    """    def size(self) -> int:""",
    """    def size(self, chain_id: str = "ait-devnet") -> int:"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/mempool.py", "w") as f:
    f.write(content)
