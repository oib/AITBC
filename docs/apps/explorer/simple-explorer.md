# Simple Explorer

## Status
✅ Operational

## Overview
Simple blockchain explorer for viewing blocks, transactions, and addresses on the AITBC blockchain.

## Architecture

### Core Components
- **Block Viewer**: Displays block information and details
- **Transaction Viewer**: Displays transaction information
- **Address Viewer**: Displays address details and transaction history
- **Search Engine**: Searches for blocks, transactions, and addresses
- **Data Fetcher**: Fetches data from blockchain RPC

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to blockchain RPC endpoint
- Web browser

### Installation
```bash
cd /opt/aitbc/apps/simple-explorer
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
BLOCKCHAIN_RPC_URL=http://localhost:8006
CHAIN_ID=ait-mainnet
EXPLORER_PORT=8080
```

### Running the Service
```bash
.venv/bin/python main.py
```

### Access Explorer
Open `http://localhost:8080` in a web browser to access the explorer.

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure blockchain RPC endpoint
5. Run tests: `pytest tests/`

### Project Structure
```
simple-explorer/
├── src/
│   ├── block_viewer/       # Block viewing
│   ├── transaction_viewer/ # Transaction viewing
│   ├── address_viewer/     # Address viewing
│   ├── search_engine/      # Search functionality
│   └── data_fetcher/       # Data fetching
├── templates/              # HTML templates
├── static/                  # Static assets
├── tests/                  # Test suite
└── pyproject.toml          # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run data fetcher tests
pytest tests/test_fetcher.py

# Run search engine tests
pytest tests/test_search.py
```

## API Reference

### Block Viewing

#### Get Block by Height
```http
GET /api/v1/explorer/block/{height}
```

#### Get Block by Hash
```http
GET /api/v1/explorer/block/hash/{hash}
```

#### Get Latest Blocks
```http
GET /api/v1/explorer/blocks/latest?limit=20
```

### Transaction Viewing

#### Get Transaction by Hash
```http
GET /api/v1/explorer/transaction/{hash}
```

#### Get Transactions by Address
```http
GET /api/v1/explorer/transactions/address/{address}?limit=50
```

#### Get Latest Transactions
```http
GET /api/v1/explorer/transactions/latest?limit=50
```

### Address Viewing

#### Get Address Details
```http
GET /api/v1/explorer/address/{address}
```

#### Get Address Balance
```http
GET /api/v1/explorer/address/{address}/balance
```

#### Get Address Transactions
```http
GET /api/v1/explorer/address/{address}/transactions?limit=50
```

### Search

#### Search
```http
GET /api/v1/explorer/search?q={query}
```

#### Search Blocks
```http
GET /api/v1/explorer/search/blocks?q={query}
```

#### Search Transactions
```http
GET /api/v1/explorer/search/transactions?q={query}
```

#### Search Addresses
```http
GET /api/v1/explorer/search/addresses?q={query}
```

### Statistics

#### Get Chain Statistics
```http
GET /api/v1/explorer/stats
```

#### Get Network Status
```http
GET /api/v1/explorer/network/status
```

## Configuration

### Environment Variables
- `BLOCKCHAIN_RPC_URL`: Blockchain RPC endpoint
- `CHAIN_ID`: Blockchain chain ID
- `EXPLORER_PORT`: Explorer web server port
- `CACHE_ENABLED`: Enable data caching
- `CACHE_TTL`: Cache time-to-live in seconds

### Display Parameters
- **Blocks Per Page**: Number of blocks per page (default: 20)
- **Transactions Per Page**: Number of transactions per page (default: 50)
- **Address History Limit**: Transaction history limit per address

### Caching
- **Block Cache**: Cache block data
- **Transaction Cache**: Cache transaction data
- **Address Cache**: Cache address data
- **Cache TTL**: Time-to-live for cached data

## Troubleshooting

**Explorer not loading**: Check blockchain RPC connectivity and explorer port.

**Data not updating**: Verify cache configuration and RPC endpoint availability.

**Search not working**: Check search index and data availability.

**Address history incomplete**: Verify blockchain sync status and data availability.

## Security Notes

- Use HTTPS in production
- Implement rate limiting for API endpoints
- Sanitize user inputs
- Cache sensitive data appropriately
- Monitor for abuse
- Regularly update dependencies
