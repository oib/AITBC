#!/bin/bash

# AITBC Local Setup Script
# Sets up AITBC services on a new host with systemd

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run as root (use sudo)"
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if required tools are installed
    command -v python3 >/dev/null 2>&1 || error "Python 3 is not installed"
    command -v pip3 >/dev/null 2>&1 || error "pip3 is not installed"
    command -v git >/dev/null 2>&1 || error "git is not installed"
    command -v systemctl >/dev/null 2>&1 || error "systemctl is not available"
    command -v node >/dev/null 2>&1 || error "Node.js is not installed"
    command -v npm >/dev/null 2>&1 || error "npm is not installed"
    
    # Check Python version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    if [ "$(printf '%s\n' "3.13.5" "$python_version" | sort -V | head -n1)" != "3.13.5" ]; then
        error "Python 3.13.5+ is required, found $python_version"
    fi
    
    # Check Node.js version
    node_version=$(node -v | sed 's/v//')
    if [ "$(printf '%s\n' "24.14.0" "$node_version" | sort -V | head -n1)" != "24.14.0" ]; then
        error "Node.js 24.14.0+ is required, found $node_version"
    fi
    
    success "Prerequisites check passed"
}

# Clone repository
clone_repo() {
    log "Cloning AITBC repository..."
    
    # Check if repository already exists
    if [ -d "/opt/aitbc/.git" ]; then
        success "AITBC repository already exists, skipping clone"
        return 0
    fi
    
    # Clone repository
    cd /opt
    git clone http://gitea.bubuit.net:3000/oib/aitbc.git aitbc || error "Failed to clone repository"
    
    cd /opt/aitbc
    success "Repository cloned successfully"
}

