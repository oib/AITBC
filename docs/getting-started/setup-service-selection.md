# AITBC Setup - Service Selection

**Last Updated**: 2026-10-04
**Version**: 1.2

## Role-Based Service Selection

`setup.sh` automatically determines which services to enable and start based on the node's configuration. The service list is built by combining two independent axes:

- **Axis 1** (`BLOCKCHAIN_MODE`): hub services or follower services
- **Axis 2** (`MARKET_ROLE`): shop services (if `shop`) or nothing extra (if `customer`)

Both axes are evaluated independently and their service lists are merged. This means a `hub+shop` node gets both hub services AND shop services, not just one or the other.

### Service Combinations

| BLOCKCHAIN_MODE | MARKET_ROLE | Services | Count |
|----------------|-------------|----------|-------|
| hub | customer | base + hub | 17 |
| hub | shop | base + hub + shop | 23 |
| follower | customer | base + follower | 9 |
| follower | shop | base + follower + shop | 15 |

### Base Services (All Nodes)

Every node gets these services enabled and started:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-node` | 9009 | Core blockchain node (chain listener on 127.0.0.1:9009) |
| `aitbc-blockchain-rpc` | 8202 | Blockchain RPC API |
| `aitbc-wallet` | 8108 | Wallet daemon |
| `aitbc-recovery` | — | Boot recovery (relinks systemd + loads secrets) |
| `aitbc-monitoring` | 8002 | System monitoring (uvicorn health/metrics HTTP on 127.0.0.1:8002) |
| `aitbc-backup` | — | Daily backup service |
| `aitbc-trading` | 8104 | Trading service (inter-chain offer sync, gossip integration) |
| `aitbc-governance` | 8105 | Governance service (proposals, voting — all nodes participate) |

### Hub Services (BLOCKCHAIN_MODE=hub)

In addition to base services, hub nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-p2p` | 7070 | P2P network service |
| `aitbc-coordinator-api` | 8203 | Coordinator API (agent management, jobs) |
| `aitbc-api-gateway` | 8201 | Public API gateway (reverse proxy) |
| `aitbc-exchange` | 8106 | Exchange API |
| `aitbc-market` | — | Market service |
| `aitbc-bridge-monitor` | — | ETH↔AIT bridge monitor |
| `aitbc-blockchain-event-bridge` | 8205 | Blockchain event → service trigger bridge |
| `aitbc-agent-coordinator` | 8107 | Agent coordination backend (WebSocket PING/PONG, REQUEST_COINS) |
| `aitbc-blockchain-explorer` | 8100 | Blockchain explorer API |

### Follower Services (BLOCKCHAIN_MODE=follower)

In addition to base services, follower nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-explorer` | 8100 | Blockchain explorer API |

Block sync from the hub (lease-based subscription) is handled by `aitbc-blockchain-node` itself; the separate `aitbc-blockchain-sync` unit was removed in `5f98fad8b2`.

### Shop Services (MARKET_ROLE=shop)

In addition to the blockchain mode services, shop nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-gpu` | 8101 | GPU service API (advertises hardware to coordinator) |
| `aitbc-miner` | — | GPU compute provider client (registers with coordinator, sends heartbeats) |
| `aitbc-coordinator-api` | 8203 | Coordinator API (for local job coordination) † |
| `aitbc-edge` | 8111 | Edge compute API (GPU job dispatch, health reporting) |
| `aitbc-pool-hub` | 8210 | Mining pool hub (pool join/leave, miner registration) † |
| `aitbc-market` | 8102 | Market service (hardware/software bundle listings — needed by edge) |

† **Fleet divergence (verified 2026-10-04):** both †-marked units are still in
`setup.sh`'s shop enable list — a fresh `setup.sh` shop install still enables
them — but neither runs on the fleet shop node2: `aitbc-coordinator-api` was
removed in the Oct-1 teardown (the miner coordinates against the hub), and
`aitbc-pool-hub` is excluded from `link-systemd.sh`'s shop link set
(`EXTRA_SERVICES` opt-in) and runs on the hub only (127.0.0.1:8210).

Two more units run on the fleet shop without being in `setup.sh`'s shop list:

| Service | Port | How it got there |
|---------|------|------------------|
| `aitbc-api-gateway` | 8201 | not in `setup.sh`'s shop list at all; active+enabled on node2, listening on 0.0.0.0:8201 |
| `aitbc-hermes-agent` | 8270 | in `link-systemd.sh`'s shop link set but not `setup.sh`'s enable list; active+enabled on node2, 127.0.0.1:8270 |

> **Note:** Shop services are added regardless of `BLOCKCHAIN_MODE`. A `hub+shop` node gets hub services PLUS shop services. A `follower+shop` node gets follower services PLUS shop services.

