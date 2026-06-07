# AITBC Governance Service v0.4.12

Manages governance operations with token-weighted voting, staking, and delegation.

## v0.4.12 New Features

- **Token-Weighted Voting**: Voting power based on token holdings and staking
- **Token Staking**: Stake tokens for 2x voting power multiplier
- **Voting Power Delegation**: Delegate voting power to other addresses
- **Enhanced Proposal Execution**: Proposal execution with logging
- **Alembic Migrations**: Database migration support for schema changes
- **PostgreSQL Support**: Production-ready PostgreSQL with connection pooling

## Installation

```bash
cd /opt/aitbc
poetry install --with governance
```

## Database Setup

### SQLite (Default)

```bash
# Database will be created at /var/lib/aitbc/data/governance_service.db
mkdir -p /var/lib/aitbc/data
```

### PostgreSQL (Production)

```bash
sudo -u postgres psql -f apps/governance/scripts/setup-database.sql
```

Or manually:

```sql
CREATE DATABASE aitbc_governance;
CREATE USER aitbc_governance WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
```

Set environment variable for PostgreSQL:
```bash
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=aitbc_governance
export DB_USER=aitbc_governance
export DB_PASS=password
```

## Running

```bash
# Development
python -m governance_service.main

# Production (systemd)
sudo systemctl start aitbc-governance
sudo systemctl enable aitbc-governance
```

## Database Migrations

```bash
cd /opt/aitbc/apps/governance

# Run migrations
/opt/aitbc/venv/bin/alembic upgrade head

# Check migration status
/opt/aitbc/venv/bin/alembic current

# Rollback
/opt/aitbc/venv/bin/alembic downgrade -1
```

## Endpoints

### Core Endpoints
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /live` - Liveness check
- `GET /v1/governance/status` - Get governance status

### Profile Endpoints
- `GET /v1/governance/profiles` - Get governance profiles
- `GET /v1/governance/profiles/{profile_id}` - Get specific profile
- `POST /v1/governance/profiles` - Create new profile

### Proposal Endpoints
- `GET /v1/governance/proposals` - Get proposals
- `GET /v1/governance/proposals/{proposal_id}` - Get specific proposal
- `POST /v1/governance/proposals` - Create new proposal
- `POST /v1/governance/proposals/{proposal_id}/execute` - Execute proposal (v0.4.12)

### Vote Endpoints
- `GET /v1/governance/votes` - Get votes
- `POST /v1/governance/votes` - Create new vote

### Treasury & Analytics
- `GET /v1/governance/treasury` - Get DAO treasury
- `GET /v1/governance/analytics` - Get governance analytics

### v0.4.12 New Endpoints
- `POST /v1/governance/stake` - Stake tokens for enhanced voting power
- `GET /v1/governance/voting-power/{address}` - Get voting power for address
- `POST /v1/governance/delegate` - Delegate voting power to another address

### Transaction Endpoints
- `POST /v1/transactions` - Submit governance transaction
- `GET /v1/transactions` - Query governance transactions

## CLI Commands

```bash
# Staking
aitbc governance stake --address 0x123... --amount 1000 --lock-days 30

# Delegation
aitbc governance delegate --delegator 0x123... --delegate 0x456... --amount 500

# Proposal Execution
aitbc governance execute <proposal_id>

# Voting Power Query
aitbc governance voting-power <address>

# Voting
aitbc governance vote <proposal_id> --vote for --wallet mywallet

# Create Proposal
aitbc governance proposal --proposal-id prop_123 --title "Test" --description "Test proposal" --wallet mywallet
```

## Testing

```bash
cd /opt/aitbc/apps/governance
pytest tests/
```

## Service Configuration

- Port: 8105
- Database: SQLite (default) or PostgreSQL (production)
- Gateway route: /governance/*
- Migration tool: Alembic

## Database Schema

### Tables
- `governance_profiles` - User governance profiles
- `proposals` - Governance proposals with v0.4.12 enhancements
- `votes` - Vote records with token-weighted power
- `delegations` - Voting power delegations
- `governance_tokens` - Token holdings and voting power
- `token_stakes` - Token staking records
- `proposal_execution_log` - Proposal execution audit trail
- `dao_treasury` - DAO treasury records
- `transparency_reports` - Governance analytics reports

### Indexes
- 14 indexes for performance optimization
- Status, voting period, proposer, voter, delegation, and execution log indexes
