# AITBC Blockchain Node Environment Configuration Guide

**Last Updated:** 2026-06-03

> **Important:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

Complete reference for configuring `node.env`, `blockchain.env`, and `blockchain-secrets.env` files for AITBC blockchain nodes.

## Overview

AITBC uses three environment configuration files:

- **`/etc/aitbc/node.env`** - Node-specific settings (unique per node)
- **`/etc/aitbc/blockchain.env`** - Shared blockchain settings (can be identical across nodes)
- **`/etc/aitbc/blockchain-secrets.env`** - Shared cluster authentication secrets (must match across nodes)

## node.env Reference

**Location:** `/etc/aitbc/node.env`
**Purpose:** Contains variables unique to each node. Must be customized for every node in the network.

### Node Identity

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_ID` | Yes | - | Unique identifier for this node (e.g., `hub`, `node1`, `node2`) |
| `p2p_node_id` | Yes | - | Unique P2P network identity. Format: `node-<uuid>` |
| `proposer_id` | Yes* | - | PoA proposer address. Format: `0x<address>` |
| `enable_block_production` | No | `true` | Set `false` on follower nodes to prevent forks |
| `block_production_chains` | No | - | Comma-separated list of chains to produce blocks for |

*Required if `enable_block_production=true`

### P2P / Gossip Relay Configuration

> **Note:** The P2P gossip relay (`aitbc-blockchain-p2p`, port 7070) is a **hub-only** service for internal gossip broadcasting. Followers do not need to configure these settings or run the p2p service. Followers receive blocks via the [lease-based subscription system](#subscription-configuration) over the hub's RPC endpoint.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `p2p_bind_host` | Hub only | `0.0.0.0` | Interface to bind gossip relay service |
| `p2p_bind_port` | No | `8200` | Node P2P listener port. Note: the hub's gossip-relay unit (`aitbc-blockchain-p2p`) binds **7070** via its wrapper's hardcoded `--port 7070`, not this variable |
| `p2p_peers` | No | - | Comma-separated list of peer nodes (legacy, not used by subscription system) |
| `trusted_proposers` | No | - | For follower nodes - trusted proposer addresses |

### Node-Specific Overrides

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_HOST` | ~~No~~ — **not read anywhere** | `0.0.0.0` | fictional var; nothing reads it |
| `NODE_PORT` | ~~No~~ — **not read anywhere** | `7070` | fictional var; the hub gossip-relay port comes from the p2p wrapper's hardcoded `--port 7070`, not env |

### Example node.env (Hub Node)

```bash
# AITBC Node-Specific Environment Configuration
# This file contains variables unique to this node

# Node Identity
NODE_ID=hub

# P2P Configuration
p2p_node_id=node-ad4e9170aea04a349469d17758de7b27
p2p_bind_host=0.0.0.0
p2p_bind_port=8200   # default is 8200 — 7070 is the hub-only gossip relay (wrapper flag); setting it here collides with aitbc-blockchain-p2p on the same host
proposer_id=0x88A13a03119cfaefe99Bd4657b5F4DD4A2199AD7

# P2P Peers (empty for hub node)
p2p_peers=

# Trusted Propers (for follower nodes)
trusted_proposers=

# Block Production Configuration
block_production_chains=ait-mainnet
enable_block_production=true
```

### Example node.env (Follower Node)

```bash
# AITBC Node-Specific Environment Configuration
# This file contains variables unique to this node

# Node Identity
NODE_ID=node2

# P2P identity (kept for uniqueness, not used for follower gossip)
p2p_node_id=node-7af14c549bab473d9deb4ca8ab4bdcde

# Followers must not set proposer_id unless they also hold the matching proposer
# key. SyncManager only enables gossip when both proposer_id and proposer_key are
# present; a stale proposer_id here causes "PROPOSER_ID/PROPOSER_KEY not set"
# warnings and can make the node try to authenticate as a validator.
# proposer_id=0x...

# Do not set stale mesh peer URLs on followers. Block push comes from the hub
# websocket subscription, not a mesh.
# GOSSIP_MESH_PEER_URLS=

# Trusted Proposers (for follower nodes)
trusted_proposers=

# Block Production Configuration
block_production_chains=
enable_block_production=false

# Keep the gossip backend explicit. Followers receive blocks via the hub
# websocket subscription, not the validator gossip broker.
GOSSIP_BACKEND=websocket
```

