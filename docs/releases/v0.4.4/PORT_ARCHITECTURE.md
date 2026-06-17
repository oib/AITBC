# Port Architecture Reorganization - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 introduces a comprehensive port architecture reorganization to standardize service ports across the platform. This reorganization improves network configuration, simplifies service discovery, and provides a clear separation between public-facing and internal services.

## Port Assignments

### Public Ports (8200-8204)

| Port | Service | Access | Description |
|------|---------|--------|-------------|
| 8200 | Blockchain P2P | Direct | P2P protocol direct access |
| 8201 | API Gateway | Nginx-proxied via /api/ | Public API gateway |
| 8202 | Blockchain RPC | Nginx-proxied via /rpc/ | Blockchain RPC endpoints |
| 8203 | Coordinator API | Nginx-proxied via /c/ | Job coordination API |
| 8204 | Agent Registry | Nginx-proxied via /agent/ | Agent registration service |

### Internal Services (8101-8108)

| Port | Service | Description |
|------|---------|-------------|
| 8101 | GPU Service | Consolidated to monolith (no longer standalone) |
| 8102 | Marketplace Service | Software marketplace |
| 8103 | Hermes Service | Messaging service |
| 8104 | Trading Service | Trading operations |
| 8105 | Governance Service | DAO governance |
| 8106 | Exchange Service | External exchange |
| 8107 | Agent Coordinator | Agent coordination |
| 8108 | Wallet Service | Wallet daemon |

## Port Changes

### Previous → New Port Mappings

| Service | Previous Port | New Port |
|---------|-------------|----------|
| Blockchain RPC | 8006 | 8202 |
| Blockchain P2P | 7070 | 8200 |
| Agent Coordinator | 8011 | 8107 |
| Hermes Service | 8014 | 8103 |

## Migration Impact

### Documentation Updates
- All documentation updated to reference new ports
- SERVICE_PORTS.md updated as authoritative reference
- API documentation updated with new endpoints

### Configuration Updates
- CLI commands updated to use port 8202 for blockchain RPC
- Service configurations updated with new port assignments
- Nginx reverse proxy configuration updated

### Breaking Changes
- Blockchain RPC port changed from 8006 to 8202
- Blockchain P2P port changed from 7070 to 8200
- Agent Coordinator port changed from 8011 to 8107
- Hermes port changed from 8014 to 8103

## Migration Commands

```bash
# Update blockchain RPC URL
sed -i 's/:8006/:8202/g' /etc/aitbc/blockchain.env
sed -i 's/:7070/:8200/g' /etc/aitbc/blockchain.env

# Update service configurations
sed -i 's/:8011/:8107/g' /etc/aitbc/node.env
sed -i 's/:8014/:8103/g' /etc/aitbc/node.env

# Update CLI configuration
aitbc config set blockchain_rpc_url http://localhost:8202
aitbc config set agent_coordinator_url http://localhost:8107
```

## Verification

```bash
# Check blockchain RPC
curl http://localhost:8202/height

# Check Agent Coordinator
curl http://localhost:8107/health

# Check Hermes
curl http://localhost:8103/health

# Check Wallet Daemon
curl http://localhost:8108/v1/wallet/balance
```

## Testing Results

- ✅ Blockchain RPC accessible on port 8202
- ✅ Blockchain P2P accessible on port 8200
- ✅ Agent Coordinator accessible on port 8107
- ✅ Hermes accessible on port 8103
- ✅ All services respond to health checks

## Performance Improvements

- **Standardized ports**: Simplified network configuration
- **Clear separation**: Public vs internal service distinction
- **Easier debugging**: Predictable port assignments

## Documentation

- [SERVICE_PORTS.md](../../../deployment/SERVICE_PORTS.md) — Updated port reference

---

*Last Updated: 2026-06-03*
