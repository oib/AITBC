#!/bin/bash

# AITBC Local Setup Script
# Sets up AITBC services on a new host with systemd

set -e

# Parse command line arguments
OPEN_ISLAND_HUB=""
NODE_ID=""
SKIP_INTERACTIVE=false
FORCE_SETUP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --open-island)
            OPEN_ISLAND_HUB="$2"
            SKIP_INTERACTIVE=true
            shift 2
            ;;
        --node-id)
            NODE_ID="$2"
            shift 2
            ;;
        --force)
            FORCE_SETUP=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --open-island HUB_URL  Configure as follower to specified hub (non-interactive)"
            echo "  --node-id NODE_ID      Set node identity (required with --open-island)"
            echo "  --force                Re-run full setup even if already installed"
            echo "  --help                 Show this help message"
            echo ""
            echo "Example:"
            echo "  $0 --open-island https://hub.aitbc.bubuit.net --node-id my-node"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_COMMON_PATH="$SCRIPT_DIR/utils/deploy_common.sh"
DEPLOY_COMMON_TEMP=""

if [ ! -f "$DEPLOY_COMMON_PATH" ]; then
    DEPLOY_COMMON_TEMP="$(mktemp)"
    if ! curl -fsSL "https://raw.githubusercontent.com/oib/AITBC/main/scripts/utils/deploy_common.sh" -o "$DEPLOY_COMMON_TEMP"; then
        rm -f "$DEPLOY_COMMON_TEMP"
        echo "[ERROR] Failed to load shared deployment helper"
        exit 1
    fi

    DEPLOY_COMMON_PATH="$DEPLOY_COMMON_TEMP"
    trap 'rm -f "$DEPLOY_COMMON_TEMP"' EXIT
fi

source "$DEPLOY_COMMON_PATH"

HEALTH_CHECK_SCRIPT="/opt/aitbc/scripts/monitoring/health_check.sh"
LEGACY_HEALTH_CHECK_PATH="/opt/aitbc/health-check.sh"

# Determine the node role from config for service selection
# Roles: hub, follower, shop, customer
get_node_role() {
    local blockchain_mode="" market_role="" hardware_profile=""
    if [ -f "/etc/aitbc/blockchain.env" ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/blockchain.env 2>/dev/null
        blockchain_mode="$BLOCKCHAIN_MODE"
        market_role="$MARKET_ROLE"
        hardware_profile="$HARDWARE_PROFILE"
    fi
    if [ -f "/etc/aitbc/node.env" ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/node.env 2>/dev/null
        blockchain_mode="${blockchain_mode:-$BLOCKCHAIN_MODE}"
        market_role="${market_role:-$MARKET_ROLE}"
        hardware_profile="${hardware_profile:-$HARDWARE_PROFILE}"
    fi

    if [ "$blockchain_mode" = "hub" ]; then
        echo "hub"
    elif [ "$market_role" = "shop" ] && [ "$hardware_profile" = "gpu" ]; then
        echo "shop"
    elif [ "$market_role" = "customer" ]; then
        echo "customer"
    else
        echo "follower"
    fi
}

# Get the list of services to enable/start for a given node role
# Usage: get_services_for_role <role>
# Outputs space-separated service names (without .service suffix)
get_services_for_role() {
    local role="${1:-follower}"

    # Base services — always enabled on every node
    local base_services=(
        aitbc-blockchain-node
        aitbc-blockchain-rpc
        aitbc-wallet
        aitbc-recovery
        aitbc-monitoring
        aitbc-backup.timer
    )

    # Hub-specific services
    local hub_services=(
        aitbc-blockchain-p2p
        aitbc-coordinator-api
        aitbc-api-gateway
        aitbc-governance
        aitbc-exchange
        aitbc-marketplace
        aitbc-bridge-monitor
        aitbc-blockchain-event-bridge
        aitbc-hermes
        aitbc-agent-management
        aitbc-agent-coordinator
        aitbc-agent-daemon
        aitbc-blockchain-explorer
    )

    # Follower-specific services (in addition to base)
    local follower_services=(
        aitbc-blockchain-sync
        aitbc-blockchain-sync.timer
        aitbc-blockchain-explorer
    )

    # Shop-specific services (GPU provider, in addition to base)
    # coordinator-api is required by the miner (COORDINATOR_URL=http://localhost:8203)
    local shop_services=(
        aitbc-gpu
        aitbc-miner
        aitbc-coordinator-api
    )

    # Customer nodes: base only (interacts with hub via CLI)
    # No additional services

    local services=("${base_services[@]}")

    case "$role" in
        hub)
            services+=("${hub_services[@]}")
            ;;
        follower)
            services+=("${follower_services[@]}")
            ;;
        shop)
            services+=("${shop_services[@]}")
            # Shop nodes also need sync (they follow a hub)
            services+=("${follower_services[@]}")
            ;;
        customer)
            # Customer nodes: base only
            ;;
        *)
            warning "Unknown role '$role', defaulting to follower services"
            services+=("${follower_services[@]}")
            ;;
    esac

    echo "${services[@]}"
}

