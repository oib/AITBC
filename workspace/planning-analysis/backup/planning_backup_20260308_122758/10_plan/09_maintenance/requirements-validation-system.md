# AITBC Requirements Validation System

## Overview

This system ensures all AITBC deployments meet the exact requirements and prevents future requirement mismatches through automated validation, version enforcement, and continuous monitoring.

## Requirements Specification

### **Strict Requirements (Non-Negotiable)**

#### **Python Requirements**
- **Minimum Version**: 3.13.5
- **Maximum Version**: 3.13.x (current series)
- **Installation Method**: System package manager or pyenv
- **Virtual Environment**: Required for all deployments
- **Package Management**: pip with requirements.txt

#### **Node.js Requirements**
- **Minimum Version**: 22.0.0
- **Maximum Version**: 22.x (current tested: v22.22.x)
- **Package Manager**: npm or yarn
- **Installation**: System package manager or nvm

#### **System Requirements**
- **Operating System**: Debian 13 Trixie
- **Architecture**: x86_64 (amd64)
- **Memory**: 8GB+ minimum, 16GB+ recommended
- **Storage**: 50GB+ available space
- **CPU**: 4+ cores recommended

#### **Network Requirements**
- **Ports**: 8000-8003 (Core Services), 8010-8016 (Enhanced Services) (must be available)
- **Firewall**: Managed by firehol on at1 host (container networking handled by incus)
- **SSL/TLS**: Required for production
- **Bandwidth**: 100Mbps+ recommended

## Requirements Validation Scripts

### **1. Pre-Deployment Validation Script**

