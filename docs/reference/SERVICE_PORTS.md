# AITBC Service Ports Reference

**Authoritative single source of truth for all AITBC service ports**

**Last Updated**: 2026-05-28
**Version**: 1.0

---

## Overview

This document provides the authoritative port configuration for all AITBC services. All other documentation should reference this file rather than duplicating port information.

## Core Services

| Service | Port | Health Endpoint | Source | Notes |
|---------|------|----------------|--------|-------|
| **Blockchain RPC** | 8006 | `http://localhost:8006/health` | `apps/blockchain-node/aitbc-blockchain-rpc-wrapper.py` | Main blockchain node RPC |
| **Blockchain P2P** | 7070 | N/A | `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` | P2P networking |
| **Coordinator API** | 8011 | `http://localhost:8011/health` | `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` | Agent registry, /v1/* routes |
| **Exchange API** | 8001 | `http://localhost:8001/health` | `apps/exchange/multichain_exchange_api.py` | Trading (localhost only) |
| **Marketplace Enhanced** | 8014 | `http://localhost:8014/health` | `apps/marketplace-service/src/marketplace_service/main.py` | GPU marketplace |
| **Wallet Daemon** | 8015 | `http://localhost:8015/health` | `apps/wallet/src/app/main.py` | Wallet management (localhost only) |

## Additional Services

| Service | Port | Health Endpoint | Source | Notes |
|---------|------|----------------|--------|-------|
| **AI Service** | 8005 | N/A | `systemd/aitbc-ai.service` | AI operations |
| **Learning Service** | 8013 | N/A | `systemd/aitbc-learning.service` | Adaptive learning |
| **Multimodal Service** | 8010 | N/A | `systemd/aitbc-multimodal.service` | Multimodal processing (CPU-only) |
| **Modality Optimization** | 8012 | N/A | `systemd/aitbc-modality-optimization.service` | Optimization service |
| **Blockchain Event Bridge** | 8204 | N/A | `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge-wrapper.py` | Event bridging |

## Port Configuration Sources

### Service Wrapper Scripts
- **Coordinator API**: `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` (line 32: `--port 8011`)
- **Wallet**: `apps/wallet/aitbc-wallet-wrapper.py` (delegates to `apps/wallet/src/app/main.py`)
- **Blockchain RPC**: `apps/blockchain-node/aitbc-blockchain-rpc-wrapper.py` (line 29: `--port 8006`)
- **Blockchain P2P**: `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` (line 26: `--port 7000`)

### Application Main Files
- **Wallet**: `apps/wallet/src/app/main.py` (line 42: `port=8015`)
- **Marketplace**: `apps/marketplace-service/src/marketplace_service/main.py` (line 558: `port=8014`)
- **Exchange**: `apps/exchange/multichain_exchange_api.py` (line 537: `port=8001`)

### Systemd Service Files
- **AI Service**: `systemd/aitbc-ai.service` (line 13: `--port 8005`)
- **Learning Service**: `systemd/aitbc-learning.service` (line 14: `--port 8013`)
- **Multimodal Service**: `systemd/aitbc-multimodal.service` (line 15: `--port 8010`)
- **Modality Optimization**: `systemd/aitbc-modality-optimization.service` (line 15: `--port 8012`)
- **Exchange API**: `systemd/aitbc-exchange-api.service` (line 14: `--port 8001`)

## Port Conflict Resolution

### Historical Conflicts (Resolved)
- **Wallet API**: Previously documented as 8003 in SETUP.md, corrected to 8015 (actual port from app/main.py)
- **Coordinator API**: Previously documented as 8000 in SETUP.md, corrected to 8011 (actual port from wrapper script)

### Configuration Notes
- Ports are typically configured in service wrapper scripts or systemd unit files
- Environment variables in `/etc/aitbc/blockchain.env` and `/etc/aitbc/node.env` may override defaults
- Some services support port configuration via environment variables (e.g., `rpc_bind_port`, `p2p_bind_port`)

## Health Check Patterns

### Standard Health Endpoints
Most services follow one of these health endpoint patterns:
- `/health` - Standard health check (Coordinator, Exchange, Blockchain RPC, Marketplace, Wallet)
- `/api/health` - API-specific health check (some Exchange implementations)
- No health endpoint - Services without health checks (P2P, some internal services)

### Health Check Commands
```bash
# Check service health
curl -s http://localhost:8006/health  # Blockchain RPC
curl -s http://localhost:8011/health  # Coordinator API
curl -s http://localhost:8001/health  # Exchange API
curl -s http://localhost:8014/health  # Marketplace Enhanced
curl -s http://localhost:8015/health  # Wallet Daemon

# Check if port is listening
netstat -tlnp | grep ':8006'
ss -tlnp | grep ':8011'
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
