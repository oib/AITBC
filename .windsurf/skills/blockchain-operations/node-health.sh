#!/bin/bash

# AITBC Node Health Check Script
# Monitors and reports on blockchain node health

set -e

# Configuration
NODE_URL="http://localhost:8545"
LOG_FILE="/var/log/aitbc/node-health.log"
ALERT_THRESHOLD=90  # Sync threshold percentage

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# JSON RPC call function
rpc_call() {
    local method=$1
    local params=$2
    curl -s -X POST $NODE_URL \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"$method\",\"params\":$params,\"id\":1}" \
        | jq -r '.result'
}

# Check if node is running
check_node_running() {
    echo -e "\n${BLUE}=== Checking Node Status ===${NC}"
    
    if pgrep -f "aitbc-node" > /dev/null; then
        echo -e "${GREEN}✓${NC} AITBC node process is running"
        log "Node process: RUNNING"
    else
        echo -e "${RED}✗${NC} AITBC node is not running"
        log "Node process: NOT RUNNING"
        return 1
    fi
}

# Check sync status
check_sync_status() {
    echo -e "\n${BLUE}=== Checking Sync Status ===${NC}"
    
    local sync_result=$(rpc_call "eth_syncing" "[]")
    
    if [ "$sync_result" = "false" ]; then
        echo -e "${GREEN}✓${NC} Node is fully synchronized"
        log "Sync status: FULLY SYNCED"
    else
        local current_block=$(echo $sync_result | jq -r '.currentBlock')
        local highest_block=$(echo $sync_result | jq -r '.highestBlock')
        local sync_percent=$(echo "scale=2; $current_block * 100 / $highest_block" | bc)
        
        if (( $(echo "$sync_percent > $ALERT_THRESHOLD" | bc -l) )); then
            echo -e "${YELLOW}⚠${NC} Node syncing: ${sync_percent}% (Block $current_block / $highest_block)"
            log "Sync status: SYNCING at ${sync_percent}%"
        else
            echo -e "${RED}✗${NC} Node far behind: ${sync_percent}% (Block $current_block / $highest_block)"
            log "Sync status: FAR BEHIND at ${sync_percent}%"
        fi
    fi
}

# Check peer connections
check_peers() {
    echo -e "\n${BLUE}=== Checking Peer Connections ===${NC}"
    
    local peer_count=$(rpc_call "net_peerCount" "[]")
    local peer_count_dec=$((peer_count))
    
    if [ $peer_count_dec -gt 0 ]; then
        echo -e "${GREEN}✓${NC} Connected to $peer_count_dec peers"
        log "Peer count: $peer_count_dec"
        
        # Get detailed peer info
        local peers=$(rpc_call "admin_peers" "[]")
        local active_peers=$(echo $peers | jq '. | length')
        echo -e "  Active peers: $active_peers"
        
        # Show peer countries
        echo -e "\n  Peer Distribution:"
        echo $peers | jq -r '.[].network.remoteAddress' | cut -d: -f1 | sort | uniq -c | sort -nr | head -5 | while read count ip; do
            country=$(geoiplookup $ip 2>/dev/null | awk -F': ' '{print $2}' | awk -F',' '{print $1}' || echo "Unknown")
            echo "    $country: $count peers"
        done
    else
        echo -e "${RED}✗${NC} No peer connections"
        log "Peer count: 0 - CRITICAL"
    fi
}

# Check block propagation
check_block_propagation() {
    echo -e "\n${BLUE}=== Checking Block Propagation ===${NC}"
    
    local latest_block=$(rpc_call "eth_getBlockByNumber" '["latest", false]')
    local block_number=$(echo $latest_block | jq -r '.number')
    local block_timestamp=$(echo $latest_block | jq -r '.timestamp')
    local current_time=$(date +%s)
    local block_age=$((current_time - block_timestamp))
    
    if [ $block_age -lt 30 ]; then
        echo -e "${GREEN}✓${NC} Latest block received ${block_age} seconds ago"
        log "Block propagation: ${block_age}s ago - GOOD"
    elif [ $block_age -lt 120 ]; then
        echo -e "${YELLOW}⚠${NC} Latest block received ${block_age} seconds ago"
        log "Block propagation: ${block_age}s ago - SLOW"
    else
        echo -e "${RED}✗${NC} Stale block (${block_age} seconds old)"
        log "Block propagation: ${block_age}s ago - CRITICAL"
    fi
    
    # Show block details
    local gas_limit=$(echo $latest_block | jq -r '.gasLimit')
    local gas_used=$(echo $latest_block | jq -r '.gasUsed')
    local utilization=$(echo "scale=2; $gas_used * 100 / $gas_limit" | bc)
    echo -e "  Block #$(($block_number)) - Gas utilization: ${utilization}%"
}

