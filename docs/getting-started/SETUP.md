# AITBC Setup Guide

**Last Updated:** 2026-06-02

Quick reference guide for AITBC setup and onboarding.

## 5-Minute Quick Start

```bash
# One-command installation
bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh)

# Or manual installation
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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

### Open Island
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
```

## Development Mode

```bash
cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Runtime Directories

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys
├── data/         # Database files
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
```

## Scenarios

For comprehensive AITBC capabilities and use cases, see [Scenarios Documentation](../scenarios/).

## See Also

- [README](../README.md) - Main documentation index
- [Deployment](../deployment/) - Production deployment guides
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
