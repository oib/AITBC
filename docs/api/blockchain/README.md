# Blockchain Node API

The Blockchain Node API provides access to blockchain operations including block queries, transaction submission, and network status.

**Note:** This API uses an RPC-style interface with the `/rpc/` prefix for all endpoints, not the REST-style `/v1/` prefix.

## Base URL

- Production: `https://aitbc.bubuit.net/rpc`
- Staging: `https://staging-api.aitbc.io/rpc`
- Development: `http://localhost:8202/rpc`

## API Documentation

Interactive API documentation is available via Swagger UI:
- Development: `http://localhost:8202/docs`
- OpenAPI Spec: `http://localhost:8202/openapi.json`

## Endpoints

**Note:** All blockchain RPC endpoints use the `/rpc/` prefix.

### Block Operations

#### Get Block by Height
`GET /rpc/blocks/{height}`

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
`GET /rpc/head`

Retrieve the latest (head) block in the blockchain.

**Response:** `200 OK`
```json
{
  "height": 11629,
  "hash": "0x9b7cb511a6e633561b803f381d864d935c439ca16242dc3d3be5fe9e748a14bc",
  "timestamp": "2026-06-07T19:55:20.950893",
  "tx_count": 0
}
```

#### Get Block Range
`GET /rpc/blocks-range?from={start}&to={end}`

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
`GET /rpc/transaction?hash={tx_hash}`

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
`POST /rpc/transaction`

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
`GET /rpc/network-info`

Retrieve network status and information.

**Response:** `200 OK`
```json
{
  "p2p_endpoint": "aitbc3:8200",
  "p2p_node_id": "node-19b909970eeb4a6a87865dbb92c4b5dc",
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "network_type": "open_island",
  "supported_chains": ["ait-hub.aitbc.bubuit.net"],
  "connection_instructions": "Connect via P2P protocol to aitbc3:8200",
  "rpc_endpoint": "http://aitbc3/rpc",
  "api_gateway": "http://aitbc3/api",
  "contact_email": "andreas.fleckl@bubuit.net",
  "version": "0.4.3"
}
```

#### Get Peers
`GET /rpc/subscribers`

Retrieve list of connected peers (subscribers).

**Response:** `200 OK`
```json
[
  {
    "peer_id": "node-...",
    "address": "192.168.1.100:8200",
    "last_seen": "2026-06-07T19:55:20Z"
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
curl http://localhost:8202/rpc/head

# Get block by height
curl http://localhost:8202/rpc/blocks/12345

# Get network info
curl http://localhost:8202/rpc/network-info

# Submit transaction
curl -X POST http://localhost:8202/rpc/transaction \
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

client = aitbc_sdk.BlockchainClient(base_url="http://localhost:8202/rpc")

# Get head block
head_block = client.get_head_block()
print(f"Current height: {head_block['height']}")

# Get block by height
block = client.get_block(height=12345)

# Get network info
network = client.get_network_info()
print(f"Chain ID: {network['chain_id']}")
print(f"Network type: {network['network_type']}")
```

## WebSocket

Real-time blockchain events are available via WebSocket connection:

```
ws://localhost:8202/rpc/subscribe
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

The blockchain node also hosts the marketplace escrow service.

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
