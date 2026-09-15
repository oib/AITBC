# AITBC CLI Reference

> **Note**: This document is a curated summary of the most-used command groups.
> The CLI registers ~70 top-level groups — the authoritative list is
> `aitbc --help` or [cli/README.md](../../cli/README.md). For authoritative port
> configuration, see [Service Ports Reference](./SERVICE_PORTS.md).

## Overview

The AITBC CLI provides a comprehensive command-line interface for interacting with the network. It supports wallet management, blockchain operations, AI job submission, marketplace operations, agent orchestration, system administration, and blockchain synchronization.

## Installation

```bash
cd /opt/aitbc
pip install -e .
```

## Global Options

All commands support the following global options:

- `--output {table,json,yaml}`: Output format (default: table)
- `--verbose`: Increase verbosity
- `--debug`: Enable debug mode
- `--version`: Show version and exit
- `--help`: Show help message

## Command Groups

### 1. wallet

Wallet lifecycle, balances, and transactions. The `wallet` group accepts
`--wallet-name` / `--wallet-path` before the subcommand; several subcommands
also take `--name`. Wallet passwords resolve from the keyring,
`AITBC_WALLET_PASSWORD[_<WALLET_NAME>]`, or an interactive prompt.

```bash
# Check balance
aitbc wallet balance --name <wallet-name>

# Create wallet
aitbc wallet create --name <name> [--type hd|simple] [--no-encrypt]

# List wallets
aitbc wallet list

# Switch wallet
aitbc wallet switch --name <name>

# Send funds (--to-address also accepts a wallet name)
aitbc wallet --wallet-name <name> send --to-address <address> --amount <amount>

# Show transaction history
aitbc wallet transactions --name <name> --limit 20
```

### 2. blockchain

Blockchain state and chain management.

```bash
# Check blockchain status
aitbc blockchain status

# List known chains
aitbc blockchain list

# Show chain details
aitbc blockchain info

# Check sync status
aitbc blockchain sync-status

# Live chain monitor
aitbc blockchain monitor
```

For block/transaction lookups use the Explorer group (`aitbc explorer`),
e.g. `aitbc explorer block --height <n>` /
`aitbc explorer transaction --tx-hash <hash>`.

### 3. sync

Blockchain synchronization utilities.

```bash
# Bulk import blocks from a leader to catch up quickly
aitbc sync bulk --source http://leader-url:8202 --import-url http://localhost:8202 --batch-size 100

# Options:
# --source: Source RPC URL (leader node)
# --import-url: Local RPC URL for import
# --batch-size: Blocks per batch (default: 100)
# --poll-interval: Seconds between batches (default: 0.2)

# Follower sync status vs the hub
aitbc sync status
```

### 4. account

Account information and management.

```bash
# Show on-chain account info
aitbc account get --address <0x...>

# List known accounts
aitbc account list
```

### 5. messaging

On-chain forum messaging (falls back to deterministic `(Simulated)` output
when the messaging RPC is unreachable).

```bash
# Send message (--topic takes a topic ID, created automatically if missing)
aitbc messaging send --recipient <agent-address> --message <text> --topic <topic-id>

# List messages
aitbc messaging list

# Create forum topic
aitbc messaging topic --title <title> --description <description>
```

### 6. network

Peer connectivity and network operations.

```bash
# Check network status
aitbc network status

# List connected peers
aitbc network peers

# Test connectivity
aitbc network test --peer <peer-address>
```

### 7. market

Marketplace offers, orders, and escrow.

```bash
# List offers
aitbc market list [--service-type ollama|whisper|ffmpeg|ipfs|hermes]

# Publish an offer
aitbc market offer --service-type ollama --model-or-variant llama3 --price 1.0

# Match offers to demand
aitbc market match

# Escrow lifecycle
aitbc market escrow status --job-id <job_id>
```

### 8. ai

AI job submission and inspection.

```bash
# Submit AI job
aitbc ai submit --wallet <wallet> --type <type> --prompt <prompt> --payment <amount>

# Check job status
aitbc ai status --job-id <job_id>

# List jobs
aitbc ai jobs
```

### 9. analytics

Blockchain analytics and statistics.

```bash
# Get analytics summary
aitbc analytics summary

# Cost/capacity optimization recommendations
aitbc analytics optimize

# Active alerts
aitbc analytics alerts

# Dashboard table
aitbc analytics dashboard
```

### 10. script

Script execution and automation.

```bash
# Run script
aitbc script run --script-path <path/to/script> [--args "..."]

# List scripts
aitbc script list [--script-dir /opt/aitbc/scripts]
```

### 11. mining

Mining lifecycle.

```bash
# Start mining (--wallet-name required)
aitbc mining start --wallet-name <wallet> [--threads 4]

# Stop mining
aitbc mining stop [--wallet <wallet>]

# Check mining status
aitbc mining status

# List registered miners
aitbc mining list
```

### 12. system

