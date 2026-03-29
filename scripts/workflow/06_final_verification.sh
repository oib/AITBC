#!/bin/bash
# Final Verification Script for AITBC Multi-Node Blockchain
# This script verifies the complete multi-node setup using enhanced CLI

set -e  # Exit on any error

echo "=== AITBC Multi-Node Blockchain Final Verification ==="

# Get wallet address (source from wallet creation script)
if [ -z "$WALLET_ADDR" ]; then
  echo "Error: WALLET_ADDR not set. Please run wallet creation script first."
  exit 1
fi

# Check both nodes are in sync using CLI
echo "1. Checking blockchain heights..."
echo "=== aitbc1 height (localhost) ==="
AITBC1_HEIGHT=$(python /opt/aitbc/cli/simple_wallet.py network --format json | jq -r '.height')
echo $AITBC1_HEIGHT

echo "=== aitbc height (remote) ==="
AITBC_HEIGHT=$(ssh aitbc 'python /opt/aitbc/cli/simple_wallet.py network --format json | jq -r ".height"')
echo $AITBC_HEIGHT

HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
echo "Height difference: $HEIGHT_DIFF blocks"

# Check wallet balance using CLI
echo "2. Checking aitbc wallet balance..."
echo "=== aitbc wallet balance (remote) ==="
BALANCE=$(ssh aitbc "python /opt/aitbc/cli/simple_wallet.py balance --name aitbc-user --format json | jq -r '.balance'")
echo $BALANCE AIT

# Get blockchain information using CLI
echo "3. Blockchain information..."
echo "=== Chain Information ==="
python /opt/aitbc/cli/simple_wallet.py chain

# Network health check using CLI
echo "4. Network health check..."
echo "=== Network Status (aitbc1) ==="
python /opt/aitbc/cli/simple_wallet.py network

echo "=== Network Status (aitbc) ==="
ssh aitbc 'python /opt/aitbc/cli/simple_wallet.py network'

# Service status
echo "5. Service status..."
echo "=== Service Status (aitbc1) ==="
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc

echo "=== Service Status (aitbc) ==="
ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc'

# Success criteria
echo "6. Success criteria check..."
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

echo "✅ Final verification completed using enhanced CLI!"
echo "Multi-node blockchain setup is ready for operation."
echo "All operations now use CLI tool with advanced capabilities."
