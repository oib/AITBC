#!/bin/bash

# AITBC Service Management Script
# Manages AITBC systemd services with dependency ordering and health checks

set -e

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service startup order (dependencies)
# Services are started in this order to ensure dependencies are met
CORE_SERVICES=(
    "postgresql"
    "redis-server"
)

BLOCKCHAIN_SERVICES=(
    "aitbc-blockchain-p2p"
    "aitbc-blockchain-node"
    "aitbc-blockchain-rpc"
    "aitbc-blockchain-sync"
    "aitbc-blockchain-event-bridge"
)

API_SERVICES=(
    "aitbc-coordinator-api"
    "aitbc-exchange-api"
    "aitbc-agent-coordinator"
)

APPLICATION_SERVICES=(
    "aitbc-wallet"
    "aitbc-agent-daemon"
    "aitbc-agent-registry"
    "aitbc-marketplace"
    "aitbc-governance"
    "aitbc-trading"
    "aitbc-monitor"
)

ALL_SERVICES=(
    "${CORE_SERVICES[@]}"
    "${BLOCKCHAIN_SERVICES[@]}"
    "${API_SERVICES[@]}"
    "${APPLICATION_SERVICES[@]}"
)

# Logging functions
log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if service exists
service_exists() {
    local service="$1"
    systemctl list-unit-files | grep -q "^${service}.service"
}

# Check service health
check_service_health() {
    local service="$1"
    
    if ! service_exists "$service"; then
        return 2
    fi
    
    if systemctl is-active --quiet "$service"; then
        return 0
    else
        return 1
    fi
}

# Wait for service to be ready
wait_for_service() {
    local service="$1"
    local timeout="${2:-30}"
    local elapsed=0
    
    log "Waiting for $service to be ready..."
    
    while [[ $elapsed -lt $timeout ]]; do
        if systemctl is-active --quiet "$service"; then
            success "$service is running"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    error "$service failed to start within ${timeout}s"
}

# Health check for API endpoints
check_api_endpoint() {
    local url="$1"
    local service_name="$2"
    
    if command -v curl &> /dev/null; then
        if curl -sf "$url" > /dev/null 2>&1; then
            success "$service_name API endpoint is healthy"
            return 0
        else
            warning "$service_name API endpoint health check failed"
            return 1
        fi
    else
        warning "curl not available, skipping API endpoint check"
        return 0
    fi
}

# Start services with dependency ordering
start_services() {
    local service_pattern="${1:-all}"
    
    log "Starting AITBC services..."
    
    if [[ "$service_pattern" == "all" ]]; then
        # Start core services first
        log "Starting core services..."
        for service in "${CORE_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Starting $service..."
                systemctl start "$service" 2>/dev/null || warning "Failed to start $service"
            fi
        done
        sleep 2
        
        # Start blockchain services
        log "Starting blockchain services..."
        for service in "${BLOCKCHAIN_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Starting $service..."
                systemctl start "$service" 2>/dev/null || warning "Failed to start $service"
                sleep 1
            fi
        done
        sleep 3
        
        # Start API services
        log "Starting API services..."
        for service in "${API_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Starting $service..."
                systemctl start "$service" 2>/dev/null || warning "Failed to start $service"
                sleep 1
            fi
        done
        sleep 2
        
        # Start application services
        log "Starting application services..."
        for service in "${APPLICATION_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Starting $service..."
                systemctl start "$service" 2>/dev/null || warning "Failed to start $service"
                sleep 1
            fi
        done
    else
        # Start specific service pattern
        log "Starting services matching: $service_pattern"
        systemctl start "$service_pattern" 2>/dev/null || error "Failed to start $service_pattern"
    fi
    
    success "Services started"
}

