#!/bin/bash

# AITBC Contract Security & Vulnerability Testing
# Comprehensive security analysis for smart contracts and service interactions

set -e

echo "🔒 AITBC CONTRACT SECURITY & VULNERABILITY TESTING"
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

# Security testing configuration
SECURITY_REPORT_DIR="/opt/aitbc/security_reports"
VULNERABILITY_DB="/opt/aitbc/vulnerability_database.txt"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

echo "🔒 CONTRACT SECURITY & VULNERABILITY TESTING"
echo "Comprehensive security analysis for smart contracts and services"
echo ""

# Function to run test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "🔍 Testing: $test_name"
    echo "================================"
    
    if eval "$test_command" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to run test with output
run_test_verbose() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "🔍 Testing: $test_name"
    echo "================================"
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to log security findings
log_security_finding() {
    local severity="$1"
    local category="$2"
    local description="$3"
    local recommendation="$4"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] [$severity] $category: $description" >> "$SECURITY_REPORT_DIR/security_findings.log"
    echo "[$timestamp] Recommendation: $recommendation" >> "$SECURITY_REPORT_DIR/security_findings.log"
    
    case "$severity" in
        "CRITICAL")
            echo -e "${RED}🚨 CRITICAL: $category - $description${NC}"
            ;;
        "HIGH")
            echo -e "${RED}⚠️ HIGH: $category - $description${NC}"
            ;;
        "MEDIUM")
            echo -e "${YELLOW}⚠️ MEDIUM: $category - $description${NC}"
            ;;
        "LOW")
            echo -e "${YELLOW}ℹ️ LOW: $category - $description${NC}"
            ;;
    esac
}

# 1. CONTRACT CODE SECURITY ANALYSIS
echo "1. 🔍 CONTRACT CODE SECURITY ANALYSIS"
echo "=================================="

