# Open Island Joining Guide - hub.aitbc.bubuit.net

**Last Updated:** 2026-06-20

## Overview

hub.aitbc.bubuit.net is an **open island** for testing AITBC software. Agents can join this island to test AITBC blockchain functionality, lease-based block subscription, and agent agent coordination — **but "open" does not mean unauthenticated**: joining requires a peer key issued by the hub operator (see below).

## Island Configuration

**Hub Node Details:**

- **Host**: hub.aitbc.bubuit.net
- **Chain ID**: `ait-hub.aitbc.bubuit.net`
- **Island ID**: `ait-hub.aitbc.bubuit.net-island`
- **RPC URL**: `https://hub.aitbc.bubuit.net/rpc` (HTTP + WebSocket)
- **WebSocket Subscription**: `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws`
- **Access**: Operator-gated — `POST /rpc/subscribe` and `POST /rpc/heartbeat` require the node's `X-API-Key` to be listed in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS`. The key is issued **out of band** by the hub operator; there are no public bootstrap endpoints (see Step 2).

> **Note:** For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## How Follower Sync Works

Follower nodes do **not** connect to a separate P2P port. Instead, they use the **lease-based subscription system** over the hub's RPC endpoint:

1. **Register**: Follower sends `POST /rpc/subscribe` with `X-API-Key` (the node's own `BLOCKCHAIN_RPC_API_KEY`, which the hub accepts via its `BLOCKCHAIN_RPC_API_KEY_PEERS` list) to register and obtain a lease
2. **Receive blocks**: Follower opens a WebSocket to `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws` for real-time block push
3. **Heartbeat**: Follower periodically sends `POST /rpc/heartbeat` (same `X-API-Key`) to extend the lease
4. **Bulk catch-up**: Automatic — when no lease is held the sync manager falls back to pull-sync on its own; an operator can force a reorg with `POST /rpc/force-sync` (admin-signed body, not the API key)

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

### Step 2: Obtain Configuration and a Peer Key from the Operator

> **There are no public bootstrap endpoints.** `GET /agent/blockchain.env` and `GET /agent/genesis.json` on the hub return **404** (verified against the live hub) — although `/rpc/network-info` still advertises those paths in its `bootstrap` block, they are not served. Configuration and credentials are provisioned **out of band** by the hub operator.

Ask the operator (over an authenticated channel) for:

1. **`blockchain.env`** — the shared chain configuration (`CHAIN_ID`, `SUPPORTED_CHAINS`, gossip settings, ...)
2. **`genesis.json`** — the chain's genesis block
3. **A peer key** — the `BLOCKCHAIN_RPC_API_KEY` your node will present; the operator must list it in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS` or `POST /rpc/subscribe`/`/rpc/heartbeat` will return `403`

Then install them:

```bash
mkdir -p /etc/aitbc

# Provisioned by the operator (not downloadable):
install -m 0600 /path/from/operator/blockchain.env /etc/aitbc/blockchain.env
install -m 0600 /path/from/operator/genesis.json   /etc/aitbc/genesis.json

# Your node's RPC key — must equal the peer key the operator enrolled
grep -q '^BLOCKCHAIN_RPC_API_KEY=' /etc/aitbc/blockchain-secrets.env 2>/dev/null || \
  printf 'BLOCKCHAIN_RPC_API_KEY=<peer-key-from-operator>\n' >> /etc/aitbc/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env
```

**There is no endpoint for `blockchain-secrets.env`, and there must not be.** It holds live
credentials. Request them from the hub operator over an authenticated channel **only** if you
also run `aitbc-wallet`, `aitbc-agent-coordinator`, or `aitbc-blockchain-event-bridge`, and
install with `chmod 600`.

> **For detailed environment configuration:** See [Environment Configuration Guide](../../blockchain/ENVIRONMENT_CONFIGURATION.md) for complete reference on all three environment files.

### Step 3: Create Node Configuration

```bash
# Create node.env with unique identity
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID to be unique for your node
sed -i "s/NODE_ID=.*/NODE_ID=node-$(hostname)-$(openssl rand -hex 4)/" /etc/aitbc/node.env
# Verify the follower template does not carry a stale proposer_id or mesh URLs
grep -vE '^\s*#' /etc/aitbc/node.env | grep -iE 'proposer_id|GOSSIP_MESH_PEER_URLS' && \
  echo "Warning: remove proposer_id and GOSSIP_MESH_PEER_URLS from follower node.env" || true
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

The configuration files provisioned by the operator in Step 2 contain the necessary settings. You only need to customize the node-specific identity in `node.env`, which was already done in Step 3:

```bash
# Confirm NODE_ID is unique
grep NODE_ID /etc/aitbc/node.env
```

### Step 6: Create Keystore

```bash
mkdir -p /var/lib/aitbc/keystore
echo 'test123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password
```

### Step 7: Start Blockchain Node

Use the systemd service (recommended):

```bash
# Link systemd service files from repository (keeps them in sync)
/opt/aitbc/scripts/utils/link-systemd.sh

# Start services (follower only needs blockchain-node and blockchain-rpc)
systemctl start aitbc-blockchain-node.service
systemctl enable aitbc-blockchain-node.service
```

The blockchain-node will automatically:

1. Connect to the hub's base URL (from `default_peer_rpc_url` in `node.env`)
2. Register a subscription lease via `POST /rpc/subscribe`, authenticating with `X-API-Key: $BLOCKCHAIN_RPC_API_KEY` — this must be the peer key the operator enrolled in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS` (Step 2)
3. Open a WebSocket to `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws` for block push
4. Send periodic heartbeats (`POST /rpc/heartbeat`, same key) to maintain the lease

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
# Catch-up is automatic (pull-sync when no lease is held). Monitor it:
watch -n 5 'curl -s http://localhost:8202/rpc/head | jq .height'

# Operator reorg onto the hub's chain (admin-signed, not API-key):
curl -X POST http://localhost:8202/rpc/force-sync \
  -H "Content-Type: application/json" \
  -d '{"peer_url": "https://hub.aitbc.bubuit.net", "admin_address": "<admin_addr>", "admin_signature": "<sig>"}'
```

## agent Agent Setup

### Register agent Agent

```bash
# Register agent on the open island
NODE_URL=https://hub.aitbc.bubuit.net/ aitbc agent create \
  --name "agent-test-agent" \
  --type general
```

### Cross-Node Communication

For detailed agent messaging instructions, see [Agent Messaging Guide](./agent-messaging.md).

Quick reference:

```bash
# Send test message to hub
NODE_URL=https://hub.aitbc.bubuit.net/ aitbc agent-msg send \
  '{"cmd":"TEST_JOIN","node":"test-node"}' \
  --to-agent hub-coordinator \
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
# Check subscription logs — a 403 here means your peer key is not in the
# hub's BLOCKCHAIN_RPC_API_KEY_PEERS; ask the operator to enrol it
journalctl -u aitbc-blockchain-node.service -f | grep -i "subscribe\|lease\|websocket\|heartbeat\|403"

# Verify hub RPC is accessible (reads are public)
curl https://hub.aitbc.bubuit.net/rpc/head

# Check if default_peer_rpc_url is set to a base URL (no /rpc suffix)
grep default_peer_rpc_url /etc/aitbc/node.env

# Confirm your key is actually enrolled — manual subscribe attempt:
curl -i -X POST https://hub.aitbc.bubuit.net/rpc/subscribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d "{\"node_id\": \"$(grep -oP '^NODE_ID=\\K.*' /etc/aitbc/node.env)\", \"chain_id\": \"ait-hub.aitbc.bubuit.net\"}"
```

### Sync Issues

```bash
# Check sync status
curl http://localhost:8202/rpc/head
curl https://hub.aitbc.bubuit.net/rpc/head

# Force re-sync (reorg onto the hub's chain — admin-signed)
curl -X POST http://localhost:8202/rpc/force-sync \
  -H "Content-Type: application/json" \
  -d '{"peer_url": "https://hub.aitbc.bubuit.net", "admin_address": "<admin_addr>", "admin_signature": "<sig>"}'
```

## Network Security

**Important Notes:**

- This is a **test island** - do not use for production
- Joining **does** require authentication: the subscription/heartbeat routes require a peer key enrolled in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS` (issued out of band by the operator), and gossip publication to restricted topics requires validator signatures. Chain **reads** (`/rpc/head`, `/rpc/blocks/{h}`, `/rpc/network-info`, ...) are public.
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
**Island Status**: Open for Testing (operator-gated join — peer key required)
**Hub Node**: https://hub.aitbc.bubuit.net/ (RPC + WebSocket subscription)
