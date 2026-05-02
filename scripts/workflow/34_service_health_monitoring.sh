#!/bin/bash

# AITBC Service Health Monitoring & Alerting
# Continuous monitoring of all blockchain services with alerting

set -e

echo "=== 🏥 AITBC SERVICE HEALTH MONITORING & ALERTING ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GENESIS_NODE="localhost"
FOLLOWER_NODE="aitbc"
GENESIS_PORT="8006"
FOLLOWER_PORT="8006"
COORDINATOR_PORT="8011"

# Monitoring configuration
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEM=90
ALERT_THRESHOLD_DISK=85
ALERT_THRESHOLD_RESPONSE_TIME=1000
MONITORING_INTERVAL=30
LOG_FILE="/var/log/aitbc/service_monitoring.log"
ALERT_LOG="/var/log/aitbc/service_alerts.log"

# Service status tracking
declare -A SERVICE_STATUS
declare -A LAST_CHECK_TIME

echo "🏥 SERVICE HEALTH MONITORING"
echo "Continuous monitoring of all blockchain services"
echo ""

# Function to log monitoring events
log_monitoring() {
    local level="$1"
    local service="$2"
    local message="$3"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] [$level] $service: $message" >> "$LOG_FILE"
    
    if [ "$level" = "ALERT" ]; then
        echo "[$timestamp] [ALERT] $service: $message" >> "$ALERT_LOG"
        echo -e "${RED}🚨 ALERT: $service - $message${NC}"
    fi
}

# Function to check service health
check_service_health() {
    local service_name="$1"
    local check_command="$2"
    local expected_result="$3"
    
    echo "Checking $service_name..."
    
    if eval "$check_command" >/dev/null 2>&1; then
        if [ -n "$expected_result" ]; then
            local result=$(eval "$check_command" 2>/dev/null)
            if echo "$result" | grep -q "$expected_result"; then
                SERVICE_STATUS["$service_name"]="healthy"
                log_monitoring "INFO" "$service_name" "Service is healthy"
                echo -e "${GREEN}✅ $service_name: Healthy${NC}"
            else
                SERVICE_STATUS["$service_name"]="unhealthy"
                log_monitoring "ALERT" "$service_name" "Service returned unexpected result: $result"
                echo -e "${RED}❌ $service_name: Unexpected result${NC}"
            fi
        else
            SERVICE_STATUS["$service_name"]="healthy"
            log_monitoring "INFO" "$service_name" "Service is healthy"
            echo -e "${GREEN}✅ $service_name: Healthy${NC}"
        fi
    else
        SERVICE_STATUS["$service_name"]="unhealthy"
        log_monitoring "ALERT" "$service_name" "Service is not responding"
        echo -e "${RED}❌ $service_name: Not responding${NC}"
    fi
    
    LAST_CHECK_TIME["$service_name"]=$(date +%s)
}

# Function to check service performance
check_service_performance() {
    local service_name="$1"
    local endpoint="$2"
    local max_response_time="$3"
    
    echo "Checking $service_name performance..."
    
    local start_time=$(date +%s%N)
    local result=$(curl -s "$endpoint" 2>/dev/null)
    local end_time=$(date +%s%N)
    local response_time=$(( (end_time - start_time) / 1000000 ))
    
    if [ "$response_time" -gt "$max_response_time" ]; then
        log_monitoring "ALERT" "$service_name" "High response time: ${response_time}ms (threshold: ${max_response_time}ms)"
        echo -e "${YELLOW}⚠️ $service_name: High response time (${response_time}ms)${NC}"
    else
        log_monitoring "INFO" "$service_name" "Response time: ${response_time}ms"
        echo -e "${GREEN}✅ $service_name: Response time OK (${response_time}ms)${NC}"
    fi
}