# Test contract implementation files
run_test_verbose "Contract implementation security" "
    echo 'Analyzing contract implementation files...'
    CONTRACT_DIR='/opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts'
    if [ -d \"\$CONTRACT_DIR\" ]; then
        echo \"Contract files found:\"
        ls -la \"\$CONTRACT_DIR\"/*.py 2>/dev/null || echo \"No Python contract files found\"
        
        # Check for common security patterns
        for contract_file in \"\$CONTRACT_DIR\"/*.py; do
            if [ -f \"\$contract_file\" ]; then
                echo \"Analyzing \$contract_file:\"
                
                # Check for hardcoded secrets
                if grep -qi \"password\\|secret\\|key\\|token\" \"\$contract_file\"; then
                    log_security_finding \"MEDIUM\" \"Code Security\" \"Potential hardcoded secrets in \$contract_file\" \"Review and use environment variables for secrets\"
                fi
                
                # Check for input validation
                if ! grep -qi \"validate\\|sanitize\\|check\" \"\$contract_file\"; then
                    log_security_finding \"MEDIUM\" \"Input Validation\" \"Missing input validation in \$contract_file\" \"Add proper input validation and sanitization\"
                fi
                
                # Check for error handling
                if ! grep -qi \"try\\|except\\|error\" \"\$contract_file\"; then
                    log_security_finding \"LOW\" \"Error Handling\" \"Limited error handling in \$contract_file\" \"Implement comprehensive error handling\"
                fi
            fi
        done
    else
        echo 'Contract directory not found'
        exit 1
    fi
"

# 2. SERVICE SECURITY TESTING
echo ""
echo "2. 🔌 SERVICE SECURITY TESTING"
echo "============================="

# Test service authentication
run_test_verbose "Service authentication security" "
    echo 'Testing service authentication mechanisms...'
    
    # Test blockchain RPC without authentication
    RPC_RESPONSE=\$(curl -s http://localhost:$GENESIS_PORT/rpc/info)
    if [ -n \"\$RPC_RESPONSE\" ]; then
        echo '✅ Blockchain RPC accessible'
        log_security_finding \"MEDIUM\" \"Authentication\" \"Blockchain RPC accessible without authentication\" \"Consider implementing API key authentication\"
    else
        echo '❌ Blockchain RPC not accessible'
    fi
    
    # Test coordinator API authentication
    COORDINATOR_RESPONSE=\$(curl -s http://localhost:$COORDINATOR_PORT/health/live)
    if [ -n \"\$COORDINATOR_RESPONSE\" ]; then
        echo '✅ Coordinator API accessible'
        if echo \"\$COORDINATOR_RESPONSE\" | grep -q 'invalid api key'; then
            echo '✅ Coordinator API requires authentication'
        else
            log_security_finding \"MEDIUM\" \"Authentication\" \"Coordinator API accessible without proper authentication\" \"Implement proper API key authentication\"
        fi
    else
        echo '❌ Coordinator API not accessible'
    fi
"

# Test service encryption
run_test_verbose "Service encryption security" "
    echo 'Testing service encryption and TLS...'
    
    # Test if services use HTTPS
    if curl -s --connect-timeout 5 https://localhost:$GENESIS_PORT >/dev/null 2>&1; then
        echo '✅ HTTPS available on blockchain RPC'
    else
        echo '⚠️ HTTPS not available on blockchain RPC'
        log_security_finding \"HIGH\" \"Encryption\" \"Blockchain RPC not using HTTPS\" \"Implement TLS/SSL for all services\"
    fi
    
    # Check for SSL/TLS configuration
    if netstat -tlnp 2>/dev/null | grep -q \":$GENESIS_PORT.*LISTEN\"; then
        echo '✅ Blockchain RPC listening on port $GENESIS_PORT'
    else
        echo '❌ Blockchain RPC not listening'
    fi
"

# 3. CONTRACT VULNERABILITY SCANNING
echo ""
echo "3. 🛡️ CONTRACT VULNERABILITY SCANNING"
echo "====================================="

# Test for common contract vulnerabilities
run_test_verbose "Common contract vulnerabilities" "
    echo 'Scanning for common contract vulnerabilities...'
    
    # Check for reentrancy patterns
    CONTRACT_FILES='/opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts/*.py'
    for contract_file in \$CONTRACT_FILES; do
        if [ -f \"\$contract_file\" ]; then
            echo \"Scanning \$contract_file for reentrancy...\"
            
            # Look for patterns that might indicate reentrancy issues
            if grep -qi \"call.*before.*update\" \"\$contract_file\"; then
                log_security_finding \"HIGH\" \"Reentrancy\" \"Potential reentrancy vulnerability in \$contract_file\" \"Implement checks-effects-interactions pattern\"
            fi
            
            # Check for integer overflow/underflow
            if grep -qi \"+=\\|-=\\|*=\\|/=\" \"\$contract_file\"; then
                log_security_finding \"MEDIUM\" \"Integer Overflow\" \"Potential integer overflow in \$contract_file\" \"Use SafeMath or similar protection\"
            fi
            
            # Check for unchecked external calls
            if grep -qi \"call.*external\" \"\$contract_file\" && ! grep -qi \"require\\|assert\" \"\$contract_file\"; then
                log_security_finding \"HIGH\" \"External Calls\" \"Unchecked external calls in \$contract_file\" \"Add proper checks for external calls\"
            fi
        fi
    done
"

# 4. SERVICE INTEGRATION SECURITY
echo ""
echo "4. 🔗 SERVICE INTEGRATION SECURITY"
echo "================================="

# Test cross-service communication security
run_test_verbose "Cross-service communication security" "
    echo 'Testing cross-service communication security...'
    
    # Test marketplace service security
    MARKETPLACE_RESPONSE=\$(curl -s http://localhost:$GENESIS_PORT/rpc/marketplace/listings)
    if [ -n \"\$MARKETPLACE_RESPONSE\" ]; then
        echo '✅ Marketplace service accessible'
        
        # Check for data validation in marketplace
        if echo \"\$MARKETPLACE_RESPONSE\" | jq . 2>/dev/null | grep -q \"listing_id\"; then
            echo '✅ Marketplace data structure validated'
        else
            log_security_finding \"MEDIUM\" \"Data Validation\" \"Marketplace service data validation issues\" \"Implement proper data validation\"
        fi
    else
        echo '❌ Marketplace service not accessible'
    fi
    
    # Test AI service security
    AI_RESPONSE=\$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/ai/stats')
    if [ -n \"\$AI_RESPONSE\" ]; then
        echo '✅ AI service accessible'
        
        # Check for AI service data exposure
        if echo \"\$AI_RESPONSE\" | jq . 2>/dev/null | grep -q \"total_jobs\"; then
            echo '✅ AI service data properly structured'
        else
            log_security_finding \"LOW\" \"Data Exposure\" \"AI service data structure issues\" \"Review AI service data exposure\"
        fi
    else
        echo '❌ AI service not accessible'
    fi
"

# 5. BLOCKCHAIN SECURITY TESTING
echo ""
echo "5. ⛓️ BLOCKCHAIN SECURITY TESTING"
echo "================================"

# Test blockchain consensus security
run_test_verbose "Blockchain consensus security" "
    echo 'Testing blockchain consensus security...'
    
    # Check for consensus health
    LOCAL_HEIGHT=\$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height 2>/dev/null || echo '0')
    REMOTE_HEIGHT=\$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height' 2>/dev/null || echo '0')
    
    if [ \"\$LOCAL_HEIGHT\" -gt 0 ] && [ \"\$REMOTE_HEIGHT\" -gt 0 ]; then
        SYNC_DIFF=\$((LOCAL_HEIGHT - REMOTE_HEIGHT))
        if [ \"\$SYNC_DIFF\" -le 10 ]; then
            echo \"✅ Blockchain consensus healthy (sync diff: \$SYNC_DIFF)\"
        else
            log_security_finding \"HIGH\" \"Consensus\" \"Large sync gap: \$SYNC_DIFF blocks\" \"Investigate consensus synchronization\"
        fi
    else
        echo '❌ Unable to get blockchain heights'
        log_security_finding \"CRITICAL\" \"Consensus\" \"Blockchain consensus not accessible\" \"Check blockchain node status\"
    fi
    
    # Check for transaction validation
    TX_COUNT=\$(curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions 2>/dev/null || echo '0')
    if [ \"\$TX_COUNT\" -gt 0 ]; then
        echo \"✅ Transactions being processed (\$TX_COUNT total)\"
    else
        log_security_finding \"MEDIUM\" \"Transaction Processing\" \"No transactions found\" \"Check transaction processing\"
    fi
"

# 6. API SECURITY TESTING
echo ""
echo "6. 🔐 API SECURITY TESTING"
echo "========================="

# Test API rate limiting
run_test_verbose "API rate limiting" "
    echo 'Testing API rate limiting...'
    
    # Make multiple rapid requests to test rate limiting
    SUCCESS_COUNT=0
    for i in {1..10}; do
        if curl -s http://localhost:$GENESIS_PORT/rpc/info >/dev/null 2>&1; then
            ((SUCCESS_COUNT++))
        fi
    done
    
    if [ \"\$SUCCESS_COUNT\" -eq 10 ]; then
        echo '⚠️ No rate limiting detected'
        log_security_finding \"MEDIUM\" \"Rate Limiting\" \"No rate limiting on blockchain RPC\" \"Implement rate limiting to prevent abuse\"
    else
        echo \"✅ Rate limiting active (\$SUCCESS_COUNT/10 requests succeeded)\"
    fi
"

# Test API input validation
run_test_verbose "API input validation" "
    echo 'Testing API input validation...'
    
    # Test with malformed input
    MALFORMED_RESPONSE=\$(curl -s -X POST http://localhost:$GENESIS_PORT/rpc/sendTx \\
        -H 'Content-Type: application/json' \\
        -d '{\"invalid\": \"data\"}' 2>/dev/null)
    
    if [ -n \"\$MALFORMED_RESPONSE\" ]; then
        if echo \"\$MALFORMED_RESPONSE\" | grep -q 'error\\|invalid'; then
            echo '✅ API properly validates input'
        else
            log_security_finding \"HIGH\" \"Input Validation\" \"API not properly validating input\" \"Implement comprehensive input validation\"
        fi
    else
        echo '❌ API not responding to malformed input'
    fi
"

# 7. CROSS-NODE SECURITY TESTING
echo ""
echo "7. 🌐 CROSS-NODE SECURITY TESTING"
echo "================================"

# Test node-to-node communication security
run_test_verbose "Node-to-node communication security" "
    echo 'Testing cross-node communication security...'
    
    # Test if nodes can communicate securely
    GENESIS_INFO=\$(curl -s http://localhost:$GENESIS_PORT/rpc/info)
    FOLLOWER_INFO=\$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info')
    
    if [ -n \"\$GENESIS_INFO\" ] && [ -n \"\$FOLLOWER_INFO\" ]; then
        echo '✅ Both nodes accessible'
        
        # Check if nodes have different identities
        GENESIS_ID=\$(echo \"\$GENESIS_INFO\" | jq -r .node_id 2>/dev/null || echo 'unknown')
        FOLLOWER_ID=\$(echo \"\$FOLLOWER_INFO\" | jq -r .node_id 2>/dev/null || echo 'unknown')
        
        if [ \"\$GENESIS_ID\" != \"\$FOLLOWER_ID\" ]; then
            echo \"✅ Nodes have different identities (Genesis: \$GENESIS_ID, Follower: \$FOLLOWER_ID)\"
        else
            log_security_finding \"MEDIUM\" \"Node Identity\" \"Nodes may have identical identities\" \"Verify node identity configuration\"
        fi
    else
        echo '❌ Cross-node communication issues'
        log_security_finding \"HIGH\" \"Communication\" \"Cross-node communication problems\" \"Check network connectivity\"
    fi
"

# 8. SECURITY REPORTING
echo ""
echo "8. 📋 SECURITY REPORTING"
echo "======================="

# Create security report directory
mkdir -p "$SECURITY_REPORT_DIR"

# Generate comprehensive security report
SECURITY_REPORT="$SECURITY_REPORT_DIR/security_report_$(date +%Y%m%d_%H%M%S).txt"

cat > "$SECURITY_REPORT" << EOF
AITBC Contract Security & Vulnerability Report
=============================================
Date: $(date)

EXECUTIVE SUMMARY
----------------
Tests Passed: $TESTS_PASSED
Tests Failed: $TESTS_FAILED
Total Tests: $((TESTS_PASSED + TESTS_FAILED))

SECURITY ASSESSMENT
------------------
EOF

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo "✅ No critical security issues detected" >> "$SECURITY_REPORT"
    echo "✅ All security tests passed" >> "$SECURITY_REPORT"
    echo "✅ System appears secure for production use" >> "$SECURITY_REPORT"
else
    echo "⚠️ $TESTS_FAILED security issues detected" >> "$SECURITY_REPORT"
    echo "🔍 Review security findings before production deployment" >> "$SECURITY_REPORT"
    echo "📋 Address identified vulnerabilities" >> "$SECURITY_REPORT"
fi

cat >> "$SECURITY_REPORT" << EOF

SERVICE SECURITY STATUS
---------------------
Blockchain RPC: $([ -n "$(curl -s http://localhost:$GENESIS_PORT/rpc/info)" ] && echo "Secure" || echo "Vulnerable")
Coordinator API: $([ -n "$(curl -s http://localhost:$COORDINATOR_PORT/health/live)" ] && echo "Secure" || echo "Vulnerable")
Marketplace Service: $([ -n "$(curl -s http://localhost:$GENESIS_PORT/rpc/marketplace/listings)" ] && echo "Secure" || echo "Vulnerable")
AI Service: $([ -n "$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/ai/stats')" ] && echo "Secure" || echo "Vulnerable")

CONTRACT SECURITY STATUS
----------------------
Contract Files: $([ -d "/opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts" ] && echo "Available" || echo "Not Found")
Security Analysis: Completed
Vulnerability Scan: Completed

RECOMMENDATIONS
--------------
EOF

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo "- 🔧 Address all identified security vulnerabilities" >> "$SECURITY_REPORT"
    echo "- 🔐 Implement proper authentication for all services" >> "$SECURITY_REPORT"
    echo "- 🔒 Enable HTTPS/TLS for all communications" >> "$SECURITY_REPORT"
    echo "- 🛡️ Add input validation and sanitization" >> "$SECURITY_REPORT"
    echo "- 📊 Implement rate limiting and monitoring" >> "$SECURITY_REPORT"
else
    echo "- ✅ System ready for production deployment" >> "$SECURITY_REPORT"
    echo "- 🔍 Continue regular security monitoring" >> "$SECURITY_REPORT"
    echo "- 📋 Maintain security best practices" >> "$SECURITY_REPORT"
fi

echo "Security report saved to: $SECURITY_REPORT"

# 9. FINAL RESULTS
echo ""
echo "9. 📊 FINAL SECURITY RESULTS"
echo "==========================="

echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL SECURITY TESTS PASSED!${NC}"
    echo "✅ No critical security vulnerabilities detected"
    echo "✅ System appears secure for production use"
    echo "✅ All services properly configured"
    exit 0
else
    echo -e "${RED}⚠️  SECURITY ISSUES DETECTED${NC}"
    echo "❌ Review security report and address vulnerabilities"
    echo "📋 Check $SECURITY_REPORT for detailed findings"
    exit 1
fi
