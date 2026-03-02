#!/bin/bash

# Force both nodes to stop and delete their databases
ssh aitbc-cascade "systemctl stop aitbc-blockchain-node-1 aitbc-blockchain-rpc-1 && rm -f /opt/blockchain-node/data/chain.db /opt/blockchain-node/data/mempool.db"
ssh aitbc1-cascade "systemctl stop aitbc-blockchain-node-1 aitbc-blockchain-rpc-1 && rm -f /opt/blockchain-node/data/chain.db /opt/blockchain-node/data/mempool.db"

# Update poa.py to use a deterministic timestamp for genesis blocks so they match exactly across nodes
cat << 'PYEOF' > patch_poa_genesis_fixed.py
with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

content = content.replace(
    """            timestamp = datetime.utcnow()
            block_hash = self._compute_block_hash(0, "0x00", timestamp)""",
    """            # Use a deterministic genesis timestamp so all nodes agree on the genesis block hash
            timestamp = datetime(2025, 1, 1, 0, 0, 0)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
PYEOF

python3 patch_poa_genesis_fixed.py
scp /home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py aitbc-cascade:/opt/blockchain-node/src/aitbc_chain/consensus/poa.py
scp /home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py aitbc1-cascade:/opt/blockchain-node/src/aitbc_chain/consensus/poa.py

# Restart everything
ssh aitbc-cascade "systemctl start aitbc-blockchain-node-1 aitbc-blockchain-rpc-1"
ssh aitbc1-cascade "systemctl start aitbc-blockchain-node-1 aitbc-blockchain-rpc-1"

echo "Waiting for nodes to start and create genesis blocks..."
sleep 5
