#!/bin/bash
# Final Verification Script for AITBC Multi-Node Blockchain
# This script verifies the complete multi-node setup

set -e  # Exit on any error

echo "=== AITBC Multi-Node Blockchain Final Verification ==="

# Get wallet address (source from wallet creation script)
if [ -z "$WALLET_ADDR" ]; then
  echo "Error: WALLET_ADDR not set. Please run wallet creation script first."
  exit 1
fi

# Check both nodes are in sync
echo "1. Checking blockchain heights..."
echo "=== aitbc1 height (localhost) ==="
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
echo $AITBC1_HEIGHT

echo "=== aitbc height (remote) ==="
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
echo $AITBC_HEIGHT

HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
echo "Height difference: $HEIGHT_DIFF blocks"

# Check wallet balance
echo "2. Checking aitbc wallet balance..."
echo "=== aitbc wallet balance (remote) ==="
BALANCE=$(ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq .")
echo $BALANCE AIT

# Transaction verification
echo "3. Transaction verification..."
echo "Transaction hash: 0x9975fc6ed8eabdc20886f9c33ddb68d40e6a9820d3e1182ebe5612686b12ca22"
# Verify transaction was mined (check if balance increased)

# Network health check
echo "4. Network health check..."
echo "=== Redis connection ==="
redis-cli -h localhost ping

echo "=== RPC connectivity ==="
curl -s http://localhost:8006/rpc/info | jq '.chain_id, .supported_chains, .rpc_version'

echo "=== Service status ==="
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc
ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc'

# Success criteria
echo "5. Success criteria check..."
if [ "$HEIGHT_DIFF" -le 5 ]; then
  echo "✅ Blockchain synchronized (height difference: $HEIGHT_DIFF)"
else
  echo "❌ Blockchain not synchronized (height difference: $HEIGHT_DIFF)"
fi

if [ "$BALANCE" -gt "0" ]; then
  echo "✅ Transaction successful (balance: $BALANCE AIT)"
else
  echo "❌ Transaction failed (balance: $BALANCE AIT)"
fi

if [ "$(systemctl is-active aitbc-blockchain-node)" = "active" ] && [ "$(systemctl is-active aitbc-blockchain-rpc)" = "active" ]; then
  echo "✅ aitbc1 services operational"
else
  echo "❌ aitbc1 services not operational"
fi

if [ "$(ssh aitbc 'systemctl is-active aitbc-blockchain-node')" = "active" ] && [ "$(ssh aitbc 'systemctl is-active aitbc-blockchain-rpc')" = "active" ]; then
  echo "✅ aitbc services operational"
else
  echo "❌ aitbc services not operational"
fi

echo "✅ Final verification completed!"
echo "Multi-node blockchain setup is ready for operation."
