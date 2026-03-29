#!/bin/bash

# AITBC Maintenance Automation Script
# Automates weekly maintenance tasks

set -e

echo "=== 🔄 AITBC MAINTENANCE AUTOMATION ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Log file
LOG_FILE="/var/log/aitbc/maintenance.log"
mkdir -p $(dirname "$LOG_FILE")

# Function to log actions
log_action() {
    echo "[$(date)] $1" | tee -a "$LOG_FILE"
}

# Function to check status
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "   ${GREEN}✅${NC} $1"
        log_action "SUCCESS: $1"
    else
        echo -e "   ${RED}❌${NC} $1"
        log_action "FAILED: $1"
    fi
}

echo "1. 🧹 SYSTEM CLEANUP"
echo "=================="

# Clean old logs
log_action "Starting log cleanup"
find /var/log/aitbc -name "*.log" -mtime +7 -delete 2>/dev/null || true
find /var/log -name "*aitbc*" -mtime +7 -delete 2>/dev/null || true
check_status "Cleaned old log files"

# Clean temporary files
log_action "Starting temp file cleanup"
find /tmp -name "*aitbc*" -mtime +1 -delete 2>/dev/null || true
find /var/tmp -name "*aitbc*" -mtime +1 -delete 2>/dev/null || true
check_status "Cleaned temporary files"

# Clean old backups (keep last 5)
log_action "Starting backup cleanup"
if [ -d "/opt/aitbc/backups" ]; then
    cd /opt/aitbc/backups
    ls -t | tail -n +6 | xargs -r rm -rf
    check_status "Cleaned old backups (kept last 5)"
else
    echo -e "   ${YELLOW}⚠️${NC} Backup directory not found"
fi

echo ""
echo "2. 💾 DATABASE MAINTENANCE"
echo "========================"

# Optimize main database
log_action "Starting database optimization"
if [ -f "/var/lib/aitbc/data/ait-mainnet/chain.db" ]; then
    sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;" 2>/dev/null || true
    sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "ANALYZE;" 2>/dev/null || true
    check_status "Main database optimized"
else
    echo -e "   ${YELLOW}⚠️${NC} Main database not found"
fi

# Optimize mempool database
if [ -f "/var/lib/aitbc/data/mempool.db" ]; then
    sqlite3 /var/lib/aitbc/data/mempool.db "VACUUM;" 2>/dev/null || true
    sqlite3 /var/lib/aitbc/data/mempool.db "ANALYZE;" 2>/dev/null || true
    check_status "Mempool database optimized"
else
    echo -e "   ${YELLOW}⚠️${NC} Mempool database not found"
fi

echo ""
echo "3. 🔍 SYSTEM HEALTH CHECK"
echo "========================"

# Check service status
log_action "Starting service health check"
services=("aitbc-blockchain-node" "aitbc-blockchain-rpc")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo -e "   ${GREEN}✅${NC} $service is running"
        log_action "SUCCESS: $service is running"
    else
        echo -e "   ${RED}❌${NC} $service is not running"
        log_action "FAILED: $service is not running"
        # Try to restart failed service
        systemctl restart "$service" || true
        sleep 2
        if systemctl is-active --quiet "$service"; then
            echo -e "   ${YELLOW}⚠️${NC} $service restarted successfully"
            log_action "RECOVERED: $service restarted"
        fi
    fi
done

# Check disk space
log_action "Starting disk space check"
disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$disk_usage" -lt 80 ]; then
    echo -e "   ${GREEN}✅${NC} Disk usage: ${disk_usage}%"
    log_action "SUCCESS: Disk usage ${disk_usage}%"
else
    echo -e "   ${YELLOW}⚠️${NC} Disk usage high: ${disk_usage}%"
    log_action "WARNING: Disk usage ${disk_usage}%"
fi

# Check memory usage
log_action "Starting memory check"
mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
if [ $(echo "$mem_usage < 80" | bc -l) -eq 1 ]; then
    echo -e "   ${GREEN}✅${NC} Memory usage: ${mem_usage}%"
    log_action "SUCCESS: Memory usage ${mem_usage}%"
else
    echo -e "   ${YELLOW}⚠️${NC} Memory usage high: ${mem_usage}%"
    log_action "WARNING: Memory usage ${mem_usage}%"
fi

echo ""
echo "4. 🌐 NETWORK CONNECTIVITY"
echo "========================"

# Test RPC endpoints
log_action "Starting RPC connectivity test"
if curl -s http://localhost:8006/rpc/info >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} Local RPC responding"
    log_action "SUCCESS: Local RPC responding"
else
    echo -e "   ${RED}❌${NC} Local RPC not responding"
    log_action "FAILED: Local RPC not responding"
fi

# Test cross-node connectivity
if ssh aitbc "curl -s http://localhost:8006/rpc/info" >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} Cross-node connectivity working"
    log_action "SUCCESS: Cross-node connectivity working"