# Validate hub connection (only relevant for follower nodes)
validate_hub_connection() {
    if [ "$SKIP_INTERACTIVE" = true ] && [ -n "$OPEN_ISLAND_HUB" ]; then
        log "Validating connection to hub: $OPEN_ISLAND_HUB"
        if curl -sf "$OPEN_ISLAND_HUB/health" >/dev/null 2>&1; then
            success "Hub connection validated: $OPEN_ISLAND_HUB"
        else
            warning "Could not reach hub at $OPEN_ISLAND_HUB — services will retry on startup"
        fi
    else
        log "Skipping hub connection validation (hub node or interactive mode)"
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Install missing prerequisites
    local missing=()
    for cmd in python3 pip3 git systemctl node npm postgresql psql redis-server redis-cli; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    # Check for python3-venv package (not a command, but a package)
    if ! python3 -m venv --help >/dev/null 2>&1; then
        missing+=("python3-venv")
    fi

    if [ "${#missing[@]}" -gt 0 ]; then
        log "Installing missing prerequisites: ${missing[*]}"

        # Detect package manager
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update -qq
            for cmd in "${missing[@]}"; do
                case "$cmd" in
                    python3)
                        apt-get install -y python3 python3-pip python3-venv
                        ;;
                    pip3)
                        apt-get install -y python3-pip
                        ;;
                    git)
                        apt-get install -y git
                        ;;
                    systemctl)
                        apt-get install -y systemd
                        ;;
                    node)
                        # Install Node.js 24.x from NodeSource
                        curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
                        apt-get install -y nodejs
                        ;;
                    npm)
                        # npm comes with nodejs
                        curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
                        apt-get install -y nodejs
                        ;;
                    postgresql)
                        apt-get install -y postgresql postgresql-contrib
                        ;;
                    psql)
                        apt-get install -y postgresql-client
                        ;;
                    python3-venv)
                        apt-get install -y python3-venv
                        ;;
                    redis-server)
                        apt-get install -y redis-server
                        ;;
                    redis-cli)
                        apt-get install -y redis-tools
                        ;;
                    libpq-dev)
                        apt-get install -y libpq-dev
                        ;;
                esac
            done
        elif command -v yum >/dev/null 2>&1; then
            yum install -y python3 python3-pip python3-venv git systemd postgresql postgresql-server postgresql-contrib redis postgresql-devel
            # Install Node.js 24.x
            curl -fsSL https://rpm.nodesource.com/setup_24.x | bash -
            yum install -y nodejs
        else
            error "Unsupported package manager. Please install manually: ${missing[*]}"
        fi

        log "Prerequisites installed"
    fi

    # Verify versions after installation
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    require_min_version "$python_version" "3.13.5" "Python"

    node_version=$(node -v | sed 's/v//')
    require_min_version "$node_version" "24.14.0" "Node.js"

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
    git clone https://github.com/oib/AITBC.git aitbc || error "Failed to clone repository"

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
    # Fix data directory permissions for blockchain-node service (runs as aitbc user)
    chown -R aitbc:aitbc /var/lib/aitbc/data 2>/dev/null || log "aitbc user not yet created — will chown after service users are set up"
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

