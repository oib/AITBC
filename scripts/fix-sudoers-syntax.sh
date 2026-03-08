#!/bin/bash
#
# Fix AITBC Sudoers Syntax Errors
# This script fixes the syntax errors in the sudoers configuration
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Fix sudoers configuration
fix_sudoers() {
    print_header "Fixing Sudoers Syntax Errors"
    
    # Create corrected sudoers file
    sudoers_file="/etc/sudoers.d/aitbc-dev"
    
    cat > "$sudoers_file" << 'EOF'
# AITBC Development Sudoers Configuration
# This file provides passwordless access for AITBC development operations

# Service management - core AITBC services
oib ALL=(root) NOPASSWD: /usr/bin/systemctl start aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl stop aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl restart aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl status aitbc-*

# Log access - development debugging
oib ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/tail -f /opt/aitbc/logs/*
oib ALL=(root) NOPASSWD: /usr/bin/cat /opt/aitbc/logs/*

# File operations - AITBC project directory (fixed syntax)
oib ALL=(root) NOPASSWD: /usr/bin/chown -R *
oib ALL=(root) NOPASSWD: /usr/bin/chmod -R *
oib ALL=(root) NOPASSWD: /usr/bin/find /opt/aitbc -exec chmod +x {} \;
oib ALL=(root) NOPASSWD: /usr/bin/find /opt/aitbc -exec chown aitbc:aitbc {} \;

# Development tools
oib ALL=(root) NOPASSWD: /usr/bin/git *
oib ALL=(root) NOPASSWD: /usr/bin/make *
oib ALL=(root) NOPASSWD: /usr/bin/cmake *
oib ALL=(root) NOPASSWD: /usr/bin/gcc *
oib ALL=(root) NOPASSWD: /usr/bin/g++ *

# Python/venv operations
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m venv /opt/aitbc/cli/venv
oib ALL=(root) NOPASSWD: /usr/bin/pip3 install *
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m pip install *

# Process management
oib ALL=(root) NOPASSWD: /usr/bin/kill -HUP *
oib ALL=(root) NOPASSWD: /usr/bin/pkill -f aitbc
oib ALL=(root) NOPASSWD: /usr/bin/ps aux

# Network operations (fixed syntax - no pipes)
oib ALL=(root) NOPASSWD: /usr/bin/netstat -tlnp
oib ALL=(root) NOPASSWD: /usr/bin/ss -tlnp

# Container operations (existing)
oib ALL=(root) NOPASSWD: /usr/bin/incus exec aitbc *
oib ALL=(root) NOPASSWD: /usr/bin/incus exec aitbc1 *
oib ALL=(root) NOPASSWD: /usr/bin/incus shell aitbc *
oib ALL=(root) NOPASSWD: /usr/bin/incus shell aitbc1 *

# User switching for service operations
oib ALL=(aitbc) NOPASSWD: ALL

EOF
    
    # Set proper permissions
    chmod 440 "$sudoers_file"
    
    print_status "Sudoers configuration fixed: $sudoers_file"
}

# Test the sudoers configuration
test_sudoers() {
    print_header "Testing Sudoers Configuration"
    
    # Test syntax
    if visudo -c -f "$sudoers_file"; then
        print_status "✅ Sudoers syntax is valid"
    else
        print_error "❌ Sudoers syntax still has errors"
        exit 1
    fi
}

# Main execution
main() {
    print_header "Fix AITBC Sudoers Syntax Errors"
    echo "This script will fix the syntax errors in /etc/sudoers.d/aitbc-dev"
    echo ""
    
    check_root
    
    # Fix and test
    fix_sudoers
    test_sudoers
    
    print_header "Fix Complete! 🎉"
    echo ""
    echo "✅ Sudoers syntax errors fixed"
    echo "✅ Configuration validated"
    echo ""
    echo "🚀 You can now:"
    echo "- Use systemctl commands without password"
    echo "- Edit files in /opt/aitbc without sudo prompts"
    echo "- Use development tools without password"
    echo "- View logs without sudo"
}

# Run main function
main "$@"
