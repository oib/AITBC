with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

# Fix block creation in _propose_block where chain_id might be missing
content = content.replace(
    """            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )""",
    """            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )"""
)

# Actually, the error says:
# [SQL: INSERT INTO block (chain_id, height, hash, parent_hash, proposer, timestamp, tx_count, state_root) VALUES (?, ?, ?, ?, ?, ?, ?, ?)]
# [parameters: (None, 1, '0x...', ...)]
# Why is chain_id None? Let's check _propose_block

content = content.replace(
    """            block = Block(
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )""",
    """            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
