#!/bin/bash

# AITBC Systemd Deployment Script
# One-command setup for AITBC services using systemd
# This script handles automated deployment of AITBC services on Linux servers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../utils/deploy_common.sh"

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
VENV_DIR="$REPO_ROOT/venv"
PYTHON_VERSION="3.13"
BACKUP_DIR="$REPO_ROOT/.backup"

# Check prerequisites
check_prerequisites() {
    log "Checking system prerequisites..."

    check_root

    # Check Linux distribution
    if [[ ! -f /etc/os-release ]]; then
        error "Cannot detect Linux distribution"
    fi
    source /etc/os-release
    log "Detected OS: $PRETTY_NAME"

    # Check Python version
    require_command python3

    PYTHON_VER=$(python3 --version | awk '{print $2}')
    log "Python version: $PYTHON_VER"
    require_min_version "$PYTHON_VER" "$PYTHON_VERSION" "Python"

    # Check systemd
    require_command systemctl

    # Check required system tools
    require_commands git curl jq

    success "Prerequisites check passed"
}

# Install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    
    if [[ "$ID" == "ubuntu" ]] || [[ "$ID" == "debian" ]]; then
        apt-get update
        apt-get install -y \
            python3-venv \
            python3-dev \
            build-essential \
            libssl-dev \
            libffi-dev \
            postgresql \
            postgresql-contrib \
            redis-server \
            nginx \
            jq \
            curl \
            git
    elif [[ "$ID" == "centos" ]] || [[ "$ID" == "rhel" ]] || [[ "$ID" == "fedora" ]]; then
        dnf install -y \
            python3-venv \
            python3-devel \
            gcc \
            openssl-devel \
            libffi-devel \
            postgresql-server \
            postgresql-contrib \
            redis \
            nginx \
            jq \
            curl \
            git
    else
        warning "Unsupported distribution. Please install dependencies manually"
        return 0
    fi
    
    success "System dependencies installed"
}

# Setup repository
setup_repository() {
    log "Setting up repository..."
    
    # Create backup of existing deployment
    if [[ -d "$REPO_ROOT" ]]; then
        log "Creating backup of existing deployment..."
        BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP_PATH="$BACKUP_DIR/backup_$BACKUP_TIMESTAMP"
        mkdir -p "$BACKUP_DIR"
        cp -r "$REPO_ROOT" "$BACKUP_PATH" || warning "Backup failed, continuing anyway"
        log "Backup created at: $BACKUP_PATH"
    fi
    
    # Clone or update repository
    if [[ -d "$REPO_ROOT/.git" ]]; then
        log "Updating existing repository..."
        cd "$REPO_ROOT"
        git pull || warning "Git pull failed, continuing with existing code"
    else
        log "Cloning repository..."
        # REPO_URL should be set as environment variable
        REPO_URL="${REPO_URL:-https://github.com/your-org/aitbc.git}"
        git clone "$REPO_URL" "$REPO_ROOT"
    fi
    
    success "Repository setup completed"
}

# Create virtual environment
create_venv() {
    log "Creating Python virtual environment..."
    
    if [[ -d "$VENV_DIR" ]]; then
        log "Virtual environment already exists, recreating..."
        rm -rf "$VENV_DIR"
    fi
    
    python3 -m venv "$VENV_DIR"
    success "Virtual environment created"
}

