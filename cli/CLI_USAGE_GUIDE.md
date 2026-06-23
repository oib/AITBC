# AITBC CLI - Complete Usage Guide

## Overview

The AITBC CLI provides comprehensive blockchain, wallet, marketplace, AI compute, agent, and federated mesh management capabilities. It is built on Click with a nested command-group structure and supports table, JSON, YAML, and CSV output.

- **Runtime version**: 2.1.0
- **Package**: `aitbc-cli`
- **Entry point**: `aitbc_cli.core.main:main`
- **Invocation**: `aitbc` (wrapper at `/usr/local/bin/aitbc` → `/opt/aitbc/venv/bin/python -m aitbc_cli.core.main`)

## Installation

The CLI is installed by `scripts/deployment/setup.sh` as an editable package into the shared venv at `/opt/aitbc/venv`:

```bash
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/pip install -e .
```

The deployment script also writes a wrapper at `/usr/local/bin/aitbc` so the command is available system-wide without activating the venv.

Verify the install:

```bash
aitbc --version
# aitbc, version 2.1.0
```

## Command Groups

The CLI registers 50+ top-level command groups in `aitbc_cli/core/main.py`. Run `aitbc --help` to see the live list. The groups fall into the following functional areas:

### Wallet & Transactions
- `wallet` — create, list, balance, send, import/export, stake/unstake, multisig, request-payment, rewards
- `transactions` — transaction management
- `account` — account information and management
- `coin-requests` — coin transfer request management

### Blockchain & Chains
- `blockchain` — multi-chain management (info, list, create, add, remove, migrate, backup, restore, monitor)
- `chain` — alias for chain operations
- `genesis` — genesis block and wallet generation
- `explorer` — blockchain explorer data access
- `analytics` — chain analytics and monitoring
- `simulate` — blockchain scenario simulation

### Network & Sync
- `network` — peer connectivity, subscriptions, heartbeat, lease-status
- `sync` — blockchain synchronization (`bulk` import from leader)
- `bridge` — blockchain event bridge management
- `crosschain` — cross-chain trading operations
- `messaging` — messaging system and forum operations

### Marketplace & Exchange
- `market` — on-chain GPU marketplace (offer, list, match, escrow, run, transcribe, transcode, rate, ratings)
- `marketplace` — global chain marketplace (legacy compat)
- `exchange` — exchange integration and trading (register, create-pair, add-liquidity, start-trading, status, monitor)
- `exchange-island` — AIT/BTC/ETH trading on islands
- `gpu` — local GPU hardware management
- `gpu-onchain` — on-chain GPU resource tracking
- `pool-hub` — pool hub SLA monitoring and billing

### AI & Agents
- `ai` — AI compute jobs (submit, jobs, status, cancel, results, stats, service)
- `agent` — agent SDK & coordinator (create, register, list, status, capabilities, submit, jobs, workflow, config-*)
- `agent-comm` — cross-chain agent communication
- `hermes` — Agent messaging via Agent Coordinator (ping, send, receive, peers, request-coins)
- `workflow` — workflow automation
- `edge` — edge API (island, GPU, database, serve)

### Mining & Resources
- `mining` — mining operations (start, stop, status, list)
- `resource` — resource management (EXPERIMENTAL)
- `operations` — general operations
- `performance` — performance monitoring and optimization

### Node / Federated Mesh
- `node` — node management (add, list, info, remove, test, bridge, chain, hub, island, monitor)
- `cluster` — cluster management
- `reputation` — reputation management

### Governance & Economics
- `governance` — governance operations
- `economics` — economic intelligence and modeling
- `contract` — smart contract operations

### System & Security
- `system` — system management (architect, audit, check, config, restart, status)
- `security` — security audit and monitoring
- `compliance` — compliance checking and reporting
- `monitor` — monitoring, metrics, and alerts
- `config` — manage CLI configuration
- `script` — script execution and management

### Misc
- `list` — legacy wallet list alias
- `version` — show version information

## Common Workflows

### 1. Wallet Setup

```bash
# Create wallet
aitbc wallet create my-wallet --password-file /var/lib/aitbc/keystore/.password

# Get wallet address
WALLET_ADDR=$(aitbc wallet address my-wallet --output json | jq -r '.address')

# Check balance
aitbc wallet balance my-wallet
```

### 2. Transaction Workflow

```bash
# Check sender balance
aitbc wallet balance sender-wallet

# Send transaction
aitbc wallet send sender-wallet --to "$WALLET_ADDR" --amount 1000 \
  --password-file /var/lib/aitbc/keystore/.password

# Monitor transactions
aitbc wallet transactions sender-wallet --limit 10

# Check recipient balance
aitbc wallet balance recipient-wallet
```

### 3. Network Monitoring

```bash
aitbc network status
aitbc network peers
aitbc blockchain info
```

### 4. All Wallet Balances

```bash
for wallet in $(aitbc wallet list --output json | jq -r '.[].name'); do
  echo "Wallet: $wallet"
  aitbc wallet balance "$wallet"
  echo "---"
done
```

### 5. Follower Subscribe to Hub

```bash
# Register this node as a follower for block subscription
aitbc network subscribe --hub-url https://hub.aitbc.bubuit.net

# Check lease status
aitbc network lease-status

# Send heartbeat to extend subscription lease
aitbc network heartbeat

# Bulk catch up from leader
aitbc sync bulk --leader-url http://hub.aitbc.bubuit.net:8202
```

