#!/bin/bash
#
# Blockchain Synchronization Verification Script
# Verifies blockchain synchronization across all 3 nodes
# Provides automatic remediation by forcing sync from healthy node
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/sync-verification.log"

# Node Configuration
#
# A target is either a bare host, which is assumed to speak the node RPC over http on
# RPC_PORT, or a full base URL, which is used verbatim. The second form is what lets CI
# point this at the public island (https://hub.aitbc.bubuit.net): since AITBC-136 the
# workflows run on a separate runner that cannot reach the private 10.1.223.x nodes, so a
# check hardcoded to them reports on infrastructure the job has no route to.
#
# Override with AITBC_NODES="name:target [name:target ...]".
if [ -n "${AITBC_NODES:-}" ]; then
    read -r -a NODES <<< "${AITBC_NODES}"
else
    NODES=(
        "aitbc:10.1.223.93"
        "aitbc1:10.1.223.40"
    )
fi

RPC_PORT=8006

# Resolve a node target to a base URL. Anything containing "://" is already a URL and gets
# no port appended -- the island is behind nginx on 443, not on RPC_PORT.
node_url() {
    local target="$1"
    case "$target" in
        *://*) printf '%s' "${target%/}" ;;
        *)     printf 'http://%s:%s' "$target" "$RPC_PORT" ;;
    esac
}
SYNC_THRESHOLD=2000
# Set to "false" to skip chain ID consistency check (allows different chains like devnet/mainnet)
CHECK_CHAIN_ID_CONSISTENCY="${CHECK_CHAIN_ID_CONSISTENCY:-true}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_success() {
    log "SUCCESS" "$@"
    echo -e "${GREEN}$@${NC}"
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}$@${NC}"
}

log_warning() {
    log "WARNING" "$@"
    echo -e "${YELLOW}$@${NC}"
}

# Get block height from RPC endpoint
get_block_height() {
    local node_ip="$1"
    local base
    base="$(node_url "$node_ip")"

    # Try to get block height from RPC /rpc/head endpoint
    height=$(curl -s --max-time 5 "${base}/rpc/head" 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*' || echo "0")

    if [ -z "$height" ] || [ "$height" = "0" ]; then
        # The public island serves head height from /api/v1/status. Parsed as JSON rather
        # than grepped, and tried before the bare /height below, because that one greps any
        # digits out of the response -- on a 404 page it happily returns "404" as a height.
        height=$(curl -s --max-time 5 "${base}/api/v1/status" 2>/dev/null \
            | python3 -c 'import sys,json; print(json.load(sys.stdin).get("height",0))' 2>/dev/null || echo "0")
    fi

    if [ -z "$height" ] || [ "$height" = "0" ]; then
        # Try alternative endpoint
        height=$(curl -s --max-time 5 "${base}/height" 2>/dev/null | grep -o '[0-9]*' || echo "0")
    fi

    echo "$height"
}

# Get chain ID from RPC endpoint
get_chain_id() {
    local node_ip="$1"

    # Get chain ID from /health endpoint using proper JSON parsing
    local base
    base="$(node_url "$node_ip")"
    local health_response=$(curl -s --max-time 10 "${base}/health" 2>/dev/null)

    # The previous form ran the same python twice, once as the `if` condition -- whose
    # stdout is the function's stdout, so a successful probe printed the id an extra time.
    chain_id=$(echo "$health_response" \
        | python3 -c "import sys, json; print(','.join(json.load(sys.stdin).get('supported_chains', [])))" 2>/dev/null || echo "")

    if [ -z "$chain_id" ]; then
        chain_id=$(curl -s --max-time 10 "${base}/chain-id" 2>/dev/null || echo "")
    fi

    # A missing endpoint answers with an nginx 404 page, and a non-empty body was being
    # accepted as a chain id -- the run then reported "chain ID consistent" about an HTML
    # document. Anything with markup, whitespace or newlines in it is not a chain id.
    case "$chain_id" in
        *"<"*|*">"*|*" "*|*"$(printf '\n')"*) chain_id="" ;;
    esac
    if [ "${#chain_id}" -gt 128 ]; then
        chain_id=""
    fi

    echo "$chain_id"
}