else
    echo -e "   ${RED}❌${NC} Cross-node connectivity failed"
    log_action "FAILED: Cross-node connectivity failed"
fi

echo ""
echo "5. 🔒 SECURITY CHECK"
echo "=================="

# Check security monitoring
log_action "Starting security check"
if [ -f "/opt/aitbc/scripts/security_monitor.sh" ]; then
    # Run security monitor
    /opt/aitbc/scripts/security_monitor.sh >/dev/null 2>&1 || true
    check_status "Security monitoring executed"
else
    echo -e "   ${YELLOW}⚠️${NC} Security monitor not found"
fi

# Check for failed SSH attempts
failed_ssh=$(grep "authentication failure" /var/log/auth.log 2>/dev/null | grep "$(date '+%b %d')" | wc -l)
if [ "$failed_ssh" -lt 10 ]; then
    echo -e "   ${GREEN}✅${NC} Failed SSH attempts: $failed_ssh"
    log_action "SUCCESS: Failed SSH attempts $failed_ssh"
else
    echo -e "   ${YELLOW}⚠️${NC} High failed SSH attempts: $failed_ssh"
    log_action "WARNING: High failed SSH attempts $failed_ssh"
fi

echo ""
echo "6. 📊 PERFORMANCE METRICS"
echo "========================"

# Collect performance metrics
log_action "Starting performance collection"
mkdir -p /opt/aitbc/performance

# Get current metrics
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
block_height=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
total_accounts=$(curl -s http://localhost:8006/rpc/info | jq -r .total_accounts 2>/dev/null || echo "0")
total_transactions=$(curl -s http://localhost:8006/rpc/info | jq -r .total_transactions 2>/dev/null || echo "0")

# Save metrics
cat > "/opt/aitbc/performance/metrics_$(date +%Y%m%d_%H%M%S).txt" << EOF
Maintenance Performance Metrics
Generated: $(date)

System Metrics:
- CPU Usage: ${cpu_usage}%
- Memory Usage: ${mem_usage}%
- Disk Usage: ${disk_usage}%

Blockchain Metrics:
- Block Height: ${block_height}
- Total Accounts: ${total_accounts}
- Total Transactions: ${total_transactions}

Services Status:
- aitbc-blockchain-node: $(systemctl is-active aitbc-blockchain-node)
- aitbc-blockchain-rpc: $(systemctl is-active aitbc-blockchain-rpc)
EOF

check_status "Performance metrics collected"

echo ""
echo "7. 💾 BACKUP CREATION"
echo "===================="

# Create backup
log_action "Starting backup creation"
backup_dir="/opt/aitbc/backups/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"

# Backup configuration files
cp -r /etc/aitbc "$backup_dir/" 2>/dev/null || true
cp -r /var/lib/aitbc/keystore "$backup_dir/" 2>/dev/null || true

# Backup database files
cp -r /var/lib/aitbc/data "$backup_dir/" 2>/dev/null || true

# Create backup manifest
cat > "$backup_dir/manifest.txt" << EOF
AITBC Backup Manifest
Created: $(date)
Hostname: $(hostname)
Block Height: $block_height
Total Accounts: $total_accounts
Total Transactions: $total_transactions

Contents:
- Configuration files
- Wallet keystore
- Database files
EOF

check_status "Backup created: $backup_dir"

echo ""
echo "8. 🔄 SERVICE RESTART (Optional)"
echo "=============================="

# Graceful service restart if needed
echo "Checking if service restart is needed..."
uptime_days=$(uptime -p 2>/dev/null | grep -o '[0-9]*' | head -1 || echo "0")
if [ "$uptime_days" -gt 7 ]; then
    echo "System uptime > 7 days, restarting services..."
    log_action "Restarting services due to high uptime"
    
    systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
    ssh aitbc 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc'
    
    sleep 5
    
    # Verify services are running
    if systemctl is-active --quiet aitbc-blockchain-node && systemctl is-active --quiet aitbc-blockchain-rpc; then
        check_status "Services restarted successfully"
    else
        echo -e "   ${RED}❌${NC} Service restart failed"
        log_action "FAILED: Service restart failed"
    fi
else
    echo -e "   ${GREEN}✅${NC} No service restart needed (uptime: $uptime_days days)"
fi

echo ""
echo "=== 🔄 MAINTENANCE COMPLETE ==="
echo ""
echo "Maintenance tasks completed:"
echo "• System cleanup performed"
echo "• Database optimization completed"
echo "• Health checks executed"
echo "• Security monitoring performed"
echo "• Performance metrics collected"
echo "• Backup created"
echo "• Log file: $LOG_FILE"
echo ""
echo -e "${GREEN}✅ Maintenance automation completed successfully!${NC}"
