# AITBC Remote Deployment Guide

## Overview
This deployment strategy builds the blockchain node directly on the ns3 server to utilize its gigabit connection, avoiding slow uploads from localhost.

## Quick Start

### 1. Deploy Everything
```bash
./scripts/deploy/deploy-all-remote.sh
```

This will:
- Copy deployment scripts to ns3
- Copy blockchain source code from localhost
- Build blockchain node directly on server
- Deploy a lightweight HTML-based explorer
- Configure port forwarding

### 2. Access Services

**Blockchain Node RPC:**
- Internal: http://localhost:8082
- External: http://aitbc.keisanki.net:8082

**Blockchain Explorer:**
- Internal: http://localhost:3000
- External: http://aitbc.keisanki.net:3000

## Architecture

```
ns3-root (95.216.198.140)
├── Blockchain Node (port 8082)
│   ├── Auto-syncs on startup
│   └── Serves RPC API
└── Explorer (port 3000)
    ├── Static HTML/CSS/JS
    ├── Served by nginx
    └── Connects to local node
```

## Key Features

### Blockchain Node
- Built directly on server from source code
- Source copied from localhost via scp
- Auto-sync on startup
- No large file uploads needed
- Uses server's gigabit connection

### Explorer
- Pure HTML/CSS/JS (no build step)
- Served by nginx
- Real-time block viewing
- Transaction details
- Auto-refresh every 30 seconds

## Manual Deployment

If you need to deploy components separately:

### Blockchain Node Only
```bash
ssh ns3-root
cd /opt
./deploy-blockchain-remote.sh
```

### Explorer Only
```bash
ssh ns3-root
cd /opt
./deploy-explorer-remote.sh
```

## Troubleshooting

### Check Services
```bash
# On ns3 server
systemctl status blockchain-node blockchain-rpc nginx

# Check logs
journalctl -u blockchain-node -f
journalctl -u blockchain-rpc -f
journalctl -u nginx -f
```

### Test RPC
```bash
# From ns3
curl http://localhost:8082/rpc/head

# From external
curl http://aitbc.keisanki.net:8082/rpc/head
```

### Port Forwarding
If port forwarding doesn't work:
```bash
# Check iptables rules
iptables -t nat -L -n

# Re-add rules
iptables -t nat -A PREROUTING -p tcp --dport 8082 -j DNAT --to-destination 192.168.100.10:8082
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 8082 -j MASQUERADE
```

## Configuration

### Blockchain Node
Location: `/opt/blockchain-node/.env`
- Chain ID: ait-devnet
- RPC Port: 8082
- P2P Port: 7070
- Auto-sync: enabled

### Explorer
Location: `/opt/blockchain-explorer/index.html`
- Served by nginx on port 3000
- Connects to localhost:8082
- No configuration needed

## Security Notes

- Services run as root (simplify for dev)
- No authentication on RPC (dev only)
- Port forwarding exposes services externally
- Consider firewall rules for production

## Next Steps

1. Set up proper authentication
2. Configure HTTPS with SSL certificates
3. Add multiple peers for network resilience
4. Implement proper backup procedures
5. Set up monitoring and alerting
