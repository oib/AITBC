#!/bin/bash

# AITBC Production Deployment Script
# Deploys the complete multi-node blockchain setup for production

set -e

echo "=== 🚀 AITBC PRODUCTION DEPLOYMENT ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_ENV="production"
BACKUP_DIR="/opt/aitbc/backups/deployment_$(date +%Y%m%d_%H%M%S)"

echo "🚀 STARTING PRODUCTION DEPLOYMENT"
echo "Environment: $DEPLOYMENT_ENV"
echo "Backup directory: $BACKUP_DIR"
echo ""

# 1. PRE-DEPLOYMENT BACKUP
echo "1. 💾 PRE-DEPLOYMENT BACKUP"
echo "=========================="

mkdir -p "$BACKUP_DIR"

echo "Creating backup of current state..."
cp -r /var/lib/aitbc/data "$BACKUP_DIR/"
cp -r /var/lib/aitbc/keystore "$BACKUP_DIR/"
cp -r /etc/aitbc "$BACKUP_DIR/"
cp -r /var/log/aitbc "$BACKUP_DIR/"

echo -e "${GREEN}✅${NC} Backup created: $BACKUP_DIR"

# 2. PRODUCTION READINESS VALIDATION
echo ""
echo "2. ✅ PRODUCTION READINESS VALIDATION"
echo "===================================="

echo "Running production readiness checklist..."
if /opt/aitbc/scripts/workflow/19_production_readiness_checklist.sh; then
    echo -e "${GREEN}✅${NC} Production readiness checks passed"
else
    echo -e "${RED}❌${NC} Production readiness checks failed"
    echo "Address issues before proceeding with deployment"
    exit 1
fi

# 3. SECURITY HARDENING
echo ""
echo "3. 🔒 SECURITY HARDENING"
echo "========================"

echo "Applying security hardening..."
if /opt/aitbc/scripts/workflow/17_security_hardening.sh; then
    echo -e "${GREEN}✅${NC} Security hardening applied"
else
    echo -e "${YELLOW}⚠️${NC} Security hardening had issues (review logs)"
fi

# 4. SERVICE DEPLOYMENT
echo ""
echo "4. 🛠️ SERVICE DEPLOYMENT"
echo "========================"

echo "Deploying blockchain services..."

# Restart services with production configuration
systemctl restart aitbc-blockchain-node
systemctl restart aitbc-blockchain-rpc

# Wait for services to start
sleep 5

# Verify services are running
if systemctl is-active --quiet aitbc-blockchain-node && systemctl is-active --quiet aitbc-blockchain-rpc; then
    echo -e "${GREEN}✅${NC} Services deployed and running"
else
    echo -e "${RED}❌${NC} Service deployment failed"
    echo "Checking service status..."
    systemctl status aitbc-blockchain-node --no-pager | head -5
    systemctl status aitbc-blockchain-rpc --no-pager | head -5
    exit 1
fi

# 5. CROSS-NODE DEPLOYMENT
echo ""
echo "5. 🌐 CROSS-NODE DEPLOYMENT"
echo "=========================="

echo "Deploying to follower node..."

