#!/bin/bash

# AITBC Production Readiness Checklist
# Validates production readiness across all system components

set -e

echo "=== 🚀 AITBC PRODUCTION READINESS CHECKLIST ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
check_pass() {
    echo -e "   ${GREEN}✅ PASS${NC}: $1"
    ((PASSED++))
}

check_fail() {
    echo -e "   ${RED}❌ FAIL${NC}: $1"
    ((FAILED++))
}

check_warn() {
    echo -e "   ${YELLOW}⚠️  WARN${NC}: $1"
    ((WARNINGS++))
}

echo "1. 🔒 SECURITY VALIDATION"
echo "========================"

# Check security hardening
if [ -f "/opt/aitbc/security_summary.txt" ]; then
    check_pass "Security hardening completed"
    echo "   Security summary available at /opt/aitbc/security_summary.txt"
else
    check_fail "Security hardening not completed"
fi

# Check SSH configuration
if grep -q "PermitRootLogin yes" /etc/ssh/sshd_config 2>/dev/null; then
    check_warn "Root SSH access enabled (development mode)"
else
    check_pass "SSH access properly configured"
fi

# Check firewall status (skipped as requested)
check_warn "Firewall configuration skipped as requested"

# Check sudo configuration (skipped as requested)
check_warn "Sudo configuration skipped as requested"

echo ""
echo "2. 📊 PERFORMANCE VALIDATION"
echo "============================"

# Check service status
services=("aitbc-blockchain-node" "aitbc-blockchain-rpc")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        check_pass "$service is running"
    else
        check_fail "$service is not running"
    fi
done

# Check blockchain height
if curl -s http://localhost:8006/rpc/head >/dev/null 2>&1; then
    height=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
    if [ "$height" -gt 1000 ]; then
        check_pass "Blockchain height: $height blocks"
    else
        check_warn "Blockchain height low: $height blocks"
    fi
else
    check_fail "Blockchain RPC not responding"
fi

# Check RPC response time
start_time=$(date +%s%N)
curl -s http://localhost:8006/rpc/info >/dev/null 2>&1
end_time=$(date +%s%N)
response_time=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds

if [ "$response_time" -lt 1000 ]; then
    check_pass "RPC response time: ${response_time}ms"
else
    check_warn "RPC response time slow: ${response_time}ms"
fi

echo ""
echo "3. 🔧 RELIABILITY VALIDATION"
echo "============================"

# Check database files
if [ -f "/var/lib/aitbc/data/ait-mainnet/chain.db" ]; then
    db_size=$(stat -f%z /var/lib/aitbc/data/ait-mainnet/chain.db 2>/dev/null || stat -c%s /var/lib/aitbc/data/ait-mainnet/chain.db 2>/dev/null || echo "0")
    if [ "$db_size" -gt 1000000 ]; then
        check_pass "Database size: $((db_size / 1024 / 1024))MB"
    else
        check_warn "Database small: $((db_size / 1024))KB"
    fi
else
    check_fail "Database file not found"
fi

# Check mempool database
if [ -f "/var/lib/aitbc/data/mempool.db" ]; then
    check_pass "Mempool database exists"
else
    check_warn "Mempool database not found"
fi

# Check log rotation
if [ -d "/var/log/aitbc" ]; then
    log_count=$(find /var/log/aitbc -name "*.log" 2>/dev/null | wc -l)
    check_pass "Log directory exists with $log_count log files"
else
    check_warn "Log directory not found"
fi

echo ""
echo "4. 📋 OPERATIONS VALIDATION"
echo "==========================="

# Check monitoring setup
if [ -f "/opt/aitbc/scripts/health_check.sh" ]; then
    check_pass "Health check script exists"
else
    check_fail "Health check script missing"
fi

# Check security monitoring
if [ -f "/opt/aitbc/scripts/security_monitor.sh" ]; then
    check_pass "Security monitoring script exists"
else
    check_fail "Security monitoring script missing"
fi

# Check documentation
if [ -d "/opt/aitbc/docs" ]; then
    doc_count=$(find /opt/aitbc/docs -name "*.md" 2>/dev/null | wc -l)
    check_pass "Documentation directory exists with $doc_count documents"
else
    check_warn "Documentation directory not found"
fi

# Check backup procedures
if [ -f "/opt/aitbc/scripts/backup.sh" ]; then
    check_pass "Backup script exists"
else
    check_warn "Backup script missing"
fi

echo ""
echo "5. 🌐 NETWORK VALIDATION"
echo "========================"

# Check cross-node connectivity
if ssh aitbc "curl -s http://localhost:8006/rpc/info" >/dev/null 2>&1; then
    check_pass "Cross-node connectivity working"
else
    check_fail "Cross-node connectivity failed"
fi

# Check blockchain sync
local_height=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
remote_height=$(ssh aitbc "curl -s http://localhost:8006/rpc/head | jq -r .height" 2>/dev/null || echo "0")
height_diff=$((local_height - remote_height))

if [ ${height_diff#-} -lt 10 ]; then
    check_pass "Blockchain sync: diff $height_diff blocks"
else
    check_warn "Blockchain sync lag: diff $height_diff blocks"
fi

echo ""
echo "6. 💰 WALLET VALIDATION"
echo "======================"

# Check genesis wallet
if curl -s "http://localhost:8006/rpc/getBalance/ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r" >/dev/null 2>&1; then
    genesis_balance=$(curl -s "http://localhost:8006/rpc/getBalance/ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r" | jq -r .balance 2>/dev/null || echo "0")
    if [ "$genesis_balance" -gt 900000000 ]; then
        check_pass "Genesis wallet balance: $genesis_balance AIT"
    else
        check_warn "Genesis wallet balance low: $genesis_balance AIT"
    fi
else
    check_fail "Cannot access genesis wallet"
fi

# Check aitbc-user wallet
if ssh aitbc "cat /var/lib/aitbc/keystore/aitbc-user.json" >/dev/null 2>&1; then
    aitbc_user_addr=$(ssh aitbc "cat /var/lib/aitbc/keystore/aitbc-user.json | jq -r .address")
    if curl -s "http://localhost:8006/rpc/getBalance/$aitbc_user_addr" >/dev/null 2>&1; then
        user_balance=$(curl -s "http://localhost:8006/rpc/getBalance/$aitbc_user_addr" | jq -r .balance 2>/dev/null || echo "0")
        check_pass "AITBC-user wallet balance: $user_balance AIT"
    else
        check_fail "Cannot access AITBC-user wallet balance"
    fi
else
    check_fail "AITBC-user wallet not found"
fi

echo ""
echo "=== 📊 READINESS SUMMARY ==="
echo "PASSED: $PASSED"
echo "FAILED: $FAILED"
echo "WARNINGS: $WARNINGS"
echo ""

# Determine overall status
if [ "$FAILED" -eq 0 ]; then
    if [ "$WARNINGS" -eq 0 ]; then
        echo -e "${GREEN}🎉 PRODUCTION READY!${NC}"
        echo "All checks passed. System is ready for production deployment."
        exit 0
    else
        echo -e "${YELLOW}⚠️  PRODUCTION READY WITH WARNINGS${NC}"
        echo "System is ready but consider addressing warnings."
        exit 0
    fi
else
    echo -e "${RED}❌ NOT PRODUCTION READY${NC}"
    echo "Please address failed checks before production deployment."
    exit 1
fi
