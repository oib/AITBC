#!/bin/bash
# File: /home/oib/windsurf/aitbc/scripts/validate-requirements.sh

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
        WARNINGS+=("Node.js is not installed (optional for core services)")
        return 0
    fi
    
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1)
    
    echo "Found Node.js version: $NODE_VERSION"
    
    # Check minimum version 24.0.0
    if [ "$NODE_MAJOR" -lt 24 ]; then
        WARNINGS+=("Node.js version $NODE_VERSION is below minimum requirement 24.14.0")
        return 0
    fi
    
    # Check if version is too new (beyond 24.x)
    if [ "$NODE_MAJOR" -gt 24 ]; then
        WARNINGS+=("Node.js version $NODE_VERSION is newer than tested 24.x series")
        return 0
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
            "Debian"*)
                if [ "$(echo $VERSION | cut -d'.' -f1)" -lt 13 ]; then
                    ERRORS+=("Debian version $VERSION is below minimum requirement 13")
                fi
                # Special case for Debian 13 Trixie
                if [ "$(echo $VERSION | cut -d'.' -f1)" -eq 13 ]; then
                    echo "✅ Detected Debian 13 Trixie"
                fi
                ;;
            *)
                ERRORS+=("Operating System $OS is not supported. Only Debian 13 Trixie is supported.")
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
    REQUIRED_PORTS=(8000 8001 8002 8003 8010 8011 8012 8013 8014 8015 8016)
    OCCUPIED_PORTS=()
    
    for port in "${REQUIRED_PORTS[@]}"; do
        if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
            OCCUPIED_PORTS+=($port)
        fi
    done
    
    if [ ${#OCCUPIED_PORTS[@]} -gt 0 ]; then
        WARNINGS+=("Ports ${OCCUPIED_PORTS[*]} are already in use (may be running services)")
    fi
    
    # Note: AITBC containers use incus networking with firehol on at1 host
    # This validation is for development environment only
    echo -e "${BLUE}ℹ️  Note: Production containers use incus networking with firehol on at1 host${NC}"
    
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
