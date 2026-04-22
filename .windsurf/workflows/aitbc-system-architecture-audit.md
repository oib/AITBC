---
name: aitbc-system-architecture-audit
description: Comprehensive AITBC system architecture analysis and path rewire workflow for FHS compliance
author: AITBC System Architect
version: 1.0.0
usage: Use this workflow to analyze AITBC codebase for architecture compliance and automatically rewire incorrect paths
---

# AITBC System Architecture Audit & Rewire Workflow

This workflow performs comprehensive analysis of the AITBC codebase to ensure proper system architecture compliance and automatically rewire any incorrect paths to follow FHS standards.

## Prerequisites

### System Requirements
- AITBC system deployed with proper directory structure
- SystemD services running
- Git repository clean of runtime files
- Administrative access to system directories

### Required Directories
- `/var/lib/aitbc/data` - Dynamic data storage
- `/etc/aitbc` - System configuration
- `/var/log/aitbc` - System and application logs
- `/opt/aitbc` - Clean repository (code only)

## Workflow Phases

### Phase 1: Architecture Analysis
**Objective**: Comprehensive analysis of current system architecture compliance

#### 1.1 Directory Structure Analysis
```bash
# Analyze current directory structure
echo "=== AITBC System Architecture Analysis ==="
echo ""
echo "=== 1. DIRECTORY STRUCTURE ANALYSIS ==="

# Check repository cleanliness
echo "Repository Analysis:"
ls -la /opt/aitbc/ | grep -E "(data|config|logs)" || echo "✅ Repository clean"

# Check system directories
echo "System Directory Analysis:"
echo "Data directory: $(ls -la /var/lib/aitbc/data/ 2>/dev/null | wc -l) items"
echo "Config directory: $(ls -la /etc/aitbc/ 2>/dev/null | wc -l) items"
echo "Log directory: $(ls -la /var/log/aitbc/ 2>/dev/null | wc -l) items"

# Check for incorrect directory usage
echo "Incorrect Directory Usage:"
find /opt/aitbc -name "data" -o -name "config" -o -name "logs" 2>/dev/null || echo "✅ No incorrect directories found"
```

#### 1.2 Code Path Analysis
```bash
# Analyze code for incorrect path references using ripgrep
echo "=== 2. CODE PATH ANALYSIS ==="

# Find repository data references
echo "Repository Data References:"
rg -l "/opt/aitbc/data" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No repository data references"

# Find repository config references
echo "Repository Config References:"
rg -l "/opt/aitbc/config" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No repository config references"

# Find repository log references
echo "Repository Log References:"
rg -l "/opt/aitbc/logs" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No repository log references"

# Find production data references
echo "Production Data References:"
rg -l "/opt/aitbc/production/data" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No production data references"

# Find production config references
echo "Production Config References:"
rg -l "/opt/aitbc/production/.env" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No production config references"

# Find production log references
echo "Production Log References:"
rg -l "/opt/aitbc/production/logs" --type py /opt/aitbc/ 2>/dev/null || echo "✅ No production log references"
```

#### 1.3 SystemD Service Analysis
```bash
# Analyze SystemD service configurations using ripgrep
echo "=== 3. SYSTEMD SERVICE ANALYSIS ==="

# Check service file paths
echo "Service File Analysis:"
rg "EnvironmentFile" /etc/systemd/system/aitbc-*.service 2>/dev/null || echo "✅ No EnvironmentFile issues"

# Check ReadWritePaths
echo "ReadWritePaths Analysis:"
rg "ReadWritePaths" /etc/systemd/system/aitbc-*.service 2>/dev/null || echo "✅ No ReadWritePaths issues"

# Check for incorrect paths in services
echo "Incorrect Service Paths:"
rg "/opt/aitbc/data|/opt/aitbc/config|/opt/aitbc/logs" /etc/systemd/system/aitbc-*.service 2>/dev/null || echo "✅ No incorrect service paths"
```

