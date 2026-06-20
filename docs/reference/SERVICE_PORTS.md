# AITBC Service Ports Reference

**Authoritative single source of truth for all AITBC service ports**

**Last Updated**: 2026-06-07
**Version**: 2.1

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
  - Returns RPC endpoint, node ID, chain ID, and subscription instructions
  - Accessible via direct port (8202) or nginx proxy (/rpc/)

**Follower Block Subscription (WebSocket via nginx):**
- `wss://hub.aitbc.bubuit.net/rpc/subscribe/ws` - Real-time block push to followers
- `POST /rpc/subscribe` - Register subscription lease
- `POST /rpc/heartbeat` - Extend subscription lease
- Nginx routes `/rpc/subscribe/ws`, `/rpc/blocks`, `/rpc/transactions` with WebSocket upgrade headers

### Public Services (Direct Access)
These services are accessible directly without nginx proxy.

| Service | Port | Health Endpoint | Binding | Notes |
|---------|------|----------------|---------|-------|
| **Blockchain P2P (Gossip Relay)** | 7070 | N/A | 0.0.0.0 | Hub-only internal gossip relay (WebSocket). Followers do not connect to this port — they use the lease-based subscription system via the hub's RPC endpoint. |
| **Blockchain Event Bridge** | 8205 | `http://localhost:8205/health` | 0.0.0.0 | Blockchain event streaming service |

### Internal Services (Ports 8101-8105)
These services bind to localhost only (127.0.0.1) and should not be exposed externally.

| Service | Port | Health Endpoint | Binding | Notes |
|---------|------|----------------|---------|-------|
| **GPU Service** | 8101 | `http://localhost:8101/health` | 127.0.0.1 | GPU marketplace + miner operations |
| **Marketplace Service** | 8102 | `http://localhost:8102/health` | 127.0.0.1 | Marketplace transactions |
| **Hermes Service** | 8103 | `http://localhost:8103/health` | 127.0.0.1 | Agent messaging and orchestration |
| **Trading Service** | 8104 | `http://localhost:8104/health` | 127.0.0.1 | Trading + explorer operations |
| **Governance Service** | 8105 | `http://localhost:8105/health` | 127.0.0.1 | Governance transactions |

## Legacy/Inactive Services

| Service | Port | Health Endpoint | Status | Notes |
|---------|------|----------------|--------|-------|
| **Exchange API** | 8106 | `http://localhost:8106/health` | Migrated | Trading (migrated from 8001 to 8106) |
| **Agent Coordinator** | 8107 | `http://localhost:8107/health` | Migrated | Advanced multi-agent coordination (migrated from 9001 to 8107) |
| **Wallet Daemon** | 8108 | `http://localhost:8108/health` | Migrated | Wallet management (migrated from 8015 to 8108) |
| **AI Service** | 8109 | `http://localhost:8109/health` | 127.0.0.1 | AI operations (plugin service) |
| **Whisper Service** | 8110 | `http://localhost:8110/health` | 127.0.0.1 | Transcription service |
| **Edge Service** | 8111 | `http://localhost:8111/health` | 0.0.0.0 | Edge API service |
| **Inference Service** | 8112 | N/A | Not implemented | Model inference (planned but not created) |
| **Swarm Service** | 8113 | N/A | Not implemented | Compute clustering (planned but not created) |
| **Admin Service** | 8114 | N/A | Not implemented | Admin/debug endpoints (planned but not created) |

## Port Configuration Sources

### Service Wrapper Scripts
- **API Gateway**: `apps/api-gateway/src/api_gateway/main.py` (line 325: `port=8201`)
- **Coordinator API**: `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` (line 32: `--port 8203`)
- **Blockchain P2P**: `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` (uses env var `p2p_bind_port` from blockchain.env)
- **Blockchain RPC**: `apps/blockchain-node/aitbc-blockchain-node-wrapper.py` (uses combined_main with settings.rpc_bind_port)
- **Blockchain Event Bridge**: `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge-wrapper.py` (line 31: `--port 8205`)
- **Hermes Service**: `apps/hermes/aitbc-hermes-wrapper.py` (line 33: `--port 8103`)
- **Trading Service**: `apps/trading/aitbc-trading-wrapper.py` (line 32: `--port 8104`)
- **Governance Service**: `apps/governance/src/governance_service/main.py` (line 286: `port=8105`)
- **Exchange API**: `apps/exchange/aitbc-exchange-api.service` (line 14: `--port 8106`)
- **Agent Coordinator**: `apps/agent-coordinator/aitbc-agent-coordinator-wrapper.py` (line 38: `--port 8107`)
- **Wallet Daemon**: `apps/wallet/aitbc-wallet-wrapper.py` (line 33: `--port 8108`)
- **Plugin Service**: `apps/plugin-service/src/plugin_service/main.py` (line 286: `port=8109`)
- **Whisper Service**: `apps/whisper/aitbc-whisper.service` (line 15: `--port 8110`)
- **Edge Service**: `apps/edge/aitbc-edge.service` (line 16: `API_PORT=8111`)

