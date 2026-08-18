#!/bin/bash

# AITBC Service Health Check Script
# Comprehensive health monitoring for AITBC services
# Checks service health endpoints, resource usage, and logs results

set -euo pipefail

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
# Overridable so a test run does not append to the production health log, matching the
# REPO_ROOT convention directly above (V23-98).
LOG_DIR="${LOG_DIR:-/var/log/aitbc}"
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

# Known HTTP health endpoints. This is the catalogue, not the probe list.
# The probe list is built from the node's role so a shop or follower is not
# blamed for hub-only units it is correct not to run (V23-92).
declare -A ALL_SERVICE_ENDPOINTS=(
    ["aitbc-blockchain-rpc"]="http://localhost:8202/health"
    ["aitbc-wallet"]="http://localhost:8108/health"
    ["aitbc-trading"]="http://localhost:8104/health"
    ["aitbc-governance"]="http://localhost:8105/health"
    ["aitbc-coordinator-api"]="http://localhost:8203/health"
    ["aitbc-api-gateway"]="http://localhost:8201/health"
    ["aitbc-exchange"]="http://localhost:8106/health"
    ["aitbc-marketplace"]="http://localhost:8102/health"
    ["aitbc-agent-coordinator"]="http://localhost:8107/health"
    ["aitbc-blockchain-explorer"]="http://localhost:8100/health"
    ["aitbc-blockchain-event-bridge"]="http://localhost:8205/health"
    ["aitbc-gpu"]="http://localhost:8101/health"
    ["aitbc-edge"]="http://localhost:8111/health"
    ["aitbc-pool-hub"]="http://localhost:8210/health"
    # Absent until V23-98. Pool Hub was not the exception -- all six of these were
    # listening and answering /health 200 while this map watched five services and two
    # that are not installed on this host at all.
    ["aitbc-monitoring"]="http://localhost:8002/health"
)

# Role lists match scripts/deployment/setup.sh get_services_for_role().
# Units without an HTTP health port (node, p2p, miner, recovery, backup,
# bridge-monitor, sync) stay off the endpoint map and are still covered by
# the systemd status check when they appear in ROLE_SERVICES.
_BASE_SERVICES=(
    aitbc-blockchain-node
    aitbc-blockchain-rpc
    aitbc-wallet
    aitbc-recovery
    aitbc-monitoring
    aitbc-backup.timer
    aitbc-trading
    aitbc-governance
)
_HUB_SERVICES=(
    aitbc-blockchain-p2p
    aitbc-coordinator-api
    aitbc-api-gateway
    aitbc-exchange
    aitbc-marketplace
    aitbc-bridge-monitor
    aitbc-blockchain-event-bridge
    aitbc-agent-coordinator
    aitbc-blockchain-explorer
)
_FOLLOWER_SERVICES=(
    aitbc-blockchain-sync
    aitbc-blockchain-sync.timer
    aitbc-blockchain-explorer
)
_SHOP_SERVICES=(
    aitbc-gpu
    aitbc-miner
    aitbc-coordinator-api
    aitbc-edge
    aitbc-pool-hub
    aitbc-marketplace
)

