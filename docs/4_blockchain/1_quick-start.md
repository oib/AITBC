# Node Quick Start

**10 minutes** — Install, configure, and sync a blockchain node.

## Prerequisites

| Resource | Minimum |
|----------|---------|
| CPU | 4 cores |
| RAM | 16 GB |
| Storage | 100 GB SSD |
| Network | 100 Mbps stable |

## 1. Install

```bash
cd /home/oib/windsurf/aitbc
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 2. Initialize & Configure

```bash
aitbc-chain init --name my-node --network ait-devnet
```

Edit `~/.aitbc/chain.yaml`:
```yaml
node:
  name: my-node
  data_dir: ./data
rpc:
  bind_host: 0.0.0.0
  bind_port: 8080
p2p:
  bind_port: 7070
  bootstrap_nodes:
    - /dns4/node-1.aitbc.com/tcp/7070/p2p/...
```

## 3. Start & Verify

```bash
aitbc-chain start
aitbc-chain status                    # node info + sync progress
curl http://localhost:8080/rpc/health # RPC health check
```

## Next

- [2_configuration.md](./2_configuration.md) — Full config reference
- [3_operations.md](./3_operations.md) — Day-to-day ops
- [7_monitoring.md](./7_monitoring.md) — Prometheus + dashboards