# Setup runtime directories
setup_runtime_directories() {
    log "Setting up runtime directories..."
    
    # Create standard Linux directories
    directories=(
        "/var/lib/aitbc"
        "/var/lib/aitbc/keystore"
        "/var/lib/aitbc/keystore/config"
        "/var/lib/aitbc/keystore/passwords"
        "/var/lib/aitbc/data"
        "/var/log/aitbc"
        "/etc/aitbc"
        "/etc/aitbc/credentials"
        "/run/aitbc/secrets"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        log "Created directory: $dir"
    done
    
    # Set permissions
    chmod 755 /var/lib/aitbc
    chmod 700 /var/lib/aitbc/keystore  # Secure keystore
    chmod 700 /var/lib/aitbc/keystore/config
    chmod 700 /var/lib/aitbc/keystore/passwords
    chmod 755 /var/lib/aitbc/data
    chmod 755 /var/log/aitbc
    chmod 755 /etc/aitbc
    chmod 700 /etc/aitbc/credentials  # Secure credentials
    chmod 700 /run/aitbc/secrets  # Runtime secrets (tmpfs)
    
    # Set ownership
    chown root:root /var/lib/aitbc
    chown root:root /var/lib/aitbc/keystore
    chown root:root /var/lib/aitbc/keystore/config
    chown root:root /var/lib/aitbc/keystore/passwords
    chown root:root /var/lib/aitbc/data
    chown root:root /var/log/aitbc
    chown root:root /etc/aitbc
    chown root:root /etc/aitbc/credentials
    chown root:root /run/aitbc/secrets
    
    # Disable Btrfs CoW on data directory to prevent SQLite corruption
    # SQLite expects overwrite-in-place behavior, which conflicts with CoW
    if command -v chattr >/dev/null 2>&1; then
        chattr +C /var/lib/aitbc 2>/dev/null || log "Could not disable CoW (not Btrfs or no permissions)"
        log "Disabled Btrfs CoW on /var/lib/aitbc to prevent SQLite corruption"
    fi
    
    # Create README files
    echo "# AITBC Runtime Data Directory" > /var/lib/aitbc/README.md
    echo "# Keystore for blockchain keys (SECURE)" > /var/lib/aitbc/keystore/README.md
    echo "# Encrypted configuration secrets" > /var/lib/aitbc/keystore/config/README.md
    echo "# Encrypted password storage" > /var/lib/aitbc/keystore/passwords/README.md
    echo "# Application databases" > /var/lib/aitbc/data/README.md
    echo "# Application logs" > /var/log/aitbc/README.md
    echo "# AITBC Configuration Files" > /etc/aitbc/README.md
    echo "# Secure credential storage (600 permissions)" > /etc/aitbc/credentials/README.md
    echo "# Runtime secrets (tmpfs, cleared on reboot)" > /run/aitbc/secrets/README.md
    
    success "Runtime directories setup completed"
}

# Setup PostgreSQL databases
setup_postgresql_databases() {
    log "Setting up PostgreSQL databases..."

    # Check if PostgreSQL is installed
    if ! command -v psql >/dev/null 2>&1; then
        warning "PostgreSQL is not installed, skipping database setup"
        warning "To install PostgreSQL: apt install postgresql postgresql-contrib"
        return 0
    fi

    # Check if PostgreSQL is running
    if ! systemctl is-active --quiet postgresql.service; then
        warning "PostgreSQL service is not running, skipping database setup"
        warning "To start PostgreSQL: systemctl start postgresql.service"
        return 0
    fi

    # Use centralized database setup script if available
    if [ -f "/opt/aitbc/infra/scripts/setup_postgresql_databases.sh" ]; then
        log "Using centralized PostgreSQL setup script..."
        /opt/aitbc/infra/scripts/setup_postgresql_databases.sh
    else
        warning "Centralized PostgreSQL setup script not found"
        warning "Creating individual databases manually..."

        # Fallback to individual database creation
        databases=(
            "aitbc_coordinator:aitbc_user"
            "aitbc_exchange:aitbc_user"
            "aitbc_wallet:aitbc_user"
            "aitbc_marketplace:aitbc_marketplace"
            "aitbc_governance:aitbc_governance"
            "aitbc_trading:aitbc_trading"
            "aitbc_gpu:aitbc_gpu"
            "aitbc_ai:aitbc_ai"
        )

        for db_user in "${databases[@]}"; do
            db_name=$(echo "$db_user" | cut -d':' -f1)
            db_user=$(echo "$db_user" | cut -d':' -f2)

            # Create user if not exists
            sudo -u postgres psql -c "DO \$\$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
                    CREATE USER ${db_user} WITH PASSWORD 'password';
                END IF;
            END
            \$\$;" 2>/dev/null || true

            # Create database if not exists
            sudo -u postgres psql -c "SELECT 'CREATE DATABASE ${db_name} OWNER ${db_user}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name}')\\gexec" 2>/dev/null || true

            # Grant privileges
            sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};" 2>/dev/null || true

            log "Database ${db_name} setup complete"
        done
    fi

    success "PostgreSQL databases setup completed"
}

# Generate UUID
generate_uuid() {
    if [ -f /proc/sys/kernel/random/uuid ]; then
        cat /proc/sys/kernel/random/uuid
    else
        python3 -c "import uuid; print(uuid.uuid4())"
    fi
}

