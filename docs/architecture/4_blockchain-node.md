# Blockchain Node - AITBC Documentation

Multi-validator Proof-of-Authority consensus blockchain with optional PBFT finality, REST/WebSocket RPC, real-time gossip layer, and comprehensive observability

● Live

## Overview

The AITBC Blockchain Node is the core infrastructure component that maintains the distributed ledger. It implements a multi-validator Proof-of-Authority consensus mechanism with optional PBFT finality and supports high throughput for AI workload transactions.

### Key Features

- Multi-validator PoA consensus with optional PBFT finality
- REST and WebSocket RPC APIs
- Real-time gossip protocol for block propagation
- Comprehensive observability with Prometheus metrics
- SQLModel-based data persistence
- Built-in devnet tooling and scripts
- **State root validation enforcement** (Phase 1.3) - Validates state roots on block import
- **Genesis metadata validation** - Verifies genesis block allocation metadata
- **Auto-re-sync trigger** - Automatic re-sync after consecutive state root rejections

## Architecture

The blockchain node is built with a modular architecture separating concerns for consensus, storage, networking, and API layers.

#### Consensus Engine

Multi-validator PoA with proposer rotation and optional PBFT consensus

#### Storage Layer

SQLModel with SQLite/PostgreSQL support

#### Networking

Two distinct networking layers:

1. **Internal gossip** (Redis pub/sub) — Used by the blockchain node process to broadcast blocks/transactions to other services on the same machine (wallet, market, etc.) via `GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379`

2. **External block subscription** (HTTP + WebSocket over RPC) — Followers receive blocks from the hub via the lease-based subscription system:
   - Follower registers via `POST /rpc/subscribe` on the hub's RPC endpoint (peer key via `X-API-Key`, enrolled in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS`)
   - Hub pushes blocks via WebSocket on `/rpc/subscribe/ws`
   - Follower sends periodic heartbeats (`POST /rpc/heartbeat`) to maintain the lease
   - When no lease is held the node catches up with automatic pull-sync (bulk pull from `default_peer_rpc_url`) — there is no `POST /rpc/sync` endpoint. A deliberate operator reorg uses the admin-signed `POST /rpc/force-sync`.

3. **Gossip relay** (`aitbc-blockchain-p2p`, port 7070, hub-only) — A Starlette WebSocket server that bridges the internal Redis gossip to external peers. Followers do **not** connect to this service; they use the subscription system over the hub's RPC endpoint.

#### Observability

Prometheus metrics + structured logging

#### Unit System

The blockchain uses compute-units as the base unit:

- **1 AIT = 36,000,000 compute-units** (fixed integer scale)
- All on-chain values (balances, amounts, fees) are stored as integer compute-units
- User-facing interfaces (CLI, APIs, explorer) convert compute-units → AIT for display
- Transaction creation converts AIT → compute-units internally
- This enables precise sub-AIT billing while maintaining user-friendly AIT values

## API Reference

The blockchain node exposes both REST and WebSocket APIs for interaction.

### REST Endpoints

`GET /rpc/head`
Get the latest block header (`/rpc/chain/head` alias; `/rpc/height` returns the height only)

`POST /rpc/transaction`
Submit a new signed transaction — body `{chain_id?, from, to, amount, fee, nonce, type, payload, signature}`

`GET /rpc/transaction/{tx_hash}`
Look up a transaction by hash (path parameter)

`GET /rpc/balance/{address}`
Get account balance breakdown

`GET /rpc/blocks/{height}`
Get block by height (`/rpc/block/{height}` singular alias)

`GET /rpc/network-info`
Network/join information (chain ID, role, subscription and gossip WebSocket URLs)

`GET /rpc/subscribers`
List nodes holding a valid subscription lease

The same router is also mounted under `/v1`, so `/v1/blocks/{height}` etc. work too. Admin/control mutations (`/rpc/contracts/deploy`, `/rpc/governance/*`, `/rpc/escrow/*` router-level, `/rpc/gpu/*` writes, `/rpc/identity/*`, `/rpc/importBlock`, `/rpc/chains/*`) require `X-API-Key`; `POST /rpc/transaction` and `POST /rpc/staking/stake` are signature-verified in the request body instead.

### WebSocket Subscriptions