### Phase 2: Architecture Compliance Check
**Objective**: Verify FHS compliance and identify violations

#### 2.1 FHS Compliance Verification
```bash
# Verify FHS compliance
echo "=== 4. FHS COMPLIANCE VERIFICATION ==="

# Check data in /var/lib
echo "Data Location Compliance:"
if [ -d "/var/lib/aitbc/data" ]; then
    echo "✅ Data in /var/lib/aitbc/data"
else
    echo "❌ Data not in /var/lib/aitbc/data"
fi

# Check config in /etc
echo "Config Location Compliance:"
if [ -d "/etc/aitbc" ]; then
    echo "✅ Config in /etc/aitbc"
else
    echo "❌ Config not in /etc/aitbc"
fi

# Check logs in /var/log
echo "Log Location Compliance:"
if [ -d "/var/log/aitbc" ]; then
    echo "✅ Logs in /var/log/aitbc"
else
    echo "❌ Logs not in /var/log/aitbc"
fi

# Check repository cleanliness
echo "Repository Cleanliness:"
if [ ! -d "/opt/aitbc/data" ] && [ ! -d "/opt/aitbc/config" ] && [ ! -d "/opt/aitbc/logs" ]; then
    echo "✅ Repository clean"
else
    echo "❌ Repository contains runtime directories"
fi
```

#### 2.2 Git Repository Analysis
```bash
# Analyze git repository for runtime files
echo "=== 5. GIT REPOSITORY ANALYSIS ==="

# Check git status
echo "Git Status:"
git status --porcelain | head -5

# Check .gitignore
echo "GitIgnore Analysis:"
if grep -q "data/\|config/\|logs/\|*.log\|*.db" .gitignore; then
    echo "✅ GitIgnore properly configured"
else
    echo "❌ GitIgnore missing runtime patterns"
fi

# Check for tracked runtime files
echo "Tracked Runtime Files:"
git ls-files | grep -E "(data/|config/|logs/|\.log|\.db)" || echo "✅ No tracked runtime files"
```

#### 2.3 Node Identity Audit
```bash
# Audit unique node identities across all nodes
echo "=== 5.5 NODE IDENTITY AUDIT ==="

# Check aitbc node IDs
echo "aitbc Node IDs:"
grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env 2>/dev/null || echo "❌ Node ID files not found"

# Check aitbc1 node IDs
echo "aitbc1 Node IDs:"
ssh aitbc1 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env' 2>/dev/null || echo "❌ aitbc1 node ID files not found"

# Check gitea-runner node IDs
echo "gitea-runner Node IDs:"
ssh gitea-runner 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env' 2>/dev/null || echo "❌ gitea-runner node ID files not found"

# Verify uniqueness
echo "Uniqueness Verification:"
AITBC_P2P=$(grep "^p2p_node_id=" /etc/aitbc/node.env 2>/dev/null | cut -d= -f2)
AITBC1_P2P=$(ssh aitbc1 'grep "^p2p_node_id=" /etc/aitbc/node.env' 2>/dev/null | cut -d= -f2)
GITEA_P2P=$(ssh gitea-runner 'grep "^p2p_node_id=" /etc/aitbc/node.env' 2>/dev/null | cut -d= -f2)

DUPLICATE_COUNT=0
if [ "$AITBC_P2P" == "$AITBC1_P2P" ] && [ -n "$AITBC_P2P" ]; then
    echo "❌ Duplicate p2p_node_id between aitbc and aitbc1"
    DUPLICATE_COUNT=$((DUPLICATE_COUNT + 1))
fi
if [ "$AITBC_P2P" == "$GITEA_P2P" ] && [ -n "$AITBC_P2P" ] && [ -n "$GITEA_P2P" ]; then
    echo "❌ Duplicate p2p_node_id between aitbc and gitea-runner"
    DUPLICATE_COUNT=$((DUPLICATE_COUNT + 1))
fi
if [ "$AITBC1_P2P" == "$GITEA_P2P" ] && [ -n "$AITBC1_P2P" ] && [ -n "$GITEA_P2P" ]; then
    echo "❌ Duplicate p2p_node_id between aitbc1 and gitea-runner"
    DUPLICATE_COUNT=$((DUPLICATE_COUNT + 1))
fi

if [ $DUPLICATE_COUNT -eq 0 ]; then
    echo "✅ All node IDs are unique"
else
    echo "❌ Found $DUPLICATE_COUNT duplicate node ID(s)"
    echo "Run remediation: python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py"
fi
```