# Setup unique node identities
setup_node_identities() {
    log "Setting up unique node identities..."

    set_env() {
        local key="$1"
        local value="$2"

        if grep -q "^${key}=" /etc/aitbc/.env; then
            sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/.env
        else
            echo "${key}=${value}" >> /etc/aitbc/.env
        fi
    }

    # Generate unique proposer_id if not already set in /etc/aitbc/.env
    if [ ! -f "/etc/aitbc/.env" ]; then
        log "/etc/aitbc/.env does not exist, creating with unique IDs..."
        PROPOSER_ID="ait1$(generate_uuid | tr -d '-')"
        P2P_NODE_ID="node-$(generate_uuid | tr -d '-')"
        cat > /etc/aitbc/.env << EOF
# AITBC Blockchain Configuration
# Auto-generated unique node identities
proposer_id=$PROPOSER_ID
p2p_node_id=$P2P_NODE_ID
gossip_backend=broadcast
gossip_broadcast_url=redis://localhost:6379
default_peer_rpc_url=http://127.0.0.1:8006
EOF
        log "Created /etc/aitbc/.env with unique IDs"
    else
        # Check if proposer_id exists, if not add it
        if ! grep -q "^proposer_id=" /etc/aitbc/.env; then
            PROPOSER_ID="ait1$(generate_uuid | tr -d '-')"
            set_env proposer_id "$PROPOSER_ID"
            log "Added unique proposer_id to /etc/aitbc/.env"
        else
            log "proposer_id already exists in /etc/aitbc/.env"
        fi
    fi

    # Ensure blockchain gossip defaults exist even if the file was created from a minimal template
    set_env gossip_backend broadcast
    set_env gossip_broadcast_url redis://localhost:6379
    set_env default_peer_rpc_url http://127.0.0.1:8006

    # Create /etc/aitbc/node.env with unique p2p_node_id if not exists
    if [ ! -f "/etc/aitbc/node.env" ]; then
        P2P_NODE_ID="node-$(generate_uuid | tr -d '-')"
        cat > /etc/aitbc/node.env << EOF
# AITBC Node-Specific Environment Configuration
# This file contains variables unique to each node - DO NOT share across nodes

# Node Identity
NODE_ID=aitbc

# P2P Configuration
# P2P node identity (must be unique for each node)
p2p_node_id=$P2P_NODE_ID

# P2P Peers (comma-separated list of peer nodes)
# Format: hostname:port (e.g., "aitbc1:7070,aitbc2:7070")
p2p_peers=
EOF
        log "Created /etc/aitbc/node.env with unique p2p_node_id"
    else
        # Check if p2p_node_id exists, if not add it
        if ! grep -q "^p2p_node_id=" /etc/aitbc/node.env; then
            P2P_NODE_ID="node-$(generate_uuid | tr -d '-')"
            echo "p2p_node_id=$P2P_NODE_ID" >> /etc/aitbc/node.env
            log "Added unique p2p_node_id to /etc/aitbc/node.env"
        else
            log "p2p_node_id already exists in /etc/aitbc/node.env"
        fi
    fi

    success "Node identities setup completed"
}

# Setup secure credentials
setup_credentials() {
    log "Setting up secure credentials..."

    # Generate secure secrets if they don't exist
    if [ ! -f "/etc/aitbc/credentials/api_hash_secret" ]; then
        python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/api_hash_secret
        chmod 600 /etc/aitbc/credentials/api_hash_secret
        log "Generated API_KEY_HASH_SECRET"
    else
        log "API_KEY_HASH_SECRET already exists"
    fi

    if [ ! -f "/etc/aitbc/credentials/keystore_password" ]; then
        python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/keystore_password
        chmod 600 /etc/aitbc/credentials/keystore_password
        log "Generated keystore password"
    else
        log "Keystore password already exists"
    fi

    # Copy proposer_id from .env to credentials
    if [ -f "/etc/aitbc/.env" ] && grep -q "^proposer_id=" /etc/aitbc/.env; then
        grep "^proposer_id=" /etc/aitbc/.env | cut -d'=' -f2 > /etc/aitbc/credentials/proposer_id
        chmod 600 /etc/aitbc/credentials/proposer_id
        log "Copied proposer_id to credentials"
    fi

    # Add API_KEY_HASH_SECRET to .env if not present
    if [ -f "/etc/aitbc/.env" ] && ! grep -q "^API_KEY_HASH_SECRET=" /etc/aitbc/.env; then
        echo "API_KEY_HASH_SECRET=$(cat /etc/aitbc/credentials/api_hash_secret)" >> /etc/aitbc/.env
        log "Added API_KEY_HASH_SECRET to .env"
    fi

    success "Secure credentials setup completed"
}

# Setup Python virtual environments
setup_venvs() {
    log "Setting up Python virtual environments..."
    
    # Create central virtual environment if it doesn't exist
    if [ ! -d "/opt/aitbc/venv" ]; then
        log "Creating central virtual environment..."
        cd /opt/aitbc
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
    else
        log "Central virtual environment already exists, activating..."
        source /opt/aitbc/venv/bin/activate
    fi
    
    # Install all dependencies from central requirements.txt
    log "Installing all dependencies from central requirements.txt..."
    
    # Install main requirements (contains all service dependencies)
    if [ -f "/opt/aitbc/requirements.txt" ]; then
        pip install -r /opt/aitbc/requirements.txt
    else
        error "Main requirements.txt not found"
    fi
    
    success "Virtual environments setup completed"
}

