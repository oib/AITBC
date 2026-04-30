# AITBC Marketplace Service

Manages GPU marketplace operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with marketplace-service
```

## Database Setup

Create a separate database for the marketplace service:

```sql
CREATE DATABASE aitbc_marketplace;
CREATE USER aitbc_marketplace WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_marketplace TO aitbc_marketplace;
```

## Running

```bash
# Development
python -m marketplace_service.main

# Production (systemd)
sudo systemctl start marketplace-service
sudo systemctl enable marketplace-service
```

## Endpoints

- `GET /health` - Health check
- `GET /marketplace/status` - Get marketplace status

## Migration Status

**Foundation Created:**
- Application structure (pyproject.toml, main.py)
- Systemd service configuration
- Basic health and status endpoints

**Remaining:**
- Extract marketplace domain models from coordinator-api
- Extract marketplace services from coordinator-api
- Extract marketplace routers from coordinator-api
- Setup separate database session management
- Update coordinator-api to remove marketplace code
- End-to-end testing with gateway

## Service Configuration

- Port: 8102
- Database: aitbc_marketplace
- Gateway route: /marketplace/*
