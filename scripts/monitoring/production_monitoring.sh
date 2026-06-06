#!/bin/bash
#
# Production Monitoring Setup for AITBC Platform
# Configures monitoring, alerting, and observability
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# Create monitoring directory
MONITORING_DIR="/opt/aitbc/monitoring"
mkdir -p "$MONITORING_DIR"

# Setup system metrics collection
setup_system_metrics() {
    log "Setting up system metrics collection..."
    
    # Create metrics collection script
    cat > "$MONITORING_DIR/collect_metrics.sh" << 'EOF'
#!/bin/bash
# System metrics collection for AITBC platform

METRICS_FILE="/opt/aitbc/monitoring/metrics.log"
TIMESTAMP=$(date -Iseconds)

# System metrics
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
DISK_USAGE=$(df -h / | awk 'NR==2{print $5}' | sed 's/%//')

# Service metrics
COORDINATOR_STATUS=$(systemctl is-active aitbc-coordinator)
BLOCKCHAIN_STATUS=$(systemctl is-active blockchain-node)

# API metrics
API_RESPONSE_TIME=$(curl -o /dev/null -s -w '%{time_total}' https://aitbc.bubuit.net/api/v1/health 2>/dev/null || echo "0")
API_STATUS=$(curl -o /dev/null -s -w '%{http_code}' https://aitbc.bubuit.net/api/v1/health 2>/dev/null || echo "000")

# Write metrics
echo "$TIMESTAMP,cpu:$CPU_USAGE,memory:$MEM_USAGE,disk:$DISK_USAGE,coordinator:$COORDINATOR_STATUS,blockchain:$BLOCKCHAIN_STATUS,api_time:$API_RESPONSE_TIME,api_status:$API_STATUS" >> "$METRICS_FILE"

# Keep only last 1000 lines
tail -n 1000 "$METRICS_FILE" > "$METRICS_FILE.tmp" && mv "$METRICS_FILE.tmp" "$METRICS_FILE"
EOF
    
    chmod +x "$MONITORING_DIR/collect_metrics.sh"
    
    # Add to crontab (every 2 minutes)
    (crontab -l 2>/dev/null; echo "*/2 * * * * $MONITORING_DIR/collect_metrics.sh") | crontab -
    
    success "System metrics collection configured"
}

# Setup alerting system
setup_alerting() {
    log "Setting up alerting system..."
    
    # Create alerting script
    cat > "$MONITORING_DIR/check_alerts.sh" << 'EOF'
#!/bin/bash
# Alert checking for AITBC platform

ALERT_LOG="/opt/aitbc/monitoring/alerts.log"
TIMESTAMP=$(date -Iseconds)
ALERT_TRIGGERED=false

# Check service status
check_service() {
    local service=$1
    local status=$(systemctl is-active "$service" 2>/dev/null || echo "failed")
    
    if [[ "$status" != "active" ]]; then
        echo "$TIMESTAMP,SERVICE,$service is $status" >> "$ALERT_LOG"
        echo "🚨 ALERT: Service $service is $status"
        ALERT_TRIGGERED=true
    fi
}

# Check API health
check_api() {
    local response=$(curl -s -o /dev/null -w '%{http_code}' https://aitbc.bubuit.net/api/v1/health 2>/dev/null || echo "000")
    
    if [[ "$response" != "200" ]]; then
        echo "$TIMESTAMP,API,Health endpoint returned $response" >> "$ALERT_LOG"
        echo "🚨 ALERT: API health check failed (HTTP $response)"
        ALERT_TRIGGERED=true
    fi
}

# Check disk space
check_disk() {
    local usage=$(df / | awk 'NR==2{print $5}' | sed 's/%//')
    
    if [[ $usage -gt 80 ]]; then
        echo "$TIMESTAMP,DISK,Disk usage is ${usage}%" >> "$ALERT_LOG"
        echo "🚨 ALERT: Disk usage is ${usage}%"
        ALERT_TRIGGERED=true
    fi
}

# Check memory usage
check_memory() {
    local usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    
    if [[ $usage -gt 90 ]]; then
        echo "$TIMESTAMP,MEMORY,Memory usage is ${usage}%" >> "$ALERT_LOG"
        echo "🚨 ALERT: Memory usage is ${usage}%"
        ALERT_TRIGGERED=true
    fi
}

# Run checks
check_service "aitbc-coordinator"
check_service "blockchain-node"
check_api
check_disk
check_memory

# If no alerts, log all clear
if [[ "$ALERT_TRIGGERED" == "false" ]]; then
    echo "$TIMESTAMP,ALL_CLEAR,All systems operational" >> "$ALERT_LOG"
fi
EOF
    
    chmod +x "$MONITORING_DIR/check_alerts.sh"
    
    # Add to crontab (every 5 minutes)
    (crontab -l 2>/dev/null; echo "*/5 * * * * $MONITORING_DIR/check_alerts.sh") | crontab -
    
    success "Alerting system configured"
}

# Setup performance dashboard
setup_dashboard() {
    log "Setting up performance dashboard..."
    
    # Create dashboard script
    cat > "$MONITORING_DIR/dashboard.sh" << 'EOF'
#!/bin/bash
# Performance dashboard for AITBC platform

clear
echo "🔍 AITBC Platform Performance Dashboard"
echo "========================================"
echo "Last Updated: $(date)"
echo ""

# System Status
echo "📊 System Status:"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')% used"
echo "Memory: $(free -h | grep Mem | awk '{print $3"/"$2}')"
echo "Disk: $(df -h / | awk 'NR==2{print $3"/"$2" ("$5")"}')"
echo ""

# Service Status
echo "🔧 Service Status:"
systemctl is-active aitbc-coordinator && echo "✅ Coordinator API: Active" || echo "❌ Coordinator API: Inactive"
systemctl is-active blockchain-node && echo "✅ Blockchain Node: Active" || echo "❌ Blockchain Node: Inactive"
systemctl is-active nginx && echo "✅ Nginx: Active" || echo "❌ Nginx: Inactive"
echo ""

# API Performance
echo "🌐 API Performance:"
API_TIME=$(curl -o /dev/null -s -w '%{time_total}' https://aitbc.bubuit.net/api/v1/health 2>/dev/null || echo "0.000")
echo "Health Endpoint: ${API_TIME}s"
echo ""

# Recent Alerts (last 10)
echo "🚨 Recent Alerts:"
if [[ -f /opt/aitbc/monitoring/alerts.log ]]; then
    tail -n 10 /opt/aitbc/monitoring/alerts.log | while IFS=',' read -r timestamp type message; do
        echo "  $timestamp: $message"
    done
else
    echo "  No alerts logged"
fi
echo ""

# Quick Stats
echo "📈 Quick Stats:"
if [[ -f /opt/aitbc/monitoring/metrics.log ]]; then
    echo "  Metrics collected: $(wc -l < /opt/aitbc/monitoring/metrics.log) entries"
    echo "  Alerts triggered: $(grep -c "ALERT" /opt/aitbc/monitoring/alerts.log 2>/dev/null || echo "0")"
fi

echo ""
echo "Press Ctrl+C to exit, or refresh in 30 seconds..."
sleep 30
exec "$0"
EOF
    
    chmod +x "$MONITORING_DIR/dashboard.sh"
    
    success "Performance dashboard created"
}

# Setup log analysis
setup_log_analysis() {
    log "Setting up log analysis..."
    
    # Create log analysis script
    cat > "$MONITORING_DIR/analyze_logs.sh" << 'EOF'
#!/bin/bash
# Log analysis for AITBC platform

LOG_DIR="/var/log"
ANALYSIS_FILE="/opt/aitbc/monitoring/log_analysis.txt"
TIMESTAMP=$(date -Iseconds)

echo "=== Log Analysis - $TIMESTAMP ===" >> "$ANALYSIS_FILE"

# Analyze nginx logs
if [[ -f "$LOG_DIR/nginx/access.log" ]]; then
    echo "" >> "$ANALYSIS_FILE"
    echo "NGINX Access Analysis:" >> "$ANALYSIS_FILE"
    
    # Top 10 endpoints
    echo "Top 10 endpoints:" >> "$ANALYSIS_FILE"
    awk '{print $7}' "$LOG_DIR/nginx/access.log" | sort | uniq -c | sort -nr | head -10 >> "$ANALYSIS_FILE"
    
    # HTTP status codes
    echo "" >> "$ANALYSIS_FILE"
    echo "HTTP Status Codes:" >> "$ANALYSIS_FILE"
    awk '{print $9}' "$LOG_DIR/nginx/access.log" | sort | uniq -c | sort -nr >> "$ANALYSIS_FILE"
    
    # Error rate
    local total=$(wc -l < "$LOG_DIR/nginx/access.log")
    local errors=$(awk '$9 >= 400 {print}' "$LOG_DIR/nginx/access.log" | wc -l)
    local error_rate=$(echo "scale=2; $errors * 100 / $total" | bc)
    echo "" >> "$ANALYSIS_FILE"
    echo "Error Rate: ${error_rate}%" >> "$ANALYSIS_FILE"
fi

# Analyze application logs
if journalctl -u aitbc-coordinator --since "1 hour ago" | grep -q "ERROR"; then
    echo "" >> "$ANALYSIS_FILE"
    echo "Application Errors (last hour):" >> "$ANALYSIS_FILE"
    journalctl -u aitbc-coordinator --since "1 hour ago" | grep "ERROR" | tail -5 >> "$ANALYSIS_FILE"
fi

echo "Analysis complete" >> "$ANALYSIS_FILE"
EOF
    
    chmod +x "$MONITORING_DIR/analyze_logs.sh"
    
    # Add to crontab (hourly)
    (crontab -l 2>/dev/null; echo "0 * * * * $MONITORING_DIR/analyze_logs.sh") | crontab -
    
    success "Log analysis configured"
}

# Main execution
main() {
    log "Setting up AITBC Production Monitoring..."
    
    setup_system_metrics
    setup_alerting
    setup_dashboard
    setup_log_analysis
    
    success "Production monitoring setup complete!"
    
    echo
    echo "📊 MONITORING SUMMARY:"
    echo "   ✅ System metrics collection (every 2 minutes)"
    echo "   ✅ Alert checking (every 5 minutes)"
    echo "   ✅ Performance dashboard"
    echo "   ✅ Log analysis (hourly)"
    echo
    echo "🔧 MONITORING COMMANDS:"
    echo "   Dashboard: $MONITORING_DIR/dashboard.sh"
    echo "   Metrics: $MONITORING_DIR/collect_metrics.sh"
    echo "   Alerts: $MONITORING_DIR/check_alerts.sh"
    echo "   Log Analysis: $MONITORING_DIR/analyze_logs.sh"
    echo
    echo "📁 MONITORING FILES:"
    echo "   Metrics: $MONITORING_DIR/metrics.log"
    echo "   Alerts: $MONITORING_DIR/alerts.log"
    echo "   Analysis: $MONITORING_DIR/log_analysis.txt"
}

main "$@"
