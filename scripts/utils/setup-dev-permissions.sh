#!/bin/bash
#
# AITBC Development Permission Setup Script
# This script configures permissions to avoid constant sudo prompts during development
#
# Usage: sudo ./setup-dev-permissions.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEV_USER="oib"
SERVICE_USER="aitbc"
PROJECT_DIR="/opt/aitbc"
LOG_DIR="/opt/aitbc/logs"
DATA_DIR="/opt/aitbc/data"

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

# Add development user to service user group
setup_user_groups() {
    print_header "Setting up User Groups"
    
    # Add dev user to service user group
    print_status "Adding $DEV_USER to $SERVICE_USER group"
    usermod -aG $SERVICE_USER $DEV_USER
    
    # Add service user to development group
    print_status "Adding $SERVICE_USER to codebase group"
    usermod -aG codebase $SERVICE_USER
    
    # Verify groups
    print_status "Verifying group memberships:"
    echo "  $DEV_USER groups: $(groups $DEV_USER | grep -o '$SERVICE_USER\|codebase' || echo 'Not in groups yet')"
    echo "  $SERVICE_USER groups: $(groups $SERVICE_USER | grep -o 'codebase\|$DEV_USER' || echo 'Not in groups yet')"
}

# Set up proper directory permissions
setup_directory_permissions() {
    print_header "Setting up Directory Permissions"
    
    # Set ownership with shared group
    print_status "Setting project directory ownership"
    chown -R $DEV_USER:$SERVICE_USER $PROJECT_DIR
    
    # Set proper permissions
    print_status "Setting directory permissions (2775 for directories, 664 for files)"
    find $PROJECT_DIR -type d -exec chmod 2775 {} \;
    find $PROJECT_DIR -type f -exec chmod 664 {} \;
    
    # Make executable files executable
    find $PROJECT_DIR -name "*.py" -exec chmod +x {} \;
    find $PROJECT_DIR -name "*.sh" -exec chmod +x {} \;
    
    # Set special permissions for critical directories
    print_status "Setting special permissions for logs and data"
    mkdir -p $LOG_DIR $DATA_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $LOG_DIR $DATA_DIR
    chmod 775 $LOG_DIR $DATA_DIR
    
    # Set SGID bit for new files to inherit group
    find $PROJECT_DIR -type d -exec chmod g+s {} \;
}

# Set up sudoers for development
setup_sudoers() {
    print_header "Setting up Sudoers Configuration"
    
    # Create sudoers file for AITBC development
    sudoers_file="/etc/sudoers.d/aitbc-dev"
    
    cat > "$sudoers_file" << EOF
# AITBC Development Sudoers Configuration
# Allows development user to manage AITBC services without password

# Service management (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start aitbc-*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop aitbc-*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart aitbc-*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status aitbc-*

# Log access (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/tail -f /opt/aitbc/logs/*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-*

# File permissions (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/chown -R *$SERVICE_USER* /opt/aitbc/*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/chmod -R * /opt/aitbc/*

# Development tools (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/git *
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/make *
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/cmake *
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/gcc *
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/g++ *

# Virtual environment operations (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/python3 -m venv /opt/aitbc/cli/venv
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/pip3 install -r /opt/aitbc/cli/requirements.txt

# Process management (no password)
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/kill -HUP *aitbc*
$DEV_USER ALL=(root) NOPASSWD: /usr/bin/pkill -f aitbc
EOF
    
    # Set proper permissions on sudoers file
    chmod 440 "$sudoers_file"
    
    print_status "Sudoers configuration created: $sudoers_file"
}

# Create development helper scripts
create_helper_scripts() {
    print_header "Creating Development Helper Scripts"
    
    # Service management script
    cat > "$PROJECT_DIR/scripts/manage-services.sh" << 'EOF'
#!/bin/bash
# AITBC Service Management Script - No sudo required

case "${1:-help}" in
    "start")
        echo "Starting AITBC services..."
        sudo systemctl start aitbc-coordinator-api.service
        sudo systemctl start aitbc-blockchain-node.service
        sudo systemctl start aitbc-blockchain-rpc.service
        echo "Services started"
        ;;
    "stop")
        echo "Stopping AITBC services..."
        sudo systemctl stop aitbc-coordinator-api.service
        sudo systemctl stop aitbc-blockchain-node.service
        sudo systemctl stop aitbc-blockchain-rpc.service
        echo "Services stopped"
        ;;
    "restart")
        echo "Restarting AITBC services..."
        sudo systemctl restart aitbc-coordinator-api.service
        sudo systemctl restart aitbc-blockchain-node.service
        sudo systemctl restart aitbc-blockchain-rpc.service
        echo "Services restarted"
        ;;
    "status")
        echo "=== AITBC Services Status ==="
        sudo systemctl status aitbc-coordinator-api.service --no-pager
        sudo systemctl status aitbc-blockchain-node.service --no-pager
        sudo systemctl status aitbc-blockchain-rpc.service --no-pager
        ;;
    "logs")
        echo "=== AITBC Service Logs ==="
        sudo journalctl -u aitbc-coordinator-api.service -f
        ;;
    "help"|*)
        echo "AITBC Service Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|help}"
        echo ""
        echo "Commands:"
        echo "  start   - Start all AITBC services"
        echo "  stop    - Stop all AITBC services"
        echo "  restart - Restart all AITBC services"
        echo "  status  - Show service status"
        echo "  logs    - Follow service logs"
        echo "  help    - Show this help message"
        ;;
