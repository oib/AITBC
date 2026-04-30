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

To test the trading service end-to-end with the gateway:

1. Start the trading service:
   ```bash
   python -m trading_service.main
   ```

2. Start the API gateway:
   ```bash
   python -m api_gateway.main
   ```

3. Test trading endpoints through the gateway:
   ```bash
   curl http://localhost:8080/trading/v1/trading/requests
   curl http://localhost:8080/trading/health
   ```

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
