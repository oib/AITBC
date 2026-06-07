# SQL Database Infrastructure for AITBC

## Purpose
Document PostgreSQL and SQLite database infrastructure configuration for AITBC nodes, including setup, migration, and troubleshooting procedures.

## Architecture Overview

### Mixed Database Strategy
AITBC uses a mixed database architecture:
- **PostgreSQL**: Application services (coordinator, exchange, marketplace, wallet)
- **SQLite**: Blockchain node chain data (chain-specific databases)

### PostgreSQL Databases
- **aitbc_coordinator**: Coordinator API relational data
- **aitbc_exchange**: Exchange API trading data
- **aitbc_marketplace**: Marketplace service listings and bids
- **aitbc_mempool**: Mempool persistence
- **aitbc_wallet**: Wallet service account data

### SQLite Databases
- **Chain-specific**: `/var/lib/aitbc/data/{chain_id}/chain.db`
  - `/var/lib/aitbc/data/ait-mainnet/chain.db` - Mainnet blockchain data
  - `/var/lib/aitbc/data/ait-testnet/chain.db` - Testnet blockchain data

## PostgreSQL Setup

### Installation
```bash
# Install PostgreSQL on Debian/Ubuntu
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Database and User Creation
```bash
# Switch to postgres user
sudo su postgres

# Create databases
createdb aitbc_coordinator
createdb aitbc_exchange
createdb aitbc_marketplace
createdb aitbc_mempool
createdb aitbc_wallet

# Create users with passwords
psql -c "CREATE USER aitbc_coordinator WITH PASSWORD 'secure_password';"
psql -c "CREATE USER aitbc_exchange WITH PASSWORD 'secure_password';"
psql -c "CREATE USER aitbc_marketplace WITH PASSWORD 'secure_password';"
psql -c "CREATE USER aitbc_mempool WITH PASSWORD 'secure_password';"
psql -c "CREATE USER aitbc_wallet WITH PASSWORD 'secure_password';"

# Grant privileges
psql -d aitbc_coordinator -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_coordinator TO aitbc_coordinator;"
psql -d aitbc_exchange -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_exchange TO aitbc_exchange;"
psql -d aitbc_marketplace -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_marketplace TO aitbc_marketplace;"
psql -d aitbc_mempool -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_mempool TO aitbc_mempool;"
psql -d aitbc_wallet -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_wallet TO aitbc_wallet;"

exit
```

### Systemd Drop-in Configuration

**Mempool** (`/etc/systemd/system/aitbc-blockchain-node.service.d/mempool-postgres.conf`):
```ini
[Service]
Environment="MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool"
```

**Exchange** (`/etc/systemd/system/aitbc-exchange-api.service.d/exchange-postgres.conf`):
```ini
[Service]
Environment="EXCHANGE_DATABASE_URL=postgresql+psycopg://aitbc_exchange:password@localhost:5432/aitbc_exchange"
```

**Coordinator** (`/etc/systemd/system/aitbc-agent-coordinator.service.d/coordinator-postgres.conf`):
```ini
[Service]
Environment="DATABASE_ADAPTER=postgresql"
Environment="DATABASE_URL=postgresql+psycopg://aitbc_coordinator:password@localhost:5432/aitbc_coordinator"
```

### Apply Configuration
```bash
# Reload systemd to pick up drop-in files
sudo systemctl daemon-reload

# Restart services
sudo systemctl restart aitbc-blockchain-node.service
sudo systemctl restart aitbc-exchange-api.service
sudo systemctl restart aitbc-agent-coordinator.service
```

## SQLite Setup

### Btrfs CoW Disablement (Critical)
SQLite corruption on Btrfs filesystems is caused by CoW behavior. Disable CoW on data directory:

```bash
# Disable CoW on AITBC data directory
sudo chattr +C /var/lib/aitbc

# Verify CoW is disabled
lsattr -d /var/lib/aitbc
# Should show: ----C--------- /var/lib/aitbc
```

### Chain-Specific Database Setup
```bash
# Create chain-specific directories
sudo mkdir -p /var/lib/aitbc/data/ait-mainnet
sudo mkdir -p /var/lib/aitbc/data/ait-testnet

