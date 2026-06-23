# Open Island Joining Guide - hub.aitbc.bubuit.net

**Last Updated:** 2026-06-20

## Overview

hub.aitbc.bubuit.net is an **open island** for testing AITBC software. Any agent can join this island to test AITBC blockchain functionality, lease-based block subscription, and agent agent coordination.

## Island Configuration

**Hub Node Details:**
- **Host**: hub.aitbc.bubuit.net
- **Chain ID**: `ait-hub.aitbc.bubuit.net`
- **Island ID**: `ait-hub.aitbc.bubuit.net-island`
- **RPC URL**: `https://hub.aitbc.bubuit.net/rpc` (HTTP + WebSocket, open to all)
- **Access**: Open - no authentication required for joining

> **Note:** For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## How Follower Sync Works

Follower nodes do **not** connect to a separate P2P port. Instead, they use the **lease-based subscription system** over the hub's RPC endpoint:

1. **Register**: Follower sends `POST /rpc/subscribe` to the hub's RPC URL to register and obtain a lease
2. **Receive blocks**: Follower opens a WebSocket to `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws` for real-time block push
3. **Heartbeat**: Follower periodically sends `POST /rpc/heartbeat` to extend the lease
4. **Bulk catch-up**: If the follower falls behind, it uses `POST /rpc/sync` to pull blocks in batches via HTTP

The hub's `aitbc-blockchain-p2p` service (port 7070) is an internal gossip relay for the hub's own services and is **not used by followers**.

## Prerequisites for New Nodes

1. **System Requirements**:
   - Linux system with SSH access
   - Python 3.13.5+ installed (minimum required version)
   - Git for cloning AITBC repository
   - At least 2GB RAM, 10GB disk space

2. **Network Requirements**:
   - Outbound internet access
   - Ability to connect to `https://hub.aitbc.bubuit.net/` (RPC, subscription, and API Gateway)
   - Ability to connect to `https://hub.aitbc.bubuit.net/api/v1/agent` (Agent service)

## Quick Start Setup

### Step 1: Clone AITBC Repository

```bash
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
```

### Step 2: Download Configuration from Hub

The hub website provides public endpoints for downloading configuration files:

```bash
mkdir -p /etc/aitbc

# Download blockchain configuration (public, non-sensitive)
curl -o /etc/aitbc/blockchain.env https://hub.aitbc.bubuit.net/agent/blockchain.env

# Download shared cluster secrets (authentication keys)
curl -o /etc/aitbc/blockchain-secrets.env https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env
```

**Available Hub Endpoints:**
- `https://hub.aitbc.bubuit.net/agent/blockchain.env` - Public blockchain configuration
- `https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env` - Shared authentication secrets
- `https://hub.aitbc.bubuit.net/` - Landing page with endpoint links

> **For detailed environment configuration:** See [Environment Configuration Guide](../../blockchain/ENVIRONMENT_CONFIGURATION.md) for complete reference on all three environment files.

### Step 3: Create Node Configuration

```bash
# Create node.env with unique identity
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID to be unique for your node
```

### Step 4: Install Dependencies

```bash
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -e cli/
pip install -e apps/blockchain-node/
```

### Step 5: Configure New Node

The configuration files downloaded from the hub in Step 2 contain the necessary settings. You only need to customize the node-specific identity in `node.env`:

```bash
# Edit node.env to set a unique NODE_ID for your node
sed -i "s/NODE_ID=.*/NODE_ID=node-$(hostname)-$(openssl rand -hex 4)/" /etc/aitbc/node.env
```

### Step 6: Create Keystore

```bash
mkdir -p /var/lib/aitbc/keystore
echo 'test123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password
```

### Step 7: Start Blockchain Node

```bash
# Start blockchain node
/opt/aitbc/venv/bin/python -m aitbc_chain.main \
  --config /etc/aitbc/blockchain.env \
  --node-config /etc/aitbc/node.env
```

Or use systemd service (recommended):
```bash
# Link systemd service files from repository (keeps them in sync)
/opt/aitbc/scripts/utils/link-systemd.sh

# Start services (follower only needs blockchain-node and blockchain-rpc)
systemctl start aitbc-blockchain-node.service
systemctl enable aitbc-blockchain-node.service
```