# Setup service users for security isolation
setup_service_users() {
    log "Setting up service users for security isolation..."

    # Create primary aitbc group (used by all systemd services as Group=aitbc)
    if ! getent group aitbc >/dev/null 2>&1; then
        log "Creating aitbc group..."
        groupadd aitbc || warning "Failed to create aitbc group (may already exist)"
    else
        log "aitbc group already exists"
    fi

    # Create primary aitbc user (all services run as User=aitbc)
    if ! id aitbc >/dev/null 2>&1; then
        log "Creating aitbc user (primary service user)..."
        useradd -r -s /bin/false -g aitbc -d /opt/aitbc aitbc || warning "Failed to create aitbc user (may already exist)"
    else
        log "aitbc user already exists"
    fi

    # Create service group for supplementary isolation
    if ! getent group aitbc-services >/dev/null 2>&1; then
        log "Creating aitbc-services group..."
        groupadd aitbc-services || warning "Failed to create aitbc-services group (may already exist)"
    else
        log "aitbc-services group already exists"
    fi

    # Create specialized service users for security isolation
    service_users=(
        "aitbc-public:Public exposure services (API Gateway, Edge, Whisper)"
        "aitbc-internal:Internal services (Marketplace, Hermes, Agent Coordinator)"
        "aitbc-blockchain:Blockchain services (Node, P2P, RPC)"
        "aitbc-gpu:GPU service (needs video group)"
        "aitbc-wallet:Wallet service (keystore access)"
    )

    for user_info in "${service_users[@]}"; do
        IFS=':' read -r username description <<< "$user_info"

        if ! id "$username" >/dev/null 2>&1; then
            log "Creating user: $username ($description)"
            useradd -r -s /bin/false -g aitbc-services "$username" || warning "Failed to create user $username (may already exist)"
        else
            log "User $username already exists"
        fi
    done

    # Add supplementary groups for specialized users
    if id aitbc-gpu >/dev/null 2>&1; then
        log "Adding aitbc-gpu to video group..."
        usermod -a -G video aitbc-gpu 2>/dev/null || warning "Failed to add aitbc-gpu to video group"
    fi

    if id aitbc-public >/dev/null 2>&1; then
        log "Adding aitbc-public to video and audio groups (for whisper)..."
        usermod -a -G video aitbc-public 2>/dev/null || warning "Failed to add aitbc-public to video group"
        usermod -a -G audio aitbc-public 2>/dev/null || warning "Failed to add aitbc-public to audio group"
    fi

    # Create additional directories for service users
    log "Creating service-specific directories..."
    mkdir -p /var/lib/aitbc/wallets
    mkdir -p /var/lib/aitbc/whisper-cache

    # Set ownership for service-specific directories
    chown -R aitbc-wallet:aitbc-services /var/lib/aitbc/wallets
    chown -R aitbc-public:aitbc-services /var/lib/aitbc/whisper-cache
    chmod 750 /var/lib/aitbc/wallets
    chmod 750 /var/lib/aitbc/whisper-cache

    # Fix data directory ownership now that aitbc user exists
    # (setup_runtime_directories runs before this step, so chown may have been skipped)
    chown -R aitbc:aitbc /var/lib/aitbc/data 2>/dev/null || true

    success "Service users setup completed"
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
        log "PostgreSQL service is not running, attempting to start..."
        systemctl start postgresql.service || {
            warning "Failed to start PostgreSQL service"
            warning "To start PostgreSQL manually: systemctl start postgresql.service"
            return 0
        }
        log "PostgreSQL service started successfully"
    fi

    # Use centralized database setup script if available
    if [ -f "/opt/aitbc/scripts/deployment/setup_postgresql_databases.sh" ]; then
        log "Using centralized PostgreSQL setup script..."
        /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh
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
            "aitbc_mempool:aitbc_mempool"
        )

        for db_user in "${databases[@]}"; do
            db_name=$(echo "$db_user" | cut -d':' -f1)
            db_user=$(echo "$db_user" | cut -d':' -f2)

            # Generate secure password for this user
            db_password=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 2>/dev/null || echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)")

            # Store password in credentials directory
            echo "$db_password" > /etc/aitbc/credentials/postgres_${db_user}_password
            chmod 600 /etc/aitbc/credentials/postgres_${db_user}_password

            # Create user if not exists with secure password
            sudo -u postgres psql -c "DO \$\$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
                    CREATE USER ${db_user} WITH PASSWORD '${db_password}';
                ELSE
                    ALTER USER ${db_user} WITH PASSWORD '${db_password}';
                END IF;
            END
            \$\$;" 2>/dev/null || true

            # Create database if not exists
            sudo -u postgres psql -c "SELECT 'CREATE DATABASE ${db_name} OWNER ${db_user}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name}')\\gexec" 2>/dev/null || true

            # Grant privileges
            sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};" 2>/dev/null || true

            log "Database ${db_name} setup complete with secure password"
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

# Setup node profiles
# Prompts user to configure node profiles that determine which services run:
# - BLOCKCHAIN_MODE: follower (receives blocks) or hub (produces blocks)
# - MARKET_ROLE: customer (consumes GPU) or shop (provides GPU)
# - HARDWARE_PROFILE: nogpu (no GPU) or gpu (GPU available)
# These profiles are set in /etc/aitbc/blockchain.env (read by blockchain node)
setup_node_profiles() {
    log "Setting up node profiles..."

    # Skip interactive prompts if blockchain.env already exists or --open-island was used
    if [ "$SKIP_INTERACTIVE" = true ] || [ -f "/etc/aitbc/blockchain.env" ]; then
        log "Skipping interactive prompts (configuration already exists or --open-island mode)"
        if [ -f "/etc/aitbc/blockchain.env" ]; then
            log "Using existing /etc/aitbc/blockchain.env"
        else
            log "Using default follower configuration for open island"
            BLOCKCHAIN_MODE="follower"
            MARKET_ROLE="customer"
            HARDWARE_PROFILE="nogpu"

            set_env_blockchain() {
                local key="$1"
                local value="$2"

                if grep -q "^${key}=" /etc/aitbc/blockchain.env; then
                    sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/blockchain.env
                else
                    echo "${key}=${value}" >> /etc/aitbc/blockchain.env
                fi
            }

            set_env_blockchain "BLOCKCHAIN_MODE" "$BLOCKCHAIN_MODE"
            set_env_blockchain "MARKET_ROLE" "$MARKET_ROLE"
            set_env_blockchain "HARDWARE_PROFILE" "$HARDWARE_PROFILE"
        fi
        success "Node profiles configured (non-interactive)"
        return 0
    fi

    # Prompt for blockchain mode
    echo ""
    echo "=== Blockchain Mode Selection ==="
    echo "Select the blockchain mode for this node:"
    echo "  1) follower - Receives blocks from hub (default for open island)"
    echo "  2) hub     - Produces and broadcasts blocks"
    read -p "Enter choice [1-2] (default: 1): " blockchain_choice
    blockchain_choice=${blockchain_choice:-1}

    case "$blockchain_choice" in
        1)
            BLOCKCHAIN_MODE="follower"
            ;;
        2)
            BLOCKCHAIN_MODE="hub"
            ;;
        *)
            log "Invalid choice, defaulting to follower"
            BLOCKCHAIN_MODE="follower"
            ;;
    esac

    # Prompt for market role
    echo ""
    echo "=== Market Role Selection ==="
    echo "Select the market role for this node:"
    echo "  1) customer - Consumes GPU resources (default)"
    echo "  2) shop     - Provides GPU resources"
    read -p "Enter choice [1-2] (default: 1): " market_choice
    market_choice=${market_choice:-1}

    case "$market_choice" in
        1)
            MARKET_ROLE="customer"
            ;;
        2)
            MARKET_ROLE="shop"
            ;;
        *)
            log "Invalid choice, defaulting to customer"
            MARKET_ROLE="customer"
            ;;
    esac

    # Prompt for hardware profile
    echo ""
    echo "=== Hardware Profile Selection ==="
    echo "Select the hardware profile for this node:"
    echo "  1) nogpu - No GPU available (default)"
    echo "  2) gpu   - GPU available for compute"
    read -p "Enter choice [1-2] (default: 1): " hardware_choice
    hardware_choice=${hardware_choice:-1}

    case "$hardware_choice" in
        1)
            HARDWARE_PROFILE="nogpu"
            ;;
        2)
            HARDWARE_PROFILE="gpu"
            ;;
        *)
            log "Invalid choice, defaulting to nogpu"
            HARDWARE_PROFILE="nogpu"
            ;;
    esac

    # Set profiles in blockchain.env
    set_env_blockchain() {
        local key="$1"
        local value="$2"

        if grep -q "^${key}=" /etc/aitbc/blockchain.env; then
            sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/blockchain.env
        else
            echo "${key}=${value}" >> /etc/aitbc/blockchain.env
        fi
    }

    set_env_blockchain "BLOCKCHAIN_MODE" "$BLOCKCHAIN_MODE"
    set_env_blockchain "MARKET_ROLE" "$MARKET_ROLE"
    set_env_blockchain "HARDWARE_PROFILE" "$HARDWARE_PROFILE"

    log "Node profiles configured:"
    log "  BLOCKCHAIN_MODE: $BLOCKCHAIN_MODE"
    log "  MARKET_ROLE: $MARKET_ROLE"
    log "  HARDWARE_PROFILE: $HARDWARE_PROFILE"

    success "Node profiles setup completed"
}

