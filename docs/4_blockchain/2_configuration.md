# Blockchain Node Configuration
Configure your blockchain node for optimal performance.

## Configuration File

Location: `~/.aitbc/chain.yaml`

## Node Configuration

```yaml
node:
  name: my-node
  network: ait-devnet  # or ait-mainnet
  data_dir: /opt/blockchain-node/data
  log_level: info
```

## RPC Configuration

```yaml
rpc:
  enabled: true
  bind_host: 0.0.0.0
  bind_port: 8080
  cors_origins:
    - http://localhost:3000
    - http://localhost:8000
  rate_limit: 1000  # requests per minute
```

## P2P Configuration

```yaml
p2p:
  enabled: true
  bind_host: 0.0.0.0
  bind_port: 7070
  bootstrap_nodes:
    - /dns4/node-1.aitbc.com/tcp/7070/p2p/...
  max_peers: 50
  min_peers: 5
```

## Mempool Configuration

```yaml
mempool:
  backend: database  # or memory
  max_size: 10000
  min_fee: 0
  eviction_interval: 60
```

## Database Configuration

```yaml
database:
  adapter: postgresql  # or sqlite
  url: postgresql://user:pass@localhost/aitbc_chain
  pool_size: 10
  max_overflow: 20
```

## Validator Configuration

```yaml
validator:
  enabled: true
  key: <VALIDATOR_PRIVATE_KEY>
  block_time: 2  # seconds
  max_block_size: 1000000  # bytes
  max_txs_per_block: 500
```

## Environment Variables

```bash
export AITBC_CHAIN_DATA_DIR=/opt/blockchain-node/data
export AITBC_CHAIN_RPC_PORT=8080
export AITBC_CHAIN_P2P_PORT=7070
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Operations](./3_operations.md) — Day-to-day ops
- [Consensus](./4_consensus.md) — Consensus mechanism