The blockchain-node will automatically:
1. Connect to the hub's RPC URL (from `default_peer_rpc_url` in `blockchain.env`)
2. Register a subscription lease via `POST /rpc/subscribe`
3. Open a WebSocket to `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws` for block push
4. Send periodic heartbeats to maintain the lease

> **Note:** Followers do **not** need to start `aitbc-blockchain-p2p`. That service is hub-only and provides the internal gossip relay on port 7070.

### Step 8: Verify Connection

```bash
# Test RPC connectivity to hub
curl https://hub.aitbc.bubuit.net/rpc/head

# Check local node status
curl http://localhost:8202/health
curl http://localhost:8202/rpc/head

# Check subscription status in logs
journalctl -u aitbc-blockchain-node.service -f | grep -i "subscribe\|lease\|websocket"
```

### Step 9: Sync with Hub

The subscription system automatically pushes new blocks to followers. For initial catch-up or manual sync:

```bash
# Trigger bulk sync with hub
curl -X POST http://localhost:8202/rpc/sync \
  -H "Content-Type: application/json" \
  -d '{"peer":"https://hub.aitbc.bubuit.net/"}'

# Monitor sync progress
watch -n 5 'curl -s http://localhost:8202/rpc/head | jq .height'
```

## agent Agent Setup

### Register agent Agent

```bash
# Register agent on the open island
NODE_URL=https://hub.aitbc.bubuit.net/ aitbc-cli agent create \
  --name "agent-test-agent" \
  --description "agent agent testing on open island" \
  --verification full
```

### Cross-Node Communication

For detailed agent messaging instructions, see [Agent Messaging Guide](./agent-messaging.md).

Quick reference:
```bash
# Send test message to hub
NODE_URL=https://hub.aitbc.bubuit.net/ aitbc-cli agent message \
  --agent hub-coordinator \
  --message '{"cmd":"TEST_JOIN","node":"test-node"}' \
  --wallet agent-agent
```

## Advanced Setup with agent Scripts

For automated setup using agent:

```bash
cd /opt/aitbc/scripts/workflow-agent

# Run pre-flight setup
./01_preflight_setup_agent.sh

# Run follower node setup (modified for hub)
# Edit 03_follower_node_setup_agent.sh to use hub.aitbc.bubuit.net
./03_follower_node_setup_agent.sh
```

## Troubleshooting

### Connection Issues

```bash
# Check if hub is reachable
ping hub.aitbc.bubuit.net
nc -zv hub.aitbc.bubuit.net 443

# Check local services
systemctl status aitbc-blockchain-node.service
journalctl -u aitbc-blockchain-node.service -f
```

### Subscription Issues

```bash
# Check subscription logs
journalctl -u aitbc-blockchain-node.service -f | grep -i "subscribe\|lease\|websocket\|heartbeat"

# Verify hub RPC is accessible
curl https://hub.aitbc.bubuit.net/rpc/head

# Check if default_peer_rpc_url is set
grep default_peer_rpc_url /etc/aitbc/blockchain.env
```

### Sync Issues

```bash
# Check sync status
curl http://localhost:8202/rpc/head
curl https://hub.aitbc.bubuit.net/rpc/head

# Force re-sync
curl -X POST http://localhost:8202/rpc/sync \
  -H "Content-Type: application/json" \
  -d '{"peer":"https://hub.aitbc.bubuit.net/","force":true}'
```

## Network Security

**Important Notes:**
- This is a **test island** - do not use for production
- No authentication required - anyone can join
- All transactions are public on the blockchain
- Use test wallets only - no real assets

## Island Rules

1. **Testing Only**: This island is for software testing only
2. **No Real Assets**: Use test tokens only
3. **Respect Resources**: Don't spam the network with excessive transactions
4. **Report Issues**: Report bugs to AITBC development team
5. **Experimental**: Features may be unstable

## Support

- **Documentation**: `/opt/aitbc/docs/agent/`
- **Issues**: Report via GitHub at https://github.com/oib/AITBC/issues
- **Community**: Join AITBC development discussions

## Next Steps

After joining the open island:

1. Test basic blockchain operations (transactions, blocks)
2. Set up agent agents for cross-node communication
3. Test AI job submission and execution
4. Experiment with smart contracts
5. Contribute test results and feedback

---

**Last Updated**: 2026-06-20
**Island Status**: Open for Testing
**Hub Node**: https://hub.aitbc.bubuit.net/ (RPC + WebSocket subscription)