# Setup unique node identities
setup_node_identities() {
    log "Setting up unique node identities..."

    set_env() {
        local key="$1"
        local value="$2"

        if grep -q "^${key}=" /etc/aitbc/blockchain.env; then
            sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/blockchain.env
        else
            echo "${key}=${value}" >> /etc/aitbc/blockchain.env
        fi
    }

    # Generate unique IDs
    PROPOSER_ID="ait1$(generate_uuid | tr -d '-')"
    P2P_NODE_ID="node-$(generate_uuid | tr -d '-')"

    # Use pre-configured example if available AND no existing config, otherwise create minimal config
    if [ -f "/etc/aitbc/blockchain.env" ]; then
        # Existing config — preserve it, only add missing IDs
        log "Preserving existing /etc/aitbc/blockchain.env"
        if ! grep -q "^proposer_id=" /etc/aitbc/blockchain.env; then
            set_env proposer_id "$PROPOSER_ID"
            log "Added unique proposer_id to /etc/aitbc/blockchain.env"
        else
            log "proposer_id already exists in /etc/aitbc/blockchain.env"
        fi
    elif [ -f "/opt/aitbc/examples/blockchain.env.open-island" ]; then
        log "Using pre-configured open-island example as base..."
        cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
        # Override with unique IDs
        set_env proposer_id "$PROPOSER_ID"
        set_env p2p_node_id "$P2P_NODE_ID"
        log "Configured blockchain.env from open-island example with unique IDs"
    else
        log "Creating minimal blockchain.env with unique IDs..."
        cat > /etc/aitbc/blockchain.env << EOF
# AITBC Blockchain Configuration
# Auto-generated unique node identities
proposer_id=$PROPOSER_ID
p2p_node_id=$P2P_NODE_ID
gossip_backend=broadcast
gossip_broadcast_url=redis://localhost:6379
default_peer_rpc_url=http://127.0.0.1:8202
EOF
        log "Created /etc/aitbc/blockchain.env with unique IDs"
    fi

    # Ensure blockchain gossip defaults exist
    set_env gossip_backend broadcast
    set_env gossip_broadcast_url redis://localhost:6379
    set_env default_peer_rpc_url http://127.0.0.1:8202

    # Use pre-configured node.env example if available AND no existing config
    if [ -f "/etc/aitbc/node.env" ]; then
        # Existing config — preserve it, only add missing p2p_node_id
        log "Preserving existing /etc/aitbc/node.env"
        if ! grep -q "^p2p_node_id=" /etc/aitbc/node.env; then
            echo "p2p_node_id=$P2P_NODE_ID" >> /etc/aitbc/node.env
            log "Added unique p2p_node_id to /etc/aitbc/node.env"
        else
            log "p2p_node_id already exists in /etc/aitbc/node.env"
        fi
    elif [ -f "/opt/aitbc/examples/node.env.open-island" ]; then
        log "Using pre-configured open-island node.env example as base..."
        cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
        # Override with unique NODE_ID and p2p_node_id
        sed -i "s|^NODE_ID=.*|NODE_ID=aitbc|" /etc/aitbc/node.env
        sed -i "s|^p2p_node_id=.*|p2p_node_id=$P2P_NODE_ID|" /etc/aitbc/node.env
        log "Configured node.env from open-island example with unique IDs"
    else
        log "Creating minimal node.env with unique p2p_node_id..."
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
    fi

    success "Node identities setup completed"
}