---

## blockchain.env Reference

**Location:** `/etc/aitbc/blockchain.env`
**Purpose:** Contains shared blockchain settings. Can be identical across all nodes or customized per node.

### Environment & Logging

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_ENV` | No | `production` | Environment mode (`development`, `production`) |
| `DEBUG` | No | `false` | Enable debug logging |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEY_HASH_SECRET` | Yes | - | Secret for API key hashing — written to the **coordinator-api** env (`aitbc-coordinator-api.env`), not `blockchain.env`; setup.sh strips it from blockchain.env |
| `SECRET_KEY` | Yes | - | Application secret key |
| `BLOCKCHAIN_API_KEY` | ~~Yes~~ — **not read anywhere** | - | fictional var (0 code hits); RPC auth uses `RPC_API_KEYS`/api-keys storage |
| `COORDINATOR_API_KEY` | Yes | - | API key for coordinator access |
| `JWT_SECRET` | Yes | - | JWT signing secret |

### Database Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | - | PostgreSQL URL (if using PostgreSQL) |
| `db_encryption_enabled` | No | `false` | Enable SQLCipher encryption (ait-mainnet only) |
| `MEMPOOL_DB_URL` | No | - | PostgreSQL URL for mempool backend |

### Redis & Gossip

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | - | Redis connection URL |
| `gossip_backend` | No | `memory` (code default in `config.py:346`) | Gossip backend type |
| `gossip_broadcast_url` | Yes | - | Redis URL for gossip broadcast |
| `SYNC_REDIS_URL` | ~~Yes~~ — **not read anywhere** | - | fictional var; chain sync uses subscription/heartbeat + bulk-pull RPC |

### Sync Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `sync_manager_enabled` | No | `true` | Master kill switch; when `false` no SyncManager is started |
| `auto_sync_enabled` | No | `true` | Enable automatic bulk sync when a gap is detected |
| `auto_sync_threshold` | No | `10` | Block-gap size that triggers a bulk sync |

> **Removed:** `SYNC_SOURCE_HOST`, `SYNC_SOURCE_PORT`, `SYNC_LEADER_HOST`,
> `SYNC_IMPORT_HOST`, `SYNC_IMPORT_PORT`, and `SYNC_CHAIN_ID` are no longer read
> by any service — they remain only in legacy `blockchain.env` files. Sync source
> selection is done through the subscription settings below
> (`default_peer_rpc_url`) or `CHAIN_SYNC_SOURCES` for multi-chain hubs.

### Subscription Configuration

Followers receive blocks from the hub via a **lease-based subscription system** over the hub's RPC endpoint. This replaces the legacy P2P gossip approach.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `subscription_enabled` | No | `true` | Enable lease-based block subscription from hub (followers) |
| `subscription_transport` | No | `websocket` | Transport for block push: `websocket`, `http`, or `redis` |
| `default_peer_rpc_url` | Followers | - | Hub **base** URL (e.g., `https://hub.example.net`) |

**How it works:**

1. Follower registers via `POST <default_peer_rpc_url>/rpc/subscribe` (`X-API-Key` peer key) to obtain a lease
2. Follower opens WebSocket to `wss://<hub>/rpc/subscribe/ws` for real-time block push
3. Follower sends periodic `POST <default_peer_rpc_url>/rpc/heartbeat` to extend the lease
4. If the follower falls behind, catch-up is **automatic pull-sync** — the sync manager bulk-pulls from `default_peer_rpc_url` whenever no lease is held or a gap is detected; there is no `POST /rpc/sync` endpoint. A deliberate operator reorg onto a peer's chain uses `POST /rpc/force-sync`, which requires an **admin-signed** request body (`admin_address` + `admin_signature`), not an API key.

**Example (follower node.env):**

