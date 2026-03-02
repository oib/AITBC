with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix DatabaseMempool.add() call in router.py
content = content.replace(
    "tx_hash = mempool.add(tx_dict, chain_id=chain_id)",
    "tx_hash = mempool.add(tx_dict, chain_id)"
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