# Set permissions
sudo chown -R aitbc:aitbc /var/lib/aitbc/data
sudo chmod -R 755 /var/lib/aitbc/data
```

### WAL Mode Configuration
```bash
# Enable WAL mode for better performance and concurrency
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "PRAGMA journal_mode=WAL;"
sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db "PRAGMA journal_mode=WAL;"
```

**Note**: WAL mode set via sqlite3 command doesn't persist after service restart. Enable at application level via database connection string or configuration.

### Blockchain Node Configuration
Edit `/etc/aitbc/blockchain.env`:
```bash
# For SQLite (default, recommended for blockchain)
# DATABASE_URL=postgresql://aitbc:password@localhost:5432/aitbc_prod
DATA_DIR=/var/lib/aitbc
CHAIN_ID=ait-mainnet
```

## Configuration Files

### blockchain.env
Location: `/etc/aitbc/blockchain.env`

Key settings:
```bash
# Database URL (comment out to use SQLite)
# DATABASE_URL=postgresql://aitbc:secure_password@localhost:5432/aitbc_prod

# Data directory for chain-specific SQLite databases
DATA_DIR=/var/lib/aitbc

# Chain ID for multi-chain support
CHAIN_ID=ait-mainnet

# Redis URL for gossip protocol
REDIS_URL=redis://10.1.223.93:6379
```

### Database Connection Strings
```bash
# PostgreSQL connection string format
postgresql+psycopg://username:password@localhost:5432/database_name

# SQLite connection string format
sqlite:////var/lib/aitbc/data/{chain_id}/chain.db
```

## Migration: SQLite to PostgreSQL

### Pre-Migration Checks
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check PostgreSQL users and databases
sudo su postgres -c "psql -l"

# Backup existing SQLite databases
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db /var/lib/aitbc/data/ait-mainnet/chain.db.backup
```

### Migration Steps
1. Create PostgreSQL databases and users (see PostgreSQL Setup)
2. Create systemd drop-in configuration files
3. Update application code to use PostgreSQL
4. Reload systemd and restart services
5. Verify database connectivity

### Rollback Procedure
```bash
# Comment out DATABASE_URL in blockchain.env
sudo sed -i 's/^DATABASE_URL/#DATABASE_URL/' /etc/aitbc/blockchain.env

# Remove systemd drop-in files
sudo rm /etc/systemd/system/aitbc-blockchain-node.service.d/mempool-postgres.conf
sudo rm /etc/systemd/system/aitbc-exchange-api.service.d/exchange-postgres.conf
sudo rm /etc/systemd/system/aitbc-agent-coordinator.service.d/coordinator-postgres.conf

# Reload systemd and restart services
sudo systemctl daemon-reload
sudo systemctl restart aitbc-blockchain-node.service
sudo systemctl restart aitbc-exchange-api.service
sudo systemctl restart aitbc-agent-coordinator.service
```

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check PostgreSQL logs
sudo tail -50 /var/log/postgresql/postgresql-*.log

# Test PostgreSQL connection
sudo su postgres -c "psql -d aitbc_coordinator -c 'SELECT 1;'"

# Check service logs
sudo journalctl -u aitbc-blockchain-node --no-pager -n 50
sudo journalctl -u aitbc-exchange-api --no-pager -n 50
sudo journalctl -u aitbc-agent-coordinator --no-pager -n 50
```

### SQLite Corruption
```bash
# Check SQLite database integrity
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "PRAGMA integrity_check;"

# If corruption detected, restore from backup
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db.backup /var/lib/aitbc/data/ait-mainnet/chain.db

# Ensure CoW is disabled
sudo chattr +C /var/lib/aitbc
lsattr -d /var/lib/aitbc
```

### Missing PostgreSQL Database
```bash
# Check if database exists
sudo su postgres -c "psql -l | grep aitbc_prod"

