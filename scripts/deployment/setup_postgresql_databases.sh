#!/bin/bash

# ============================================================================
# AITBC PostgreSQL Database Setup Script
# ============================================================================
# This script creates all PostgreSQL databases and users required for AITBC services
# ============================================================================

set -euo pipefail

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

# Does a PostgreSQL role already exist?
role_exists() {
    local out
    out=$(sudo -u postgres psql -tAc \
        "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '$1'")
    [ "$out" = "1" ]
}

# Merge a KEY=VALUE pair into an env file: update in place when the key
# already exists, append otherwise. Re-running this script must merge, not
# clobber -- a plain `cat >` wiped every unrelated key the operator had in
# the file.
set_env_key() {
    local file="$1"
    local key="$2"
    local value="$3"
    mkdir -p "$(dirname "$file")"
    if [ -f "$file" ] && grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|g" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Function to create user and database
setup_database() {
    local db_name=$1
    local db_user=$2
    local db_password="${3:-}"
    local cred_file="$CREDENTIALS_DIR/postgres_${db_user}_password"

    echo -e "${BLUE}Setting up ${db_name}...${NC}"

    mkdir -p "$CREDENTIALS_DIR"

    if role_exists "$db_user"; then
        # Keep the existing role AND its password: rotating on every run used
        # to invalidate the env files the services already had.
        if [ -f "$cred_file" ]; then
            db_password=$(cat "$cred_file")
            echo -e "${GREEN}✅ Role ${db_user} already exists; keeping its password${NC}"
        else
            db_password=""
            echo -e "${YELLOW}⚠️  Role ${db_user} exists but ${cred_file} is missing;${NC}"
            echo -e "${YELLOW}   its password is unknown -- env files are left unchanged.${NC}"
        fi
    else
        if [ -z "$db_password" ]; then
            db_password=$(generate_password)
        fi
        # -v ON_ERROR_STOP=1 plus set -e: a failed CREATE USER aborts the run
        # instead of being swallowed by `|| echo`.
        sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
            "CREATE USER ${db_user} WITH PASSWORD '${db_password}';"
        echo "$db_password" > "$cred_file"
        chmod 600 "$cred_file"
    fi

    # Create database if it does not exist
    if ! sudo -u postgres psql -tAc \
        "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -q '^1$'; then
        sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
            "CREATE DATABASE ${db_name} OWNER ${db_user};"
    fi

    # Grant privileges
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};"

    # Grant schema permissions
    sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${db_name}" -c \
        "ALTER SCHEMA public OWNER TO ${db_user};"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${db_name}" -c \
        "GRANT CREATE ON SCHEMA public TO ${db_user};"

    # Guard (BACKUP-PG-OWNER-1): reassign public-schema tables owned by a
    # foreign role (e.g. tables created by an early `sudo -u postgres` run)
    # to ${db_user}, so same-named-role operations — migrations, restores,
    # role-scoped dumps — see the whole schema. Idempotent.
    foreign_tables=$(sudo -u postgres psql -d "${db_name}" -tAc \
        "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner <> '${db_user}'")
    if [ "${foreign_tables}" != "0" ]; then
        echo "Reassigning ${foreign_tables} foreign-owned table(s) in ${db_name} to ${db_user}"
        sudo -u postgres psql -d "${db_name}" -tAc \
            "SELECT 'ALTER TABLE ' || quote_ident(tablename) || ' OWNER TO ${db_user};' FROM pg_tables WHERE schemaname='public' AND tableowner <> '${db_user}'" \
            | sudo -u postgres psql -d "${db_name}" >/dev/null
    fi

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

# Function to pin PostgreSQL to the loopback interface.
#
# This is the default and it is what every DSN in this repository expects:
# the coordinator, wallet, governance, pool-hub and mempool connection strings
# are all localhost or 127.0.0.1. Nothing here connects to another host's
# database, so there is no reason for the postmaster to be listening on the
# container bridge -- and on a flat bridge, listening there means every other
# container can reach 5432 with only pg_hba standing in the way.
enforce_local_only() {
    echo -e "${BLUE}Pinning PostgreSQL to localhost...${NC}"

    sudo sed -i -E "s/^[[:space:]]*#?[[:space:]]*listen_addresses[[:space:]]*=.*/listen_addresses = 'localhost'/" \
        /etc/postgresql/*/main/postgresql.conf

    sudo systemctl reload postgresql.service 2>/dev/null || sudo systemctl restart postgresql.service

    echo -e "${GREEN}✅ PostgreSQL listening on localhost only${NC}"
}

# Function to configure PostgreSQL for remote connections
configure_remote_connections() {
    # No default: the CIDR allowed to reach PostgreSQL is deployment-specific,
    # and a wrong guess here opens the database to the wrong network.
    local network_cidr="${1:?pass the CIDR allowed to connect, e.g. 10.0.0.0/24}"
    # Bind to one named address rather than '*'. On a flat container bridge the
    # two are very different: '*' also picks up every other interface the
    # container has, so a pg_hba mistake becomes reachable from everywhere
    # instead of from one subnet.
    local bind_addr="${2:?pass the address to bind, e.g. 10.0.0.7 (never '*')}"

    if [ "$bind_addr" = "*" ] || [ "$bind_addr" = "0.0.0.0" ]; then
        echo -e "${RED}Refusing to bind PostgreSQL to ${bind_addr}; pass a specific address${NC}" >&2
        return 1
    fi

    echo -e "${BLUE}Configuring PostgreSQL for remote connections...${NC}"

    # Update listen_addresses. Keep localhost in the list so local clients and
    # the maintenance scripts keep working.
    sudo sed -i -E "s/^[[:space:]]*#?[[:space:]]*listen_addresses[[:space:]]*=.*/listen_addresses = 'localhost,${bind_addr}'/" \
        /etc/postgresql/*/main/postgresql.conf

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

# Shared password for the aitbc_user role (coordinator, exchange, wallet).
# Reuse the stored password when the role already exists -- generating a new
# one every run used to rotate the role and invalidate the env files.
AITBC_USER_PASSWORD=""
if [ -f "$CREDENTIALS_DIR/postgres_aitbc_user_password" ]; then
    AITBC_USER_PASSWORD=$(cat "$CREDENTIALS_DIR/postgres_aitbc_user_password")
fi
if [ -z "$AITBC_USER_PASSWORD" ] && ! role_exists "aitbc_user"; then
    AITBC_USER_PASSWORD=$(generate_password)
fi

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
if [ -n "$AITBC_USER_PASSWORD" ]; then
    write_env_database_url "aitbc-coordinator-api" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_coordinator"
    write_env_database_url "aitbc-exchange" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_exchange"
    write_env_database_url "aitbc-wallet" "postgresql://aitbc_user:${AITBC_USER_PASSWORD}@localhost:5432/aitbc_wallet"
else
    echo -e "${YELLOW}⚠️  aitbc_user exists but its password is not in ${CREDENTIALS_DIR};${NC}"
    echo -e "${YELLOW}   leaving the DATABASE_URL env files unchanged.${NC}"
fi

# governance uses DB_USER/DB_PASS/DB_HOST/DB_PORT/DB_NAME format (not DATABASE_URL)
GOVERNANCE_PASS=$(cat "$CREDENTIALS_DIR/postgres_aitbc_governance_password" 2>/dev/null || echo "")
if [ -n "$GOVERNANCE_PASS" ]; then
    GOV_ENV="$ENV_DIR/aitbc-governance.env"
    if [ ! -f "$GOV_ENV" ]; then
        echo "# Database configuration for governance service" > "$GOV_ENV"
    fi
    set_env_key "$GOV_ENV" DB_TYPE postgresql
    set_env_key "$GOV_ENV" DB_HOST localhost
    set_env_key "$GOV_ENV" DB_PORT 5432
    set_env_key "$GOV_ENV" DB_NAME aitbc_governance
    set_env_key "$GOV_ENV" DB_USER aitbc_governance
    set_env_key "$GOV_ENV" DB_PASS "${GOVERNANCE_PASS}"
    set_env_key "$GOV_ENV" REDIS_URL "redis://localhost:6379/0"
    echo -e "${GREEN}✅ Wrote governance DB config to ${GOV_ENV}${NC}"
fi

# mempool uses MEMPOOL_DB_URL format
MEMPOOL_PASS=$(cat "$CREDENTIALS_DIR/postgres_aitbc_mempool_password" 2>/dev/null || echo "")
if [ -n "$MEMPOOL_PASS" ]; then
    MEMPOOL_ENV="$ENV_DIR/aitbc-blockchain-p2p.env"
    if [ ! -f "$MEMPOOL_ENV" ]; then
        echo "# Mempool database URL for P2P service" > "$MEMPOOL_ENV"
    fi
    set_env_key "$MEMPOOL_ENV" MEMPOOL_DB_URL \
        "postgresql+psycopg2://aitbc_mempool:${MEMPOOL_PASS}@localhost:5432/aitbc_mempool"
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
DB_LIST=$(sudo -u postgres psql -c "\l")
echo "$DB_LIST" | grep aitbc || echo "(no aitbc databases found)"

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
echo "PostgreSQL listens on localhost only. Every DSN this repository ships"
echo "expects that; remote access is opt-in and needs a reason."
echo ""
echo "To open it to one subnet anyway, run:"
echo "  $0 --remote-configure <network-cidr> <bind-address>"
echo "  Example: $0 --remote-configure 10.0.0.0/24 10.0.0.7"
echo ""

# Pin the postmaster to loopback unless the caller explicitly asks otherwise.
if [[ "${1:-}" == "--remote-configure" ]]; then
    network_cidr="${2:?pass the CIDR allowed to connect, e.g. 10.0.0.0/24}"
    bind_addr="${3:?pass the address to bind, e.g. 10.0.0.7 (never '*')}"
    configure_remote_connections "$network_cidr" "$bind_addr"
else
    enforce_local_only
fi
true
