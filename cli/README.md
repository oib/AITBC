# AITBC CLI

The AITBC CLI is a comprehensive command-line interface for managing the AITBC blockchain network, including wallet operations, blockchain management, AI compute jobs, agent coordination, marketplace interactions, and federated mesh operations.

**Version**: 2.1.0 (CLI runtime) · **Package**: `aitbc-cli` · **Python**: ≥ 3.13

## Installation

The CLI is installed as part of the AITBC deployment via `scripts/deployment/setup.sh`, which performs an editable install of this package into the shared venv at `/opt/aitbc/venv` and exposes a wrapper at `/usr/local/bin/aitbc`.

```bash
# Editable install (used by the deployment script)
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/pip install -e .

# Verify
aitbc --version
# aitbc, version 2.1.0
```

The wrapper script (`/usr/local/bin/aitbc`) invokes `/opt/aitbc/venv/bin/python -m aitbc_cli.core.main "$@"`, so `aitbc` works from any shell without manually activating the venv.

## Quick Start

```bash
# Top-level help (lists all 50+ command groups)
aitbc --help

# Create a wallet
aitbc wallet create my-wallet --password-file /var/lib/aitbc/keystore/.password

# Check chain info
aitbc blockchain info

# Network status
aitbc network status

# Submit an AI job
aitbc ai submit --wallet my-wallet --type text-generation --prompt "Hello world" --payment 10
```

## Command Structure

The CLI uses a nested Click group structure:

```
aitbc [GLOBAL OPTIONS] <command-group> <subcommand> [OPTIONS]
```

Global options (apply to all commands):

| Option | Description |
|---|---|
| `--url TEXT` | Coordinator API URL (overrides config) |
| `--api-key TEXT` | API key for authentication |
| `--chain-id TEXT` | Chain ID for multichain operations (e.g. `ait-mainnet`, `ait-devnet`) |
| `--output [table\|json\|yaml\|csv]` | Output format (default: `table`) |
| `-v, --verbose` | Increase verbosity (repeatable) |
| `--debug` | Enable debug mode |
| `--version` | Show version and exit |

## Command Groups

The CLI exposes 50+ top-level command groups registered in `aitbc_cli/core/main.py`. The main groups:

| Group | Description | Key subcommands |
|---|---|---|
| `wallet` | Wallet management & transactions | `create`, `list`, `balance`, `send`, `import-wallet`, `export`, `stake`, `unstake`, `multisig-*`, `request-payment` |
| `blockchain` | Multi-chain management | `info`, `list`, `create`, `add`, `remove`, `migrate`, `backup`, `restore`, `monitor` |
| `network` | Peer connectivity & subscriptions | `status`, `peers`, `test`, `force-sync`, `subscribe`, `subscribers`, `lease-status`, `heartbeat` |
| `market` | On-chain GPU marketplace | `offer`, `list`, `match`, `cancel`, `escrow`, `run`, `transcribe`, `transcode`, `rate`, `ratings` |
| `marketplace` | Global chain marketplace (legacy compat) | `list`, `create`, `buy` |
| `ai` | AI compute job management | `submit`, `jobs`, `status`, `cancel`, `results`, `stats`, `service` |
| `agent` | Agent SDK & coordinator | `create`, `register`, `list`, `status`, `capabilities`, `submit`, `jobs`, `workflow`, `config-*` |
| `agent-comm` | Cross-chain agent communication | `register`, `send`, `receive` |
| `mining` | Mining operations | `start`, `stop`, `status`, `list` |
| `hermes` | Hermes agent messaging | `ping`, `send`, `receive`, `peers`, `request-coins` |
| `node` | Federated mesh node management | `add`, `list`, `info`, `remove`, `test`, `bridge`, `chain`, `hub`, `island` |
| `exchange` | Exchange integration & trading | `register`, `create-pair`, `add-liquidity`, `start-trading`, `status`, `monitor` |
| `exchange-island` | AIT/BTC/ETH trading on islands | (island exchange ops) |
| `gpu` | Local GPU hardware management | (GPU service ops) |
| `gpu-onchain` | On-chain GPU resource tracking | (on-chain GPU ops) |
| `sync` | Blockchain synchronization | `bulk` |
| `system` | System management & audits | `architect`, `audit`, `check`, `config`, `restart`, `status` |
| `governance` | Governance operations | (proposal lifecycle) |
| `genesis` | Genesis block & wallet generation | (genesis ops) |
| `analytics` | Chain analytics & monitoring | (analytics ops) |
| `monitor` | Monitoring, metrics, alerts | (monitoring ops) |
| `performance` | Performance monitoring | (perf ops) |
| `reputation` | Reputation management | (reputation ops) |
| `bridge` | Blockchain event bridge | (bridge ops) |
| `messaging` | Messaging system & forum | (messaging ops) |
| `workflow` | Workflow automation | (workflow ops) |
| `resource` | Resource management (EXPERIMENTAL) | (resource ops) |
| `operations` | General operations | (ops) |
| `pool-hub` | Pool hub SLA & billing | (pool-hub ops) |
| `contract` | Smart contract operations | (contract ops) |
| `script` | Script execution & management | (script ops) |
| `economics` | Economic intelligence & modeling | (economics ops) |
| `cluster` | Cluster management | (cluster ops) |
| `security` | Security audit & monitoring | (security ops) |
| `compliance` | Compliance checking & reporting | (compliance ops) |
| `edge` | Edge API (island, GPU, database, serve) | (edge ops) |
| `account` | Account information & management | (account ops) |
| `coin-requests` | Coin transfer request management | (request ops) |
| `explorer` | Blockchain explorer data access | (explorer ops) |
| `simulate` | Blockchain scenario simulation | (simulate ops) |
| `crosschain` | Cross-chain trading operations | (cross-chain ops) |
| `config` | Manage CLI configuration | (config ops) |
| `list` | Legacy wallet list alias | — |
| `version` | Show version information | — |

