#!/bin/bash
#
# Clean AITBC Sudoers - Only Basic Working Commands
# This creates a minimal, working sudoers configuration
#

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
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

# Create minimal working sudoers
create_clean_sudoers() {
    print_header "Creating Clean Working Sudoers"
    
    sudoers_file="/etc/sudoers.d/aitbc-dev"
    
    cat > "$sudoers_file" << 'EOF'
# AITBC Development Sudoers Configuration
# Clean, minimal, working configuration

# Service management
oib ALL=(root) NOPASSWD: /usr/bin/systemctl start aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl stop aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl restart aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl status aitbc-*

# Log access
oib ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/tail -f /opt/aitbc/logs/*
oib ALL=(root) NOPASSWD: /usr/bin/cat /opt/aitbc/logs/*

# File operations
oib ALL=(root) NOPASSWD: /usr/bin/chown -R *
oib ALL=(root) NOPASSWD: /usr/bin/chmod -R *
oib ALL=(root) NOPASSWD: /usr/bin/touch /opt/aitbc/*
oib ALL=(root) NOPASSWD: /usr/bin/mkdir -p /opt/aitbc/*
oib ALL=(root) NOPASSWD: /usr/bin/rm -rf /opt/aitbc/*

# Development tools
oib ALL=(root) NOPASSWD: /usr/bin/git *
oib ALL=(root) NOPASSWD: /usr/bin/make *
oib ALL=(root) NOPASSWD: /usr/bin/cmake *
oib ALL=(root) NOPASSWD: /usr/bin/gcc *
oib ALL=(root) NOPASSWD: /usr/bin/g++ *

# Python operations
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m venv /opt/aitbc/cli/venv
oib ALL=(root) NOPASSWD: /usr/bin/pip3 install *
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m pip install *

# Process management
oib ALL=(root) NOPASSWD: /usr/bin/kill -HUP *
oib ALL=(root) NOPASSWD: /usr/bin/pkill -f aitbc
oib ALL=(root) NOPASSWD: /usr/bin/ps aux

# Network tools (basic commands only)
oib ALL=(root) NOPASSWD: /usr/bin/netstat -tlnp
oib ALL=(root) NOPASSWD: /usr/bin/ss -tlnp
oib ALL=(root) NOPASSWD: /usr/bin/lsof

# Container operations
oib ALL=(root) NOPASSWD: /usr/bin/incus exec aitbc *
oib ALL=(root) NOPASSWD: /usr/bin/incus exec aitbc1 *
oib ALL=(root) NOPASSWD: /usr/bin/incus shell aitbc *
oib ALL=(root) NOPASSWD: /usr/bin/incus shell aitbc1 *

# User switching
oib ALL=(aitbc) NOPASSWD: ALL

EOF
    
    chmod 440 "$sudoers_file"
    print_status "Clean sudoers created: $sudoers_file"
}

# Test configuration
test_sudoers() {
    print_header "Testing Sudoers"
    
    if visudo -c -f "$sudoers_file"; then
        print_status "✅ Sudoers syntax is valid"
        return 0
    else
        print_error "❌ Sudoers syntax has errors"
        return 1
    fi
}

# Main execution
main() {
    print_header "Clean AITBC Sudoers Fix"
    echo "Creating minimal, working sudoers configuration"
    echo ""
    
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
    
    create_clean_sudoers
    
    if test_sudoers; then
        print_header "Success! 🎉"
        echo ""
        echo "✅ Clean working sudoers configuration"
        echo ""
        echo "🚀 You can now use:"
        echo "  sudo systemctl status aitbc-coordinator-api.service"
        echo "  sudo chown -R oib:aitbc /opt/aitbc"
        echo "  sudo lsof -i :8000  (with arguments after the command)"
        echo "  sudo netstat -tlnp | grep :8000  (pipe works in terminal)"
        echo "  /opt/aitbc/scripts/fix-permissions.sh  (for complex ops)"
    else
        exit 1
    fi
}

main "$@"
