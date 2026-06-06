# Blockchain Node API

The Blockchain Node API provides access to blockchain operations including block queries, transaction submission, and network status.

## Base URL

- Production: `https://aitbc.bubuit.net/api`
- Staging: `https://staging-api.aitbc.io`
- Development: `http://localhost:8080`

## Endpoints

### Block Operations

#### Get Block by Height
`GET /v1/blocks/{height}`

Retrieve a block by its height.

**Parameters:**
- `height` (path parameter): Block height as integer

**Response:** `200 OK`
```json
{
  "height": 12345,
  "hash": "0x...",
  "parent_hash": "0x...",
  "timestamp": "2026-05-11T10:00:00Z",
  "transactions": [],
  "state_root": "0x...",
  "difficulty": 1000
}
```

#### Get Head Block
`GET /v1/blocks/head`

Retrieve the latest (head) block in the blockchain.

**Response:** `200 OK`
```json
{
  "height": 12345,
  "hash": "0x...",
  "parent_hash": "0x...",
  "timestamp": "2026-05-11T10:00:00Z",
  "transactions": [],
  "state_root": "0x...",
  "difficulty": 1000
}
```

#### Get Block Range
`GET /v1/blocks?from={start}&to={end}`

Retrieve a range of blocks.

**Parameters:**
- `from` (query): Starting block height
- `to` (query): Ending block height

**Response:** `200 OK`
```json
[
  {
    "height": 12345,
    "hash": "0x...",
    "timestamp": "2026-05-11T10:00:00Z"
  }
]
```

### Transaction Operations

#### Get Transaction
`GET /v1/transactions/{tx_hash}`

Retrieve a transaction by its hash.

**Parameters:**
- `tx_hash` (path parameter): Transaction hash

**Response:** `200 OK`
```json
{
  "hash": "0x...",
  "block_height": 12345,
  "from": "0x...",
  "to": "0x...",
  "value": 1000,
  "gas_used": 21000,
  "timestamp": "2026-05-11T10:00:00Z"
}
```

#### Submit Transaction
`POST /v1/transactions`

Submit a new transaction to the blockchain.

**Request Body:**
```json
{
  "from": "0x...",
  "to": "0x...",
  "value": 1000,
  "gas": 21000,
  "data": "0x...",
  "signature": "0x..."
}
```

**Response:** `201 Created`
```json
{
  "hash": "0x...",
  "status": "pending"
}
```

### Network Status

#### Get Network Info
`GET /v1/network`

Retrieve network status and information.

**Response:** `200 OK`
```json
{
  "chain_id": 1,
  "block_height": 12345,
  "peer_count": 42,
  "sync_status": "synced",
  "version": "1.0.0"
}
```

#### Get Peers
`GET /v1/network/peers`

Retrieve list of connected peers.

**Response:** `200 OK`
```json
[
  {
    "peer_id": "Qm...",
    "address": "192.168.1.100:8080",
    "latency_ms": 50,
    "is_outbound": true
  }
]
```

### Smart Contract Operations

#### Call Contract
`POST /v1/contracts/{address}/call`

Call a smart contract method (read-only).

**Request Body:**
```json
{
  "method": "balanceOf",
  "args": ["0x..."]
}
```

**Response:** `200 OK`
```json
{
  "result": "0x...",
  "gas_used": 1000
}
```

#### Send Transaction to Contract
`POST /v1/contracts/{address}/transact`

Send a transaction to a smart contract (state-changing).

**Request Body:**
```json
{
  "method": "transfer",
  "args": ["0x...", 1000],
  "gas": 100000,
  "value": 0
}
```

**Response:** `201 Created`
```json
{
  "hash": "0x...",
  "status": "pending"
}
```

## Examples

### cURL

```bash
# Get head block
curl http://localhost:8080/v1/blocks/head

# Get block by height
curl http://localhost:8080/v1/blocks/12345

# Get network info
curl http://localhost:8080/v1/network

# Submit transaction
curl -X POST http://localhost:8080/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0x...",
    "to": "0x...",
    "value": 1000,
    "gas": 21000,
    "signature": "0x..."
  }'
```

### Python SDK

```python
import aitbc_sdk

client = aitbc_sdk.BlockchainClient(base_url="http://localhost:8080")

# Get head block
head_block = client.get_head_block()
print(f"Current height: {head_block['height']}")

# Get block by height
block = client.get_block(height=12345)

# Get network info
network = client.get_network_info()
print(f"Peer count: {network['peer_count']}")
```

## WebSocket

Real-time blockchain events are available via WebSocket connection:

```
ws://localhost:8080/v1/events
```

The WebSocket sends events as JSON messages:
```json
{
  "type": "new_block",
  "block": {
    "height": 12346,
    "hash": "0x...",
    "timestamp": "2026-05-11T10:05:00Z"
  }
}
```

### Escrow Operations

The blockchain node also hosts the marketplace escrow service. See the full reference at [Escrow API](../escrow-api.md).

#### Create Escrow
`POST /rpc/escrow/create`

Lock buyer funds for a marketplace job. Automatically called by marketplace-service on `book_offer`.

#### Get Escrow State
`GET /rpc/escrow/{job_id}`

Query escrow state: `created`, `released`, `refunded`, etc.

#### Release Escrow
`POST /rpc/escrow/{job_id}/release`

Release funds to provider on job completion.

#### Refund Escrow
`POST /rpc/escrow/{job_id}/refund`

Refund funds to buyer.

**Base URL:** `http://localhost:8202/rpc`

---

## Rate Limits

- Block queries: 1000 requests per minute
- Transaction submission: 100 requests per minute
- Contract calls: 500 requests per minute
- Escrow operations: 100 requests per minute

## OpenAPI Specification

The complete OpenAPI 3.1.0 specification is available in [openapi.json](./openapi.json).