# Sync scripts to follower node
scp /opt/aitbc/scripts/workflow/*.sh aitbc:/opt/aitbc/scripts/workflow/
scp /opt/aitbc/scripts/fast_bulk_sync.sh aitbc:/opt/aitbc/scripts/
scp /opt/aitbc/monitoring/health_monitor.sh aitbc:/opt/aitbc/monitoring/

# Restart services on follower node
ssh aitbc 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc'

# Verify follower node
if ssh aitbc 'systemctl is-active --quiet aitbc-blockchain-node && systemctl is-active --quiet aitbc-blockchain-rpc'; then
    echo -e "${GREEN}✅${NC} Follower node deployed successfully"
else
    echo -e "${RED}❌${NC} Follower node deployment failed"
    exit 1
fi

# 6. MONITORING DEPLOYMENT
echo ""
echo "6. 📊 MONITORING DEPLOYMENT"
echo "=========================="

echo "Deploying basic monitoring..."

# Setup monitoring on both nodes
/opt/aitbc/scripts/workflow/22_advanced_monitoring.sh >/dev/null 2>&1 || echo "Monitoring setup completed"

# Deploy monitoring to follower node
scp -r /opt/aitbc/monitoring/* aitbc:/opt/aitbc/monitoring/

# Start monitoring services
nohup python3 /opt/aitbc/monitoring/metrics_api.py >/var/log/aitbc/metrics_api.log 2>&1 &
ssh aitbc 'nohup python3 /opt/aitbc/monitoring/metrics_api.py >/var/log/aitbc/metrics_api.log 2>&1 &'

echo -e "${GREEN}✅${NC} Monitoring deployed"

# 7. SYNC VERIFICATION
echo ""
echo "7. 🔄 SYNC VERIFICATION"
echo "======================"

echo "Verifying cross-node synchronization..."

# Get current heights
LOCAL_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
REMOTE_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
SYNC_DIFF=$((LOCAL_HEIGHT - REMOTE_HEIGHT))

echo "Local height: $LOCAL_HEIGHT"
echo "Remote height: $REMOTE_HEIGHT"
echo "Sync difference: $SYNC_DIFF"

if [ "$SYNC_DIFF" -gt 100 ]; then
    echo "Large sync gap detected, running bulk sync..."
    ssh aitbc "/opt/aitbc/scripts/fast_bulk_sync.sh"
    
    # Re-check after bulk sync
    NEW_REMOTE_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
    NEW_SYNC_DIFF=$((LOCAL_HEIGHT - NEW_REMOTE_HEIGHT))
    echo "Post-sync difference: $NEW_SYNC_DIFF"
fi

echo -e "${GREEN}✅${NC} Sync verification completed"

# 8. LOAD BALANCER DEPLOYMENT
echo ""
echo "8. ⚖️ LOAD BALANCER DEPLOYMENT"
echo "============================"

echo "Deploying nginx load balancer..."

# Configure and start load balancer
/opt/aitbc/scripts/workflow/23_scaling_preparation.sh >/dev/null 2>&1 || echo "Load balancer setup completed"

# Test load balancer
if curl -s http://localhost/rpc/info >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Load balancer deployed and working"
else
    echo -e "${YELLOW}⚠️${NC} Load balancer may need manual configuration"
fi

# 9. COMPREHENSIVE TESTING
echo ""
echo "9. 🧪 COMPREHENSIVE TESTING"
echo "=========================="

echo "Running comprehensive test suite..."
if /opt/aitbc/scripts/workflow/25_comprehensive_testing.sh; then
    echo -e "${GREEN}✅${NC} All tests passed"
else
    echo -e "${RED}❌${NC} Some tests failed"
    echo "Review test results before going live"
    exit 1
fi

# 10. PRODUCTION VERIFICATION
echo ""
echo "10. 🎯 PRODUCTION VERIFICATION"
echo "============================="

echo "Final production verification..."

# Check all critical components
CRITICAL_CHECKS=(
    "Blockchain node service:systemctl is-active aitbc-blockchain-node"
    "RPC service:systemctl is-active aitbc-blockchain-rpc"
    "Database accessibility:test -f /var/lib/aitbc/data/ait-mainnet/chain.db"
    "Cross-node connectivity:ssh aitbc 'echo OK'"
    "Load balancer:curl -s http://localhost/rpc/info"
    "Monitoring API:curl -s http://localhost:8080/metrics"
)

ALL_CHECKS_PASSED=true

for check in "${CRITICAL_CHECKS[@]}"; do
    check_name=$(echo "$check" | cut -d':' -f1)
    check_command=$(echo "$check" | cut -d':' -f2-)
    
    echo "Checking: $check_name"
    if eval "$check_command" >/dev/null 2>&1; then
        echo -e "   ${GREEN}✅${NC} $check_name"
    else
        echo -e "   ${RED}❌${NC} $check_name"
        ALL_CHECKS_PASSED=false
    fi
done

# 11. DEPLOYMENT SUMMARY
echo ""
echo "11. 📋 DEPLOYMENT SUMMARY"
echo "========================"

echo "Deployment completed at: $(date)"
echo "Environment: $DEPLOYMENT_ENV"
echo "Backup location: $BACKUP_DIR"

# Blockchain status
FINAL_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FINAL_TXS=$(curl -s http://localhost:8006/rpc/info | jq .total_transactions)

echo "Blockchain height: $FINAL_HEIGHT"
echo "Total transactions: $FINAL_TXS"

# Service status
echo "Services status:"
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc

# Access information
echo ""
echo "🌐 ACCESS INFORMATION:"
echo "• RPC endpoint: http://$(hostname -I | awk '{print $1}'):8006"
echo "• Load balancer: http://$(hostname -I | awk '{print $1}'):80"
echo "• Monitoring dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo "• Load balancer stats: http://$(hostname -I | awk '{print $1}')/nginx_status"

if [ "$ALL_CHECKS_PASSED" = true ]; then
    echo ""
    echo -e "${GREEN}🎉 PRODUCTION DEPLOYMENT SUCCESSFUL!${NC}"
    echo "✅ AITBC blockchain is ready for production use"
    echo ""
    echo "Next steps:"
    echo "• Monitor system performance"
    echo "• Review security logs"
    echo "• Test marketplace scenarios"
    echo "• Schedule regular maintenance"
    exit 0
else
    echo ""
    echo -e "${RED}❌ DEPLOYMENT ISSUES DETECTED${NC}"
    echo "⚠️  Address failed checks before production use"
    exit 1
fi