```bash
NODE_ID=your-node-id
BLOCKCHAIN_MODE=follower
default_peer_rpc_url=https://hub.example.net
subscription_enabled=true
subscription_transport=websocket
```

The `default_peer_rpc_url` must be a base URL with no `/rpc` suffix.

### Blockchain Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CHAIN_ID` | Yes | - | Primary chain ID (e.g. `ait-localnet`) |
| `supported_chains` | No | `chain_id` | Comma-separated list of supported chains |
| `island_id` | No | `DEFAULT_ISLAND_ID` | Island identifier for this node |
| `block_time_seconds` | No | `10` | Target block time in seconds |

> **Removed:** `BLOCK_TIME` (use `block_time_seconds`), `NETWORK_ID`, and
> `CONSENSUS` are no longer read by the node.

### RPC Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `rpc_bind_host` | No | `0.0.0.0` | RPC service bind host |
| `rpc_bind_port` | No | `8202` | RPC service port |
| `default_peer_rpc_url` | No | - | Default peer RPC URL for sync |

### Service Ports

Per-service ports are configured by each service's own `*_BIND_HOST` / `*_BIND_PORT`
variables (e.g. `AGENT_COORDINATOR_BIND_PORT`) — see
[Service Ports Reference](../reference/SERVICE_PORTS.md). The legacy
`api_host`/`api_port`, `wallet_host`/`wallet_port`, and
`exchange_host`/`exchange_port` variables are no longer read.

### Feature Flags

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNC_STATE_ROOT_VALIDATION_ENABLED` | No | `true` | Validate state roots on sync/bulk import (`enforce_state_root_validation` was removed — it was never read) |
| `WORKERS` | No | `1` | Number of worker processes |

### Monitoring

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AITBC_NODE_METRICS_PORT` | No | `9009` | Port where the blockchain node main process exposes `/metrics` |

### Example blockchain.env (Hub Node - ait-mainnet)

```bash
# AITBC Environment Configuration
# This file contains shared environment variables

# Environment
NODE_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# API Key Security
API_KEY_HASH_SECRET=f55e8a64e2cc3b44c50a43f25c7f985a6251ad4d0ceb469852d297721def28d2
SECRET_KEY=production-secret-key-change-me-in-production
BLOCKCHAIN_API_KEY=production-api-key-change-me
COORDINATOR_API_KEY=admin_prod_key_use_real_value
JWT_SECRET=production-jwt-secret-32-chars-long-change-me

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
gossip_backend=broadcast
gossip_broadcast_url=redis://redis.example.com:6379
SYNC_REDIS_URL=redis://redis.example.com:6379

# Sync Configuration (bulk-sync gap recovery)
sync_manager_enabled=true
auto_sync_enabled=true
auto_sync_threshold=10

# Blockchain Configuration
CHAIN_ID=ait-mainnet
block_time_seconds=10

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8202

# Services Configuration
island_id=ait-mainnet-island
supported_chains=ait-mainnet,ait-testnet
db_encryption_enabled=false
default_peer_rpc_url=https://node1.example.net
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
SYNC_STATE_ROOT_VALIDATION_ENABLED=true
WORKERS=1

# Monitoring Configuration
AITBC_NODE_METRICS_PORT=9009
```

### Example blockchain.env (Hub Node - ait-testnet)

```bash
# AITBC Environment Configuration

# Environment
NODE_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# API Key Security
API_KEY_HASH_SECRET=f55e8a64e2cc3b44c50a43f25c7f985a6251ad4d0ceb469852d297721def28d2
SECRET_KEY=production-secret-key-change-me-in-production
BLOCKCHAIN_API_KEY=production-api-key-change-me
COORDINATOR_API_KEY=admin_prod_key_use_real_value
JWT_SECRET=production-jwt-secret-32-chars-long-change-me

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
gossip_backend=broadcast
gossip_broadcast_url=redis://redis.example.com:6379
SYNC_REDIS_URL=redis://redis.example.com:6379

# Sync Configuration (following ait-mainnet)
sync_manager_enabled=true
auto_sync_enabled=true
auto_sync_threshold=10
default_peer_rpc_url=https://hub.example.net
subscription_enabled=true
subscription_transport=websocket

# Blockchain Configuration
CHAIN_ID=ait-testnet
block_time_seconds=10

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8202

# Services Configuration
island_id=ait-testnet-island
supported_chains=ait-testnet
db_encryption_enabled=false
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
SYNC_STATE_ROOT_VALIDATION_ENABLED=true
WORKERS=1

# Monitoring Configuration
AITBC_NODE_METRICS_PORT=9009
```

