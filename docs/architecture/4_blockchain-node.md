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

1. **Internal gossip** (Redis pub/sub) — Used by the blockchain node process to broadcast blocks/transactions to other services on the same machine (wallet, marketplace, etc.) via `GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379`

2. **External block subscription** (HTTP + WebSocket over RPC) — Followers receive blocks from the hub via the lease-based subscription system:
   - Follower registers via `POST /rpc/subscribe` on the hub's RPC endpoint
   - Hub pushes blocks via WebSocket on `/rpc/subscribe/ws`
   - Follower sends periodic heartbeats to maintain the lease
   - Falls back to periodic pull sync (`POST /rpc/sync`) if subscription fails

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

`GET /rpc/get_head`
Get the latest block header

`POST /rpc/send_tx`
Submit a new transaction

`GET /rpc/get_balance/{address}`
Get account balance

`GET /rpc/get_block/{height}`
Get block by height

### WebSocket Subscriptions

- `/rpc/subscribe/ws` - Lease-based block push to subscribed followers (hub → follower)
- `/rpc/blocks` - Real-time block stream (public)
- `/rpc/transactions` - Transaction pool updates (public)

## Configuration

The node can be configured via environment variables or configuration file.

### Key Settings

```bash
# Database
DATABASE_URL=sqlite:///blockchain.db

# Network
RPC_HOST=0.0.0.0
RPC_PORT=8202
WS_PORT=9081

# Consensus
CONSENSUS_MODE=poa
VALIDATOR_ADDRESS=0x...
BLOCK_TIME=1s

# Observability
METRICS_PORT=9090
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

Available at `http://localhost:9090/metrics`

Key metrics:

- `blockchain_blocks_total` - Total blocks produced
- `blockchain_transactions_total` - Total transactions processed
- `blockchain_consensus_rounds` - Consensus rounds completed
- `blockchain_network_peers` - Active peer connections

### Health Checks

```bash
# Node status
curl http://localhost:8202/health

# Sync status
curl http://localhost:8202/sync_status
```

## Troubleshooting

### Common Issues

1. **Node not syncing**
   - Check peer connections: `curl /rpc/peers`
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
git clone https://github.com/aitbc/blockchain
cd blockchain
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
