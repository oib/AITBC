# AITBC Quick Reference

**Last Updated**: 2026-08-13
**Version**: 2.0 (refreshed to current CLI and service ports)

A condensed reference for common AITBC commands. For the full CLI, see [cli/README.md](../cli/README.md). For authoritative ports, see [reference/SERVICE_PORTS.md](./reference/SERVICE_PORTS.md).

## Service ports

| Service | Port | Health / Notes |
|---------|------|----------------|
| API Gateway | 8201 | Public nginx-proxied entry point |
| Blockchain RPC | 8202 | `aitbc blockchain info`, RPC calls |
| Coordinator API | 8203 | Job lifecycle, marketplace endpoints |
| Agent Registry | 8204 | Agent discovery |
| Blockchain Explorer API | 8100 | Block/transaction search |
| GPU Service | 8101 | GPU marketplace / miner operations |
| Marketplace Service | 8102 | Marketplace transactions |
| Trading Service | 8104 | Order matching, subscription sync |
| Governance Service | 8105 | Proposals and voting |
| Exchange API | 8106 | Trading, bridge, deposit/withdraw |
| Agent Coordinator | 8107 | Agent messaging / orchestration |
| Wallet Daemon | 8108 | Multi-chain wallet |
| Whisper Service | 8110 | Transcription |
| Edge Service | 8111 | Edge compute and dispatch |
| Blockchain P2P | 7070 | Hub-only gossip relay |

## Service lifecycle

Services are systemd units, not `aitbc` subcommands:

```bash
# Start/stop/restart individual services
sudo systemctl start aitbc-blockchain-node
sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-miner
sudo systemctl restart aitbc-gpu

# Check all installed AITBC services
systemctl list-units 'aitbc-*' --type=service --no-pager
```

## Wallet

```bash
aitbc wallet create my-wallet --password-file /var/lib/aitbc/keystore/.password
aitbc wallet list
aitbc wallet balance my-wallet
aitbc wallet send my-wallet --to <address> --amount 1000 --password-file /var/lib/aitbc/keystore/.password
```

## Blockchain and network

```bash
aitbc blockchain info
aitbc blockchain list
aitbc network status
aitbc network peers
aitbc network subscribe --hub-url https://hub.aitbc.bubuit.net

# RPC helpers
curl http://localhost:8202/rpc/head | python3 -m json.tool
curl http://localhost:8202/rpc/info | python3 -m json.tool
```

## AI jobs (client)

```bash
aitbc ai submit --wallet my-wallet --type text-generation --prompt "Hello world" --payment 10
aitbc ai jobs
aitbc ai status --job-id <job-id>
aitbc ai results --job-id <job-id>
aitbc ai cancel --job-id <job-id> --wallet my-wallet
```

## Marketplace / GPU

```bash
aitbc market list
aitbc market offer --gpu-id gpu-0 --memory 24 --price 100
aitbc market match
```

## Mining

```bash
aitbc mining start --wallet my-wallet --threads 4
aitbc mining status
aitbc mining stop
aitbc mining list
```

## Agent SDK

```bash
aitbc agent create --name my-agent --type provider --auto-detect
aitbc agent register --agent-id <agent-id> --coordinator-url http://localhost:8203
aitbc agent list
aitbc agent status --agent-id <agent-id>
aitbc agent capabilities
```

## Node / mesh

```bash
aitbc node list
aitbc node add --name my-node --url http://node.example:8202
aitbc node test --name my-node
aitbc node hub --help
aitbc node island --help
```

## Development validation

```bash
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q

# App-specific tests
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

## See also

- [CLI README](../cli/README.md) — full command reference
- [Service Ports Reference](./reference/SERVICE_PORTS.md) — authoritative ports
- [Getting Started](./getting-started/) — hub/shop/client paths
