# AITBC Quick Reference

**Last Updated**: 2026-06-30
**Version**: 1.0

Quick reference for common AITBC commands and operations.

## Blockchain Commands

### Node Operations
```bash
# Start blockchain node
aitbc blockchain-node start

# Stop blockchain node
aitbc blockchain-node stop

# Check node status
aitbc blockchain-node status

# View node logs
journalctl -u aitbc-blockchain-node -f

# Get block height
curl http://localhost:8202/rpc/head | python3 -m json.tool

# Get state snapshot
curl http://localhost:8202/rpc/state/snapshot | python3 -m json.tool
```

### Chain Management
```bash
# List all chains
aitbc chain list

# Get chain status
aitbc chain status --chain-id ait-hub.aitbc.bubuit.net

# Create a new chain
aitbc chain create --chain-id my-chain --genesis-file genesis.json

# Delete a chain
aitbc chain delete --chain-id my-chain

# Add chain to supported chains
aitbc chain add --chain-id my-chain

# Remove chain from supported chains
aitbc chain remove --chain-id my-chain

# Migrate chain data
aitbc chain migrate --from-chain old-chain --to-chain new-chain

# Check sync status
aitbc chain sync-status --all-chains
```

### Island Operations
```bash
# Join an island
aitbc node island join --island-id <uuid> --chain-id ait-hub.aitbc.bubuit.net

# Leave an island
aitbc node island leave --island-id <uuid>

# List islands
aitbc node island list

# Get island info
aitbc node island info --island-id <uuid>

# Check island health
aitbc node island health
```

## Wallet Commands

### Wallet Operations
```bash
# Initialize wallet
aitbc wallet init

# Import private key
aitbc wallet import --private-key <key>

# Generate new address
aitbc wallet new-address

# List addresses
aitbc wallet list

# Get balance
aitbc wallet balance --address <address>

# Send transaction
aitbc wallet send --to <address> --amount 0.01 --fee 0.01

# Sign transaction
aitbc wallet sign --tx-data <data>
```

## Agent Commands

### Agent Operations
```bash
# Initialize agent
aitbc agent init --name my-agent

# Start agent
aitbc agent start

# Stop agent
aitbc agent stop

# List agents
aitbc agent list

# Get agent status
aitbc agent status --agent-id <id>

# Register agent
aitbc agent register --endpoint http://localhost:8000

# Discover agents
aitbc agent discover --capability compute
```

### Agent Coordinator
```bash
# Start agent coordinator
aitbc agent-coordinator start

# Stop agent coordinator
aitbc agent-coordinator stop

# View swarm status
curl http://localhost:8000/swarms | python3 -m json.tool

# Register agent with coordinator
curl -X POST http://localhost:8000/agents/register -H "Content-Type: application/json" -d '{"agent_id": "...", "endpoint": "..."}'
```

## Coordinator API Commands

### Job Operations
```bash
# Start coordinator API
aitbc coordinator-api start

# Submit job
curl -X POST http://localhost:8000/jobs -H "Content-Type: application/json" -d '{"job_type": "...", "params": {...}}'

# Get job status
curl http://localhost:8000/jobs/<job-id> | python3 -m json.tool

# List jobs
curl http://localhost:8000/jobs | python3 -m json.tool

# Cancel job
curl -X DELETE http://localhost:8000/jobs/<job-id>
```

## Marketplace Commands

### Marketplace Operations
```bash
# Start marketplace service
aitbc marketplace-service start

# List resources
curl http://localhost:8001/resources | python3 -m json.tool

# Submit bid
curl -X POST http://localhost:8001/bids -H "Content-Type: application/json" -d '{"resource_id": "...", "amount": 100}'

# List bids
curl http://localhost:8001/bids | python3 -m json.tool

# Accept bid
curl -X POST http://localhost:8001/bids/<bid-id>/accept
```

### GPU Service
```bash
# Start GPU service
aitbc gpu-service start

# Register GPU resource
curl -X POST http://localhost:8002/register -H "Content-Type: application/json" -d '{"gpu_id": "...", "specs": {...}}'

# Monitor jobs
curl http://localhost:8002/jobs | python3 -m json.tool
```

