# Exchange Integration

## Status
✅ Operational

## Overview
Integration service for connecting the exchange with external systems, blockchains, and data providers.

## Architecture

### Core Components
- **Blockchain Connector**: Connects to blockchain RPC endpoints
- **Data Feed Manager**: Manages external data feeds
- **Webhook Handler**: Processes webhook notifications
- **API Client**: Client for external exchange APIs
- **Event Processor**: Processes integration events

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to blockchain RPC endpoints
- API keys for external exchanges

### Installation
```bash
cd /opt/aitbc/apps/exchange-integration
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
BLOCKCHAIN_RPC_URL=http://localhost:8006
EXTERNAL_EXCHANGE_API_KEY=your-api-key
WEBHOOK_SECRET=your-webhook-secret
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
4. Configure environment variables
5. Run tests: `pytest tests/`

### Project Structure
```
exchange-integration/
├── src/
│   ├── blockchain_connector/ # Blockchain integration
│   ├── data_feed_manager/     # Data feed management
│   ├── webhook_handler/        # Webhook processing
│   ├── api_client/             # External API client
│   └── event_processor/       # Event processing
├── tests/                     # Test suite
└── pyproject.toml             # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run blockchain integration tests
pytest tests/test_blockchain.py

# Run webhook tests
pytest tests/test_webhook.py
```

## API Reference

### Blockchain Integration

#### Get Blockchain Status
```http
GET /api/v1/integration/blockchain/status
```

#### Sync Blockchain Data
```http
POST /api/v1/integration/blockchain/sync
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "from_height": 1000,
  "to_height": 2000
}
```

### Data Feeds

#### Subscribe to Data Feed
```http
POST /api/v1/integration/feeds/subscribe
Content-Type: application/json

{
  "feed_type": "price|volume|orders",
  "symbols": ["BTC_AIT", "ETH_AIT"]
}
```

#### Get Feed Data
```http
GET /api/v1/integration/feeds/{feed_id}/data
```

### Webhooks

#### Register Webhook
```http
POST /api/v1/integration/webhooks
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "events": ["order_filled", "price_update"],
  "secret": "your-secret"
}
```

#### Process Webhook
```http
POST /api/v1/integration/webhooks/process
Content-Type: application/json
X-Webhook-Secret: your-secret

{
  "event": "order_filled",
  "data": {}
}
```

## Configuration

### Environment Variables
- `BLOCKCHAIN_RPC_URL`: Blockchain RPC endpoint
- `EXTERNAL_EXCHANGE_API_KEY`: API key for external exchanges
- `WEBHOOK_SECRET`: Secret for webhook validation
- `SYNC_INTERVAL`: Interval for blockchain sync (default: 60s)
- `MAX_RETRIES`: Maximum retry attempts for failed requests
- `TIMEOUT`: Request timeout in seconds

### Integration Settings
- **Supported Chains**: List of supported blockchain networks
- **Data Feed Providers**: External data feed providers
- **Webhook Endpoints**: Configurable webhook endpoints

## Troubleshooting

**Blockchain sync failed**: Check RPC endpoint connectivity and authentication.

**Data feed not updating**: Verify API key and data feed configuration.

**Webhook not triggered**: Check webhook URL and secret configuration.

**API rate limiting**: Implement retry logic with exponential backoff.

## Security Notes

- Validate webhook signatures
- Use HTTPS for all external connections
- Rotate API keys regularly
- Implement rate limiting for external API calls
- Monitor for suspicious activity