# Install Python dependencies
install_python_dependencies() {
    log "Installing Python dependencies..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install using Poetry
    if [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
        pip install poetry
        cd "$REPO_ROOT" && poetry install
    else
        warning "pyproject.toml not found, installing basic dependencies"
        pip install fastapi uvicorn sqlmodel alembic pydantic httpx requests
    fi
    
    success "Python dependencies installed"
}

# Configure environment
configure_environment() {
    log "Configuring environment variables..."
    
    # Create /etc/aitbc directory
    mkdir -p /etc/aitbc
    
    # Setup node.env if it doesn't exist
    if [[ ! -f /etc/aitbc/node.env ]] && [[ -f "$REPO_ROOT/examples/node.env.example" ]]; then
        cp "$REPO_ROOT/examples/node.env.example" /etc/aitbc/node.env
        warning "Created /etc/aitbc/node.env from template. Please edit with node-specific values"
    fi
    
    # Generate unique node IDs if not set
    if [[ -f /etc/aitbc/node.env ]]; then
        if grep -q "node-<unique-uuid-here>" /etc/aitbc/node.env; then
            log "Generating unique node IDs..."
            UUID=$(uuidgen | tr -d '-')
            sed -i "s/node-<unique-uuid-here>/node-$UUID/g" /etc/aitbc/node.env
            sed -i "s/ait1<unique-uuid-here>/ait1$UUID/g" /etc/aitbc/node.env
            log "Generated node IDs with UUID: $UUID"
        fi
    fi
    
    # Setup blockchain.env if it doesn't exist
    if [[ ! -f /etc/aitbc/blockchain.env ]]; then
        if [[ -f "$REPO_ROOT/examples/env.example" ]]; then
            # Extract relevant blockchain configuration from examples/env.example
            grep -E "^(chain_id|CHAIN_ID|rpc_bind_host|rpc_bind_port|p2p_bind_host|p2p_bind_port|enable_block_production|block_time_seconds|proposer_id)" "$REPO_ROOT/examples/env.example" > /etc/aitbc/blockchain.env || true
        fi
        
        # Add defaults if file is empty
        if [[ ! -s /etc/aitbc/blockchain.env ]]; then
            cat > /etc/aitbc/blockchain.env << EOF
# Blockchain Configuration
chain_id=ait-testnet
rpc_bind_host=0.0.0.0
rpc_bind_port=8006
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
enable_block_production=true
EOF
        fi
    fi
    
    # Setup secrets directory
    mkdir -p /run/aitbc/secrets
    touch /run/aitbc/secrets/.env
    
    success "Environment configuration completed"
}

# Initialize databases
initialize_databases() {
    log "Initializing databases..."
    
    # Start PostgreSQL if not running
    if systemctl is-active --quiet postgresql || systemctl is-active --quiet postgresql@13-main; then
        log "PostgreSQL is already running"
    else
        log "Starting PostgreSQL..."
        systemctl start postgresql || systemctl start postgresql@13-main || warning "Failed to start PostgreSQL"
    fi
    
    # Create databases if they don't exist
    if command -v psql &> /dev/null; then
        for db in aitbc aitbc_coordinator aitbc_marketplace; do
            if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw $db; then
                log "Creating database: $db"
                sudo -u postgres createdb $db || warning "Failed to create database $db"
            fi
        done
    fi
    
    # Start Redis if not running
    if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis; then
        log "Redis is already running"
    else
        log "Starting Redis..."
        systemctl start redis-server || systemctl start redis || warning "Failed to start Redis"
    fi
    
    success "Database initialization completed"
}

# Setup systemd services
setup_systemd_services() {
    log "Setting up systemd services..."
    
    # Link systemd service files
    if [[ -f "$REPO_ROOT/scripts/utils/link-systemd.sh" ]]; then
        bash "$REPO_ROOT/scripts/utils/link-systemd.sh"
    else
        # Manual linking
        log "Linking systemd service files..."
        mkdir -p /etc/systemd/system
        for service in "$REPO_ROOT/systemd"/*.service; do
            if [[ -f "$service" ]]; then
                ln -sf "$service" "/etc/systemd/system/$(basename $service)"
            fi
        done
    fi
    
    # Reload systemd
    systemctl daemon-reload
    
    success "Systemd services setup completed"
}

# Start services in dependency order
start_services() {
    log "Starting AITBC services..."
    
    # Define service startup order
    SERVICES=(
        "postgresql"
        "redis-server"
        "aitbc-blockchain-p2p"
        "aitbc-blockchain-node"
        "aitbc-blockchain-rpc"
        "aitbc-coordinator-api"
        "aitbc-exchange-api"
        "aitbc-wallet"
        "aitbc-agent-daemon"
        "aitbc-agent-coordinator"
        "aitbc-marketplace"
    )
    
    for service in "${SERVICES[@]}"; do
        log "Starting $service..."
        if systemctl list-unit-files | grep -q "^$service.service"; then
            systemctl enable "$service" 2>/dev/null || true
            systemctl start "$service" || warning "Failed to start $service"
            sleep 2
        else
            log "$service not found, skipping"
        fi
    done
    
    success "Services started"
}

# Run health checks
run_health_checks() {
    log "Running health checks..."
    
    # Wait for services to be ready
    log "Waiting for services to stabilize..."
    sleep 10
    
    # Check service status
    FAILED_SERVICES=()
    for service in aitbc-blockchain-node aitbc-blockchain-rpc aitbc-coordinator-api; do
        if systemctl is-active --quiet "$service"; then
            success "$service is running"
        else
            error "$service is not running"
            FAILED_SERVICES+=("$service")
        fi
    done
    
    # Check API endpoints if available
    if command -v curl &> /dev/null; then
        log "Checking API endpoints..."
        
        # Check blockchain RPC
        if curl -sf http://localhost:8006/health > /dev/null 2>&1; then
            success "Blockchain RPC health check passed"
        else
            warning "Blockchain RPC health check failed"
        fi
        
        # Check coordinator API
        if curl -sf http://localhost:8011/health > /dev/null 2>&1; then
            success "Coordinator API health check passed"
        else
            warning "Coordinator API health check failed"
        fi
    fi
    
    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        error "Some services failed to start: ${FAILED_SERVICES[*]}"
    fi
    
    success "Health checks completed"
}

# Rollback deployment
rollback_deployment() {
    log "Rolling back deployment..."
    
    # Find latest backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_* 2>/dev/null | head -1)
    
    if [[ -z "$LATEST_BACKUP" ]]; then
        error "No backup found for rollback"
    fi
    
    log "Restoring from: $LATEST_BACKUP"
    
    # Stop services
    log "Stopping services..."
    for service in aitbc-*; do
        systemctl stop "$service" 2>/dev/null || true
    done
    
    # Restore backup
    rm -rf "$REPO_ROOT"
    cp -r "$LATEST_BACKUP" "$REPO_ROOT"
    
    # Restart services
    start_services
    
    success "Rollback completed"
}

# Display deployment status
display_status() {
    log "Deployment Status"
    echo "=================="
    echo "Repository: $REPO_ROOT"
    echo "Virtual Environment: $VENV_DIR"
    echo "Python: $(python3 --version)"
    echo ""
    echo "Service Status:"
    systemctl list-units --type=service --state=running | grep aitbc || echo "No AITBC services running"
    echo ""
    echo "Next Steps:"
    echo "1. Edit /etc/aitbc/blockchain.env with blockchain configuration"
    echo "2. Edit /etc/aitbc/node.env with node-specific values"
    echo "3. Restart services: systemctl restart aitbc-*"
    echo "4. Check logs: journalctl -u aitbc-blockchain-node -f"
    echo "5. Run health checks: $REPO_ROOT/scripts/monitoring/health_check.sh"
}

# Main deployment function
main() {
    local COMMAND="${1:-deploy}"
    
    case "$COMMAND" in
        "deploy")
            log "Starting AITBC deployment..."
            check_prerequisites
            install_dependencies
            setup_repository
            create_venv
            install_python_dependencies
            configure_environment
            initialize_databases
            setup_systemd_services
            start_services
            run_health_checks
            display_status
            success "Deployment completed successfully!"
            ;;
        "rollback")
            rollback_deployment
            ;;
        "status")
            display_status
            ;;
        "health-check")
            run_health_checks
            ;;
        *)
            echo "Usage: $0 {deploy|rollback|status|health-check}"
            echo ""
            echo "Commands:"
            echo "  deploy         - Full deployment of AITBC services"
            echo "  rollback       - Rollback to previous deployment"
            echo "  status         - Display deployment status"
            echo "  health-check   - Run health checks on services"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Run main function
main "$@"
