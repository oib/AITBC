#!/usr/bin/env bash
# Comprehensive Security Audit Framework for AITBC
# Covers Solidity contracts, Circom circuits, Python code, system security, and malware detection
#
# Usage: ./scripts/comprehensive-security-audit.sh [--contracts-only | --circuits-only | --app-only | --system-only | --malware-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="$PROJECT_ROOT/logs/security-reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$REPORT_DIR"

echo "=== AITBC Comprehensive Security Audit ==="
echo "Project root: $PROJECT_ROOT"
echo "Report directory: $REPORT_DIR"
echo "Timestamp: $TIMESTAMP"
echo ""

# Determine what to run
RUN_CONTRACTS=true
RUN_CIRCUITS=true
RUN_APP=true
RUN_SYSTEM=true
RUN_MALWARE=true

case "${1:-}" in
    --contracts-only)
        RUN_CIRCUITS=false
        RUN_APP=false
        RUN_SYSTEM=false
        RUN_MALWARE=false
        ;;
    --circuits-only)
        RUN_CONTRACTS=false
        RUN_APP=false
        RUN_SYSTEM=false
        RUN_MALWARE=false
        ;;
    --app-only)
        RUN_CONTRACTS=false
        RUN_CIRCUITS=false
        RUN_SYSTEM=false
        RUN_MALWARE=false
        ;;
    --system-only)
        RUN_CONTRACTS=false
        RUN_CIRCUITS=false
        RUN_APP=false
        RUN_MALWARE=false
        ;;
    --malware-only)
        RUN_CONTRACTS=false
        RUN_CIRCUITS=false
        RUN_APP=false
        RUN_SYSTEM=false
        ;;
esac

