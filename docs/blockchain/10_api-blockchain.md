# Blockchain API Reference

**Last Updated:** 2026-09-16

Complete API reference for the blockchain node RPC service.

The blockchain RPC is a FastAPI app (`aitbc_chain.app`) served by the
`aitbc-blockchain-rpc` systemd unit. It binds `rpc_bind_host`/`rpc_bind_port`
(default `0.0.0.0:8202`) and mounts the same router under both `/rpc` and a
`/v1` compatibility prefix. The examples below use `/rpc`.

This is **not** a Tendermint/Cosmos RPC surface — there is no
`broadcast_tx_*`, `node_info`, `sync_info`, `validator_info`, `/rpc/tx`, or
`/rpc/block` subscription. The endpoints below are the ones that exist.

## Read-surface posture (#1936)

The `/rpc/*` read surface reachable through the edge vhost is
**public-read-by-design for chain data** — the same posture as any public
blockchain RPC (accounts, balances, blocks, transactions, mempool, state
snapshot/delta, AI jobs, GPU/edge registrations, market listings, forum
and DM ciphertext, on-chain dispute records, bridge transfer listings,
consensus validator set). The explorer, public website, MCP read tools,
monitoring textfile exporters, ops scripts and follower sync all consume
these reads without credentials, and `docs/ops/failover-runbook.md` treats
the chain-read paths as the flippable public read-path.

What is **not** public:

- Every mutating route requires `X-API-Key` (node key, a
  `BLOCKCHAIN_RPC_API_KEY_PEERS` fleet key, or — on the lease routes — an
  issued `/rpc/join` peer key). See the auth notes per section.
