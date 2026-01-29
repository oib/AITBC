# Blockchain Node - AITBC Documentation

PoA/PoS consensus blockchain with REST/WebSocket RPC, real-time gossip layer, and comprehensive observability

<span class="status-badge live">● Live</span>

## Overview

The AITBC Blockchain Node is the core infrastructure component that maintains the distributed ledger. It implements a hybrid Proof-of-Authority/Proof-of-Stake consensus mechanism with fast finality and supports high throughput for AI workload transactions.

### Key Features

- Hybrid PoA/PoS consensus with sub-second finality
- REST and WebSocket RPC APIs
- Real-time gossip protocol for block propagation
- Comprehensive observability with Prometheus metrics
- SQLModel-based data persistence
- Built-in devnet tooling and scripts

## Architecture

The blockchain node is built with a modular architecture separating concerns for consensus, storage, networking, and API layers.

#### Consensus Engine
Hybrid PoA/PoS with proposer rotation and validator sets

#### Storage Layer
SQLModel with SQLite/PostgreSQL support

#### Networking
WebSocket gossip + REST API

#### Observability
Prometheus metrics + structured logging

## API Reference

The blockchain node exposes both REST and WebSocket APIs for interaction.

### REST Endpoints

`GET /rpc/get_head`
Get the latest block header

`POST /rpc/send_tx`
Submit a new transaction

`GET /rpc/get_balance/{address}`
Get account balance

`GET /rpc/get_block/{height}`
Get block by height

### WebSocket Subscriptions

- `new_blocks` - Real-time block notifications
- `new_transactions` - Transaction pool updates
- `consensus_events` - Consensus round updates

## Configuration

The node can be configured via environment variables or configuration file.

### Key Settings

```bash
# Database
DATABASE_URL=sqlite:///blockchain.db

# Network
RPC_HOST=0.0.0.0
RPC_PORT=9080
WS_PORT=9081

# Consensus
CONSENSUS_MODE=poa
VALIDATOR_ADDRESS=0x...
BLOCK_TIME=1s

# Observability
METRICS_PORT=9090
LOG_LEVEL=info
```

## Running a Node

### Development Mode

```bash
# Initialize devnet
python -m blockchain.scripts.init_devnet

# Start node
python -m blockchain.main --config devnet.yaml
```

### Production Mode

```bash
# Using Docker
docker run -d \
  -v /data/blockchain:/data \
  -p 9080:9080 \
  -p 9081:9081 \
  -p 9090:9090 \
  aitbc/blockchain-node:latest
```

## Monitoring

### Prometheus Metrics

Available at `http://localhost:9090/metrics`

Key metrics:
- `blockchain_blocks_total` - Total blocks produced
- `blockchain_transactions_total` - Total transactions processed
- `blockchain_consensus_rounds` - Consensus rounds completed
- `blockchain_network_peers` - Active peer connections

### Health Checks

```bash
# Node status
curl http://localhost:9080/health

# Sync status
curl http://localhost:9080/sync_status
```

## Troubleshooting

### Common Issues

1. **Node not syncing**
   - Check peer connections: `curl /rpc/peers`
   - Verify network connectivity
   - Check logs for consensus errors

2. **High memory usage**
   - Reduce `block_cache_size` in config
   - Enable block pruning

3. **RPC timeouts**
   - Increase `rpc_timeout` setting
   - Check system resources

## Development

### Building from Source

```bash
git clone https://github.com/aitbc/blockchain
cd blockchain
pip install -e .
```

### Running Tests

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/
```

## Security Considerations

- Validator keys should be kept secure
- Use HTTPS in production
- Implement rate limiting on RPC endpoints
- Regular security updates for dependencies
