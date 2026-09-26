# Blockchain Node Configuration

**Last Updated:** 2026-09-16

Configure your blockchain node for optimal performance.

## Configuration Model

There is **no YAML config file** and no `~/.aitbc` directory. The node reads
`ChainSettings` (`apps/blockchain-node/src/aitbc_chain/config.py`) via
pydantic-settings — keys are matched **case-insensitively** from the process
environment.

Environment is layered through `EnvironmentFile=` directives in the systemd
units (`aitbc-blockchain-node.service`, `aitbc-blockchain-rpc.service`,
`aitbc-blockchain-p2p.service`):

| File | Scope |
|------|-------|
| `/etc/aitbc/blockchain.env` | Shared chain-wide settings (same on every node) |
| `/etc/aitbc/node.env` | Per-node settings (identity, role, hub URL) |
| `/etc/aitbc/<unit>.env` | Per-service secrets (e.g. `MEMPOOL_DB_URL`), created at deploy time |
| `/etc/aitbc/blockchain-secrets.env` | Shared cluster secrets (optional) |
| `/etc/aitbc/validator-secrets.env` | `VALIDATOR_KEYS` / `PROPOSER_KEY` — consensus signing, blockchain units only |

When run outside systemd, `ChainSettings` also auto-reads
`/etc/aitbc/blockchain.env` (override with `AITBC_CHAIN_ENV_FILE`; set it to an
empty string to load no env file — used by tests).

For the full field reference see
[ENVIRONMENT_CONFIGURATION.md](./ENVIRONMENT_CONFIGURATION.md). The most
commonly touched settings are summarized below.

## Chain Identity

```bash
# blockchain.env — shared
CHAIN_ID=ait-localnet
SUPPORTED_CHAINS=ait-localnet   # comma-separated; defaults to CHAIN_ID
ISLAND_ID=<uuid>                          # island identifier
```

## RPC and P2P

```bash
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202          # blockchain RPC API (also serves /metrics, /health)
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8200          # code default; the hub gossip relay binds 7070  # check-ports: ignore
```

> **Note:** The P2P gossip relay (`aitbc-blockchain-p2p`, port 7070) is a
> **hub-only** internal service. Followers do not run it and must not expose
> 7070 — they receive blocks over the hub's RPC/websocket subscription.
> For authoritative port configuration, see
> [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Block Production

```bash
ENABLE_BLOCK_PRODUCTION=true      # hub/proposer; false on followers
BLOCK_PRODUCTION_CHAINS=          # comma-separated; empty = all supported chains
PROPOSER_ID=0x<40-hex address>    # block-signing identity (must match keystore/proposer.json)
BLOCK_TIME_SECONDS=10             # block interval (default 10)
MAX_BLOCK_SIZE_BYTES=1000000
MAX_TXS_PER_BLOCK=500
BLOCK_GENERATION_MODE=hybrid      # always | mempool-only | hybrid
MAX_EMPTY_BLOCK_INTERVAL=60       # seconds before forcing an empty (heartbeat) block
```

> `PROPOSER_ID` is the identity a node signs blocks *as* and is also used by
> followers to filter gossip — a follower that copies the hub's `PROPOSER_ID`
> silently discards every block the hub gossips. See
> [blockchain-setup.md](../getting-started/node/blockchain-setup.md) for the
> full warning.

## Sync and Subscription

Followers pull blocks from the hub via the lease-based subscription system;
bulk catch-up is automatic.

```bash
# Follower (node.env)
BLOCKCHAIN_MODE=follower
DEFAULT_PEER_RPC_URL=https://hub.example.net   # hub base URL, no /rpc suffix
SUBSCRIPTION_ENABLED=true
SUBSCRIPTION_TRANSPORT=websocket                    # websocket | http | redis
BLOCKCHAIN_RPC_API_KEY=<key>                        # must be in the hub's
                                                  # BLOCKCHAIN_RPC_API_KEY_PEERS

# Sync tuning (blockchain.env)
SYNC_MANAGER_ENABLED=true       # master kill switch for the SyncManager
AUTO_SYNC_ENABLED=true          # automatic bulk sync on gap detection
AUTO_SYNC_THRESHOLD=10          # block gap that triggers a bulk sync
PERIODIC_SYNC_ENABLED=true      # periodic pull sync from default peer
PERIODIC_SYNC_INTERVAL=30
```

## Consensus

```bash
MULTI_VALIDATOR_CONSENSUS_ENABLED=false   # code default; live fleet sets true
VALIDATOR_SET='[{"address":"0x...","stake":"1000"}]'   # MV-PoA validator set (JSON)
VALIDATOR_KEYS='{"0x...":"<private key>"}'             # this node's keys — keep in validator-secrets.env
MULTI_VALIDATOR_MIN_ATTESTATIONS=2        # attestation quorum for MV-PoA blocks
PBFT_CONSENSUS_ENABLED=false              # PBFT is implemented but disabled on the live fleet
```

## Storage

Chain data is **SQLite**, one database per chain:

```
<AITBC_DATA_DIR>/data/<chain_id>/chain.db
```

`AITBC_DATA_DIR` sets the data root (defaults to the platform data dir; on the
live fleet `/var/lib/aitbc`). There is no `DATABASE_URL` for chain data —
`DATABASE_URL`/`MEMPOOL_DB_URL` only concern the mempool PostgreSQL backend.

```bash
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:<password>@localhost:5432/aitbc_mempool
```

## Gossip Backend

```bash
GOSSIP_BACKEND=memory                     # memory | broadcast | websocket | mesh
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
GOSSIP_WEBSOCKET_URL=                     # wss://host/rpc/gossip/ws for the websocket backend
GOSSIP_MESH_PEER_URLS=                    # comma-separated wss://<peer>/rpc/gossip/ws (validators only)
```

## Metrics

```bash
AITBC_NODE_METRICS_PORT=9009   # /metrics on the node process (RPC app also serves /metrics on 8202)
```

## Applying Changes

Settings are read at process start — there is no `config reload` command:

```bash
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
# hub additionally:
systemctl restart aitbc-blockchain-p2p
```

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Operations](./3_operations.md) — Day-to-day ops
- [Consensus](./4_consensus.md) — Consensus mechanism
