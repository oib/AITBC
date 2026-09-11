# AITBC Service Ports Reference

**Authoritative single source of truth for live AITBC service ports**

**Last Updated**: 2026-09-11
**Version**: 3.3

---

## Overview

This document lists the ports used by live AITBC services. Other documentation should reference this file instead of duplicating port information. Ports are taken from the current systemd unit files and application source code on `<hub-node>` and `<node2>`.

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
| Blockchain Explorer API | 8100 | `/health` | `127.0.0.1` | Block/transaction search; proxied at `/explorer-api/`. Pinned via `EXPLORER_BIND_HOST`; set it to the private interface address where nginx runs on another host |
| Blockchain P2P (gossip relay) | 7070 | N/A | `0.0.0.0` | Hub-only WebSocket gossip for followers |
| Blockchain Event Bridge | 8205 | `/health` | `127.0.0.1` | Chain event streaming; nginx `/` route if configured |

## Internal services (not nginx-proxied)

These serve internal callers only. AITBC runs no host firewall, so the bind
address is the entire access control -- see
[Port exposure policy](../deployment/DEPENDENCIES.md#port-exposure-policy).

The **Bind** column is the address the service actually comes up on with the
repo's systemd unit and code defaults. Most of these default to `0.0.0.0`, which
means they are reachable from anywhere that can route to the host. Units loading
`EnvironmentFile=/etc/aitbc/*.env` may be overridden on the live hosts; those
files are not in this repo, so the values below are the repo default, not a
confirmed live reading. Verify with the `ss` command in the exposure policy.

| Service | Port | Health | Bind | Notes |
|---------|------|--------|------|-------|
| GPU Service | 8101 | `/health` | `127.0.0.1` | Pinned in unit via `GPU_BIND_HOST` |
| Marketplace Service | 8102 | `/health` | `127.0.0.1` | Pinned in unit via `MARKETPLACE_BIND_HOST` |
| Trading Service | 8104 | `/health` | `127.0.0.1` | Pinned in unit via `TRADING_BIND_HOST` |
| Governance Service | 8105 | `/health` | `127.0.0.1` | Pinned in unit via `GOVERNANCE_BIND_HOST` |
| Exchange API | 8106 | `/health` | `127.0.0.1` | Pinned in unit via `--host` |
| Agent Coordinator | 8107 | `/health` | `127.0.0.1` | Pinned in unit via `AGENT_COORDINATOR_BIND_HOST` |
| Wallet Daemon | 8108 | `/health` | `127.0.0.1` | Code default was already loopback (`settings.py`); now pinned in unit via `WALLET_BIND_HOST` |
| Whisper Service | 8110 | `/health` | `127.0.0.1` | Pinned in unit via `WHISPER_BIND_HOST` |
| Edge Service | 8111 | `/health` | `127.0.0.1` | Edge compute and dispatch (island/shop). Pinned in unit via `APP_HOST`; peers reach it via `EDGE_ADVERTISE_HOST` |
| Pool Hub | 8210 | `/health` | `127.0.0.1` | Pinned in unit via `--host` |
| FFmpeg Service | 8230 | `/health` | `127.0.0.1` | Pinned in unit via `FFMPEG_BIND_HOST` |

As of 2026-09-11 every service in this table pins its bind explicitly in its
systemd unit rather than relying on an application default. See
[Network Policy](../deployment/NETWORK_POLICY.md) for the rule and the drift
gate that holds it.

## Internal support services

These have systemd units and listen, but were absent from this reference until
2026-09-11. The `apps/ai-engine` and monitoring units pin `--host 127.0.0.1`
directly in their `ExecStart`; Hermes Agent now pins `HERMES_BIND_HOST` the same
way the internal tier does.

| Service | Port | Bind | Unit | Notes |
|---------|------|------|------|-------|
| Monitoring Service | 8002 | `127.0.0.1` | `aitbc-monitoring.service` | Metrics collection |
| AI Engine | 8005 | `127.0.0.1` | `aitbc-ai.service` | `apps/ai-engine`; experimental |
| Adaptive Learning | 8012 | `127.0.0.1` | `aitbc-learning.service` | `apps/ai-engine` |
| Multi-Modal Agent | 8020 | `127.0.0.1` | `aitbc-multimodal.service` | `apps/ai-engine` |
| Modality Optimization | 8021 | `127.0.0.1` | `aitbc-modality-optimization.service` | `apps/ai-engine` |
| Hermes Agent | 8270 | `127.0.0.1` | `aitbc-hermes-agent.service` | Pinned in unit via `HERMES_BIND_HOST` |

### Island IPFS daemon

`aitbc-island-ipfs.service` runs a private-swarm IPFS daemon with three ports:

| Purpose | Port | Bind | Env var |
|---------|------|------|---------|
| IPFS API | 5002 | `127.0.0.1` | `ISLAND_IPFS_API_PORT` |
| IPFS Gateway | 8081 | `127.0.0.1` | `ISLAND_IPFS_GATEWAY_PORT` |
| IPFS Swarm | 4002 | `0.0.0.0` | `ISLAND_IPFS_SWARM_PORT` |

The daemon writes these into the IPFS config itself
(`apps/ipfs/island_ipfs_daemon.py`). Swarm binds all interfaces by design -- it
needs inbound peers.

**TCP only, despite what the config says.** The daemon writes QUIC entries into
`Addresses.Swarm` and runs with `IPFS_FORCE_PNET=1`, but Kubo does not support
QUIC on a private network: it drops those transports without an error, so
nothing ever binds UDP 4002. `ipfs swarm addrs listen` shows only
`/ip4/<addr>/tcp/4002`. Do not announce a `udp/.../quic-v1` address for an
island node and do not open UDP 4002 on a perimeter -- there is nothing behind
it. The QUIC entries are left in place so they take effect if the private
network is ever lifted.

Binding `0.0.0.0` is not enough on its own. A node behind NAT or a container
port-forward only sees its own private address, so with `Addresses.Announce`
empty it advertises an address no outside peer can dial. Set
`ISLAND_IPFS_ANNOUNCE` to the multiaddr peers actually reach, and
`ISLAND_IPFS_BOOTSTRAP` to the peers this node should dial -- both accept a
comma-separated list, and both belong in `/etc/aitbc/aitbc-island-ipfs.env`
rather than in the unit, since the value is per host:

```
ISLAND_IPFS_ANNOUNCE=/ip4/<public-ip>/tcp/4002
ISLAND_IPFS_BOOTSTRAP=/ip4/<peer-public-ip>/tcp/4002/p2p/<peer-id>
```

Leave both empty for a node whose swarm address is already directly reachable.

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
| AI Service | 8109 | Not a live service | Nothing listens on 8109. `apps/ai-engine` does run units, on 8005/8012/8020/8021 -- see Internal support services above. |
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
- Monitoring: `apps/monitoring-service/aitbc-monitoring.service` (`--host 127.0.0.1 --port 8002`)
- AI Engine: `apps/ai-engine/aitbc-ai.service` (`--host 127.0.0.1 --port 8005`)
- Adaptive Learning: `apps/ai-engine/aitbc-learning.service` (`--host 127.0.0.1 --port 8012`)
- Multi-Modal Agent: `apps/ai-engine/aitbc-multimodal.service` (`--host 127.0.0.1 --port 8020`)
- Modality Optimization: `apps/ai-engine/aitbc-modality-optimization.service` (`--host 127.0.0.1 --port 8021`)
- Hermes Agent: `apps/hermes_agent/aitbc-hermes-agent.service` (`HERMES_PORT=8270`); bind from `apps/hermes_agent/main.py` (`HERMES_BIND_HOST` default `0.0.0.0`)
- Island IPFS: `apps/ipfs/aitbc-island-ipfs.service` (`ISLAND_IPFS_{API,GATEWAY,SWARM}_PORT`)

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
3. Record the bind address alongside the port -- with no firewall it is the access control, not a detail.
4. Replace inline port lists in other docs with a link to this file.
