# AITBC systemd services

> **Last Updated:** 2026-09-01
> **Scope:** Live service inventory on hub (`hub.aitbc`) and shop/follower (`aitbc3`) nodes. For authoritative port numbers, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

AITBC runs as a set of `systemd` units. Service startup, stop, restart, and health checks are performed with `systemctl` and `journalctl`; there are no `aitbc <service> start` CLI commands.

## Service inventory

The exact units installed vary by node role. The hub runs the coordinator, customer-facing services and block production; the shop/follower runs the miner, pool hub, GPU and island services. A typical follower/customer replica (e.g. `hub2.aitbc`) runs a subset of the hub's blockchain services.

### Core blockchain services (all node types)

| Unit | Purpose | Port | Health |
|------|---------|------|--------|
| `aitbc-blockchain-node.service` | Block production and chain state | `BLOCKCHAIN_NODE_RPC` (8202 via `aitbc-blockchain-rpc.service`) | `journalctl -u aitbc-blockchain-node` |
| `aitbc-blockchain-rpc.service` | Public blockchain RPC | 8202 | `curl -s http://localhost:8202/rpc/info` |
| `aitbc-blockchain-explorer.service` | Block/transaction explorer API | 8100 | `curl -s http://localhost:8100/health` |

On the hub an additional `aitbc-blockchain-p2p.service` may run the gossip relay for followers. Followers do **not** run `aitbc-blockchain-p2p`; they subscribe to the hub via the RPC WebSocket.

### Hub / customer services (`hub.aitbc`)

| Unit | Purpose | Port | Health |
|------|---------|------|--------|
| `aitbc-coordinator-api.service` | Job lifecycle, marketplace, escrow, payments, bonds | 8203 | `curl -s http://localhost:8203/health` |
| `aitbc-pool-hub.service` | Miner registration, heartbeats, matching | 8210 | `curl -s http://localhost:8210/health` |
| `aitbc-marketplace.service` | Marketplace listings and offers | 8102 | `curl -s http://localhost:8102/health` |
| `aitbc-api-gateway.service` | External nginx-proxied API entry point | 8201 | `curl -s http://localhost:8201/health` |
| `aitbc-wallet.service` | Wallet daemon | 8108 | `curl -s http://localhost:8108/health` |
| `aitbc-exchange.service` | Exchange / bridge operations | 8106 | `curl -s http://localhost:8106/health` |
| `aitbc-trading.service` | Trading and subscription sync | 8104 | `curl -s http://localhost:8104/health` |
| `aitbc-governance.service` | Proposals and voting | 8105 | `curl -s http://localhost:8105/health` |
| `aitbc-agent-coordinator.service` | Agent messaging and orchestration | 8107 | `curl -s http://localhost:8107/health` |
| `aitbc-blockchain-event-bridge.service` | Blockchain event streaming | 8205 | `curl -s http://localhost:8205/health` |
| `aitbc-bridge-monitor.service` | Bridge validator monitoring | — | `journalctl -u aitbc-bridge-monitor` |

### Shop / island services (`aitbc3`)

| Unit | Purpose | Port | Health |
|------|---------|------|--------|
| `aitbc-miner.service` | Production miner; polls coordinator for jobs | — | `journalctl -u aitbc-miner -n 20` |
| `aitbc-pool-hub.service` | Local pool hub for miner coordination | 8210 | `curl -s http://localhost:8210/health` |
| `aitbc-gpu.service` | GPU marketplace and hardware registration | 8101 | `curl -s http://localhost:8101/health` |
| `aitbc-ffmpeg.service` | FFmpeg media processing | 8230 | `curl -s http://localhost:8230/health` |
| `aitbc-whisper.service` | Whisper transcription | 8110 | `curl -s http://localhost:8110/health` |
| `aitbc-edge.service` | Edge compute and dispatch | 8111 | `curl -s http://localhost:8111/health` |
| `aitbc-marketplace.service` | Marketplace listings and offers | 8102 | `curl -s http://localhost:8102/health` |
| `aitbc-trading.service` | Trading and subscription sync | 8104 | `curl -s http://localhost:8104/health` |
| `aitbc-governance.service` | Proposals and voting | 8105 | `curl -s http://localhost:8105/health` |
| `aitbc-wallet.service` | Wallet daemon | 8108 | `curl -s http://localhost:8108/health` |

### Support / utility services

| Unit | Purpose |
|------|---------|
| `aitbc-load-secrets.service` | One-shot load of keystore secrets |
| `aitbc-backup.service` | Scheduled backup script |
| `aitbc-recovery.service` | One-shot recovery / systemd link setup |
| `aitbc-monitoring.service` | Monitoring and log aggregation |

## Common commands

```bash
# List installed AITBC units
systemctl list-unit-files 'aitbc-*.service' --no-pager

# Check running services
systemctl list-units 'aitbc-*.service' --type=service --no-pager

# Status, start, stop, restart
systemctl status aitbc-coordinator-api
sudo systemctl start aitbc-coordinator-api
sudo systemctl stop aitbc-coordinator-api
sudo systemctl restart aitbc-coordinator-api

# Follow logs
journalctl -u aitbc-coordinator-api -f

# View recent logs across all AITBC services
journalctl -u 'aitbc-*' --no-pager -n 50

# Reload after a service file change
sudo systemctl daemon-reload
```

## Service startup order

1. `aitbc-load-secrets.service` (one-shot, loads keystore)
2. `aitbc-blockchain-node.service` and `aitbc-blockchain-rpc.service`
3. `aitbc-coordinator-api.service` / `aitbc-pool-hub.service`
4. `aitbc-miner.service` (after coordinator/pool hub is available)
5. Remaining application services

Most units declare `Restart=always` or `Restart=on-failure`; use `systemctl` to inspect individual unit dependencies.

## Related documentation

- [Service Ports Reference](../reference/SERVICE_PORTS.md) — authoritative port numbers and nginx routes
- [Apps Catalog](../apps/README.md) — app-to-service mapping and source layout
- [Getting Started](../getting-started/) — hub/shop/client setup
