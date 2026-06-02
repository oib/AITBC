# AITBC Service Ports Reference

**Authoritative single source of truth for all AITBC service ports**

**Last Updated**: 2026-06-02
**Version**: 2.0

---

## Overview

This document provides the authoritative port configuration for all AITBC services. All other documentation should reference this file rather than duplicating port information.

## Port Architecture

### Public Services with Nginx Reverse Proxy (Recommended)
These services should be accessed through nginx for SSL termination, security headers, and load balancing.

| Service | Port | Health Endpoint | Binding | Nginx Port | Notes |
|---------|------|----------------|---------|------------|-------|
| **API Gateway** | 8201 | `http://localhost:8201/health` | 0.0.0.0 | 80/443 | Single entry point for all external API calls |
| **Agent Registry** | 8204 | `http://localhost:8204/agent/health` | 127.0.0.1 | 80/443 | Agent discovery and management |
| **Blockchain RPC** | 8202 | `http://localhost:8202/health` | 127.0.0.1 | 80/443 | External blockchain node access |
| **Coordinator API** | 8203 | `http://localhost:8203/health` | 127.0.0.1 | 80/443 | Legacy failover service |

**Nginx Configuration**: Services in this group are proxied through nginx on ports 80 (HTTP) and 443 (HTTPS) with SSL termination.

**Nginx Routing Configuration:**
```
/agent/    → localhost:8204 (Agent Registry)
/api/      → localhost:8201 (API Gateway)
/rpc/      → localhost:8202 (Blockchain RPC)
/c/        → localhost:8203 (Coordinator API - failover)
```

**Network Discovery Endpoint:**
- `/rpc/network-info` - Provides network configuration for open island joining
  - Returns P2P endpoint, node ID, chain ID, and connection instructions
  - Accessible via direct port (8202) or nginx proxy (/rpc/)

### Public Services (Direct Access)
These services are accessible directly without nginx proxy (typically P2P protocols).

| Service | Port | Health Endpoint | Binding | Notes |
|---------|------|----------------|---------|-------|
| **Blockchain P2P** | 8200 | N/A | 0.0.0.0 | P2P network communication (direct access required) |

### Internal Services (Ports 8101-8105)
These services bind to localhost only (127.0.0.1) and should not be exposed externally.

| Service | Port | Health Endpoint | Binding | Notes |
|---------|------|----------------|---------|-------|
| **GPU Service** | 8101 | `http://localhost:8101/health` | 127.0.0.1 | GPU marketplace + miner operations |
| **Marketplace Service** | 8102 | `http://localhost:8102/health` | 127.0.0.1 | Marketplace transactions |
| **Trading Service** | 8103 | `http://localhost:8103/health` | 127.0.0.1 | Trading + explorer operations |
| **Governance Service** | 8104 | `http://localhost:8104/health` | 127.0.0.1 | Governance transactions |
| **Hermes Service** | 8105 | `http://localhost:8105/health` | 127.0.0.1 | Agent messaging and orchestration |

## Legacy/Inactive Services

| Service | Port | Health Endpoint | Status | Notes |
|---------|------|----------------|--------|-------|
| **Exchange API** | 8001 | `http://localhost:8001/health` | Inactive | Trading (legacy, not currently running) |
| **Wallet Daemon** | 8015 | `http://localhost:8015/health` | Inactive | Wallet management (not currently running) |
| **Agent Coordinator** | 9001 | N/A | Inactive | Advanced multi-agent coordination (not currently running) |
| **AI Service** | 8106 | N/A | Not implemented | AI operations (planned but not created) |
| **Monitoring Service** | 8107 | N/A | Not implemented | Monitoring (planned but not created) |
| **Plugin Service** | 8108 | N/A | Not implemented | Plugin management (planned but not created) |

## Port Configuration Sources

### Service Wrapper Scripts
- **API Gateway**: `apps/api-gateway/src/api_gateway/main.py` (line 325: `port=8200`)
- **Coordinator API**: `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` (line 32: `--port 8203`)
- **Blockchain P2P**: `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` (uses env var `p2p_bind_port` from blockchain.env)
- **Blockchain RPC**: `apps/blockchain-node/aitbc-blockchain-node-wrapper.py` (uses combined_main with settings.rpc_bind_port)
- **Trading Service**: `apps/trading/aitbc-trading-wrapper.py` (line 36: `--port 8103`)
- **Governance Service**: `apps/governance/aitbc-governance-wrapper.py` (line 36: `--port 8104`)
- **Hermes Service**: `apps/agent-services/aitbc-hermes-wrapper.py` (line 35: `--port 8105`)

