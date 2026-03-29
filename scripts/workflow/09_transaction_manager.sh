#!/bin/bash
# AITBC Transaction Manager Script
# Enhanced transaction sending with proper error handling

echo "=== AITBC Transaction Manager ==="

# Configuration
GENESIS_WALLET="aitbc1genesis"
TARGET_WALLET="aitbc-wallet"
AMOUNT=1000
FEE=10
PASSWORD_FILE="/var/lib/aitbc/keystore/.password"

# Check prerequisites
echo "1. Checking prerequisites..."
if [ ! -f "$PASSWORD_FILE" ]; then
  echo "❌ Password file not found: $PASSWORD_FILE"
  exit 1
fi

# Get wallet addresses
echo "2. Getting wallet addresses..."
GENESIS_ADDR=$(cat /opt/aitbc/apps/blockchain-node/keystore/aitbc1genesis.json | jq -r '.address')
TARGET_ADDR=$(ssh aitbc 'cat /var/lib/aitbc/keystore/aitbc-wallet.json | jq -r ".address"')

echo "Genesis address: $GENESIS_ADDR"
echo "Target address: $TARGET_ADDR"

# Check balances
echo "3. Checking current balances..."
GENESIS_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .balance)
TARGET_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$TARGET_ADDR" | jq .balance)

echo "Genesis balance: $GENESIS_BALANCE AIT"
echo "Target balance: $TARGET_BALANCE AIT"

# Create transaction using RPC
echo "4. Creating and sending transaction..."
TX_DATA=$(cat << EOF
{
  "type": "transfer",
  "from": "$GENESIS_ADDR",
  "sender": "$GENESIS_ADDR",
  "to": "$TARGET_ADDR",
  "amount": $AMOUNT,
  "fee": $FEE,
  "nonce": $GENESIS_BALANCE,
  "payload": "0x"
}
EOF
)

echo "Transaction data: $TX_DATA"

# Send transaction
echo "5. Sending transaction..."
TX_RESULT=$(curl -X POST http://localhost:8006/rpc/sendTx \
  -H "Content-Type: application/json" \
  -d "$TX_DATA")

echo "Transaction result: $TX_RESULT"

# Extract transaction hash if successful
TX_HASH=$(echo "$TX_RESULT" | jq -r '.hash // .transaction_hash // empty')

if [ -n "$TX_HASH" ] && [ "$TX_HASH" != "null" ]; then
  echo "✅ Transaction sent successfully!"
  echo "Transaction hash: $TX_HASH"
  
  # Wait for transaction to be mined
  echo "6. Waiting for transaction to be mined..."
  for i in {1..20}; do
    sleep 2
    NEW_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$TARGET_ADDR" | jq .balance)
    echo "Check $i/20: Target balance = $NEW_BALANCE AIT"
    
    if [ "$NEW_BALANCE" -gt "$TARGET_BALANCE" ]; then
      echo "✅ Transaction mined successfully!"
      echo "New balance: $NEW_BALANCE AIT"
      break
    fi
  done
else
  echo "❌ Transaction failed"
  echo "Error: $TX_RESULT"
  
  # Try alternative method using CLI
  echo "7. Trying alternative CLI method..."
  /opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py send \
    --from $GENESIS_WALLET \
    --to $TARGET_ADDR \
    --amount $AMOUNT \
    --fee $FEE \
    --password-file $PASSWORD_FILE \
    --rpc-url http://localhost:8006
fi

# Final verification
echo "8. Final balance verification..."
FINAL_GENESIS_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .balance)
FINAL_TARGET_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$TARGET_ADDR" | jq .balance)

echo "Final genesis balance: $FINAL_GENESIS_BALANCE AIT"
echo "Final target balance: $FINAL_TARGET_BALANCE AIT"

if [ "$FINAL_TARGET_BALANCE" -gt "$TARGET_BALANCE" ]; then
  TRANSFERRED=$((FINAL_TARGET_BALANCE - TARGET_BALANCE))
  echo "✅ Transaction successful! Transferred: $TRANSFERRED AIT"
else
  echo "❌ Transaction may have failed or is still pending"
fi

echo "=== Transaction Manager Complete ==="
