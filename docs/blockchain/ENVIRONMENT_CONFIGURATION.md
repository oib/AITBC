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
| `NODE_ID` | Yes | - | Unique identifier for this node (e.g., `aitbc`, `aitbc1`, `aitbc2`) |
| `p2p_node_id` | Yes | - | Unique P2P network identity. Format: `node-<uuid>` |
| `proposer_id` | Yes* | - | PoA proposer address. Format: `ait1<public-key>` |
| `enable_block_production` | No | `true` | Set `false` on follower nodes to prevent forks |
| `block_production_chains` | No | - | Comma-separated list of chains to produce blocks for |

*Required if `enable_block_production=true`

### P2P / Gossip Relay Configuration

> **Note:** The P2P gossip relay (`aitbc-blockchain-p2p`, port 7070) is a **hub-only** service for internal gossip broadcasting. Followers do not need to configure these settings or run the p2p service. Followers receive blocks via the [lease-based subscription system](#subscription-configuration) over the hub's RPC endpoint.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `p2p_bind_host` | Hub only | `0.0.0.0` | Interface to bind gossip relay service |
| `p2p_bind_port` | Hub only | `7070` | Gossip relay service port (hub-only) |
| `p2p_peers` | No | - | Comma-separated list of peer nodes (legacy, not used by subscription system) |
| `trusted_proposers` | No | - | For follower nodes - trusted proposer addresses |

### Node-Specific Overrides

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_HOST` | No | `0.0.0.0` | Override default host binding |
| `NODE_PORT` | No | `7070` | Override default port (hub gossip relay) |

### Example node.env (Hub Node)

```bash
# AITBC Node-Specific Environment Configuration
# This file contains variables unique to this node

# Node Identity
NODE_ID=aitbc

# P2P Configuration
p2p_node_id=node-ad4e9170aea04a349469d17758de7b27
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
proposer_id=ait1ytkh0cn8v2a4zjwzyav6854832myf9j7unsse8yntmuwzst4qhtqe9hqdw

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
NODE_ID=aitbc2

# P2P Configuration (not needed for followers — subscription system uses RPC)
p2p_node_id=node-7af14c549bab473d9deb4ca8ab4bdcde
proposer_id=ait1ytkh0cn8v2a4zjwzyav6854832myf9j7unsse8yntmuwzst4qhtqe9hqdw

# Trusted Proposers (for follower nodes)
trusted_proposers=

# Block Production Configuration
block_production_chains=
enable_block_production=false
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
| `API_KEY_HASH_SECRET` | Yes | - | Secret for API key hashing |
| `SECRET_KEY` | Yes | - | Application secret key |
| `BLOCKCHAIN_API_KEY` | Yes | - | API key for blockchain access |
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
| `gossip_backend` | Yes | `broadcast` | Gossip backend type |
| `gossip_broadcast_url` | Yes | - | Redis URL for gossip broadcast |
| `SYNC_REDIS_URL` | Yes | - | Redis URL for chain sync |

### Sync Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNC_SOURCE_HOST` | No | - | Host to sync from |
| `SYNC_SOURCE_PORT` | No | `8202` | Port to sync from |
| `SYNC_LEADER_HOST` | No | - | Leader node host |
| `SYNC_IMPORT_HOST` | No | `localhost` | Import service host |
| `SYNC_IMPORT_PORT` | No | `8202` | Import service port |
| `SYNC_CHAIN_ID` | No | - | Chain ID to sync |
| `auto_sync_enabled` | No | `false` | Enable automatic sync on gap detection |

### Subscription Configuration

Followers receive blocks from the hub via a **lease-based subscription system** over the hub's RPC endpoint. This replaces the legacy P2P gossip approach.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `subscription_enabled` | No | `true` | Enable lease-based block subscription from hub (followers) |
| `subscription_transport` | No | `websocket` | Transport for block push: `websocket`, `http`, or `redis` |
| `default_peer_rpc_url` | Followers | - | Hub RPC URL (e.g., `http://hub.aitbc.bubuit.net/rpc`) |

**How it works:**
1. Follower registers via `POST <default_peer_rpc_url>/subscribe` to obtain a lease
2. Follower opens WebSocket to `ws://<hub>/rpc/subscribe/ws` for real-time block push
3. Follower sends periodic `POST <default_peer_rpc_url>/heartbeat` to extend the lease
4. If the follower falls behind, it uses bulk sync via `POST /rpc/sync` to catch up

**Example (follower blockchain.env):**
```bash
default_peer_rpc_url=http://hub.aitbc.bubuit.net/rpc
subscription_enabled=true
subscription_transport=websocket
```

### Blockchain Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CHAIN_ID` | Yes | `ait-mainnet` | Primary chain ID |
| `supported_chains` | Yes | `ait-mainnet` | Comma-separated list of supported chains |
| `island_id` | Yes | - | Island identifier for this node |
| `BLOCK_TIME` | No | `5` | Target block time in seconds |
| `NETWORK_ID` | No | `1337` | Network identifier |
| `CONSENSUS` | No | `proof_of_authority` | Consensus mechanism |

### RPC Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `rpc_bind_host` | No | `0.0.0.0` | RPC service bind host |
| `rpc_bind_port` | No | `8202` | RPC service port |
| `default_peer_rpc_url` | No | - | Default peer RPC URL for sync |

### Service Ports

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `api_host` | No | `0.0.0.0` | API service host |
| `api_port` | No | `8203` | API service port |
| `wallet_host` | No | `0.0.0.0` | Wallet service host |
| `wallet_port` | No | `8015` | Wallet service port |
| `exchange_host` | No | `0.0.0.0` | Exchange service host |
| `exchange_port` | No | `8001` | Exchange service port |

### Feature Flags

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENFORCE_STATE_ROOT_VALIDATION` | No | `false` | Enable state root validation |
| `WORKERS` | No | `1` | Number of worker processes |

### Monitoring

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONITORING_PORT` | No | `9000` | Monitoring service port |
| `PROMETHEUS_PORT` | No | `9090` | Prometheus port |
| `GRAFANA_PORT` | No | `3000` | Grafana port |

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

# Sync Configuration (for ait-testnet following)
SYNC_SOURCE_HOST=node1
SYNC_SOURCE_PORT=8202
SYNC_LEADER_HOST=node1
SYNC_IMPORT_HOST=localhost
SYNC_IMPORT_PORT=8202
SYNC_CHAIN_ID=ait-testnet

# Blockchain Configuration
CHAIN_ID=ait-mainnet
BLOCK_TIME=5
NETWORK_ID=1337
CONSENSUS=proof_of_authority

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8202

# API Configuration
api_host=0.0.0.0
api_port=8203

# Wallet Configuration
wallet_host=0.0.0.0
wallet_port=8015

# Exchange Configuration
exchange_host=0.0.0.0
exchange_port=8001

# Services Configuration
auto_sync_enabled=true
island_id=ait-mainnet-island
supported_chains=ait-mainnet,ait-testnet
db_encryption_enabled=false
default_peer_rpc_url=http://node1:8202
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
ENFORCE_STATE_ROOT_VALIDATION=true
WORKERS=1

# Monitoring Configuration
MONITORING_PORT=9000
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
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
SYNC_SOURCE_HOST=aitbc
SYNC_SOURCE_PORT=8202
SYNC_LEADER_HOST=aitbc
SYNC_IMPORT_HOST=localhost
SYNC_IMPORT_PORT=8202
SYNC_CHAIN_ID=ait-testnet

# Blockchain Configuration
CHAIN_ID=ait-testnet
BLOCK_TIME=5
NETWORK_ID=1337
CONSENSUS=proof_of_authority

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8202

# API Configuration
api_host=0.0.0.0
api_port=8203

# Wallet Configuration
wallet_host=0.0.0.0
wallet_port=8015

# Exchange Configuration
exchange_host=0.0.0.0
exchange_port=8001

# Services Configuration
auto_sync_enabled=true
island_id=ait-testnet-island
supported_chains=ait-testnet
db_encryption_enabled=false
default_peer_rpc_url=http://aitbc:8202
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
ENFORCE_STATE_ROOT_VALIDATION=true
WORKERS=1

# Monitoring Configuration
MONITORING_PORT=9000
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

---

## blockchain-secrets.env Reference

**Location:** `/etc/aitbc/blockchain-secrets.env`
**Purpose:** Shared cluster authentication secrets. Contains API keys that must match across all nodes in the same island for authentication.
**Security Level:** Private - Contains sensitive authentication secrets. File permissions should be `600`.

**Source:** Downloaded from hub's public endpoint for open islands: `https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env`

### Authentication Secrets

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COORDINATOR_API_KEY` | Yes | - | API key for Agent Coordinator authentication |
| `SECRET_KEY` | Yes | - | JWT signing and message authentication secret |

### Example blockchain-secrets.env

```bash
# Shared cluster secrets for the ait-hub.aitbc.bubuit.net open island
COORDINATOR_API_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8de5c
SECRET_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8de5c
```

### Services That Load This File

- `aitbc-wallet.service` - For wallet daemon authentication
- `aitbc-hermes.service` - For Hermes service authentication
- `aitbc-blockchain-rpc.service` - For authenticated RPC endpoints (if needed)

### Security Notes

- **File permissions:** Should be `600` (owner read/write only)
- **Distribution:** For open islands, these keys are public (downloadable from hub)
- **Private islands:** Should use unique, non-public keys generated during setup
- **Consistency:** All nodes in the same island must use the same keys

### Setup Instructions

```bash
# Download from hub (for open islands)
curl -o /etc/aitbc/blockchain-secrets.env https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env

# For private islands, generate unique keys
# and distribute securely to all nodes
```

---

## Environment File Loading Order

Systemd services load environment files in the order specified in the `[Service]` section. Later files can override earlier ones.

**Example (aitbc-wallet.service):**
```ini
EnvironmentFile=/etc/aitbc/blockchain.env
EnvironmentFile=/etc/aitbc/blockchain-secrets.env
EnvironmentFile=/etc/aitbc/node.env
```

**Loading order:**
1. `blockchain.env` - Base blockchain configuration
2. `blockchain-secrets.env` - Authentication secrets (may override blockchain.env if duplicates exist)
3. `node.env` - Node-specific settings (highest priority)

---

## Service Dependencies

### Blockchain Node Services
- **aitbc-blockchain-node.service:** Loads `blockchain.env`, `node.env`
- **aitbc-blockchain-rpc.service:** Loads `blockchain.env`, `blockchain-secrets.env`, `node.env`

### Agent Services
- **aitbc-hermes.service:** Loads `blockchain.env`, `node.env`
- **aitbc-agent-coordinator.service:** Loads `node.env`
- **aitbc-agent-daemon.service:** Loads `node.env`

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

**Example:** aitbc for ait-mainnet, aitbc1 for ait-testnet

### Follower Node

**Characteristics:**
- `enable_block_production=false`
- `block_production_chains=` (empty)
- `subscription_enabled=true`
- `default_peer_rpc_url=http://hub.aitbc.bubuit.net/rpc`
- `auto_sync_enabled=true`
- Does **not** run `aitbc-blockchain-p2p` (hub-only service)
- Receives blocks via lease-based subscription over RPC (WebSocket push)
- Syncs genesis from hub

**Example:** gitea-runner following both chains

---

## Common Issues and Solutions

### Issue: "Gap detected" errors

**Cause:** Node is receiving blocks but missing intermediate blocks

**Solution:**
```bash
# Enable auto-sync
auto_sync_enabled=true
default_peer_rpc_url=http://hub-node:8202
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
p2p_bind_port=7070
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

# Ensure file exists
curl -o /etc/aitbc/blockchain-secrets.env https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env
```

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
- [ ] `default_peer_rpc_url` points to hub node RPC URL for followers
- [ ] `subscription_enabled` is `true` for follower nodes
- [ ] Redis URLs are correct and accessible
- [ ] `blockchain-secrets.env` exists and has correct permissions (600)
- [ ] `COORDINATOR_API_KEY` and `SECRET_KEY` match hub's shared secrets
- [ ] All three environment files exist at `/etc/aitbc/`

---

## Related Documentation

- [Adding Third Node Guide](./adding_gitea_runner_as_third_node.md) - Real-world setup example
- [Node Deployment Guide](../infrastructure/NODE_AITBC.md) - Infrastructure setup
- [Blockchain Node Schema](./node/SCHEMA.md) - Database schema reference
- [Multi-Node Setup Core](../../.windsurf/workflows/multi-node-blockchain-setup-core.md) - Workflow guide

---

**Version:** 1.0
**Last Updated:** 2026-05-19
**Status:** Complete