---

## blockchain-secrets.env Reference

**Location:** `/etc/aitbc/blockchain-secrets.env`
**Purpose:** Shared cluster authentication secrets. Contains API keys that must match across all nodes in the same island for authentication.
**Security Level:** Private - Contains sensitive authentication secrets. File permissions should be `600`.

**Source:** Generated per island and distributed out of band. **Never published over HTTP.**

Until v0.23 this file was served unauthenticated from `https://hub.example.net/agent/blockchain-secrets.env`, and this page printed the hub's live values as an "example". Both are fixed (V23-58); if you deployed before that, rotate — see [Rotating these secrets](#rotating-these-secrets).

### Authentication Secrets

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COORDINATOR_API_KEY` | Yes | - | API key for Agent Coordinator authentication. Also the fallback credential for `X-Api-Key` miner auth (`aitbc/auth/dependencies.py`) — presenting it authenticates as role `miner`. |
| `SECRET_KEY` | Yes | - | Message authentication secret. Accepted **interchangeably with** `COORDINATOR_API_KEY` by the agent-coordinator coin-request and websocket routers, so the two are not independent: either value alone opens both. |
| `API_KEY_HASH_SECRET` | Yes | - | HMAC secret for API-key hash derivation. |
| `JWT_SECRET` | Yes | - | Token signing secret for JWT-secured coordinator endpoints. |

### Redis / Gossip Secrets

Cluster-wide backend secrets also live in this file:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | If using Redis | - | Full `redis://` or `rediss://` URL including credentials. |
| `GOSSIP_BROADCAST_URL` | If using Redis gossip | - | `redis://` URL used by the hub's gossip broker. |
| `SYNC_REDIS_URL` | If using Redis sync | - | `redis://` URL used by the sync backend. |

### Example blockchain-secrets.env

Generate the values; do not copy them from anywhere, including this page.

```bash
# Shared cluster secrets for one island -- placeholders, not usable values
COORDINATOR_API_KEY=<64 hex chars from `openssl rand -hex 32`>
SECRET_KEY=<a different 64 hex chars from a second `openssl rand -hex 32`>
API_KEY_HASH_SECRET=<64 hex chars from a third `openssl rand -hex 32`>
JWT_SECRET=<64 hex chars from a fourth `openssl rand -hex 32`>
# Redis backend URL with password (only for hub/validator deployments)
# REDIS_URL=redis://:<password>@localhost:6379/0
```

Use two different values. Because the coordinator routers accept either one, reusing a single value for both means a leak of one is a leak of the other, with nothing left to fall back on during rotation.

### Services That Load This File

- `aitbc-wallet.service` - For wallet daemon authentication
- `aitbc-agent-coordinator.service` - For Agent Coordinator authentication
- `aitbc-blockchain-rpc.service` - For authenticated RPC endpoints (if needed)

### Security Notes

- **File permissions:** Should be `600` (owner read/write only)
- **Distribution:** Out of band only. These are credentials, not configuration — "open island" describes who may *join* the chain, not who may *authenticate* to its services.
- **Consistency:** All nodes in the same island must use the same keys
- **Not needed to follow the chain as a plain follower:** a follower only needs `blockchain.env` and `genesis.json`. The `aitbc-blockchain-node` service will load `blockchain-secrets.env` if it exists, but it is not required and must not be distributed to new followers. Install it only on hosts running `aitbc-wallet`, `aitbc-agent-coordinator`, `aitbc-blockchain-rpc` (hub/validator), or `aitbc-blockchain-event-bridge`.

### Setup Instructions

