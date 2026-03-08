#!/bin/bash
#
# Complete AITBC Development Permission Fix
# This script integrates AITBC development permissions with existing sudoers
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

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
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
    print_header "Fixing Sudoers Configuration"
    
    # Create comprehensive AITBC sudoers file
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

# File operations - AITBC project directory
oib ALL=(root) NOPASSWD: /usr/bin/chown -R * /opt/aitbc/*
oib ALL=(root) NOPASSWD: /usr/bin/chmod -R * /opt/aitbc/*
oib ALL=(root) NOPASSWD: /usr/bin/find /opt/aitbc/* -exec chmod * {} \;
oib ALL=(root) NOPASSWD: /usr/bin/find /opt/aitbc/* -exec chown * {} \;

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
oib ALL=(root) NOPASSWD: /usr/bin/kill -HUP *aitbc*
oib ALL=(root) NOPASSWD: /usr/bin/pkill -f aitbc
oib ALL=(root) NOPASSWD: /usr/bin/ps aux | grep aitbc

# Network operations
oib ALL=(root) NOPASSWD: /usr/bin/netstat -tlnp | grep :800*
oib ALL=(root) NOPASSWD: /usr/bin/ss -tlnp | grep :800*

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
    
    print_status "Sudoers configuration updated: $sudoers_file"
}

# Fix directory permissions completely
fix_permissions() {
    print_header "Fixing Directory Permissions"
    
    # Set proper ownership
    print_status "Setting ownership to oib:aitbc"
    chown -R oib:aitbc /opt/aitbc
    
    # Set directory permissions (2775 = rwxrwsr-x)
    print_status "Setting directory permissions to 2775"
    find /opt/aitbc -type d -exec chmod 2775 {} \;
    
    # Set file permissions (664 = rw-rw-r--)
    print_status "Setting file permissions to 664"
    find /opt/aitbc -type f -exec chmod 664 {} \;
    
    # Make scripts executable
    print_status "Making scripts executable"
    find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
    find /opt/aitbc -name "*.py" -exec chmod +x {} \;
    
    # Set SGID bit for group inheritance
    print_status "Setting SGID bit for group inheritance"
    find /opt/aitbc -type d -exec chmod g+s {} \;
    
    # Special permissions for logs and data
    print_status "Setting special permissions for logs and data"
    mkdir -p /opt/aitbc/logs /opt/aitbc/data
    chown -R aitbc:aitbc /opt/aitbc/logs /opt/aitbc/data
    chmod 775 /opt/aitbc/logs /opt/aitbc/data
    
    print_status "Directory permissions fixed"
}

# Create enhanced helper scripts
create_helper_scripts() {
    print_header "Creating Enhanced Helper Scripts"
    
    # Enhanced service management script
    cat > "/opt/aitbc/scripts/dev-services.sh" << 'EOF'
#!/bin/bash
# Enhanced AITBC Service Management for Development

case "${1:-help}" in
    "start")
        echo "🚀 Starting AITBC services..."
        sudo systemctl start aitbc-coordinator-api.service
        sudo systemctl start aitbc-blockchain-node.service
        sudo systemctl start aitbc-blockchain-rpc.service
        echo "✅ Services started"
        ;;
    "stop")
        echo "🛑 Stopping AITBC services..."
        sudo systemctl stop aitbc-coordinator-api.service
        sudo systemctl stop aitbc-blockchain-node.service
        sudo systemctl stop aitbc-blockchain-rpc.service
        echo "✅ Services stopped"
        ;;
    "restart")
        echo "🔄 Restarting AITBC services..."
        sudo systemctl restart aitbc-coordinator-api.service
        sudo systemctl restart aitbc-blockchain-node.service
        sudo systemctl restart aitbc-blockchain-rpc.service
        echo "✅ Services restarted"
        ;;
    "status")
        echo "📊 AITBC Services Status:"
        echo ""
        sudo systemctl status aitbc-coordinator-api.service --no-pager -l
        echo ""
        sudo systemctl status aitbc-blockchain-node.service --no-pager -l
        echo ""
        sudo systemctl status aitbc-blockchain-rpc.service --no-pager -l
        ;;
    "logs")
        echo "📋 AITBC Service Logs (Ctrl+C to exit):"
        sudo journalctl -u aitbc-coordinator-api.service -f
        ;;
    "logs-all")
        echo "📋 All AITBC Logs (Ctrl+C to exit):"
        sudo journalctl -u aitbc-* -f
        ;;
    "test")
        echo "🧪 Testing AITBC services..."
        echo "Testing Coordinator API..."
        curl -s http://localhost:8000/health || echo "❌ Coordinator API not responding"
        echo ""
        echo "Testing Blockchain RPC..."
        curl -s http://localhost:8006/health || echo "❌ Blockchain RPC not responding"
        echo ""
        echo "✅ Service test completed"
        ;;
    "help"|*)
        echo "🛠️  AITBC Development Service Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|logs-all|test|help}"
        echo ""
        echo "Commands:"
        echo "  start     - Start all AITBC services"
        echo "  stop      - Stop all AITBC services"
        echo "  restart   - Restart all AITBC services"
        echo "  status    - Show detailed service status"
        echo "  logs      - Follow coordinator API logs"
        echo "  logs-all  - Follow all AITBC service logs"
        echo "  test      - Test service endpoints"
        echo "  help      - Show this help message"
        ;;
esac
EOF
    
    # Quick permission fix script
    cat > "/opt/aitbc/scripts/quick-fix.sh" << 'EOF'
#!/bin/bash
# Quick Permission Fix for AITBC Development

echo "🔧 Quick AITBC Permission Fix..."

# Fix ownership
sudo chown -R oib:aitbc /opt/aitbc

# Fix directory permissions
sudo find /opt/aitbc -type d -exec chmod 2775 {} \;

# Fix file permissions
sudo find /opt/aitbc -type f -exec chmod 664 {} \;

# Make scripts executable
sudo find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
sudo find /opt/aitbc -name "*.py" -exec chmod +x {} \;

# Set SGID bit
sudo find /opt/aitbc -type d -exec chmod g+s {} \;

echo "✅ Permissions fixed!"
EOF
    
    # Make scripts executable
    chmod +x /opt/aitbc/scripts/dev-services.sh
    chmod +x /opt/aitbc/scripts/quick-fix.sh
    
    print_status "Enhanced helper scripts created"
}

# Create development environment setup
create_dev_env() {
    print_header "Creating Development Environment"
    
    # Create comprehensive .env file
    cat > "/opt/aitbc/.env.dev" << 'EOF'
# AITBC Development Environment
# Source this file: source /opt/aitbc/.env.dev

# Development flags
export AITBC_DEV_MODE=1
export AITBC_DEBUG=1
export AITBC_LOG_LEVEL=DEBUG

# Service URLs
export AITBC_COORDINATOR_URL=http://localhost:8000
export AITBC_BLOCKCHAIN_RPC=http://localhost:8006
export AITBC_WEB_UI=http://localhost:3000

# Database paths
export AITBC_DB_PATH=/opt/aitbc/data/coordinator.db
export AITBC_BLOCKCHAIN_DB_PATH=/opt/aitbc/data/blockchain.db

# Development paths
export AITBC_HOME=/opt/aitbc
export AITBC_CLI_PATH=/opt/aitbc/cli
export AITBC_VENV_PATH=/opt/aitbc/cli/venv
export AITBC_LOG_DIR=/opt/aitbc/logs

# Add CLI to PATH
export PATH=$AITBC_CLI_PATH:$PATH

# Python path for CLI
export PYTHONPATH=$AITBC_CLI_PATH:$PYTHONPATH

# Development aliases
alias aitbc-dev='source /opt/aitbc/.env.dev'
alias aitbc-services='/opt/aitbc/scripts/dev-services.sh'
alias aitbc-fix='/opt/aitbc/scripts/quick-fix.sh'
alias aitbc-logs='sudo journalctl -u aitbc-* -f'

echo "🚀 AITBC Development Environment Loaded"
echo "💡 Available commands: aitbc-services, aitbc-fix, aitbc-logs"
EOF
    
    print_status "Development environment created: /opt/aitbc/.env.dev"
}

# Main execution
main() {
    print_header "Complete AITBC Development Permission Fix"
    echo "This script will fix all permission issues for AITBC development"
    echo ""
    echo "Current setup:"
    echo "  Development user: oib"
    echo "  Service user: aitbc"
    echo "  Project directory: /opt/aitbc"
    echo ""
    
    check_root
    
    # Execute all fixes
    fix_sudoers
    fix_permissions
    create_helper_scripts
    create_dev_env
    
    print_header "Setup Complete! 🎉"
    echo ""
    echo "✅ Sudoers configuration fixed"
    echo "✅ Directory permissions corrected"
    echo "✅ Enhanced helper scripts created"
    echo "✅ Development environment set up"
    echo ""
    echo "🚀 Next Steps:"
    echo "1. Reload your shell or run: source ~/.zshrc"
    echo "2. Load development environment: source /opt/aitbc/.env.dev"
    echo "3. Test with: /opt/aitbc/scripts/dev-services.sh status"
    echo ""
    echo "💡 You should now be able to:"
    echo "- Edit files without sudo prompts"
    echo "- Manage services without password"
    echo "- View logs without sudo"
    echo "- Use all development tools seamlessly"
}

# Run main function
main "$@"
