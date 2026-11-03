#!/bin/bash


set -euo pipefail
# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

GENESIS_NODE="${NODE1_HOST}"
GENESIS_PORT="8006"
LOCAL_PORT="8006"
MAX_SYNC_DIFF=100
LOG_FILE="${AITBC_SYNC_LOG:-/var/log/aitbc/sync_detector.log}"

log_sync() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

check_sync_diff() {
    local_height=$(curl -s "http://localhost:$LOCAL_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")
    genesis_height=$(curl -s "http://$GENESIS_NODE:$GENESIS_PORT/rpc/head" | jq -r .height 2>/dev/null || echo "0")

    case "$local_height$genesis_height" in
        (""|*[!0-9]*) log_sync "ERROR: Cannot get blockchain heights (local=${local_height:-empty}, genesis=${genesis_height:-empty})"; return 1 ;;
    esac
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
        /opt/aitbc/venv/bin/aitbc network force-sync >> "$LOG_FILE" 2>&1

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