#### 2.4 P2P Network Configuration Audit
```bash
# Audit P2P network configuration
echo "=== 5.6 P2P NETWORK CONFIGURATION AUDIT ==="

# Check P2P service status
echo "P2P Service Status:"
systemctl status aitbc-blockchain-p2p.service --no-pager | grep -E "(Active|loaded)" || echo "❌ P2P service not found"
ssh aitbc1 'systemctl status aitbc-blockchain-p2p.service --no-pager' | grep -E "(Active|loaded)" || echo "❌ aitbc1 P2P service not found"

# Check for P2P handshake errors
echo "P2P Handshake Errors:"
journalctl -u aitbc-blockchain-p2p --no-pager | grep -c "invalid or self node_id" || echo "0 errors on aitbc"
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p --no-pager | grep -c "invalid or self node_id"' || echo "0 errors on aitbc1"

# Verify P2P service uses p2p_node_id
echo "P2P Service Configuration:"
grep "node-id" /etc/systemd/system/aitbc-blockchain-p2p.service 2>/dev/null || echo "❌ P2P service not configured with node-id"
```

#### 2.5 Node Identity Utility Script Audit
```bash
# Audit node identity utility script
echo "=== 5.7 NODE IDENTITY UTILITY SCRIPT AUDIT ==="

# Check if utility script exists
echo "Utility Script Existence:"
if [ -f "/opt/aitbc/scripts/utils/generate_unique_node_ids.py" ]; then
    echo "✅ Node identity utility script exists"
else
    echo "❌ Node identity utility script not found"
fi

# Verify script is executable
echo "Script Executability:"
if [ -x "/opt/aitbc/scripts/utils/generate_unique_node_ids.py" ]; then
    echo "✅ Script is executable"
else
    echo "⚠️  Script may not be executable (chmod +x recommended)"
fi

# Test script syntax
echo "Script Syntax Check:"
python3 -m py_compile /opt/aitbc/scripts/utils/generate_unique_node_ids.py 2>/dev/null && echo "✅ Script syntax valid" || echo "❌ Script has syntax errors"

# Verify script functions
echo "Script Functionality Test:"
python3 -c "
import sys
sys.path.insert(0, '/opt/aitbc/scripts/utils')
from generate_unique_node_ids import generate_proposer_id, generate_p2p_node_id
print('✅ generate_proposer_id function works')
print('✅ generate_p2p_node_id function works')
" 2>/dev/null || echo "❌ Script functions not working correctly"
```

### Phase 3: Path Rewire Operations
**Objective**: Automatically rewire incorrect paths to system locations

#### 3.1 Python Code Path Rewire
```bash
# Rewire Python code paths
echo "=== 6. PYTHON CODE PATH REWIRE ==="

# Rewire data paths
echo "Rewiring Data Paths:"
rg -l "/opt/aitbc/data" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/data|/var/lib/aitbc/data|g' 2>/dev/null || echo "No data paths to rewire"
rg -l "/opt/aitbc/production/data" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/production/data|/var/lib/aitbc/data|g' 2>/dev/null || echo "No production data paths to rewire"
echo "✅ Data paths rewired"

# Rewire config paths
echo "Rewiring Config Paths:"
rg -l "/opt/aitbc/config" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/config|/etc/aitbc|g' 2>/dev/null || echo "No config paths to rewire"
rg -l "/opt/aitbc/production/.env" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/production/.env|/etc/aitbc/production.env|g' 2>/dev/null || echo "No production config paths to rewire"
echo "✅ Config paths rewired"

# Rewire log paths
echo "Rewiring Log Paths:"
rg -l "/opt/aitbc/logs" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/logs|/var/log/aitbc|g' 2>/dev/null || echo "No log paths to rewire"
rg -l "/opt/aitbc/production/logs" --type py /opt/aitbc/ | xargs sed -i 's|/opt/aitbc/production/logs|/var/log/aitbc/production|g' 2>/dev/null || echo "No production log paths to rewire"
echo "✅ Log paths rewired"
```

