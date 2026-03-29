#!/bin/bash
# AITBC Complete Blockchain Sync Script
# Handles complete synchronization between nodes

echo "=== AITBC Complete Blockchain Sync ==="

# Configuration
WALLET_ADDR="ait11c02342d4fec502240c20d609a8bb839ccd23838"

# Check current heights
echo "1. Current blockchain status:"
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")

echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"

# Check if sync is needed
if [ "$AITBC_HEIGHT" -ge "$((AITBC1_HEIGHT - 5))" ]; then
  echo "✅ Nodes are already synchronized (diff: $((AITBC1_HEIGHT - AITBC_HEIGHT)) blocks)"
  exit 0
fi

echo "2. Performing complete sync from aitbc1..."
echo "   Syncing from block $((AITBC_HEIGHT + 1)) to $AITBC1_HEIGHT"

# Get proposer address for proper block format
PROPOSER_ADDR=$(cat /opt/aitbc/apps/blockchain-node/keystore/aitbc1genesis.json | jq -r '.address')

# Sync blocks in batches
BATCH_SIZE=10
CURRENT_HEIGHT=$((AITBC_HEIGHT + 1))

while [ $CURRENT_HEIGHT -le $AITBC1_HEIGHT ]; do
  END_HEIGHT=$((CURRENT_HEIGHT + BATCH_SIZE - 1))
  if [ $END_HEIGHT -gt $AITBC1_HEIGHT ]; then
    END_HEIGHT=$AITBC1_HEIGHT
  fi
  
  echo "   Syncing batch: blocks $CURRENT_HEIGHT to $END_HEIGHT"
  
  # Import blocks in batch
  for height in $(seq $CURRENT_HEIGHT $END_HEIGHT); do
    echo "     Importing block $height..."
    
    # Get block with proper proposer field
    curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height" | \
      jq '.blocks[0] + {"proposer": "'$PROPOSER_ADDR'"}' > /tmp/block$height.json
    
    # Import to aitbc
    scp /tmp/block$height.json aitbc:/tmp/ 2>/dev/null
    ssh aitbc "curl -X POST http://localhost:8006/rpc/importBlock -H 'Content-Type: application/json' -d @/tmp/block$height.json" > /dev/null 2>&1
    
    sleep 0.5
  done
  
  # Check progress
  CURRENT_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')
  PROGRESS=$((CURRENT_HEIGHT * 100 / AITBC1_HEIGHT))
  echo "   Progress: $PROGRESS% ($CURRENT_HEIGHT/$AITBC1_HEIGHT blocks)"
  
  # Brief pause between batches
  sleep 2
done

echo "3. Final verification:"
FINAL_AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')
FINAL_DIFF=$((AITBC1_HEIGHT - FINAL_AITBC_HEIGHT))

echo "   aitbc1 final height: $AITBC1_HEIGHT"
echo "   aitbc final height: $FINAL_AITBC_HEIGHT"
echo "   Height difference: $FINAL_DIFF blocks"

if [ $FINAL_DIFF -le 2 ]; then
  echo "✅ Complete sync successful!"
else
  echo "⚠️ Sync may need additional time"
fi

# Final balance verification
echo "4. Final balance verification:"
if [ -n "$WALLET_ADDR" ]; then
  FINAL_BALANCE=$(ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq .balance 2>/dev/null || echo "0"")
  echo "   Wallet balance: $FINAL_BALANCE AIT"
fi

echo "=== Complete Blockchain Sync Finished ==="
