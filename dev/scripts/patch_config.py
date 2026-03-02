with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/config.py", "r") as f:
    content = f.read()

content = content.replace(
    """    chain_id: str = "ait-devnet\"""",
    """    supported_chains: str = "ait-devnet" # Comma-separated list of supported chain IDs"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/config.py", "w") as f:
    f.write(content)
