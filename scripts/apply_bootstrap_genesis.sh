#!/bin/bash

echo "=== AITBC Bootstrap Genesis Setup ==="
echo ""

# Stop the blockchain node
echo "1. Stopping blockchain node..."
sudo systemctl stop aitbc-node

# Backup current data
echo "2. Backing up current blockchain data..."
sudo mv /root/aitbc/apps/blockchain-node/data/devnet/db.sqlite /root/aitbc/apps/blockchain-node/data/devnet/db.sqlite.backup.$(date +%s) 2>/dev/null || true

# Copy new genesis
echo "3. Applying bootstrap genesis..."
sudo cp /root/aitbc/apps/blockchain-node/data/genesis_with_bootstrap.json /root/aitbc/apps/blockchain-node/data/devnet/genesis.json

# Reset database
echo "4. Resetting blockchain database..."
sudo rm -f /root/aitbc/apps/blockchain-node/data/devnet/db.sqlite

# Restart blockchain node
echo "5. Restarting blockchain node..."
sudo systemctl start aitbc-node

# Wait for node to start
echo "6. Waiting for node to initialize..."
sleep 5

# Verify treasury balance
echo "7. Verifying treasury balance..."
curl -s http://localhost:9080/rpc/getBalance/aitbcexchange00000000000000000000000000000000 | jq

echo ""
echo "=== Bootstrap Complete! ==="
echo "Treasury should now have 10,000,000 AITBC"
echo ""
echo "Initial Distribution:"
echo "- Exchange Treasury: 10,000,000 AITBC (47.6%)"
echo "- Community Faucet: 1,000,000 AITBC (4.8%)"
echo "- Team Fund: 2,000,000 AITBC (9.5%)"
echo "- Early Investors: 5,000,000 AITBC (23.8%)"
echo "- Ecosystem Fund: 3,000,000 AITBC (14.3%)"
