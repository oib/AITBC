with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/config.py", "r") as f:
    content = f.read()

content = content.replace(
    """    chain_id: str = "ait-devnet\"""",
    """    chain_id: str = "ait-devnet"
    supported_chains: str = "ait-devnet" # Comma-separated list of supported chain IDs"""
)

# And define ProposerConfig in consensus/poa.py instead to avoid circular import or import issues
# Actually, the original code had it in consensus/poa.py, wait...
# In previous version `ProposerConfig` was defined in `consensus/poa.py` and we were trying to import it from `config.py`.