# Function to check system resources
check_system_resources() {
    echo "Checking system resources..."
    
    # CPU usage
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    if (( $(echo "$cpu_usage > $ALERT_THRESHOLD_CPU" | bc -l) )); then
        log_monitoring "ALERT" "System" "High CPU usage: ${cpu_usage}%"
        echo -e "${YELLOW}⚠️ System: High CPU usage (${cpu_usage}%)${NC}"
    else
        echo -e "${GREEN}✅ System: CPU usage OK (${cpu_usage}%)${NC}"
    fi
    
    # Memory usage
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    if (( $(echo "$mem_usage > $ALERT_THRESHOLD_MEM" | bc -l) )); then
        log_monitoring "ALERT" "System" "High memory usage: ${mem_usage}%"
        echo -e "${YELLOW}⚠️ System: High memory usage (${mem_usage}%)${NC}"
    else
        echo -e "${GREEN}✅ System: Memory usage OK (${mem_usage}%)${NC}"
    fi
    
    # Disk usage
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt "$ALERT_THRESHOLD_DISK" ]; then
        log_monitoring "ALERT" "System" "High disk usage: ${disk_usage}%"
        echo -e "${YELLOW}⚠️ System: High disk usage (${disk_usage}%)${NC}"
    else
        echo -e "${GREEN}✅ System: Disk usage OK (${disk_usage}%)${NC}"
    fi
}

# Function to check blockchain-specific metrics
check_blockchain_metrics() {
    echo "Checking blockchain metrics..."
    
    # Check block height
    local block_height=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height 2>/dev/null || echo "0")
    if [ "$block_height" -gt 0 ]; then
        log_monitoring "INFO" "Blockchain" "Current block height: $block_height"
        echo -e "${GREEN}✅ Blockchain: Block height $block_height${NC}"
    else
        log_monitoring "ALERT" "Blockchain" "Unable to get block height"
        echo -e "${RED}❌ Blockchain: Unable to get block height${NC}"
    fi
    
    # Check transaction count
    local tx_count=$(curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions 2>/dev/null || echo "0")
    log_monitoring "INFO" "Blockchain" "Total transactions: $tx_count"
    echo -e "${GREEN}✅ Blockchain: $tx_count transactions${NC}"
    
    # Check cross-node sync
    local local_height=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height 2>/dev/null || echo "0")
    local remote_height=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height' 2>/dev/null || echo "0")
    local sync_diff=$((local_height - remote_height))
    
    if [ "$sync_diff" -le 10 ]; then
        log_monitoring "INFO" "Blockchain" "Cross-node sync OK (diff: $sync_diff)"
        echo -e "${GREEN}✅ Blockchain: Cross-node sync OK (diff: $sync_diff)${NC}"
    else
        log_monitoring "ALERT" "Blockchain" "Large sync gap: $sync_diff blocks"
        echo -e "${YELLOW}⚠️ Blockchain: Large sync gap ($sync_diff blocks)${NC}"
    fi
}

