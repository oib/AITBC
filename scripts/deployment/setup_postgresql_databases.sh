#!/bin/bash

# ============================================================================
# AITBC PostgreSQL Database Setup Script
# ============================================================================
# This script creates all PostgreSQL databases and users required for AITBC services
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directory for storing generated passwords
CREDENTIALS_DIR="/etc/aitbc/credentials"
ENV_DIR="/etc/aitbc"

echo -e "${BLUE}=== AITBC PostgreSQL Database Setup ===${NC}"
echo ""

# Generate a secure random password
generate_password() {
    python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || \
    openssl rand -base64 32 2>/dev/null || \
    echo "$(date +%s)-$(head -c 16 /dev/urandom | xxd -p)"
}

# Function to create user and database
setup_database() {
    local db_name=$1
    local db_user=$2
    local db_password=$3

    # Generate a secure password if not provided
    if [ -z "$db_password" ]; then
        db_password=$(generate_password)
    fi

    echo -e "${BLUE}Setting up ${db_name}...${NC}"

    # Create user if not exists, or update password if already exists
    sudo -u postgres psql -c "DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
            CREATE USER ${db_user} WITH PASSWORD '${db_password}';
        ELSE
            ALTER USER ${db_user} WITH PASSWORD '${db_password}';
        END IF;
    END
    \$\$;" 2>/dev/null || echo "User ${db_user} setup completed"

    # Create database if not exists
    sudo -u postgres psql -c "SELECT 'CREATE DATABASE ${db_name} OWNER ${db_user}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name}')\\gexec" 2>/dev/null || echo "Database ${db_name} already exists"

    # Grant privileges
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};" 2>/dev/null || true

    # Grant schema permissions
    sudo -u postgres psql -d ${db_name} -c "ALTER SCHEMA public OWNER TO ${db_user};" 2>/dev/null || true
    sudo -u postgres psql -d ${db_name} -c "GRANT CREATE ON SCHEMA public TO ${db_user};" 2>/dev/null || true

    # Store password in credentials directory
    mkdir -p "$CREDENTIALS_DIR"
    echo "$db_password" > "$CREDENTIALS_DIR/postgres_${db_user}_password"
    chmod 600 "$CREDENTIALS_DIR/postgres_${db_user}_password"

    echo -e "${GREEN}✅ ${db_name} setup complete${NC}"
}

# Function to write DATABASE_URL to a service's %N.env file
# systemd %N expands to the unit name without .service suffix
# Usage: write_env_database_url <service_name> <db_url>
write_env_database_url() {
    local service_name=$1
    local db_url=$2
    local env_file="$ENV_DIR/${service_name}.env"

    mkdir -p "$ENV_DIR"

    if [ -f "$env_file" ] && grep -q "^DATABASE_URL=" "$env_file"; then
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${db_url}|g" "$env_file"
    else
        echo "DATABASE_URL=${db_url}" >> "$env_file"
    fi

    echo -e "${GREEN}✅ Wrote DATABASE_URL to ${env_file}${NC}"
}

# Function to configure PostgreSQL for remote connections
configure_remote_connections() {
    local network_cidr=${1:-10.1.223.0/24}

    echo -e "${BLUE}Configuring PostgreSQL for remote connections...${NC}"

    # Update listen_addresses
    sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/*/main/postgresql.conf 2>/dev/null || echo "listen_addresses already configured"

    # Add pg_hba.conf rule if not exists
    if ! sudo grep -q "${network_cidr}" /etc/postgresql/*/main/pg_hba.conf 2>/dev/null; then
        sudo bash -c "echo \"host    all             all             ${network_cidr}          scram-sha-256\" >> /etc/postgresql/*/main/pg_hba.conf"
        echo -e "${GREEN}✅ Added pg_hba.conf rule for ${network_cidr}${NC}"
    else
        echo -e "${YELLOW}⚠️  pg_hba.conf rule already exists for ${network_cidr}${NC}"
    fi

    # Reload PostgreSQL
    sudo systemctl reload postgresql.service 2>/dev/null || sudo systemctl restart postgresql.service

    echo -e "${GREEN}✅ PostgreSQL remote connections configured${NC}"
}

# Main setup
echo -e "${BLUE}Creating databases and users...${NC}"
echo ""

# Generate a shared password for the aitbc_user role (used by coordinator, exchange, wallet)
AITBC_USER_PASSWORD=$(generate_password)

# AITBC core databases (shared user)
setup_database "aitbc_coordinator" "aitbc_user" "$AITBC_USER_PASSWORD"
setup_database "aitbc_exchange" "aitbc_user" "$AITBC_USER_PASSWORD"
setup_database "aitbc_wallet" "aitbc_user" "$AITBC_USER_PASSWORD"

# Service-specific databases (each gets its own user and password)
setup_database "aitbc_marketplace" "aitbc_marketplace"
setup_database "aitbc_governance" "aitbc_governance"
setup_database "aitbc_trading" "aitbc_trading"
setup_database "aitbc_gpu" "aitbc_gpu"
setup_database "aitbc_ai" "aitbc_ai"
setup_database "aitbc_mempool" "aitbc_mempool"

