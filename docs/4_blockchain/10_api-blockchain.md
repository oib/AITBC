# Blockchain API Reference
Complete API reference for blockchain node operations.

## RPC Endpoints

### Get Block

```
GET /rpc/block/{height}
```

**Response:**

```json
{
  "block": {
    "header": {
      "height": 100,
      "timestamp": "2026-02-13T10:00:00Z",
      "proposer": "ait-devnet-proposer-1",
      "parent_hash": "0xabc123...",
      "state_root": "0xdef456...",
      "tx_root": "0xghi789..."
    },
    "transactions": [...],
    "receipts": [...]
  },
  "block_id": "0xjkl012..."
}
```

### Get Transaction

```
GET /rpc/tx/{tx_hash}
```

**Response:**

```json
{
  "tx": {
    "hash": "0xabc123...",
    "type": "transfer",
    "from": "0x1234...",
    "to": "0x5678...",
    "value": 100,
    "gas": 21000,
    "data": "0x..."
  },
  "height": 100,
  "index": 0
}
```

### Submit Transaction

```
POST /rpc/broadcast_tx_commit
```

**Request Body:**

```json
{
  "tx": "0xabc123...",
  "type": "transfer",
  "from": "0x1234...",
  "to": "0x5678...",
  "value": 100,
  "data": "0x..."
}
```

**Response:**

```json
{
  "tx_response": {
    "code": 0,
    "data": "0x...",
    "log": "success",
    "hash": "0xabc123..."
  },
  "height": 100,
  "index": 0
}
```

### Get Status

```
GET /rpc/status
```

**Response:**

```json
{
  "node_info": {
    "protocol_version": "v0.1.0",
    "network": "ait-devnet",
    "node_id": "12D3KooW...",
    "listen_addr": "tcp://0.0.0.0:7070"
  },
  "sync_info": {
    "latest_block_height": 1000,
    "catching_up": false,
    "earliest_block_height": 1
  },
  "validator_info": {
    "voting_power": 1000,
    "proposer": true
  }
}
```

### Get Mempool

```
GET /rpc/mempool
```

**Response:**

```json
{
  "size": 50,
  "txs": [
    {
      "hash": "0xabc123...",
      "fee": 0.001,
      "size": 200
    }
  ]
}
```

## WebSocket Endpoints

### Subscribe to Blocks

```
WS /rpc/block
```

**Message:**

```json
{
  "type": "new_block",
  "data": {
    "height": 1001,
    "hash": "0x...",
    "proposer": "ait-devnet-proposer-1"
  }
}
```

### Subscribe to Transactions

```
WS /rpc/tx
```

**Message:**

```json
{
  "type": "new_tx",
  "data": {
    "hash": "0xabc123...",
    "type": "transfer",
    "from": "0x1234...",
    "to": "0x5678...",
    "value": 100
  }
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Internal error |
| 2 | Invalid transaction |
| 3 | Invalid request |
| 4 | Not found |
| 5 | Conflict |

## Rate Limits

- 1000 requests/minute for RPC
- 100 requests/minute for writes
- 10 connections per IP

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
