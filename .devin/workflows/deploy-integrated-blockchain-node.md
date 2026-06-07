---
description: Deploy integrated blockchain node with mempool support
---

# Integrated Blockchain Node Deployment Workflow

This workflow deploys the integrated blockchain node (with full mempool support) to a target host or container. This is the recommended approach for production deployments.

## Prerequisites

- Target host with SSH access
- Python 3.13+ installed on target
- Root or sudo access on target
- Git installed on target

## Workflow Steps

### 1. Verify Target Environment

```bash
# Check Python version
ssh $TARGET "python3 --version"

# Check if git is available
ssh $TARGET "git --version"

# Check if systemd is available
ssh $TARGET "systemctl --version"
```

### 2. Clone Repository

```bash
# Clone AITBC repository to target
ssh $TARGET "sudo git clone https://gitea.bubuit.net:3000/oib/aitbc.git /opt/aitbc"
```

### 3. Run Deployment Script

```bash
# Execute deployment script on target
ssh $TARGET "sudo bash /opt/aitbc/scripts/deployment/deploy-integrated-blockchain-node.sh"
```

### 4. Verify Deployment

```bash
# Check service status
ssh $TARGET "sudo systemctl status aitbc-blockchain-node --no-pager"

# Check RPC endpoint
ssh $TARGET "curl -s http://localhost:8006/rpc/head"

# Check mempool endpoint
ssh $TARGET "curl -s http://localhost:8006/rpc/mempool"
```

### 5. Configure for Production

```bash
# Edit blockchain configuration
ssh $TARGET "sudo nano /etc/aitbc/blockchain.env"

# Set production values
# ENABLE_BLOCK_PRODUCTION=true/false
# CHAIN_ID=ait-mainnet
# NODE_ROLE=hub/follower

# Restart service to apply changes
ssh $TARGET "sudo systemctl restart aitbc-blockchain-node"
```

## Container Deployment

### For incus Containers

```bash
# Create container
TARGET_CONTAINER="aitbc-container"
incus launch ubuntu:22.04 $TARGET_CONTAINER

# Push repository to container
incus file push -r /opt/aitbc $TARGET_CONTAINER/opt/

# Run setup inside container
incus exec $TARGET_CONTAINER -- bash /opt/aitbc/scripts/deployment/deploy-integrated-blockchain-node.sh

# Verify deployment
incus exec $TARGET_CONTAINER -- systemctl status aitbc-blockchain-node --no-pager
incus exec $TARGET_CONTAINER -- curl -s http://localhost:8006/rpc/mempool
```

### For ns3 Container (hub.aitbc.bubuit.net)

```bash
# SSH to ns3
ssh ns3

# Stop standalone node
incus exec aitbc -- systemctl stop aitbc-blockchain-node-3
incus exec aitbc -- systemctl disable aitbc-blockchain-node-3

# Clone repository
incus exec aitbc -- git clone https://gitea.bubuit.net:3000/oib/aitbc.git /opt/aitbc

# Run deployment script
incus exec aitbc -- bash /opt/aitbc/scripts/deployment/deploy-integrated-blockchain-node.sh

# Verify deployment
incus exec aitbc -- curl -s http://localhost:8006/rpc/mempool
```

## Configuration Templates

### Hub Node Configuration

```env
# /etc/aitbc/blockchain.env
CHAIN_ID=ait-mainnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8001
ENABLE_BLOCK_PRODUCTION=true
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
CROSS_SITE_REMOTE_ENDPOINTS=
```

```env
# /etc/aitbc/node.env
NODE_ID=hub.aitbc.bubuit.net
ISLAND_ID=ait-public-island
CHAIN_ID=ait-mainnet
NODE_ROLE=hub
P2P_BIND_PORT=8001
```

### Follower Node Configuration

```env
# /etc/aitbc/blockchain.env
CHAIN_ID=ait-mainnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8001
ENABLE_BLOCK_PRODUCTION=false
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
CROSS_SITE_REMOTE_ENDPOINTS=https://hub.aitbc.bubuit.net/rpc
```

```env
# /etc/aitbc/node.env
NODE_ID=follower-$(hostname)
ISLAND_ID=ait-public-island
CHAIN_ID=ait-mainnet
NODE_ROLE=follower
P2P_BIND_PORT=8001
```

## Verification Steps

After deployment, verify:

1. **Service Status:**
   ```bash
   systemctl is-active aitbc-blockchain-node
   ```

2. **RPC Endpoint:**
   ```bash
   curl -s http://localhost:8006/rpc/head | jq
   ```

3. **Mempool Endpoint:**
   ```bash
   curl -s http://localhost:8006/rpc/mempool | jq
   ```

4. **P2P Connectivity:**
   ```bash
   netstat -tlnp | grep 8001
   ```

5. **No Errors in Logs:**
   ```bash
   journalctl -u aitbc-blockchain-node -n 100 --no-pager | grep -i error
   ```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
journalctl -u aitbc-blockchain-node -n 50 --no-pager

# Check configuration
python3 -m aitbc_chain.main --check-config

# Verify environment files
cat /etc/aitbc/blockchain.env
cat /etc/aitbc/node.env
```

### Mempool Endpoint Returns 404

This should not happen with integrated node. If it does:

```bash
# Verify using correct port (8006, not 8082)
curl -s http://localhost:8006/rpc/mempool

# Check if integrated node is running
ps aux | grep aitbc_chain.main
```

### Port Conflicts

```bash
# Find process using port
lsof -i :8006

# Kill conflicting process
kill -9 <PID>
```

## Migration from Standalone

See [Blockchain Node Implementation Guide](../../docs/blockchain/IMPLEMENTATION_GUIDE.md) for detailed migration instructions.

## Related Documentation

- [Integrated Node Setup Guide](../../docs/deployment/INTEGRATED_NODE_SETUP.md)
- [Blockchain Node Implementation Guide](../../docs/blockchain/IMPLEMENTATION_GUIDE.md)
- [Deployment Documentation](../../docs/deployment/)
