#!/bin/bash
# AITBC Cache Monitoring Script
# Monitors Redis cache performance and statistics

# Configuration
LOG_FILE="/var/log/aitbc/cache-monitor.log"
ALERT_THRESHOLD=90  # Memory usage alert threshold

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to log messages
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Function to check Redis connection
check_redis_connection() {
    echo "=== Redis Connection Status ==="

    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}OK: Redis is connected${NC}"
        log_message "INFO" "Redis is connected"
        return 0
    else
        echo -e "${RED}ALERT: Redis is not connected${NC}"
        log_message "ALERT" "Redis is not connected"
        return 1
    fi
}

# Function to check Redis memory usage
check_redis_memory() {
    echo ""
    echo "=== Redis Memory Status ==="

    local memory_used=$(redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    local memory_peak=$(redis-cli info memory | grep used_memory_peak_human | cut -d: -f2 | tr -d '\r')
    local max_memory=$(redis-cli config get maxmemory | tail -1)

    echo "Current Memory: $memory_used"
    echo "Peak Memory: $memory_peak"
    echo "Max Memory: $max_memory"

    if [ "$max_memory" != "0" ]; then
        # Calculate percentage (simplified)
        echo "Memory limit is configured"
    else
        echo -e "${YELLOW}WARNING: No memory limit configured${NC}"
        log_message "WARNING" "No Redis memory limit configured"
    fi
}

# Function to check cache statistics
check_cache_stats() {
    echo ""
    echo "=== Cache Statistics ==="

    local keyspace_hits=$(redis-cli info stats | grep keyspace_hits | cut -d: -f2 | tr -d '\r')
    local keyspace_misses=$(redis-cli info stats | grep keyspace_misses | cut -d: -f2 | tr -d '\r')
    local total_keys=$(redis-cli info keyspace | grep db0 | cut -d: -f2 | tr -d '\r')

    echo "Keyspace Hits: $keyspace_hits"
    echo "Keyspace Misses: $keyspace_misses"
    echo "Total Keys: $total_keys"

    if [ "$keyspace_hits" != "0" ] || [ "$keyspace_misses" != "0" ]; then
        local total=$((keyspace_hits + keyspace_misses))
        local hit_rate=$((keyspace_hits * 100 / total))
        echo "Hit Rate: ${hit_rate}%"

        if [ $hit_rate -lt 50 ]; then
            echo -e "${YELLOW}WARNING: Low cache hit rate (${hit_rate}%)${NC}"
            log_message "WARNING" "Low cache hit rate (${hit_rate}%)"
        else
            echo -e "${GREEN}OK: Cache hit rate is ${hit_rate}%${NC}"
            log_message "INFO" "Cache hit rate is ${hit_rate}%"
        fi
    else
        echo "No cache activity yet"
    fi
}

# Function to check AITBC cache keys
check_aitbc_keys() {
    echo ""
    echo "=== AITBC Cache Keys ==="

    local aitbc_keys=$(redis-cli keys "aitbc:*" | wc -l)
    echo "Total AITBC keys: $aitbc_keys"

    if [ $aitbc_keys -gt 0 ]; then
        echo "Key types:"
        redis-cli keys "aitbc:*" | head -10 | while read key; do
            local ttl=$(redis-cli ttl "$key")
            echo "  $key (TTL: ${ttl}s)"
        done
    fi
}

# Main execution
main() {
    echo "AITBC Cache Monitoring Report"
    echo "=============================="
    echo ""

    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"

    # Run checks
    local connection_status=0

    check_redis_connection || connection_status=1

    if [ $connection_status -eq 0 ]; then
        check_redis_memory
        check_cache_stats
        check_aitbc_keys

        echo ""
        echo "=== Summary ==="
        echo -e "${GREEN}Cache monitoring completed successfully${NC}"
        log_message "INFO" "Cache monitoring completed successfully"
        exit 0
    else
        echo ""
        echo "=== Summary ==="
        echo -e "${RED}Redis connection failed - check log file: $LOG_FILE${NC}"
        log_message "ALERT" "Redis connection failed"
        exit 1
    fi
}

# Run main function
main "$@"
