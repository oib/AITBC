# AITBC Blockchain Explorer API

## Status

**Agent-First API Service** - Pure JSON API for blockchain data access. Frontend served separately by nginx at `/opt/aitbc/website/`.

## Purpose

Provides JSON API endpoints for blockchain data:
- Chain information and statistics
- Block and transaction queries (by height, hash, or address)
- Advanced search capabilities
- Analytics and leaderboards
- Data export functionality

## Architecture

- **Agent-First**: Pure JSON API (no HTML UI in this service)
- **UI Location**: Human interface at `/opt/aitbc/website/explorer.html`, `/block.html`, `/tx.html`
- **API Endpoints**: All endpoints under `/api/*` prefix
- **Backend**: Reads directly from blockchain SQLite database (`/var/lib/aitbc/data/*/chain.db`)
- **Access**: Nginx proxies `/explorer-api/` → `http://localhost:8100`
- **Port**: 8100 (internal), accessed via nginx proxy in production

## Service

1 systemd service: `aitbc-blockchain-explorer.service`

## API Endpoints

### Chain Information
- `GET /api/chains` - List supported chains
- `GET /api/chain/head` - Get current chain head
- `GET /api/chain/info` - Get chain information

### Blocks
- `GET /api/blocks/{height}` - Get block by height (includes full transaction list)
- `GET /api/blocks/latest` - Get latest blocks (paginated)
- `GET /api/blocks/non-empty` - Get latest blocks that contain transactions
- `GET /api/blocks/by-hash/{hash}` - Get block by hash
- `GET /api/blocks/by-address/{address}` - Get all blocks containing transactions for an address
- `GET /api/blocks/search` - Advanced block search

### Transactions
- `GET /api/transactions/{tx_hash}` - Get transaction by hash
- `GET /api/transactions/by-hash/{hash}` - Alias for transaction by hash
- `GET /api/transactions/search?address=...` - Search transactions by sender, recipient, or payload

### Analytics
- `GET /api/analytics/activity?days=30` - Daily transaction counts by type (for timeline charts)
- `GET /api/analytics/network-stats` - Aggregate network stats (total AIT, active offers, unique nodes/providers, total TXs)
- `GET /api/analytics/top-addresses?limit=20` - Top addresses by transaction count and AIT volume
- `GET /api/analytics/provider-reputation/{provider_id}` - Computed reputation score (0-100) with level from blockchain history

### Export
- `GET /api/export/search` - Export search results as CSV or JSON
- `GET /api/export/blocks` - Export latest blocks as CSV or JSON

## Configuration

Environment variables:
- `CHAIN_ID` - Chain ID (default: `ait-hub.aitbc.bubuit.net`)
- `BLOCKCHAIN_RPC_URL` - Blockchain RPC URL (default: `http://localhost:8202`)

## Usage

### For Agents (JSON API)
```bash
# Get chain head
curl http://localhost:8100/api/chain/head

# Get block by height (includes transactions)
curl http://localhost:8100/api/blocks/29656

# Get transaction by hash
curl http://localhost:8100/api/transactions/0x...

# Search transactions by address
curl "http://localhost:8100/api/transactions/search?address=ait1db524..."

# Get all blocks for an address
curl "http://localhost:8100/api/blocks/by-address/ait1db524..."

# Network stats
curl http://localhost:8100/api/analytics/network-stats

# Activity timeline (30 days)
curl "http://localhost:8100/api/analytics/activity?days=30"

# Top addresses leaderboard
curl "http://localhost:8100/api/analytics/top-addresses?limit=10"

# Provider reputation
curl "http://localhost:8100/api/analytics/provider-reputation/ait1db524..."
```

### For Humans (Web UI)
Visit: `https://hub.aitbc.bubuit.net/explorer.html`

The web UI provides:
- Real-time blockchain visualization with live feed ticker
- Block and transaction search with direction indicators (IN/OUT/SELF)
- Activity timeline chart (daily volume by type)
- Top addresses leaderboard
- Dedicated detail pages: `/block.html?height=N`, `/tx.html?hash=0x...`
- Expandable block cards with transaction details
- Copy-to-clipboard for all hashes
- Data export functionality

## Frontend Pages

| Page | Purpose |
|------|---------|
| `explorer.html` | Main explorer: stats, search, live feed, top addresses, block list |
| `block.html?height=N` | Block detail: metadata table + transaction list |
| `tx.html?hash=0x...` | Transaction detail: metadata table + JSON payload viewer |

## Testing

```bash
cd /opt/aitbc/apps/blockchain-explorer
/opt/aitbc/venv/bin/python -m pytest tests/ -v -o addopts=""
```

---
*Last updated: 2026-06-20*
