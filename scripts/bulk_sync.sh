#!/bin/bash

# AITBC Bulk Sync Script
# Detects large sync differences and performs bulk synchronization

set -e

# Configuration
GENESIS_NODE="10.1.223.40"
GENESIS_PORT="8006"
LOCAL_PORT="8006"
MAX_SYNC_DIFF=100  # Trigger bulk sync if difference > 100 blocks
BULK_BATCH_SIZE=500  # Process 500 blocks at a time

echo "=== 🔄 AITBC BULK SYNC DETECTOR ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to get blockchain height
get_height() {
    local url=$1
    curl -s "$url/rpc/head" | jq -r .height 2>/dev/null || echo "0"
}

# Function to import a block
import_block() {
    local block_data=$1
    curl -s -X POST "http://localhost:$LOCAL_PORT/rpc/importBlock" \
        -H "Content-Type: application/json" \
        -d "$block_data" | jq -r .accepted 2>/dev/null || echo "false"
}

# Function to get blocks range
get_blocks_range() {
    local start=$1
    local end=$2
    curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/blocks-range?start=$start&end=$end" | jq -r '.blocks[]' 2>/dev/null
}

echo "1. 🔍 DETECTING SYNC DIFFERENCE"
echo "=============================="

# Get current heights
local_height=$(get_height "http://localhost:$LOCAL_PORT")
genesis_height=$(get_height "http://$GENESIS_NODE:$GENESIS_PORT")

echo "Local height: $local_height"
echo "Genesis height: $genesis_height"

# Calculate difference
if [ "$local_height" -eq 0 ] || [ "$genesis_height" -eq 0 ]; then
    echo -e "${RED}❌ ERROR: Cannot get blockchain heights${NC}"
    exit 1
fi

diff=$((genesis_height - local_height))
echo "Sync difference: $diff blocks"

# Determine if bulk sync is needed
if [ "$diff" -le $MAX_SYNC_DIFF ]; then
    echo -e "${GREEN}✅ Sync difference is within normal range ($diff <= $MAX_SYNC_DIFF)${NC}"
    echo "Normal sync should handle this difference."
    exit 0
fi

echo -e "${YELLOW}⚠️  LARGE SYNC DIFFERENCE DETECTED${NC}"
echo "Difference ($diff) exceeds threshold ($MAX_SYNC_DIFF)"
echo "Initiating bulk sync..."

echo ""
echo "2. 🔄 INITIATING BULK SYNC"
echo "=========================="

# Calculate sync range
start_height=$((local_height + 1))
end_height=$genesis_height

echo "Sync range: $start_height to $end_height"
echo "Batch size: $BULK_BATCH_SIZE blocks"

# Process in batches
current_start=$start_height
total_imported=0
total_failed=0

while [ "$current_start" -le "$end_height" ]; do
    current_end=$((current_start + BULK_BATCH_SIZE - 1))
    if [ "$current_end" -gt "$end_height" ]; then
        current_end=$end_height
    fi
    
    echo ""
    echo "Processing batch: $current_start to $current_end"
    
    # Get blocks from genesis node
    blocks_json=$(curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/blocks-range?start=$current_start&end=$current_end")
    
    if [ $? -ne 0 ] || [ -z "$blocks_json" ]; then
        echo -e "${RED}❌ Failed to get blocks range${NC}"
        break
    fi
    
    # Process each block in the batch
    batch_imported=0
    batch_failed=0
    
    # Extract blocks and import them
    echo "$blocks_json" | jq -c '.blocks[]' 2>/dev/null | while read -r block; do
        if [ -n "$block" ] && [ "$block" != "null" ]; then
            # Extract block data for import
            block_height=$(echo "$block" | jq -r .height)
            block_hash=$(echo "$block" | jq -r .hash)
            parent_hash=$(echo "$block" | jq -r .parent_hash)
            proposer=$(echo "$block" | jq -r .proposer)
            timestamp=$(echo "$block" | jq -r .timestamp)
            tx_count=$(echo "$block" | jq -r .tx_count)
            
            # Create import request
            import_request=$(cat << EOF
{
    "height": $block_height,
    "hash": "$block_hash",
    "parent_hash": "$parent_hash",
    "proposer": "$proposer",
    "timestamp": "$timestamp",
    "tx_count": $tx_count
}
EOF
            )
            
            # Import block
            result=$(import_block "$import_request")
            
            if [ "$result" = "true" ]; then
                echo -e "   ${GREEN}✅${NC} Imported block $block_height"
                ((batch_imported++))
            else
                echo -e "   ${RED}❌${NC} Failed to import block $block_height"
                ((batch_failed++))
            fi
        fi
    done
    
    # Update counters
    total_imported=$((total_imported + batch_imported))
    total_failed=$((total_failed + batch_failed))
    
    echo "Batch complete: $batch_imported imported, $batch_failed failed"
    
    # Move to next batch
    current_start=$((current_end + 1))
    
    # Brief pause to avoid overwhelming the system
    sleep 1
done

echo ""
echo "3. 📊 SYNC RESULTS"
echo "================"

# Final verification
final_local_height=$(get_height "http://localhost:$LOCAL_PORT")
final_diff=$((genesis_height - final_local_height))

echo "Initial difference: $diff blocks"
echo "Final difference: $final_diff blocks"
echo "Blocks imported: $total_imported"
echo "Blocks failed: $total_failed"

# Determine success
if [ "$final_diff" -le $MAX_SYNC_DIFF ]; then
    echo -e "${GREEN}✅ BULK SYNC SUCCESSFUL${NC}"
    echo "Sync difference is now within normal range."
else
    echo -e "${YELLOW}⚠️  PARTIAL SYNC${NC}"
    echo "Some blocks may still need to sync normally."
fi

echo ""
echo "=== 🔄 BULK SYNC COMPLETE ==="
