#!/bin/bash
#
# Final AITBC Sudoers Fix - Simple and Working
# This script creates a clean, working sudoers configuration
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

# Create simple, working sudoers configuration
create_simple_sudoers() {
    print_header "Creating Simple Working Sudoers"
    
    # Create clean sudoers file
    sudoers_file="/etc/sudoers.d/aitbc-dev"
    
    cat > "$sudoers_file" << 'EOF'
# AITBC Development Sudoers Configuration
# Simple, working configuration without complex commands

# Service management - core AITBC services
oib ALL=(root) NOPASSWD: /usr/bin/systemctl start aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl stop aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl restart aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl status aitbc-*

# Log access - development debugging
oib ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/tail -f /opt/aitbc/logs/*
oib ALL=(root) NOPASSWD: /usr/bin/cat /opt/aitbc/logs/*

# Simple file operations - AITBC project directory
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

# Python/venv operations
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m venv /opt/aitbc/cli/venv
oib ALL=(root) NOPASSWD: /usr/bin/pip3 install *
oib ALL=(root) NOPASSWD: /usr/bin/python3 -m pip install *

# Process management
oib ALL=(root) NOPASSWD: /usr/bin/kill -HUP *
oib ALL=(root) NOPASSWD: /usr/bin/pkill -f aitbc
oib ALL=(root) NOPASSWD: /usr/bin/ps aux

# Network operations (simple, no pipes)
oib ALL=(root) NOPASSWD: /usr/bin/netstat -tlnp
oib ALL=(root) NOPASSWD: /usr/bin/ss -tlnp
oib ALL=(root) NOPASSWD: /usr/bin/lsof -i :8000
oib ALL=(root) NOPASSWD: /usr/bin/lsof -i :8006

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
    
    print_status "Simple sudoers configuration created: $sudoers_file"
}

# Test the sudoers configuration
test_sudoers() {
    print_header "Testing Sudoers Configuration"
    
    # Test syntax
    if visudo -c -f "$sudoers_file"; then
        print_status "✅ Sudoers syntax is valid"
        return 0
    else
        print_error "❌ Sudoers syntax still has errors"
        return 1
    fi
}

# Create helper scripts for complex operations
create_helper_scripts() {
    print_header "Creating Helper Scripts for Complex Operations"
    
    # Create permission fix script
    cat > "/opt/aitbc/scripts/fix-permissions.sh" << 'EOF'
#!/bin/bash
# Permission fix script - handles complex find operations
echo "🔧 Fixing AITBC permissions..."

# Set ownership
sudo chown -R oib:aitbc /opt/aitbc

# Set directory permissions
sudo find /opt/aitbc -type d -exec chmod 2775 {} \;

# Set file permissions
sudo find /opt/aitbc -type f -exec chmod 664 {} \;

# Make scripts executable
sudo find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
sudo find /opt/aitbc -name "*.py" -exec chmod +x {} \;

# Set SGID bit
sudo find /opt/aitbc -type d -exec chmod g+s {} \;

echo "✅ Permissions fixed!"
EOF
    
    # Make script executable
    chmod +x /opt/aitbc/scripts/fix-permissions.sh
    
    print_status "Helper scripts created"
}

# Main execution
main() {
    print_header "Final AITBC Sudoers Fix"
    echo "Creating simple, working sudoers configuration"
    echo ""
    
    check_root
    
    # Create simple configuration
    create_simple_sudoers
    
    # Test it
    if test_sudoers; then
        # Create helper scripts
        create_helper_scripts
        
        print_header "Success! 🎉"
        echo ""
        echo "✅ Working sudoers configuration created"
        echo "✅ Helper scripts for complex operations"
        echo ""
        echo "🚀 You can now:"
        echo "- Manage services: sudo systemctl status aitbc-coordinator-api.service"
        echo "- Edit files: touch /opt/aitbc/test.txt (no sudo needed for most ops)"
        echo "- Fix permissions: /opt/aitbc/scripts/fix-permissions.sh"
        echo "- Use dev tools: git status, make, gcc, etc."
        echo ""
        echo "💡 For complex file operations, use the helper script:"
        echo "  /opt/aitbc/scripts/fix-permissions.sh"
    else
        print_error "Failed to create valid sudoers configuration"
        exit 1
    fi
}

# Run main function
main "$@"
