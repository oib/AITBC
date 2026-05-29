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

echo -e "${BLUE}=== AITBC PostgreSQL Database Setup ===${NC}"
echo ""

# Function to create user and database
setup_database() {
    local db_name=$1
    local db_user=$2
    local db_password=${3:-password}
    
    echo -e "${BLUE}Setting up ${db_name}...${NC}"
    
    # Create user if not exists
    sudo -u postgres psql -c "DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
            CREATE USER ${db_user} WITH PASSWORD '${db_password}';
        END IF;
    END
    \$\$;" 2>/dev/null || echo "User ${db_user} already exists"
    
    # Create database if not exists
    sudo -u postgres psql -c "SELECT 'CREATE DATABASE ${db_name} OWNER ${db_user}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name}')\\gexec" 2>/dev/null || echo "Database ${db_name} already exists"
    
    # Grant privileges
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};" 2>/dev/null || true
    
    # Grant schema permissions
    sudo -u postgres psql -d ${db_name} -c "ALTER SCHEMA public OWNER TO ${db_user};" 2>/dev/null || true
    sudo -u postgres psql -d ${db_name} -c "GRANT CREATE ON SCHEMA public TO ${db_user};" 2>/dev/null || true
    
    echo -e "${GREEN}✅ ${db_name} setup complete${NC}"
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

# AITBC core databases (shared user)
setup_database "aitbc_coordinator" "aitbc_user"
setup_database "aitbc_exchange" "aitbc_user"
setup_database "aitbc_wallet" "aitbc_user"

# Service-specific databases
setup_database "aitbc_marketplace" "aitbc_marketplace"
setup_database "aitbc_governance" "aitbc_governance"
setup_database "aitbc_trading" "aitbc_trading"
setup_database "aitbc_gpu" "aitbc_gpu"
setup_database "aitbc_ai" "aitbc_ai"
setup_database "aitbc_mempool" "aitbc_mempool"

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
echo "To configure PostgreSQL for remote connections, run:"
echo "  $0 --remote-configure [network-cidr]"
echo "  Example: $0 --remote-configure 10.1.223.0/24"
echo ""

# Handle optional remote configuration
if [[ "$1" == "--remote-configure" ]]; then
    network_cidr=${2:-10.1.223.0/24}
    configure_remote_connections "$network_cidr"
fi
