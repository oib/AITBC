with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/config.py", "r") as f:
    content = f.read()

content = content.replace(
    "class ChainSettings(BaseSettings):",
    """from pydantic import BaseModel

class ProposerConfig(BaseModel):
    chain_id: str
    proposer_id: str
    interval_seconds: int
    max_block_size_bytes: int
    max_txs_per_block: int

class ChainSettings(BaseSettings):"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/config.py", "w") as f:
    f.write(content)
