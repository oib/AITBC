# Block Production Operational Runbook

## Architecture Overview

```
Clients → RPC /sendTx → Mempool → PoA Proposer → Block (with Transactions)
                                      ↓
                              Circuit Breaker
                              (graceful degradation)
```

## Configuration

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| `block_time_seconds` | 2 | `BLOCK_TIME_SECONDS` | Block interval |
| `max_block_size_bytes` | 1,000,000 | `MAX_BLOCK_SIZE_BYTES` | Max block size (1 MB) |
| `max_txs_per_block` | 500 | `MAX_TXS_PER_BLOCK` | Max transactions per block |
| `min_fee` | 0 | `MIN_FEE` | Minimum fee to accept into mempool |
| `mempool_backend` | memory | `MEMPOOL_BACKEND` | "memory" or "database" |
| `mempool_max_size` | 10,000 | `MEMPOOL_MAX_SIZE` | Max pending transactions |
| `circuit_breaker_threshold` | 5 | `CIRCUIT_BREAKER_THRESHOLD` | Failures before circuit opens |
| `circuit_breaker_timeout` | 30 | `CIRCUIT_BREAKER_TIMEOUT` | Seconds before half-open retry |

## Mempool Backends

### In-Memory (default)
- Fast, no persistence
- Lost on restart
- Suitable for devnet/testnet

### Database-backed (SQLite)
- Persistent across restarts
- Shared between services via file
- Set `MEMPOOL_BACKEND=database`

## Monitoring Metrics

### Block Production
- `blocks_proposed_total` — Total blocks proposed
- `chain_head_height` — Current chain height
- `last_block_tx_count` — Transactions in last block
- `last_block_total_fees` — Total fees in last block
- `block_build_duration_seconds` — Time to build last block
- `block_interval_seconds` — Time between blocks

### Mempool
- `mempool_size` — Current pending transaction count
- `mempool_tx_added_total` — Total transactions added
- `mempool_tx_drained_total` — Total transactions included in blocks
- `mempool_evictions_total` — Transactions evicted (low fee)

### Circuit Breaker
- `circuit_breaker_state` — 0=closed, 1=open
- `circuit_breaker_trips_total` — Times circuit breaker opened
- `blocks_skipped_circuit_breaker_total` — Blocks skipped due to open circuit

### RPC
- `rpc_send_tx_total` — Total transaction submissions
- `rpc_send_tx_success_total` — Successful submissions
- `rpc_send_tx_rejected_total` — Rejected (fee too low, validation)
- `rpc_send_tx_failed_total` — Failed (mempool unavailable)

## Troubleshooting

### Empty blocks (tx_count=0)
1. Check mempool size: `GET /metrics` → `mempool_size`
2. Verify transactions are being submitted: `rpc_send_tx_total`
3. Check if fees meet minimum: `rpc_send_tx_rejected_total`
4. Verify block size limits aren't too restrictive

### Circuit breaker open
1. Check `circuit_breaker_state` metric (1 = open)
2. Review logs for repeated failures
3. Check database connectivity
4. Wait for timeout (default 30s) for automatic half-open retry
5. If persistent, restart the node

### Mempool full
1. Check `mempool_size` vs `MEMPOOL_MAX_SIZE`
2. Low-fee transactions are auto-evicted
3. Increase `MEMPOOL_MAX_SIZE` or raise `MIN_FEE`

### High block build time
1. Check `block_build_duration_seconds`
2. Reduce `MAX_TXS_PER_BLOCK` if too slow
3. Consider database mempool for large volumes
4. Check disk I/O if using SQLite backend

### Transaction not included in block
1. Verify transaction was accepted: check `tx_hash` in response
2. Check fee is competitive (higher fee = higher priority)
3. Check transaction size vs `MAX_BLOCK_SIZE_BYTES`
4. Transaction may be queued — check `mempool_size`
