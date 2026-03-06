with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

# Update _propose_block
content = content.replace(
    """        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()""",
    """        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()"""
)

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

# Update _ensure_genesis_block
content = content.replace(
    """        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()""",
    """        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()"""
)

content = content.replace(
    """            genesis = Block(
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )""",
    """            genesis = Block(
                chain_id=self._config.chain_id,
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )"""
)

# Update _fetch_chain_head
content = content.replace(
    """    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()""",
    """    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()"""
)

# Broadcast metrics specific to chain
content = content.replace(
    """            metrics_registry.increment("blocks_proposed_total")
            metrics_registry.set_gauge("chain_head_height", float(next_height))""",
    """            metrics_registry.increment(f"blocks_proposed_total_{self._config.chain_id}")
            metrics_registry.set_gauge(f"chain_head_height_{self._config.chain_id}", float(next_height))"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
