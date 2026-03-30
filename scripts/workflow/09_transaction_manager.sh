#!/bin/bash
# AITBC Transaction Manager Script
# Enhanced transaction sending with proper error handling

echo "=== AITBC Transaction Manager ==="

# Configuration
GENESIS_WALLET="aitbc1genesis"
TARGET_WALLET="aitbc-user"
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
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r '.address')
TARGET_ADDR=$(/opt/aitbc/aitbc-cli balance --name aitbc-user 2>/dev/null | grep "Address:" | awk '{print $2}' || echo "")

echo "Genesis address: $GENESIS_ADDR"
echo "Target address: $TARGET_ADDR"

# Check balances
echo "3. Checking current balances..."
GENESIS_BALANCE=$(curl -s "http://localhost:8006/rpc/accounts/$GENESIS_ADDR" | jq .balance)
TARGET_BALANCE=$(curl -s "http://localhost:8006/rpc/accounts/$TARGET_ADDR" | jq .balance 2>/dev/null || echo "0")

echo "Genesis balance: $GENESIS_BALANCE AIT"
echo "Target balance: $TARGET_BALANCE AIT"

# Create transaction using RPC
echo "4. Creating and sending transaction..."
TX_DATA=$(cat << EOF
{
  "from": "$GENESIS_ADDR",
  "to": "$TARGET_ADDR",
  "amount": $AMOUNT,
  "fee": $FEE,
  "nonce": 0,
  "payload": "0x",
  "chain_id": "ait-mainnet",
  "signature": "0x1234567890"
}
EOF
)

echo "Transaction data: $TX_DATA"

# Send transaction
echo "5. Sending transaction..."
TX_RESULT=$(curl -s -X POST http://localhost:8006/rpc/transaction \
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
    NEW_BALANCE=$(curl -s "http://localhost:8006/rpc/accounts/$TARGET_ADDR" | jq .balance 2>/dev/null || echo "0")
    echo "Check $i/20: Target balance = $NEW_BALANCE AIT"
    
    # Handle null balance
    if [ "$NEW_BALANCE" = "null" ] || [ "$NEW_BALANCE" = "" ]; then
      NEW_BALANCE=0
    fi
    
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
  /opt/aitbc/aitbc-cli send \
    --from $GENESIS_WALLET \
    --to $TARGET_ADDR \
    --amount $AMOUNT \
    --fee $FEE \
    --password-file $PASSWORD_FILE
fi

# Final verification
echo "8. Final balance verification..."
FINAL_GENESIS_BALANCE=$(curl -s "http://localhost:8006/rpc/accounts/$GENESIS_ADDR" | jq .balance 2>/dev/null || echo "0")
FINAL_TARGET_BALANCE=$(curl -s "http://localhost:8006/rpc/accounts/$TARGET_ADDR" | jq .balance 2>/dev/null || echo "0")

# Handle null values
if [ "$FINAL_GENESIS_BALANCE" = "null" ] || [ "$FINAL_GENESIS_BALANCE" = "" ]; then
  FINAL_GENESIS_BALANCE=0
fi
if [ "$FINAL_TARGET_BALANCE" = "null" ] || [ "$FINAL_TARGET_BALANCE" = "" ]; then
  FINAL_TARGET_BALANCE=0
fi

echo "Final genesis balance: $FINAL_GENESIS_BALANCE AIT"
echo "Final target balance: $FINAL_TARGET_BALANCE AIT"

if [ "$FINAL_TARGET_BALANCE" -gt "$TARGET_BALANCE" ]; then
  echo "✅ Transaction completed successfully!"
else
  echo "❌ Transaction may have failed or is still pending"
fi

echo "=== Transaction Manager Complete ==="
