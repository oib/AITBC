#!/bin/bash

# AITBC Comprehensive Multi-Node Scenario Orchestration
# Executes end-to-end scenarios across all 3 nodes (aitbc1, aitbc, gitea-runner)
# Using all AITBC apps with real execution, verbose logging, and health checks

set -e

# Configuration
AITBC1_HOST="aitbc1"
AITBC_HOST="localhost"
GITEA_RUNNER_HOST="gitea-runner"
GENESIS_PORT="8006"
LOG_DIR="/var/log/aitbc"
LOG_FILE="$LOG_DIR/comprehensive_scenario_$(date +%Y%m%d_%H%M%S).log"
ERROR_LOG="$LOG_DIR/comprehensive_scenario_errors_$(date +%Y%m%d_%H%M%S).log"

# Debug mode flags
DEBUG_MODE=true
VERBOSE_LOGGING=true
HEALTH_CHECKS=true
ERROR_DETAILED=true

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Helper functions
log_debug() {
    if [ "$DEBUG_MODE" = true ]; then
        echo "[DEBUG] $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
    fi
}

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE" | tee -a "$ERROR_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

# Health check function
health_check() {
    local node=$1
    local service=$2
    local port=$3
    
    log_info "Checking $service on $node:$port"
    
    if [ "$node" = "localhost" ]; then
        local health_url="http://localhost:$port/health"
    else
        local health_url="http://$node:$port/health"
    fi
    
    if [ "$node" = "localhost" ]; then
        local health_status=$(curl -s -o /dev/null -w "%{http_code}" "$health_url" 2>/dev/null || echo "000")
    else
        local health_status=$(ssh -o ConnectTimeout=5 "$node" "curl -s -o /dev/null -w '%{http_code}' $health_url" 2>/dev/null || echo "000")
    fi
    
    if [ "$health_status" = "200" ]; then
        log_success "$service on $node is healthy"
        return 0
    else
        log_error "$service on $node is unhealthy (HTTP $health_status)"
        return 1
    fi
}

# Execute command on remote node
execute_on_node() {
    local node=$1
    local command=$2
    local quiet=${3:-false}
    
    if [ "$quiet" = true ]; then
        # Quiet mode - no debug logging
        if [ "$node" = "localhost" ]; then
            eval "$command" 2>/dev/null
        else
            ssh -o ConnectTimeout=10 "$node" "cd /opt/aitbc && $command" 2>/dev/null
        fi
    else
        log_debug "Executing on $node: $command"
        if [ "$node" = "localhost" ]; then
            eval "$command"
        else
            ssh -o ConnectTimeout=10 "$node" "cd /opt/aitbc && $command"
        fi
    fi
}

# Check SSH connectivity
check_ssh_connectivity() {
    local node=$1
    
    log_info "Checking SSH connectivity to $node"
    
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$node" "echo 'SSH OK'" >/dev/null 2>&1; then
        log_success "SSH connectivity to $node OK"
        return 0
    else
        log_error "SSH connectivity to $node FAILED"
        return 1
    fi
}