```bash
# Generate one island's secrets, on the hub, once
umask 077
{ echo "COORDINATOR_API_KEY=$(openssl rand -hex 32)"
  echo "SECRET_KEY=$(openssl rand -hex 32)"; } > /etc/aitbc/blockchain-secrets.env
```

Copy the file to joining nodes over an authenticated channel — `scp`, your configuration
manager, or a secrets store. Do not put it behind a URL.

### Rotating these secrets

Rotate if the file was ever fetched over HTTP, or if you deployed a hub whose values came
from a published example.

---

## coordinator.env / Stale Miner Reaper Reference

**Location:** `/etc/aitbc/aitbc-coordinator-api.env` (unit `EnvironmentFile`) or `apps/coordinator-api/.env.example`
**Purpose:** Control the background reaper that marks miners with stale heartbeats as `OFFLINE`.

### Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COORDINATOR_STALE_MINER_REAPER_ENABLED` | `true` | Start the reaper at coordinator startup. Set to `false` to disable. |
| `COORDINATOR_STALE_MINER_REAPER_INTERVAL_SECONDS` | `60` | Seconds between sweeps. |
| `COORDINATOR_MINER_HEARTBEAT_CUTOFF_SECONDS` | `300` | A miner whose `last_heartbeat` is older than this is marked `OFFLINE` and its `inflight` count is reset. |

### Example

```bash
COORDINATOR_STALE_MINER_REAPER_ENABLED=true
COORDINATOR_STALE_MINER_REAPER_INTERVAL_SECONDS=60
COORDINATOR_MINER_HEARTBEAT_CUTOFF_SECONDS=300
```

```bash
# 1. On the hub: generate replacements (as above), keeping the old file for step 3
# 2. Distribute to every node running wallet / agent-coordinator / event-bridge
# 3. Restart those services together -- the old and new keys are not accepted
#    simultaneously, so nodes mid-rotation will 401 against each other
systemctl restart aitbc-agent-coordinator aitbc-wallet aitbc-blockchain-event-bridge
```

Rotation is the only remedy once a value has been served publicly. Removing the endpoint does not un-publish what was already fetched, cached, or indexed.

---

## Environment File Loading Order

Systemd services load environment files in the order specified in the `[Service]` section. Later files can override earlier ones.

**Example (aitbc-blockchain-rpc.service):**

```ini
EnvironmentFile=-/etc/aitbc/blockchain.env
EnvironmentFile=-/etc/aitbc/node.env
EnvironmentFile=-/etc/aitbc/%N.env
EnvironmentFile=-/etc/aitbc/blockchain-secrets.env
```

**Loading order:**

1. `blockchain.env` - Public base blockchain configuration
2. `node.env` - Node-specific settings
3. `%N.env` - Service-specific settings
4. `blockchain-secrets.env` - Cluster-wide secrets (highest priority, overrides public files)

---

## Service Dependencies

### Blockchain Node Services

- **aitbc-blockchain-node.service:** Loads `%N.env`, `blockchain.env`, `node.env`, `blockchain-secrets.env`
- **aitbc-blockchain-rpc.service:** Loads `blockchain.env`, `node.env`, `%N.env`, `blockchain-secrets.env`

### Agent Services

- **aitbc-agent-coordinator.service:** Loads `blockchain.env`, `node.env`, `blockchain-secrets.env`, `aitbc-agent-coordinator.env`
- **aitbc-hermes-agent.service:** Loads `hermes.env` (optional)

### Wallet Service

- **aitbc-wallet.service:** Loads `blockchain.env`, `blockchain-secrets.env`, `node.env`

### CLI

- **aitbc CLI:** Loads `blockchain.env` and `node.env` via `get_config()`

---

## Node Role Patterns

### Hub Node (Block Producer)

**Characteristics:**

- `enable_block_production=true`
- `block_production_chains=<chain-id>`
- `p2p_peers=` (empty or minimal)
- `auto_sync_enabled=false` (for its own chain)
- Creates genesis block locally

**Example:** `hub` for the primary chain, a designated hub for each additional chain

### Follower Node

**Characteristics:**

