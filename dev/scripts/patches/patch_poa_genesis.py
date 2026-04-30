with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

content = content.replace(
    """    def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
            if head is not None:
                return

            timestamp = datetime.now(datetime.UTC)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)
            genesis = Block(
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )""",
    """    def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()
            if head is not None:
                return

            timestamp = datetime.now(datetime.UTC)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)
            genesis = Block(
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

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