```bash
#!/bin/bash
# File: /opt/aitbc/scripts/validate-requirements.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Validation results
VALIDATION_PASSED=true
ERRORS=()
WARNINGS=()

echo "🔍 AITBC Requirements Validation"
echo "=============================="

# Function to check Python version
check_python() {
    echo -e "\n📋 Checking Python Requirements..."
    
    if ! command -v python3 &> /dev/null; then
        ERRORS+=("Python 3 is not installed")
        return 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    PYTHON_PATCH=$(echo $PYTHON_VERSION | cut -d'.' -f3)
    
    echo "Found Python version: $PYTHON_VERSION"
    
    # Check minimum version 3.13.5
    if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MAJOR" -eq 3 -a "$PYTHON_MINOR" -lt 13 ] || [ "$PYTHON_MAJOR" -eq 3 -a "$PYTHON_MINOR" -eq 13 -a "$PYTHON_PATCH" -lt 5 ]; then
        ERRORS+=("Python version $PYTHON_VERSION is below minimum requirement 3.13.5")
        return 1
    fi
    
    # Check if version is too new (beyond 3.13.x)
    if [ "$PYTHON_MAJOR" -gt 3 ] || [ "$PYTHON_MAJOR" -eq 3 -a "$PYTHON_MINOR" -gt 13 ]; then
        WARNINGS+=("Python version $PYTHON_VERSION is newer than recommended 3.13.x series")
    fi
    
    echo -e "${GREEN}✅ Python version check passed${NC}"
    return 0
}

# Function to check Node.js version
check_nodejs() {
    echo -e "\n📋 Checking Node.js Requirements..."
    
    if ! command -v node &> /dev/null; then
        ERRORS+=("Node.js is not installed")
        return 1
    fi
    
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1)
    
    echo "Found Node.js version: $NODE_VERSION"
    
    # Check minimum version 18.0.0
    if [ "$NODE_MAJOR" -lt 18 ]; then
        ERRORS+=("Node.js version $NODE_VERSION is below minimum requirement 18.0.0")
        return 1
    fi
    
    # Check if version is too new (beyond 20.x LTS)
    if [ "$NODE_MAJOR" -gt 20 ]; then
        WARNINGS+=("Node.js version $NODE_VERSION is newer than recommended 20.x LTS series")
    fi
    
    echo -e "${GREEN}✅ Node.js version check passed${NC}"
    return 0
}

# Function to check system requirements
check_system() {
    echo -e "\n📋 Checking System Requirements..."
    
    # Check OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
        VERSION=$VERSION_ID
        echo "Operating System: $OS $VERSION"
        
        case $OS in
            "Ubuntu"*)
                if [ "$(echo $VERSION | cut -d'.' -f1)" -lt 20 ]; then
                    ERRORS+=("Ubuntu version $VERSION is below minimum requirement 20.04")
                fi
                ;;
            "Debian"*)
                if [ "$(echo $VERSION | cut -d'.' -f1)" -lt 11 ]; then
                    ERRORS+=("Debian version $VERSION is below minimum requirement 11")
                fi
                ;;
            *)
                WARNINGS+=("Operating System $OS may not be fully supported")
                ;;
        esac
    else
        ERRORS+=("Cannot determine operating system")
    fi
    
    # Check memory
    MEMORY_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    MEMORY_GB=$((MEMORY_KB / 1024 / 1024))
    echo "Available Memory: ${MEMORY_GB}GB"
    
    if [ "$MEMORY_GB" -lt 8 ]; then
        ERRORS+=("Available memory ${MEMORY_GB}GB is below minimum requirement 8GB")
    elif [ "$MEMORY_GB" -lt 16 ]; then
        WARNINGS+=("Available memory ${MEMORY_GB}GB is below recommended 16GB")
    fi
    
    # Check storage
    STORAGE_KB=$(df / | tail -1 | awk '{print $4}')
    STORAGE_GB=$((STORAGE_KB / 1024 / 1024))
    echo "Available Storage: ${STORAGE_GB}GB"
    
    if [ "$STORAGE_GB" -lt 50 ]; then
        ERRORS+=("Available storage ${STORAGE_GB}GB is below minimum requirement 50GB")
    fi
    
    # Check CPU cores
    CPU_CORES=$(nproc)
    echo "CPU Cores: $CPU_CORES"
    
    if [ "$CPU_CORES" -lt 4 ]; then
        WARNINGS+=("CPU cores $CPU_CORES is below recommended 4")
    fi
    
    echo -e "${GREEN}✅ System requirements check passed${NC}"
}

# Function to check network requirements
check_network() {
    echo -e "\n📋 Checking Network Requirements..."
    
    # Check if required ports are available
    REQUIRED_PORTS=(8000 8001 8002 8003 8004 8005 8006 8007 8008 9080 3000 8080)
    OCCUPIED_PORTS=()
    
    for port in "${REQUIRED_PORTS[@]}"; do
        if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
            OCCUPIED_PORTS+=($port)
        fi
    done
    
    if [ ${#OCCUPIED_PORTS[@]} -gt 0 ]; then
        WARNINGS+=("Ports ${OCCUPIED_PORTS[*]} are already in use")
    fi
    
    # Check firewall status
    if command -v ufw &> /dev/null; then
        UFW_STATUS=$(ufw status | head -1)
        echo "Firewall Status: $UFW_STATUS"
    fi
    
    echo -e "${GREEN}✅ Network requirements check passed${NC}"
}

# Function to check required packages
check_packages() {
    echo -e "\n📋 Checking Required Packages..."
    
    REQUIRED_PACKAGES=("sqlite3" "git" "curl" "wget")
    MISSING_PACKAGES=()
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! command -v $package &> /dev/null; then
            MISSING_PACKAGES+=($package)
        fi
    done
    
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        ERRORS+=("Missing required packages: ${MISSING_PACKAGES[*]}")
    fi
    
    echo -e "${GREEN}✅ Package requirements check passed${NC}"
}

# Run all checks
check_python
check_nodejs
check_system
check_network
check_packages

# Display results
echo -e "\n📊 Validation Results"
echo "===================="

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo -e "${RED}❌ VALIDATION FAILED${NC}"
    echo -e "${RED}Errors:${NC}"
    for error in "${ERRORS[@]}"; do
        echo -e "  ${RED}• $error${NC}"
    done
    VALIDATION_PASSED=false
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  WARNINGS:${NC}"
    for warning in "${WARNINGS[@]}"; do
        echo -e "  ${YELLOW}• $warning${NC}"
    done
fi

if [ "$VALIDATION_PASSED" = true ]; then
    echo -e "${GREEN}✅ ALL REQUIREMENTS VALIDATED SUCCESSFULLY${NC}"
    echo -e "${GREEN}Ready for AITBC deployment!${NC}"
    exit 0
else
    echo -e "${RED}❌ Please fix the above errors before proceeding with deployment${NC}"
    exit 1
fi
```

### **2. Requirements Configuration File**