# Install systemd services
install_services() {
    log "Installing systemd services..."

    # Use link-systemd.sh script for consistent service linking
    if [ -f "/opt/aitbc/scripts/utils/link-systemd.sh" ]; then
        log "Using link-systemd.sh to install services..."
        /opt/aitbc/scripts/utils/link-systemd.sh
    else
        warning "link-systemd.sh not found, using manual installation..."
        # Install core services
        services=(
            "aitbc-wallet.service"
            "aitbc-coordinator-api.service"
            "aitbc-exchange-api.service"
            "aitbc-blockchain-node.service"
            "aitbc-blockchain-rpc.service"
            "aitbc-marketplace.service"
            "aitbc-openclaw.service"
            "aitbc-ai.service"
            "aitbc-learning.service"
            "aitbc-explorer.service"
            "aitbc-web-ui.service"
            "aitbc-agent-coordinator.service"
            "aitbc-agent-registry.service"
            "aitbc-multimodal.service"
            "aitbc-modality-optimization.service"
        )

        for service in "${services[@]}"; do
            if [ -f "/opt/aitbc/systemd/$service" ]; then
                log "Installing $service..."
                ln -sf "/opt/aitbc/systemd/$service" /etc/systemd/system/
            else
                warning "Service file not found: $service"
            fi
        done

        # Reload systemd
        systemctl daemon-reload
    fi

    success "Systemd services installed"
}

# Create health check script
create_health_check() {
    log "Creating health check script..."
    
    cat > /opt/aitbc/health-check.sh << 'EOF'
#!/bin/bash

# AITBC Health Check Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local name=$1
    local url=$2
    local expected=${3:-200}
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected"; then
        echo -e "${GREEN}✓${NC} $name is healthy"
        return 0
    else
        echo -e "${RED}✗${NC} $name is unhealthy"
        return 1
    fi
}

echo "AITBC Service Health Check"
echo "========================"

# Core Services (8000-8009)
echo ""
echo "🔧 Core Services (8000-8009):"
check_service "Coordinator API" "http://localhost:8000/health"
check_service "Exchange API" "http://localhost:8001/api/health"
check_service "Marketplace API" "http://localhost:8007/health"
check_service "Wallet API" "http://localhost:8003/health"
check_service "Explorer" "http://localhost:8004/health"

# Check blockchain node and RPC
echo ""
echo "⛓️ Blockchain Services:"
if systemctl is-active --quiet aitbc-blockchain-node.service; then
    echo -e "${GREEN}✓${NC} Blockchain Node is running"
else
    echo -e "${RED}✗${NC} Blockchain Node is not running"
fi

if systemctl is-active --quiet aitbc-blockchain-rpc.service; then
    echo -e "${GREEN}✓${NC} Blockchain RPC (port 8006) is running"
else
    echo -e "${RED}✗${NC} Blockchain RPC (port 8006) is not running"
fi

# AI/Agent/GPU Services (8010-8019)
echo ""
echo "🚀 AI/Agent/GPU Services (8010-8019):"
check_service "GPU Service" "http://localhost:8010/health"
check_service "Learning Service" "http://localhost:8011/health"
check_service "Agent Coordinator" "http://localhost:8012/health"
check_service "Agent Registry" "http://localhost:8013/health"
check_service "OpenClaw Service" "http://localhost:8014/health"
check_service "AI Service" "http://localhost:8015/health"

# Other Services (8020-8029)
echo ""
echo "📊 Other Services (8020-8029):"
check_service "Multimodal Service" "http://localhost:8020/health"
check_service "Modality Optimization" "http://localhost:8021/health"

# Check process status
echo ""
echo "Process Status:"
ps aux | grep -E "simple_daemon|uvicorn|simple_exchange_api" | grep -v grep | while read line; do
    echo -e "${GREEN}✓${NC} $line"
