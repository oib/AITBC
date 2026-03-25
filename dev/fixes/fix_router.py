import re

with open("/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Make sure we use the correct chain_id when adding to mempool
new_content = content.replace("mempool.add(tx_dict, chain_id=chain_id)", "mempool.add(tx_dict, chain_id=chain_id or request.payload.get('chain_id') or 'ait-mainnet')")

with open("/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(new_content)
