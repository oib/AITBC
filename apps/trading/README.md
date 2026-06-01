# AITBC Trading Service

Manages trading operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with trading-service
```

## Database Setup

Create a separate database for the trading service:

```bash
sudo -u postgres psql -f apps/trading-service/scripts/setup-database.sql
```

Or manually:

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
- `GET /v1/trading/requests` - Get trade requests
- `GET /v1/trading/requests/{request_id}` - Get specific request
- `POST /v1/trading/requests` - Create new request
- `GET /v1/trading/matches` - Get trade matches
- `POST /v1/trading/matches` - Create new match
- `GET /v1/trading/agreements` - Get trade agreements
- `POST /v1/trading/agreements` - Create new agreement
- `GET /v1/trading/analytics` - Get trading analytics

## Testing

### Prerequisites

- PostgreSQL running and aitbc_trading database created
- Poetry dependencies installed

### Database Setup

```bash
sudo -u postgres psql -f scripts/setup-database.sql
```

### Start Service (Development)

```bash
python -m trading_service.main
```

### Health Check

```bash
curl http://localhost:8104/health
```

Expected response:
```json
{"status": "healthy", "service": "trading-service"}
```

### Trading Status

```bash
curl http://localhost:8104/trading/status
```

Expected response:
```json
{
  "status": "operational",
  "service": "trading-service",
  "message": "Trading service is running"
}
```

### Get Trade Requests

```bash
curl http://localhost:8104/v1/trading/requests
```

Expected response:
```json
[]
```

### Create Trade Request

```bash
curl -X POST http://localhost:8104/v1/trading/requests \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_agent_id": "test_buyer",
    "trade_type": "compute_resources",
    "title": "Test Trade Request",
    "description": "Test description"
  }'
```

### Test Through Gateway

1. Start the API gateway:
   ```bash
   python -m api_gateway.main
   ```

2. Test trading endpoints through the gateway:
   ```bash
   curl http://localhost:8080/trading/health
   curl http://localhost:8080/trading/v1/trading/requests
   ```

For comprehensive testing procedures, see [MICROSERVICES_TESTING_GUIDE.md](../docs/MICROSERVICES_TESTING_GUIDE.md).

## Service Configuration

- Port: 8104
- Database: aitbc_trading
- Gateway route: /trading/*

## Migration Status

**Completed:**
- Extracted trading domain models (TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement, TradeFeedback, TradingAnalytics)
- Extracted trading services (TradingService with CRUD operations)
- Set up database session management
- Extracted trading router endpoints
- Created systemd service configuration
- Created database setup script

**Remaining:**
- Remove trading routers from coordinator-api
- Remove trading services from coordinator-api
- Remove trading domain models from coordinator-api
- Run database migration script to create aitbc_trading database
- Install and enable systemd service
- End-to-end testing with gateway

Note: The trading service is ~60K lines, so full removal from coordinator-api requires careful coordination to avoid breaking existing functionality. The foundation is in place for gradual migration.