Run `aitbc <group> --help` for the full subcommand list and options of any group.

## Common Use Cases

### Wallet Management

```bash
# Create wallet with password file
aitbc wallet create demo-wallet --password-file /var/lib/aitbc/keystore/.password

# List all wallets
aitbc wallet list

# Check balance
aitbc wallet balance demo-wallet

# Send transaction
aitbc wallet send demo-wallet --to <recipient-address> --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Import wallet from JSON export
aitbc wallet import-wallet imported-wallet --path /path/to/wallet.json

# Stake / unstake
aitbc wallet stake demo-wallet --amount 500 --password-file /var/lib/aitbc/keystore/.password
aitbc wallet unstake demo-wallet --amount 500 --password-file /var/lib/aitbc/keystore/.password

# Multisig
aitbc wallet multisig-create --owners alice,bob --required 2
aitbc wallet multisig-propose --wallet msig --to <addr> --amount 100
aitbc wallet multisig-sign --wallet msig --proposal-id 1
```

### Blockchain Operations

```bash
# Chain info
aitbc blockchain info

# List configured chains
aitbc blockchain list

# Create a new chain from genesis config
aitbc blockchain create --config /path/to/genesis.yaml

# Monitor chain activity
aitbc blockchain monitor --chain-id ait-mainnet
```

### Network & Sync

```bash
# Network status
aitbc network status

# List peers
aitbc network peers

# Test connectivity to a peer
aitbc network test --peer <peer-address>

# Force synchronization
aitbc network force-sync

# Subscribe this follower node to a hub
aitbc network subscribe --hub-url https://hub.aitbc.bubuit.net

# Bulk import blocks from a leader to catch up
aitbc sync bulk --leader-url http://hub.aitbc.bubuit.net:8202
```

### Hermes Ping/Pong (Follower ↔ Hub)

Followers can ping a remote Hermes agent (e.g. the hub coordinator) and wait for its PONG reply:

```bash
# Ping the hub coordinator agent and wait up to 10s for PONG
aitbc hermes ping \
  --agent hub-coordinator \
  --sender my-follower-agent \
  --coordinator-url http://hub.aitbc.bubuit.net:8203 \
  --timeout 10
```

This posts a `PING` message to the coordinator's `/v1/hermes/messages/send` endpoint and polls `/v1/hermes/messages/{sender}` for the `PONG` reply.

### AI Compute

```bash
# Submit AI job
aitbc ai submit --wallet my-wallet --type text-generation --prompt "Hello world" --payment 10

# List AI jobs
aitbc ai jobs

# Get specific job status
aitbc ai status --job-id <job-id>

# Get results
aitbc ai results --job-id <job-id>

# Cancel
aitbc ai cancel --job-id <job-id> --wallet my-wallet
```

### Agent SDK

```bash
# Create a new agent (auto-detect capabilities)
aitbc agent create --name my-agent --type provider --auto-detect

# Register with coordinator
aitbc agent register --agent-id <agent-id> --coordinator-url http://localhost:8203

# List local agents
aitbc agent list

# Get agent status
aitbc agent status --agent-id <agent-id>

# Show auto-detected system capabilities
aitbc agent capabilities
```

### Mining

```bash
aitbc mining start --wallet my-wallet --threads 4
aitbc mining status
aitbc mining stop
aitbc mining list
```

### Marketplace (on-chain GPU)

