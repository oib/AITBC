#!/bin/bash
# AITBC Memory Monitoring Script
# Monitors service memory usage and system memory status

# Configuration
ALERT_THRESHOLD=90  # System memory usage alert threshold
LOG_FILE="/var/log/aitbc/memory-monitor.log"
ALERT_EMAIL="admin@aitbc.bubuit.net"  # Optional: configure email alerts

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

# Function to check system memory
check_system_memory() {
    local total_mem=$(free -m | awk '/^Mem:/{print $2}')
    local used_mem=$(free -m | awk '/^Mem:/{print $3}')

    if [ -z "$total_mem" ] || [ "$total_mem" -eq 0 ]; then
        echo "SKIPPED: Unable to get system memory information (permission issue)"
        log_message "WARNING" "Unable to get system memory information (permission issue)"
        return 0  # Don't fail on permission issues
    fi

    local mem_percent=$((used_mem * 100 / total_mem))

    echo "=== System Memory Status ==="
    echo "Total: ${total_mem}MB"
    echo "Used: ${used_mem}MB (${mem_percent}%)"
    echo "Available: $((total_mem - used_mem))MB"

    if [ $mem_percent -gt $ALERT_THRESHOLD ]; then
        echo -e "${RED}ALERT: System memory usage is ${mem_percent}% (threshold: ${ALERT_THRESHOLD}%)${NC}"
        log_message "ALERT" "System memory usage is ${mem_percent}% (threshold: ${ALERT_THRESHOLD}%)"
        return 1
    else
        echo -e "${GREEN}OK: System memory usage is ${mem_percent}%${NC}"
        log_message "INFO" "System memory usage is ${mem_percent}%"
        return 0
    fi
}

# Function to check service memory
check_service_memory() {
    echo ""
    echo "=== Service Memory Status ==="

    local services=$(systemctl list-units --type=service --state=running | grep aitbc | awk '{print $1}')
    local alert_count=0

    for service in $services; do
        local memory_current=$(systemctl show "$service" -p MemoryCurrent --value)
        local memory_max=$(systemctl show "$service" -p MemoryMax --value)
        local memory_limit=$(systemctl show "$service" -p MemoryLimit --value)

        # Convert bytes to MB
        local memory_current_mb=$((memory_current / 1024 / 1024))
        local memory_max_mb=$((memory_max / 1024 / 1024))
        local memory_limit_mb=$((memory_limit / 1024 / 1024))

        # Calculate usage percentage
        local usage_percent=0
        if [ "$memory_max" != "18446744073709551615" ] && [ "$memory_max" != "infinity" ]; then
            usage_percent=$((memory_current * 100 / memory_max))
        fi

        # Check if service is near limit
        if [ "$memory_max" != "18446744073709551615" ] && [ "$memory_max" != "infinity" ]; then
            if [ $usage_percent -gt 80 ]; then
                echo -e "${RED}ALERT: $service - ${memory_current_mb}MB/${memory_max_mb}MB (${usage_percent}%)${NC}"
                log_message "ALERT" "$service memory usage is ${usage_percent}% (${memory_current_mb}MB/${memory_max_mb}MB)"
                alert_count=$((alert_count + 1))
            elif [ $usage_percent -gt 60 ]; then
                echo -e "${YELLOW}WARNING: $service - ${memory_current_mb}MB/${memory_max_mb}MB (${usage_percent}%)${NC}"
                log_message "WARNING" "$service memory usage is ${usage_percent}% (${memory_current_mb}MB/${memory_max_mb}MB)"
            else
                echo "OK: $service - ${memory_current_mb}MB/${memory_max_mb}MB (${usage_percent}%)"
            fi
        else
            echo "OK: $service - ${memory_current_mb}MB (no limit)"
        fi
    done

    if [ $alert_count -gt 0 ]; then
        return 1
    else
        return 0
    fi
}

# Function to check for OOM killer events
check_oom_events() {
    echo ""
    echo "=== OOM Killer Events ==="

    local oom_count=$(sudo dmesg 2>/dev/null | grep -i "out of memory" | wc -l)

    if [ $oom_count -gt 0 ]; then
        echo -e "${RED}ALERT: Found $oom_count OOM killer events in kernel log${NC}"
        log_message "ALERT" "Found $oom_count OOM killer events in kernel log"
        sudo dmesg 2>/dev/null | grep -i "out of memory" | tail -5
        return 1
    else
        echo -e "${GREEN}OK: No OOM killer events found${NC}"
        log_message "INFO" "No OOM killer events found"
        return 0
    fi
}

# Main execution
main() {
    echo "AITBC Memory Monitoring Report"
    echo "=============================="
    echo ""

    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"

    # Run checks
    local system_status=0
    local service_status=0
    local oom_status=0

    check_system_memory || system_status=1
    check_service_memory || service_status=1
    check_oom_events || oom_status=2

    echo ""
    echo "=== Summary ==="
    if [ $service_status -eq 0 ] && [ $oom_status -eq 0 ]; then
        echo -e "${GREEN}Service memory checks passed${NC}"
        log_message "INFO" "Service memory checks passed"
        if [ $system_status -eq 1 ]; then
            echo -e "${YELLOW}Note: System memory check failed (may be permission issue)${NC}"
        fi
        exit 0
    else
        echo -e "${RED}Memory alerts detected - check log file: $LOG_FILE${NC}"
        log_message "ALERT" "Memory alerts detected"
        exit 1
    fi
}

# Run main function
main "$@"