# Stop services in reverse dependency order
stop_services() {
    local service_pattern="${1:-all}"
    
    log "Stopping AITBC services..."
    
    if [[ "$service_pattern" == "all" ]]; then
        # Stop in reverse order
        log "Stopping application services..."
        for service in "${APPLICATION_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Stopping $service..."
                systemctl stop "$service" 2>/dev/null || warning "Failed to stop $service"
            fi
        done
        
        log "Stopping API services..."
        for service in "${API_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Stopping $service..."
                systemctl stop "$service" 2>/dev/null || warning "Failed to stop $service"
            fi
        done
        
        log "Stopping blockchain services..."
        for service in "${BLOCKCHAIN_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Stopping $service..."
                systemctl stop "$service" 2>/dev/null || warning "Failed to stop $service"
            fi
        done
        
        log "Stopping core services..."
        for service in "${CORE_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Stopping $service..."
                systemctl stop "$service" 2>/dev/null || warning "Failed to stop $service"
            fi
        done
    else
        # Stop specific service pattern
        log "Stopping services matching: $service_pattern"
        systemctl stop "$service_pattern" 2>/dev/null || error "Failed to stop $service_pattern"
    fi
    
    success "Services stopped"
}

# Restart services
restart_services() {
    local service_pattern="${1:-all}"
    
    log "Restarting AITBC services..."
    
    if [[ "$service_pattern" == "all" ]]; then
        stop_services "all"
        sleep 2
        start_services "all"
    else
        log "Restarting services matching: $service_pattern"
        systemctl restart "$service_pattern" 2>/dev/null || error "Failed to restart $service_pattern"
    fi
    
    success "Services restarted"
}

# Show service status
show_status() {
    local service_pattern="${1:-aitbc-*}"
    
    log "AITBC Service Status"
    echo "===================="
    echo ""
    
    if [[ "$service_pattern" == "all" ]]; then
        # Show all AITBC services
        for category in "Core Services" "Blockchain Services" "API Services" "Application Services"; do
            echo -e "${BLUE}$category${NC}"
            echo "----------------------------------------"
            
            case "$category" in
                "Core Services")
                    services=("${CORE_SERVICES[@]}")
                    ;;
                "Blockchain Services")
                    services=("${BLOCKCHAIN_SERVICES[@]}")
                    ;;
                "API Services")
                    services=("${API_SERVICES[@]}")
                    ;;
                "Application Services")
                    services=("${APPLICATION_SERVICES[@]}")
                    ;;
            esac
            
            for service in "${services[@]}"; do
                if service_exists "$service"; then
                    if systemctl is-active --quiet "$service"; then
                        echo -e "  ${GREEN}●${NC} $service - running"
                    elif systemctl is-failed --quiet "$service"; then
                        echo -e "  ${RED}●${NC} $service - failed"
                    else
                        echo -e "  ${YELLOW}●${NC} $service - inactive"
                    fi
                else
                    echo -e "  ${YELLOW}○${NC} $service - not installed"
                fi
            done
            echo ""
        done
    else
        # Show specific service
        systemctl status "$service_pattern"
    fi
}

# Show service logs
show_logs() {
    local service="$1"
    local lines="${2:-100}"
    
    if [[ -z "$service" ]]; then
        error "Usage: $0 logs <service> [lines]"
    fi
    
    if ! service_exists "$service"; then
        error "Service $service not found"
    fi
    
    log "Showing logs for $service (last $lines lines)..."
    journalctl -u "$service" -n "$lines" -f
}

# Enable services
enable_services() {
    local service_pattern="${1:-all}"
    
    log "Enabling AITBC services..."
    
    if [[ "$service_pattern" == "all" ]]; then
        for service in "${ALL_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Enabling $service..."
                systemctl enable "$service" 2>/dev/null || warning "Failed to enable $service"
            fi
        done
    else
        systemctl enable "$service_pattern" 2>/dev/null || error "Failed to enable $service_pattern"
    fi
    
    success "Services enabled"
}