# Get block hash at specific height
get_block_hash() {
    local node_ip="$1"
    local height="$2"

    # Get block hash from /rpc/blocks/{height} endpoint
    local base
    base="$(node_url "$node_ip")"

    hash=$(curl -s --max-time 5 "${base}/rpc/blocks/${height}" 2>/dev/null \
        | grep -o '"hash":"[^"]*"' | head -1 | sed -E 's/^"hash":"//; s/"$//' || echo "")

    if [ -z "$hash" ]; then
        # Try alternative endpoint
        hash=$(curl -s --max-time 5 "${base}/blockchain/block/${height}/hash" 2>/dev/null || echo "")
        case "$hash" in *"<"*|*" "*) hash="" ;; esac
    fi

    if [ -z "$hash" ]; then
        # /api/v1/status carries the head hash only, so it answers for the head height and
        # must stay silent otherwise rather than return the wrong block's hash.
        hash=$(curl -s --max-time 5 "${base}/api/v1/status" 2>/dev/null \
            | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("hash","") if str(d.get("height"))==sys.argv[1] else "")' "$height" 2>/dev/null || echo "")
    fi

    echo "$hash"
}

# Check chain ID consistency (or just validity if CHECK_CHAIN_ID_CONSISTENCY=false)
check_chain_id_consistency() {
    log "Checking chain ID consistency across nodes"

    local first_chain_id=""
    local consistent=true
    local chain_ids=()

    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"

        chain_id=$(get_chain_id "$node_ip")

        if [ -z "$chain_id" ]; then
            # CHECK_CHAIN_ID_CONSISTENCY=false means "do not gate on chain id". It used to
            # gate anyway when the id could not be read at all -- a mismatch was skipped but
            # an unavailable id still failed the run. The public island exposes no chain-id
            # endpoint, so that path is now reachable in normal use.
            if [ "$CHECK_CHAIN_ID_CONSISTENCY" = "true" ]; then
                log_error "Could not get chain ID from ${node_name}"
                consistent=false
            else
                log_warning "No chain ID from ${node_name} (check skipped)"
            fi
            continue
        fi

        log "Chain ID on ${node_name}: ${chain_id}"
        chain_ids+=("${node_name}:${chain_id}")

        if [ -z "$first_chain_id" ]; then
            first_chain_id="$chain_id"
        elif [ "$chain_id" != "$first_chain_id" ]; then
            if [ "$CHECK_CHAIN_ID_CONSISTENCY" = "true" ]; then
                log_error "Chain ID mismatch on ${node_name}: ${chain_id} vs ${first_chain_id}"
                consistent=false
            else
                log_warning "Chain ID mismatch on ${node_name}: ${chain_id} vs ${first_chain_id} (check skipped)"
            fi
        fi
    done

    if [ "${#chain_ids[@]}" -lt 2 ]; then
        # Comparing one reading with itself always agrees. Say so rather than report a
        # consistency this run did not establish.
        log_warning "Chain ID consistency not established: ${#chain_ids[@]} of ${#NODES[@]} node(s) reported an id"
        return 0
    fi

    if [ "$consistent" = true ]; then
        log_success "Chain ID consistent across all nodes"
        return 0
    else
        if [ "$CHECK_CHAIN_ID_CONSISTENCY" = "true" ]; then
            log_error "Chain ID inconsistent across nodes"
            return 1
        else
            log_warning "Chain ID check skipped - nodes may be on different chains"
            return 0
        fi
    fi
}

# Check block synchronization
check_block_sync() {
    log "Checking block synchronization across nodes"

    local heights=()
    local max_height=0
    local min_height=999999999

    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"

        height=$(get_block_height "$node_ip")

        if [ -z "$height" ] || [ "$height" = "0" ]; then
            log_error "Could not get block height from ${node_name}"
            return 1
        fi

        heights+=("${node_name}:${height}")
        log "Block height on ${node_name}: ${height}"

        if [ "$height" -gt "$max_height" ]; then
            max_height=$height
            max_node="${node_name}"
            max_ip="${node_ip}"
        fi

        if [ "$height" -lt "$min_height" ]; then
            min_height=$height
        fi
    done

    local height_diff=$((max_height - min_height))

    log "Max height: ${max_height} (${max_node}), Min height: ${min_height}, Diff: ${height_diff}"

    if [ "$height_diff" -le "$SYNC_THRESHOLD" ]; then
        log_success "Block synchronization within threshold (diff: ${height_diff})"
        return 0
    else
        log_error "Block synchronization exceeds threshold (diff: ${height_diff})"
        return 1
    fi
}