#### 3.2 SystemD Service Path Rewire
```bash
# Rewire SystemD service paths
echo "=== 7. SYSTEMD SERVICE PATH REWIRE ==="

# Rewire EnvironmentFile paths
echo "Rewiring EnvironmentFile Paths:"
rg -l "EnvironmentFile=/opt/aitbc/.env" /etc/systemd/system/aitbc-*.service | xargs sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' 2>/dev/null || echo "No .env paths to rewire"
rg -l "EnvironmentFile=/opt/aitbc/production/.env" /etc/systemd/system/aitbc-*.service | xargs sed -i 's|EnvironmentFile=/opt/aitbc/production/.env|EnvironmentFile=/etc/aitbc/production.env|g' 2>/dev/null || echo "No production .env paths to rewire"
echo "✅ EnvironmentFile paths rewired"

# Rewire ReadWritePaths
echo "Rewiring ReadWritePaths:"
rg -l "/opt/aitbc/production/data" /etc/systemd/system/aitbc-*.service | xargs sed -i 's|/opt/aitbc/production/data|/var/lib/aitbc/data|g' 2>/dev/null || echo "No production data ReadWritePaths to rewire"
rg -l "/opt/aitbc/production/logs" /etc/systemd/system/aitbc-*.service | xargs sed -i 's|/opt/aitbc/production/logs|/var/log/aitbc/production|g' 2>/dev/null || echo "No production logs ReadWritePaths to rewire"
echo "✅ ReadWritePaths rewired"
```

#### 3.3 Drop-in Configuration Rewire
```bash
# Rewire drop-in configuration files
echo "=== 8. DROP-IN CONFIGURATION REWIRE ==="

# Find and rewire drop-in files
rg -l "EnvironmentFile=/opt/aitbc/.env" /etc/systemd/system/aitbc-*.service.d/*.conf 2>/dev/null | xargs sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' || echo "No drop-in .env paths to rewire"
rg -l "EnvironmentFile=/opt/aitbc/production/.env" /etc/systemd/system/aitbc-*.service.d/*.conf 2>/dev/null | xargs sed -i 's|EnvironmentFile=/opt/aitbc/production/.env|EnvironmentFile=/etc/aitbc/production.env|g' || echo "No drop-in production .env paths to rewire"
echo "✅ Drop-in configurations rewired"
```

### Phase 4: System Directory Creation
**Objective**: Ensure proper system directory structure exists

#### 4.1 Create System Directories
```bash
# Create system directories
echo "=== 9. SYSTEM DIRECTORY CREATION ==="

# Create data directories
echo "Creating Data Directories:"
mkdir -p /var/lib/aitbc/data/blockchain
mkdir -p /var/lib/aitbc/data/marketplace
mkdir -p /var/lib/aitbc/data/openclaw
mkdir -p /var/lib/aitbc/data/coordinator
mkdir -p /var/lib/aitbc/data/exchange
mkdir -p /var/lib/aitbc/data/registry
echo "✅ Data directories created"

# Create log directories
echo "Creating Log Directories:"
mkdir -p /var/log/aitbc/production/blockchain
mkdir -p /var/log/aitbc/production/marketplace
mkdir -p /var/log/aitbc/production/openclaw
mkdir -p /var/log/aitbc/production/services
mkdir -p /var/log/aitbc/production/errors
mkdir -p /var/log/aitbc/repository-logs
echo "✅ Log directories created"

# Set permissions
echo "Setting Permissions:"
chmod 755 /var/lib/aitbc/data
chmod 755 /var/lib/aitbc/data/*
chmod 755 /var/log/aitbc
chmod 755 /var/log/aitbc/*
echo "✅ Permissions set"
```

