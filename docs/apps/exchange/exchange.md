# Exchange

## Status
✅ Operational

## Overview
Cross-chain exchange and trading platform supporting multiple blockchain networks with real-time price tracking and order matching.

## Architecture

### Core Components
- **Order Book**: Central order book for all trading pairs
- **Matching Engine**: Real-time order matching and execution
- **Price Ticker**: Real-time price updates and market data
- **Cross-Chain Bridge**: Bridge for cross-chain asset transfers
- **Health Monitor**: System health monitoring and alerting
- **API Server**: RESTful API for exchange operations

### Supported Features
- Multiple trading pairs
- Cross-chain asset transfers
- Real-time price updates
- Order management (limit, market, stop orders)
- Health monitoring
- Multi-chain support

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database (production default)
- Redis for caching
- Access to blockchain RPC endpoints

### Installation
```bash
cd /opt/aitbc/apps/exchange
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/exchange
REDIS_URL=redis://localhost:6379
BLOCKCHAIN_RPC_URL=http://localhost:8006
CROSS_CHAIN_ENABLED=true
```

### Running the Service
```bash
# Start the exchange server
python server.py

# Or use the production launcher
bash deploy_real_exchange.sh
```

### Web Interface
Open `index.html` in a browser to access the web interface.

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up database: See database.py
5. Configure environment variables
6. Run tests: `pytest tests/`

### Project Structure
```
exchange/
├── server.py                # Main server
├── exchange_api.py           # Exchange API endpoints
├── multichain_exchange_api.py # Multi-chain API
├── simple_exchange_api.py   # Simple exchange API
├── cross_chain_exchange.py  # Cross-chain exchange logic
├── real_exchange_integration.py # Real exchange integration
├── models.py                 # Database models
├── database.py               # Database connection
├── health_monitor.py         # Health monitoring
├── index.html                # Web interface
├── styles.css                # Web styles
├── update_price_ticker.js    # Price ticker update script
└── scripts/                  # Utility scripts
```

### Testing
```bash
# Run all tests
pytest tests/

# Run API tests
pytest tests/test_api.py

# Run cross-chain tests
pytest tests/test_cross_chain.py
```

## API Reference

### Market Data

#### Get Order Book
```http
GET /api/v1/orderbook?pair=BTC_AIT
```

#### Get Price Ticker
```http
GET /api/v1/ticker?pair=BTC_AIT
```

#### Get Market Summary
```http
GET /api/v1/market/summary
```

### Orders

#### Place Order
```http
POST /api/v1/orders
Content-Type: application/json

{
  "pair": "BTC_AIT",
  "side": "buy|sell",
  "type": "limit|market|stop",
  "amount": 100,
  "price": 1.0,
  "user_id": "string"
}
```

#### Get Order Status
```http
GET /api/v1/orders/{order_id}
```

#### Cancel Order
```http
DELETE /api/v1/orders/{order_id}
```

#### Get User Orders
```http
GET /api/v1/orders?user_id=string&status=open
```

### Cross-Chain

#### Initiate Cross-Chain Transfer
```http
POST /api/v1/crosschain/transfer
Content-Type: application/json

{
  "from_chain": "ait-mainnet",
  "to_chain": "btc-mainnet",
  "asset": "BTC",
  "amount": 100,
  "recipient": "address"
}
```

#### Get Transfer Status
```http
GET /api/v1/crosschain/transfers/{transfer_id}
```

### Health

#### Get Health Status
```http
GET /health
```

#### Get System Metrics
```http
GET /metrics
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `BLOCKCHAIN_RPC_URL`: Blockchain RPC endpoint
- `CROSS_CHAIN_ENABLED`: Enable cross-chain transfers
- `MAX_ORDER_SIZE`: Maximum order size
- `MIN_ORDER_SIZE`: Minimum order size
- `TRADING_FEE_PERCENTAGE`: Trading fee percentage
- `ORDER_TIMEOUT`: Order timeout in seconds

### Trading Parameters
- **Order Types**: limit, market, stop orders
- **Order Sides**: buy, sell
- **Trading Pairs**: Configurable trading pairs
- **Fee Structure**: Percentage-based trading fees

## Troubleshooting

**Order not matched**: Check order book depth and price settings.

**Cross-chain transfer failed**: Verify blockchain connectivity and bridge status.

**Price ticker not updating**: Check WebSocket connection and data feed.

**Database connection errors**: Verify DATABASE_URL and database server status.

## Security Notes

- Use API keys for authentication
- Implement rate limiting for API endpoints
- Validate all order parameters
- Encrypt sensitive data at rest
- Monitor for suspicious trading patterns
- Regularly audit order history