## Mining Commands

### Mining Operations
```bash
# Start mining
aitbc miner start

# Stop mining
aitbc miner stop

# Check mining status
aitbc miner status

# View mining logs
journalctl -u aitbc-miner -f
```

## CLI Commands

### General CLI
```bash
# Get CLI help
aitbc --help

# Get command help
aitbc <command> --help

# Set configuration
aitbc config set <key> <value>

# Get configuration
aitbc config get <key>

# List all configuration
aitbc config list
```

## System Commands

### Service Management
```bash
# Start all AITBC services
aitbc services start

# Stop all AITBC services
aitbc services stop

# Restart all AITBC services
aitbc services restart

# Check service status
aitbc services status

# View service logs
aitbc services logs --service <service-name>
```

### Health Checks
```bash
# Run health check
./health-check.sh

# Check specific service health
curl http://localhost:8000/health

# Check database connectivity
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db "SELECT COUNT(*) FROM block;"

# Check Redis connectivity
redis-cli ping
```

## Development Commands

### Type Checking
```bash
# Type check shared core
./venv/bin/python -m mypy --show-error-codes aitbc/

# Type check specific app
./venv/bin/python -m mypy --show-error-codes apps/<app-name>/src

# Type check all apps
for app in blockchain-node coordinator-api wallet; do
  ./venv/bin/python -m mypy --show-error-codes apps/$app/src
done
```

### Linting
```bash
# Lint all code
./venv/bin/python -m ruff check .

# Lint specific directory
./venv/bin/python -m ruff check aitbc/

# Format code
./venv/bin/python -m ruff format .
```

### Testing
```bash
# Run unit tests
./venv/bin/python -m pytest tests/unit -q

# Run integration tests
./venv/bin/python -m pytest tests/integration -q

# Run specific test file
./venv/bin/python -m pytest tests/unit/test_file.py -q

# Run with coverage
./venv/bin/python -m pytest tests/unit --cov=aitbc --cov-report=html
```

## Configuration Files

### Common Config Locations
```bash
# Blockchain node config
/etc/aitbc/blockchain.env

# Coordinator API config
/etc/aitbc/coordinator.env

# Wallet config
/etc/aitbc/wallet.env

# Agent config
~/.aitbc/agent.yaml

# Client config
~/.aitbc/config.yaml
```

### Environment Variables
```bash
# Set chain ID
export CHAIN_ID=ait-hub.aitbc.bubuit.net

# Set node ID
export NODE_ID=<uuid>

# Set database path
export DATABASE_PATH=/var/lib/aitbc/data

# Set RPC port
export RPC_PORT=8202

# Set log level
export LOG_LEVEL=INFO
```

## Troubleshooting

### Common Issues

**Node won't start**
```bash
# Check logs
journalctl -u aitbc-blockchain-node -n 50 --no-pager

# Check port availability
netstat -tlnp | grep 8202

# Check database
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db "PRAGMA integrity_check;"
```

**Sync issues**
```bash
# Check sync status
aitbc chain sync-status --all-chains

# Verify peer connectivity
curl http://localhost:8202/rpc/network-info | python3 -m json.tool

# Check default peer URL
grep default_peer_rpc_url /etc/aitbc/blockchain.env
```

**Transaction failed**
```bash
# Check fee settings
grep "fee.*=" /opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/transactions.py

# Verify balance
aitbc wallet balance --address <address>

# Check mempool
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db "SELECT * FROM mempool LIMIT 10;"
```

## Useful URLs

### Default Ports
- Blockchain Node RPC: 8202
- Coordinator API: 8000
- Exchange: 8001
- Marketplace Service: 8001
- GPU Service: 8002
- Wallet API: 8003
- Explorer: 8080
- Monitoring Dashboard: 9000

### API Endpoints
- Blockchain RPC: http://localhost:8202/rpc/
- Coordinator API: http://localhost:8000/
- Marketplace: http://localhost:8001/
- Explorer: http://localhost:8080/

---

**Quick Reference Version**: 1.0
**Last Updated**: 2026-06-30
**Maintained By**: Documentation Team
