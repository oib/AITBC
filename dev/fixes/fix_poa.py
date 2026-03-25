import re

with open("/opt/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

# Make sure we use the correct chain_id when draining from mempool
new_content = content.replace("mempool.drain(max_txs, max_bytes, self._config.chain_id)", "mempool.drain(max_txs, max_bytes, 'ait-mainnet')")

with open("/opt/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(new_content)
