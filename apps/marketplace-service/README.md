# AITBC Marketplace Service

Manages GPU marketplace operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with marketplace-service
```

## Database Setup

Create a separate database for the marketplace service:

```bash
sudo -u postgres psql -f apps/marketplace-service/scripts/setup-database.sql
```

Or manually:

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
- `GET /v1/marketplace/offers` - Get marketplace offers
- `GET /v1/marketplace/offers/{offer_id}` - Get specific offer
- `POST /v1/marketplace/offers` - Create new offer
- `GET /v1/marketplace/bids` - Get marketplace bids
- `POST /v1/marketplace/bids` - Create new bid
- `GET /v1/marketplace/analytics` - Get marketplace analytics

## Testing

To test the marketplace service end-to-end with the gateway:

1. Start the marketplace service:
   ```bash
   python -m marketplace_service.main
   ```

2. Start the API gateway:
   ```bash
   python -m api_gateway.main
   ```

3. Test marketplace endpoints through the gateway:
   ```bash
   curl http://localhost:8080/marketplace/v1/marketplace/offers
   curl http://localhost:8080/marketplace/health
   ```

## Service Configuration

- Port: 8102
- Database: aitbc_marketplace
- Gateway route: /marketplace/*

## Migration Status

**Completed:**
- Extracted marketplace domain models (MarketplaceOffer, MarketplaceBid, GlobalMarketplaceOffer, GlobalMarketplaceTransaction, etc.)
- Extracted marketplace services (MarketplaceService with CRUD operations)
- Extracted marketplace data structures
- Set up database session management
- Extracted marketplace router endpoints
- Created systemd service configuration
- Created database setup script

**Remaining:**
- Remove marketplace routers from coordinator-api (marketplace, marketplace_gpu, marketplace_offers, global_marketplace, global_marketplace_integration)
- Remove marketplace services from coordinator-api
- Remove marketplace domain models from coordinator-api
- Run database migration script to create aitbc_marketplace database
- Install and enable systemd service
- End-to-end testing with gateway

Note: The marketplace service is very large (~130K lines), so full removal from coordinator-api requires careful coordination to avoid breaking existing functionality. The foundation is in place for gradual migration.