# Disable services
disable_services() {
    local service_pattern="${1:-all}"
    
    log "Disabling AITBC services..."
    
    if [[ "$service_pattern" == "all" ]]; then
        for service in "${ALL_SERVICES[@]}"; do
            if service_exists "$service"; then
                log "Disabling $service..."
                systemctl disable "$service" 2>/dev/null || warning "Failed to disable $service"
            fi
        done
    else
        systemctl disable "$service_pattern" 2>/dev/null || error "Failed to disable $service_pattern"
    fi
    
    success "Services disabled"
}

# Run health checks
run_health_checks() {
    log "Running AITBC service health checks..."
    echo ""
    
    FAILED=0
    
    # Check core services
    log "Checking core services..."
    for service in "${CORE_SERVICES[@]}"; do
        if service_exists "$service"; then
            if check_service_health "$service"; then
                success "$service is healthy"
            else
                error "$service is not healthy"
                FAILED=$((FAILED + 1))
            fi
        fi
    done
    
    # Check blockchain services
    log "Checking blockchain services..."
    for service in "${BLOCKCHAIN_SERVICES[@]}"; do
        if service_exists "$service"; then
            if check_service_health "$service"; then
                success "$service is healthy"
            else
                error "$service is not healthy"
                FAILED=$((FAILED + 1))
            fi
        fi
    done
    
    # Check API services
    log "Checking API services..."
    for service in "${API_SERVICES[@]}"; do
        if service_exists "$service"; then
            if check_service_health "$service"; then
                success "$service is healthy"
            else
                error "$service is not healthy"
                FAILED=$((FAILED + 1))
            fi
        fi
    done
    
    # Check API endpoints
    log "Checking API endpoints..."
    check_api_endpoint "http://localhost:8006/health" "Blockchain RPC" || FAILED=$((FAILED + 1))
    check_api_endpoint "http://localhost:8011/health" "Coordinator API" || FAILED=$((FAILED + 1))
    check_api_endpoint "http://localhost:8001/health" "Exchange API" || FAILED=$((FAILED + 1))
    check_api_endpoint "http://localhost:9001/health" "Agent Coordinator" || FAILED=$((FAILED + 1))
    
    echo ""
    if [[ $FAILED -eq 0 ]]; then
        success "All health checks passed"
        return 0
    else
        error "$FAILED health check(s) failed"
        return 1
    fi
}

# Show help
show_help() {
    echo "AITBC Service Management Script"
    echo "================================"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start [service]     Start services (default: all)"
    echo "  stop [service]      Stop services (default: all)"
    echo "  restart [service]  Restart services (default: all)"
    echo "  status [service]    Show service status (default: all)"
    echo "  logs <service> [n]  Show service logs (default: 100 lines)"
    echo "  enable [service]    Enable services (default: all)"
    echo "  disable [service]   Disable services (default: all)"
    echo "  health-check        Run health checks on all services"
    echo "  help                Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start all services"
    echo "  $0 start aitbc-blockchain-node  # Start specific service"
    echo "  $0 status                   # Show status of all services"
    echo "  $0 logs aitbc-blockchain-node 50  # Show last 50 lines"
    echo "  $0 health-check             # Run health checks"
    echo ""
    echo "Service Groups:"
    echo "  Core: postgresql, redis-server"
    echo "  Blockchain: blockchain-p2p, blockchain-node, blockchain-rpc, blockchain-sync"
    echo "  API: coordinator-api, exchange-api, agent-coordinator"
    echo "  Application: wallet, agent-daemon, marketplace, governance, trading"
    echo ""
}

# Main command handling
main() {
    local COMMAND="${1:-help}"
    shift || true
    
    case "$COMMAND" in
        "start")
            start_services "$@"
            ;;
        "stop")
            stop_services "$@"
            ;;
        "restart")
            restart_services "$@"
            ;;
        "status")
            show_status "$@"
            ;;
        "logs")
            show_logs "$@"
            ;;
        "enable")
            enable_services "$@"
            ;;
        "disable")
            disable_services "$@"
            ;;
        "health-check")
            run_health_checks
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Run main function
main "$@"