- `enable_block_production=false`
- `block_production_chains=` (empty)
- `subscription_enabled=true`
- `default_peer_rpc_url=https://hub.example.net` (base URL, no `/rpc` suffix)
- `auto_sync_enabled=true`
- Does **not** run `aitbc-blockchain-p2p` (hub-only service)
- Receives blocks via lease-based subscription over RPC (WebSocket push)
- Syncs genesis from hub

**Example:** a follower node following both chains

---

## Common Issues and Solutions

### Issue: "Gap detected" errors

**Cause:** Node is receiving blocks but missing intermediate blocks

**Solution:**

```bash
# Enable auto-sync
auto_sync_enabled=true
default_peer_rpc_url=https://hub.example.net
```

### Issue: Fork detection errors

**Cause:** Multiple nodes with same `proposer_id` producing blocks simultaneously

**Solution:**

```bash
# On follower nodes
enable_block_production=false
```

### Issue: P2P service fails to start

**Cause:** Missing `p2p_bind_host` or `p2p_bind_port` (hub nodes only)

**Solution:**

```bash
# Add to node.env (hub nodes only — followers don't need the p2p service)
p2p_bind_host=0.0.0.0
p2p_bind_port=8200   # default is 8200 — 7070 is the hub-only gossip relay (wrapper flag); setting it here collides with aitbc-blockchain-p2p on the same host
```

### Issue: Chain ID mismatch

**Cause:** `supported_chains` not set explicitly

**Solution:**

```bash
# Always set explicitly in blockchain.env
supported_chains=ait-mainnet,ait-testnet
```

### Issue: "COORDINATOR_API_KEY not set" error

**Cause:** `blockchain-secrets.env` not loaded or missing

**Solution:**

```bash
# Add to service file
EnvironmentFile=/etc/aitbc/blockchain-secrets.env

# Ensure file exists -- copy it from the hub over an authenticated channel
scp hub:/etc/aitbc/blockchain-secrets.env /etc/aitbc/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env
```

If this node only follows the chain, the real fix is the opposite one: drop the
`EnvironmentFile=/etc/aitbc/blockchain-secrets.env` line, because `blockchain-node` never
reads either variable.

### Issue: Service fails to start with "Failed to load environment files"

**Cause:** One of the specified `EnvironmentFile` paths doesn't exist

**Solution:**

```bash
# Ensure all referenced files exist
ls -la /etc/aitbc/blockchain.env /etc/aitbc/node.env /etc/aitbc/blockchain-secrets.env
```

### Issue: Database location mismatch

**Cause:** `DATABASE_URL` doesn't match actual database path

**Solution:**

```bash
# Use correct path (default is /var/lib/aitbc/data/<chain-id>/chain.db)
# Don't override DATABASE_URL unless using PostgreSQL
```

---

## Validation Checklist

Before starting services, verify:

- [ ] `NODE_ID` is unique across all nodes
- [ ] `p2p_node_id` is unique across all nodes
- [ ] `proposer_id` is unique for each proposer node
- [ ] `p2p_bind_host` and `p2p_bind_port` are set (hub nodes only)
- [ ] `supported_chains` matches the network chain ID
- [ ] `island_id` is set correctly
- [ ] `auto_sync_enabled` is `true` for follower nodes
- [ ] `enable_block_production` is `false` for follower nodes
- [ ] `default_peer_rpc_url` points to hub base URL for followers (no `/rpc` suffix)
- [ ] `subscription_enabled` is `true` for follower nodes
- [ ] Redis URLs are correct and accessible
- [ ] `blockchain-secrets.env` exists and has correct permissions (600)
- [ ] `COORDINATOR_API_KEY` and `SECRET_KEY` match hub's shared secrets
- [ ] All three environment files exist at `/etc/aitbc/`

---

## Related Documentation

- Adding Third Node Guide - Real-world setup example
- Node Deployment Guide - Infrastructure setup
- [Blockchain Node Schema](../apps/blockchain-node/SCHEMA.md) - Database schema reference
- Multi-Node Setup Core - Workflow guide

---

**Version:** 1.0
**Last Updated:** 2026-05-19
**Status:** Complete