# Setup secure credentials
setup_credentials() {
    log "Setting up secure credentials..."

    # Generate secure secrets if they don't exist
    if [ ! -f "/etc/aitbc/credentials/api_hash_secret" ]; then
        log "Generating API_KEY_HASH_SECRET..."
        if python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/api_hash_secret 2>/dev/null; then
            chmod 600 /etc/aitbc/credentials/api_hash_secret
            log "Generated API_KEY_HASH_SECRET"
        else
            warning "Failed to generate API_KEY_HASH_SECRET"
            warning "Using fallback random value"
            openssl rand -hex 32 > /etc/aitbc/credentials/api_hash_secret 2>/dev/null || {
                warning "OpenSSL also failed, using timestamp-based fallback"
                echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)" > /etc/aitbc/credentials/api_hash_secret
            }
            chmod 600 /etc/aitbc/credentials/api_hash_secret
        fi
    else
        log "API_KEY_HASH_SECRET already exists"
    fi

    if [ ! -f "/etc/aitbc/credentials/keystore_password" ]; then
        log "Generating keystore password..."
        if python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/keystore_password 2>/dev/null; then
            chmod 600 /etc/aitbc/credentials/keystore_password
            log "Generated keystore password"
        else
            warning "Failed to generate keystore password"
            warning "Using fallback random value"
            openssl rand -hex 32 > /etc/aitbc/credentials/keystore_password 2>/dev/null || {
                warning "OpenSSL also failed, using timestamp-based fallback"
                echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)" > /etc/aitbc/credentials/keystore_password
            }
            chmod 600 /etc/aitbc/credentials/keystore_password
        fi
    else
        log "Keystore password already exists"
    fi

    # Generate JWT authentication secrets (required for JWT token signing/verification)
    if [ ! -f "/etc/aitbc/credentials/jwt_secret" ]; then
        log "Generating JWT_SECRET..."
        if python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/jwt_secret 2>/dev/null; then
            chmod 600 /etc/aitbc/credentials/jwt_secret
            log "Generated JWT_SECRET"
        else
            warning "Failed to generate JWT_SECRET"
            openssl rand -hex 32 > /etc/aitbc/credentials/jwt_secret 2>/dev/null || {
                warning "OpenSSL also failed, using timestamp-based fallback"
                echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)" > /etc/aitbc/credentials/jwt_secret
            }
            chmod 600 /etc/aitbc/credentials/jwt_secret
        fi
    else
        log "JWT_SECRET already exists"
    fi

    if [ ! -f "/etc/aitbc/credentials/secret_key" ]; then
        log "Generating SECRET_KEY..."
        if python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/aitbc/credentials/secret_key 2>/dev/null; then
            chmod 600 /etc/aitbc/credentials/secret_key
            log "Generated SECRET_KEY"
        else
            warning "Failed to generate SECRET_KEY"
            openssl rand -hex 32 > /etc/aitbc/credentials/secret_key 2>/dev/null || {
                warning "OpenSSL also failed, using timestamp-based fallback"
                echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)" > /etc/aitbc/credentials/secret_key
            }
            chmod 600 /etc/aitbc/credentials/secret_key
        fi
    else
        log "SECRET_KEY already exists"
    fi

    # Copy proposer_id from blockchain.env to credentials
    if [ -f "/etc/aitbc/blockchain.env" ] && grep -q "^proposer_id=" /etc/aitbc/blockchain.env; then
        grep "^proposer_id=" /etc/aitbc/blockchain.env | cut -d'=' -f2 > /etc/aitbc/credentials/proposer_id
        chmod 600 /etc/aitbc/credentials/proposer_id
        log "Copied proposer_id to credentials"
    else
        log "No proposer_id found in /etc/aitbc/blockchain.env, generating random ID"
        if python3 -c "import secrets; print(secrets.token_hex(16))" > /etc/aitbc/credentials/proposer_id 2>/dev/null; then
            chmod 600 /etc/aitbc/credentials/proposer_id
            log "Generated random proposer_id"
        else
            warning "Failed to generate proposer_id"
            echo "proposer-$(date +%s)-$(head -c 8 /dev/urandom | xxd -p)" > /etc/aitbc/credentials/proposer_id
            chmod 600 /etc/aitbc/credentials/proposer_id
            log "Generated fallback proposer_id"
        fi
    fi

    # Add API_KEY_HASH_SECRET to blockchain.env if not present
    if [ -f "/etc/aitbc/blockchain.env" ] && ! grep -q "^API_KEY_HASH_SECRET=" /etc/aitbc/blockchain.env; then
        echo "API_KEY_HASH_SECRET=$(cat /etc/aitbc/credentials/api_hash_secret)" >> /etc/aitbc/blockchain.env
        log "Added API_KEY_HASH_SECRET to blockchain.env"
    fi

    # Write JWT_SECRET and API_KEY_HASH_SECRET to coordinator-api %N.env file
    # systemd %N expands to unit name without .service suffix
    local COORD_ENV="/etc/aitbc/aitbc-coordinator-api.env"
    mkdir -p /etc/aitbc
    if [ -f "$COORD_ENV" ]; then
        # Update existing values or append
        if grep -q "^JWT_SECRET=" "$COORD_ENV"; then
            sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(cat /etc/aitbc/credentials/jwt_secret)|g" "$COORD_ENV"
        else
            echo "JWT_SECRET=$(cat /etc/aitbc/credentials/jwt_secret)" >> "$COORD_ENV"
        fi
        if grep -q "^API_KEY_HASH_SECRET=" "$COORD_ENV"; then
            sed -i "s|^API_KEY_HASH_SECRET=.*|API_KEY_HASH_SECRET=$(cat /etc/aitbc/credentials/api_hash_secret)|g" "$COORD_ENV"
        else
            echo "API_KEY_HASH_SECRET=$(cat /etc/aitbc/credentials/api_hash_secret)" >> "$COORD_ENV"
        fi
    else
        cat > "$COORD_ENV" << EOF
