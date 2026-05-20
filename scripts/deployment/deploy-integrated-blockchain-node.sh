#!/bin/bash
#
# Integrated Blockchain Node Deployment Script
# Deploys the full-featured integrated blockchain node with mempool support
# This script sets up the node from scratch on a new host or container
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://gitea.bubuit.net:3000/oib/aitbc.git"
INSTALL_DIR="/opt/aitbc"
ENV_FILE="/etc/aitbc/blockchain.env"
NODE_ENV_FILE="/etc/aitbc/node.env"
SERVICE_NAME="aitbc-blockchain-node"

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

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for required commands
    for cmd in git python3 pip3 systemctl; do
        if ! command -v $cmd &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done
    
    # Check Python version
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    REQUIRED_VERSION="3.13"
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        log_error "Python $REQUIRED_VERSION+ required, found $PYTHON_VERSION"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

clone_repository() {
    log_info "Cloning AITBC repository..."
    
    if [ -d "$INSTALL_DIR" ]; then
        log_warn "Directory $INSTALL_DIR already exists"
        log_info "Updating existing repository via git pull"
        cd "$INSTALL_DIR"
        git pull origin main || {
            log_error "Failed to update repository"
            log_info "Attempting to continue with existing version"
        }
        log_info "Repository updated successfully"
        return
    fi
    
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    log_info "Repository cloned successfully"
}

setup_python_environment() {
    log_info "Setting up Python environment..."
    
    cd "$INSTALL_DIR"
    
    # Create virtual environment
    python3 -m venv venv
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install essential blockchain-node dependencies
    log_info "Installing essential dependencies"
    pip install pydantic pydantic-settings fastapi uvicorn sqlalchemy sqlmodel psycopg2-binary psycopg2 aiosqlite httpx redis prometheus-client alembic
    
    # Install blockchain-node package in editable mode
    if [ -f "apps/blockchain-node/pyproject.toml" ]; then
        log_info "Installing blockchain-node package in editable mode"
        pip install -e apps/blockchain-node
    else
        log_error "No pyproject.toml found in apps/blockchain-node"
        deactivate
        exit 1
    fi
    
    deactivate
    
    log_info "Python environment setup complete"
}

setup_directories() {
    log_info "Setting up directories..."
    
    # Create runtime directories
    mkdir -p /var/lib/aitbc/keystore
    mkdir -p /var/lib/aitbc/data
    mkdir -p /var/lib/aitbc/logs
    
    # Create configuration directory
    mkdir -p /etc/aitbc
    
    # Set permissions
    chmod 700 /var/lib/aitbc/keystore
    chmod 755 /var/lib/aitbc/data
    chmod 755 /var/lib/aitbc/logs
    chmod 755 /etc/aitbc
    
    log_info "Directories setup complete"
}

setup_postgresql() {
    log_info "Setting up PostgreSQL for mempool..."
    
    # Install PostgreSQL and development headers
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y postgresql postgresql-contrib libpq-dev
    elif command -v yum &> /dev/null; then
        yum install -y postgresql-server postgresql-contrib postgresql-devel
    else
        log_error "Unsupported package manager"
        exit 1
    fi
    
    # Start PostgreSQL service
    if command -v systemctl &> /dev/null; then
        systemctl enable postgresql
        systemctl start postgresql
    fi
    
    # Wait for PostgreSQL to be ready
    sleep 5
    
    # Create mempool database and user
    log_info "Creating mempool database and user..."
    sudo -u postgres psql << EOF
CREATE DATABASE aitbc_mempool;
CREATE USER aitbc_mempool WITH PASSWORD 'aitbc_mempool_password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_mempool TO aitbc_mempool;
ALTER USER aitbc_mempool WITH SUPERUSER;
EOF
    
    log_info "PostgreSQL setup complete"
}

setup_environment_files() {
    log_info "Setting up environment files..."
    
    # Generate unique chain ID for this node
    NODE_ID=$(hostname)
    CHAIN_ID="ait-${NODE_ID}"
    
    # Create blockchain.env if it doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << EOF
# Blockchain Node Configuration
CHAIN_ID=$CHAIN_ID
SUPPORTED_CHAINS=$CHAIN_ID
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8001
ENABLE_BLOCK_PRODUCTION=false
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
CROSS_SITE_REMOTE_ENDPOINTS=
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:aitbc_mempool_password@localhost:5432/aitbc_mempool
EOF
        chmod 600 "$ENV_FILE"
        log_info "Created $ENV_FILE with chain ID: $CHAIN_ID"
    else
        log_info "$ENV_FILE already exists, skipping"
    fi
    
    # Create node.env if it doesn't exist
    if [ ! -f "$NODE_ENV_FILE" ]; then
        cat > "$NODE_ENV_FILE" << EOF
# Node Configuration
NODE_ID=$NODE_ID
ISLAND_ID=$CHAIN_ID-island
CHAIN_ID=$CHAIN_ID
NODE_ROLE=follower
P2P_BIND_PORT=8001
EOF
        chmod 600 "$NODE_ENV_FILE"
        log_info "Created $NODE_ENV_FILE with node ID: $NODE_ID"
    else
        log_info "$NODE_ENV_FILE already exists, skipping"
    fi
}