- `GET /rpc/export-chain` requires a **fleet** key — issued join keys are
  rejected (#1871).
- `GET /rpc/lease/{node_id}` and `GET /rpc/subscribers` require a peer
  key (#1936): lease/subscriber state is node-local fleet topology, not
  chain data. Issued join keys are bound to their own `node_id`.
- `/rpc/subscribe/ws` requires a peer key inside the handshake frame
  (#1702); `/rpc/gossip/ws` allows anonymous subscribe but gates publish
  on public topics behind a peer key or validator auth (#1874).
- Node-local operational views that stay public by design:
  `/rpc/network-info` (the documented join contract), `/rpc/info`,
  `/rpc/status`, `/rpc/sync/config`, `/rpc/health`-style bridge
  `security/status` + `oracle/status` probes (runbook/monitoring
  consumers), `/rpc/chains`, `/rpc/islands`, `/rpc/mining/*` (admin-key
  gated), `/rpc/join` (self-serve, rate-limited).

`/rpc/state/snapshot` and `/rpc/state/delta` remain public deliberately
(#1871 residual): every account they return is already readable
individually via `/rpc/account/{address}`, and unauthenticated consumers
(follower `sync_state`, `authority-balances-textfile.py`, MCP read
tools, ops verify scripts) depend on them. They are rate-limited
(`10/min`) as the bulk-disclosure mitigation.

## Transactions

### Submit Transaction

```
POST /rpc/transaction
```

Validates the signature, checks nonce/balance admission rules, and queues the
transaction into the mempool for the next block.

**Request body** (`TransactionRequest` in `rpc/transactions.py`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chain_id` | string | no | Target chain (defaults to the node's `chain_id`) |
| `from` | string | yes | Sender address (`0x` 40-hex) |
| `to` | string | yes | Recipient address |
| `amount` | int | yes | Transfer amount in compute-units (1 AIT = 36,000,000) |
| `fee` | int | no | Fee in compute-units (default `DEFAULT_TX_FEE_UNITS`) |
| `nonce` | int | no | Sender nonce (default 0; must equal the account nonce) |
| `type` | string | no | `TRANSFER` (default), `MESSAGE`, `RECEIPT_CLAIM`, `GPU_MARKET`, `EXCHANGE`, ... |
| `payload` | object | no | Type-specific payload; `to`/`amount` are mirrored into it |
| `signature` | string | yes | secp256k1 signature over the transaction fields |

```json
{
  "type": "TRANSFER",
  "from": "0x1234...",
  "to": "0x5678...",
  "amount": 36000000,
  "fee": 360000,
  "nonce": 7,
  "payload": {},
  "signature": "0xabc123..."
}
```

**Response:**

```json
{
  "success": true,
  "transaction_hash": "0xabc123...",
  "message": "Transaction submitted to mempool"
}
```

### Get Transaction

```
GET /rpc/transaction/{tx_hash}?chain_id=<chain>
```

**Response:**

```json
{
  "transaction_id": 1234,
  "tx_hash": "0xabc123...",
  "chain_id": "ait-localnet",
  "block_height": 100,
  "sender": "0x1234...",
  "recipient": "0x5678...",
  "payload": {"amount": 36000000, "to": "0x5678..."},
  "type": "TRANSFER",
  "status": "confirmed",
  "created_at": "2026-02-13T10:00:00+00:00",
  "timestamp": null,
  "nonce": 7,
  "value": 36000000,
  "fee": 360000
}
```

`404` if the hash is unknown on that chain.

### Pending Transactions (Mempool)

```
GET /rpc/mempool?chain_id=<chain>&limit=100
GET /rpc/pending            # alias
```

**Response:**

```json
{
  "transactions": [ ... ],
  "count": 50
}
```

## Blocks and Head

### Get Chain Head

```
GET /rpc/head?chain_id=<chain>
GET /rpc/chain/head         # compatibility alias
```

**Response:**

```json
{
  "height": 1000,
  "hash": "0xjkl012...",
  "timestamp": "2026-02-13T10:00:00+00:00",
  "tx_count": 12
}
```

`GET /rpc/height` returns just `{"height": 1000}`.

### Get Block

```
GET /rpc/blocks/{height}?chain_id=<chain>
GET /rpc/block?height=<n>   # alias; head block when height omitted
GET /rpc/block/{height}     # singular alias
```

**Response:**

```json
{
  "chain_id": "ait-localnet",
  "height": 100,
  "hash": "0xabc123...",
  "parent_hash": "0xdef456...",
  "proposer": "0xDb52...",
  "timestamp": "2026-02-13T10:00:00+00:00",
  "tx_count": 3,
  "state_root": "0xghi789...",
  "bridge_state_root": "0x...",
  "signature": "0x...",          // proposer secp256k1 signature (v0.7.1+)
  "transactions": [
    {
      "tx_hash": "0x...",
      "from": "0x1234...",
      "to": "0x5678...",
      "value": 36000000,
      "fee": 360000,
      "nonce": 7,
      "type": "TRANSFER"
    }
  ]
}
```

### Block Range

```
GET /rpc/blocks-range?start=<n>&end=<n>&chain_id=<chain>
GET /rpc/blocks-range?limit=<n>          # last N blocks from head
```

Returns the same block objects for an inclusive height range (`start`/`end`,
`include_tx` controls transaction payloads) — used by bulk sync. Defaults to
`start=0, end=10`.

## Node Status

### Get Status / Info

```
GET /rpc/status             # alias for /rpc/info
GET /rpc/info
```

**Response:**

```json
{
  "chain_id": "ait-localnet",
  "height": 1000,
  "total_transactions": 15234,
  "total_accounts": 87,
  "genesis_params": {
    "block_time_seconds": 10,
    "max_block_size_bytes": 1000000
  },
  "last_block_hash": "0xjkl012...",
  "timestamp": "2026-02-13T10:00:00+00:00"
}
```

There is no `sync_info`/`validator_info` — sync state lives in the SyncManager
(see `aitbc blockchain sync-status`) and validator state under `/rpc/consensus/*`.

### Get Network Info

```
GET /rpc/network-info
```

Public, machine-readable description of the node for nodes that want to join:

```json
{
  "chain_id": "ait-localnet",
  "island_id": "...",
  "supported_chains": ["ait-localnet"],
  "is_hub": true,
  "role": "hub",
  "public_rpc_url": "https://hub.example.net/rpc",
  "subscription_websocket_url": "wss://hub.example.net/rpc/subscribe/ws",
  "gossip_websocket_url": "wss://hub.example.net/rpc/gossip/ws",
  "gossip_websocket_urls": { "ait-localnet": "wss://hub.example.net/rpc/gossip/ws?chain=ait-localnet" },
  "gossip_auth_required": true,
  "validators": [ ... ],
  "connection_instructions": "Set default_peer_rpc_url=... "
}
```

### Get Proposer

```
GET /rpc/proposer
```

Returns `{proposer_id, chain_id, supported_chains}` — the address this node
signs blocks as.

## Accounts

### Get Balance Breakdown

```
GET /rpc/balance/{address}?chain_id=<chain>
```

Returns the balance breakdown from the balance tracker: available balance,
staked amount, bridge-locked amount, and total.

Related: `GET /rpc/account/{address}` (alias `/rpc/accounts/{address}`) for the
raw account row, `GET /rpc/accounts` to list accounts, and
`GET /rpc/balance/{address}/reconcile` to recompute a balance from recorded
operations.

## Consensus

Mounted when the consensus sub-router loads; these back the
`aitbc blockchain consensus` CLI commands.

```
GET /rpc/consensus/status?chain_id=<chain>
GET /rpc/consensus/validators?chain_id=<chain>
GET /rpc/consensus/slashing-history?chain_id=<chain>
```

## Subscription (Follower Block Push)

The lease-based subscription system is how followers receive blocks. These
endpoints exist on the **hub**; followers call them outbound.

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /rpc/subscribe` | peer key (node RPC key, `BLOCKCHAIN_RPC_API_KEY_PEERS` member, or issued `/rpc/join` key bound to the same `node_id`) | Register a lease: `{node_id, transport, chain_id, duration?}` |
| `POST /rpc/heartbeat` | peer key | Extend the lease: `{node_id, chain_id}` |
| `GET /rpc/lease/{node_id}` | peer key | Lease status for a subscriber (#1936) |
| `DELETE /rpc/lease/{node_id}` | peer key | Revoke a lease |
| `GET /rpc/subscribers` | peer key | List subscribers with valid leases (#1936) |

**Response for `GET /rpc/subscribers`:**

```json
{
  "subscribers": [
    {"node_id": "node-...", "transport": "websocket", "chain_id": "ait-localnet", "expiry": 1730000000.0, "client_ip": "10.0.0.5"}
  ],
  "count": 1
}
```

## Sync Operations

### Get Sync Config

```
GET /rpc/sync/config
```

Returns the sync optimization configuration (`sync_parallel_*`,
`sync_delta_*`, `gossip_*` settings). There is no `/rpc/sync` or
`/rpc/sync/status` route — sync progress is observed through
`aitbc blockchain sync-status` and the node logs.

### Export Chain

```
GET /rpc/export-chain?chain_id=<chain>
```

Requires `X-API-Key`: this node's `BLOCKCHAIN_RPC_API_KEY` or a key listed in
its `BLOCKCHAIN_RPC_API_KEY_PEERS` (fleet peers calling `force-sync` use
their own node key). Issued `/rpc/join` keys are rejected (#1871).

Exports the full chain state (blocks, accounts, transactions) as JSON:

```json
{
  "success": true,
  "export_data": {
    "chain_id": "ait-localnet",
    "export_timestamp": "...",
    "block_count": 1000,
    "account_count": 87,
    "transaction_count": 15234,
    "blocks": [ ... ],
    "accounts": [ ... ],
    "transactions": [ ... ]
  },
  "export_size_bytes": 12345678
}
```

### Import Chain

```
POST /rpc/import-chain
```

Imports a full chain-state export. **Admin-signed request** — the body must
carry `admin_address` and `admin_signature` over the payload
(`verify_admin_signature` in `rpc/sync.py`).

### Import Single Block

```
POST /rpc/importBlock
X-API-Key: <key>
```

Imports one block through the validated sync path (signature, parent linkage,
state root, transaction application). Requires `X-API-Key`. Returns `409` when
the height or hash already exists.

### Force Sync

```
POST /rpc/force-sync
```

Force a reorganization to match a peer. Requires `X-API-Key` **and** an
admin-signed request body:

```json
{
  "peer_url": "https://peer.example.net",
  "admin_address": "0x...",
  "admin_signature": "0x...",
  "issued_at": "<unix epoch, within ±5 min>",
  "nonce": "<unique, single-use>",
  "target_chain_id": "<this node's chain id>",
  "target_height": 2000
}
```

The node fetches `GET {peer_url}/rpc/export-chain` and imports it through the
normal import path. `peer_url` must be `http`/`https`; loopback, link-local,
reserved, multicast and unspecified addresses are rejected (SSRF guard) —
private LAN addresses are allowed for fleet peers. Prefer
`aitbc network force-sync`, which signs and injects the API key.

## Contracts

```
POST /rpc/contracts/call
```

Read-only contract call: `{address, method, params?, chain_id?}`. Contract
deployment and mutating calls go through `POST /rpc/transaction` with the
appropriate `type`/`payload`; see the contracts router for the full set of
`/rpc/contracts/*` routes.

## WebSocket Endpoints

WebSockets are mounted under `/rpc` on the same port (8202).

### Block Subscription (followers)

```
WS /rpc/subscribe/ws
```

Requires a valid lease — register first via `POST /rpc/subscribe`. The hub
pushes new blocks to the follower over this socket; the follower renews the
lease with `POST /rpc/heartbeat`.

### Gossip Stream

```
WS /rpc/gossip/ws?topic=<topic>
```

Streams a gossip topic (e.g. `transactions`, `blocks.<chain_id>`). Public
topics stream after the server accepts the socket; publishing on them
requires a `peer_auth` frame with a peer key (#1874 — see
`docs/api/websocket.md`). **Restricted topics require
a signed validator challenge** — the server sends an `auth_challenge` message
and the client must answer with a valid validator signature before the stream
starts. Per-IP connection and message-rate limits apply
(`gossip_max_*` settings).

## Errors and Rate Limits

Errors are standard FastAPI responses — HTTP status plus
`{"detail": "..."}`:

| Status | Meaning |
|--------|---------|
| 400 | Malformed request (bad hash/height, invalid URL, ...) |
| 403 | Bad or missing signature / API key |
| 404 | Block, transaction, or lease not found |
| 409 | Import conflict (height or hash already exists) |
| 503 | Optional sub-router failed to load; service unavailable |

Per-endpoint rate limits are enforced by the `rate_limit` decorator — read
endpoints are typically 200/min, imports and force-sync 50/min, subscription
writes lower. `429` responses include the standard FastAPI `detail` body.

## Metrics and Health

The RPC process also serves:

- `GET /metrics` — Prometheus text exposition (combined registry)
- `GET /health` — `{status, supported_chains, proposer_id, node_wallet}`

The node process (`aitbc-blockchain-node`) serves its own `/metrics` on
`AITBC_NODE_METRICS_PORT` (default `9009`).

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