# AITBC Coordinator API service-specific configuration
JWT_SECRET=$(cat /etc/aitbc/credentials/jwt_secret)
API_KEY_HASH_SECRET=$(cat /etc/aitbc/credentials/api_hash_secret)
REDIS_URL=redis://localhost:6379/0
EOF
    fi
    log "Wrote JWT_SECRET and API_KEY_HASH_SECRET to $COORD_ENV"

    # Generate runtime secrets file for systemd services
    log "Generating runtime secrets file..."
    if [ -f "/opt/aitbc/scripts/utils/load-keystore-secrets.sh" ]; then
        /opt/aitbc/scripts/utils/load-keystore-secrets.sh || {
            warning "Failed to generate runtime secrets file"
            warning "Services may fail to start without /run/aitbc/secrets/.env"
        }
    else
        warning "load-keystore-secrets.sh not found, skipping runtime secrets generation"
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
        if ! python3 -m venv venv; then
            warning "Failed to create virtual environment"
            warning "Checking if configs exist that might need cleanup..."

            # Check for existing configs that might have been created before venv failure
            if [ -d "/etc/aitbc" ] && [ "$(ls -A /etc/aitbc 2>/dev/null)" ]; then
                warning "Found existing configs in /etc/aitbc"
                warning "Virtual environment creation failed, but configs exist"
                warning "You may need to manually create the venv or remove configs and retry"
                warning "Manual venv creation: cd /opt/aitbc && python3 -m venv venv"
                # Don't fail the entire setup, just warn
                return 0
            else
                error "Failed to create virtual environment and no existing configs found"
                error "Please ensure python3-venv is installed: apt install python3-venv"
            fi
        fi

        # Activate venv with error handling
        if ! source venv/bin/activate; then
            warning "Failed to activate virtual environment"
            warning "Virtual environment may be corrupted"
            warning "Manual fix: rm -rf /opt/aitbc/venv && python3 -m venv /opt/aitbc/venv"
            return 0
        fi

        # Upgrade pip with error handling
        if ! pip install --upgrade pip; then
            warning "Failed to upgrade pip in virtual environment"
            warning "Continuing with existing pip version"
        fi
    else
        log "Central virtual environment already exists, activating..."
        if ! source /opt/aitbc/venv/bin/activate; then
            warning "Failed to activate existing virtual environment"
            warning "Virtual environment may be corrupted"
            warning "Manual fix: rm -rf /opt/aitbc/venv && python3 -m venv /opt/aitbc/venv"
            return 0
        fi
    fi

    # Install dependencies using install-profiles.sh
    log "Installing dependencies using install-profiles.sh..."

    # Detect appropriate profile based on configuration
    local PROFILE="server-no-gpu"  # default

    # Check if install-profiles.sh exists
    if [ -f "/opt/aitbc/scripts/deployment/install-profiles.sh" ]; then
        log "Using install-profiles.sh for dependency installation..."

        # Try to detect profile from environment if available
        # Combines BLOCKCHAIN_MODE and MARKET_ROLE as independent axes
        if [ -f "/etc/aitbc/blockchain.env" ]; then
            source /etc/aitbc/blockchain.env
            local profile_parts=""
            [ "$BLOCKCHAIN_MODE" = "hub" ] && profile_parts="hub" || profile_parts="follower"
            if [ "$MARKET_ROLE" = "shop" ] && [ "$HARDWARE_PROFILE" = "gpu" ]; then
                profile_parts="${profile_parts}-shop-gpu"
            elif [ "$MARKET_ROLE" = "shop" ]; then
                profile_parts="${profile_parts}-shop"
            elif [ "$HARDWARE_PROFILE" = "gpu" ]; then
                profile_parts="${profile_parts}-gpu"
            else
                profile_parts="${profile_parts}-customer"
            fi
            PROFILE="$profile_parts"
        fi

        log "Installing profile: $PROFILE"
        /opt/aitbc/scripts/deployment/install-profiles.sh "$PROFILE" || warning "Failed to install profile $PROFILE"
    else
        log "install-profiles.sh not found, using manual installation..."

        # Fallback to manual installation
        if [ -f "/opt/aitbc/requirements.txt" ]; then
            log "Installing core production dependencies..."
            pip install -r /opt/aitbc/requirements.txt || warning "Failed to install core dependencies"
        else
            warning "requirements.txt not found, installing critical dependencies manually..."
            pip install fastapi uvicorn sqlmodel || warning "Failed to install core packages"
        fi

        # Install development dependencies (optional for production)
        if [ -f "/opt/aitbc/requirements-dev.txt" ]; then
            log "Installing development dependencies..."
            pip install -r /opt/aitbc/requirements-dev.txt || warning "Failed to install dev dependencies"
        fi

        # Install critical PostgreSQL driver
        log "Installing psycopg2 for PostgreSQL support..."
        pip install psycopg2-binary || warning "Failed to install psycopg2-binary"
    fi

    # Install AITBC CLI
    log "Installing AITBC CLI..."
    if [ -d "/opt/aitbc/cli" ]; then
        cd /opt/aitbc/cli
        pip install -e . || warning "Failed to install AITBC CLI"
        log "AITBC CLI installed"
    else
        warning "CLI directory not found at /opt/aitbc/cli"
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
        # Install services based on node role
        local role
        role=$(get_node_role)
        local role_services
        read -ra role_services <<< "$(get_services_for_role "$role")"
        log "Installing ${#role_services[@]} services for role '$role'..."

        for svc_base in "${role_services[@]}"; do
            # Handle both .service and .timer units
            if [[ "$svc_base" == *.timer ]]; then
                local unit="${svc_base}"
            else
                local unit="${svc_base}.service"
            fi
            # Find unit file in app directories
            svc_file=$(find /opt/aitbc/apps /opt/aitbc/scripts -name "$unit" -print -quit 2>/dev/null)
            if [ -n "$svc_file" ]; then
                log "Installing $unit..."
                ln -sf "$svc_file" /etc/systemd/system/
            else
                warning "Unit file not found: $unit"
            fi
        done

        # Reload systemd
        systemctl daemon-reload
    fi

    # Add aitbc CLI to PATH
    log "Adding aitbc CLI to system PATH..."
    # Create wrapper script in /usr/local/bin/aitbc
    cat > /usr/local/bin/aitbc << 'EOF'