### Application Main Files
- **GPU Service**: `apps/gpu/src/gpu_service/main.py` (line 552: `port=8101`)
- **Marketplace Service**: `apps/marketplace/src/marketplace_service/main.py` (line 559: `port=8102`)
- **Trading Service**: `apps/trading/src/main.py` (not used - wrapper script controls port)
- **Governance Service**: `apps/governance/src/main.py` (not used - wrapper script controls port)
- **Wallet**: `apps/wallet/src/app/main.py` (line 42: `port=8015` - inactive)
- **Exchange**: `apps/exchange/multichain_exchange_api.py` (line 537: `port=8001` - inactive)

### Environment Configuration Files
- **Blockchain Configuration**: `/etc/aitbc/blockchain.env` (RPC_BIND_PORT=8202, p2p_bind_port=8201)
- **Node Configuration**: `/etc/aitbc/node.env` (P2P_BIND_PORT=8201)

### CLI Configuration
- **CLI Config**: `cli/aitbc_cli/config.py` (service URLs for all microservices)

## Port Conflict Resolution

### Historical Conflicts (Resolved)
- **Wallet API**: Previously documented as 8003 in SETUP.md, corrected to 8015 (actual port from app/main.py)
- **Coordinator API**: Previously documented as 8000 in SETUP.md, corrected to 8203
- **Blockchain RPC**: Previously on 8006, moved to 8202 as part of public port reorganization
- **Blockchain P2P**: Previously on 8001, moved to 8201 as part of public port reorganization
- **API Gateway**: Previously on 8080, moved to 8200 as part of public port reorganization

### Configuration Notes
- Ports are typically configured in service wrapper scripts or systemd unit files
- Environment variables in `/etc/aitbc/blockchain.env` and `/etc/aitbc/node.env` may override defaults
- Some services support port configuration via environment variables (e.g., `rpc_bind_port`, `p2p_bind_port`)
- Public services (8200-8203) bind to 0.0.0.0 for external access
- Internal services (8101-8105) bind to 127.0.0.1 for security

## Health Check Patterns

### Standard Health Endpoints
Most services follow one of these health endpoint patterns:
- `/health` - Standard health check (Coordinator, Exchange, Blockchain RPC, Marketplace, Wallet)
- `/api/health` - API-specific health check (some Exchange implementations)
- No health endpoint - Services without health checks (P2P, some internal services)

### Health Check Commands
```bash
# Check service health (public services)
curl -s http://localhost:8200/health  # API Gateway
curl -s http://localhost:8202/health  # Blockchain RPC
curl -s http://localhost:8203/health  # Coordinator API (failover)

# Check service health (internal services)
curl -s http://localhost:8101/health  # GPU Service
curl -s http://localhost:8102/health  # Marketplace Service
curl -s http://localhost:8103/health  # Trading Service
curl -s http://localhost:8104/health  # Governance Service
curl -s http://localhost:8105/health  # Hermes Service

# Check if port is listening
netstat -tlnp | grep ':8200'
ss -tlnp | grep ':8101'
```

## CLI Entry Point Reference

### Canonical CLI Entry Point
- **Primary**: `/opt/aitbc/aitbc-cli` (wrapper script that loads unified_cli.py)
- **Alternative**: `python3 cli/unified_cli.py` (direct invocation for specific operations)

### Usage Guidelines
- Use `/opt/aitbc/aitbc-cli` for: general operations, wallet, blockchain, network commands
- Use `python3 cli/unified_cli.py` for: marketplace operations, GPU testing, specific module features

## Related Documentation

- [Setup Guide](../deployment/SETUP.md) - Installation and configuration
- [Basic Operations Skill](../../skills/aitbc/aitbc-basic-operations.md) - CLI and service operations
- [Troubleshooting Skill](../../skills/aitbc/aitbc-blockchain-troubleshooting.md) - Service and connectivity issues

## Maintenance

When adding or modifying services:
1. Update this file with the new port configuration
2. Add source reference (wrapper script, app main.py, or systemd file)
3. Update related documentation to reference this file instead of duplicating port information
4. Add health endpoint pattern if applicable

---

**Last Updated**: 2026-05-28
**Maintained By**: AITBC Documentation Team