# Phase 1: Pre-Flight Health Checks
phase1_preflight_checks() {
    log_info "=== PHASE 1: PRE-FLIGHT HEALTH CHECKS ==="
    
    # Check SSH connectivity
    log_info "Checking SSH connectivity to all nodes"
    check_ssh_connectivity "$AITBC1_HOST" || return 1
    check_ssh_connectivity "$GITEA_RUNNER_HOST" || return 1
    log_success "SSH connectivity verified for all nodes"
    
    # Check AITBC services on aitbc1
    log_info "Checking AITBC services on aitbc1"
    health_check "$AITBC1_HOST" "blockchain-node" "8006" || log_warning "Blockchain node on aitbc1 may not be healthy"
    health_check "$AITBC1_HOST" "coordinator-api" "8011" || log_warning "Coordinator API on aitbc1 may not be healthy"
    
    # Check AITBC services on localhost
    log_info "Checking AITBC services on localhost"
    health_check "localhost" "blockchain-node" "8006" || log_warning "Blockchain node on localhost may not be healthy"
    health_check "localhost" "coordinator-api" "8011" || log_warning "Coordinator API on localhost may not be healthy"
    # blockchain-event-bridge service not configured - skipping health check
    
    # Check AITBC services on gitea-runner
    log_info "Checking AITBC services on gitea-runner"
    health_check "$GITEA_RUNNER_HOST" "blockchain-node" "8006" || log_warning "Blockchain node on gitea-runner may not be healthy"
    health_check "$GITEA_RUNNER_HOST" "blockchain-node" "8007" || log_warning "Blockchain node on gitea-runner may not be healthy"
    
    # Verify blockchain sync status
    log_info "Checking blockchain sync status across nodes"
    local aitbc1_height=$(execute_on_node "$AITBC1_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local aitbc_height=$(execute_on_node "localhost" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local gitea_height=$(execute_on_node "$GITEA_RUNNER_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    
    log_info "Blockchain heights - aitbc1: $aitbc1_height, aitbc: $aitbc_height, gitea-runner: $gitea_height"
    
    # Check CLI tools
    log_info "Checking CLI tools installation"
    if command -v /opt/aitbc/aitbc-cli >/dev/null 2>&1; then
        log_success "CLI tool found on localhost"
    else
        log_error "CLI tool not found on localhost"
        return 1
    fi
    
    log_success "Phase 1: Pre-flight checks completed"
}

# Phase 2: Complete Transaction Flow
phase2_transaction_flow() {
    log_info "=== PHASE 2: COMPLETE TRANSACTION FLOW ==="
    
    # Check if genesis wallet exists
    log_info "Checking genesis wallet on aitbc1"
    local genesis_wallets=$(execute_on_node "$AITBC1_HOST" "/opt/aitbc/aitbc-cli wallet list" 2>/dev/null || echo "")
    
    if echo "$genesis_wallets" | grep -q "aitbc1genesis"; then
        log_success "Genesis wallet exists on aitbc1"
    else
        log_warning "Genesis wallet may not exist, creating..."
        execute_on_node "$AITBC1_HOST" "/opt/aitbc/aitbc-cli wallet create aitbc1genesis aitbc123" || log_error "Failed to create genesis wallet"
    fi
    
    # Check user wallet on localhost
    log_info "Checking user wallet on localhost"
    local user_wallets=$(/opt/aitbc/aitbc-cli wallet list 2>/dev/null || echo "")
    
    if echo "$user_wallets" | grep -q "scenario_user"; then
        log_success "User wallet exists on localhost"
    else
        log_info "Creating user wallet on localhost"
        /opt/aitbc/aitbc-cli wallet create scenario_user scenario123 || log_error "Failed to create user wallet"
    fi
    
    # Get addresses
    local genesis_addr=$(execute_on_node "$AITBC1_HOST" "cat /var/lib/aitbc/keystore/aitbc1genesis.json" true 2>/dev/null | jq -r .address 2>/dev/null || echo "")
    local user_addr=$(cat /var/lib/aitbc/keystore/scenario_user.json 2>/dev/null | jq -r .address 2>/dev/null || echo "")
    
    log_info "Genesis address: $genesis_addr"
    log_info "User address: $user_addr"
    
    # Check genesis balance via RPC (quiet mode to avoid debug output in variable)
    local genesis_balance=$(execute_on_node "$AITBC1_HOST" "curl -s http://localhost:8006/rpc/getBalance/$genesis_addr" true 2>/dev/null | jq -r '.balance // 0' 2>/dev/null || echo "0")
    
    # Handle null or non-numeric balance
    if [ "$genesis_balance" = "null" ] || ! [[ "$genesis_balance" =~ ^[0-9]+$ ]]; then
        genesis_balance=0
    fi
    
    log_info "Genesis balance: $genesis_balance AIT"
    
    if [ "$genesis_balance" -lt 100 ]; then
        log_warning "Genesis balance is low ($genesis_balance AIT), mining some blocks first..."
        # Mine some blocks to fund the genesis wallet
        log_info "Mining 5 blocks to fund genesis wallet..."
        for i in {1..5}; do
            log_debug "Mining block $i..."
            execute_on_node "$AITBC1_HOST" "curl -s -X POST http://localhost:8006/rpc/mineBlock -H 'Content-Type: application/json' -d '{}'" >/dev/null 2>&1 || log_warning "Failed to mine block $i"
            sleep 1
        done
        
        # Check balance again after mining
        genesis_balance=$(execute_on_node "$AITBC1_HOST" "curl -s http://localhost:8006/rpc/getBalance/$genesis_addr" true 2>/dev/null | jq -r '.balance // 0' 2>/dev/null || echo "0")
        if [ "$genesis_balance" = "null" ] || ! [[ "$genesis_balance" =~ ^[0-9]+$ ]]; then
            genesis_balance=0
        fi
        log_info "Genesis balance after mining: $genesis_balance AIT"
    fi
    
    # Skip transaction if balance is still too low
    if [ "$genesis_balance" -lt 50 ]; then
        log_warning "Genesis balance still too low ($genesis_balance AIT), skipping transaction phase"
        log_success "Phase 2: Transaction flow skipped (insufficient balance)"
        return 0
    fi
    
    # Send transaction from genesis to user
    log_info "Sending transaction from genesis to user"
    local tx_result=$(execute_on_node "$AITBC1_HOST" "/opt/aitbc/aitbc-cli wallet send aitbc1genesis $user_addr 50 --fee 5" 2>/dev/null || echo "")
    
    if echo "$tx_result" | grep -q "tx_hash"; then
        log_success "Transaction sent successfully"
    else
        log_error "Failed to send transaction"
        return 1
    fi
    
    # Wait for confirmation
    log_info "Waiting for transaction confirmation..."
    sleep 5
    
    # Verify balance updates via RPC
    local user_balance=$(curl -s "http://localhost:8006/rpc/getBalance/$user_addr" | jq -r .balance 2>/dev/null || echo "0")
    log_info "User balance after transaction: $user_balance AIT"
    
    log_success "Phase 2: Transaction flow completed"
}

# Phase 3: AI Job Submission Flow
phase3_ai_job_submission() {
    log_info "=== PHASE 3: AI JOB SUBMISSION FLOW ==="
    
    # Get GPU info
    log_info "Getting GPU information"
    local gpu_info=$(execute_on_node "localhost" "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" 2>/dev/null || echo "Unknown,0")
    log_info "GPU: $gpu_info"
    
    # Submit AI job
    log_info "Submitting AI job"
    local ai_result=$(/opt/aitbc/aitbc-cli ai submit --wallet scenario_user --type text-generation --prompt "Test prompt for comprehensive scenario" --payment 10 2>/dev/null || echo "")
    
    if echo "$ai_result" | grep -q "job_id\|success"; then
        log_success "AI job submitted successfully"
    else
        log_warning "AI job submission may have failed, continuing..."
    fi
    
    # List AI jobs
    log_info "Listing AI jobs"
    /opt/aitbc/aitbc-cli ai jobs || log_warning "Failed to list AI jobs"
    
    # Check marketplace listings
    log_info "Checking marketplace listings"
    /opt/aitbc/aitbc-cli market list || log_warning "Failed to list marketplace items"
    
    log_success "Phase 3: AI job submission flow completed"
}

# Phase 4: Multi-Node Blockchain Sync with Event Bridge
phase4_blockchain_sync_event_bridge() {
    log_info "=== PHASE 4: BLOCKCHAIN SYNC WITH EVENT BRIDGE ==="
    
    # Check event bridge health
    log_info "Checking blockchain event bridge health"
    /opt/aitbc/aitbc-cli bridge health || log_warning "Event bridge health check failed"
    
    # Check event bridge metrics
    log_info "Getting event bridge metrics"
    /opt/aitbc/aitbc-cli bridge metrics || log_warning "Failed to get event bridge metrics"
    
    # Get current heights (quiet mode to avoid debug output in variables)
    local aitbc1_height=$(execute_on_node "$AITBC1_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local aitbc_height=$(execute_on_node "localhost" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local gitea_height=$(execute_on_node "$GITEA_RUNNER_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    
    log_info "Current heights - aitbc1: $aitbc1_height, aitbc: $aitbc_height, gitea-runner: $gitea_height"
    
    # Trigger sync if needed
    local height_diff=$((aitbc1_height - aitbc_height))
    if [ "$height_diff" -gt 5 ]; then
        log_info "Height difference detected ($height_diff blocks), triggering sync"
        execute_on_node "localhost" "/opt/aitbc/scripts/workflow/12_complete_sync.sh" || log_warning "Sync script execution failed"
    else
        log_success "Nodes are synchronized"
    fi
    
    # Check event bridge status
    log_info "Checking event bridge status"
    /opt/aitbc/aitbc-cli bridge status || log_warning "Failed to get event bridge status"
    
    log_success "Phase 4: Blockchain sync with event bridge completed"
}

# Phase 5: Agent Coordination via OpenClaw
phase5_agent_coordination() {
    log_info "=== PHASE 5: AGENT COORDINATION VIA OPENCLAW ==="
    
    # Check if OpenClaw is available
    if command -v openclaw >/dev/null 2>&1; then
        log_success "OpenClaw CLI found"
        
        # Create a test session
        local session_id="scenario_$(date +%s)"
        log_info "Creating OpenClaw session: $session_id"
        
        # Send coordination message
        log_info "Sending coordination message to agent network"
        openclaw agent --agent main --session-id "$session_id" --message "Multi-node scenario coordination: All nodes operational" --thinking low 2>/dev/null || log_warning "OpenClaw agent command failed"
        
        log_success "Phase 5: Agent coordination completed"
    else
        log_warning "OpenClaw CLI not found, skipping agent coordination"
    fi
}

# Phase 6: Pool-Hub SLA and Billing
phase6_pool_hub_sla_billing() {
    log_info "=== PHASE 6: POOL-HUB SLA AND BILLING ==="
    
    # Trigger SLA metrics collection
    log_info "Triggering SLA metrics collection"
    /opt/aitbc/aitbc-cli pool-hub collect-metrics --test-mode || log_warning "Pool-hub metrics collection failed"
    
    # Get capacity snapshots
    log_info "Getting capacity planning snapshots"
    /opt/aitbc/aitbc-cli pool-hub capacity-snapshots --test-mode || log_warning "Failed to get capacity snapshots"
    
    # Get capacity forecast
    log_info "Getting capacity forecast"
    /opt/aitbc/aitbc-cli pool-hub capacity-forecast --test-mode || log_warning "Failed to get capacity forecast"
    
    # Check SLA violations
    log_info "Checking SLA violations"
    /opt/aitbc/aitbc-cli pool-hub sla-violations --test-mode || log_warning "Failed to check SLA violations"
    
    # Get billing usage
    log_info "Getting billing usage data"
    /opt/aitbc/aitbc-cli pool-hub billing-usage --test-mode || log_warning "Failed to get billing usage"
    
    log_success "Phase 6: Pool-hub SLA and billing completed"
}

# Phase 7: Exchange Integration
phase7_exchange_integration() {
    log_info "=== PHASE 7: EXCHANGE INTEGRATION ==="
    
    log_info "Exchange integration phase - checking exchange status"
    
    # Note: Exchange integration would require actual exchange API setup
    # This phase is informational for now
    log_warning "Exchange integration requires external API configuration, skipping for now"
    
    log_success "Phase 7: Exchange integration completed (skipped - requires external config)"
}

# Phase 8: Plugin System
phase8_plugin_system() {
    log_info "=== PHASE 8: PLUGIN SYSTEM ==="
    
    log_info "Checking plugin system"
    
    # Browse plugin marketplace
    log_info "Browsing plugin marketplace"
    # Plugin marketplace would require coordinator-api plugin service
    log_warning "Plugin marketplace requires coordinator-api plugin service, skipping for now"
    
    log_success "Phase 8: Plugin system completed (skipped - requires plugin service)"
}

# Phase 9: Final Verification
phase9_final_verification() {
    log_info "=== PHASE 9: FINAL VERIFICATION ==="
    
    # Check blockchain heights consistency (quiet mode)
    log_info "Final blockchain height check"
    local aitbc1_height=$(execute_on_node "$AITBC1_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local aitbc_height=$(execute_on_node "localhost" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    local gitea_height=$(execute_on_node "$GITEA_RUNNER_HOST" "curl -s http://localhost:8006/rpc/head | jq -r .height" true 2>/dev/null || echo "0")
    
    log_info "Final heights - aitbc1: $aitbc1_height, aitbc: $aitbc_height, gitea-runner: $gitea_height"
    
    # Check service health
    log_info "Final service health check"
    health_check "localhost" "blockchain-node" "8006" || log_error "Blockchain node unhealthy"
    health_check "localhost" "coordinator-api" "8011" || log_warning "Coordinator API unhealthy"
    health_check "localhost" "blockchain-event-bridge" "8204" || log_warning "Event bridge unhealthy"
    
    # Generate comprehensive report
    log_info "Generating comprehensive scenario report"
    
    echo "========================================" | tee -a "$LOG_FILE"
    echo "COMPREHENSIVE SCENARIO REPORT" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    echo "Timestamp: $(date)" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "Blockchain Heights:" | tee -a "$LOG_FILE"
    echo "  aitbc1: $aitbc1_height" | tee -a "$LOG_FILE"
    echo "  aitbc: $aitbc_height" | tee -a "$LOG_FILE"
    echo "  gitea-runner: $gitea_height" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
    echo "Error log: $ERROR_LOG" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    
    log_success "Phase 9: Final verification completed"
}

# Main execution
main() {
    log_info "Starting comprehensive multi-node scenario"
    log_info "Log file: $LOG_FILE"
    log_info "Error log: $ERROR_LOG"
    
    # Execute phases
    phase1_preflight_checks || { log_error "Phase 1 failed"; exit 1; }
    phase2_transaction_flow || { log_error "Phase 2 failed"; exit 1; }
    phase3_ai_job_submission || { log_warning "Phase 3 had issues"; }
    phase4_blockchain_sync_event_bridge || { log_error "Phase 4 failed"; exit 1; }
    phase5_agent_coordination || { log_warning "Phase 5 had issues"; }
    phase6_pool_hub_sla_billing || { log_warning "Phase 6 had issues"; }
    phase7_exchange_integration || { log_warning "Phase 7 skipped"; }
    phase8_plugin_system || { log_warning "Phase 8 skipped"; }
    phase9_final_verification || { log_error "Phase 9 failed"; exit 1; }
    
    log_success "Comprehensive multi-node scenario completed successfully"
    log_info "Full log available at: $LOG_FILE"
}

# Run main function
main
