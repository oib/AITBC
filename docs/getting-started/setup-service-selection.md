# AITBC Setup - Service Selection

**Last Updated**: 2026-07-01
**Version**: 1.1

## Role-Based Service Selection

`setup.sh` automatically determines which services to enable and start based on the node's configuration. The service list is built by combining two independent axes:

- **Axis 1** (`BLOCKCHAIN_MODE`): hub services or follower services
- **Axis 2** (`MARKET_ROLE`): shop services (if `shop`) or nothing extra (if `customer`)

Both axes are evaluated independently and their service lists are merged. This means a `hub+shop` node gets both hub services AND shop services, not just one or the other.

### Service Combinations

| BLOCKCHAIN_MODE | MARKET_ROLE | Services | Count |
|----------------|-------------|----------|-------|
| hub | customer | base + hub | 18 |
| hub | shop | base + hub + shop | 23 |
| follower | customer | base + follower | 10 |
| follower | shop | base + follower + shop | 16 |

### Base Services (All Nodes)

Every node gets these services enabled and started:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-node` | — | Core blockchain node |
| `aitbc-blockchain-rpc` | 8202 | Blockchain RPC API |
| `aitbc-wallet` | 8108 | Wallet daemon |
| `aitbc-recovery` | — | Boot recovery (relinks systemd + loads secrets) |
| `aitbc-monitoring` | — | System monitoring |
| `aitbc-backup` | — | Daily backup service |
| `aitbc-trading` | 8109 | Trading service (inter-chain offer sync, gossip integration) |
| `aitbc-governance` | 8105 | Governance service (proposals, voting — all nodes participate) |

### Hub Services (BLOCKCHAIN_MODE=hub)

In addition to base services, hub nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-p2p` | 8200 | P2P network service |
| `aitbc-coordinator-api` | 8203 | Coordinator API (agent management, jobs) |
| `aitbc-api-gateway` | 8201 | Public API gateway (reverse proxy) |
| `aitbc-exchange` | 8106 | Exchange API |
| `aitbc-marketplace` | — | Marketplace service |
| `aitbc-bridge-monitor` | — | ETH↔AIT bridge monitor |
| `aitbc-blockchain-event-bridge` | 8205 | Blockchain event → service trigger bridge |
| `aitbc-agent` | 8107 | Agent messaging (coin requests) |
| `aitbc-agent-management` | 8204 | Agent registry API (public, followers connect) |
| `aitbc-agent-coordinator` | 8107 | Agent coordination backend (WebSocket PING/PONG, REQUEST_COINS) |
| `aitbc-blockchain-explorer` | 8100 | Blockchain explorer API |

### Follower Services (BLOCKCHAIN_MODE=follower)

In addition to base services, follower nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-sync` | — | Syncs blocks from hub via lease-based subscription |
| `aitbc-blockchain-explorer` | 8100 | Blockchain explorer API |

### Shop Services (MARKET_ROLE=shop)

In addition to the blockchain mode services, shop nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-gpu` | 8101 | GPU service API (advertises hardware to coordinator) |
| `aitbc-miner` | — | GPU compute provider client (registers with coordinator, sends heartbeats) |
| `aitbc-coordinator-api` | 8203 | Coordinator API (for local job coordination) |
| `aitbc-edge` | 8111 | Edge compute API (GPU job dispatch, health reporting) |
| `aitbc-pool-hub` | 8210 | Mining pool hub (pool join/leave, miner registration) |
| `aitbc-marketplace` | 8102 | Marketplace service (hardware/software bundle listings — needed by edge) |

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
| `aitbc-plugin` | Plugin system needed |

```bash
# Manually enable an optional service
sudo systemctl enable aitbc-ai
sudo systemctl start aitbc-ai
```

## Backup Service

All nodes get a daily backup service enabled automatically by `setup.sh`.

### What Gets Backed Up

| Component | Format | Description |
|-----------|--------|-------------|
| PostgreSQL | `.sql.gz` | Governance database dump |
| SQLite DBs | `.gz` | Blockchain chain DB, coordinator, marketplace, agent, wallet, GPU |
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

The password is **never** read from `blockchain-secrets.env` — that file is published on the website for followers to join the island and must not contain database credentials.

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Security](./setup-security.md) - Service user security
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
