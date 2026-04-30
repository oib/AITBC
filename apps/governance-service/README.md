# AITBC Governance Service

Manages governance operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with governance-service
```

## Database Setup

Create a separate database for the governance service:

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

## Migration Status

**Foundation Created:**
- Application structure (pyproject.toml, main.py)
- Systemd service configuration
- Basic health and status endpoints

**Remaining:**
- Extract governance domain models from coordinator-api
- Extract governance services from coordinator-api
- Extract governance routers from coordinator-api
- Setup separate database session management
- Update coordinator-api to remove governance code
- End-to-end testing with gateway

## Service Configuration

- Port: 8105
- Database: aitbc_governance
- Gateway route: /governance/*