_node_role() {
    # Capture the caller's env first. Sourcing the files would otherwise
    # overwrite a pinned BLOCKCHAIN_MODE/MARKET_ROLE (used by the suite and
    # by operators testing a role on a box that is already configured).
    local pinned_mode="${BLOCKCHAIN_MODE:-}" pinned_market="${MARKET_ROLE:-}" pinned_hw="${HARDWARE_PROFILE:-}"
    local blockchain_mode="" market_role="" hardware_profile=""
    if [ -f "/etc/aitbc/blockchain.env" ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/blockchain.env 2>/dev/null || true
        blockchain_mode="${BLOCKCHAIN_MODE:-}"
        market_role="${MARKET_ROLE:-}"
        hardware_profile="${HARDWARE_PROFILE:-}"
    fi
    if [ -f "/etc/aitbc/node.env" ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/node.env 2>/dev/null || true
        blockchain_mode="${BLOCKCHAIN_MODE:-${blockchain_mode}}"
        market_role="${MARKET_ROLE:-${market_role}}"
        hardware_profile="${HARDWARE_PROFILE:-${hardware_profile}}"
    fi
    blockchain_mode="${pinned_mode:-${blockchain_mode}}"
    market_role="${pinned_market:-${market_role}}"
    hardware_profile="${pinned_hw:-${hardware_profile}}"
    if [ "${blockchain_mode}" = "hub" ]; then
        echo "hub"
    elif [ "${market_role}" = "shop" ] && [ "${hardware_profile}" = "gpu" ]; then
        echo "shop"
    elif [ "${market_role}" = "customer" ]; then
        echo "customer"
    else
        echo "follower"
    fi
}

_services_for_role() {
    local role="${1:-follower}"
    local services=("${_BASE_SERVICES[@]}")
    case "$role" in
        hub) services+=("${_HUB_SERVICES[@]}") ;;
        follower) services+=("${_FOLLOWER_SERVICES[@]}") ;;
        shop)
            services+=("${_SHOP_SERVICES[@]}")
            services+=("${_FOLLOWER_SERVICES[@]}")
            ;;
        customer) ;;
        *) services+=("${_FOLLOWER_SERVICES[@]}") ;;
    esac
    printf '%s\n' "${services[@]}"
}

declare -A SERVICE_ENDPOINTS=()
ROLE="$(_node_role)"
ROLE_SERVICES=()
while IFS= read -r svc; do
    [ -n "$svc" ] || continue
    ROLE_SERVICES+=("$svc")
    if [ -n "${ALL_SERVICE_ENDPOINTS[$svc]+x}" ]; then
        SERVICE_ENDPOINTS["$svc"]="${ALL_SERVICE_ENDPOINTS[$svc]}"
    fi
done < <(_services_for_role "$ROLE")

# Logging functions
log() {
    local msg
    msg="[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${BLUE}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

error() {
    local msg
    msg="[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo -e "${RED}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

success() {
    local msg
    msg="[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS: $1"
    echo -e "${GREEN}$msg${NC}"
    echo "$msg" >> "$HEALTH_CHECK_LOG" 2>/dev/null || true
}

warning() {
    local msg
    msg="[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1"
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

# Is this unit installed on this host at all?
#
# SERVICE_ENDPOINTS is one map shared across every kind of node, and this one is a
# follower/shop node: aitbc-exchange and aitbc-agent-coordinator have never been
# installed here. Counting an absent unit as a failure made the script exit 1 on every
# run regardless of what was actually wrong, which is a plausible reason nobody ever
# scheduled it. Absent is not down.
service_is_installed() {
    [[ "$(systemctl is-enabled "$1" 2>/dev/null || true)" != "not-found" ]]
}

# Systemd check for one service, skipping units this host does not have.
#
# It also keeps "inactive" a warning. check_service_status draws a three-way distinction --
# running, failed, inactive -- and returns 0, 1, 2 for them. Every call site was
# `check_service_status "$s" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))`, and `||` fires on any
# non-zero, so that collapsed back to two and the warning path was unreachable. This makes
# the counters agree with what the function already says.
#
# Returns non-zero only when the service was skipped, so callers can skip the follow-on
# resource check too.
check_installed_service() {
    local service="$1"

    if ! service_is_installed "$service"; then
        log "$service is not installed on this host, skipping"
        TOTAL_SKIPPED=$((TOTAL_SKIPPED + 1))
        return 1
    fi

    local rc=0
    check_service_status "$service" || rc=$?
    case $rc in
        0) ;;
        2) TOTAL_WARNINGS=$((TOTAL_WARNINGS + 1)) ;;
        *) TOTAL_ERRORS=$((TOTAL_ERRORS + 1)) ;;
    esac
    return 0
}

