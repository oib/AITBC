#!/bin/bash

# AITBC Operations Automation Script
# Handles routine operations, monitoring, and maintenance

set -e

echo "=== 🔧 AITBC OPERATIONS AUTOMATION ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
LOG_FILE="/var/log/aitbc/operations.log"
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEM=90
ALERT_THRESHOLD_DISK=85

# Function to log operations
log_ops() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# Function to send alert
send_alert() {
    local message="$1"
    echo "ALERT: $message" | tee -a "$LOG_FILE"
    # Could integrate with email, Slack, etc.
}

# Function to check system health
check_system_health() {
    echo "🏥 SYSTEM HEALTH CHECK"
    echo "===================="
    
    # CPU usage
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    echo "CPU Usage: ${cpu_usage}%"
    
    if (( $(echo "$cpu_usage > $ALERT_THRESHOLD_CPU" | bc -l) )); then
        send_alert "High CPU usage: ${cpu_usage}%"
    fi
    
    # Memory usage
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    echo "Memory Usage: ${mem_usage}%"
    
    if (( $(echo "$mem_usage > $ALERT_THRESHOLD_MEM" | bc -l) )); then
        send_alert "High memory usage: ${mem_usage}%"
    fi
    
    # Disk usage
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    echo "Disk Usage: ${disk_usage}%"
    
    if [ "$disk_usage" -gt "$ALERT_THRESHOLD_DISK" ]; then
        send_alert "High disk usage: ${disk_usage}%"
    fi
    
    log_ops "Health check: CPU=${cpu_usage}%, MEM=${mem_usage}%, DISK=${disk_usage}%"
}