#!/bin/bash
/opt/aitbc/venv/bin/python -m aitbc_cli.core.main "$@"
EOF
    chmod +x /usr/local/bin/aitbc
    log "aitbc CLI installed to /usr/local/bin/aitbc"

    success "Systemd services installed"
}

# Setup backup service
setup_backup() {
    log "Setting up backup service..."

    local backup_script="/opt/aitbc/scripts/maintenance/aitbc-backup.sh"
    local backup_service="/opt/aitbc/scripts/maintenance/aitbc-backup.service"
    local backup_timer="/opt/aitbc/scripts/maintenance/aitbc-backup.timer"

    if [ ! -f "$backup_script" ]; then
        warning "Backup script not found: $backup_script"
        return 0
    fi

    # Make script executable
    chmod +x "$backup_script"

    # Create backup directory
    mkdir -p /var/backups/aitbc

    # Link service and timer files if they exist
    if [ -f "$backup_service" ]; then
        ln -sf "$backup_service" /etc/systemd/system/
    else
        warning "Backup service file not found: $backup_service"
    fi

    if [ -f "$backup_timer" ]; then
        ln -sf "$backup_timer" /etc/systemd/system/
    else
        warning "Backup timer file not found: $backup_timer"
    fi

    systemctl daemon-reload

    # Enable and start the timer
    systemctl enable aitbc-backup.timer 2>/dev/null && log "  Backup timer enabled" || warning "  Could not enable backup timer"
    systemctl start aitbc-backup.timer 2>/dev/null && log "  Backup timer started" || warning "  Could not start backup timer"

    success "Backup service configured (daily at 01:00, 30-day retention)"
}

prepare_health_check() {
    log "Preparing health check script..."

    if [ ! -f "$HEALTH_CHECK_SCRIPT" ]; then
        error "Health check script not found: $HEALTH_CHECK_SCRIPT"
    fi

    chmod +x "$HEALTH_CHECK_SCRIPT"
    ln -sf "$HEALTH_CHECK_SCRIPT" "$LEGACY_HEALTH_CHECK_PATH"

    success "Health check script ready"
}

# Start services
start_services() {
    log "Starting AITBC services..."

    local role
    role=$(get_node_role)
    log "Node role: $role"

    # Get services for this role
    local services
    read -ra services <<< "$(get_services_for_role "$role")"
    log "Starting ${#services[@]} services for role '$role'..."

    local failed=()
    for svc in "${services[@]}"; do
        if systemctl start "$svc" 2>/dev/null; then
            log "  Started: $svc"
        else
            warning "  Failed to start: $svc"
            failed+=("$svc")
        fi
    done

    # Wait for services to initialize
    sleep 10

    # Report status
    local active_count=0
    for svc in "${services[@]}"; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            ((active_count++))
        fi
    done
    log "Services active: ${active_count}/${#services[@]}"

    if [ "${#failed[@]}" -gt 0 ]; then
        warning "Failed services: ${failed[*]}"
        warning "Check logs: journalctl -u <service-name> -f"
    fi

    # Run health check
    "$HEALTH_CHECK_SCRIPT" || warning "Health check reported issues"
}

# Setup auto-start
setup_autostart() {
    log "Setting up auto-start..."

    local role
    role=$(get_node_role)
    log "Node role: $role"

    local services
    read -ra services <<< "$(get_services_for_role "$role")"
    log "Enabling ${#services[@]} services for role '$role'..."

    for svc in "${services[@]}"; do
        systemctl enable "$svc" 2>/dev/null && log "  Enabled: $svc" || warning "  Could not enable: $svc"
    done

    success "Auto-start configured"
}