# Function to check service-specific metrics
check_service_metrics() {
    echo "Checking service-specific metrics..."
    
    # AI Service metrics
    local ai_stats=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:8006/rpc/ai/stats' 2>/dev/null)
    if [ -n "$ai_stats" ]; then
        local ai_jobs=$(echo "$ai_stats" | jq .total_jobs 2>/dev/null || echo "0")
        local ai_revenue=$(echo "$ai_stats" | jq .total_revenue 2>/dev/null || echo "0")
        log_monitoring "INFO" "AI Service" "Jobs: $ai_jobs, Revenue: $ai_revenue AIT"
        echo -e "${GREEN}✅ AI Service: $ai_jobs jobs, $ai_revenue AIT revenue${NC}"
    else
        log_monitoring "ALERT" "AI Service" "Unable to get stats"
        echo -e "${RED}❌ AI Service: Unable to get stats${NC}"
    fi
    
    # Marketplace metrics
    local marketplace_listings=$(curl -s http://localhost:$GENESIS_PORT/rpc/marketplace/listings | jq '.listings | length' 2>/dev/null || echo "0")
    if [ "$marketplace_listings" -gt 0 ]; then
        log_monitoring "INFO" "Marketplace" "Active listings: $marketplace_listings"
        echo -e "${GREEN}✅ Marketplace: $marketplace_listings active listings${NC}"
    else
        log_monitoring "INFO" "Marketplace" "No active listings"
        echo -e "${YELLOW}⚠️ Marketplace: No active listings${NC}"
    fi
    
    # Coordinator API metrics
    local coordinator_health=$(curl -s http://localhost:$COORDINATOR_PORT/health/live 2>/dev/null)
    if [ -n "$coordinator_health" ]; then
        local coordinator_status=$(echo "$coordinator_health" | jq -r .status 2>/dev/null || echo "unknown")
        if [ "$coordinator_status" = "alive" ]; then
            log_monitoring "INFO" "Coordinator API" "Status: $coordinator_status"
            echo -e "${GREEN}✅ Coordinator API: Status $coordinator_status${NC}"
        else
            log_monitoring "ALERT" "Coordinator API" "Status: $coordinator_status"
            echo -e "${RED}❌ Coordinator API: Status $coordinator_status${NC}"
        fi
    else
        log_monitoring "ALERT" "Coordinator API" "Unable to get health status"
        echo -e "${RED}❌ Coordinator API: Unable to get health status${NC}"
    fi
}

# Function to check contract service health
check_contract_service_health() {
    echo "Checking contract service health..."
    
    # Check if contract endpoints are available
    local contracts_endpoint=$(curl -s http://localhost:$GENESIS_PORT/rpc/contracts 2>/dev/null)
    if [ -n "$contracts_endpoint" ] && [ "$contracts_endpoint" != '{"detail":"Not Found"}' ]; then
        local contract_count=$(echo "$contracts_endpoint" | jq '.total' 2>/dev/null || echo "0")
        log_monitoring "INFO" "Contract Service" "Available contracts: $contract_count"
        echo -e "${GREEN}✅ Contract Service: $contract_count contracts available${NC}"
    else
        log_monitoring "WARNING" "Contract Service" "Contract endpoints not available"
        echo -e "${YELLOW}⚠️ Contract Service: Endpoints not available${NC}"
    fi
    
    # Check contract implementation files
    local contract_files=$(find /opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts/ -name "*.py" 2>/dev/null | wc -l)
    if [ "$contract_files" -gt 0 ]; then
        log_monitoring "INFO" "Contract Service" "Implementation files: $contract_files"
        echo -e "${GREEN}✅ Contract Service: $contract_files implementation files${NC}"
    else
        log_monitoring "WARNING" "Contract Service" "No implementation files found"
        echo -e "${YELLOW}⚠️ Contract Service: No implementation files${NC}"
    fi
}

# Function to generate monitoring report
generate_monitoring_report() {
    local report_file="/opt/aitbc/monitoring_report_$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
AITBC Service Health Monitoring Report
==================================
Date: $(date)
Monitoring Interval: ${MONITORING_INTERVAL}s

SYSTEM STATUS
------------
CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')%
Memory Usage: $(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')%
Disk Usage: $(df / | awk 'NR==2 {print $5}' | sed 's/%//')%

SERVICE STATUS
--------------
Blockchain RPC: ${SERVICE_STATUS[blockchain_rpc]:-unknown}
AI Service: ${SERVICE_STATUS[ai_service]:-unknown}
Marketplace: ${SERVICE_STATUS[marketplace]:-unknown}
Coordinator API: ${SERVICE_STATUS[coordinator_api]:-unknown}
Contract Service: ${SERVICE_STATUS[contract_service]:-unknown}

BLOCKCHAIN METRICS
------------------
Block Height: $(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height 2>/dev/null || echo "N/A")
Total Transactions: $(curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions 2>/dev/null || echo "N/A")
Cross-node Sync: $(( $(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height 2>/dev/null || echo "0") - $(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height' 2>/dev/null || echo "0") )) blocks

SERVICE METRICS
---------------
AI Jobs: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:8006/rpc/ai/stats | jq .total_jobs' 2>/dev/null || echo "N/A")
AI Revenue: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:8006/rpc/ai/stats | jq .total_revenue' 2>/dev/null || echo "N/A") AIT
Marketplace Listings: $(curl -s http://localhost:$GENESIS_PORT/rpc/marketplace/listings | jq '.listings | length' 2>/dev/null || echo "N/A")
Contract Files: $(find /opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts/ -name "*.py" 2>/dev/null | wc -l)

RECENT ALERTS
-------------
$(tail -10 "$ALERT_LOG" 2>/dev/null || echo "No recent alerts")

RECOMMENDATIONS
--------------
EOF

    # Add recommendations based on current status
    if [ "${SERVICE_STATUS[blockchain_rpc]:-unknown}" != "healthy" ]; then
        echo "- CRITICAL: Blockchain RPC not responding - check service status" >> "$report_file"
    fi
    
    if [ "${SERVICE_STATUS[ai_service]:-unknown}" != "healthy" ]; then
        echo "- WARNING: AI service not responding - check follower node" >> "$report_file"
    fi
    
    if [ "${SERVICE_STATUS[coordinator_api]:-unknown}" != "healthy" ]; then
        echo "- WARNING: Coordinator API not responding - check service configuration" >> "$report_file"
    fi
    
    echo "Monitoring report saved to: $report_file"
}

# Function to run continuous monitoring
run_continuous_monitoring() {
    local duration="$1"
    local end_time=$(($(date +%s) + duration))
    
    echo "Starting continuous monitoring for ${duration}s..."
    echo "Press Ctrl+C to stop monitoring"
    echo ""
    
    while [ $(date +%s) -lt $end_time ]; do
        echo "=== $(date) ==="
        
        # System resources
        check_system_resources
        echo ""
        
        # Blockchain metrics
        check_blockchain_metrics
        echo ""
        
        # Service-specific metrics
        check_service_metrics
        echo ""
        
        # Contract service health
        check_contract_service_health
        echo ""
        
        # Service health checks
        check_service_health "Blockchain RPC" "curl -s http://localhost:$GENESIS_PORT/rpc/info"
        check_service_health "AI Service" "ssh $FOLLOWER_NODE 'curl -s http://localhost:8006/rpc/ai/stats'"
        check_service_health "Coordinator API" "curl -s http://localhost:$COORDINATOR_PORT/health/live"
        echo ""
        
        # Performance checks
        check_service_performance "Blockchain RPC" "http://localhost:$GENESIS_PORT/rpc/info" "$ALERT_THRESHOLD_RESPONSE_TIME"
        check_service_performance "Coordinator API" "http://localhost:$COORDINATOR_PORT/health/live" "$ALERT_THRESHOLD_RESPONSE_TIME"
        echo ""
        
        # Wait for next check
        echo "Waiting ${MONITORING_INTERVAL}s for next check..."
        sleep "$MONITORING_INTERVAL"
        echo ""
    done
}

# Function to run quick health check
run_quick_health_check() {
    echo "=== QUICK HEALTH CHECK ==="
    echo ""
    
    # System resources
    check_system_resources
    echo ""
    
    # Service health
    check_service_health "Blockchain RPC" "curl -s http://localhost:$GENESIS_PORT/rpc/info"
    check_service_health "AI Service" "ssh $FOLLOWER_NODE 'curl -s http://localhost:8006/rpc/ai/stats'"
    check_service_health "Coordinator API" "curl -s http://localhost:$COORDINATOR_PORT/health/live"
    check_service_health "Marketplace" "curl -s http://localhost:$GENESIS_PORT/rpc/marketplace/listings"
    echo ""
    
    # Blockchain metrics
    check_blockchain_metrics
    echo ""
    
    # Service metrics
    check_service_metrics
    echo ""
    
    # Contract service
    check_contract_service_health
    echo ""
    
    # Generate report
    generate_monitoring_report
}

# Main execution
case "${1:-quick}" in
    "quick")
        run_quick_health_check
        ;;
    "continuous")
        run_continuous_monitoring "${2:-300}"  # Default 5 minutes
        ;;
    "report")
        generate_monitoring_report
        ;;
    "alerts")
        echo "=== RECENT ALERTS ==="
        tail -20 "$ALERT_LOG" 2>/dev/null || echo "No alerts found"
        ;;
    *)
        echo "Usage: $0 {quick|continuous [duration]|report|alerts}"
        echo ""
        echo "Commands:"
        echo "  quick           - Run quick health check"
        echo "  continuous [duration] - Run continuous monitoring (default: 300s)"
        echo "  report          - Generate monitoring report"
        echo "  alerts          - Show recent alerts"
        exit 1
        ;;
esac

echo ""
echo "=== 🏥 SERVICE HEALTH MONITORING COMPLETE ==="
echo "Log file: $LOG_FILE"
echo "Alert log: $ALERT_LOG"