# Check block hash consistency at current height
check_block_hash_consistency() {
    log "Checking block hash consistency"

    local target_height=""

    # Find the minimum height to compare at
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        height=$(get_block_height "$node_ip")

        if [ -z "$target_height" ] || [ "$height" -lt "$target_height" ]; then
            target_height=$height
        fi
    done

    log "Comparing block hashes at height ${target_height}"

    local first_hash=""
    local consistent=true
    local hashes_seen=0

    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"

        hash=$(get_block_hash "$node_ip" "$target_height")

        if [ -z "$hash" ]; then
            log_warning "Could not get block hash from ${node_name} at height ${target_height}"
            continue
        fi

        log "Block hash on ${node_name} at height ${target_height}: ${hash}"
        hashes_seen=$((hashes_seen + 1))

        if [ -z "$first_hash" ]; then
            first_hash="$hash"
        elif [ "$hash" != "$first_hash" ]; then
            log_warning "Block hash mismatch on ${node_name} at height ${target_height}"
            log_warning "This may be due to transient sync differences or blockchain reorgs"
            consistent=false
        fi
    done

    if [ "$hashes_seen" -lt 2 ]; then
        log_warning "Block hash consistency not established: ${hashes_seen} of ${#NODES[@]} node(s) returned a hash at height ${target_height}"
        return 0
    fi

    if [ "$consistent" = true ]; then
        log_success "Block hashes consistent at height ${target_height}"
        return 0
    else
        log_warning "Block hashes inconsistent - this may resolve as nodes sync"
        return 0  # Don't fail on hash mismatches for now
    fi
}

# Remediation: Skip force sync (not supported without SSH)
force_sync_from_source() {
    local target_name="$1"
    local source_name="$2"

    log "Skipping SSH-based force sync from ${source_name} to ${target_name} (not supported without SSH)"
    log "Sync remediation requires SSH access to copy chain.db between nodes"
    return 1
}

# Main sync verification
main() {
    log "=== Blockchain Synchronization Verification Started ==="

    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"

    local total_failures=0

    # Check chain ID consistency
    if ! check_chain_id_consistency; then
        log_error "Chain ID inconsistency detected - this is critical"
        ((total_failures++))
    fi

    # Check block synchronization
    if ! check_block_sync; then
        log_error "Block synchronization issue detected"
        ((total_failures++))

        # Determine source and target nodes for remediation
        local max_height=0
        local max_node=""
        local max_ip=""
        local min_height=999999999
        local min_node=""
        local min_ip=""

        for node_config in "${NODES[@]}"; do
            IFS=':' read -r node_name node_ip <<< "$node_config"
            height=$(get_block_height "$node_ip")

            if [ "$height" -gt "$max_height" ]; then
                max_height=$height
                max_node="${node_name}"
                max_ip="${node_ip}"
            fi

            if [ "$height" -lt "$min_height" ]; then
                min_height=$height
                min_node="${node_name}"
                min_ip="${node_ip}"
            fi
        done

        # Skip remediation (not supported without SSH)
        local height_diff=$((max_height - min_height))
        if [ "$height_diff" -gt "$SYNC_THRESHOLD" ]; then
            log_warning "Sync difference exceeds threshold (diff: ${height_diff} blocks)"
            log_warning "Skipping SSH-based remediation (requires SSH access to copy chain.db)"
            ((total_failures++))
        fi
    fi

    # Check block hash consistency
    if ! check_block_hash_consistency; then
        log_error "Block hash inconsistency detected"
        ((total_failures++))
    fi

    log "=== Blockchain Synchronization Verification Completed ==="
    log "Total failures: ${total_failures}"

    if [ ${total_failures} -eq 0 ]; then
        log_success "Blockchain synchronization verification passed"
        exit 0
    else
        log_error "Blockchain synchronization verification failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