# Check resource usage
check_resources() {
    echo -e "\n${BLUE}=== Checking Resource Usage ===${NC}"
    
    # Memory usage
    local node_pid=$(pgrep -f "aitbc-node")
    if [ -n "$node_pid" ]; then
        local memory=$(ps -p $node_pid -o rss= | awk '{print $1/1024 " MB"}')
        local cpu=$(ps -p $node_pid -o %cpu= | awk '{print $1 "%"}')
        
        echo -e "  Memory usage: $memory"
        echo -e "  CPU usage: $cpu"
        log "Resource usage - Memory: $memory, CPU: $cpu"
        
        # Check if memory usage is high
        local memory_mb=$(ps -p $node_pid -o rss= | awk '{print $1}')
        if [ $memory_mb -gt 8388608 ]; then  # 8GB
            echo -e "${YELLOW}⚠${NC} High memory usage detected"
        fi
    fi
    
    # Disk usage for blockchain data
    local blockchain_dir="/var/lib/aitbc/blockchain"
    if [ -d "$blockchain_dir" ]; then
        local disk_usage=$(du -sh $blockchain_dir | awk '{print $1}')
        echo -e "  Blockchain data size: $disk_usage"
    fi
}

# Check consensus status
check_consensus() {
    echo -e "\n${BLUE}=== Checking Consensus Status ===${NC}"
    
    # Get latest block and verify consensus
    local latest_block=$(rpc_call "eth_getBlockByNumber" '["latest", false]')
    local block_hash=$(echo $latest_block | jq -r '.hash')
    local difficulty=$(echo $latest_block | jq -r '.difficulty')
    
    echo -e "  Latest block hash: ${block_hash:0:10}..."
    echo -e "  Difficulty: $difficulty"
    
    # Check for consensus alerts
    local chain_id=$(rpc_call "eth_chainId" "[]")
    echo -e "  Chain ID: $chain_id"
    
    log "Consensus check - Block: ${block_hash:0:10}..., Chain: $chain_id"
}

# Generate health report
generate_report() {
    echo -e "\n${BLUE}=== Health Report Summary ===${NC}"
    
    # Overall status
    local score=0
    local total=5
    
    # Node running
    if pgrep -f "aitbc-node" > /dev/null; then
        ((score++))
    fi
    
    # Sync status
    local sync_result=$(rpc_call "eth_syncing" "[]")
    if [ "$sync_result" = "false" ]; then
        ((score++))
    fi
    
    # Peers
    local peer_count=$(rpc_call "net_peerCount" "[]")
    if [ $((peer_count)) -gt 0 ]; then
        ((score++))
    fi
    
    # Block propagation
    local latest_block=$(rpc_call "eth_getBlockByNumber" '["latest", false]')
    local block_timestamp=$(echo $latest_block | jq -r '.timestamp')
    local current_time=$(date +%s)
    local block_age=$((current_time - block_timestamp))
    if [ $block_age -lt 30 ]; then
        ((score++))
    fi
    
    # Resources
    local node_pid=$(pgrep -f "aitbc-node")
    if [ -n "$node_pid" ]; then
        ((score++))
    fi
    
    local health_percent=$((score * 100 / total))
    
    if [ $health_percent -eq 100 ]; then
        echo -e "${GREEN}Overall Health: EXCELLENT (${health_percent}%)${NC}"
    elif [ $health_percent -ge 80 ]; then
        echo -e "${YELLOW}Overall Health: GOOD (${health_percent}%)${NC}"
    else
        echo -e "${RED}Overall Health: POOR (${health_percent}%)${NC}"
    fi
    
    log "Health check completed - Score: ${score}/${total} (${health_percent}%)"
}

# Main execution
main() {
    log "Starting node health check"
    echo -e "${BLUE}AITBC Node Health Check${NC}"
    echo "============================"
    
    check_node_running
    check_sync_status
    check_peers
    check_block_propagation
    check_resources
    check_consensus
    generate_report
    
    echo -e "\n${BLUE}Health check completed. Log saved to: $LOG_FILE${NC}"
}

# Run main function
main "$@"
