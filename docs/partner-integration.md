# Partner Integration Guide

This guide helps third-party services integrate with the AITBC platform for explorers, analytics, and other services.

## Overview

AITBC provides multiple integration points for partners:
- REST APIs for real-time data
- WebSocket streams for live updates
- Export endpoints for bulk data
- Webhook notifications for events

## Getting Started

### 1. Register Your Application

Register your service to get API credentials:

```bash
curl -X POST https://aitbc.bubuit.net/api/v1/partners/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Your Service Name",
    "description": "Brief description of your service",
    "website": "https://yourservice.com",
    "contact": "contact@yourservice.com",
    "integration_type": "explorer"
  }'
```

**Response:**
```json
{
  "partner_id": "partner-uuid",
  "api_key": "aitbc_xxxxxxxxxxxx",
  "api_secret": "secret_xxxxxxxxxxxx",
  "rate_limit": {
    "requests_per_minute": 1000,
    "requests_per_hour": 50000
  }
}
```

### 2. Authenticate Requests

Use your API credentials for authenticated requests:

```bash
curl -H "Authorization: Bearer aitbc_xxxxxxxxxxxx" \
  https://aitbc.bubuit.net/api/explorer/blocks
```

## API Endpoints

### Blockchain Data

#### Get Latest Blocks
```http
GET /api/explorer/blocks?limit={limit}&offset={offset}
```

**Response:**
```json
{
  "blocks": [
    {
      "hash": "0x123...",
      "height": 1000000,
      "timestamp": "2025-12-28T18:00:00Z",
      "proposer": "0xabc...",
      "transaction_count": 150,
      "gas_used": "15000000",
      "size": 1024000
    }
  ],
  "total": 1000000
}
```

#### Get Block Details
```http
GET /api/explorer/blocks/{block_hash}
```

#### Get Transaction
```http
GET /api/explorer/transactions/{tx_hash}
```

#### Get Address Details
```http
GET /api/explorer/addresses/{address}?transactions={true|false}
```

### Marketplace Data

#### Get Active Offers
```http
GET /api/v1/marketplace/offers?status=active&limit={limit}
```

#### Get Bid History
```http
GET /api/v1/marketplace/bids?offer_id={offer_id}
```

#### Get Service Categories
```http
GET /api/v1/marketplace/services/categories
```

### Analytics Data

#### Get Network Stats
```http
GET /api/v1/analytics/network/stats
```

**Response:**
```json
{
  "total_blocks": 1000000,
  "total_transactions": 50000000,
  "active_addresses": 10000,
  "network_hashrate": 1500000000000,
  "average_block_time": 5.2,
  "marketplace_volume": {
    "24h": "1500000",
    "7d": "10000000",
    "30d": "40000000"
  }
}
```

#### Get Historical Data
```http
GET /api/v1/analytics/historical?metric={metric}&period={period}&start={timestamp}&end={timestamp}
```

**Metrics:**
- `block_count`
- `transaction_count`
- `active_addresses`
- `marketplace_volume`
- `gas_price`

**Periods:**
- `1h`, `1d`, `1w`, `1m`

## WebSocket Streams

Connect to the WebSocket for real-time updates:

```javascript
const ws = new WebSocket('wss://aitbc.bubuit.net/ws');

// Authenticate
ws.send(JSON.stringify({
  type: 'auth',
  api_key: 'aitbc_xxxxxxxxxxxx'
}));

// Subscribe to blocks
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'blocks'
}));

// Subscribe to transactions
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'transactions',
  filters: {
    to_address: '0xabc...'
  }
}));

// Handle messages
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

### Available Channels

- `blocks` - New blocks
- `transactions` - New transactions
- `marketplace_offers` - New marketplace offers
- `marketplace_bids` - New bids
- `governance` - Governance proposals and votes

## Bulk Data Export

### Export Blocks
```http
POST /api/v1/export/blocks
```

**Request:**
```json
{
  "start_block": 900000,
  "end_block": 1000000,
  "format": "json",
  "compression": "gzip"
}
```

**Response:**
```json
{
  "export_id": "export-uuid",
  "estimated_size": "500MB",
  "download_url": "https://aitbc.bubuit.net/api/v1/export/download/export-uuid"
}
```

### Export Transactions
```http
POST /api/v1/export/transactions
```

## Webhooks

Configure webhooks to receive event notifications:

```bash
curl -X POST https://aitbc.bubuit.net/api/v1/webhooks \
  -H "Authorization: Bearer aitbc_xxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://yourservice.com/webhook",
    "events": ["block.created", "transaction.confirmed"],
    "secret": "your_webhook_secret"
  }'
```

**Webhook Payload:**
```json
{
  "event": "block.created",
  "timestamp": "2025-12-28T18:00:00Z",
  "data": {
    "block": {
      "hash": "0x123...",
      "height": 1000000,
      "proposer": "0xabc..."
    }
  },
  "signature": "sha256_signature"
}
```

Verify webhook signatures:
```javascript
const crypto = require('crypto');

