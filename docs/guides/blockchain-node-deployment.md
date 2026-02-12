# Blockchain Node Deployment Guide

## Prerequisites

- Python 3.11+
- SQLite 3.35+
- 512 MB RAM minimum (1 GB recommended)
- 10 GB disk space

## Configuration

All settings via environment variables or `.env` file:

```bash
# Core
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
PROPOSER_ID=ait-devnet-proposer
BLOCK_TIME_SECONDS=2

# RPC
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8080

# Block Production
MAX_BLOCK_SIZE_BYTES=1000000
MAX_TXS_PER_BLOCK=500
MIN_FEE=0

# Mempool
MEMPOOL_BACKEND=database        # "memory" or "database"
MEMPOOL_MAX_SIZE=10000

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=30

# Sync
TRUSTED_PROPOSERS=proposer-a,proposer-b
MAX_REORG_DEPTH=10
SYNC_VALIDATE_SIGNATURES=true

# Gossip
GOSSIP_BACKEND=memory           # "memory" or "broadcast"
GOSSIP_BROADCAST_URL=            # Required for broadcast backend
```

## Installation

```bash
cd apps/blockchain-node
pip install -e .
```

## Running

### Development
```bash
uvicorn aitbc_chain.app:app --host 127.0.0.1 --port 8080 --reload
```

### Production
```bash
uvicorn aitbc_chain.app:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 1 \
  --timeout-keep-alive 30 \
  --access-log \
  --log-level info
```

**Note:** Use `--workers 1` because the PoA proposer must run as a single instance.

### Systemd Service
```ini
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/apps/blockchain-node
EnvironmentFile=/opt/aitbc/.env
ExecStart=/opt/aitbc/venv/bin/uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8080 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/rpc/head` | Chain head |
| GET | `/rpc/blocks/{height}` | Block by height |
| GET | `/rpc/blocks` | Latest blocks |
| GET | `/rpc/tx/{hash}` | Transaction by hash |
| POST | `/rpc/sendTx` | Submit transaction |
| POST | `/rpc/importBlock` | Import block from peer |
| GET | `/rpc/syncStatus` | Sync status |
| POST | `/rpc/admin/mintFaucet` | Mint devnet funds |

## Monitoring

### Health Check
```bash
curl http://localhost:8080/health
```

### Key Metrics
- `poa_proposer_running` — 1 if proposer is active
- `chain_head_height` — Current block height
- `mempool_size` — Pending transactions
- `circuit_breaker_state` — 0=closed, 1=open
- `rpc_requests_total` — Total RPC requests
- `rpc_rate_limited_total` — Rate-limited requests

### Alerting Rules (Prometheus)
```yaml
- alert: ProposerDown
  expr: poa_proposer_running == 0
  for: 1m

- alert: CircuitBreakerOpen
  expr: circuit_breaker_state == 1
  for: 30s

- alert: HighErrorRate
  expr: rate(rpc_server_errors_total[5m]) > 0.1
  for: 2m
```

## Troubleshooting

- **Proposer not producing blocks**: Check `poa_proposer_running` metric, review logs for DB errors
- **Rate limiting**: Increase `max_requests` in middleware or add IP allowlist
- **DB locked**: Switch to `MEMPOOL_BACKEND=database` for separate mempool DB
- **Sync failures**: Check `TRUSTED_PROPOSERS` config, verify peer connectivity
