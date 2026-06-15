#!/bin/bash

# AITBC Service Health Check Script
# Comprehensive health monitoring for AITBC services
# Checks service health endpoints, resource usage, and logs results

set -e

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
LOG_DIR="/var/log/aitbc"
HEALTH_CHECK_LOG="$LOG_DIR/health_check.log"
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEM=80
ALERT_THRESHOLD_DISK=90

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service health endpoints
declare -A SERVICE_ENDPOINTS=(
    ["aitbc-blockchain-rpc"]="http://localhost:8006/health"
    ["aitbc-coordinator-api"]="http://localhost:8203/health"
    ["aitbc-exchange-api"]="http://localhost:8001/health"
    ["aitbc-agent-coordinator"]="http://localhost:9001/health"
    ["aitbc-marketplace"]="http://localhost:8102/health"
    ["aitbc-wallet"]="http://localhost:8000/health"
)

# Logging functions
log() {
    local msg="[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${BLUE}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

error() {
    local msg="[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo -e "${RED}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

success() {
    local msg="[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS: $1"
    echo -e "${GREEN}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

warning() {
    local msg="[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1"
    echo -e "${YELLOW}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

# Initialize log directory
init_logging() {
    mkdir -p "$LOG_DIR"
    touch "$HEALTH_CHECK_LOG"
}

# Check systemd service status
check_service_status() {
    local service="$1"

    if systemctl is-active --quiet "$service"; then
        success "$service is running"
        return 0
    elif systemctl is-failed --quiet "$service"; then
        error "$service has failed"
        return 1
    else
        warning "$service is inactive"
        return 2
    fi
}

# Check API endpoint health
check_endpoint_health() {
    local service="$1"
    local url="$2"

    if ! command -v curl &> /dev/null; then
        warning "curl not available, skipping endpoint check for $service"
        return 0
    fi

    if curl -sf "$url" > /dev/null 2>&1; then
        success "$service endpoint is healthy ($url)"
        return 0
    else
        error "$service endpoint is unhealthy ($url)"
        return 1
    fi
}

# Check service resource usage
check_resource_usage() {
    local service="$1"

    # Get PID of service
    local pid=$(systemctl show -p MainPID --value "$service" 2>/dev/null || echo "")

    if [[ -z "$pid" ]] || [[ "$pid" == "0" ]]; then
        warning "Cannot get PID for $service"
        return 0
    fi

    # Check CPU usage
    if [[ -f "/proc/$pid/stat" ]]; then
        local cpu_usage=$(ps -p "$pid" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0")
        local cpu_int=${cpu_usage%.*}
        if [[ $cpu_int -gt $ALERT_THRESHOLD_CPU ]]; then
            error "$service CPU usage high: ${cpu_usage}%"
        else
            log "$service CPU usage: ${cpu_usage}%"
        fi
    fi

    # Check memory usage
    local mem_usage=$(ps -p "$pid" -o %mem --no-headers 2>/dev/null | tr -d ' ' || echo "0")
    local mem_int=${mem_usage%.*}
    if [[ $mem_int -gt $ALERT_THRESHOLD_MEM ]]; then
        error "$service memory usage high: ${mem_usage}%"
    else
        log "$service memory usage: ${mem_usage}%"
    fi
}

# Check disk usage
check_disk_usage() {
    local path="${1:-/var/lib/aitbc}"

    if [[ ! -d "$path" ]]; then
        warning "Path $path does not exist"
        return 0
    fi

    local disk_usage=$(df "$path" | awk 'NR==2 {print $5}' | tr -d '%')
    local disk_int=${disk_usage%.*}

    if [[ $disk_int -gt $ALERT_THRESHOLD_DISK ]]; then
        error "Disk usage high for $path: ${disk_usage}%"
    else
        log "Disk usage for $path: ${disk_usage}%"
    fi
}

# Check system memory
check_system_memory() {
    local mem_info=$(free | grep Mem)
    local total=$(echo $mem_info | awk '{print $2}')
    local used=$(echo $mem_info | awk '{print $3}')
    local percent=$((used * 100 / total))

    if [[ $percent -gt $ALERT_THRESHOLD_MEM ]]; then
        error "System memory usage high: ${percent}%"
    else
        log "System memory usage: ${percent}%"
    fi
}

# Check blockchain sync status
check_blockchain_sync() {
    local rpc_url="http://localhost:8006"

    if ! command -v curl &> /dev/null || ! command -v jq &> /dev/null; then
        warning "curl or jq not available, skipping blockchain sync check"
        return 0
    fi

    local block_height=$(curl -s "$rpc_url/rpc/head" | jq -r '.height' 2>/dev/null || echo "0")

    if [[ "$block_height" != "0" ]] && [[ "$block_height" != "null" ]]; then
        success "Blockchain current height: $block_height"
        return 0
    else
        warning "Could not retrieve blockchain height"
        return 1
    fi
}

# Check database connectivity
check_database() {
    if command -v psql &> /dev/null; then
        if pg_isready -h localhost -p 5432 &> /dev/null; then
            success "PostgreSQL is reachable"
            return 0
        else
            error "PostgreSQL is not reachable"
            return 1
        fi
    else
        warning "psql not available, skipping database check"
        return 0
    fi
}

# Check Redis connectivity
check_redis() {
    if command -v redis-cli &> /dev/null; then
        if redis-cli -h localhost ping 2>/dev/null | grep -q PONG; then
            success "Redis is reachable"
            return 0
        else
            error "Redis is not reachable"
            return 1
        fi
    else
        warning "redis-cli not available, skipping Redis check"
        return 0
    fi
}

# Check network connectivity
check_network() {
    local target_host="${1:-8.8.8.8}"

    if ping -c 1 -W 2 "$target_host" &> /dev/null; then
        success "Network connectivity OK (ping to $target_host)"
        return 0
    else
        error "Network connectivity failed (ping to $target_host)"
        return 1
    fi
}

# Main health check function
main() {
    local check_type="${1:-all}"

    init_logging

    log "=== Starting AITBC Health Check ==="
    log "Check type: $check_type"
    echo ""

    TOTAL_ERRORS=0
    TOTAL_WARNINGS=0

    case "$check_type" in
        "services")
            log "Checking systemd services..."
            echo ""

            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_service_status "$service" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                check_resource_usage "$service"
            done
            ;;
        "endpoints")
            log "Checking API endpoints..."
            echo ""

            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_endpoint_health "$service" "${SERVICE_ENDPOINTS[$service]}" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            done
            ;;
        "resources")
            log "Checking resource usage..."
            echo ""

            check_disk_usage "/var/lib/aitbc"
            check_system_memory
            ;;
        "blockchain")
            log "Checking blockchain status..."
            echo ""

            check_blockchain_sync || TOTAL_WARNINGS=$((TOTAL_WARNINGS + 1))
            ;;
        "infrastructure")
            log "Checking infrastructure..."
            echo ""

            check_database || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            check_redis || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            check_network || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            ;;
        "all")
            log "Running comprehensive health check..."
            echo ""

            # Check services
            log "--- Service Status ---"
            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_service_status "$service" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                check_resource_usage "$service"
            done
            echo ""

            # Check endpoints
            log "--- API Endpoints ---"
            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_endpoint_health "$service" "${SERVICE_ENDPOINTS[$service]}" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            done
            echo ""

            # Check resources
            log "--- Resource Usage ---"
            check_disk_usage "/var/lib/aitbc"
            check_system_memory
            echo ""

            # Check blockchain
            log "--- Blockchain Status ---"
            check_blockchain_sync || TOTAL_WARNINGS=$((TOTAL_WARNINGS + 1))
            echo ""

            # Check infrastructure
            log "--- Infrastructure ---"
            check_database || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            check_redis || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            check_network || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            ;;
        *)
            echo "Usage: $0 {all|services|endpoints|resources|blockchain|infrastructure}"
            echo ""
            echo "Check types:"
            echo "  all            - Run all health checks"
            echo "  services       - Check systemd service status"
            echo "  endpoints      - Check API endpoint health"
            echo "  resources      - Check resource usage (CPU, memory, disk)"
            echo "  blockchain     - Check blockchain sync status"
            echo "  infrastructure  - Check database, Redis, network"
            exit 1
            ;;
    esac

    echo ""
    log "=== Health Check Complete ==="

    if [[ $TOTAL_ERRORS -eq 0 ]] && [[ $TOTAL_WARNINGS -eq 0 ]]; then
        success "All health checks passed"
        exit 0
    elif [[ $TOTAL_ERRORS -eq 0 ]]; then
        warning "Health checks passed with $TOTAL_WARNINGS warning(s)"
        exit 0
    else
        error "Health checks failed with $TOTAL_ERRORS error(s) and $TOTAL_WARNINGS warning(s)"
        exit 1
    fi
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Run main function
main "$@"