# Endpoint counterpart: an absent unit is skipped, not reported unreachable.
check_installed_endpoint() {
    local service="$1"

    if ! service_is_installed "$service"; then
        log "$service is not installed on this host, skipping"
        TOTAL_SKIPPED=$((TOTAL_SKIPPED + 1))
        return 0
    fi

    check_endpoint_health "$service" "${SERVICE_ENDPOINTS[$service]}" || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
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
    local pid
    pid=$(systemctl show -p MainPID --value "$service" 2>/dev/null || echo "")

    if [[ -z "$pid" ]] || [[ "$pid" == "0" ]]; then
        warning "Cannot get PID for $service"
        return 0
    fi

    # Check CPU usage
    if [[ -f "/proc/$pid/stat" ]]; then
        local cpu_usage
        cpu_usage=$(ps -p "$pid" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0")
        local cpu_int=${cpu_usage%.*}
        if [[ $cpu_int -gt $ALERT_THRESHOLD_CPU ]]; then
            error "$service CPU usage high: ${cpu_usage}%"
        else
            log "$service CPU usage: ${cpu_usage}%"
        fi
    fi

    # Check memory usage
    local mem_usage
    mem_usage=$(ps -p "$pid" -o %mem --no-headers 2>/dev/null | tr -d ' ' || echo "0")
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

    local disk_usage
    disk_usage=$(df "$path" | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")
    local disk_int=${disk_usage%.*}

    if [[ $disk_int -gt $ALERT_THRESHOLD_DISK ]]; then
        error "Disk usage high for $path: ${disk_usage}%"
    else
        log "Disk usage for $path: ${disk_usage}%"
    fi
}

# Check system memory
check_system_memory() {
    local mem_info
    mem_info=$(free | awk '/^(Mem|Speicher):/ {print $2, $3}' || true)
    local total
    total=$(echo "$mem_info" | awk '{print $1}')
    local used
    used=$(echo "$mem_info" | awk '{print $2}')
    if [[ -z "$total" || -z "$used" || "$total" -eq 0 ]]; then
        warning "Could not determine system memory usage"
        return 0
    fi
    local percent=$((used * 100 / total))

    if [[ $percent -gt $ALERT_THRESHOLD_MEM ]]; then
        error "System memory usage high: ${percent}%"
    else
        log "System memory usage: ${percent}%"
    fi
}

# Check blockchain sync status
check_blockchain_sync() {
    local rpc_url="http://localhost:8202"

    if ! command -v curl &> /dev/null || ! command -v jq &> /dev/null; then
        warning "curl or jq not available, skipping blockchain sync check"
        return 0
    fi

    local block_height
    block_height=$(curl -s "$rpc_url/rpc/head" | jq -r '.height' 2>/dev/null || echo "0")

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
    local target_host="8.8.8.8"

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
    log "Node role: $ROLE (${#ROLE_SERVICES[@]} units, ${#SERVICE_ENDPOINTS[@]} HTTP endpoints)"
    echo ""

    TOTAL_ERRORS=0
    TOTAL_WARNINGS=0
    TOTAL_SKIPPED=0

    case "$check_type" in
        "services")
            log "Checking systemd services..."
            echo ""

            for service in "${ROLE_SERVICES[@]}"; do
                check_installed_service "$service" || continue
                check_resource_usage "$service"
            done
            ;;
        "endpoints")
            log "Checking API endpoints..."
            echo ""

            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_installed_endpoint "$service"
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
            for service in "${ROLE_SERVICES[@]}"; do
                check_installed_service "$service" || continue
                check_resource_usage "$service"
            done
            echo ""

            # Check endpoints
            log "--- API Endpoints ---"
            for service in "${!SERVICE_ENDPOINTS[@]}"; do
                check_installed_endpoint "$service"
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

    if [[ $TOTAL_SKIPPED -gt 0 ]]; then
        log "$TOTAL_SKIPPED check(s) skipped: unit not installed on this host"
    fi

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
trap 'error "Script interrupted"; exit 130' INT TERM

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
