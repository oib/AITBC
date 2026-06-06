# AITBC CLI

The AITBC CLI is a comprehensive command-line interface for managing the AITBC blockchain network, including wallet operations, blockchain management, AI compute jobs, agent coordination, and marketplace interactions.

## Installation

The CLI is located at `/opt/aitbc/aitbc-cli` and can be invoked directly or via the `aitbc` alias (after sourcing shell configuration).

```bash
# Direct invocation
/opt/aitbc/aitbc-cli --help

# Using alias (if configured)
aitbc --help
```

## Quick Start

### Basic Wallet Operations

```bash
# Create a new wallet
aitbc wallet create my-wallet --password-file /path/to/password

# List all wallets
aitbc wallet list

# Check wallet balance
aitbc wallet balance my-wallet

# Send transaction
aitbc wallet send my-wallet --to <recipient-address> --amount 1000 --password-file /path/to/password
```

### Blockchain Operations

```bash
# Get blockchain information
aitbc blockchain info

# Check network status
aitbc network status

# Get analytics
aitbc analytics
```

### Agent SDK Operations

```bash
# Create a new agent using Agent SDK
aitbc agent sdk create --name my-agent --type provider --auto-detect

# Register agent with coordinator
aitbc agent sdk register --agent-id <agent-id>

# Check system capabilities
aitbc agent sdk capabilities

# List local agents
aitbc agent sdk list

# Get agent status
aitbc agent sdk status --agent-id <agent-id>
```

## Command Structure

The CLI uses a nested command structure for better organization:

```
aitbc <category> <action> [options]
```

### Main Categories

- **wallet**: Wallet management (create, list, balance, send, import, export)
- **blockchain**: Blockchain operations (info, blocks, transactions, mempool)
- **network**: Network monitoring and peer management
- **market**: Marketplace operations (listings, GPU registration)
- **ai**: AI compute job management
- **agent**: Agent workflow orchestration and SDK management
- **mining**: Mining operations
- **system**: System status and diagnostics
- **genesis**: Genesis block management
- **messaging**: Cross-chain messaging
- **workflow**: Workflow automation
- **resource**: Resource management
- **pool-hub**: Pool hub operations
- **bridge**: Blockchain event bridge management

## Common Use Cases

### Wallet Management

```bash
# Create wallet with automatic password generation
aitbc wallet create demo-wallet

# Create wallet with password file
aitbc wallet create demo-wallet --password-file /var/lib/aitbc/keystore/.password

# Import wallet from private key
aitbc wallet import imported-wallet --private-key <hex-key> --password-file /path/to/password

# Export private key (use with caution)
aitbc wallet export my-wallet --password-file /path/to/password

# Delete wallet
aitbc wallet delete old-wallet
```

### Transaction Operations

```bash
# Send single transaction
aitbc wallet send sender-wallet --to <address> --amount 1000 --password-file /path/to/password

# Send batch transactions
aitbc wallet batch --from transactions.json --password-file /path/to/password

# Check transaction history
aitbc wallet transactions my-wallet --limit 10
```

### Blockchain Monitoring

```bash
# Get current blockchain height
aitbc blockchain height

# Get specific block
aitbc blockchain block --height 1000

# Get block range
aitbc blockchain blocks --start 1000 --end 1010

# View mempool
aitbc blockchain mempool

# Get chain information
aitbc blockchain info
```

### Network Operations

```bash
# Check network status
aitbc network status

# List connected peers
aitbc network peers

# Sync status
aitbc network sync

# Ping a peer
aitbc network ping --peer <peer-address>

# Force sync
aitbc network force-sync
```

### AI Compute Operations

```bash
# Submit AI job
aitbc ai submit --wallet my-wallet --type text-generation --prompt "Hello world" --payment 10

# List AI jobs
aitbc ai jobs

# Get specific job status
aitbc ai job --job-id <job-id>

# Cancel job
aitbc ai cancel --job-id <job-id> --wallet my-wallet

# Get AI statistics
aitbc ai stats
```

### Agent Operations

```bash
# Create agent workflow
aitbc agent create --name my-workflow --description "ML training pipeline"

# Execute agent workflow
aitbc agent execute --name my-workflow --input-data data.json

# Check agent status
aitbc agent status --name my-workflow

# List agents
aitbc agent list

# Send message to agent
aitbc agent message --agent my-agent --message "task data" --wallet my-wallet

# Agent SDK operations
aitbc agent sdk create --name gpu-provider --type provider --gpu-memory 24 --models llama3.2,mistral
aitbc agent sdk register --agent-id <agent-id> --coordinator-url http://localhost:8001
aitbc agent sdk capabilities
aitbc agent sdk list
aitbc agent sdk status --agent-id <agent-id>
```

### Mining Operations

```bash
# Start mining
aitbc mining start --wallet my-wallet --threads 4

# Stop mining
aitbc mining stop

# Check mining status
aitbc mining status
```

