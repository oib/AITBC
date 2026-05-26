# Integrated Blockchain Node Setup Guide

## Overview

This guide explains how to deploy the integrated blockchain node (with full mempool support) from scratch on any host or container. This is the recommended approach for production deployments.

## Quick Start

### Automated Setup

```bash
# Run the deployment script
sudo bash /opt/aitbc/scripts/deployment/deploy-integrated-blockchain-node.sh
```

### Manual Setup

See the step-by-step instructions below.

## Prerequisites

- **OS**: Debian 12+ or Ubuntu 22.04+
- **Python**: 3.13+
- **Git**: For cloning repository
- **Systemd**: For service management
- **PostgreSQL**: Optional, for mempool backend (can use SQLite)

## Step-by-Step Setup

### 1. Clone Repository

```bash
sudo git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
```

### 2. Setup Python Environment

```bash
# Create virtual environment
sudo python3 -m venv /opt/aitbc/venv

# Activate and install dependencies
sudo /opt/aitbc/venv/bin/pip install -r apps/blockchain-node/requirements.txt
```

### 3. Create Runtime Directories

```bash
sudo mkdir -p /var/lib/aitbc/keystore
sudo mkdir -p /var/lib/aitbc/data
sudo mkdir -p /var/lib/aitbc/logs
sudo mkdir -p /etc/aitbc

# Set permissions
sudo chmod 700 /var/lib/aitbc/keystore
sudo chmod 755 /var/lib/aitbc/data
sudo chmod 755 /var/lib/aitbc/logs
sudo chmod 755 /etc/aitbc
```

### 4. Create Environment Files

**Blockchain Configuration (`/etc/aitbc/blockchain.env`):**
```bash
sudo nano /etc/aitbc/blockchain.env
```

```env
# Blockchain Node Configuration
CHAIN_ID=ait-mainnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=8001
ENABLE_BLOCK_PRODUCTION=false
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
CROSS_SITE_REMOTE_ENDPOINTS=
```

**Node Configuration (`/etc/aitbc/node.env`):**
```bash
sudo nano /etc/aitbc/node.env
```

```env
# Node Configuration
NODE_ID=$(hostname)
ISLAND_ID=default-island
CHAIN_ID=ait-mainnet
NODE_ROLE=follower
P2P_BIND_PORT=8001
```

### 5. Setup Systemd Service

```bash
sudo nano /etc/systemd/system/aitbc-blockchain-node.service
```

```ini
[Unit]
Description=AITBC Production Blockchain Node
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
Environment="PATH=/opt/aitbc/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=/etc/aitbc/blockchain.env
EnvironmentFile=/etc/aitbc/node.env
ExecStartPre=/opt/aitbc/scripts/utils/load-keystore-secrets.sh
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6. Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable aitbc-blockchain-node

# Start service
sudo systemctl start aitbc-blockchain-node
```

### 7. Verify Deployment

```bash
# Check service status
sudo systemctl status aitbc-blockchain-node

# Check RPC endpoint
curl http://localhost:8006/rpc/head

# Check mempool endpoint
curl http://localhost:8006/rpc/mempool
```

## Container Deployment

### For incus Containers

```bash
# Create container
incus launch ubuntu:22.04 aitbc-container

# Push repository to container
incus file push -r /opt/aitbc aitbc-container/opt/

# Run setup inside container
incus exec aitbc-container -- bash /opt/aitbc/scripts/deployment/deploy-integrated-blockchain-node.sh
```

### For Docker

```bash
# Build image
docker build -t aitbc-blockchain-node -f docker/blockchain/Dockerfile .

# Run container
docker run -d \
  --name aitbc-blockchain \
  -p 8006:8006 \
  -p 8001:8001 \
  -v /var/lib/aitbc:/var/lib/aitbc \
  -v /etc/aitbc:/etc/aitbc \
  aitbc-blockchain-node
```

## Configuration

### Enable Block Production

Edit `/etc/aitbc/blockchain.env`:
```env
ENABLE_BLOCK_PRODUCTION=true
```

Then restart:
```bash
sudo systemctl restart aitbc-blockchain-node
```

### Configure Mempool Backend

**PostgreSQL (Recommended):**
```env
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool
```

**SQLite (Default):**
```env
MEMPOOL_BACKEND=database
```

### Configure Cross-Site Sync

```env
CROSS_SITE_REMOTE_ENDPOINTS=https://aitbc.bubuit.net/rpc,https://aitbc1.bubuit.net/rpc
```

## Management

### Service Management

```bash
# Status
sudo systemctl status aitbc-blockchain-node

# Restart
sudo systemctl restart aitbc-blockchain-node

# Stop
sudo systemctl stop aitbc-blockchain-node

# Logs
sudo journalctl -u aitbc-blockchain-node -f
```

### Update Node

```bash
cd /opt/aitbc
sudo git pull origin main
sudo systemctl restart aitbc-blockchain-node
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u aitbc-blockchain-node -n 50 --no-pager

# Check configuration
sudo /opt/aitbc/venv/bin/python -m aitbc_chain.main --check-config
```

### Port Already in Use

```bash
# Find process using port
sudo lsof -i :8006

# Kill process
sudo kill -9 <PID>
```

### Mempool Endpoint Not Working

```bash
# Check if mempool backend is configured
grep MEMPOOL_BACKEND /etc/aitbc/blockchain.env

# Verify database connection
sudo -u postgres psql -d aitbc_mempool -c "SELECT 1"
```

## Migration from Standalone Node

See [Blockchain Node Implementation Guide](../blockchain/IMPLEMENTATION_GUIDE.md) for detailed migration instructions.

## Agent Deployment

For automated deployment using hermes agents, see the agent workflow in [/.windsurf/workflows/](/.windsurf/workflows/).

## Verification Checklist

- [ ] Service is running: `systemctl is-active aitbc-blockchain-node`
- [ ] RPC endpoint accessible: `curl http://localhost:8006/rpc/head`
- [ ] Mempool endpoint accessible: `curl http://localhost:8006/rpc/mempool`
- [ ] P2P listening on port 8001
- [ ] No errors in logs: `journalctl -u aitbc-blockchain-node -n 100`
- [ ] Configuration files exist: `/etc/aitbc/blockchain.env`, `/etc/aitbc/node.env`
- [ ] Runtime directories exist: `/var/lib/aitbc/keystore`, `/var/lib/aitbc/data`, `/var/lib/aitbc/logs`

## Support

For issues or questions:
- Check logs: `sudo journalctl -u aitbc-blockchain-node -f`
- Review configuration: `/etc/aitbc/blockchain.env`
- See [Implementation Guide](../blockchain/IMPLEMENTATION_GUIDE.md)
