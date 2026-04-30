# AITBC Trading Service

Manages trading operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with trading-service
```

## Database Setup

Create a separate database for the trading service:

```sql
CREATE DATABASE aitbc_trading;
CREATE USER aitbc_trading WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_trading TO aitbc_trading;
```

## Running

```bash
# Development
python -m trading_service.main

# Production (systemd)
sudo systemctl start trading-service
sudo systemctl enable trading-service
```

## Endpoints

- `GET /health` - Health check
- `GET /trading/status` - Get trading status

## Migration Status

**Foundation Created:**
- Application structure (pyproject.toml, main.py)
- Systemd service configuration
- Basic health and status endpoints

**Remaining:**
- Extract trading domain models from coordinator-api
- Extract trading services from coordinator-api
- Extract trading routers from coordinator-api
- Setup separate database session management
- Update coordinator-api to remove trading code
- End-to-end testing with gateway

## Service Configuration

- Port: 8104
- Database: aitbc_trading
- Gateway route: /trading/*
