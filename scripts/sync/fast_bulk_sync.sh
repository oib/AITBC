#!/bin/bash

# Fast AITBC Bulk Sync - Optimized for large sync differences

GENESIS_NODE="10.1.223.40"
GENESIS_PORT="8006"
LOCAL_PORT="8006"
MAX_SYNC_DIFF=100
BULK_BATCH_SIZE=1000

echo "=== 🚀 FAST AITBC BULK SYNC ==="
echo "Timestamp: $(date)"

# Get current heights
local_height=$(curl -s "http://localhost:$LOCAL_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")
genesis_height=$(curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")

diff=$((genesis_height - local_height))
echo "Current sync difference: $diff blocks"

if [ "$diff" -le $MAX_SYNC_DIFF ]; then
    echo "✅ Sync is within normal range"
    exit 0
fi

echo "🔄 Starting fast bulk sync..."
start_height=$((local_height + 1))
end_height=$genesis_height

# Process in larger batches
current_start=$start_height
while [ "$current_start" -le "$end_height" ]; do
    current_end=$((current_start + BULK_BATCH_SIZE - 1))
    if [ "$current_end" -gt "$end_height" ]; then
        current_end=$end_height
    fi
    
    echo "Processing batch: $current_start to $current_end"
    
    # Get blocks and import them
    curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/blocks-range?start=$current_start&end=$current_end" | \
    jq -r '.blocks[] | @base64' | while read -r block_b64; do
        if [ -n "$block_b64" ] && [ "$block_b64" != "null" ]; then
            block=$(echo "$block_b64" | base64 -d)
            height=$(echo "$block" | jq -r .height)
            hash=$(echo "$block" | jq -r .hash)
            parent_hash=$(echo "$block" | jq -r .parent_hash)
            proposer=$(echo "$block" | jq -r .proposer)
            timestamp=$(echo "$block" | jq -r .timestamp)
            tx_count=$(echo "$block" | jq -r .tx_count)
            
            # Create import request
            import_req="{\"height\":$height,\"hash\":\"$hash\",\"parent_hash\":\"$parent_hash\",\"proposer\":\"$proposer\",\"timestamp\":\"$timestamp\",\"tx_count\":$tx_count}"
            
            # Import block
            result=$(curl -s -X POST "http://localhost:$LOCAL_PORT/rpc/importBlock" \
                -H "Content-Type: application/json" \
                -d "$import_req" | jq -r .accepted 2>/dev/null || echo "false")
            
            if [ "$result" = "true" ]; then
                echo "✅ Imported block $height"
            fi
        fi
    done
    
    current_start=$((current_end + 1))
    sleep 0.5
done

# Check final result
final_height=$(curl -s "http://localhost:$LOCAL_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")
final_diff=$((genesis_height - final_height))

echo ""
echo "📊 SYNC RESULTS:"
echo "Initial difference: $diff blocks"
echo "Final difference: $final_diff blocks"
echo "Blocks synced: $((final_height - local_height))"

if [ "$final_diff" -le $MAX_SYNC_DIFF ]; then
    echo "✅ Fast bulk sync successful!"
else
    echo "⚠️  Partial sync, may need additional runs"
fi
