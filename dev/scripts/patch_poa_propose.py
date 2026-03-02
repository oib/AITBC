import re
with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

# Fix the head query to filter by chain_id in _propose_block
content = content.replace(
    """        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()""",
    """        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
