#!/bin/bash
# Monitoring Setup Script for AITBC Production
# This script sets up comprehensive health monitoring and alerting

set -e  # Exit on any error

echo "=== AITBC Monitoring Setup ==="

# Create health check script
echo "1. Creating health check script..."
cat > /opt/aitbc/scripts/health_check.sh << 'EOF'
#!/bin/bash
# AITBC Health Check Script

HEALTH_LOG="/var/log/aitbc/health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Create log directory if it doesn't exist
mkdir -p /var/log/aitbc

# Function to check service health
check_service() {
    local service=$1
    local status=$(systemctl is-active "$service" 2>/dev/null)
    if [ "$status" = "active" ]; then
        echo "[$TIMESTAMP] ✅ $service: $status" >> $HEALTH_LOG
        return 0
    else
        echo "[$TIMESTAMP] ❌ $service: $status" >> $HEALTH_LOG
        return 1
    fi
}

# Function to check RPC endpoint
check_rpc() {
    local url=$1
    local response=$(curl -s --max-time 5 "$url" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$response" ]; then
        echo "[$TIMESTAMP] ✅ RPC $url: Responsive" >> $HEALTH_LOG
        return 0
    else
        echo "[$TIMESTAMP] ❌ RPC $url: Not responding" >> $HEALTH_LOG
        return 1
    fi
}

# Function to check blockchain sync
check_sync() {
    local height=$(curl -s --max-time 5 http://localhost:8006/rpc/head | jq .height 2>/dev/null)
    if [ -n "$height" ] && [ "$height" -gt 0 ]; then
        echo "[$TIMESTAMP] ✅ Blockchain height: $height" >> $HEALTH_LOG
        return 0
    else
        echo "[$TIMESTAMP] ❌ Blockchain sync: Failed" >> $HEALTH_LOG
        return 1
    fi
}

# Run health checks
FAILED_CHECKS=0

check_service "aitbc-blockchain-node" || ((FAILED_CHECKS++))
check_service "aitbc-blockchain-rpc" || ((FAILED_CHECKS++))
check_rpc "http://localhost:8006/rpc/info" || ((FAILED_CHECKS++))
check_sync || ((FAILED_CHECKS++))

# Check Redis if available
if systemctl is-active redis >/dev/null 2>&1; then
    check_service "redis" || ((FAILED_CHECKS++))
fi

# Exit with appropriate status
if [ $FAILED_CHECKS -eq 0 ]; then
    echo "[$TIMESTAMP] ✅ All health checks passed" >> $HEALTH_LOG
    exit 0
else
    echo "[$TIMESTAMP] ❌ $FAILED_CHECKS health checks failed" >> $HEALTH_LOG
    exit 1
fi
EOF

chmod +x /opt/aitbc/scripts/health_check.sh

# Setup cron job for health checks
echo "2. Setting up health check cron job..."
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/aitbc/scripts/health_check.sh") | crontab -

# Create log rotation configuration
echo "3. Setting up log rotation..."
cat > /etc/logrotate.d/aitbc << EOF
/var/log/aitbc/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        systemctl reload aitbc-blockchain-rpc >/dev/null 2>&1 || true
    endscript
}
EOF

# Create monitoring dashboard script
echo "4. Creating monitoring dashboard..."
cat > /opt/aitbc/scripts/monitoring_dashboard.sh << 'EOF'
#!/bin/bash
# AITBC Monitoring Dashboard

echo "=== AITBC Monitoring Dashboard ==="
echo "Timestamp: $(date)"
echo

# Service Status
echo "🔧 Service Status:"
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc redis 2>/dev/null | while read service status; do
    echo "   $service: $status"
done
echo

# Blockchain Status
echo "⛓️  Blockchain Status:"
BLOCK_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null)
BLOCK_TIME=$(curl -s http://localhost:8006/rpc/info | jq .genesis_params.block_time_seconds 2>/dev/null)
echo "   Height: $BLOCK_HEIGHT"
echo "   Block Time: $BLOCK_TIME seconds"
echo

# Mining Status
echo "⛏️  Mining Status:"
MINING_STATUS=$(curl -s http://localhost:8006/rpc/mining/status | jq .active 2>/dev/null)
HASH_RATE=$(curl -s http://localhost:8006/rpc/mining/status | jq .hash_rate 2>/dev/null)
echo "   Active: $MINING_STATUS"
echo "   Hash Rate: $HASH_RATE H/s"
echo

# Marketplace Status
echo "🏪 Marketplace Status:"
MARKETPLACE_COUNT=$(curl -s http://localhost:8006/rpc/marketplace/listings | jq .total 2>/dev/null)
echo "   Active Listings: $MARKETPLACE_COUNT"
echo

# AI Services Status
echo "🤖 AI Services Status:"
AI_STATS=$(curl -s http://localhost:8006/rpc/ai/stats | jq .total_jobs 2>/dev/null)
echo "   Total Jobs: $AI_STATS"
echo

echo "=== End Dashboard ==="
EOF

chmod +x /opt/aitbc/scripts/monitoring_dashboard.sh

# Deploy to aitbc node
echo "5. Deploying monitoring to aitbc node..."
scp /opt/aitbc/scripts/health_check.sh aitbc:/opt/aitbc/scripts/
scp /opt/aitbc/scripts/monitoring_dashboard.sh aitbc:/opt/aitbc/scripts/
ssh aitbc 'chmod +x /opt/aitbc/scripts/health_check.sh /opt/aitbc/scripts/monitoring_dashboard.sh'

# Setup cron on aitbc
ssh aitbc '(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/aitbc/scripts/health_check.sh") | crontab -'

echo "✅ Monitoring setup completed successfully!"
echo "   • Health check script created and scheduled"
echo "   • Log rotation configured"
echo "   • Monitoring dashboard available"
echo "   • Deployed to both nodes"