```yaml
# File: /opt/aitbc/config/requirements.yaml

requirements:
  python:
    minimum_version: "3.13.5"
    maximum_version: "3.13.99"
    required_packages:
      - "fastapi>=0.111.0"
      - "uvicorn[standard]>=0.30.0"
      - "sqlalchemy>=2.0.30"
      - "aiosqlite>=0.20.0"
      - "sqlmodel>=0.0.16"
      - "pydantic>=2.7.0"
      - "pydantic-settings>=2.2.1"
      - "httpx>=0.24.0"
      - "aiofiles>=23.0.0"
      - "python-jose[cryptography]>=3.3.0"
      - "passlib[bcrypt]>=1.7.4"
      - "prometheus-client>=0.16.0"
      - "slowapi>=0.1.9"
      - "websockets>=11.0"
      - "numpy>=1.26.0"
  
  nodejs:
    minimum_version: "22.0.0"
    maximum_version: "22.99.99"
    current_tested: "v22.22.x"
    required_packages:
      - "npm>=8.0.0"
  
  system:
    operating_systems:
      - "Debian 13 Trixie"
    architecture: "x86_64"
    minimum_memory_gb: 8
    recommended_memory_gb: 16
    minimum_storage_gb: 50
    recommended_cpu_cores: 4
  
  network:
    required_ports:
      # Core Services (8000+)
      - 8000  # Coordinator API
      - 8001  # Exchange API
      - 8002  # Blockchain Node
      - 8003  # Blockchain RPC
      
      # Enhanced Services (8010+)
      - 8010  # Multimodal GPU
      - 8011  # GPU Multimodal
      - 8012  # Modality Optimization
      - 8013  # Adaptive Learning
      - 8014  # Marketplace Enhanced
      - 8015  # OpenClaw Enhanced
      - 8016  # Web UI
    firewall_managed_by: "firehol on at1 host"
    container_networking: "incus"
    ssl_required: true
    minimum_bandwidth_mbps: 100

validation:
  strict_mode: true
  fail_on_warnings: false
  auto_fix_packages: false
  generate_report: true
```

### **3. Continuous Monitoring Script**

```bash
#!/bin/bash
# File: /opt/aitbc/scripts/monitor-requirements.sh

set -e

CONFIG_FILE="/opt/aitbc/config/requirements.yaml"
LOG_FILE="/opt/aitbc/logs/requirements-monitor.log"
ALERT_THRESHOLD=3

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Function to check Python version continuously
monitor_python() {
    CURRENT_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2)
    MINIMUM_VERSION="3.13.5"
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 13, 5) else 1)" 2>/dev/null; then
        log_message "ERROR: Python version $CURRENT_VERSION is below minimum requirement $MINIMUM_VERSION"
        return 1
    fi
    
    log_message "INFO: Python version $CURRENT_VERSION meets requirements"
    return 0
}

# Function to check service health
monitor_services() {
    FAILED_SERVICES=()
    
    # Check critical services
    CRITICAL_SERVICES=("aitbc-coordinator-api" "aitbc-exchange-api" "aitbc-blockchain-node-1")
    
    for service in "${CRITICAL_SERVICES[@]}"; do
        if ! systemctl is-active --quiet "$service.service"; then
            FAILED_SERVICES+=("$service")
        fi
    done
    
    if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
        log_message "ERROR: Failed services: ${FAILED_SERVICES[*]}"
        return 1
    fi
    
    log_message "INFO: All critical services are running"
    return 0
}

# Function to check system resources
monitor_resources() {
    # Check memory usage
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [ "$MEMORY_USAGE" -gt 90 ]; then
        log_message "WARNING: Memory usage is ${MEMORY_USAGE}%"
    fi
    
    # Check disk usage
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$DISK_USAGE" -gt 85 ]; then
        log_message "WARNING: Disk usage is ${DISK_USAGE}%"
    fi
    
    # Check CPU load
    CPU_LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    if (( $(echo "$CPU_LOAD > 2.0" | bc -l) )); then
        log_message "WARNING: CPU load is ${CPU_LOAD}"
    fi
    
    log_message "INFO: Resource usage - Memory: ${MEMORY_USAGE}%, Disk: ${DISK_USAGE}%, CPU: ${CPU_LOAD}"
}

# Run monitoring checks
log_message "INFO: Starting requirements monitoring"

monitor_python
monitor_services  
monitor_resources

log_message "INFO: Requirements monitoring completed"

# Check if alerts should be sent
ERROR_COUNT=$(grep -c "ERROR" "$LOG_FILE" | tail -1)
if [ "$ERROR_COUNT" -gt "$ALERT_THRESHOLD" ]; then
    log_message "ALERT: Error count ($ERROR_COUNT) exceeds threshold ($ALERT_THRESHOLD)"
    # Here you could add alert notification logic
fi
```

### **4. Pre-Commit Hook for Requirements**