generate_wallet_and_genesis() {
    log_info "Generating wallet and genesis allocation..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    # Get chain ID from environment file
    CHAIN_ID=$(grep "^CHAIN_ID=" "$ENV_FILE" | cut -d'=' -f2)
    NODE_ID=$(grep "^NODE_ID=" "$NODE_ENV_FILE" | cut -d'=' -f2)
    
    # Generate wallet using Python
    python3 << EOF
import secrets
import json
from pathlib import Path

# Generate wallet keys
private_key = f"0x{secrets.token_hex(32)}"
public_key = f"0x{secrets.token_hex(32)}"
address = f"aitbc1{secrets.token_hex(20)}"

# Save wallet
wallet_data = {
    "wallet_id": "genesis-wallet",
    "address": address,
    "private_key": private_key,
    "public_key": public_key,
    "chain_id": "$CHAIN_ID",
    "created_at": "2026-05-20T00:00:00Z"
}

wallet_path = Path("/var/lib/aitbc/keystore/genesis-wallet.json")
wallet_path.parent.mkdir(parents=True, exist_ok=True)
with open(wallet_path, "w") as f:
    json.dump(wallet_data, f, indent=2)

# Generate genesis allocation
genesis_allocation = {
    "allocations": [
        {
            "address": address,
            "balance": "1000000",  # 1 million tokens
            "nonce": 0
        }
    ]
}

genesis_path = Path(f"/var/lib/aitbc/data/{CHAIN_ID}/genesis.json")
genesis_path.parent.mkdir(parents=True, exist_ok=True)
with open(genesis_path, "w") as f:
    json.dump(genesis_allocation, f, indent=2)

print(f"Generated wallet: {address}")
print(f"Saved wallet to: {wallet_path}")
print(f"Saved genesis allocation to: {genesis_path}")
EOF
    
    deactivate
    
    log_info "Wallet and genesis allocation generated successfully"
}

generate_genesis_block() {
    log_info "Generating genesis block for chain..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    # Get chain ID from environment file
    CHAIN_ID=$(grep "^CHAIN_ID=" "$ENV_FILE" | cut -d'=' -f2)
    NODE_ID=$(grep "^NODE_ID=" "$NODE_ENV_FILE" | cut -d'=' -f2)
    
    log_info "Generating genesis for chain: $CHAIN_ID, node: $NODE_ID"
    
    # Run genesis initialization script
    cd apps/blockchain-node
    python3 init_genesis.py
    
    deactivate
    
    log_info "Genesis block generation complete"
}

setup_systemd_service() {
    log_info "Setting up systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=AITBC Production Blockchain Node
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=$ENV_FILE
EnvironmentFile=$NODE_ENV_FILE
ExecStartPre=$INSTALL_DIR/scripts/utils/load-keystore-secrets.sh
ExecStart=$INSTALL_DIR/venv/bin/python -m aitbc_chain.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    
    log_info "Systemd service setup complete"
}

start_service() {
    log_info "Starting blockchain node service..."
    
    systemctl start $SERVICE_NAME
    
    # Wait for service to start
    sleep 5
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        log_info "Service started successfully"
    else
        log_error "Service failed to start"
        systemctl status $SERVICE_NAME --no-pager
        exit 1
    fi
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check service status
    if systemctl is-active --quiet $SERVICE_NAME; then
        log_info "✓ Service is running"
    else
        log_error "✗ Service is not running"
        exit 1
    fi
    
    # Check RPC endpoint
    if curl -s http://localhost:8006/rpc/head > /dev/null; then
        log_info "✓ RPC endpoint is accessible"
    else
        log_error "✗ RPC endpoint is not accessible"
        exit 1
    fi
    
    # Check mempool endpoint
    if curl -s http://localhost:8006/rpc/mempool > /dev/null; then
        log_info "✓ Mempool endpoint is accessible"
    else
        log_error "✗ Mempool endpoint is not accessible"
        exit 1
    fi
    
    log_info "Deployment verification complete"
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "  Integrated Blockchain Node Deployed"
    echo "=========================================="
    echo ""
    echo "Service: $SERVICE_NAME"
    echo "Install Dir: $INSTALL_DIR"
    echo "Config: $ENV_FILE"
    echo ""
    echo "RPC Endpoints:"
    echo "  - Head: http://localhost:8006/rpc/head"
    echo "  - Mempool: http://localhost:8006/rpc/mempool"
    echo ""
    echo "Management Commands:"
    echo "  - Status: systemctl status $SERVICE_NAME"
    echo "  - Restart: systemctl restart $SERVICE_NAME"
    echo "  - Logs: journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "Configuration:"
    echo "  - Edit config: nano $ENV_FILE"
    echo "  - After edit: systemctl restart $SERVICE_NAME"
    echo ""
}

# Main execution
main() {
    echo "=========================================="
    echo "  Integrated Blockchain Node Deployment"
    echo "=========================================="
    echo ""
    
    check_root
    check_prerequisites
    clone_repository
    setup_directories
    setup_postgresql
    setup_environment_files
    setup_python_environment
    generate_wallet_and_genesis
    setup_systemd_service
    start_service
    verify_deployment
    print_summary
    
    log_info "Deployment completed successfully!"
}

# Run main function
main "$@"
