with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

content = content.replace(
    """            timestamp = datetime.now(datetime.UTC)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)""",
    """            # Use a deterministic genesis timestamp so all nodes agree on the genesis block hash
            timestamp = datetime(2025, 1, 1, 0, 0, 0)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