### 6. Hermes Ping/Pong (Follower ↔ Hub)

```bash
# Ping the hub coordinator and wait for PONG
aitbc hermes ping \
  --agent hub-coordinator \
  --sender my-follower-agent \
  --coordinator-url http://hub.aitbc.bubuit.net:8203 \
  --timeout 10 \
  --interval 0.5
```

Posts a `PING` to `/v1/hermes/messages/send` and polls `/v1/hermes/messages/{sender}` for the `PONG` reply.

### 7. AI Job Submission

```bash
aitbc ai submit --wallet my-wallet --type text-generation --prompt "Hello world" --payment 10
aitbc ai jobs
aitbc ai status --job-id <job-id>
aitbc ai results --job-id <job-id>
```

### 8. Agent SDK

```bash
aitbc agent create --name gpu-provider --type provider --gpu-memory 24 --models llama3.2,mistral
aitbc agent register --agent-id <agent-id> --coordinator-url http://localhost:8203
aitbc agent capabilities
aitbc agent list
aitbc agent status --agent-id <agent-id>
```

### 9. Mining

```bash
aitbc mining start --wallet my-wallet --threads 4
aitbc mining status
aitbc mining list
aitbc mining stop
```

### 10. On-chain GPU Marketplace

```bash
aitbc market list
aitbc market offer --gpu-id gpu-0 --memory 24 --price 100
aitbc market match
aitbc market run --offer-id <offer-id> --input input.json
aitbc market rate --offer-id <offer-id> --rating 5
aitbc market ratings --offer-id <offer-id>
```

### 11. Cross-Node Operations

```bash
# Local
aitbc network status

# Remote via SSH
ssh aitbc 'aitbc network status'

# Send cross-node
aitbc wallet send genesis --to "$AITBC_WALLET_ADDR" --amount 1000 \
  --password-file /var/lib/aitbc/keystore/.password

# Check balance on remote
ssh aitbc 'aitbc wallet balance aitbc-user'
```

## Output Formats

Most commands honor the global `--output` flag:

```bash
aitbc wallet list --output table   # default, human-readable
aitbc wallet list --output json    # machine-readable, script-friendly
aitbc wallet list --output yaml
aitbc wallet list --output csv
```

## Remote Node Operations

```bash
# Per-invocation override
aitbc wallet balance my-wallet --url http://remote-node:8203

# Persistent via env var
export AITBC_RPC_URL=http://remote-node:8202
aitbc wallet balance my-wallet
```

## Password Management

```bash
# Interactive prompt (default)
aitbc wallet send my-wallet --to <address> --amount 1000

# Password file (recommended for scripts)
aitbc wallet send my-wallet --to <address> --amount 1000 \
  --password-file /var/lib/aitbc/keystore/.password

# Direct password (NOT recommended for production)
aitbc wallet send my-wallet --to <address> --amount 1000 --password mypassword
```

## Script Integration

```bash
#!/bin/bash
BALANCE=$(aitbc wallet balance my-wallet --output json | jq -r '.balance')

if [ "$BALANCE" -gt "1000" ]; then
  echo "Sufficient balance for transaction"
  aitbc wallet send my-wallet --to "$RECIPIENT" --amount 1000 \
    --password-file /var/lib/aitbc/keystore/.password
else
  echo "Insufficient balance: $BALANCE AIT"
fi
```

## Error Handling

The CLI uses specific exception types throughout the codebase:

- **Network**: `ConnectionError`, `Timeout`, `HTTPError`
- **File I/O**: `FileNotFoundError`, `PermissionError`, `IOError`
- **Data**: `JSONDecodeError`, `KeyError`, `StopIteration`
- **System**: `OSError`, `psutil.Error`

User-facing error messages cover:
- **Wallet Not Found** — clear message when wallet doesn't exist
- **Invalid Parameters** — detailed parameter validation
- **Network Errors** — RPC connectivity issues with hints
- **Transaction Errors** — detailed transaction failure context
- **System Errors** — system-level errors with context

## Security Best Practices

1. **Password Management** — use `--password-file` instead of `--password`
2. **File Permissions** — keystore files should be `600`
3. **Network Security** — use HTTPS for RPC endpoints in production
4. **Backup** — regularly back up keystore files (`aitbc wallet backup`)
5. **Validation** — always verify transaction details before sending

## Troubleshooting

| Issue | Fix |
|---|---|
| Permission Denied | `chmod 600 /var/lib/aitbc/keystore/*.json` |
| Connection Refused | `systemctl status aitbc-blockchain-rpc.service` |
| Invalid Password | verify password file contents |
| Wallet Not Found | `aitbc wallet list` to verify name |

### Debug Mode

```bash
aitbc --debug wallet balance my-wallet
aitbc -vv network status
```

## Testing

```bash
# CLI-internal smoke tests (6 files)
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/python -m pytest tests/

# Comprehensive command & integration tests (119 files)
cd /opt/aitbc
/opt/aitbc/venv/bin/python -m pytest tests/cli/
```

## Support

1. Check the error messages for specific guidance
2. Run `aitbc <group> --help` for command-specific usage
3. Verify network connectivity and service status
4. Review this guide and `README.md`
5. Check system logs in `/var/log/aitbc/`
