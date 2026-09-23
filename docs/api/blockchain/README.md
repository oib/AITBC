# Blockchain Node API

The Blockchain Node API provides access to blockchain operations including block queries, transaction submission, and network status.

**Note:** The canonical mount is the RPC-style `/rpc/` prefix. The same router is also mounted under `/v1/` on the node for backward compatibility, so `/v1/blocks/{height}` etc. also work.

## Base URL

- Production (public hub, via nginx): `https://hub.example.net/rpc`
- Development: `http://localhost:8202/rpc`

The raw `http://hub.example.net:8202` listener is internal-only; external clients must go through the nginx TLS endpoint.

## API Documentation

Interactive API documentation is available via Swagger UI:

- Development: `http://localhost:8202/docs`
- OpenAPI Spec: `http://localhost:8202/openapi.json`

## Endpoints

### Block Operations

#### Get Block by Height

`GET /rpc/blocks/{height}`

Retrieve a block by its height (`GET /rpc/block/{height}` is a singular alias; `GET /rpc/block?height=` also works).

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
  "tx_count": 3
}
```

#### Get Head Block

`GET /rpc/head`

Retrieve the latest (head) block in the blockchain. `GET /rpc/chain/head` is a compatibility alias, `GET /rpc/height` returns just the height.

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

`GET /rpc/blocks-range?start={start}&end={end}&limit={n}&include_tx={bool}&chain_id={id}`

Retrieve a range of blocks.

**Parameters:**

- `start` (query): Starting block height
- `end` (query): Ending block height
- `limit` (query): Max blocks to return
- `include_tx` (query): Include full transaction bodies
- `chain_id` (query): Select a non-default chain

**Response:** `200 OK`

```json
{
  "success": true,
  "blocks": [
    {
      "height": 12345,
      "hash": "0x...",
      "timestamp": "2026-05-11T10:00:00Z"
    }
  ],
  "count": 1
}
```

### Transaction Operations

#### Get Transaction

`GET /rpc/transaction/{tx_hash}`

Retrieve a transaction by its hash (`tx_hash` is a **path** parameter, not a query parameter). Optional `?chain_id=` query selects a non-default chain. Returns `404` when the chain does not have the hash.

**Response:** `200 OK`

```json
{
  "transaction_id": 42,
  "tx_hash": "0x...",
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "block_height": 12345,
  "sender": "0x...",
  "recipient": "0x...",
  "payload": {"to": "0x...", "amount": 1000},
  "type": "TRANSFER",
  "status": "confirmed",
  "created_at": "2026-05-11T10:00:00",
  "timestamp": 1720000000.0,
  "nonce": 7,
  "value": 1000,
  "fee": 1
}
```

#### Submit Transaction

`POST /rpc/transaction`

Submit a new signed transaction to the mempool.

**Request Body** (this is the full schema — there are no `gas`/`data`/`value` request fields; `value`/`gas`-style Ethereum field names do not exist):

```json
{
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "from": "0x...",
  "to": "0x...",
  "amount": 1000,
  "fee": 1,
  "nonce": 7,
  "type": "TRANSFER",
  "payload": {"to": "0x...", "amount": 1000},
  "signature": "0x..."
}
```

- `from`, `to`, `signature` are required; `amount` and `fee` are integers in compute-units (1 AIT = 36,000,000 units); `nonce` must equal the sender's current account nonce; `type` defaults to `TRANSFER`; `payload` is an arbitrary dict (recipient/amount are auto-filled into it when absent).
- The `signature` is verified against `from` over the whole transaction body (including `chain_id`, which prevents cross-chain replay); an invalid signature returns `403`.

**Response:** `200 OK`

```json
{
  "success": true,
  "transaction_hash": "0x...",
  "message": "Transaction submitted to mempool"
}
```

Related: `GET /rpc/mempool` lists pending transactions and `GET /rpc/transactions` queries confirmed transactions with filters (`transaction_type`, `address`, `job_id`, `status`, `chain_id`, `limit`, ...).

### Network Status

#### Get Network Info

`GET /rpc/network-info`

Retrieve network configuration for joining the island. The node derives the public URLs from the reverse-proxy headers (`X-Forwarded-Proto`, `Host`) or the `AITBC_PROTOCOL`/`AITBC_HOSTNAME` overrides.

**Response:** `200 OK` (representative fields)

```json
{
  "node_id": "node-...",
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "island_id": "ait-hub.aitbc.bubuit.net-island",
  "network_type": "open_island",
  "supported_chains": ["ait-hub.aitbc.bubuit.net"],
  "is_hub": true,
  "role": "hub",
  "public_rpc_url": "https://hub.example.net/rpc",
  "subscription_websocket_url": "wss://hub.example.net/rpc/subscribe/ws",
  "gossip_websocket_url": "wss://hub.example.net/rpc/gossip/ws",
  "gossip_auth_required": true,
  "validators": [],
  "default_peer_rpc_url": "https://hub.example.net",
  "connection_instructions": "Set default_peer_rpc_url=... and enable subscription (subscription_transport=websocket). Register via POST .../rpc/subscribe, then receive blocks via WebSocket at .../rpc/subscribe/ws. Extend the lease with POST .../rpc/heartbeat.",
  "version": "0.7.6"
}
```

> **Joining is a subscription model, not raw P2P dialing.** Followers do not "connect via P2P to <node>:7070"; they register with `POST /rpc/subscribe` (peer-key authenticated), then receive pushed blocks over `WS /rpc/subscribe/ws` and extend the lease with `POST /rpc/heartbeat`. The `p2p_endpoint`/`p2p_bind_port` (default `8200`) in the response refers to the node's internal gossip listener and is not a public join address.

#### Get Subscribers

`GET /rpc/subscribers`

Retrieve the list of nodes holding a valid subscription lease (the effective peer list for block distribution).

**Response:** `200 OK`

```json
{
  "subscribers": [
    {"node_id": "node-...", "chain_id": "ait-hub.aitbc.bubuit.net", "transport": "websocket"}
  ]
}
```

### Smart Contract Operations

The contracts router is mounted at `/contracts` under both `/rpc` and `/v1`. There is **no** per-address `/v1/contracts/{address}/call` or `/transact` route — all calls go through `POST /rpc/contracts/call`.

#### Call Contract

`POST /rpc/contracts/call` (also `POST /v1/contracts/call`)

Call a method on a deployed contract. The call is read-only: it looks the contract up by `address` and returns the stored state entry for `method`.

**Request Body:**

```json
{
  "address": "0x...",
  "method": "balanceOf",
  "params": {"account": "0x..."},
  "chain_id": "ait-hub.aitbc.bubuit.net"
}
```

**Response:** `200 OK`

```json
{
  "success": true,
  "result": "...",
  "address": "0x...",
  "method": "balanceOf",
  "params": {"account": "0x..."},
  "abi": {}
}
```

Other contract routes: `GET /rpc/contracts` (list deployed contracts), `POST /rpc/contracts/deploy` (requires `X-API-Key`), `POST /rpc/contracts/verify` (ZK proof check), plus the `/rpc/contracts/messaging/*` forum routes.

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
    "amount": 1000,
    "fee": 1,
    "nonce": 7,
    "type": "TRANSFER",
    "payload": {"to": "0x...", "amount": 1000},
    "signature": "0x..."
  }'
```

### Python SDK

The `aitbc-sdk` package (`packages/py/aitbc-sdk`) does **not** ship a `BlockchainClient`. It exposes `CoordinatorAPIClient` (with `.wallet` and `.registry` sub-clients), `CoordinatorReceiptClient`, `WalletClient`, and `RegistryClient` — all aimed at the coordinator-api, not the chain RPC. For raw chain reads use any HTTP client:

```python
import httpx

RPC = "http://localhost:8202/rpc"

head = httpx.get(f"{RPC}/head").json()
print(f"Current height: {head['height']}")

block = httpx.get(f"{RPC}/blocks/12345").json()
network = httpx.get(f"{RPC}/network-info").json()
print(f"Chain ID: {network['chain_id']}")

tx = httpx.get(f"{RPC}/transaction/0x<tx_hash>").json()

# Coordinator-side calls go through the SDK:
from aitbc_sdk import CoordinatorAPIClient
client = CoordinatorAPIClient(base_url="http://localhost:8203")
print(client.health())
```

## WebSocket

Real-time block delivery uses the subscription WebSocket — **not** `/rpc/subscribe` (that path is the REST lease-registration endpoint):

```
WS /rpc/subscribe/ws
```

You must hold a valid lease first: `POST /rpc/subscribe` with a peer key (`X-API-Key`), then connect and send `{"node_id": "...", "chain_id": "...", "transport": "websocket"}` as the first message. Blocks on the `blocks.<chain_id>` topic are pushed as JSON; the server sends a `{"type": "ping"}` heartbeat every ~20 s.

The second WebSocket is `WS /rpc/gossip/ws?topic=<topic>` for bidirectional gossip (restricted topics such as `blocks`/`pbft`/`consensus` require a signed validator challenge). See [websocket.md](../websocket.md) for the full protocol.

### Escrow Operations

The blockchain node also hosts the marketplace escrow service. **All escrow routes — including GET — require the `X-API-Key` header** (router-level dependency against `BLOCKCHAIN_RPC_API_KEY`).

#### Create Escrow

`POST /rpc/escrow/create`

Lock buyer funds for a marketplace job. The body must include a buyer-signed `lock_tx` (or `lock_signature` plus lock fields) transferring the amount to the node wallet. See [escrow-api.md](../escrow-api.md).

#### Get Escrow State

`GET /rpc/escrow/{job_id}`

Query escrow state: `locked`, `released`, `refunded`, etc.

#### Release Escrow

`POST /rpc/escrow/{job_id}/release`

Release funds to provider on job completion.

#### Refund Escrow

`POST /rpc/escrow/{job_id}/refund`

Refund funds to buyer.

**Base URL:** `http://localhost:8202/rpc`

---

## Rate Limits

Rate limits are applied **per route** with `@rate_limit(rate=..., per=...)` decorators rather than a single global policy — e.g. `POST /rpc/transaction` is limited to 50 requests/60 s and most read endpoints to 100–200 requests/60 s. See `apps/blockchain-node/src/aitbc_chain/rpc/` for the authoritative per-route values.

## OpenAPI Specification

The complete OpenAPI 3.1.0 specification is available in [openapi.json](./openapi.json).