### Application Main Files
- **GPU Service**: `apps/gpu-service/src/gpu_service/main.py` (line 458: `port=8101`)
- **Marketplace Service**: `apps/marketplace-service/src/marketplace_service/main.py` (line 559: `port=8102`)
- **Hermes Service**: `apps/hermes/aitbc-hermes-wrapper.py` (line 33: `--port 8103`)
- **Trading Service**: `apps/trading/aitbc-trading-wrapper.py` (line 32: `--port 8104`)
- **Governance Service**: `apps/governance/src/governance_service/main.py` (line 286: `port=8105`)
- **Wallet**: `apps/wallet/src/app/main.py` (line 42: `port=8108`)
- **Exchange**: `apps/exchange/aitbc-exchange-api.service` (line 14: `--port 8106`)
- **Agent Coordinator**: `apps/agent-coordinator/aitbc-agent-coordinator-wrapper.py` (line 38: `--port 8107`)
- **Plugin Service**: `apps/plugin-service/src/plugin_service/main.py` (line 286: `port=8109`)
- **Whisper Service**: `apps/whisper/main.py` (line 42: `port=8110`)
- **Edge Service**: `apps/edge/src/aitbc_edge/main.py` (line 42: `port=8111`)

### Environment Configuration Files
- **Blockchain Configuration**: `/etc/aitbc/blockchain.env` (rpc_bind_port=8202, default_peer_rpc_url for followers)
- **Node Configuration**: `/etc/aitbc/node.env` (P2P_BIND_PORT=7070 for hub gossip relay)

### CLI Configuration
- **CLI Config**: `cli/aitbc_cli/config.py` (service URLs for all microservices)

## Port Conflict Resolution

### Historical Conflicts (Resolved)
- **Wallet API**: Previously documented as 8003 in SETUP.md, corrected to 8015 (actual port from app/main.py)
- **Coordinator API**: Previously documented as 8000 in SETUP.md, corrected to 8203
- **Blockchain RPC**: Previously on 8006, moved to 8202 as part of public port reorganization
- **Blockchain P2P**: Previously on 8001, now on 7070 (gossip relay, hub-only)
- **API Gateway**: Previously on 8080, moved to 8201 as part of public port reorganization
- **Miner Coordinator**: Previously using legacy port 8011, updated to 8203 (current coordinator port)
- **Edge Service**: Previously on 8110 (conflict with whisper), moved to 8111
- **Blockchain Event Bridge**: Previously on 8204 (conflict with coordinator), moved to 8205

### Configuration Notes
- Ports are typically configured in service wrapper scripts or systemd unit files
- Environment variables in `/etc/aitbc/blockchain.env` and `/etc/aitbc/node.env` may override defaults
- Some services support port configuration via environment variables (e.g., `rpc_bind_port`, `p2p_bind_port`)
- Public services (8201-8205) bind to 127.0.0.0.0 for external access via nginx
- P2P gossip relay (7070) binds to 0.0.0.0 (hub-only, direct access)
- Internal services (8101-8110) bind to 127.0.0.1 for security

## Health Check Patterns

### Standard Health Endpoints
Most services follow one of these health endpoint patterns:
- `/health` - Standard health check (Coordinator, Exchange, Blockchain RPC, Marketplace, Wallet)
- `/api/health` - API-specific health check (some Exchange implementations)
- No health endpoint - Services without health checks (P2P, some internal services)

### Health Check Commands
```bash
# Check service health (public services)
curl -s http://localhost:8201/health  # API Gateway
curl -s http://localhost:8202/health  # Blockchain RPC
curl -s http://localhost:8203/health  # Coordinator API (failover)

# Check service health (internal services)
curl -s http://localhost:8101/health  # GPU Service
curl -s http://localhost:8102/health  # Marketplace Service
curl -s http://localhost:8103/health  # Hermes Service
curl -s http://localhost:8104/health  # Trading Service
curl -s http://localhost:8105/health  # Governance Service
curl -s http://localhost:8106/health  # Exchange API
curl -s http://localhost:8107/health  # Agent Coordinator
curl -s http://localhost:8108/health  # Wallet Daemon
curl -s http://localhost:8109/health  # Plugin Service
curl -s http://localhost:8110/health  # Whisper Service
curl -s http://localhost:8111/health  # Edge Service
curl -s http://localhost:8205/health  # Blockchain Event Bridge

# Check if port is listening
netstat -tlnp | grep ':8200'  # Blockchain P2P
netstat -tlnp | grep ':8201'  # API Gateway
ss -tlnp | grep ':8101'     # GPU Service
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

**Last Updated**: 2026-06-02
**Maintained By**: AITBC Documentation Team

## Port Migration History

### 2026-06-02 Migration
- **Exchange API**: 8001 → 8106 (migrated to 8100+ range)
- **Agent Coordinator**: 9001 → 8107 (migrated to 8100+ range)
- **Wallet Daemon**: 8015 → 8108 (migrated to 8100+ range)
- **Trading Service**: 8103 → 8104 (corrected based on codemap validation)
- **Governance Service**: 8104 → 8105 (corrected based on codemap validation)
- **Hermes Service**: 8105 → 8103 (corrected based on codemap validation)