### Marketplace Operations

```bash
# List marketplace items
aitbc market list

# Create marketplace listing
aitbc market create --name "GPU Hour" --price 50 --description "High-performance GPU"

# Register GPU on marketplace
aitbc market gpu-register --gpu-id gpu-0 --memory 24 --price 100

# List GPU offerings
aitbc market gpu-list

# Buy from marketplace
aitbc market buy --item-id <item-id> --wallet my-wallet --password-file /path/to/password
```

## Configuration

### Environment Variables

The CLI respects several environment variables:

- `AITBC_RPC_URL`: Default RPC endpoint URL
- `AITBC_COORDINATOR_URL`: Agent coordinator URL
- `AITBC_KEYSTORE_DIR`: Directory for wallet keystore files
- `AITBC_DATA_DIR`: Directory for blockchain data

### Configuration Files

- `/etc/aitbc/.env`: Main configuration file
- `/etc/aitbc/node.env`: Node-specific configuration
- `~/.aitbc/config`: User-specific configuration

## Output Formats

Most commands support multiple output formats:

```bash
# Table format (default, human-readable)
aitbc wallet list --format table

# JSON format (machine-readable, script-friendly)
aitbc wallet list --format json

# YAML format
aitbc wallet list --format yaml
```

## Remote Operations

Connect to remote blockchain nodes:

```bash
# Specify RPC URL
aitbc wallet balance my-wallet --rpc-url http://remote-node:8006

# Use environment variable
export AITBC_RPC_URL=http://remote-node:8006
aitbc wallet balance my-wallet
```

## Password Management

Multiple password input methods:

```bash
# Interactive prompt
aitbc wallet send my-wallet --to <address> --amount 1000

# Password file (recommended for scripts)
aitbc wallet send my-wallet --to <address> --amount 1000 --password-file /path/to/password

# Direct password (not recommended for production)
aitbc wallet send my-wallet --to <address> --amount 1000 --password mypassword
```

## Advanced Features

### Batch Operations

Send multiple transactions in a single command:

```json
// transactions.json
[
  {
    "from_wallet": "wallet1",
    "to_address": "address1",
    "amount": 1000
  },
  {
    "from_wallet": "wallet2",
    "to_address": "address2",
    "amount": 2000
  }
]
```

```bash
aitbc wallet batch --from transactions.json --password-file /path/to/password
```

### Cross-Chain Operations

Manage multi-chain deployments:

```bash
# Cross-chain messaging
aitbc messaging send --sender agent1 --receiver agent2 --chain-id ait-testnet --message-type job_request

# Cross-chain agent communication
aitbc agent comm register --agent-id agent1 --name "Cross-chain Agent" --chain-id ait-testnet --endpoint http://node1:8001
```

### System Diagnostics

```bash
# System status
aitbc system status

# System performance
aitbc system performance

# Security audit
aitbc system security

# Economics overview
aitbc system economics
```

## Script Integration

The CLI is designed for easy script integration:

```bash
#!/bin/bash
# Get wallet balance
BALANCE=$(aitbc wallet balance my-wallet --format json | jq -r '.balance')

if [ "$BALANCE" -gt "1000" ]; then
  echo "Sufficient balance for transaction"
  aitbc wallet send my-wallet --to $RECIPIENT --amount 1000 --password-file /path/to/password
else
  echo "Insufficient balance: $BALANCE AIT"
fi
```

## Troubleshooting

### Common Issues

**Permission Denied**
```bash
# Check keystore permissions
ls -la /var/lib/aitbc/keystore/
chmod 600 /var/lib/aitbc/keystore/*.json
```

**Connection Refused**
```bash
# Verify RPC service is running
systemctl status aitbc-blockchain-rpc.service
systemctl start aitbc-blockchain-rpc.service
```

**Invalid Wallet**
```bash
# List available wallets
aitbc wallet list

# Verify wallet file exists
ls -la /var/lib/aitbc/keystore/
```

### Debug Mode

Enable verbose output for debugging:

```bash
aitbc --debug wallet balance my-wallet
aitbc --verbose network status
```

## Development

### Running from Source

```bash
cd /opt/aitbc
python cli/aitbc_cli.py --help
```

### Testing

```bash
cd /opt/aitbc/cli
python -m pytest tests/
```

## Additional Documentation

- **CLI Usage Guide**: See `CLI_USAGE_GUIDE.md` for detailed command examples
- **Agent SDK**: See `packages/py/aitbc-agent-sdk/README.md` for agent development
- **Blockchain**: See blockchain documentation in `docs/blockchain/`
- **API Reference**: See `docs/api.html` for REST API documentation

## Support

For issues or questions:
1. Check this documentation
2. Review the CLI Usage Guide
3. Check system logs in `/var/log/aitbc/`
4. Run with `--debug` flag for detailed error information