#!/bin/bash

GENESIS_NODE="10.1.223.40"
GENESIS_PORT="8006"
LOCAL_PORT="8006"
MAX_SYNC_DIFF=100
LOG_FILE="/var/log/aitbc/sync_detector.log"

log_sync() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

check_sync_diff() {
    local_height=$(curl -s "http://localhost:$LOCAL_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")
    genesis_height=$(curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")
    
    if [ "$local_height" -eq 0 ] || [ "$genesis_height" -eq 0 ]; then
        log_sync "ERROR: Cannot get blockchain heights"
        return 1
    fi
    
    diff=$((genesis_height - local_height))
    echo "$diff"
}

main() {
    log_sync "Starting sync check"
    
    diff=$(check_sync_diff)
    log_sync "Sync difference: $diff blocks"
    
    if [ "$diff" -gt "$MAX_SYNC_DIFF" ]; then
        log_sync "Large sync difference detected ($diff > $MAX_SYNC_DIFF), initiating bulk sync"
        /opt/aitbc/scripts/bulk_sync.sh >> "$LOG_FILE" 2>&1
        
        new_diff=$(check_sync_diff)
        log_sync "Post-sync difference: $new_diff blocks"
        
        if [ "$new_diff" -le "$MAX_SYNC_DIFF" ]; then
            log_sync "Bulk sync successful"
        else
            log_sync "Bulk sync partially successful, may need additional runs"
        fi
    else
        log_sync "Sync difference is normal ($diff <= $MAX_SYNC_DIFF)"
    fi
    
    log_sync "Sync check completed"
}

main
EOF && chmod +x /opt/aitbc/scripts/sync_detector.sh && echo "✅ Sync detector script fixed and made executable"
