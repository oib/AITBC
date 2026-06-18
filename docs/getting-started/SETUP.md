# AITBC Setup Guide

**Last Updated:** 2026-06-18

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

| Profile | Description | Use Case |
|---------|-------------|----------|
| **server-no-gpu** | Core blockchain services without GPU dependencies | Standard blockchain node, no GPU hardware |
| **hub** | Full blockchain hub with all services | Central hub node with development tools |
| **customer-no-gpu** | Lightweight client for customers | Customer nodes consuming GPU resources |
| **provider-gpu** | GPU service provider with AI/ML capabilities | GPU shop nodes providing compute resources |

### Manual Profile Installation

```bash
# Activate virtual environment first
source /opt/aitbc/venv/bin/activate

# Install specific profile
./scripts/deployment/install-profiles.sh server-no-gpu
./scripts/deployment/install-profiles.sh hub
./scripts/deployment/install-profiles.sh customer-no-gpu
./scripts/deployment/install-profiles.sh provider-gpu

# List all available profiles
./scripts/deployment/install-profiles.sh
```

### Automatic Profile Detection

The setup.sh script automatically selects the appropriate profile based on your `/etc/aitbc/blockchain.env` configuration:

- `HARDWARE_PROFILE=gpu` + `MARKET_ROLE=shop` → **provider-gpu**
- `BLOCKCHAIN_MODE=hub` → **hub**
- `MARKET_ROLE=customer` → **customer-no-gpu**
- Default → **server-no-gpu**

### Profile Dependencies

Each profile installs different dependency sets:

- **server-no-gpu**: requirements.txt + security.txt
- **hub**: requirements.txt + security.txt + dev.txt
- **customer-no-gpu**: requirements-minimal.txt + CLI requirements
- **provider-gpu**: requirements.txt + ai-ml.txt + security.txt

## Node Profiles

During setup, you will be prompted to configure node profiles that determine which services run:

### Blockchain Mode
- **follower** (default) - Receives blocks from hub, runs periodic sync
- **hub** - Produces and broadcasts blocks, runs lease tracker for subscription system

### Market Role
- **customer** (default) - Consumes GPU resources
- **shop** - Provides GPU resources (requires GPU hardware)

### Hardware Profile
- **nogpu** (default) - No GPU available
- **gpu** - GPU available for compute

These profiles are set in `/etc/aitbc/blockchain.env` (read by blockchain node):

```bash
# Node Profiles (set during setup.sh)
BLOCKCHAIN_MODE=follower  # follower or hub
MARKET_ROLE=customer       # customer or shop
HARDWARE_PROFILE=nogpu    # gpu or nogpu
```

> **For detailed environment configuration:** See [Environment Configuration Guide](../blockchain/ENVIRONMENT_CONFIGURATION.md) for complete reference on `blockchain.env`, `node.env`, and `blockchain-secrets.env`.

## Lease-Based Subscription System

The blockchain node supports a lease-based push synchronization mechanism for efficient block propagation:

### Hub Configuration
Set `BLOCKCHAIN_MODE=hub` on hub nodes to enable:
- Block production and broadcasting
- Redis lease tracker for subscriber management
- Subscription RPC endpoints for follower registration

### Follower Configuration
Set `BLOCKCHAIN_MODE=follower` on follower nodes to enable:
- Periodic pull sync (fallback)
- Subscription client for push-based block reception
- Automatic lease renewal via heartbeat

### Subscription Settings
Configure in `/etc/aitbc/blockchain.env`:

```bash
# Lease-based subscription settings (followers)
SUBSCRIPTION_ENABLED=true
SUBSCRIPTION_TRANSPORT=redis
LEASE_DURATION=3600
LEASE_RENEWAL_THRESHOLD=300
HEARTBEAT_INTERVAL=60
```

### Subscription RPC Endpoints
Hub nodes provide these endpoints:
- `POST /rpc/subscribe` - Register for block subscription with lease
- `POST /rpc/heartbeat` - Extend subscription lease via heartbeat
- `GET /rpc/lease/{node_id}` - Get lease status for a subscriber
- `DELETE /rpc/lease/{node_id}` - Revoke subscription lease
- `GET /rpc/subscribers` - Get all valid subscribers

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
- Hub pushes blocks to subscribed followers via Redis pub/sub
- Requires valid lease (DHCP-style subscription)
- Automatic lease renewal via heartbeat
- Falls back to pull sync if subscription fails
- Settings in `/etc/aitbc/blockchain.env`:
  ```bash
  SUBSCRIPTION_ENABLED=true
  SUBSCRIPTION_TRANSPORT=redis
  LEASE_DURATION=3600
  LEASE_RENEWAL_THRESHOLD=300
  HEARTBEAT_INTERVAL=60
  ```

### Sync Mode Selection
The node automatically selects the sync mode based on configuration:
- If `SUBSCRIPTION_ENABLED=true` and hub is available → **Push sync**
- If subscription fails or hub unavailable → **Pull sync (fallback)**
- If `SUBSCRIPTION_ENABLED=false` → **Pull sync only**

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
curl https://hub.aitbc.bubuit.net/agent/blockchain.env -o /etc/aitbc/blockchain.env
curl https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env -o /etc/aitbc/blockchain-secrets.env

# 3. Configure node identity
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID in /etc/aitbc/node.env to a unique value for your node

# 4. Run setup script (non-interactive mode)
./scripts/deployment/setup.sh --open-island https://hub.aitbc.bubuit.net --node-id your-node-id

# 5. Start blockchain node
systemctl start aitbc-blockchain-node
systemctl status aitbc-blockchain-node
```

The node will automatically:
- Sync blocks from the hub via periodic pull sync
- Attempt subscription-based push sync (if hub supports it)
- Join the island with the configured `CHAIN_ID`

#### Verify Sync Status

```bash
# Check sync status
journalctl -u aitbc-blockchain-node -f | grep "Sync mode"

# View imported blocks
journalctl -u aitbc-blockchain-node | grep "Imported block"
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

AITBC uses a streamlined service user strategy based on network exposure for security isolation:

### Service Users

| User | Purpose | Services |
|------|---------|----------|
| **aitbc-public** | Public exposure services (0.0.0.0 binding) | API Gateway, Edge, Whisper |
| **aitbc-internal** | Internal services (127.0.0.1 binding) | Marketplace, Hermes, Agent Coordinator |
| **aitbc-blockchain** | Blockchain services | Node, P2P, RPC |
| **aitbc-gpu** | GPU service (needs video group) | GPU service |
| **aitbc-wallet** | Wallet service (keystore access) | Wallet service |

### Security Benefits

- **Principle of least privilege**: Services run with minimal required permissions
- **Exposure-based grouping**: Clear security boundaries (public vs internal vs specialized)
- **Compromise containment**: Limited to exposure category
- **Reduced user count**: 5 users for 26 services (vs individual users for each service)

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