esac
EOF
    
    # Permission fix script
    cat > "$PROJECT_DIR/scripts/fix-permissions.sh" << 'EOF'
#!/bin/bash
# AITBC Permission Fix Script - No sudo required

echo "Fixing AITBC project permissions..."

# Fix ownership
sudo chown -R oib:aitbc /opt/aitbc

# Fix directory permissions
sudo find /opt/aitbc -type d -exec chmod 2775 {} \;

# Fix file permissions
sudo find /opt/aitbc -type f -exec chmod 664 {} \;

# Make scripts executable
sudo find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
sudo find /opt/aitbc -name "*.py" -exec chmod +x {} \;

# Set SGID bit for directories
sudo find /opt/aitbc -type d -exec chmod g+s {} \;

echo "Permissions fixed!"
EOF
    
    # Make scripts executable
    chmod +x "$PROJECT_DIR/scripts/manage-services.sh"
    chmod +x "$PROJECT_DIR/scripts/fix-permissions.sh"
    
    print_status "Helper scripts created in $PROJECT_DIR/scripts/"
}

# Create development environment setup
setup_dev_environment() {
    print_header "Setting up Development Environment"
    
    # Create .env file for development
    cat > "$PROJECT_DIR/.env.dev" << 'EOF'
# AITBC Development Environment Configuration
# This file is used for development setup

# Development flags
export AITBC_DEV_MODE=1
export AITBC_DEBUG=1
export AITBC_LOG_LEVEL=DEBUG

# Service URLs (development)
export AITBC_COORDINATOR_URL=http://localhost:8011
export AITBC_BLOCKCHAIN_RPC=http://localhost:8006
export AITBC_WEB_UI=http://localhost:3000

# Database (development)
export AITBC_DB_PATH=/opt/aitbc/data/coordinator.db
export AITBC_BLOCKCHAIN_DB_PATH=/opt/aitbc/data/blockchain.db

# Development tools
export AITBC_CLI_PATH=/opt/aitbc/cli
export AITBC_VENV_PATH=/opt/aitbc/cli/venv

# Logging
export AITBC_LOG_DIR=/opt/aitbc/logs
export AITBC_LOG_FILE=/opt/aitbc/logs/aitbc-dev.log
EOF
    
    print_status "Development environment file created: $PROJECT_DIR/.env.dev"
}

# Main execution
main() {
    print_header "AITBC Development Permission Setup"
    echo "This script will configure permissions to avoid sudo prompts during development"
    echo ""
    echo "Current setup:"
    echo "  Development user: $DEV_USER"
    echo "  Service user: $SERVICE_USER"
    echo "  Project directory: $PROJECT_DIR"
    echo ""
    
    read -p "Continue with permission setup? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Setup cancelled"
        exit 0
    fi
    
    check_root
    
    # Execute setup steps
    setup_user_groups
    setup_directory_permissions
    setup_sudoers
    create_helper_scripts
    setup_dev_environment
    
    print_header "Setup Complete!"
    echo ""
    echo "✅ User permissions configured"
    echo "✅ Directory permissions set"
    echo "✅ Sudoers configured for development"
    echo "✅ Helper scripts created"
    echo "✅ Development environment set up"
    echo ""
    echo "Next steps:"
    echo "1. Log out and log back in (or run: newgrp $SERVICE_USER)"
    echo "2. Use helper scripts in $PROJECT_DIR/scripts/"
    echo "3. Source development environment: source $PROJECT_DIR/.env.dev"
    echo ""
    echo "You should now be able to:"
    echo "- Start/stop services without sudo password"
    echo "- Edit files without permission issues"
    echo "- View logs without sudo password"
    echo "- Manage development environment easily"
}

# Run main function
main "$@"
