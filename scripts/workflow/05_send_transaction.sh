#!/bin/bash
# Transaction Sending Script for AITBC
# This script sends 1000 AIT from genesis to aitbc wallet using enhanced CLI

set -e  # Exit on any error

echo "=== AITBC Transaction Sending (Enhanced CLI) ==="

# Get wallet address (source from wallet creation script)
if [ -z "$WALLET_ADDR" ]; then
  echo "Error: WALLET_ADDR not set. Please run wallet creation script first."
  exit 1
fi

echo "1. Pre-transaction verification..."
echo "=== Genesis wallet balance (before) ==="
python /opt/aitbc/cli/aitbc_cli.py balance --name aitbc1genesis

echo "=== Target wallet address ==="
echo $WALLET_ADDR

echo "2. Sending 1000 AIT from genesis to aitbc wallet..."
# Send transaction using CLI
python /opt/aitbc/cli/aitbc_cli.py send \
  --from aitbc1genesis \
  --to $WALLET_ADDR \
  --amount 1000 \
  --fee 10 \
  --password-file /var/lib/aitbc/keystore/.password \
  --rpc-url http://localhost:8006

# Get transaction hash from CLI
echo "3. Transaction details..."
TX_HASH=$(python /opt/aitbc/cli/aitbc_cli.py transactions --from aitbc1genesis --limit 1 --format json 2>/dev/null | jq -r '.[0].hash' || echo "Transaction hash retrieval failed")
echo "Transaction hash: $TX_HASH"

# Wait for transaction to be mined with enhanced monitoring
echo "4. Monitoring transaction confirmation..."
for i in {1..10}; do
  sleep 2
  
  # Check balance using CLI
  BALANCE=$(ssh aitbc "python /opt/aitbc/cli/aitbc_cli.py balance --name aitbc-user --format json | jq -r '.balance'")
  
  if [ "$BALANCE" -gt "0" ]; then
    echo "✅ Transaction mined! Balance: $BALANCE AIT"
    break
  fi
  echo "Check $i/10: Balance = $BALANCE AIT"
done

# Final verification using CLI
echo "5. Post-transaction verification..."
echo "=== Genesis wallet balance (after) ==="
python /opt/aitbc/cli/aitbc_cli.py balance --name aitbc1genesis

echo "=== Target wallet balance (final) ==="
ssh aitbc "python /opt/aitbc/cli/aitbc_cli.py balance --name aitbc-user"

echo "=== Recent transactions ==="
python /opt/aitbc/cli/aitbc_cli.py transactions --from aitbc1genesis --limit 3

echo "✅ Transaction sent successfully using enhanced CLI!"
echo "From: aitbc1genesis"
echo "To: $WALLET_ADDR"
echo "Amount: 1000 AIT"
echo "Transaction hash: $TX_HASH"
echo "All operations used enhanced CLI capabilities."