### Customer Nodes (MARKET_ROLE=customer)

Customer nodes get **no additional services** beyond their blockchain mode services. They interact with the hub and shops via CLI and API calls.

### Services Not Auto-Enabled

The following services are never auto-enabled by `setup.sh`. They remain available as `linked` and can be enabled manually:

| Service | When to enable manually |
|---------|------------------------|
| `aitbc-ai` | AI approval mode enabled |
| `aitbc-learning` | Adaptive learning feature |
| `aitbc-modality-optimization` | Modality optimization feature |
| `aitbc-multimodal` | Multi-modal agent feature |
| `aitbc-whisper` | Audio transcription needed |
| `aitbc-ffmpeg` | Video processing needed |

```bash
# Manually enable an optional service
sudo systemctl enable aitbc-ai
sudo systemctl start aitbc-ai
```

## Runtime Units Outside the `setup.sh` Role Lists

The following run fleet-wide (verified on all five hosts 2026-10-04) but are
not in `setup.sh`'s base/hub/follower/shop enable lists — they arrive through
`link-systemd.sh` gates or were installed by hand:

| Unit | Port | Installed by | Notes |
|------|------|--------------|-------|
| `aitbc-island-ipfs` | 4002, 5002, 8081 | `link-systemd.sh`, only when `/etc/aitbc/aitbc-island-ipfs.env` exists or via `EXTRA_SERVICES` | island kubo IPFS; 4002 public, 5002+8081 on 127.0.0.1 |
| `aitbc-prometheus-watch` | — | no repo installer — host-created unit | watches local Prometheus alerts and writes `alerts.log` |
| `aitbc-load-secrets` | — | `link-systemd.sh` infra list (all roles) | `Type=oneshot`; runs `load-keystore-secrets.sh` at boot |

Also observed running, outside AITBC's unit set:

| Process | Port | Class |
|---------|------|-------|
| `ollama` | 11434 | non-AITBC system service (`ollama.service`, enabled) on the GPU nodes node0/node1/node2 |

**hub1 note (verified 2026-10-04):** the former hub runs the follower/base
set only — its hub-era units (`aitbc-api-gateway`, `aitbc-exchange`,
`aitbc-market`, `aitbc-agent-coordinator`, `aitbc-blockchain-event-bridge`,
`aitbc-blockchain-p2p`) were stopped and disabled on 2026-10-04 (their
symlinks into `/opt/aitbc` removed — the repo unit files still exist),
leaving `aitbc-blockchain-node` + `aitbc-blockchain-rpc` +
`aitbc-blockchain-explorer` + the base services behind nginx. Intended role:
demoted follower.

## Backup Service

All nodes get a daily backup service enabled automatically by `setup.sh`.

### What Gets Backed Up

| Component | Format | Description |
|-----------|--------|-------------|
| PostgreSQL | `.sql.gz` | Governance database dump |
| SQLite DBs | `.gz` | Blockchain chain DB, coordinator, market, agent, wallet, GPU |
| Keystore | `tar.gz` | All keys in `/var/lib/aitbc/keystore/` |
| Service configs | `tar.gz` | All files in `/etc/aitbc/` (env files, credentials, secrets) |
| Prometheus config | `tar.gz` | `/etc/prometheus/` if present |
| Redis | `rdb` | BGSAVE snapshot |

### Schedule & Retention

- **Schedule**: Daily at 01:00 (with up to 5 min random delay)
- **Retention**: 30 days
- **Location**: `/var/backups/aitbc/YYYYMMDD_HHMMSS/`

### Managing Backups

```bash
# Check timer status
systemctl status aitbc-backup.timer

# Check next scheduled run
systemctl list-timers aitbc-backup.timer

# Run a manual backup
sudo /opt/aitbc/scripts/maintenance/aitbc-backup.sh

# View backup logs
journalctl -t aitbc-backup --since today

# List existing backups
ls -la /var/backups/aitbc/

# Restore config from backup
sudo tar xzf /var/backups/aitbc/<timestamp>/etc-aitbc.tar.gz -C /
```

### PostgreSQL Backup Note

The backup script reads the governance database password from `/etc/aitbc/credentials/postgres_aitbc_governance_password` (created by `setup_postgresql_databases.sh`). As a fallback, it reads `DB_PASS` from `/etc/aitbc/aitbc-governance.env`.

The password is **never** read from `blockchain-secrets.env`. That file used to be published on the website, so it was kept free of database credentials; publishing it was itself the defect and stopped in v0.23 (V23-58). Keep DB credentials out of it regardless — it is distributed to every node running the wallet or agent-coordinator, which is a far wider audience than needs Postgres.

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Security](./setup-security.md) - Service user security
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