function verifyWebhook(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}
```

## Rate Limits

API requests are rate-limited based on your partner tier:

| Tier | Requests/Minute | Requests/Hour | Features |
|------|----------------|--------------|----------|
| Basic | 100 | 5,000 | Public data |
| Pro | 1,000 | 50,000 | + WebSocket |
| Enterprise | 10,000 | 500,000 | + Bulk export |

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640692800
```

## SDKs and Libraries

### Python SDK
```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    api_key="aitbc_xxxxxxxxxxxx",
    base_url="https://aitbc.bubuit.net/api/v1"
)

# Get latest block
block = client.blocks.get_latest()
print(f"Latest block: {block.height}")

# Stream transactions
for tx in client.stream.transactions():
    print(f"New tx: {tx.hash}")
```

### JavaScript SDK
```javascript
import { AITBCClient } from 'aitbc-sdk-js';

const client = new AITBCClient({
  apiKey: 'aitbc_xxxxxxxxxxxx',
  baseUrl: 'https://aitbc.bubuit.net/api/v1'
});

// Get network stats
const stats = await client.analytics.getNetworkStats();
console.log('Network stats:', stats);

// Subscribe to blocks
client.subscribe('blocks', (block) => {
  console.log('New block:', block);
});
```

## Explorer Integration Guide

### Display Blocks
```html
<div class="block-list">
  {% for block in blocks %}
  <div class="block-item">
    <a href="/block/{{ block.hash }}">
      Block #{{ block.height }}
    </a>
    <span class="timestamp">{{ block.timestamp }}</span>
    <span class="proposer">{{ block.proposer }}</span>
  </div>
  {% endfor %}
</div>
```

### Transaction Details
```javascript
async function showTransaction(txHash) {
  const tx = await client.transactions.get(txHash);
  
  document.getElementById('tx-hash').textContent = tx.hash;
  document.getElementById('tx-status').textContent = tx.status;
  document.getElementById('tx-from').textContent = tx.from_address;
  document.getElementById('tx-to').textContent = tx.to_address;
  document.getElementById('tx-amount').textContent = tx.amount;
  document.getElementById('tx-gas').textContent = tx.gas_used;
  
  // Show events
  const events = await client.transactions.getEvents(txHash);
  renderEvents(events);
}
```

### Address Activity
```javascript
async function loadAddress(address) {
  const [balance, transactions, tokens] = await Promise.all([
    client.addresses.getBalance(address),
    client.addresses.getTransactions(address),
    client.addresses.getTokens(address)
  ]);
  
  updateBalance(balance);
  renderTransactions(transactions);
  renderTokens(tokens);
}
```

## Analytics Integration

### Custom Dashboards
```python
import plotly.graph_objects as go
from aitbc_sdk import AITBCClient

client = AITBCClient(api_key="your_key")

# Get historical data
data = client.analytics.get_historical(
  metric='transaction_count',
  period='1d',
  start='2025-01-01',
  end='2025-12-28'
)

# Create chart
fig = go.Figure()
fig.add_trace(go.Scatter(
  x=data.timestamps,
  y=data.values,
  mode='lines',
  name='Transactions per Day'
))

fig.show()
```

### Real-time Monitoring
```javascript
const client = new AITBCClient({ apiKey: 'your_key' });

// Monitor network health
client.subscribe('blocks', (block) => {
  const blockTime = calculateBlockTime(block);
  updateBlockTimeMetric(blockTime);
  
  if (blockTime > 10) {
    alert('Block time is high!');
  }
});

// Monitor marketplace activity
client.subscribe('marketplace_bids', (bid) => {
  updateBidChart(bid);
  checkForAnomalies(bid);
});
```

## Best Practices

1. **Caching**: Cache frequently accessed data
2. **Pagination**: Use pagination for large datasets
3. **Error Handling**: Implement proper error handling
4. **Rate Limiting**: Respect rate limits and implement backoff
5. **Security**: Keep API keys secure and use HTTPS
6. **Webhooks**: Verify webhook signatures
7. **Monitoring**: Monitor your API usage and performance

## Support

For integration support:
- Documentation: https://aitbc.bubuit.net/docs/
- API Reference: https://aitbc.bubuit.net/api/v1/docs
- Email: partners@aitbc.io
- Discord: https://discord.gg/aitbc

## Example Implementations

### Block Explorer
- GitHub: https://github.com/aitbc/explorer-example
- Demo: https://explorer.aitbc-example.com

### Analytics Platform
- GitHub: https://github.com/aitbc/analytics-example
- Demo: https://analytics.aitbc-example.com

### Mobile App
- GitHub: https://github.com/aitbc/mobile-example
- iOS: https://apps.apple.com/aitbc-wallet
- Android: https://play.google.com/aitbc-wallet

## Changelog

### v1.2.0 (2025-12-28)
- Added governance endpoints
- Improved WebSocket reliability
- New analytics metrics

### v1.1.0 (2025-12-15)
- Added bulk export API
- Webhook support
- Python SDK improvements

### v1.0.0 (2025-12-01)
- Initial release
- REST API v1
- WebSocket streams
- JavaScript SDK
