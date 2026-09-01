# AITBC Service Ports Reference

**Authoritative single source of truth for live AITBC service ports**

**Last Updated**: 2026-09-01
**Version**: 3.0

---

## Overview

This document lists the ports used by live AITBC services. Other documentation should reference this file instead of duplicating port information. Ports are taken from the current systemd unit files and application source code on `hub.aitbc` and `aitbc3`.

## Public services (nginx-proxied)

External traffic reaches these services through nginx on ports `80`/`443`.

| Service | Local Port | Health | Nginx Path | Notes |
|---------|-----------|--------|------------|-------|
| API Gateway | 8201 | `/health` | `/api/` | Customer-facing API entry point |
| Blockchain RPC | 8202 | `/health` | `/rpc/` | Public chain RPC and follower subscription |
| Coordinator API | 8203 | `/health` | `/c/` | Job/marketplace/escrow failover endpoint |

## Public services (direct access)

These services bind externally and may be reached directly.

| Service | Port | Health | Bind | Notes |
|---------|------|--------|------|-------|
| Blockchain Explorer API | 8100 | `/health` | `0.0.0.0` | Block/transaction search; also proxied at `/explorer-api/` |
| Blockchain P2P (gossip relay) | 7070 | N/A | `0.0.0.0` | Hub-only WebSocket gossip for followers |
| Blockchain Event Bridge | 8205 | `/health` | `127.0.0.1` | Chain event streaming; nginx `/` route if configured |

## Internal services (localhost only)

These bind to `127.0.0.1` and are not exposed directly.

| Service | Port | Health | Notes |
|---------|------|--------|-------|
| GPU Service | 8101 | `/health` | GPU marketplace and hardware registration |
| Marketplace Service | 8102 | `/health` | Marketplace listings and offer matching |
| Trading Service | 8104 | `/health` | Order matching and subscription sync |
| Governance Service | 8105 | `/health` | Proposals and voting |
| Exchange API | 8106 | `/health` | Trading, bridge, deposit/withdraw |
| Agent Coordinator | 8107 | `/health` | Agent messaging and orchestration |
| Wallet Daemon | 8108 | `/health` | Multi-chain wallet daemon |
| Whisper Service | 8110 | `/health` | Whisper transcription (island/shop) |
| Edge Service | 8111 | `/health` | Edge compute and dispatch (island/shop) |
| Pool Hub | 8210 | `/health` | Miner registration/heartbeat and matching |
| FFmpeg Service | 8230 | `/health` | Media processing (island/shop) |

## Services without a listening port

| Service | Notes |
|---------|-------|
| `aitbc-blockchain-node.service` | Runs the chain producer/follower logic; RPC is served by `aitbc-blockchain-rpc.service` on 8202. |
| `aitbc-miner.service` | Polls the coordinator and pool hub for work; does not accept incoming connections. |
| `aitbc-load-secrets.service` | One-shot unit that loads keystore secrets before other services start. |
| `aitbc-backup.service` | One-shot scheduled backup script. |
| `aitbc-recovery.service` | One-shot recovery / systemd link setup. |

## Legacy / not-implemented ports

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| AI Service | 8109 | Not a live service | `apps/ai-engine` is experimental; no systemd unit listens on this port. |
| Inference Service | 8112 | Not implemented | Planned, no service exists. |
| Swarm Service | 8113 | Not implemented | Planned, no service exists. |
| Admin Service | 8114 | Not implemented | Planned, no service exists. |

The historical port migrations (e.g. wallet `8015` → `8108`, exchange `8001` → `8106`) are recorded in the older change logs under `docs/releases/`.

## Configuration sources

- Coordinator API: `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` (`--port 8203`)
- Blockchain RPC: `apps/blockchain-node/aitbc-blockchain-rpc.service` (`RPC_BIND_PORT=8202`)
- Blockchain Explorer: `apps/blockchain-explorer/main.py` (`port=8100`)
- Blockchain P2P: `/etc/aitbc/node.env` (`P2P_BIND_PORT=7070`)
- GPU Service: `apps/gpu/src/gpu_service/main.py` (`GPU_BIND_PORT` default `8101`)
- Marketplace: `apps/marketplace/src/marketplace_service/main.py` (`MARKETPLACE_BIND_PORT` default `8102`)
- Trading: `apps/trading/src/trading_service/main.py` (`TRADING_BIND_PORT` default `8104`)
- Governance: `apps/governance/src/governance_service/main.py` (`GOVERNANCE_PORT` default `8105`)
- Exchange: `apps/exchange/simple_exchange/server.py` (`--port 8106`)
- Agent Coordinator: `apps/agent-coordinator/src/agent_app/main.py` (`--port 8107`)
- Wallet: `apps/wallet/src/wallet_app/settings.py` (`port` default `8108`)
- Whisper: `apps/whisper/aitbc-whisper.service` (`WHISPER_BIND_PORT` default `8110`)
- Edge: `apps/edge/src/aitbc_edge/main.py` (`EDGE_BIND_PORT` default `8111`)
- Pool Hub: `apps/pool-hub/src/poolhub/settings.py` (`bind_port` default `8210`)
- FFmpeg: `apps/ffmpeg/aitbc-ffmpeg.service` (`FFMPEG_PORT` default `8230`)
- Event Bridge: `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge-wrapper.py` (`BIND_PORT=8205`)

## Health check commands

```bash
# Public services via nginx
curl -s https://hub.aitbc.bubuit.net/api/health
curl -s https://hub.aitbc.bubuit.net/rpc/info
curl -s https://hub.aitbc.bubuit.net/c/health

# Direct local checks
curl -s http://localhost:8201/health  # API gateway
curl -s http://localhost:8202/health  # Blockchain RPC
curl -s http://localhost:8203/health  # Coordinator API
curl -s http://localhost:8100/health  # Explorer
curl -s http://localhost:8101/health  # GPU
curl -s http://localhost:8102/health  # Marketplace
curl -s http://localhost:8108/health  # Wallet
curl -s http://localhost:8210/health  # Pool hub
curl -s http://localhost:8230/health  # FFmpeg
```

## Maintenance

1. Update this file when a service port changes.
2. Add the source reference (systemd unit, wrapper, or app source) for the new value.
3. Replace inline port lists in other docs with a link to this file.