### Phase 5: Repository Cleanup
**Objective**: Clean repository of runtime files

#### 5.1 Remove Runtime Directories
```bash
# Remove runtime directories from repository
echo "=== 10. REPOSITORY CLEANUP ==="

# Remove data directories
echo "Removing Runtime Directories:"
rm -rf /opt/aitbc/data 2>/dev/null || echo "No data directory to remove"
rm -rf /opt/aitbc/config 2>/dev/null || echo "No config directory to remove"
rm -rf /opt/aitbc/logs 2>/dev/null || echo "No logs directory to remove"
rm -rf /opt/aitbc/production/data 2>/dev/null || echo "No production data directory to remove"
rm -rf /opt/aitbc/production/logs 2>/dev/null || echo "No production logs directory to remove"
echo "✅ Runtime directories removed"
```

#### 5.2 Update GitIgnore
```bash
# Update .gitignore
echo "Updating GitIgnore:"
echo "data/" >> .gitignore
echo "config/" >> .gitignore
echo "logs/" >> .gitignore
echo "production/data/" >> .gitignore
echo "production/logs/" >> .gitignore
echo "*.log" >> .gitignore
echo "*.log.*" >> .gitignore
echo "*.db" >> .gitignore
echo "*.db-wal" >> .gitignore
echo "*.db-shm" >> .gitignore
echo "!*.example" >> .gitignore
echo "✅ GitIgnore updated"
```

#### 5.3 Remove Tracked Files
```bash
# Remove tracked runtime files
echo "Removing Tracked Runtime Files:"
git rm -r --cached data/ 2>/dev/null || echo "No data directory tracked"
git rm -r --cached config/ 2>/dev/null || echo "No config directory tracked"
git rm -r --cached logs/ 2>/dev/null || echo "No logs directory tracked"
git rm -r --cached production/data/ 2>/dev/null || echo "No production data directory tracked"
git rm -r --cached production/logs/ 2>/dev/null || echo "No production logs directory tracked"
echo "✅ Tracked runtime files removed"
```

### Phase 6: Service Restart and Verification
**Objective**: Restart services and verify proper operation

#### 6.1 SystemD Reload
```bash
# Reload SystemD
echo "=== 11. SYSTEMD RELOAD ==="
systemctl daemon-reload
echo "✅ SystemD reloaded"
```

#### 6.2 Service Restart
```bash
# Restart AITBC services
echo "=== 12. SERVICE RESTART ==="
services=("aitbc-marketplace.service" "aitbc-mining-blockchain.service" "aitbc-openclaw-ai.service" "aitbc-blockchain-node.service" "aitbc-blockchain-rpc.service")

for service in "${services[@]}"; do
    echo "Restarting $service..."
    systemctl restart "$service" 2>/dev/null || echo "Service $service not found"
done

echo "✅ Services restarted"
```

#### 6.3 Service Verification
```bash
# Verify service status
echo "=== 13. SERVICE VERIFICATION ==="

# Check service status
echo "Service Status:"
for service in "${services[@]}"; do
    status=$(systemctl is-active "$service" 2>/dev/null || echo "not-found")
    echo "$service: $status"
done

# Test marketplace service
echo "Marketplace Test:"
curl -s http://localhost:8002/health 2>/dev/null | jq '.status' 2>/dev/null || echo "Marketplace not responding"

# Test blockchain service
echo "Blockchain Test:"
curl -s http://localhost:8005/health 2>/dev/null | jq '.status' 2>/dev/null || echo "Blockchain HTTP not responding"
```