System health, service management, and configuration display. `start` /
`stop` / `restart` take `--service <name>`; the name is normalised to the
`aitbc-<name>.service` systemd unit.

```bash
# Check system status
aitbc system status

# Health-check all installed aitbc-* services
aitbc system check

# Restart a service (e.g. aitbc-coordinator-api.service)
aitbc system restart --service coordinator-api
```

### 13. economics

Economic intelligence and modeling.

```bash
# Show economics status for a proposal
aitbc economics status --proposal-id <id>

# Distributed economics model
aitbc economics distributed

# Market economics view
aitbc economics market
```

### 14. cluster

Cluster management operations.

```bash
# Check cluster status
aitbc cluster status

# Sync cluster state
aitbc cluster sync

# Rebalance cluster load
aitbc cluster balance
```

### 15. performance

Performance optimization and metrics.

```bash
# Run a performance benchmark
aitbc performance benchmark

# Apply optimizations
aitbc performance optimize

# Tune parameters
aitbc performance tune
```

### 16. security

Security audit and scanning.

```bash
# Run security audit
aitbc security audit

# Scan for vulnerabilities
aitbc security scan
```

### 17. compliance

Compliance policy, classification, and audit commands.

```bash
# Check whether a data classification is permitted by a framework's policy
aitbc compliance check --framework hipaa --classification phi

# Normalize a data classification label
aitbc compliance classify --label PHI

# Export the compliance audit trail to a JSON file
aitbc compliance export-audit --output-file audit-export.json
```

Frameworks: `hipaa`, `soc2`, `glba`, `pci_dss`, `manufacturing`, `education`, `retail`,
`generic`. Classifications: `public`, `internal`, `restricted`, `confidential`, `pii`,
`phi`, `pci`.

> `aitbc compliance report` was removed in v0.15.2, which replaced the placeholder
> `check`/`report` pair with real policy evaluation. Use `export-audit` to produce a
> compliance artifact.

### 18. simulate

Simulation utilities and testing.

```bash
# Run a named simulation
aitbc simulate run --scenario <scenario> [--params '{...}']

# Deterministic block/wallet simulations
aitbc simulate blockchain --blocks 10
aitbc simulate wallets --wallets 5
```

### 19. agent

AI agent identity and orchestration (agent SDK surface).

```bash
# Create an agent (generates RSA keypair + ~/.aitbc/agents/<name>.json)
aitbc agent create --name <name> --type provider

# List local agents
aitbc agent list

# Check agent status
aitbc agent status --agent-id <agent_id>
```

### 20. workflow

Workflow templates and execution.

```bash
# Run workflow
aitbc workflow run --workflow-name <workflow_name>

# List workflows
aitbc workflow list
```

### 22. resource

Resource utilization and allocation.

```bash
# Allocate resources for an agent
aitbc resource allocate --agent-id <agent-id> --cpu-cores 4 --memory-gb 16

# Optimize resource usage
aitbc resource optimize --agent-id <agent-id>
```

### 23. genesis

Genesis block and wallet generation.

```bash
# Initialize genesis (optionally creating the genesis wallet)
aitbc genesis init --chain-id <chain-id> --create-wallet

# Verify genesis
aitbc genesis verify --chain-id <chain-id>

# Show genesis info
aitbc genesis info --chain-id <chain-id>
```

### 24. pool-hub

Pool hub management for SLA monitoring and billing.

```bash
# Check pool status
aitbc pool-hub status

# SLA summary / violations
aitbc pool-hub sla [--violations] [--pool-id <id>]
```

### 25. bridge

Cross-chain bridge operations.

```bash
# Check bridge health
aitbc bridge health

# Check bridge status
aitbc bridge status

# Lock funds for a transfer
aitbc bridge lock --target-chain <chain> --sender <addr> --recipient <addr> --amount <n>
```

### 26. contract

Smart contract operations.

```bash
# Deploy contract
aitbc contract deploy --contract-name <contract_name>

# Call contract
aitbc contract call --contract-address <contract_address> --method <method>
```

## Examples

### Basic Wallet Operations

```bash
# Create wallet and check balance
aitbc wallet create --name my_wallet
aitbc wallet balance --name my_wallet
```

### AI Job Submission

```bash
# Submit text generation job
aitbc ai submit --wallet my_wallet --type text-generation --prompt "Hello world" --payment 1
```

### Blockchain Operations

```bash
# Check blockchain status and chain info
aitbc blockchain status
aitbc blockchain info
```

### Marketplace Operations

```bash
# List available offers
aitbc market list
```

## Help

For command-specific help:

```bash
aitbc <command> --help
```

For example:

```bash
aitbc wallet --help
aitbc ai --help
```

## Environment Configuration

The CLI uses `/etc/aitbc/.env` for configuration. Key settings include:

- Coordinator API URL: `http://localhost:8203`
- Blockchain RPC: `http://localhost:8202`
- Wallet Daemon: `http://localhost:8108`

For authoritative port configuration, see [Service Ports Reference](./SERVICE_PORTS.md).
