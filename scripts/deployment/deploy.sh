#!/bin/bash

# AITBC Systemd Deployment Script
# One-command setup for AITBC services using systemd
# This script handles automated deployment of AITBC services on Linux servers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
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
    # shellcheck disable=SC1091
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
        # Default to the public mirror; override with REPO_URL for a private source.
        REPO_URL="${REPO_URL:-https://github.com/oib/AITBC.git}"
        git clone "$REPO_URL" "$REPO_ROOT"
    fi

    success "Repository setup completed"
}

# Create virtual environment (idempotent: keep existing venv when it is usable)
create_venv() {
    log "Setting up Python virtual environment..."

    if [[ -d "$VENV_DIR" ]] && [[ -x "$VENV_DIR/bin/python" ]]; then
        log "Virtual environment already exists, reusing it"
        return 0
    fi

    if [[ -d "$VENV_DIR" ]]; then
        warning "Virtual environment exists but is incomplete, recreating it"
        rm -rf "$VENV_DIR"
    fi

    python3 -m venv "$VENV_DIR"
    success "Virtual environment created"
}

# Install Python dependencies using declarative profiles (mirrors setup.sh/update.sh)
install_python_dependencies() {
    log "Installing Python dependencies..."

    # Activate virtual environment
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    # Upgrade pip
    pip install --upgrade pip setuptools wheel

    local PROFILE="server-no-gpu"
    if [[ -f "/etc/aitbc/blockchain.env" ]]; then
        # shellcheck disable=SC1091
        source "/etc/aitbc/blockchain.env"
        if [[ "${HARDWARE_PROFILE:-}" == "gpu" ]]; then
            PROFILE="provider-gpu"
        elif [[ "${BLOCKCHAIN_MODE:-}" == "hub" ]]; then
            PROFILE="hub"
        elif [[ "${MARKET_ROLE:-}" == "customer" ]]; then
            PROFILE="customer-no-gpu"
        else
            PROFILE="server-no-gpu"
        fi
    fi

    if [[ -x "$REPO_ROOT/scripts/deployment/install-profiles.sh" ]]; then
        "$REPO_ROOT/scripts/deployment/install-profiles.sh" "$PROFILE" || error "Profile installation failed"
    else
        warning "install-profiles.sh not found, falling back to requirements.txt"
        if [[ -f "$REPO_ROOT/requirements.txt" ]]; then
            pip install -r "$REPO_ROOT/requirements.txt" || error "Failed to install requirements"
        else
            error "No requirements.txt found and install-profiles.sh is missing"
        fi
    fi

    # Install repo-local packages and CLI so imports resolve
    for pkg_dir in "$REPO_ROOT/packages/aitbc-shared" "$REPO_ROOT/packages/py/"*; do
        if [[ -d "$pkg_dir" ]] && [[ -f "$pkg_dir/pyproject.toml" ]]; then
            if pip install -q -e "$pkg_dir" >/dev/null 2>&1; then
                log "Installed $(basename "$pkg_dir")"
            else
                warning "Failed to install $(basename "$pkg_dir")"
            fi
        fi
    done

    if [[ -d "$REPO_ROOT/cli" ]]; then
        cd "$REPO_ROOT/cli"
        pip install -e . || warning "Failed to install AITBC CLI"
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
        if [[ -f "$REPO_ROOT/examples/blockchain.env.example" ]]; then
            # Copy example and strip comments for production use
            grep -v '^#' "$REPO_ROOT/examples/blockchain.env.example" | grep -v '^$' > /etc/aitbc/blockchain.env || true
        fi

        # Add defaults if file is empty
        if [[ ! -s /etc/aitbc/blockchain.env ]]; then
            cat > /etc/aitbc/blockchain.env << EOF
# Blockchain Configuration
CHAIN_ID=ait-testnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8200
ENABLE_BLOCK_PRODUCTION=true
BLOCK_TIME_SECONDS=6
PROPOSER_ID=ait1<unique-proposer-id>
P2P_PEERS=auto
SUBSCRIPTION_ENABLED=true
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

# Bring every Alembic-managed service's schema to head.
#
# This step did not exist. `initialize_databases` above creates the Postgres databases and
# nothing else, and `main` went straight from there to `start_services`, so a fresh install
# brought every service up against whatever schema happened to be present -- for services
# whose `init_db()` deliberately creates nothing, that is no schema at all. Only update.sh
# migrated, and update.sh is the path for a node that is already installed (V23-79).
#
# Shared with update.sh so the install and update paths cannot drift apart.
run_database_migrations() {
    log "Running Alembic DB migrations..."
    if ! AITBC_ROOT="$REPO_ROOT" VENV_DIR="$VENV_DIR" "$REPO_ROOT/scripts/deployment/run-migrations.sh"; then
        # `error` in deploy_common.sh exits. That is the right behaviour here: starting
        # services against a schema that failed to migrate is what this step exists to stop.
        error "Database migrations failed — not starting services"
    fi
    success "Database migrations completed"
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
                ln -sf "$service" "/etc/systemd/system/$(basename "$service")"
            fi
        done
    fi

    # Load keystore secrets before services start
    if [[ -f "$REPO_ROOT/scripts/utils/load-keystore-secrets.sh" ]]; then
        log "Loading keystore secrets..."
        bash "$REPO_ROOT/scripts/utils/load-keystore-secrets.sh" || warning "Failed to load keystore secrets"
    fi

    # Reload systemd
    systemctl daemon-reload

    # Enable recovery service to run on boot
    if systemctl list-unit-files | grep -q "aitbc-recovery.service"; then
        log "Enabling aitbc-recovery service for automatic startup on boot..."
        systemctl enable aitbc-recovery
        if systemctl is-enabled --quiet aitbc-recovery; then
            success "aitbc-recovery service enabled successfully"
        else
            error "Failed to enable aitbc-recovery service"
        fi
    else
        warning "aitbc-recovery.service not found, skipping enable"
    fi

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
        if curl -sf http://localhost:8203/health > /dev/null 2>&1; then
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
    LATEST_BACKUP=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'backup_*' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2-)

    if [[ -z "$LATEST_BACKUP" ]]; then
        error "No backup found for rollback"
    fi

    log "Restoring from: $LATEST_BACKUP"

    # Stop services
    log "Stopping services..."
    for service in aitbc-*; do
        systemctl stop "$service" 2>/dev/null || true
    done

    # Restore backup.
    #
    # This was `rm -rf "$REPO_ROOT"` followed by `cp -r`, with no confirmation: a failure
    # partway through the copy (disk full, corrupt backup) left the install directory
    # empty with nothing to fall back to. Now the old tree is moved aside, the copy is
    # verified to have succeeded, and only then is the old tree discarded.
    if [[ "${ROLLBACK_ASSUME_YES:-}" != "yes" ]]; then
        if [[ ! -t 0 ]]; then
            error "Refusing to roll back non-interactively; set ROLLBACK_ASSUME_YES=yes to proceed"
        fi
        read -r -p "This will replace $REPO_ROOT with $LATEST_BACKUP. Type 'rollback' to continue: " _confirm
        [[ "$_confirm" == "rollback" ]] || error "Rollback not confirmed; aborting"
    fi

    PREVIOUS_TREE="${REPO_ROOT}.rollback-$(date +%Y%m%d_%H%M%S)"
    log "Moving current tree aside to $PREVIOUS_TREE"
    mv "$REPO_ROOT" "$PREVIOUS_TREE"

    if ! cp -r "$LATEST_BACKUP" "$REPO_ROOT"; then
        log "Restore failed; putting the previous tree back"
        rm -rf "$REPO_ROOT"
        mv "$PREVIOUS_TREE" "$REPO_ROOT"
        error "Rollback failed to restore $LATEST_BACKUP; original tree preserved"
    fi

    log "Restore succeeded; previous tree retained at $PREVIOUS_TREE"

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
            # After the units are linked, not before: run-migrations.sh skips any service
            # whose unit is absent, which is how it stays role-aware. Before start_services,
            # because migrating under a running service is what corrupts one.
            run_database_migrations
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
trap 'error "Script interrupted"; exit 130' INT TERM

# Run main function
main "$@"
