#!/bin/bash
# AITBC Blockchain Sync Fix Script
# Resolves synchronization issues between genesis and follower nodes

echo "=== AITBC Blockchain Sync Fix ==="

# Check current status
echo "1. Current blockchain status:"
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')

echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"

# Check if aitbc has any blocks
if [ "$AITBC_HEIGHT" = "0" ] || [ "$AITBC_HEIGHT" = "null" ]; then
  echo "2. aitbc has no blocks - performing manual sync..."
  
  # Copy genesis block with proper format
  echo "   Copying genesis block..."
  scp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/genesis.json aitbc:/tmp/
  
  # Create proper genesis block format for import
  ssh aitbc 'cat > /tmp/genesis_proper.json << EOF
{
  "height": 0,
  "hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
  "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
  "timestamp": "1774794510",
  "proposer": "ait128p577qftddusxvtu4yvxjkwlnx232jlr8lrq57u93getatdrkcsqghm0q",
  "allocations": [
    {"address": "ait128p577qftddusxvtu4yvxjkwlnx232jlr8lrq57u93getatdrkcsqghm0q", "balance": 1000000000, "nonce": 0},
    {"address": "ait1uwunjewjrserytqzd28pmpkq46uyl2els8c2536f8e8496sahpcsy3r3cz", "balance": 0, "nonce": 0}
  ],
  "authorities": [
    {"address": "ait128p577qftddusxvtu4yvxjkwlnx232jlr8lrq57u93getatdrkcsqghm0q", "weight": 1}
  ],
  "params": {
    "base_fee": 10,
    "coordinator_ratio": 0.05,
    "fee_per_byte": 1,
    "mint_per_unit": 0
  }
}
EOF'
  
  # Import genesis block
  echo "   Importing genesis block..."
  ssh aitbc 'curl -X POST http://localhost:8006/rpc/importBlock -H "Content-Type: application/json" -d @/tmp/genesis_proper.json'
  
  # Restart services
  echo "   Restarting aitbc services..."
  ssh aitbc 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc'
  
  # Wait for services to start
  sleep 5
  
  # Check status again
  AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')
  echo "   aitbc height after genesis import: $AITBC_HEIGHT"
fi

# Sync recent blocks if still behind
if [ "$AITBC_HEIGHT" -lt "$((AITBC1_HEIGHT - 5))" ]; then
  echo "3. Syncing recent blocks from aitbc1..."
  
  # Get proposer address from genesis
  PROPOSER=$(cat /opt/aitbc/apps/blockchain-node/keystore/aitbc1genesis.json | jq -r '.address')
  
  for height in $(seq $((AITBC_HEIGHT + 1)) $AITBC1_HEIGHT); do
    echo "   Importing block $height..."
    
    # Get block from aitbc1
    curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height" | \
      jq '.blocks[0] + {"proposer": "'$PROPOSER'"}' > /tmp/block$height.json
    
    # Import to aitbc
    scp /tmp/block$height.json aitbc:/tmp/
    ssh aitbc "curl -X POST http://localhost:8006/rpc/importBlock -H 'Content-Type: application/json' -d @/tmp/block$height.json"
    
    sleep 1
  done
  
  echo "   Block sync completed!"
fi

# Final verification
echo "4. Final sync verification:"
AITBC1_FINAL=$(curl -s http://localhost:8006/rpc/head | jq .height)
AITBC_FINAL=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')

echo "aitbc1 final height: $AITBC1_FINAL"
echo "aitbc final height: $AITBC_FINAL"

if [ "$AITBC_FINAL" -ge "$((AITBC1_FINAL - 2))" ]; then
  echo "✅ Blockchain synchronization successful!"
else
  echo "⚠️ Sync may still be in progress"
fi

echo "=== Blockchain Sync Fix Complete ==="