# Write DATABASE_URL to service %N.env files
# systemd %N expands to the unit name without .service suffix
# These files are referenced by EnvironmentFile=/etc/aitbc/%N.env in service units
echo ""
echo -e "${BLUE}Writing service environment files...${NC}"
write_env_database_url "aitbc-coordinator-api" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_coordinator"
write_env_database_url "aitbc-exchange" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_exchange"
write_env_database_url "aitbc-wallet" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_wallet"

# governance uses DB_USER/DB_PASS/DB_HOST/DB_PORT/DB_NAME format (not DATABASE_URL)
GOVERNANCE_PASS=$(cat "$CREDENTIALS_DIR/postgres_aitbc_governance_password" 2>/dev/null || echo "")
if [ -n "$GOVERNANCE_PASS" ]; then
    GOV_ENV="$ENV_DIR/aitbc-governance.env"
    mkdir -p "$ENV_DIR"
    cat > "$GOV_ENV" << EOF
# Database configuration for governance service
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aitbc_governance
DB_USER=aitbc_governance
DB_PASS=${GOVERNANCE_PASS}

# Redis configuration
REDIS_URL=redis://localhost:6379/0
EOF
    echo -e "${GREEN}✅ Wrote governance DB config to ${GOV_ENV}${NC}"
fi

# mempool uses MEMPOOL_DB_URL format
MEMPOOL_PASS=$(cat "$CREDENTIALS_DIR/postgres_aitbc_mempool_password" 2>/dev/null || echo "")
if [ -n "$MEMPOOL_PASS" ]; then
    MEMPOOL_ENV="$ENV_DIR/aitbc-blockchain-p2p.env"
    mkdir -p "$ENV_DIR"
    cat > "$MEMPOOL_ENV" << EOF
# Mempool database URL for P2P service
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:${MEMPOOL_PASS}@localhost:5432/aitbc_mempool
EOF
    echo -e "${GREEN}✅ Wrote mempool DB config to ${MEMPOOL_ENV}${NC}"

    # Also update MEMPOOL_DB_URL in node.env if it exists (blockchain-node reads it from there)
    NODE_ENV="$ENV_DIR/node.env"
    if [ -f "$NODE_ENV" ]; then
        NEW_MEMPOOL_URL="postgresql+psycopg2://aitbc_mempool:${MEMPOOL_PASS}@localhost:5432/aitbc_mempool"
        if grep -q "MEMPOOL_DB_URL=" "$NODE_ENV"; then
            sed -i "s|^MEMPOOL_DB_URL=.*|MEMPOOL_DB_URL=${NEW_MEMPOOL_URL}|" "$NODE_ENV"
            echo -e "${GREEN}✅ Updated MEMPOOL_DB_URL in ${NODE_ENV}${NC}"
        else
            echo "" >> "$NODE_ENV"
            echo "# Mempool database URL (auto-generated by setup_postgresql_databases.sh)" >> "$NODE_ENV"
            echo "MEMPOOL_DB_URL=${NEW_MEMPOOL_URL}" >> "$NODE_ENV"
            echo -e "${GREEN}✅ Added MEMPOOL_DB_URL to ${NODE_ENV}${NC}"
        fi
    fi
fi

echo ""
echo -e "${BLUE}=== Database Summary ===${NC}"
sudo -u postgres psql -c "\l" | grep aitbc

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Databases created:"
echo "  - aitbc_coordinator (user: aitbc_user)"
echo "  - aitbc_exchange (user: aitbc_user)"
echo "  - aitbc_wallet (user: aitbc_user)"
echo "  - aitbc_marketplace (user: aitbc_marketplace)"
echo "  - aitbc_governance (user: aitbc_governance)"
echo "  - aitbc_trading (user: aitbc_trading)"
echo "  - aitbc_gpu (user: aitbc_gpu)"
echo "  - aitbc_ai (user: aitbc_ai)"
echo "  - aitbc_mempool (user: aitbc_mempool)"
echo ""
echo "Service environment files written:"
echo "  - /etc/aitbc/aitbc-coordinator-api.env (DATABASE_URL)"
echo "  - /etc/aitbc/aitbc-exchange.env (DATABASE_URL)"
echo "  - /etc/aitbc/aitbc-wallet.env (DATABASE_URL)"
echo "  - /etc/aitbc/aitbc-governance.env (DB_USER/DB_PASS)"
echo "  - /etc/aitbc/aitbc-blockchain-p2p.env (MEMPOOL_DB_URL)"
echo ""
echo "Passwords stored in: $CREDENTIALS_DIR/postgres_<user>_password"
echo ""
echo "To configure PostgreSQL for remote connections, run:"
echo "  $0 --remote-configure [network-cidr]"
echo "  Example: $0 --remote-configure 10.1.223.0/24"
echo ""

# Handle optional remote configuration
if [[ "$1" == "--remote-configure" ]]; then
    network_cidr=${2:-10.1.223.0/24}
    configure_remote_connections "$network_cidr"
fi
