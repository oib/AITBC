# Trading Engine

## Status
✅ Operational

## Overview
High-performance trading engine for order matching, execution, and trade settlement with support for multiple order types and trading strategies.

## Architecture

### Core Components
- **Order Matching Engine**: Real-time order matching algorithm
- **Trade Executor**: Executes matched trades
- **Risk Manager**: Risk assessment and position management
- **Settlement Engine**: Trade settlement and clearing
- **Order Book Manager**: Manages order book state
- **Price Engine**: Calculates fair market prices

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Redis for caching
- Access to exchange APIs

### Installation
```bash
cd /opt/aitbc/apps/trading-engine
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/trading
REDIS_URL=redis://localhost:6379
EXCHANGE_API_KEY=your-api-key
RISK_LIMITS_ENABLED=true
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up database
5. Configure environment variables
6. Run tests: `pytest tests/`

### Project Structure
```
trading-engine/
├── src/
│   ├── matching_engine/      # Order matching logic
│   ├── trade_executor/       # Trade execution
│   ├── risk_manager/         # Risk management
│   ├── settlement_engine/    # Trade settlement
│   ├── order_book/           # Order book management
│   └── price_engine/         # Price calculation
├── tests/                    # Test suite
└── pyproject.toml            # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run matching engine tests
pytest tests/test_matching.py

# Run risk manager tests
pytest tests/test_risk.py
```

## API Reference

### Order Management

#### Submit Order
```http
POST /api/v1/trading/orders
Content-Type: application/json

{
  "user_id": "string",
  "symbol": "BTC_AIT",
  "side": "buy|sell",
  "type": "limit|market|stop",
  "quantity": 100,
  "price": 1.0,
  "stop_price": 1.1
}
```

#### Cancel Order
```http
DELETE /api/v1/trading/orders/{order_id}
```

#### Get Order Status
```http
GET /api/v1/trading/orders/{order_id}
```

### Trade Execution

#### Get Trade History
```http
GET /api/v1/trading/trades?symbol=BTC_AIT&limit=100
```

#### Get User Trades
```http
GET /api/v1/trading/users/{user_id}/trades
```

### Risk Management

#### Check Risk Limits
```http
POST /api/v1/trading/risk/check
Content-Type: application/json

{
  "user_id": "string",
  "order": {}
}
```

#### Get User Risk Profile
```http
GET /api/v1/trading/users/{user_id}/risk-profile
```

### Settlement

#### Get Settlement Status
```http
GET /api/v1/trading/settlement/{trade_id}
```

#### Trigger Settlement
```http
POST /api/v1/trading/settlement/trigger
Content-Type: application/json

{
  "trade_ids": ["trade1", "trade2"]
}
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `EXCHANGE_API_KEY`: Exchange API key
- `RISK_LIMITS_ENABLED`: Enable risk management
- `MAX_POSITION_SIZE`: Maximum position size
- `MARGIN_REQUIREMENT`: Margin requirement percentage
- `LIQUIDATION_THRESHOLD`: Liquidation threshold

### Order Types
- **Limit Order**: Execute at specified price or better
- **Market Order**: Execute immediately at market price
- **Stop Order**: Trigger when price reaches stop price
- **Stop-Limit**: Limit order triggered by stop price

### Risk Parameters
- **Position Limits**: Maximum position sizes
- **Margin Requirements**: Required margin for leverage
- **Liquidation Threshold**: Price at which positions are liquidated

## Troubleshooting

**Order not matched**: Check order book depth and price settings.

**Trade execution failed**: Verify exchange connectivity and balance.

**Risk check failed**: Review user risk profile and position limits.

**Settlement delayed**: Check blockchain network status and gas fees.

## Security Notes

- Implement order validation
- Use rate limiting for order submission
- Monitor for wash trading
- Validate user authentication
- Implement position limits
- Regularly audit trade history
