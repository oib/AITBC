# AITBC Setup Guide

**Last Updated:** 2026-06-22

Quick reference guide for AITBC setup and onboarding.

> **🟢 Service Status**: All core services are operational as of June 7, 2026. See [Service Status](../infrastructure/SYSTEMD_SERVICES.md#current-service-status) for details.

> **⚠️ v0.4.26 Update**: JWT authentication is now required. `setup.sh` automatically generates `JWT_SECRET` and `SECRET_KEY`. If upgrading from an earlier version, run `/opt/aitbc/scripts/utils/load-keystore-secrets.sh` after updating the credential files.

## 5-Minute Quick Start

```bash
# One-command installation (includes service user setup)
bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh)

# Or manual installation
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The setup script automatically creates service users for security isolation based on network exposure.

## Install Profiles

AITBC provides pre-configured dependency profiles for different deployment scenarios. The setup script automatically detects the appropriate profile based on your node configuration, or you can manually install a specific profile.

### Available Profiles

Profiles are composed from the two independent axes (`BLOCKCHAIN_MODE` + `MARKET_ROLE` + `HARDWARE_PROFILE`):

| Profile | Description | Use Case |
|---------|-------------|----------|
| **follower-customer** | Core blockchain services, no GPU | Standard follower node consuming resources |
| **follower-customer-gpu** | Core blockchain services with GPU drivers | Follower with GPU but not selling |
| **follower-shop** | Follower + GPU provider services | Follower that also sells GPU compute |
| **follower-shop-gpu** | Follower + GPU provider + AI/ML deps | Follower with GPU selling compute |
| **hub-customer** | Full blockchain hub without GPU deps | Central hub node, no GPU selling |
| **hub-customer-gpu** | Full blockchain hub with GPU drivers | Central hub with GPU but not selling |
| **hub-shop** | Full hub + GPU provider services | Hub that also sells GPU compute |
| **hub-shop-gpu** | Full hub + GPU provider + AI/ML deps | Hub with GPU selling compute |

### Manual Profile Installation

```bash
# Activate virtual environment first
source /opt/aitbc/venv/bin/activate

# Install specific profile
./scripts/deployment/install-profiles.sh follower-customer
./scripts/deployment/install-profiles.sh hub-shop-gpu

# List all available profiles
./scripts/deployment/install-profiles.sh
```

### Automatic Profile Detection

The setup.sh script automatically selects the appropriate profile based on your `/etc/aitbc/blockchain.env` configuration. The profile name is composed as `{blockchain_mode}-{market_role}[-gpu]`:

- `BLOCKCHAIN_MODE=hub` + `MARKET_ROLE=shop` + `HARDWARE_PROFILE=gpu` → **hub-shop-gpu**
- `BLOCKCHAIN_MODE=hub` + `MARKET_ROLE=customer` → **hub-customer**
- `BLOCKCHAIN_MODE=follower` + `MARKET_ROLE=shop` + `HARDWARE_PROFILE=gpu` → **follower-shop-gpu**
- `BLOCKCHAIN_MODE=follower` + `MARKET_ROLE=customer` → **follower-customer**
- Default → **follower-customer**

### Profile Dependencies

Each profile installs different dependency sets:

- **follower-customer**: requirements-minimal.txt + CLI requirements
- **hub-customer**: requirements.txt + security.txt + dev.txt
- **follower-shop-gpu**: requirements.txt + ai-ml.txt + security.txt
- **hub-shop-gpu**: requirements.txt + ai-ml.txt + security.txt + dev.txt

## Node Profiles

During setup, you will be prompted to configure two independent axes that determine which services run:

### Axis 1: Blockchain Mode (`BLOCKCHAIN_MODE`)
- **follower** (default) - Receives blocks from hub, runs periodic sync
- **hub** - Produces and broadcasts blocks, runs lease tracker for subscription system

### Axis 2: Market Role (`MARKET_ROLE`)
- **customer** (default) - Consumes GPU resources
- **shop** - Provides GPU resources to the marketplace

### Hardware Profile (`HARDWARE_PROFILE`)
- **nogpu** (default) - No GPU available
- **gpu** - GPU available for compute

These two axes are **independent** — a hub can also be a shop, and a follower can be a customer or a shop. The service selection combines both axes (see [Role-Based Service Selection](#role-based-service-selection) below).

These profiles are set in `/etc/aitbc/blockchain.env` (read by blockchain node):

```bash
# Node Profiles (set during setup.sh) — two independent axes
BLOCKCHAIN_MODE=follower  # follower or hub
MARKET_ROLE=customer       # customer or shop
HARDWARE_PROFILE=nogpu    # gpu or nogpu
```

> **For detailed environment configuration:** See [Environment Configuration Guide](../blockchain/ENVIRONMENT_CONFIGURATION.md) for complete reference on `blockchain.env`, `node.env`, and `blockchain-secrets.env`.

## Role-Based Service Selection

`setup.sh` automatically determines which services to enable and start based on the node's configuration. The service list is built by combining two independent axes:

- **Axis 1** (`BLOCKCHAIN_MODE`): hub services or follower services
- **Axis 2** (`MARKET_ROLE`): shop services (if `shop`) or nothing extra (if `customer`)

Both axes are evaluated independently and their service lists are merged. This means a `hub+shop` node gets both hub services AND shop services, not just one or the other.

### Service Combinations

| BLOCKCHAIN_MODE | MARKET_ROLE | Services | Count |
|----------------|-------------|----------|-------|
| hub | customer | base + hub | 20 |
| hub | shop | base + hub + shop | 22 |
| follower | customer | base + follower | 9 |
| follower | shop | base + follower + shop | 12 |

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

### Hub Services (BLOCKCHAIN_MODE=hub)

In addition to base services, hub nodes get:

| Service | Port | Description |
|---------|------|-------------|
| `aitbc-blockchain-p2p` | 8200 | P2P network service |
| `aitbc-coordinator-api` | 8203 | Coordinator API (agent management, jobs) |
| `aitbc-api-gateway` | 8201 | Public API gateway (reverse proxy) |
| `aitbc-governance` | 8105 | Governance service |
| `aitbc-exchange` | 8106 | Exchange API |
| `aitbc-marketplace` | — | Marketplace service |
| `aitbc-bridge-monitor` | — | ETH↔AIT bridge monitor |
| `aitbc-blockchain-event-bridge` | 8205 | Blockchain event → service trigger bridge |
| `aitbc-hermes` | 8103 | Hermes messaging (coin requests) |
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
| `aitbc-trading` | Trading bot feature |
| `aitbc-edge` | Edge API needed |
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
| SQLite DBs | `.gz` | Blockchain chain DB, coordinator, marketplace, hermes, wallet, GPU |
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

## Lease-Based Subscription System

The blockchain node supports a lease-based push synchronization mechanism for efficient block propagation from hub to followers. Followers do **not** need the `aitbc-blockchain-p2p` service (port 7070) — that is a hub-only internal gossip relay. Followers receive blocks via the subscription system over the hub's RPC endpoint.

### Hub Configuration
Set `BLOCKCHAIN_MODE=hub` on hub nodes to enable:
- Block production and broadcasting
- Redis lease tracker for subscriber management
- Subscription RPC endpoints for follower registration
- WebSocket block push on `/rpc/subscribe/ws`

### Follower Configuration
Set `BLOCKCHAIN_MODE=follower` on follower nodes to enable:
- Subscription client connects to hub's RPC URL (`default_peer_rpc_url`)
- Registers a lease via `POST /rpc/subscribe`
- Receives blocks via WebSocket on `wss://hub/rpc/subscribe/ws`
- Automatic lease renewal via heartbeat (`POST /rpc/heartbeat`)
- Falls back to periodic pull sync if subscription fails

### Subscription Settings
Configure in `/etc/aitbc/blockchain.env`:

```bash
# Required: Hub RPC URL for follower subscription
default_peer_rpc_url=http://hub.aitbc.bubuit.net/rpc

# Lease-based subscription settings (followers)
subscription_enabled=true
subscription_transport=websocket
```

### Subscription RPC Endpoints
Hub nodes provide these endpoints (proxied through nginx):

**HTTP endpoints** (via `/rpc/` nginx proxy):
- `POST /rpc/subscribe` - Register for block subscription with lease
- `POST /rpc/heartbeat` - Extend subscription lease via heartbeat
- `GET /rpc/lease/{node_id}` - Get lease status for a subscriber
- `DELETE /rpc/lease/{node_id}` - Revoke subscription lease
- `GET /rpc/subscribers` - Get all valid subscribers

**WebSocket endpoints** (via nginx with upgrade headers):
- `ws://hub/rpc/subscribe/ws` - Real-time block push to subscribed followers
- `ws://hub/rpc/blocks` - Block stream (public)
- `ws://hub/rpc/transactions` - Transaction stream (public)

## Sync Modes

The blockchain node supports two synchronization modes for block propagation:

### Pull Sync (Periodic)
- **Default mode** for follower nodes
- Periodically polls the hub for new blocks
- Configurable interval (default: 30 seconds)
- Always available as fallback
- Settings in `/etc/aitbc/blockchain.env`:
  ```bash
  PERIODIC_SYNC_ENABLED=true
  PERIODIC_SYNC_INTERVAL=30
  ```

### Push Sync (Subscription)
- **Efficient mode** when subscription is enabled
- Hub pushes blocks to subscribed followers via WebSocket (`/rpc/subscribe/ws`)
- Requires valid lease (DHCP-style subscription)
- Automatic lease renewal via heartbeat
- Falls back to pull sync if subscription fails
- Settings in `/etc/aitbc/blockchain.env`:
  ```bash
  subscription_enabled=true
  subscription_transport=websocket
  default_peer_rpc_url=http://hub.aitbc.bubuit.net/rpc
  ```

### Sync Mode Selection
The node automatically selects the sync mode based on configuration:
- If `subscription_enabled=true` and hub is available → **Push sync** (WebSocket)
- If subscription fails or hub unavailable → **Pull sync (fallback)**
- If `subscription_enabled=false` → **Pull sync only**

The current sync mode is logged at startup and can be monitored via:
```bash
journalctl -u aitbc-blockchain-node -f | grep "Sync mode"
```

## Essential Links

### Installation
- [Prerequisites](installation/prerequisites.md) - System and software requirements
- [Quick Start](installation/quick-start.md) - One-command installation
- [Installation](installation/installation.md) - Monorepo installation
- [Requirements Management](installation/requirements-management.md) - Dependency profiles

### Node Onboarding
- [Blockchain Setup](node/blockchain-setup.md) - Configure blockchain node
- [Hermes Messaging](node/hermes-messaging.md) - PING/PONG messaging
- [Coin Requests](node/coin-requests.md) - Request free coins from hub
- [Configuration Guide](node/configuration-guide.md) - Configuration files

### Mining
- [Miner Quick Start](mining/miner-quick-start.md) - Register GPU and earn tokens

### Platform Overview
- [Introduction](overview/introduction.md) - What is AITBC
- [CLI Guide](overview/cli-guide.md) - CLI setup and usage
- [Enhanced Services](overview/enhanced-services.md) - Enhanced services guide

### Reference
- [Service Endpoints](reference/service-endpoints.md) - Port configuration
- [Management Commands](reference/management-commands.md) - Service control
- [Troubleshooting](reference/troubleshooting.md) - Common issues
- [Security Notes](reference/security-notes.md) - Security best practices
- [Production Deployment](reference/production-deployment.md) - Production checklist
- [Service Isolation](../operations/SERVICE_ISOLATION_2026-06-07.md) - Service user security configuration

### Open Island

#### Join an Open Island as Follower

To join an existing AITBC hub (e.g., `https://hub.aitbc.bubuit.net`) as a follower node:

```bash
# 1. Clone the repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# 2. Download hub configuration
mkdir -p /etc/aitbc
curl https://hub.aitbc.bubuit.net/agent/blockchain.env -o /etc/aitbc/blockchain.env
curl https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env -o /etc/aitbc/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env

# 3. Configure node identity
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID in /etc/aitbc/node.env to a unique value for your node

# 4. Run setup script (non-interactive mode)
./scripts/deployment/setup.sh --open-island https://hub.aitbc.bubuit.net --node-id your-node-id

# 5. Start blockchain node (follower only needs blockchain-node, not blockchain-p2p)
systemctl start aitbc-blockchain-node
systemctl enable aitbc-blockchain-node
systemctl status aitbc-blockchain-node
```

The node will automatically:
- Connect to the hub's RPC URL (`default_peer_rpc_url` from `blockchain.env`)
- Register a subscription lease via `POST /rpc/subscribe`
- Receive blocks via WebSocket push (`wss://hub/rpc/subscribe/ws`)
- Send periodic heartbeats to maintain the lease
- Fall back to periodic pull sync if subscription fails
- Join the island with the configured `CHAIN_ID`

> **Note:** Followers do **not** need to start `aitbc-blockchain-p2p`. That service is hub-only.

#### Verify Sync Status

```bash
# Check subscription status
journalctl -u aitbc-blockchain-node -f | grep -i "subscribe\|lease\|websocket\|Sync mode"

# View imported blocks
journalctl -u aitbc-blockchain-node | grep "Imported block"

# Check local node height vs hub
curl -s http://localhost:8202/rpc/head | jq .height
curl -s https://hub.aitbc.bubuit.net/rpc/head | jq .height
```
- [Open Island Testing](open-island.md) - Join hub.aitbc.bubuit.net

## Common Commands

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs
tail -f /var/lib/aitbc/logs/aitbc-*.log

# Systemd control
systemctl status aitbc-blockchain-node
systemctl restart aitbc-coordinator-api

# AITBC CLI (marketplace, wallet, blockchain operations)
aitbc market list          # List marketplace offers
aitbc wallet balance       # Check wallet balance
aitbc blockchain status    # Check blockchain status
aitbc --help               # Show all CLI commands
```

## Updating an Existing Node

After the initial `setup.sh` run, use `update.sh` to safely apply new code
changes. It backs up, pulls, syncs the venv, relinks systemd, restarts
services, and runs a health check.

```bash
sudo /opt/aitbc/scripts/deployment/update.sh
```

For flags (`--no-pull`, `--no-restart`, `--skip-backup`), step-by-step
details, rollback procedures, and troubleshooting, see
[UPDATE.md](./UPDATE.md).

### Re-running setup on an existing node

If you run `setup.sh` on a node that is already installed (detected by the
presence of `/etc/aitbc/node.env` and `/opt/aitbc/venv`), it automatically
forwards to `update.sh` instead of re-running the full first-time install.
This prevents accidental re-initialization of databases, credentials, and
node identity.

To force a full re-run (e.g. to repair a broken install), use `--force`:

```bash
sudo /opt/aitbc/scripts/deployment/setup.sh --force
```

## Development Mode

```bash
cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8203
```

## Runtime Directories

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys
├── data/         # Database files
├── wallets/      # Wallet files (aitbc-wallet user)
├── whisper-cache/ # Whisper model cache (aitbc-public user)
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
```

## Required Secrets

The following secrets are generated automatically by `setup.sh` and stored in `/etc/aitbc/credentials/` (mode 600). They are loaded at runtime into `/run/aitbc/secrets/.env` (tmpfs, cleared on reboot) by `load-keystore-secrets.sh`.

| Secret | Environment Variable | Used By | Description |
|--------|---------------------|---------|-------------|
| `api_hash_secret` | `API_KEY_HASH_SECRET` | API Gateway | Hash secret for API key validation |
| `jwt_secret` | `JWT_SECRET` | Coordinator API | JWT token signing/verification |
| `secret_key` | `SECRET_KEY` | Coordinator API | Application secret key |
| `keystore_password` | `KEYSTORE_PASSWORD` | Wallet service | Keystore encryption password |
| `proposer_id` | `proposer_id` | Blockchain node | Node proposer identity |

### Regenerating Secrets

If secrets are missing (e.g. after a fresh clone on an existing node):

```bash
# Regenerate all secrets
sudo /opt/aitbc/scripts/deployment/setup.sh

# Or regenerate individual secrets manually
python3 -c "import secrets; print(secrets.token_hex(32))" | sudo tee /etc/aitbc/credentials/jwt_secret
chmod 600 /etc/aitbc/credentials/jwt_secret
sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh
sudo systemctl restart aitbc-coordinator-api
```

## Per-Service Environment Files (%N.env)

Each systemd service uses `EnvironmentFile=/etc/aitbc/%N.env` to load service-specific configuration. The `%N` specifier expands to the **unit name without the `.service` suffix** (e.g., `aitbc-coordinator-api.service` → `/etc/aitbc/aitbc-coordinator-api.env`).

These files are created automatically by `setup_postgresql_databases.sh` and contain `DATABASE_URL` with credentials, `JWT_SECRET`, `REDIS_URL`, and other service-specific settings.

### File Naming Convention

| Service unit | `%N` expands to | Env file path |
|---|---|---|
| `aitbc-coordinator-api.service` | `aitbc-coordinator-api` | `/etc/aitbc/aitbc-coordinator-api.env` |
| `aitbc-governance.service` | `aitbc-governance` | `/etc/aitbc/aitbc-governance.env` |
| `aitbc-blockchain-p2p.service` | `aitbc-blockchain-p2p` | `/etc/aitbc/aitbc-blockchain-p2p.env` |
| `aitbc-exchange.service` | `aitbc-exchange` | `/etc/aitbc/aitbc-exchange.env` |

> **Important:** The file name must NOT include `.service` — `%N` strips the `.service` suffix. Naming a file `aitbc-coordinator-api.service.env` will cause systemd to fail with `Failed to load environment files: No such file or directory`.

### DATABASE_URL Format

The `DATABASE_URL` must include credentials. Without them, PostgreSQL rejects the connection with `fe_sendauth: no password supplied`.

```bash
# Correct (with credentials)
DATABASE_URL=postgresql://aitbc_user:aitbc_user_password@localhost:5432/aitbc_coordinator

# Wrong (no credentials — causes fe_sendauth error)
DATABASE_URL=postgresql://localhost:5432/aitbc_coordinator
```

### Regenerating Per-Service Env Files

If env files are missing or have incorrect `DATABASE_URL`:

```bash
# Regenerate all databases, users, and env files
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh

# Or manually create a single env file
sudo tee /etc/aitbc/aitbc-coordinator-api.env << 'EOF'
JWT_SECRET=<your-jwt-secret>
API_KEY_HASH_SECRET=<your-api-key-hash-secret>
DATABASE_URL=postgresql://aitbc_user:<password>@localhost:5432/aitbc_coordinator
REDIS_URL=redis://localhost:6379/0
EOF
sudo systemctl restart aitbc-coordinator-api
```

### [Install] Section in Service Files

Each service file must include an `[Install]` section for `systemctl enable` to work:

```ini
[Install]
WantedBy=multi-user.target
```

Without this, `systemctl enable` fails with "no installation config" and the service won't auto-start on boot.

### Upgrading from v0.4.25 or Earlier

Earlier versions did not generate `JWT_SECRET` or `SECRET_KEY`. After upgrading:

```bash
# 1. Generate the new secrets
sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh

# 2. Verify they were added to the runtime env file
grep -E "JWT_SECRET|SECRET_KEY" /run/aitbc/secrets/.env

# 3. Restart the coordinator-api
sudo systemctl restart aitbc-coordinator-api
```

## Service User Security

AITBC services run as the `aitbc` system user (created by `setup.sh`). Additional specialized service users are created for future security isolation but are not currently used by the service files.

### Service Users

| User | Purpose | Currently Used By |
|------|---------|----------|
| **aitbc** | Primary service user (all services run as this) | All 32+ systemd services |
| **aitbc-public** | Reserved for public exposure services | Not yet assigned |
| **aitbc-internal** | Reserved for internal services | Not yet assigned |
| **aitbc-blockchain** | Reserved for blockchain services | Not yet assigned |
| **aitbc-gpu** | Reserved for GPU service (needs video group) | Not yet assigned |
| **aitbc-wallet** | Reserved for wallet service (keystore access) | Not yet assigned |

### Security Benefits

- **Principle of least privilege**: Services run with minimal required permissions
- **Exposure-based grouping**: Clear security boundaries (public vs internal vs specialized)
- **Compromise containment**: Limited to exposure category
- **Reduced user count**: 1 active user for all services (specialized users ready for future isolation)

### User Configuration

All service users:
- Shell: `/bin/false` (no shell access)
- Group: `aitbc-services` (common group)
- Home directory: Created but not used

**Special Groups:**
- `aitbc-gpu`: Added to `video` group for GPU access
- `aitbc-public`: Added to `video` and `audio` groups for whisper

### Service Isolation Status

**Currently Isolated:** 11/26 services (42%)
- Public services: 3/26
- Internal services: 3/26
- Blockchain services: 3/26
- Specialized services: 2/26

**Remaining Services:** 15/26 still run as root

For detailed service isolation configuration, see [Service Isolation Documentation](../operations/SERVICE_ISOLATION_2026-06-07.md).

## Scenarios

For comprehensive AITBC capabilities and use cases, see [Scenarios Documentation](../scenarios/).

## See Also

- [README](../README.md) - Main documentation index
- [Deployment](../deployment/) - Production deployment guides
- [Incus Port Forwarding](../deployment/incus-port-forwarding.md) - Container port configuration
- [Firehol Configuration](../deployment/firehol-configuration.md) - Firewall configuration
- [Nginx Setup](../deployment/nginx-setup.md) - Nginx reverse proxy configuration
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration

## Troubleshooting

### Common Setup Issues

#### ModuleNotFoundError: No module named 'pydantic-settings'

`pydantic-settings` is a core dependency (required by multiple apps including coordinator-api and blockchain-node). It is included in `requirements.txt` since v0.4.26. If you see this error, reinstall dependencies:

```bash
cd /opt/aitbc
source venv/bin/activate
pip install -r requirements.txt
systemctl restart aitbc-coordinator-api aitbc-blockchain-node
```

#### PermissionError: Permission denied on /var/lib/aitbc/data

The blockchain-node service runs as `aitbc-blockchain` user and needs write access to data directories.

```bash
# Fix permissions
chown -R aitbc-blockchain:aitbc-services /var/lib/aitbc/data
systemctl restart aitbc-blockchain-node
```

#### Service fails to start: Unable to locate executable '/opt/aitbc/venv/bin/python'

The virtual environment may not exist or was corrupted.

```bash
# Recreate virtual environment
rm -rf /opt/aitbc/venv
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
systemctl restart aitbc-blockchain-node
```

#### Service user does not exist

Service users are created by the setup script. If they're missing:

```bash
# Create service users manually
groupadd aitbc-services
useradd -r -s /bin/false -g aitbc-services aitbc-blockchain
useradd -r -s /bin/false -g aitbc-services aitbc-public
useradd -r -s /bin/false -g aitbc-services aitbc-internal
useradd -r -s /bin/false -g aitbc-services aitbc-gpu
useradd -r -s /bin/false -g aitbc-services aitbc-wallet
```

#### Sync mode: pull (periodic, WebSocket push unavailable)

The node is using pull sync instead of push sync. This is normal for follower nodes and will work correctly.

```bash
# Verify sync is working
journalctl -u aitbc-blockchain-node | grep "Imported block"
```

If you want to enable push sync, ensure the hub supports subscription endpoints and check your network connectivity to the hub.

#### Service fails: "Failed to load environment files: No such file or directory"

The service's `EnvironmentFile=/etc/aitbc/%N.env` references a file that doesn't exist. The `%N` specifier expands to the unit name **without** `.service` (e.g., `aitbc-blockchain-node.service` → `aitbc-blockchain-node`).

```bash
# Check which env file the service expects
grep EnvironmentFile /etc/systemd/system/aitbc-blockchain-node.service

# Verify the file exists (must NOT have .service in the name)
ls -la /etc/aitbc/aitbc-blockchain-node.env

# If missing, regenerate env files
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh

# Or create manually (see "Per-Service Environment Files" section above)
```

#### Service fails: "fe_sendauth: no password supplied"

The `DATABASE_URL` in the service's `%N.env` file lacks credentials. PostgreSQL requires a username and password.

```bash
# Check the DATABASE_URL in the env file
grep DATABASE_URL /etc/aitbc/aitbc-coordinator-api.env

# If it's missing credentials, fix it:
# Wrong:  DATABASE_URL=postgresql://localhost:5432/aitbc_coordinator
# Right:  DATABASE_URL=postgresql://aitbc_user:<password>@localhost:5432/aitbc_coordinator

# Regenerate with correct credentials
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh
sudo systemctl restart aitbc-coordinator-api
```

#### systemctl enable fails: "no installation config"

The service file is missing an `[Install]` section. Add it to the service file:

```bash
echo -e '\n[Install]\nWantedBy=multi-user.target' | sudo tee -a /etc/systemd/system/aitbc-coordinator-api.service
sudo systemctl daemon-reload
sudo systemctl enable aitbc-coordinator-api
```