```bash
# List offers and bids
aitbc market list

# List a hardware+software bundle offer
aitbc market offer --gpu-id gpu-0 --memory 24 --price 100

# Match bids with offers (price discovery)
aitbc market match

# Run an inference job against a software offer
aitbc market run --offer-id <offer-id> --input input.json

# Rate a service offer
aitbc market rate --offer-id <offer-id> --rating 5
```

### Node / Federated Mesh

```bash
# List configured nodes
aitbc node list

# Add a node
aitbc node add --name my-node --url http://node.example:8202

# Test connectivity
aitbc node test --name my-node

# Hub / island / bridge subcommands
aitbc node hub --help
aitbc node island --help
aitbc node bridge --help
```

## Configuration

### Environment Variables

- `AITBC_RPC_URL`: Default RPC endpoint URL
- `AITBC_COORDINATOR_URL`: Agent coordinator URL
- `AITBC_KEYSTORE_DIR`: Directory for wallet keystore files
- `AITBC_DATA_DIR`: Directory for blockchain data

### Configuration Files

- `/etc/aitbc/blockchain.env`: Node role & blockchain config (`BLOCKCHAIN_MODE`, `MARKET_ROLE`, `HARDWARE_PROFILE`)
- `/etc/aitbc/node.env`: Node-specific configuration
- `~/.aitbc/config`: User-specific configuration

Use `aitbc config --help` for in-CLI configuration management.

## Output Formats

Most commands support multiple output formats via the global `--output` flag:

```bash
# Table (default, human-readable)
aitbc wallet list --output table

# JSON (machine-readable, script-friendly)
aitbc wallet list --output json

# YAML
aitbc wallet list --output yaml

# CSV
aitbc wallet list --output csv
```

## Remote Operations

Connect to remote blockchain/coordinator endpoints:

```bash
# Per-invocation override
aitbc wallet balance my-wallet --url http://remote-node:8203

# Persistent via env var
export AITBC_RPC_URL=http://remote-node:8202
aitbc wallet balance my-wallet
```

## Password Management

Multiple password input methods:

```bash
# Interactive prompt (default)
aitbc wallet send my-wallet --to <address> --amount 1000

# Password file (recommended for scripts)
aitbc wallet send my-wallet --to <address> --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Direct password (NOT recommended for production)
aitbc wallet send my-wallet --to <address> --amount 1000 --password mypassword
```

## Script Integration

```bash
#!/bin/bash
BALANCE=$(aitbc wallet balance my-wallet --output json | jq -r '.balance')

if [ "$BALANCE" -gt "1000" ]; then
  echo "Sufficient balance"
  aitbc wallet send my-wallet --to "$RECIPIENT" --amount 1000 \
    --password-file /var/lib/aitbc/keystore/.password
else
  echo "Insufficient balance: $BALANCE AIT"
fi
```

## Troubleshooting

### Common Issues

**Permission Denied** — keystore files need `600` perms:
```bash
ls -la /var/lib/aitbc/keystore/
chmod 600 /var/lib/aitbc/keystore/*.json
```

**Connection Refused** — verify the RPC service:
```bash
systemctl status aitbc-blockchain-rpc.service
systemctl start aitbc-blockchain-rpc.service
```

**Invalid Wallet** — verify the wallet exists:
```bash
aitbc wallet list
ls -la /var/lib/aitbc/keystore/
```

### Debug Mode

```bash
aitbc --debug wallet balance my-wallet
aitbc -vv network status
```

## Development

### Running from Source

```bash
# Editable install into the shared venv
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/pip install -e .

# Or invoke the module directly without installing
/opt/aitbc/venv/bin/python -m aitbc_cli.core.main --help
```

### Testing

The CLI has two test locations:

```bash
# CLI-internal smoke tests
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/python -m pytest tests/

# Comprehensive command & integration tests (119 files)
cd /opt/aitbc
/opt/aitbc/venv/bin/python -m pytest tests/cli/
```

### Project Layout

See `FILE_ORGANIZATION_SUMMARY.md` for the full directory tree and `docs/FILE_ORGANIZATION_SUMMARY.md` for the docs subdirectory.

## Additional Documentation

- **CLI Usage Guide**: `CLI_USAGE_GUIDE.md` — detailed command examples and workflows
- **File Organization**: `FILE_ORGANIZATION_SUMMARY.md` — directory structure reference
- **Disabled Commands Cleanup**: `docs/DISABLED_COMMANDS_CLEANUP.md` — historical analysis of re-enabled commands
- **Agent SDK**: `packages/py/aitbc-agent-sdk/README.md` — agent development
- **Blockchain docs**: `docs/blockchain/`
- **REST API reference**: `docs/api.html`

## Support

1. Check this README and `CLI_USAGE_GUIDE.md`
2. Run `aitbc <group> --help` for command-specific guidance
3. Run with `--debug` for verbose error information
4. Check system logs in `/var/log/aitbc/`
