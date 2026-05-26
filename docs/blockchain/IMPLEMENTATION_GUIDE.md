# Blockchain Node Implementation Guide

## Overview

AITBC has two blockchain node implementations with different capabilities and deployment scenarios.

## Implementations

### 1. Integrated Blockchain Node (`/opt/aitbc/apps/blockchain-node`)

**Location:** `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/`

**Used By:** aitbc (localhost), aitbc1

**Features:**
- ✅ Full RPC API including mempool endpoint
- ✅ Integrated with AITBC monorepo
- ✅ Multi-chain support
- ✅ PostgreSQL mempool backend
- ✅ Gossip relay
- ✅ WebSocket support
- ✅ Comprehensive monitoring

**RPC Endpoints:**
- `GET /rpc/head` - Get latest block
- `GET /rpc/mempool` - Get mempool status ✅ **AVAILABLE**
- `GET /rpc/block/{height}` - Get specific block
- `POST /rpc/broadcast_tx_commit` - Submit transaction

**Configuration:**
- Environment file: `/etc/aitbc/blockchain.env`
- Port: 8006
- Database: PostgreSQL (chain-specific)

**Deployment:**
- Managed via systemd: `aitbc-blockchain-node.service`
- Part of main AITBC repository
- Updated via git pull

### 2. Standalone Blockchain Node (`/opt/blockchain-node`)

**Location:** `/opt/blockchain-node/src/aitbc_chain/`

**Used By:** ns3 container (hub.aitbc.bubuit.net)

**Features:**
- ✅ Basic RPC API
- ❌ **Missing mempool endpoint**
- ✅ Lightweight deployment
- ✅ Container-friendly
- ⚠️ Limited feature set compared to integrated version

**RPC Endpoints:**
- `GET /rpc/head` - Get latest block ✅
- `GET /rpc/mempool` - Get mempool status ❌ **NOT IMPLEMENTED**
- `GET /rpc/block/{height}` - Get specific block ✅

**Configuration:**
- Environment file: `/etc/aitbc/blockchain.env`
- Port: 8082
- Database: SQLite (default)

**Deployment:**
- Managed via systemd: `aitbc-blockchain-node-3.service`
- Standalone package (not in main repo)
- Requires manual updates

## Key Differences

| Feature | Integrated | Standalone |
|---------|-----------|------------|
| Mempool Endpoint | ✅ Available | ❌ Missing |
| Repository | Main monorepo | Standalone package |
| Port | 8006 | 8082 |
| Database | PostgreSQL | SQLite |
| Updates | Git pull | Manual |
| Multi-chain | ✅ Yes | ⚠️ Limited |
| WebSocket | ✅ Yes | ❌ No |
| Gossip Relay | ✅ Yes | ⚠️ Basic |

## Deployment Recommendations

### For Production Nodes (aitbc, aitbc1, etc.)
**Use:** Integrated Blockchain Node

**Reason:**
- Full feature set including mempool endpoint
- Integrated with main codebase
- Easier maintenance and updates
- Better monitoring and observability

**Setup:**
```bash
# Clone main repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Run setup script
sudo ./scripts/setup.sh

# Start service
sudo systemctl start aitbc-blockchain-node
```

### For Container Deployments (ns3, hub nodes)
**Use:** Standalone Blockchain Node (with limitations)

**Reason:**
- Lightweight and container-friendly
- Simplified deployment
- Suitable for hub nodes that don't need full mempool functionality

**Limitations:**
- No mempool RPC endpoint
- Manual updates required
- Limited feature set

**Setup:**
```bash
# Deploy standalone package
# (deployment script specific to container environment)
```

## Mempool Endpoint Status

### Working Endpoints
- **aitbc (localhost):** `http://localhost:8006/rpc/mempool` ✅
- **aitbc1:** `http://localhost:8006/rpc/mempool` ✅

### Non-Working Endpoints
- **ns3 container:** `http://localhost:8082/rpc/mempool` ❌ (404 Not Found)

### Response Format (Integrated Node Only)
```json
{
  "success": true,
  "transactions": [],
  "count": 0
}
```

## Troubleshooting

### Mempool Endpoint Returns 404

**If using standalone blockchain node:**
1. This is expected behavior - the endpoint is not implemented
2. Consider migrating to integrated blockchain node if mempool access is needed
3. Update cross-site sync code to handle missing endpoint gracefully

**If using integrated blockchain node:**
1. Check service status: `systemctl status aitbc-blockchain-node`
2. Verify port: Should be 8006, not 8082
3. Check logs: `journalctl -u aitbc-blockchain-node -f`

### Port Conflicts

- **Integrated node:** Uses port 8006
- **Standalone node:** Uses port 8082
- Ensure no port conflicts when running both implementations

## Migration Guide

### From Standalone to Integrated

1. **Stop standalone node:**
```bash
sudo systemctl stop aitbc-blockchain-node-3
sudo systemctl disable aitbc-blockchain-node-3
```

2. **Clone main repository:**
```bash
sudo git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
```

3. **Run setup:**
```bash
sudo ./scripts/setup.sh
```

4. **Configure environment:**
```bash
sudo cp /etc/aitbc/blockchain.env.backup /etc/aitbc/blockchain.env
# Update configuration as needed
```

5. **Start integrated node:**
```bash
sudo systemctl start aitbc-blockchain-node
sudo systemctl enable aitbc-blockchain-node
```

6. **Verify mempool endpoint:**
```bash
curl http://localhost:8006/rpc/mempool
```

## Future Work

- [ ] Implement mempool endpoint in standalone blockchain node
- [ ] Unify implementations to reduce maintenance burden
- [ ] Update setup documentation to clarify which implementation to use
- [ ] Add feature matrix to API documentation
- [ ] Implement graceful fallback for missing mempool endpoint in cross-site sync