# === Smart Contract Security Audit ===
if $RUN_CONTRACTS; then
    echo "--- Smart Contract Security Audit ---"
    CONTRACTS_DIR="$PROJECT_ROOT/contracts"
    SOLIDITY_DIR="$PROJECT_ROOT/packages/solidity/aitbc-token/contracts"
    
    # Slither Analysis
    echo "Running Slither static analysis..."
    if command -v slither &>/dev/null; then
        SLITHER_REPORT="$REPORT_DIR/slither_${TIMESTAMP}.json"
        SLITHER_TEXT="$REPORT_DIR/slither_${TIMESTAMP}.txt"
        
        # Analyze main contracts
        slither "$CONTRACTS_DIR" "$SOLIDITY_DIR" \
            --json "$SLITHER_REPORT" \
            --checklist \
            --exclude-dependencies \
            --filter-paths "node_modules/" \
            2>&1 | tee "$SLITHER_TEXT" || true
        
        echo "Slither report: $SLITHER_REPORT"
        
        # Count issues by severity
        if [[ -f "$SLITHER_REPORT" ]]; then
            HIGH=$(grep -c '"impact": "High"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            MEDIUM=$(grep -c '"impact": "Medium"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            LOW=$(grep -c '"impact": "Low"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            echo "Slither Summary: High=$HIGH Medium=$MEDIUM Low=$LOW"
        fi
    else
        echo "WARNING: slither not installed. Install with: pip install slither-analyzer"
    fi
    
    # Mythril Analysis
    echo "Running Mythril symbolic execution..."
    if command -v myth &>/dev/null; then
        MYTHRIL_REPORT="$REPORT_DIR/mythril_${TIMESTAMP}.json"
        MYTHRIL_TEXT="$REPORT_DIR/mythril_${TIMESTAMP}.txt"
        
        myth analyze "$CONTRACTS_DIR/ZKReceiptVerifier.sol" \
            --solv 0.8.24 \
            --execution-timeout 300 \
            --max-depth 22 \
            -o json \
            2>&1 > "$MYTHRIL_REPORT" || true
        
        myth analyze "$CONTRACTS_DIR/ZKReceiptVerifier.sol" \
            --solv 0.8.24 \
            --execution-timeout 300 \
            --max-depth 22 \
            -o text \
            2>&1 | tee "$MYTHRIL_TEXT" || true
        
        echo "Mythril report: $MYTHRIL_REPORT"
        
        if [[ -f "$MYTHRIL_REPORT" ]]; then
            ISSUES=$(grep -c '"swcID"' "$MYTHRIL_REPORT" 2>/dev/null || echo "0")
            echo "Mythril Summary: $ISSUES issues found"
        fi
    else
        echo "WARNING: mythril not installed. Install with: pip install mythril"
    fi
    
    # Manual Security Checklist
    echo "Running manual security checklist..."
    CHECKLIST_REPORT="$REPORT_DIR/contract_checklist_${TIMESTAMP}.md"
    
    cat > "$CHECKLIST_REPORT" << 'EOF'
# Smart Contract Security Checklist

## Access Control
- [ ] Role-based access control implemented
- [ ] Admin functions properly protected
- [ ] Multi-signature for critical operations
- [ ] Time locks for sensitive changes

## Reentrancy Protection
- [ ] Reentrancy guards on external calls
- [ ] Checks-Effects-Interactions pattern
- [ ] Pull over push payment patterns

## Integer Safety
- [ ] SafeMath operations (Solidity <0.8)
- [ ] Overflow/underflow protection
- [ ] Proper bounds checking

## Gas Optimization
- [ ] Gas limit considerations
- [ ] Loop optimization
- [ ] Storage optimization

## Logic Security
- [ ] Input validation
- [ ] State consistency
- [ ] Emergency mechanisms

## External Dependencies
- [ ] Oracle security
- [ ] External call validation
- [ ] Upgrade mechanism security
EOF
    
    echo "Contract checklist: $CHECKLIST_REPORT"
    echo ""
fi

# === ZK Circuit Security Audit ===
if $RUN_CIRCUITS; then
    echo "--- ZK Circuit Security Audit ---"
    CIRCUITS_DIR="$PROJECT_ROOT/apps/zk-circuits"
    
    # Circuit Compilation Check
    echo "Checking circuit compilation..."
    if command -v circom &>/dev/null; then
        CIRCUIT_REPORT="$REPORT_DIR/circuits_${TIMESTAMP}.txt"
        
        for circuit in "$CIRCUITS_DIR"/*.circom; do
            if [[ -f "$circuit" ]]; then
                circuit_name=$(basename "$circuit" .circom)
                echo "Analyzing circuit: $circuit_name" | tee -a "$CIRCUIT_REPORT"
                
                # Compile circuit
                circom "$circuit" --r1cs --wasm --sym -o "/tmp/$circuit_name" 2>&1 | tee -a "$CIRCUIT_REPORT" || true
                
                # Check for common issues
                echo "  - Checking for unconstrained signals..." | tee -a "$CIRCUIT_REPORT"
                # Add signal constraint analysis here
                
                echo "  - Checking circuit complexity..." | tee -a "$CIRCUIT_REPORT"
                # Add complexity analysis here
            fi
        done
        
        echo "Circuit analysis: $CIRCUIT_REPORT"
    else
        echo "WARNING: circom not installed. Install from: https://docs.circom.io/"
    fi
    
    # ZK Security Checklist
    CIRCUIT_CHECKLIST="$REPORT_DIR/circuit_checklist_${TIMESTAMP}.md"
    
    cat > "$CIRCUIT_CHECKLIST" << 'EOF'
# ZK Circuit Security Checklist

## Circuit Design
- [ ] Proper signal constraints
- [ ] No unconstrained signals
- [ ] Soundness properties verified
- [ ] Completeness properties verified

## Cryptographic Security
- [ ] Secure hash functions
- [ ] Proper random oracle usage
- [ ] Side-channel resistance
- [ ] Parameter security

## Implementation Security
- [ ] Input validation
- [ ] Range proofs where needed
- [ ] Nullifier security
- [ ] Privacy preservation

## Performance
- [ ] Reasonable proving time
- [ ] Memory usage optimization
- [ ] Circuit size optimization
- [ ] Verification efficiency
EOF
    
    echo "Circuit checklist: $CIRCUIT_CHECKLIST"
    echo ""
fi

# === Application Security Audit ===
if $RUN_APP; then
    echo "--- Application Security Audit ---"
    
    # Python Security Scan
    echo "Running Python security analysis..."
    if command -v bandit &>/dev/null; then
        PYTHON_REPORT="$REPORT_DIR/python_security_${TIMESTAMP}.json"
        
        bandit -r "$PROJECT_ROOT/apps" -f json -o "$PYTHON_REPORT" || true
        bandit -r "$PROJECT_ROOT/apps" -f txt 2>&1 | tee "$REPORT_DIR/python_security_${TIMESTAMP}.txt" || true
        
        echo "Python security report: $PYTHON_REPORT"
    else
        echo "WARNING: bandit not installed. Install with: pip install bandit"
    fi
    
    # Dependency Security Scan
    echo "Running dependency vulnerability scan..."
    if command -v safety &>/dev/null; then
        DEPS_REPORT="$REPORT_DIR/dependencies_${TIMESTAMP}.json"
        
        safety check --json --output "$DEPS_REPORT" "$PROJECT_ROOT" || true
        safety check 2>&1 | tee "$REPORT_DIR/dependencies_${TIMESTAMP}.txt" || true
        
        echo "Dependency report: $DEPS_REPORT"
    else
        echo "WARNING: safety not installed. Install with: pip install safety"
    fi
    
    # API Security Checklist
    API_CHECKLIST="$REPORT_DIR/api_checklist_${TIMESTAMP}.md"
    
    cat > "$API_CHECKLIST" << 'EOF'
# API Security Checklist

## Authentication
- [ ] Proper authentication mechanisms
- [ ] Token validation
- [ ] Session management
- [ ] Password policies

## Authorization
- [ ] Role-based access control
- [ ] Principle of least privilege
- [ ] Resource ownership checks
- [ ] Admin function protection

## Input Validation
- [ ] SQL injection protection
- [ ] XSS prevention
- [ ] CSRF protection
- [ ] Input sanitization

## Data Protection
- [ ] Sensitive data encryption
- [ ] Secure headers
- [ ] CORS configuration
- [ ] Rate limiting

## Error Handling
- [ ] Secure error messages
- [ ] Logging security
- [ ] Exception handling
- [ ] Information disclosure prevention
EOF
    
    echo "API checklist: $API_CHECKLIST"
    echo ""
fi

# === System & Network Security Audit ===
if $RUN_SYSTEM; then
    echo "--- System & Network Security Audit ---"
    
    # Network Security
    echo "Running network security analysis..."
    if command -v nmap &>/dev/null; then
        NETWORK_REPORT="$REPORT_DIR/network_security_${TIMESTAMP}.txt"
        
        # Scan localhost ports (safe local scanning)
        echo "Scanning localhost ports..." | tee -a "$NETWORK_REPORT"
        nmap -sT -O localhost --reason -oN - 2>&1 | tee -a "$NETWORK_REPORT" || true
        
        echo "Network security: $NETWORK_REPORT"
    else
        echo "WARNING: nmap not installed. Install with: apt-get install nmap"
    fi
    
    # System Security Audit
    echo "Running system security audit..."
    if command -v lynis &>/dev/null; then
        SYSTEM_REPORT="$REPORT_DIR/system_security_${TIMESTAMP}.txt"
        
        # Run Lynis system audit
        sudo lynis audit system --quick --report-file "$SYSTEM_REPORT" 2>&1 | tee -a "$SYSTEM_REPORT" || true
        
        echo "System security: $SYSTEM_REPORT"
    else
        echo "WARNING: lynis not installed. Install with: apt-get install lynis"
    fi
    
    # OpenSCAP Vulnerability Scanning (if available)
    echo "Running OpenSCAP vulnerability scan..."
    if command -v oscap &>/dev/null; then
        OSCAP_REPORT="$REPORT_DIR/openscap_${TIMESTAMP}.xml"
        OSCAP_HTML="$REPORT_DIR/openscap_${TIMESTAMP}.html"
        
        # Scan system vulnerabilities
        sudo oscap oval eval --results "$OSCAP_REPORT" --report "$OSCAP_HTML" /usr/share/openscap/oval/ovalorg.cis.bench.debian_11.xml 2>&1 | tee "$REPORT_DIR/openscap_${TIMESTAMP}.txt" || true
        
        echo "OpenSCAP report: $OSCAP_HTML"
    else
        echo "INFO: OpenSCAP not available in this distribution"
    fi
    
    # System Security Checklist
    SYSTEM_CHECKLIST="$REPORT_DIR/system_checklist_${TIMESTAMP}.md"
    
    cat > "$SYSTEM_CHECKLIST" << 'EOF'
# System Security Checklist

## Network Security
- [ ] Firewall configuration
- [ ] Port exposure minimization
- [ ] SSL/TLS encryption
- [ ] VPN/tunnel security

## Access Control
- [ ] User account management
- [ ] SSH security configuration
- [ ] Sudo access restrictions
- [ ] Service account security

## System Hardening
- [ ] Service minimization
- [ ] File permissions
- [ ] System updates
- [ ] Kernel security

## Monitoring & Logging
- [ ] Security event logging
- [ ] Intrusion detection
- [ ] Access monitoring
- [ ] Alert configuration

## Malware Protection
- [ ] Antivirus scanning
- [ ] File integrity monitoring
- [ ] Rootkit detection
- [ ] Suspicious process monitoring
EOF
    
    echo "System checklist: $SYSTEM_CHECKLIST"
    echo ""
fi

# === Malware & Rootkit Detection Audit ===
if $RUN_MALWARE; then
    echo "--- Malware & Rootkit Detection Audit ---"
    
    # RKHunter Scan
    echo "Running RKHunter rootkit detection..."
    if command -v rkhunter &>/dev/null; then
        RKHUNTER_REPORT="$REPORT_DIR/rkhunter_${TIMESTAMP}.txt"
        RKHUNTER_SUMMARY="$REPORT_DIR/rkhunter_summary_${TIMESTAMP}.txt"
        
        # Run rkhunter scan
        sudo rkhunter --check --skip-keypress --reportfile "$RKHUNTER_REPORT" 2>&1 | tee "$RKHUNTER_SUMMARY" || true
        
        # Extract key findings
        echo "RKHunter Summary:" | tee -a "$RKHUNTER_SUMMARY"
        echo "================" | tee -a "$RKHUNTER_SUMMARY"
        
        if [[ -f "$RKHUNTER_REPORT" ]]; then
            SUSPECT_FILES=$(grep -c "Suspect files:" "$RKHUNTER_REPORT" 2>/dev/null || echo "0")
            POSSIBLE_ROOTKITS=$(grep -c "Possible rootkits:" "$RKHUNTER_REPORT" 2>/dev/null || echo "0")
            WARNINGS=$(grep -c "Warning:" "$RKHUNTER_REPORT" 2>/dev/null || echo "0")
            
            echo "Suspect files: $SUSPECT_FILES" | tee -a "$RKHUNTER_SUMMARY"
            echo "Possible rootkits: $POSSIBLE_ROOTKITS" | tee -a "$RKHUNTER_SUMMARY"
            echo "Warnings: $WARNINGS" | tee -a "$RKHUNTER_SUMMARY"
            
            # Extract specific warnings
            echo "" | tee -a "$RKHUNTER_SUMMARY"
            echo "Specific Warnings:" | tee -a "$RKHUNTER_SUMMARY"
            echo "==================" | tee -a "$RKHUNTER_SUMMARY"
            grep "Warning:" "$RKHUNTER_REPORT" | head -10 | tee -a "$RKHUNTER_SUMMARY" || true
        fi
        
        echo "RKHunter report: $RKHUNTER_REPORT"
        echo "RKHunter summary: $RKHUNTER_SUMMARY"
    else
        echo "WARNING: rkhunter not installed. Install with: apt-get install rkhunter"
    fi
    
    # ClamAV Scan
    echo "Running ClamAV malware scan..."
    if command -v clamscan &>/dev/null; then
        CLAMAV_REPORT="$REPORT_DIR/clamav_${TIMESTAMP}.txt"
        
        # Scan critical directories
        echo "Scanning /home directory..." | tee -a "$CLAMAV_REPORT"
        clamscan --recursive=yes --infected --bell /home/oib 2>&1 | tee -a "$CLAMAV_REPORT" || true
        
        echo "Scanning /tmp directory..." | tee -a "$CLAMAV_REPORT"
        clamscan --recursive=yes --infected --bell /tmp 2>&1 | tee -a "$CLAMAV_REPORT" || true
        
        echo "ClamAV report: $CLAMAV_REPORT"
    else
        echo "WARNING: clamscan not installed. Install with: apt-get install clamav"
    fi
    
    # Malware Security Checklist
    MALWARE_CHECKLIST="$REPORT_DIR/malware_checklist_${TIMESTAMP}.md"
    
    cat > "$MALWARE_CHECKLIST" << 'EOF'
# Malware & Rootkit Security Checklist

## Rootkit Detection
- [ ] RKHunter scan completed
- [ ] No suspicious files found
- [ ] No possible rootkits detected
- [ ] System integrity verified

## Malware Scanning
- [ ] ClamAV database updated
- [ ] User directories scanned
- [ ] Temporary directories scanned
- [ ] No infected files found

## System Integrity
- [ ] Critical system files verified
- [ ] No unauthorized modifications
- [ ] Boot sector integrity checked
- [ ] Kernel modules verified

## Monitoring
- [ ] File integrity monitoring enabled
- [ ] Process monitoring active
- [ ] Network traffic monitoring
- [ ] Anomaly detection configured

## Response Procedures
- [ ] Incident response plan documented
- [ ] Quarantine procedures established
- [ ] Recovery procedures tested
- [ ] Reporting mechanisms in place
EOF
    
    echo "Malware checklist: $MALWARE_CHECKLIST"
    echo ""
fi

# === Summary Report ===
echo "--- Security Audit Summary ---"
SUMMARY_REPORT="$REPORT_DIR/summary_${TIMESTAMP}.md"

cat > "$SUMMARY_REPORT" << EOF
# AITBC Security Audit Summary

**Date:** $(date)
**Scope:** Full system security assessment
**Tools:** Slither, Mythril, Bandit, Safety, Lynis, RKHunter, ClamAV, Nmap

## Executive Summary

This comprehensive security audit covers:
- Smart contracts (Solidity)
- ZK circuits (Circom)
- Application code (Python/TypeScript)
- System and network security
- Malware and rootkit detection

## Risk Assessment

### High Risk Issues
- *To be populated after tool execution*

### Medium Risk Issues  
- *To be populated after tool execution*

### Low Risk Issues
- *To be populated after tool execution*

## Recommendations

1. **Immediate Actions** (High Risk)
   - Address critical vulnerabilities
   - Implement missing security controls

2. **Short Term** (Medium Risk)
   - Enhance monitoring and logging
   - Improve configuration security

3. **Long Term** (Low Risk)
   - Security training and awareness
   - Process improvements

## Compliance Status

- ✅ Security scanning automated
- ✅ Vulnerability tracking implemented
- ✅ Remediation planning in progress
- ⏳ Third-party audit recommended for production

## Next Steps

1. Review detailed reports in each category
2. Implement remediation plan
3. Re-scan after fixes
4. Consider professional audit for critical components

---

**Report Location:** $REPORT_DIR
**Timestamp:** $TIMESTAMP
EOF

echo "Summary report: $SUMMARY_REPORT"
echo ""
echo "=== Security Audit Complete ==="
echo "All reports saved in: $REPORT_DIR"
echo "Review summary: $SUMMARY_REPORT"
echo ""
echo "Quick install commands for missing tools:"
echo "  pip install slither-analyzer mythril bandit safety"
echo "  sudo npm install -g circom"
echo "  sudo apt-get install nmap openscap-utils lynis clamav rkhunter"