# Main function
main() {
    echo "=== AITBC SETUP STARTED ==="
    log "Starting AITBC setup..."

    # If already installed, forward to update.sh unless --force was given.
    # Signals of an existing install: /etc/aitbc/node.env + /opt/aitbc/venv
    if [ "$FORCE_SETUP" = "false" ] \
       && [ -f /etc/aitbc/node.env ] \
       && [ -d /opt/aitbc/venv ]; then
        local update_script="/opt/aitbc/scripts/deployment/update.sh"
        warning "AITBC is already installed on this node (/etc/aitbc/node.env + /opt/aitbc/venv exist)"
        if [ -x "$update_script" ]; then
            log "Forwarding to update.sh (use --force to re-run full setup)..."
            exec "$update_script"
        else
            warning "update.sh not found at $update_script — continuing with full setup"
        fi
    fi

    echo "[STEP 1/12] Checking root privileges..."
    check_root
    echo "[STEP 1/12] ✓ Root privileges verified"

    echo "[STEP 2/12] Checking prerequisites..."
    check_prerequisites
    echo "[STEP 2/12] ✓ Prerequisites check passed"

    echo "[STEP 3/12] Cloning repository..."
    clone_repo
    echo "[STEP 3/12] ✓ Repository cloned"

    echo "[STEP 4/12] Setting up runtime directories..."
    setup_runtime_directories
    echo "[STEP 4/12] ✓ Runtime directories created"

    echo "[STEP 5/12] Setting up service users..."
    setup_service_users
    echo "[STEP 5/12] ✓ Service users created"

    echo "[STEP 6/12] Setting up PostgreSQL databases..."
    setup_postgresql_databases
    echo "[STEP 6/12] ✓ PostgreSQL databases configured"

    echo "[STEP 7/12] Setting up node profiles..."
    setup_node_profiles
    echo "[STEP 7/12] ✓ Node profiles configured"

    echo "[STEP 8/12] Setting up node identities..."
    setup_node_identities
    echo "[STEP 8/12] ✓ Node identities configured"

    echo "[STEP 9/12] Setting up credentials..."
    setup_credentials
    echo "[STEP 9/12] ✓ Credentials configured"

    echo "[STEP 10/12] Setting up virtual environments..."
    setup_venvs
    echo "[STEP 10/12] ✓ Virtual environments created"

    echo "[STEP 11/12] Installing systemd services..."
    install_services
    echo "[STEP 11/12] ✓ Systemd services installed"

    echo "[STEP 12/12] Setting up backup service..."
    setup_backup
    echo "[STEP 12/12] ✓ Backup service configured"

    echo "[PREPARING] Preparing health check..."
    echo "[VALIDATING] Validating hub connection..."
    validate_hub_connection
    echo "[VALIDATING] ✓ Hub connection validated"
    prepare_health_check
    echo "[PREPARING] ✓ Health check prepared"

    echo "[STARTING] Starting AITBC services..."
    start_services
    echo "[STARTING] ✓ Services started"

    echo "[AUTOSTART] Configuring auto-start..."
    setup_autostart
    echo "[AUTOSTART] ✓ Auto-start configured"

    success "AITBC setup completed!"
    echo "=== AITBC SETUP COMPLETED ==="
    echo ""
    echo "Service Information:"
    echo "  Wallet API: http://localhost:8108/health"
    echo "  Exchange API: http://localhost:8106/api/health"
    echo "  Coordinator API: http://localhost:8203/health"
    echo "  API Gateway: http://localhost:8201/health"
    echo "  Blockchain RPC: http://localhost:8202/health"
    echo "  Event Bridge: http://localhost:8205/health"
    echo ""
    echo "Runtime Directories:"
    echo "  Keystore: /var/lib/aitbc/keystore/"
    echo "  Data: /var/lib/aitbc/data/"
    echo "  Logs: /var/log/aitbc/"
    echo "  Config: /etc/aitbc/"
    echo "  Credentials: /etc/aitbc/credentials/ (600 permissions)"
    echo "  Runtime secrets: /run/aitbc/secrets/ (tmpfs)"
    echo "  Backups: /var/backups/aitbc/ (30-day retention)"
    echo ""
    echo "Management Commands:"
    echo "  Health check: $HEALTH_CHECK_SCRIPT"
    echo "  Load secrets: /opt/aitbc/scripts/utils/load-keystore-secrets.sh"
    echo "  Restart services: systemctl restart aitbc-wallet aitbc-coordinator-api aitbc-exchange"
    echo "  View logs: journalctl -u aitbc-wallet -f"
    echo "  Manual backup: /opt/aitbc/scripts/maintenance/aitbc-backup.sh"
    echo "  Backup timer: systemctl status aitbc-backup.timer"
    echo ""
    echo "Security Notes:"
    echo "  - Secrets stored in /etc/aitbc/credentials/ with 600 permissions"
    echo "  - Services load secrets at runtime via systemd ExecStartPre"
    echo "  - API_KEY_HASH_SECRET required (no insecure default)"
    echo "  - Per-service env files in /etc/aitbc/<service-name>.env (systemd %N.env)"
    echo "  - DATABASE_URL includes credentials (generated by setup_postgresql_databases.sh)"
}

# Run main function
main "$@"