done
EOF

    chmod +x /opt/aitbc/health-check.sh
    
    success "Health check script created"
}

# Start services
start_services() {
    log "Starting AITBC services..."
    
    # Try systemd first
    if systemctl start aitbc-wallet aitbc-coordinator-api aitbc-exchange-api aitbc-blockchain-node aitbc-blockchain-rpc aitbc-gpu aitbc-marketplace aitbc-openclaw aitbc-ai aitbc-learning aitbc-explorer aitbc-agent-coordinator aitbc-agent-registry aitbc-multimodal aitbc-modality-optimization 2>/dev/null; then
        log "Services started via systemd"
        sleep 5

        # Check if services are running
        if systemctl is-active --quiet aitbc-wallet aitbc-coordinator-api aitbc-exchange-api aitbc-blockchain-node aitbc-blockchain-rpc aitbc-gpu aitbc-marketplace aitbc-openclaw aitbc-ai aitbc-learning aitbc-explorer aitbc-agent-coordinator aitbc-agent-registry aitbc-multimodal aitbc-modality-optimization; then
            success "Services started successfully via systemd"
        else
            warning "Some systemd services failed, falling back to manual startup"
            /opt/aitbc/start-services.sh
        fi
    else
        log "Systemd services not available, using manual startup"
        /opt/aitbc/start-services.sh
    fi
    
    # Wait for services to initialize
    sleep 10
    
    # Run health check
    /opt/aitbc/health-check.sh
}

# Setup auto-start
setup_autostart() {
    log "Setting up auto-start..."
    
    # Enable services for auto-start on boot
    systemctl enable aitbc-wallet.service
    systemctl enable aitbc-coordinator-api.service
    systemctl enable aitbc-exchange-api.service
    systemctl enable aitbc-blockchain-node.service
    systemctl enable aitbc-blockchain-rpc.service
    systemctl enable aitbc-marketplace.service
    systemctl enable aitbc-openclaw.service
    systemctl enable aitbc-ai.service
    systemctl enable aitbc-learning.service
    systemctl enable aitbc-explorer.service
    systemctl enable aitbc-web-ui.service
    systemctl enable aitbc-agent-coordinator.service
    systemctl enable aitbc-agent-registry.service
    systemctl enable aitbc-multimodal.service
    systemctl enable aitbc-modality-optimization.service
    
    success "Auto-start configured"
}

# Main function
main() {
    log "Starting AITBC setup..."

    check_root
    check_prerequisites
    clone_repo
    setup_runtime_directories
    setup_postgresql_databases
    setup_node_identities
    setup_credentials
    setup_venvs
    install_services
    create_health_check
    start_services
    setup_autostart

    success "AITBC setup completed!"
    echo ""
    echo "Service Information:"
    echo "  Wallet API: http://localhost:8003/health"
    echo "  Exchange API: http://localhost:8001/api/health"
    echo "  Coordinator API: http://localhost:8000/health"
    echo ""
    echo "Runtime Directories:"
    echo "  Keystore: /var/lib/aitbc/keystore/"
    echo "  Data: /var/lib/aitbc/data/"
    echo "  Logs: /var/lib/aitbc/logs/"
    echo "  Config: /etc/aitbc/"
    echo "  Credentials: /etc/aitbc/credentials/ (600 permissions)"
    echo "  Runtime secrets: /run/aitbc/secrets/ (tmpfs)"
    echo ""
    echo "Management Commands:"
    echo "  Health check: /opt/aitbc/health-check.sh"
    echo "  Load secrets: /opt/aitbc/scripts/utils/load-keystore-secrets.sh"
    echo "  Restart services: systemctl restart aitbc-wallet aitbc-coordinator-api aitbc-exchange-api"
    echo "  View logs: journalctl -u aitbc-wallet -f"
    echo ""
    echo "Security Notes:"
    echo "  - Secrets stored in /etc/aitbc/credentials/ with 600 permissions"
    echo "  - Services load secrets at runtime via systemd ExecStartPre"
    echo "  - API_KEY_HASH_SECRET required (no insecure default)"
}

# Run main function
main "$@"
