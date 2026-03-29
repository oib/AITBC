#!/bin/bash
# Transaction Sending Script for AITBC
# This script sends 1000 AIT from genesis to aitbc wallet

set -e  # Exit on any error

echo "=== AITBC Transaction Sending ==="

# Get wallet address (source from wallet creation script)
if [ -z "$WALLET_ADDR" ]; then
  echo "Error: WALLET_ADDR not set. Please run wallet creation script first."
  exit 1
fi

echo "1. Sending 1000 AIT from genesis to aitbc wallet..."
python /opt/aitbc/cli/simple_wallet.py send \
  --from aitbc1genesis \
  --to $WALLET_ADDR \
  --amount 1000 \
  --fee 10 \
  --password-file /var/lib/aitbc/keystore/.password \
  --rpc-url http://localhost:8006

# Get transaction hash for verification (simplified - using RPC to check latest transaction)
TX_HASH=$(curl -s http://localhost:8006/rpc/transactions --limit 1 | jq -r '.transactions[0].hash' 2>/dev/null || echo "Transaction hash retrieval failed")
echo "Transaction hash: $TX_HASH"

# Wait for transaction to be mined
echo "2. Waiting for transaction to be mined..."
for i in {1..10}; do
  sleep 2
  BALANCE=$(ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq .balance")
  if [ "$BALANCE" -gt "0" ]; then
    echo "Transaction mined! Balance: $BALANCE AIT"
    break
  fi
  echo "Check $i/10: Balance = $BALANCE AIT"
done

# Final balance verification
echo "3. Final balance verification..."
ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq ."

echo "✅ Transaction sent successfully!"
echo "From: aitbc1genesis"
echo "To: $WALLET_ADDR"
echo "Amount: 1000 AIT"
echo "Transaction hash: $TX_HASH"
