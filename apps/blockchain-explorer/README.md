# blockchain-explorer

## Status

**Agent-First API Service** - Pure API for blockchain data access

## Purpose

Provides JSON API endpoints for blockchain data:
- Chain information and statistics
- Block and transaction queries
- Advanced search capabilities
- Data export functionality

## Architecture

- **Agent-First**: Pure JSON API (no HTML UI)
- **UI Location**: Human interface moved to `/opt/aitbc/website/explorer.html`
- **API Endpoints**: All endpoints under `/api/*` prefix
- **Backend**: Connects to blockchain RPC on port 8202

## Service

1 systemd service(s): aitbc-blockchain-explorer.service

## API Endpoints

### Chain Information
- `GET /api/chains` - List supported chains
- `GET /api/chain/head` - Get current chain head
- `GET /api/chain/info` - Get chain information

### Blocks
- `GET /api/blocks/{height}` - Get block by height
- `GET /api/blocks/latest` - Get latest blocks
- `GET /api/blocks/search` - Advanced block search

### Transactions
- `GET /api/transactions/{tx_hash}` - Get transaction by hash
- `GET /api/transactions/search` - Advanced transaction search

### Analytics
- `GET /api/analytics` - Get analytics overview
- `GET /api/analytics/export` - Export analytics data

## Configuration

Environment variables:
- `CHAIN_ID` - Chain ID (default: ait-hub.aitbc.bubuit.net)
- `BLOCKCHAIN_RPC_URL` - Blockchain RPC URL (default: http://localhost:8202)

## Usage

### For Agents (JSON API)
```bash
# Get chain head
curl http://localhost:8100/api/chain/head

# Get block by height
curl http://localhost:8100/api/blocks/100

# Search transactions
curl "http://localhost:8100/api/transactions/search?address=0x..."
```

### For Humans (Web UI)
Visit: `http://hub.aitbc.bubuit.net/explorer.html`

The web UI consumes this API and provides:
- Real-time blockchain visualization
- Block and transaction search
- Analytics and charts
- Data export functionality

---
*Last updated: 2026-06-18*
