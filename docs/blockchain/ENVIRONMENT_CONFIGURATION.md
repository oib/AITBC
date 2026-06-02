# AITBC Blockchain Node Environment Configuration Guide

**Last Updated:** 2026-05-28

> **Important:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

Complete reference for configuring `node.env` and `blockchain.env` files for AITBC blockchain nodes.

## Overview

AITBC uses two environment configuration files:

- **`/etc/aitbc/node.env`** - Node-specific settings (unique per node)
- **`/etc/aitbc/blockchain.env`** - Shared blockchain settings (can be identical across nodes)

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

### P2P Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `p2p_bind_host` | Yes | `0.0.0.0` | Interface to bind P2P service |
| `p2p_bind_port` | Yes | `7070` | P2P service port |
| `p2p_peers` | No | - | Comma-separated list of peer nodes (e.g., `aitbc1:7070,aitbc2:7070`) |
| `trusted_proposers` | No | - | For follower nodes - trusted proposer addresses |

### Node-Specific Overrides

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_HOST` | No | `0.0.0.0` | Override default host binding |
| `NODE_PORT` | No | `7070` | Override default port |

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

# P2P Configuration
p2p_node_id=node-7af14c549bab473d9deb4ca8ab4bdcde
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
proposer_id=ait1ytkh0cn8v2a4zjwzyav6854832myf9j7unsse8yntmuwzst4qhtqe9hqdw

# P2P Peers (connect to hub and other nodes)
p2p_peers=node1:7070,node2:7070

# Trusted Propers (for follower nodes)
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
| `SYNC_SOURCE_PORT` | No | `8006` | Port to sync from |
| `SYNC_LEADER_HOST` | No | - | Leader node host |
| `SYNC_IMPORT_HOST` | No | `localhost` | Import service host |
| `SYNC_IMPORT_PORT` | No | `8006` | Import service port |
| `SYNC_CHAIN_ID` | No | - | Chain ID to sync |
| `auto_sync_enabled` | No | `false` | Enable automatic sync on gap detection |

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
| `rpc_bind_port` | No | `8006` | RPC service port |
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
SYNC_SOURCE_PORT=8006
SYNC_LEADER_HOST=node1
SYNC_IMPORT_HOST=localhost
SYNC_IMPORT_PORT=8006
SYNC_CHAIN_ID=ait-testnet

# Blockchain Configuration
CHAIN_ID=ait-mainnet
BLOCK_TIME=5
NETWORK_ID=1337
CONSENSUS=proof_of_authority

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8006

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
default_peer_rpc_url=http://node1:8006
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
SYNC_SOURCE_PORT=8006
SYNC_LEADER_HOST=aitbc
SYNC_IMPORT_HOST=localhost
SYNC_IMPORT_PORT=8006
SYNC_CHAIN_ID=ait-testnet

# Blockchain Configuration
CHAIN_ID=ait-testnet
BLOCK_TIME=5
NETWORK_ID=1337
CONSENSUS=proof_of_authority

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8006

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
default_peer_rpc_url=http://aitbc:8006
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
ENFORCE_STATE_ROOT_VALIDATION=true
WORKERS=1

# Monitoring Configuration
MONITORING_PORT=9000
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

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
- `p2p_peers=hub:7070,other:7070`
- `auto_sync_enabled=true`
- `default_peer_rpc_url=http://hub:8006`
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
default_peer_rpc_url=http://hub-node:8006
```

### Issue: Fork detection errors

**Cause:** Multiple nodes with same `proposer_id` producing blocks simultaneously

**Solution:**
```bash
# On follower nodes
enable_block_production=false
```

### Issue: P2P service fails to start

**Cause:** Missing `p2p_bind_host` or `p2p_bind_port`

**Solution:**
```bash
# Add to node.env
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
- [ ] `p2p_bind_host` and `p2p_bind_port` are set
- [ ] `supported_chains` matches the network chain ID
- [ ] `island_id` is set correctly
- [ ] `auto_sync_enabled` is `true` for follower nodes
- [ ] `enable_block_production` is `false` for follower nodes
- [ ] `default_peer_rpc_url` points to hub node for followers
- [ ] Redis URLs are correct and accessible

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
