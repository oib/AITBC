import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix chain_id in sync endpoint
content = content.replace(
    """    sync = ChainSync(session_factory=session_scope, chain_id=cfg.chain_id)""",
    """    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)"""
)

# Any missed chain_id uses?
content = content.replace("Account.balance", "Account.balance") # just checking
with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