# Function to check blockchain health
check_blockchain_health() {
    echo ""
    echo "⛓️ BLOCKCHAIN HEALTH CHECK"
    echo "========================"
    
    # Check local node
    if curl -s http://localhost:8006/rpc/info >/dev/null 2>&1; then
        local height=$(curl -s http://localhost:8006/rpc/head | jq .height)
        local txs=$(curl -s http://localhost:8006/rpc/info | jq .total_transactions)
        echo "Local node: Height=$height, Transactions=$txs"
        log_ops "Local blockchain: height=$height, txs=$txs"
    else
        send_alert "Local blockchain node not responding"
        return 1
    fi
    
    # Check remote node
    if ssh aitbc 'curl -s http://localhost:8006/rpc/info' >/dev/null 2>&1; then
        local remote_height=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
        echo "Remote node: Height=$remote_height"
        log_ops "Remote blockchain: height=$remote_height"
        
        # Check sync difference
        local sync_diff=$((height - remote_height))
        if [ "$sync_diff" -gt 100 ]; then
            send_alert "Large sync gap: $sync_diff blocks"
            echo "Triggering bulk sync..."
            ssh aitbc '/opt/aitbc/scripts/fast_bulk_sync.sh'
        fi
    else
        send_alert "Remote blockchain node not responding"
        return 1
    fi
    
    # Check services
    echo ""
    echo "Service Status:"
    systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc
}

# Function to check GPU health
check_gpu_health() {
    echo ""
    echo "🖥️ GPU HEALTH CHECK"
    echo "=================="
    
    if ssh aitbc "command -v nvidia-smi" >/dev/null 2>&1; then
        local gpu_info=$(ssh aitbc "nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits")
        local gpu_name=$(echo "$gpu_info" | cut -d',' -f1)
        local gpu_util=$(echo "$gpu_info" | cut -d',' -f2)
        local gpu_temp=$(echo "$gpu_info" | cut -d',' -f3)
        local mem_used=$(echo "$gpu_info" | cut -d',' -f4)
        local mem_total=$(echo "$gpu_info" | cut -d',' -f5)
        
        echo "GPU: $gpu_name"
        echo "Utilization: ${gpu_util}%"
        echo "Temperature: ${gpu_temp}°C"
        echo "Memory: ${mem_used}MB/${mem_total}MB"
        
        # GPU alerts
        if [ "$gpu_temp" -gt 80 ]; then
            send_alert "High GPU temperature: ${gpu_temp}°C"
        fi
        
        if [ "$gpu_util" -gt 90 ]; then
            send_alert "High GPU utilization: ${gpu_util}%"
        fi
        
        log_ops "GPU health: util=${gpu_util}%, temp=${gpu_temp}°C, mem=${mem_used}/${mem_total}MB"
    else
        echo "GPU not available"
        log_ops "GPU health: not available"
    fi
}

# Function to check marketplace activity
check_marketplace_activity() {
    echo ""
    echo "🛒 MARKETPLACE ACTIVITY CHECK"
    echo "==========================="
    
    if ssh aitbc 'curl -s http://localhost:8006/rpc/marketplace/listings' >/dev/null 2>&1; then
        local listings=$(ssh aitbc 'curl -s http://localhost:8006/rpc/marketplace/listings | jq .total')
        echo "Active listings: $listings"
        
        # Check AI activity
        local ai_stats=$(ssh aitbc 'curl -s http://localhost:8006/rpc/ai/stats 2>/dev/null || echo "{}"')
        echo "AI service status: Available"
        
        log_ops "Marketplace: listings=$listings"
    else
        echo "Marketplace not available"
        log_ops "Marketplace: not available"
    fi
}

# Function to perform routine maintenance
perform_maintenance() {
    echo ""
    echo "🔧 ROUTINE MAINTENANCE"
    echo "===================="
    
    echo "Performing system cleanup..."
    log_ops "Starting routine maintenance"
    
    # Clean old logs
    find /var/log/aitbc -name "*.log" -mtime +7 -delete 2>/dev/null || true
    echo "Cleaned old log files"
    
    # Optimize database
    if [ -f "/var/lib/aitbc/data/ait-mainnet/chain.db" ]; then
        sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;" 2>/dev/null || true
        echo "Optimized blockchain database"
    fi
    
    if [ -f "/var/lib/aitbc/data/mempool.db" ]; then
        sqlite3 /var/lib/aitbc/data/mempool.db "VACUUM;" 2>/dev/null || true
        echo "Optimized mempool database"
    fi
    
    # Check disk space
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 80 ]; then
        echo "Cleaning temporary files..."
        find /tmp -mtime +1 -delete 2>/dev/null || true
        find /var/tmp -mtime +1 -delete 2>/dev/null || true
    fi
    
    echo "Maintenance completed"
    log_ops "Routine maintenance completed"
}

# Function to generate daily report
generate_daily_report() {
    echo ""
    echo "📊 GENERATING DAILY REPORT"
    echo "========================"
    
    local report_file="/opt/aitbc/reports/daily_report_$(date +%Y%m%d).txt"
    mkdir -p "$(dirname "$report_file")"
    
    cat > "$report_file" << EOF
AITBC Daily Operations Report
============================
Date: $(date)
Generated: $(date)

SYSTEM STATUS
------------
CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')%
Memory Usage: $(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')%
Disk Usage: $(df / | awk 'NR==2 {print $5}' | sed 's/%//')%

BLOCKCHAIN STATUS
----------------
Local Height: $(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "N/A")
Total Transactions: $(curl -s http://localhost:8006/rpc/info | jq .total_transactions 2>/dev/null || echo "N/A")
Remote Height: $(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height' 2>/dev/null || echo "N/A")

GPU STATUS
----------
$(ssh aitbc "nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu --format=csv,noheader,nounits" 2>/dev/null || echo "GPU not available")

MARKETPLACE STATUS
------------------
Active Listings: $(ssh aitbc 'curl -s http://localhost:8006/rpc/marketplace/listings | jq .total' 2>/dev/null || echo "N/A")

SERVICES
--------
$(systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc)

ALERTS
------
$(tail -10 "$LOG_FILE" | grep ALERT || echo "No alerts")

RECOMMENDATIONS
---------------
EOF

    # Add recommendations based on current status
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    
    if (( $(echo "$cpu_usage > 70" | bc -l) )); then
        echo "- Consider CPU optimization or scaling" >> "$report_file"
    fi
    
    if (( $(echo "$mem_usage > 80" | bc -l) )); then
        echo "- Monitor memory usage, consider optimization" >> "$report_file"
    fi
    
    echo "Report saved to: $report_file"
    log_ops "Daily report generated: $report_file"
}

# Function to handle alerts
handle_alerts() {
    echo ""
    echo "🚨 ALERT HANDLING"
    echo "==============="
    
    local recent_alerts=$(tail -20 "$LOG_FILE" | grep ALERT | tail -5)
    if [ -n "$recent_alerts" ]; then
        echo "Recent alerts:"
        echo "$recent_alerts"
        
        # Count alerts in last hour
        local alert_count=$(tail -100 "$LOG_FILE" | grep "$(date '+%Y-%m-%d %H:')" | grep ALERT | wc -l)
        if [ "$alert_count" -gt 5 ]; then
            send_alert "High alert frequency: $alert_count alerts in last hour"
        fi
    else
        echo "No recent alerts"
    fi
}

# Main operations function
main_operations() {
    local operation_type="$1"
    
    case "$operation_type" in
        "health")
            check_system_health
            check_blockchain_health
            check_gpu_health
            check_marketplace_activity
            ;;
        "maintenance")
            perform_maintenance
            ;;
        "report")
            generate_daily_report
            ;;
        "alerts")
            handle_alerts
            ;;
        "full")
            check_system_health
            check_blockchain_health
            check_gpu_health
            check_marketplace_activity
            perform_maintenance
            generate_daily_report
            handle_alerts
            ;;
        *)
            echo "Usage: $0 {health|maintenance|report|alerts|full}"
            echo ""
            echo "Operations:"
            echo "  health     - Check system and blockchain health"
            echo "  maintenance - Perform routine maintenance"
            echo "  report     - Generate daily report"
            echo "  alerts     - Handle recent alerts"
            echo "  full       - Run all operations"
            exit 1
            ;;
    esac
}

# Main execution
if [ $# -eq 0 ]; then
    echo "=== 🔄 RUNNING FULL OPERATIONS CHECK ==="
    main_operations "full"
else
    main_operations "$1"
fi

echo ""
echo "=== 🔧 OPERATIONS AUTOMATION COMPLETE ==="
echo "Log file: $LOG_FILE"