# If missing, create it
sudo su postgres -c "createdb aitbc_prod"
sudo su postgres -c "psql -c \"CREATE USER aitbc WITH PASSWORD 'secure_password';\""
sudo su postgres -c "psql -d aitbc_prod -c \"GRANT ALL PRIVILEGES ON DATABASE aitbc_prod TO aitbc;\""
```

### RPC Returns Wrong Block Height

**Root Cause**: The RPC service (`aitbc-blockchain-rpc.service`) runs as a separate systemd service from the blockchain node service (`aitbc-blockchain-node.service`). It maintains its own in-memory SQLAlchemy engine cache in the `_engines` dict. When only the blockchain node service is restarted, the RPC service's cached engines are not cleared, causing it to return stale data from a previous database state.

**Database Engine Architecture** (in `database.py`):
- **Default `_engine`** (non-chain-specific): `DATA_DIR / "data" / "chain.db"`
- **Chain-specific engines** (in `_engines` dict): `DATA_DIR / "data" / {chain_id} / "chain.db"`
- RPC uses chain-specific engines via `session_scope(chain_id)` → `get_engine(chain_id)`

**Resolution Steps**:
```bash
# Check which database RPC is reading from
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "SELECT COUNT(*), MAX(height) FROM block;"
sqlite3 /var/lib/aitbc/data/chain.db "SELECT COUNT(*), MAX(height) FROM block WHERE chain_id='ait-mainnet';"

# Check RPC output
curl -s http://localhost:8006/rpc/head?chain_id=ait-mainnet | jq '.'

# If RPC returns stale data, restart both services
sudo systemctl restart aitbc-blockchain-node.service
sudo systemctl restart aitbc-blockchain-rpc.service

# If default chain.db exists and is causing conflicts, move it
sudo mv /var/lib/aitbc/data/chain.db /var/lib/aitbc/data/chain.db.bak
sudo systemctl restart aitbc-blockchain-node.service
sudo systemctl restart aitbc-blockchain-rpc.service
```

**Important**: When making database configuration changes (e.g., removing `DATABASE_URL`, deleting conflicting database files), always restart BOTH `aitbc-blockchain-node.service` and `aitbc-blockchain-rpc.service` to ensure all in-memory caches are cleared.

## Verification

### PostgreSQL Verification
```bash
# Check all PostgreSQL databases
sudo su postgres -c "psql -l"

# Check database tables
sudo su postgres -c "psql -d aitbc_coordinator -c '\dt'"
sudo su postgres -c "psql -d aitbc_exchange -c '\dt'"
sudo su postgres -c "psql -d aitbc_mempool -c '\dt'"

# Test service connectivity
curl -s http://localhost:8000/v1/health
curl -s http://localhost:8001/health
```

### SQLite Verification
```bash
# Check chain-specific databases
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "SELECT COUNT(*), MAX(height) FROM block;"
sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db "SELECT COUNT(*), MAX(height) FROM block;"

# Check RPC reflects correct database
curl -s http://localhost:8006/rpc/head?chain_id=ait-mainnet | jq '.height'
```

## Important Notes

- **Never use PostgreSQL for blockchain chain data**: Use SQLite for chain-specific databases
- **Always disable CoW on Btrfs**: SQLite corruption occurs on Btrfs without CoW disablement
- **Use systemd drop-ins for service configuration**: Don't modify main service files
- **Backup before migration**: Always backup SQLite databases before PostgreSQL migration
- **Test connection strings**: Verify database connectivity before restarting services
- **Chain-specific databases**: Blockchain node uses chain-specific SQLite databases for multi-chain support

## Common Operations

### Check PostgreSQL database size
```bash
sudo su postgres -c "psql -c \"SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;\""
```

### Backup PostgreSQL database
```bash
sudo su postgres -c "pg_dump aitbc_coordinator > /var/backups/aitbc_coordinator.sql"
```

### Restore PostgreSQL database
```bash
sudo su postgres -c "psql aitbc_coordinator < /var/backups/aitbc_coordinator.sql"
```

### Check SQLite database size
```bash
ls -lh /var/lib/aitbc/data/ait-mainnet/chain.db
ls -lh /var/lib/aitbc/data/ait-testnet/chain.db
```

### Vacuum SQLite database
```bash
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;"
```

## Multi-Node Operations

### Apply PostgreSQL setup to all nodes
```bash
for node in aitbc1 gitea-runner; do
  ssh "$node" "sudo apt install postgresql postgresql-contrib -y"
  ssh "$node" "sudo systemctl start postgresql"
  ssh "$node" "sudo systemctl enable postgresql"
done
```

### Check database status across all nodes
```bash
for node in aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh "$node" "sudo systemctl status postgresql --no-pager"
  ssh "$node" "sudo su postgres -c 'psql -l'"
done
```

### Disable CoW on all nodes
```bash
for node in aitbc1 gitea-runner; do
  ssh "$node" "sudo chattr +C /var/lib/aitbc"
  ssh "$node" "lsattr -d /var/lib/aitbc"
done
```
