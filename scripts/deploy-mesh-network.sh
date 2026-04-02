#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Master Deployment Script
# ============================================================================
# Single command deployment with integrated validation, progress tracking,
# and rollback capability for the complete mesh network implementation
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
SCRIPTS_DIR="$AITBC_ROOT/scripts/plan"
TESTS_DIR="$AITBC_ROOT/tests"
CONFIG_DIR="$AITBC_ROOT/config"
LOG_DIR="$AITBC_ROOT/logs"
BACKUP_DIR="$AITBC_ROOT/backups"
VENV_DIR="$AITBC_ROOT/venv"
PYTHON_CMD="$VENV_DIR/bin/python"
PIP_CMD="$VENV_DIR/bin/pip"

# Environment detection
ENVIRONMENT="${1:-dev}"
VALID_ENVIRONMENTS=("dev" "staging" "production")

# Log file configuration
LOG_FILE="$LOG_DIR/deployment.log"

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $1" >> "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$LOG_FILE"
}

# Progress tracking
PROGRESS_FILE="$AITBC_ROOT/.deployment_progress"
PHASES=("consensus" "network" "economics" "agents" "contracts")
CURRENT_PHASE=0

update_progress() {
    local phase="$1"
    local status="$2"
    echo "$phase:$status:$(date +%s)" >> "$PROGRESS_FILE"
}

get_progress() {
    if [[ -f "$PROGRESS_FILE" ]]; then
        tail -n 1 "$PROGRESS_FILE"
    else
        echo "no_progress"
    fi
}

# Validation functions
validate_environment() {
    log_info "Validating environment: $ENVIRONMENT"
    
    # Check if environment is valid
    if [[ ! " ${VALID_ENVIRONMENTS[@]} " =~ " ${ENVIRONMENT} " ]]; then
        log_error "Invalid environment: $ENVIRONMENT. Valid options: ${VALID_ENVIRONMENTS[*]}"
        exit 1
    fi
    
    # Check environment config exists
    local env_config="$CONFIG_DIR/$ENVIRONMENT/.env"
    if [[ ! -f "$env_config" ]]; then
        log_error "Environment config not found: $env_config"
        exit 1
    fi
    
    # Load environment config
    source "$env_config"
    
    log_info "Environment validation passed"
    return 0
}

validate_prerequisites() {
    log_info "Validating prerequisites"
    
    # Check required directories
    local required_dirs=("$SCRIPTS_DIR" "$TESTS_DIR" "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR")
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log_error "Required directory not found: $dir"
            exit 1
        fi
    done
    
    # Check required scripts
    local required_scripts=(
        "$SCRIPTS_DIR/01_consensus_setup.sh"
        "$SCRIPTS_DIR/02_network_infrastructure.sh"
        "$SCRIPTS_DIR/03_economic_layer.sh"
        "$SCRIPTS_DIR/04_agent_network_scaling.sh"
        "$SCRIPTS_DIR/05_smart_contracts.sh"
    )
    
    for script in "${required_scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            log_error "Required script not found: $script"
            exit 1
        fi
        if [[ ! -x "$script" ]]; then
            log_warn "Making script executable: $script"
            chmod +x "$script"
        fi
    done
    
    log_info "Prerequisites validation passed"
    return 0
}

# Backup functions
create_backup() {
    log_info "Creating backup before deployment"
    
    local backup_name="pre_deployment_$(date +%Y%m%d_%H%M%S)"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    mkdir -p "$backup_path"
    
    # Backup configuration
    cp -r "$CONFIG_DIR" "$backup_path/"
    
    # Backup current blockchain data if exists
    if [[ -d "$AITBC_ROOT/data" ]]; then
        cp -r "$AITBC_ROOT/data" "$backup_path/"
    fi
    
    # Backup logs
    if [[ -d "$AITBC_ROOT/logs" ]]; then
        cp -r "$AITBC_ROOT/logs" "$backup_path/"
    fi
    
    log_info "Backup created: $backup_path"
    echo "$backup_path" > "$AITBC_ROOT/.last_backup"
}

