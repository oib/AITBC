#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Quick Deployment Script
# ============================================================================
# Simplified deployment that focuses on core implementation without complex tests
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
SCRIPTS_DIR="$AITBC_ROOT/scripts/plan"
CONFIG_DIR="$AITBC_ROOT/config"
LOG_FILE="$AITBC_ROOT/logs/quick_deployment.log"

# Environment detection
ENVIRONMENT="${1:-dev}"

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $1" >> "$LOG_FILE"
}

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

log_info "Starting AITBC Mesh Network Quick Deployment"
log_info "Environment: $ENVIRONMENT"
log_info "Timestamp: $(date)"

# Load environment configuration
env_config="$CONFIG_DIR/$ENVIRONMENT/.env"
if [[ ! -f "$env_config" ]]; then
    log_error "Environment config not found: $env_config"
    exit 1
fi

log_info "Loading environment configuration: $env_config"
source "$env_config"

# Phase deployment functions
deploy_phase() {
    local phase="$1"
    local script_name="$2"
    
    log_info "Deploying phase: $phase"
    
    local script_path="$SCRIPTS_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        log_error "Phase script not found: $script_path"
        return 1
    fi
    
    # Execute phase script
    if bash "$script_path"; then
        log_info "Phase $phase deployed successfully"
        return 0
    else
        log_error "Phase $phase deployment failed"
        return 1
    fi
}

# Deploy phases
log_info "Starting phase deployment..."

phases=(
    "consensus:01_consensus_setup.sh"
    "network:02_network_infrastructure.sh"
    "economics:03_economic_layer.sh"
    "agents:04_agent_network_scaling.sh"
    "contracts:05_smart_contracts.sh"
)

failed_phases=()

for phase_info in "${phases[@]}"; do
    phase="${phase_info%:*}"
    script="${phase_info#*:}"
    
    if ! deploy_phase "$phase" "$script"; then
        failed_phases+=("$phase")
        log_warn "Continuing with next phase despite $phase failure"
    fi
done

# Summary
log_info "Deployment Summary"
log_info "=================="

if [[ ${#failed_phases[@]} -eq 0 ]]; then
    log_info "✅ All phases deployed successfully"
    log_info "🎉 AITBC Mesh Network deployment complete!"
else
    log_warn "⚠️  Some phases had issues: ${failed_phases[*]}"
    log_info "Core infrastructure is deployed, but some features may be limited"
fi

# Health check
log_info "Running basic health checks..."

# Check if consensus modules are accessible
cd "$AITBC_ROOT"
python3 -c "
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    print('✅ Consensus modules accessible')
except Exception as e:
    print(f'❌ Consensus module error: {e}')
"

# Check configuration files
if [[ -f "$CONFIG_DIR/$ENVIRONMENT/.env" ]]; then
    log_info "✅ Environment configuration loaded"
else
    log_warn "⚠️  Environment configuration issue"
fi

# Check scripts
if [[ -f "$SCRIPTS_DIR/01_consensus_setup.sh" ]]; then
    log_info "✅ Implementation scripts present"
else
    log_warn "⚠️  Implementation scripts missing"
fi

# Generate deployment report
report_file="$AITBC_ROOT/logs/quick_deployment_report_$(date +%Y%m%d_%H%M%S).txt"
{
    echo "AITBC Mesh Network Quick Deployment Report"
    echo "=========================================="
    echo "Environment: $ENVIRONMENT"
    echo "Timestamp: $(date)"
    echo ""
    echo "Phase Results:"
    for phase_info in "${phases[@]}"; do
        phase="${phase_info%:*}"
        if [[ " ${failed_phases[@]} " =~ " ${phase} " ]]; then
            echo "  $phase: FAILED"
        else
            echo "  $phase: SUCCESS"
        fi
    done
    echo ""
    echo "Configuration: $env_config"
    echo "Log File: $LOG_FILE"
    echo ""
    echo "Next Steps:"
    echo "1. Monitor system: tail -f $LOG_FILE"
    echo "2. Test basic functionality"
    echo "3. Configure validators and agents"
    echo "4. Start network services"
} > "$report_file"

log_info "Deployment report generated: $report_file"

if [[ ${#failed_phases[@]} -eq 0 ]]; then
    log_info "🚀 Ready for network operations!"
    echo ""
    echo "Next Commands:"
    echo "1. Start services: ./scripts/start-services.sh"
    echo "2. Check status: ./scripts/check-status.sh"
    echo "3. Add validators: ./scripts/add-validator.sh <address>"
else
    log_info "🔧 Basic deployment complete with some limitations"
    echo ""
    echo "Recommended Actions:"
    echo "1. Review failed phases: ${failed_phases[*]}"
    echo "2. Fix test issues in affected phases"
    echo "3. Re-run specific phases as needed"
fi

log_info "Quick deployment completed!"