- `/rpc/subscribe/ws` — Lease-based block push to subscribed followers (hub → follower). Requires a prior lease from `POST /rpc/subscribe`; the first client message must be `{"node_id", "chain_id", "transport": "websocket"}`.
- `/rpc/gossip/ws?topic=<topic>` — Bidirectional gossip bridged into the node's gossip broker. Public topics (`transactions`, `status`, `mempool` + sub-topics) are publishable by anyone (rate-limited); restricted topics (`blocks`, `pbft`, `consensus` + sub-topics) require a signed validator challenge. Caps: `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=32`, `GOSSIP_MAX_MESSAGES_PER_MINUTE=2000`, `GOSSIP_MAX_MESSAGE_SIZE=1 MiB`.

There are no other WebSocket endpoints — no `/rpc/blocks` or `/rpc/transactions` streams.

## Configuration

The node can be configured via environment variables or configuration file.

### Key Settings

```bash
# Chain identity
CHAIN_ID=ait-localnet
SUPPORTED_CHAINS=ait-localnet   # defaults to CHAIN_ID

# Database — per-chain SQLite at $AITBC_DATA_DIR/data/<chain_id>/chain.db
# (e.g. /var/lib/aitbc/data/ait-localnet/chain.db). No single
# "blockchain.db" file exists.
AITBC_DATA_DIR=/var/lib/aitbc

# Network
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202

# Consensus / block production
PROPOSER_ID=0x...                          # proposer identity of this node
ENABLE_BLOCK_PRODUCTION=true               # false on followers
BLOCK_TIME_SECONDS=10                      # default block interval

# Subscription (followers)
DEFAULT_PEER_RPC_URL=https://hub.example.net
SUBSCRIPTION_ENABLED=true
SUBSCRIPTION_TRANSPORT=websocket

# Gossip limits
GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=32
GOSSIP_MAX_MESSAGES_PER_MINUTE=2000
GOSSIP_MAX_MESSAGE_SIZE=1048576

# Observability — Prometheus exporter port (the app also serves /metrics on 8202)
AITBC_NODE_METRICS_PORT=9009
LOG_LEVEL=info
```

> **Note:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Running a Node

### Development Mode

```bash
# The devnet helper creates a genesis and starts a local chain
cd apps/blockchain-node
python -m venv .venv
source .venv/bin/activate
./scripts/devnet_up.sh
```

### Production Mode

```bash
# Enable and start the systemd service
sudo systemctl enable aitbc-blockchain-node
sudo systemctl start aitbc-blockchain-node
```

## Monitoring

### Prometheus Metrics

Available on the metrics exporter at `http://localhost:9009/metrics` (`AITBC_NODE_METRICS_PORT`, default `9009`); the RPC app also serves `GET /metrics` on port `8202`.

Key metrics:

- `blockchain_blocks_total` - Total blocks produced
- `blockchain_transactions_total` - Total transactions processed
- `blockchain_consensus_rounds` - Consensus rounds completed
- `blockchain_network_peers` - Active peer connections

### Health Checks

```bash
# Node status (also reports node_wallet for escrow locks)
curl http://localhost:8202/health

# Sync optimization config
curl http://localhost:8202/rpc/sync/config

# Detailed per-chain sync state (optional SyncManager status server,
# disabled by default; enable with SYNC_MANAGER_HTTP_ENABLED=true)
curl http://localhost:8204/sync/status   # check-ports: ignore
```

## Troubleshooting

### Common Issues

1. **Node not syncing**
   - Check subscription leases: `curl http://localhost:8202/rpc/subscribers`
   - Check lease status for this node: `curl http://localhost:8202/rpc/lease/{node_id}`
   - Verify network connectivity
   - Check logs for consensus errors

2. **High memory usage**
   - Reduce `block_cache_size` in config
   - Enable block pruning

3. **RPC timeouts**
   - Increase `rpc_timeout` setting
   - Check system resources

## Development

### Building from Source

```bash
git clone https://github.com/oib/AITBC.git
cd AITBC/apps/blockchain-node
pip install -e .
```

### Running Tests

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/
```

## Security Considerations

- Validator keys should be kept secure
- Use HTTPS in production
- Implement rate limiting on RPC endpoints
- Regular security updates for dependencies