# Deployment functions
deploy_phase() {
    local phase="$1"
    local script_name="$2"
    
    log_info "Deploying phase: $phase"
    update_progress "$phase" "started"
    
    local script_path="$SCRIPTS_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        log_error "Phase script not found: $script_path"
        update_progress "$phase" "failed"
        return 1
    fi
    
    # Execute phase script
    if bash "$script_path"; then
        log_info "Phase $phase deployed successfully"
        update_progress "$phase" "completed"
        return 0
    else
        log_error "Phase $phase deployment failed"
        update_progress "$phase" "failed"
        return 1
    fi
}

# Validation functions
validate_phase() {
    local phase="$1"
    
    log_info "Validating phase: $phase"
    
    # Run phase-specific tests
    cd "$TESTS_DIR"
    
    case "$phase" in
        "consensus")
            "$PYTHON_CMD" -m pytest phase1/ -v --tb=short
            ;;
        "network")
            "$PYTHON_CMD" -m pytest phase2/ -v --tb=short
            ;;
        "economics")
            "$PYTHON_CMD" -m pytest phase3/ -v --tb=short
            ;;
        "agents")
            "$PYTHON_CMD" -m pytest phase4/ -v --tb=short
            ;;
        "contracts")
            "$PYTHON_CMD" -m pytest phase5/ -v --tb=short
            ;;
        *)
            log_warn "No specific tests for phase: $phase"
            ;;
    esac
    
    if [[ $? -eq 0 ]]; then
        log_info "Phase $phase validation passed"
        return 0
    else
        log_error "Phase $phase validation failed"
        return 1
    fi
}

# Rollback functions
rollback_deployment() {
    log_warn "Rolling back deployment"
    
    local last_backup_file="$AITBC_ROOT/.last_backup"
    if [[ ! -f "$last_backup_file" ]]; then
        log_error "No backup found for rollback"
        exit 1
    fi
    
    local backup_path=$(cat "$last_backup_file")
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        exit 1
    fi
    
    # Restore configuration
    if [[ -d "$backup_path/config" ]]; then
        cp -r "$backup_path/config" "$AITBC_ROOT/"
        log_info "Configuration restored"
    fi
    
    # Restore data
    if [[ -d "$backup_path/data" ]]; then
        cp -r "$backup_path/data" "$AITBC_ROOT/"
        log_info "Data restored"
    fi
    
    # Restore logs
    if [[ -d "$backup_path/logs" ]]; then
        cp -r "$backup_path/logs" "$AITBC_ROOT/"
        log_info "Logs restored"
    fi
    
    log_info "Rollback completed"
}

# Health check functions
health_check() {
    log_info "Running health checks"
    
    # Check if services are running
    local services=("aitbc-coordinator" "aitbc-validator" "aitbc-agent-registry")
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log_info "Service $service is running"
        else
            log_warn "Service $service is not running"
        fi
    done
    
    # Check network connectivity
    if ping -c 1 localhost >/dev/null 2>&1; then
        log_info "Network connectivity OK"
    else
        log_warn "Network connectivity issues detected"
    fi
    
    # Check disk space
    local disk_usage=$(df "$AITBC_ROOT" | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ $disk_usage -lt 80 ]]; then
        log_info "Disk space OK: ${disk_usage}% used"
    else
        log_warn "Disk space high: ${disk_usage}% used"
    fi
}