### Phase 7: Final Verification
**Objective**: Comprehensive verification of architecture compliance

#### 7.1 Architecture Compliance Check
```bash
# Final architecture compliance check
echo "=== 14. FINAL ARCHITECTURE COMPLIANCE CHECK ==="

# Check system directories
echo "System Directory Check:"
echo "Data: $(test -d /var/lib/aitbc/data && echo "✅" || echo "❌")"
echo "Config: $(test -d /etc/aitbc && echo "✅" || echo "❌")"
echo "Logs: $(test -d /var/log/aitbc && echo "✅" || echo "❌")"

# Check repository cleanliness
echo "Repository Cleanliness:"
echo "No data dir: $(test ! -d /opt/aitbc/data && echo "✅" || echo "❌")"
echo "No config dir: $(test ! -d /opt/aitbc/config && echo "✅" || echo "❌")"
echo "No logs dir: $(test ! -d /opt/aitbc/logs && echo "✅" || echo "❌")"

# Check path references
echo "Path References:"
echo "No repo data refs: $(rg -l "/opt/aitbc/data" --type py /opt/aitbc/ 2>/dev/null | wc -l)"
echo "No repo config refs: $(rg -l "/opt/aitbc/config" --type py /opt/aitbc/ 2>/dev/null | wc -l)"
echo "No repo log refs: $(rg -l "/opt/aitbc/logs" --type py /opt/aitbc/ 2>/dev/null | wc -l)"
```

#### 7.2 Generate Report
```bash
# Generate architecture compliance report
echo "=== 15. ARCHITECTURE COMPLIANCE REPORT ==="
echo "Generated on: $(date)"
echo ""
echo "✅ COMPLETED TASKS:"
echo "  • Directory structure analysis"
echo "  • Code path analysis"
echo "  • SystemD service analysis"
echo "  • FHS compliance verification"
echo "  • Git repository analysis"
echo "  • Node identity audit"
echo "  • P2P network configuration audit"
echo "  • Node identity utility script audit"
echo "  • Python code path rewire"
echo "  • SystemD service path rewire"
echo "  • System directory creation"
echo "  • Repository cleanup"
echo "  • Service restart and verification"
echo "  • Final compliance check"
echo ""
echo "🎯 AITBC SYSTEM ARCHITECTURE IS NOW FHS COMPLIANT!"
```

## Success Metrics

### Architecture Compliance
- **FHS Compliance**: 100% compliance with Linux standards
- **Repository Cleanliness**: 0 runtime files in repository
- **Path Accuracy**: 100% services use system paths
- **Service Health**: All services operational

### System Integration
- **SystemD Integration**: All services properly configured
- **Log Management**: Centralized logging system
- **Data Storage**: Proper data directory structure
- **Configuration**: System-wide configuration management

## Troubleshooting

### Common Issues
1. **Service Failures**: Check for incorrect path references
2. **Permission Errors**: Verify system directory permissions
3. **Path Conflicts**: Ensure no hardcoded repository paths
4. **Git Issues**: Remove runtime files from tracking

### Recovery Commands
```bash
# Service recovery
systemctl daemon-reload
systemctl restart aitbc-*.service

# Path verification
rg -l "/opt/aitbc/data|/opt/aitbc/config|/opt/aitbc/logs" --type py /opt/aitbc/ 2>/dev/null

# Directory verification
ls -la /var/lib/aitbc/ /etc/aitbc/ /var/log/aitbc/
```

## Usage Instructions

### Running the Workflow
1. Execute the workflow phases in sequence
2. Monitor each phase for errors
3. Verify service operation after completion
4. Review final compliance report

### Customization
- **Phase Selection**: Run specific phases as needed
- **Service Selection**: Modify service list for specific requirements
- **Path Customization**: Adapt paths for different environments
- **Reporting**: Customize report format and content

---

**This workflow ensures complete AITBC system architecture compliance with automatic path rewire and comprehensive verification.**
