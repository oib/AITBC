# AITBC Governance Service

Manages governance operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with governance-service
```

## Database Setup

Create a separate database for the governance service:

```bash
sudo -u postgres psql -f apps/governance-service/scripts/setup-database.sql
```

Or manually:

```sql
CREATE DATABASE aitbc_governance;
CREATE USER aitbc_governance WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
```

## Running

```bash
# Development
python -m governance_service.main

# Production (systemd)
sudo systemctl start governance-service
sudo systemctl enable governance-service
```

## Endpoints

- `GET /health` - Health check
- `GET /governance/status` - Get governance status
- `GET /v1/governance/profiles` - Get governance profiles
- `GET /v1/governance/profiles/{profile_id}` - Get specific profile
- `POST /v1/governance/profiles` - Create new profile
- `GET /v1/governance/proposals` - Get proposals
- `GET /v1/governance/proposals/{proposal_id}` - Get specific proposal
- `POST /v1/governance/proposals` - Create new proposal
- `GET /v1/governance/votes` - Get votes
- `POST /v1/governance/votes` - Create new vote
- `GET /v1/governance/treasury` - Get DAO treasury
- `GET /v1/governance/analytics` - Get governance analytics

## Testing

To test the governance service end-to-end with the gateway:

1. Start the governance service:
   ```bash
   python -m governance_service.main
   ```

2. Start the API gateway:
   ```bash
   python -m api_gateway.main
   ```

3. Test governance endpoints through the gateway:
   ```bash
   curl http://localhost:8080/governance/v1/governance/proposals
   curl http://localhost:8080/governance/health
   ```

## Service Configuration

- Port: 8105
- Database: aitbc_governance
- Gateway route: /governance/*

## Migration Status

**Completed:**
- Extracted governance domain models (GovernanceProfile, Proposal, Vote, DaoTreasury, TransparencyReport)
- Extracted governance services (GovernanceService with CRUD operations)
- Set up database session management
- Extracted governance router endpoints
- Created systemd service configuration
- Created database setup script

**Remaining:**
- Remove governance routers from coordinator-api
- Remove governance services from coordinator-api
- Remove governance domain models from coordinator-api
- Run database migration script to create aitbc_governance database
- Install and enable systemd service
- End-to-end testing with gateway

Note: The governance service is ~50K lines, so full removal from coordinator-api requires careful coordination to avoid breaking existing functionality. The foundation is in place for gradual migration.