```bash
#!/bin/bash
# File: .git/hooks/pre-commit-requirements

# Check if requirements files have been modified
if git diff --cached --name-only | grep -E "(requirements\.txt|pyproject\.toml|requirements\.yaml)"; then
    echo "🔍 Requirements files modified, running validation..."
    
    # Run requirements validation
    if /opt/aitbc/scripts/validate-requirements.sh; then
        echo "✅ Requirements validation passed"
    else
        echo "❌ Requirements validation failed"
        echo "Please fix requirement issues before committing"
        exit 1
    fi
fi

# Check Python version compatibility
if git diff --cached --name-only | grep -E ".*\.py$"; then
    echo "🔍 Checking Python version compatibility..."
    
    # Ensure current Python version meets requirements
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 13, 5) else 1)"; then
        echo "❌ Current Python version does not meet minimum requirement 3.13.5"
        exit 1
    fi
    
    echo "✅ Python version compatibility confirmed"
fi

exit 0
```

### **5. CI/CD Pipeline Validation**

```yaml
# File: .github/workflows/requirements-validation.yml

name: Requirements Validation

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  validate-requirements:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v3
    
    - name: Set up Python 3.13.5
      uses: actions/setup-python@v4
      with:
        python-version: "3.13.5"
    
    - name: Set up Node.js 18
      uses: actions/setup-node@v3
      with:
        node-version: "18"
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run requirements validation
      run: |
        chmod +x scripts/validate-requirements.sh
        ./scripts/validate-requirements.sh
    
    - name: Check Python version in code
      run: |
        # Check for hardcoded Python versions
        if grep -r "python3\.1[0-2]" --include="*.py" --include="*.sh" --include="*.md" .; then
          echo "❌ Found Python versions below 3.13 in code"
          exit 1
        fi
        
        if grep -r "python.*3\.[0-9][0-9]" --include="*.py" --include="*.sh" --include="*.md" . | grep -v "3\.13"; then
          echo "❌ Found unsupported Python versions in code"
          exit 1
        fi
        
        echo "✅ Python version checks passed"
    
    - name: Validate documentation requirements
      run: |
        # Check if documentation mentions correct Python version
        if ! grep -q "3\.13\.5" docs/10_plan/aitbc.md; then
          echo "❌ Documentation does not specify Python 3.13.5 requirement"
          exit 1
        fi
        
        echo "✅ Documentation requirements validated"
```

## Implementation Steps

### **1. Install Validation System**

```bash
# Make validation scripts executable
chmod +x /opt/aitbc/scripts/validate-requirements.sh
chmod +x /opt/aitbc/scripts/monitor-requirements.sh

# Install pre-commit hook
cp /opt/aitbc/scripts/pre-commit-requirements .git/hooks/pre-commit-requirements
chmod +x .git/hooks/pre-commit-requirements

# Set up monitoring cron job
echo "*/5 * * * * /opt/aitbc/scripts/monitor-requirements.sh" | crontab -
```

### **2. Update All Documentation**

```bash
# Update all documentation to specify Python 3.13.5
find docs/ -name "*.md" -exec sed -i 's/python.*3\.[0-9][0-9]/python 3.13.5+/g' {} \;
find docs/ -name "*.md" -exec sed -i 's/Python.*3\.[0-9][0-9]/Python 3.13.5+/g' {} \;
```

### **3. Update Service Files**

```bash
# Update all systemd service files to check Python version
find /etc/systemd/system/aitbc-*.service -exec sed -i 's/python3 --version/python3 -c \"import sys; exit(0 if sys.version_info >= (3, 13, 5) else 1)\" || (echo \"Python 3.13.5+ required\" && exit 1)/g' {} \;
```

## Prevention Strategies

### **1. Automated Validation**
- Pre-deployment validation script
- Continuous monitoring
- CI/CD pipeline checks
- Pre-commit hooks

### **2. Documentation Synchronization**
- Single source of truth for requirements
- Automated documentation updates
- Version-controlled requirements specification
- Cross-reference validation

### **3. Development Environment Enforcement**
- Development container with Python 3.13.5
- Local validation scripts
- IDE configuration checks
- Automated testing in correct environment

### **4. Deployment Gates**
- Requirements validation before deployment
- Environment-specific checks
- Rollback procedures for version mismatches
- Monitoring and alerting

## Maintenance Procedures

### **Weekly**
- Run requirements validation
- Update requirements specification
- Review monitoring logs
- Update documentation as needed

### **Monthly**
- Review and update minimum versions
- Test validation scripts
- Update CI/CD pipeline
- Review security patches

### **Quarterly**
- Major version compatibility testing
- Requirements specification review
- Documentation audit
- Performance impact assessment

---

**Version**: 1.0  
**Last Updated**: 2026-03-04  
**Maintainer**: AITBC Development Team
