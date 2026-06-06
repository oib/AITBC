#!/bin/bash
# Production Readiness Script for AITBC
# This script performs comprehensive production readiness validation

set -e  # Exit on any error


# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "=== AITBC Production Readiness Check ==="

# Initialize counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Function to perform check
check() {
    local description=$1
    local command=$2
    local expected=$3
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -n "   Checking $description... "
    
    if eval "$command" | grep -q "$expected" 2>/dev/null; then
        echo "✅ PASS"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo "❌ FAIL"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Function to check service status
check_service() {
    local service=$1
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -n "   Checking $service status... "
    
    if systemctl is-active "$service" >/dev/null 2>&1; then
        echo "✅ PASS"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo "❌ FAIL"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Function to check endpoint
check_endpoint() {
    local url=$1
    local description=$2
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -n "   Checking $description... "
    
    if curl -s --max-time 10 "$url" >/dev/null 2>&1; then
        echo "✅ PASS"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo "❌ FAIL"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

echo "1. Service Status Checks"
check_service "aitbc-blockchain-node"
check_service "aitbc-blockchain-rpc"
check_service "redis"

echo ""
echo "2. Network Connectivity Checks"
check_endpoint "$BLOCKCHAIN_RPC/rpc/info" "RPC endpoint"
check_endpoint "$BLOCKCHAIN_RPC/rpc/head" "Blockchain head"
check_endpoint "$BLOCKCHAIN_RPC/rpc/mempool" "Mempool"

echo ""
echo "3. Blockchain Functionality Checks"
check "Blockchain height" "curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height" "^[0-9]"
check "Genesis block exists" "curl -s $BLOCKCHAIN_RPC/rpc/blocks/0" "hash"

echo ""
echo "4. Security Configuration Checks"
check "Root login disabled" "grep '^PermitRootLogin no' /etc/ssh/sshd_config" "PermitRootLogin no"
check "Password auth disabled" "grep '^PasswordAuthentication no' /etc/ssh/sshd_config" "PasswordAuthentication no"
check "Firewall active" "ufw status | grep 'Status: active'" "Status: active"

echo ""
echo "5. File System Checks"
check "Keystore directory exists" "test -d /var/lib/aitbc/keystore" ""
check "Keystore permissions" "stat -c '%a' /var/lib/aitbc/keystore" "700"
check "Config file exists" "test -f /etc/aitbc/blockchain.env" ""

echo ""
echo "6. Cross-Node Connectivity Checks"
if ssh -o ConnectTimeout=5 aitbc 'echo "SSH_OK"' >/dev/null 2>&1; then
    echo "   SSH to aitbc: ✅ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo "   SSH to aitbc: ❌ FAIL"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

if ssh aitbc 'curl -s $BLOCKCHAIN_RPC/rpc/info' >/dev/null 2>&1; then
    echo "   Remote RPC: ✅ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo "   Remote RPC: ❌ FAIL"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
echo "7. Performance Checks"
MEMORY_USAGE=$(free | awk 'NR==2{printf "%.1f", $3*100/$2}')
if (( $(echo "$MEMORY_USAGE < 80" | bc -l) )); then
    echo "   Memory usage ($MEMORY_USAGE%): ✅ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo "   Memory usage ($MEMORY_USAGE%): ❌ FAIL"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo "   Disk usage ($DISK_USAGE%): ✅ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo "   Disk usage ($DISK_USAGE%): ❌ FAIL"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
echo "8. Integration Tests"
if /opt/aitbc/tests/integration_test.sh >/dev/null 2>&1; then
    echo "   Integration tests: ✅ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo "   Integration tests: ❌ FAIL"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
echo "=== Production Readiness Results ==="
echo "Total Checks: $TOTAL_CHECKS"
echo "Passed: $PASSED_CHECKS"
echo "Failed: $FAILED_CHECKS"
echo "Success Rate: $(( PASSED_CHECKS * 100 / TOTAL_CHECKS ))%"

# Generate report
cat > /opt/aitbc/production_readiness_report.txt << EOF
AITBC Production Readiness Report
Generated: $(date)

SUMMARY:
Total Checks: $TOTAL_CHECKS
Passed: $PASSED_CHECKS
Failed: $FAILED_CHECKS
Success Rate: $(( PASSED_CHECKS * 100 / TOTAL_CHECKS ))%

RECOMMENDATIONS:
EOF

if [ $FAILED_CHECKS -eq 0 ]; then
    echo "✅ PRODUCTION READY" >> /opt/aitbc/production_readiness_report.txt
    echo "   All checks passed. System is ready for production deployment." >> /opt/aitbc/production_readiness_report.txt
    echo ""
    echo "🎉 PRODUCTION READY!"
    echo "   All $TOTAL_CHECKS checks passed successfully"
    echo "   System is ready for production deployment"
else
    echo "⚠️  NOT PRODUCTION READY" >> /opt/aitbc/production_readiness_report.txt
    echo "   $FAILED_CHECKS checks failed. Address issues before production deployment." >> /opt/aitbc/production_readiness_report.txt
    echo ""
    echo "⚠️  NOT PRODUCTION READY"
    echo "   $FAILED_CHECKS checks failed"
    echo "   Address issues before production deployment"
    echo ""
    echo "📋 Detailed report saved to /opt/aitbc/production_readiness_report.txt"
fi

echo ""
echo "9. Generating performance baseline..."
cat > /opt/aitbc/performance_baseline.txt << EOF
AITBC Performance Baseline
Generated: $(date)

SYSTEM METRICS:
- CPU Load: $(uptime | awk -F'load average:' '{print $2}')
- Memory Usage: $MEMORY_USAGE%
- Disk Usage: $DISK_USAGE%
- Uptime: $(uptime -p)

BLOCKCHAIN METRICS:
- Current Height: $(curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo "Unknown")
- Block Time: $(curl -s $BLOCKCHAIN_RPC/rpc/info | jq .genesis_params.block_time_seconds 2>/dev/null || echo "Unknown")s
- Mining Status: $(curl -s $BLOCKCHAIN_RPC/rpc/mining/status | jq .active 2>/dev/null || echo "Unknown")

NETWORK METRICS:
- RPC Response Time: $(curl -o /dev/null -s -w '%{time_total}' $BLOCKCHAIN_RPC/rpc/info)s
- SSH Connectivity: $(ssh -o ConnectTimeout=5 aitbc 'echo "OK"' 2>/dev/null || echo "Failed")

Use this baseline for future performance monitoring.
EOF

echo "   ✅ Performance baseline generated"
echo ""
echo "=== Production Readiness Check Complete ==="
