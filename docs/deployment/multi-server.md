# Multi-Server Deployment

This guide covers deploying AITBC across multiple servers for high availability and scalability.

## Architecture

```
                    Load Balancer
                         |
        +----------------+----------------+
        |                |                |
   Blockchain Node   Coordinator API   Market
        |                |                |
        +----------------+----------------+
                         |
                   PostgreSQL Cluster
                         |
                   Redis Cluster
```

## Node Types

1. **Blockchain Node**
   - Runs blockchain consensus
   - Maintains ledger
   - Requires public IP

2. **Coordinator API**
   - Job submission and management
   - Payment processing
   - API gateway

3. **Market Service**
   - GPU offer management
   - Matching engine
   - Price discovery

4. **Database Node**
   - PostgreSQL cluster
   - Redis cache
   - Data persistence

## Setup Steps

Every node runs the same installer — `scripts/deployment/setup.sh` — and gets
its service set from three node-profile variables written to
`/etc/aitbc/blockchain.env`:

- `BLOCKCHAIN_MODE` — `hub` (produces blocks) or `follower` (receives blocks)
- `MARKET_ROLE` — `customer` or `shop` (provides GPU)
- `HARDWARE_PROFILE` — `nogpu` or `gpu`

There is no etcd dependency and no per-service setup scripts; roles compose
into concrete units (see [setup-service-selection](../getting-started/setup-service-selection.md)).

### 1. Provision each node

```bash
# On every node
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/deployment/setup.sh        # interactive role prompts
# or non-interactively:
BLOCKCHAIN_MODE=follower MARKET_ROLE=customer ./scripts/deployment/setup.sh
```

### 2. Hub node

```bash
BLOCKCHAIN_MODE=hub MARKET_ROLE=customer ./scripts/deployment/setup.sh
```

Runs `aitbc-blockchain-p2p` (gossip relay), `aitbc-coordinator-api`,
`aitbc-api-gateway`, `aitbc-market`, `aitbc-exchange`, and the
agent-coordinator in addition to the base units.

### 3. Follower nodes

```bash
BLOCKCHAIN_MODE=follower MARKET_ROLE=customer ./scripts/deployment/setup.sh
```

Followers need outbound HTTPS to the hub only — they subscribe for blocks
via `POST /rpc/subscribe` (the node's `BLOCKCHAIN_RPC_API_KEY` must be listed
in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS`) and receive pushes on
`WS /rpc/subscribe/ws`. No inbound service ports are required.

### 4. Shop nodes (GPU providers)

```bash
BLOCKCHAIN_MODE=follower MARKET_ROLE=shop HARDWARE_PROFILE=gpu ./scripts/deployment/setup.sh
```

Adds `aitbc-gpu`, `aitbc-miner`, `aitbc-edge`, `aitbc-pool-hub`, and
`aitbc-market` on top of the follower set.

### 5. Datastores

Chain state is SQLite at `/var/lib/aitbc/data/<chain-id>/chain.db` — no
external database is required for the chain itself. PostgreSQL/Redis are used
only by specific services (e.g. `MEMPOOL_DB_URL` for the database mempool
backend, gossip/sync transports); provision them per service env file.

## See Also

- [Prerequisites](../getting-started/installation/prerequisites.md) - System requirements
- Cloud Deployment - Cloud-specific deployment
- [Configuration](configuration.md) - Environment configuration
