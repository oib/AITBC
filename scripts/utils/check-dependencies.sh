#!/bin/bash
#
# AITBC Dependency Check Script
#
# This script verifies that all required dependencies are present and operational
# before executing AITBC operations. It checks:
# - Python virtual environment
# - Required Python packages
# - Service status
# - Network connectivity
# - Data directory permissions
#
# Usage: ./scripts/utils/check-dependencies.sh [--verbose] [--fix]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AITBC_DIR="/opt/aitbc"
VENV_DIR="$AITBC_DIR/venv"
DATA_DIR="/var/lib/aitbc"
KEYSTORE_DIR="$DATA_DIR/keystore"
CLI_PATH="$AITBC_DIR/aitbc-cli"

# Required Python packages
REQUIRED_PACKAGES=("fastapi" "click" "uvicorn" "sqlalchemy" "pydantic")

# Required services
REQUIRED_SERVICES=("aitbc-blockchain-node.service" "aitbc-blockchain-p2p.service")

# Optional services
OPTIONAL_SERVICES=("aitbc-coordinator-api.service" "aitbc-wallet.service" "aitbc-marketplace.service")

# Flags
VERBOSE=false
FIX=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE=true
            shift
            ;;
        --fix)
            FIX=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--verbose] [--fix]"
            exit 1
            ;;
    esac
done

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python_venv() {
    log_info "Checking Python virtual environment..."

    if [ ! -d "$VENV_DIR" ]; then
        log_error "Virtual environment not found at $VENV_DIR"
        if [ "$FIX" = true ]; then
            log_info "Creating virtual environment..."
            python3 -m venv "$VENV_DIR"
            log_info "Virtual environment created. Please install dependencies."
        fi
        return 1
    fi

    if [ ! -f "$VENV_DIR/bin/python" ]; then
        log_error "Python executable not found in virtual environment"
        return 1
    fi

    log_info "Virtual environment found at $VENV_DIR"
    return 0
}

check_python_packages() {
    log_info "Checking required Python packages..."

    source "$VENV_DIR/bin/activate"

    missing_packages=()
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! pip show "$package" > /dev/null 2>&1; then
            missing_packages+=("$package")
            log_error "Missing package: $package"
        else
            if [ "$VERBOSE" = true ]; then
                log_info "Found package: $package"
            fi
        fi
    done

    if [ ${#missing_packages[@]} -gt 0 ]; then
        log_error "Missing ${#missing_packages[@]} required packages: ${missing_packages[*]}"
        if [ "$FIX" = true ]; then
            log_info "Installing missing packages..."
            pip install "${missing_packages[@]}"
        fi
        return 1
    fi

    log_info "All required Python packages installed"
    deactivate
    return 0
}

check_cli() {
    log_info "Checking AITBC CLI..."

    if [ ! -f "$CLI_PATH" ]; then
        log_error "CLI not found at $CLI_PATH"
        return 1
    fi

    if [ ! -x "$CLI_PATH" ]; then
        log_error "CLI is not executable"
        if [ "$FIX" = true ]; then
            log_info "Making CLI executable..."
            chmod +x "$CLI_PATH"
        fi
        return 1
    fi

    # Test CLI
    if "$CLI_PATH" --version > /dev/null 2>&1; then
        log_info "CLI is functional"
        if [ "$VERBOSE" = true ]; then
            "$CLI_PATH" --version
        fi
        return 0
    else
        log_error "CLI failed to execute"
        return 1
    fi
}

check_services() {
    log_info "Checking required systemd services..."

    failed_services=()
    for service in "${REQUIRED_SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            if [ "$VERBOSE" = true ]; then
                log_info "Service running: $service"
            fi
        else
            log_error "Service not running: $service"
            failed_services+=("$service")
        fi
    done

    # Check optional services
    log_info "Checking optional systemd services..."
    for service in "${OPTIONAL_SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            if [ "$VERBOSE" = true ]; then
                log_info "Optional service running: $service"
            fi
        else
            log_warn "Optional service not running: $service"
        fi
    done

    if [ ${#failed_services[@]} -gt 0 ]; then
        log_error "Failed required services: ${failed_services[*]}"
        if [ "$FIX" = true ]; then
            log_info "Attempting to start failed services..."
            for service in "${failed_services[@]}"; do
                sudo systemctl start "$service"
            fi
        fi
        return 1
    fi

    log_info "All required services running"
    return 0
}

check_data_directory() {
    log_info "Checking data directory..."

    if [ ! -d "$DATA_DIR" ]; then
        log_error "Data directory not found at $DATA_DIR"
        if [ "$FIX" = true ]; then
            log_info "Creating data directory..."
            sudo mkdir -p "$DATA_DIR"
            sudo chown -R $USER:$USER "$DATA_DIR"
        fi
        return 1
    fi

    # Check CoW status (Btrfs)
    if command -v lsattr > /dev/null 2>&1; then
        cow_status=$(lsattr -d "$DATA_DIR" 2>/dev/null | awk '{print $1}')
        if [[ "$cow_status" =~ "C" ]]; then
            log_info "CoW disabled on data directory (good)"
        else
            log_warn "CoW not disabled on data directory (may cause SQLite corruption)"
            if [ "$FIX" = true ]; then
                log_info "Disabling CoW on data directory..."
                sudo chattr +C "$DATA_DIR"
            fi
        fi
    fi

    log_info "Data directory exists at $DATA_DIR"
    return 0
}

check_keystore() {
    log_info "Checking keystore directory..."

    if [ ! -d "$KEYSTORE_DIR" ]; then
        log_warn "Keystore directory not found at $KEYSTORE_DIR"
        if [ "$FIX" = true ]; then
            log_info "Creating keystore directory..."
            sudo mkdir -p "$KEYSTORE_DIR"
            sudo chown -R $USER:$USER "$KEYSTORE_DIR"
        fi
        return 1
    fi

    log_info "Keystore directory exists at $KEYSTORE_DIR"
    return 0
}

check_network_ports() {
    log_info "Checking network ports..."

    ports=("8006" "8203" "8102" "8015")

    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":$port "; then
            if [ "$VERBOSE" = true ]; then
                log_info "Port $port is listening"
            fi
        else
            log_warn "Port $port is not listening"
        fi
    done

    return 0
}

check_health_endpoints() {
    log_info "Checking service health endpoints..."

    endpoints=(
        "http://localhost:8006/health"
        "http://localhost:8203/health"
        "http://localhost:8102/health"
        "http://localhost:8015/health"
    )

    for endpoint in "${endpoints[@]}"; do
        if curl -s -f "$endpoint" > /dev/null 2>&1; then
            if [ "$VERBOSE" = true ]; then
                log_info "Health endpoint OK: $endpoint"
            fi
        else
            log_warn "Health endpoint failed: $endpoint"
        fi
    done

    return 0
}

# Main execution
main() {
    echo "======================================"
    echo "AITBC Dependency Check"
    echo "======================================"
    echo ""

    exit_code=0

    check_python_venv || exit_code=1
    check_python_packages || exit_code=1
    check_cli || exit_code=1
    check_services || exit_code=1
    check_data_directory || exit_code=1
    check_keystore || exit_code=1
    check_network_ports || exit_code=0  # Non-critical
    check_health_endpoints || exit_code=0  # Non-critical

    echo ""
    echo "======================================"
    if [ $exit_code -eq 0 ]; then
        log_info "All critical dependencies satisfied"
    else
        log_error "Some dependencies are missing or misconfigured"
        log_info "Run with --fix to attempt automatic resolution"
    fi
    echo "======================================"

    exit $exit_code
}

main