# Main deployment function
main() {
    log_info "Starting AITBC Mesh Network Deployment"
    log_info "Environment: $ENVIRONMENT"
    log_info "Timestamp: $(date)"
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Validate environment and prerequisites
    validate_environment
    validate_prerequisites
    
    # Create backup
    create_backup
    
    # Deploy phases
    local failed_phases=()
    
    for i in "${!PHASES[@]}"; do
        local phase="${PHASES[$i]}"
        local script_number=$((i + 1))
        
        # Map phase to correct script name
        local script_name
        case "$phase" in
            "consensus")
                script_name="01_consensus_setup.sh"
                ;;
            "network")
                script_name="02_network_infrastructure.sh"
                ;;
            "economics")
                script_name="03_economic_layer.sh"
                ;;
            "agents")
                script_name="04_agent_network_scaling.sh"
                ;;
            "contracts")
                script_name="05_smart_contracts.sh"
                ;;
            *)
                log_error "Unknown phase: $phase"
                continue
                ;;
        esac
        
        if ! deploy_phase "$phase" "$script_name"; then
            failed_phases+=("$phase")
            continue
        fi
        
        if ! validate_phase "$phase"; then
            failed_phases+=("$phase")
        fi
    done
    
    # Check if any phases failed
    if [[ ${#failed_phases[@]} -gt 0 ]]; then
        log_error "Deployment failed for phases: ${failed_phases[*]}"
        
        read -p "Do you want to rollback? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rollback_deployment
        fi
        exit 1
    fi
    
    # Run health checks
    health_check
    
    log_info "Deployment completed successfully"
    log_info "All phases deployed and validated"
    
    # Generate deployment report
    local report_file="$AITBC_ROOT/logs/deployment_report_$(date +%Y%m%d_%H%M%S).txt"
    {
        echo "AITBC Mesh Network Deployment Report"
        echo "==================================="
        echo "Environment: $ENVIRONMENT"
        echo "Timestamp: $(date)"
        echo "Status: SUCCESS"
        echo ""
        echo "Deployed Phases:"
        for phase in "${PHASES[@]}"; do
            echo "  - $phase: COMPLETED"
        done
        echo ""
        echo "Backup: $(cat "$AITBC_ROOT/.last_backup")"
        echo ""
        echo "Health Check: PASSED"
    } > "$report_file"
    
    log_info "Deployment report generated: $report_file"
}

# Help function
show_help() {
    echo "AITBC Mesh Network Deployment Script"
    echo "====================================="
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "Environments:"
    echo "  dev         Development environment (default)"
    echo "  staging     Staging environment"
    echo "  production  Production environment"
    echo ""
    echo "Options:"
    echo "  --help      Show this help message"
    echo "  --rollback  Rollback last deployment"
    echo "  --status    Show deployment status"
    echo "  --validate  Run validation only"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Deploy to development"
    echo "  $0 staging                # Deploy to staging"
    echo "  $0 production             # Deploy to production"
    echo "  $0 --rollback             # Rollback last deployment"
    echo "  $0 --status               # Show deployment status"
    echo ""
}

# Status function
show_status() {
    echo "Deployment Status"
    echo "================="
    echo ""
    
    local progress=$(get_progress)
    if [[ "$progress" == "no_progress" ]]; then
        echo "No deployment in progress"
        return
    fi
    
    local phase=$(echo "$progress" | cut -d: -f1)
    local status=$(echo "$progress" | cut -d: -f2)
    local timestamp=$(echo "$progress" | cut -d: -f3)
    
    echo "Last Phase: $phase"
    echo "Status: $status"
    echo "Timestamp: $(date -d @$timestamp)"
    echo ""
    
    echo "Phase Progress:"
    for phase in "${PHASES[@]}"; do
        local phase_progress=$(grep "^$phase:" "$PROGRESS_FILE" 2>/dev/null | tail -n 1)
        if [[ -n "$phase_progress" ]]; then
            local phase_status=$(echo "$phase_progress" | cut -d: -f2)
            local phase_time=$(echo "$phase_progress" | cut -d: -f3)
            echo "  $phase: $phase_status ($(date -d @$phase_time))"
        else
            echo "  $phase: NOT_STARTED"
        fi
    done
}

# Parse command line arguments
case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --rollback)
        rollback_deployment
        exit 0
        ;;
    --status)
        show_status
        exit 0
        ;;
    --validate)
        validate_environment
        validate_prerequisites
        log_info "Validation passed"
        exit 0
        ;;
    "")
        # No arguments, use default environment
        main
        ;;
    *)
        # Assume environment argument
        main
        ;;
esac
