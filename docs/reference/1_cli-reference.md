# AITBC CLI Reference

> **Note**: This document describes the current 26-command CLI structure. For authoritative port configuration, see [Service Ports Reference](./SERVICE_PORTS.md).

## Overview

The AITBC CLI provides a comprehensive command-line interface with 26 command groups for interacting with the AITBC network. It supports wallet management, blockchain operations, AI job submission, marketplace operations, agent orchestration, system administration, and blockchain synchronization.

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
Wallet lifecycle, balances, and transactions.

```bash
# Check balance
aitbc wallet balance

# Create wallet
aitbc wallet create <name> --password <password>

# List wallets
aitbc wallet list

# Switch wallet
aitbc wallet switch <name>

# Send funds
aitbc wallet send <address> <amount>

# Show history
aitbc wallet history
```

### 2. blockchain
Blockchain state and block inspection.

```bash
# Check blockchain status
aitbc blockchain status

# List recent blocks
aitbc blockchain blocks --limit 10

# Get block details
aitbc blockchain block <block_hash>

# Get transaction details
aitbc blockchain transaction <tx_hash>

# Check sync status
aitbc blockchain sync-status

# List peers
aitbc blockchain peers
```

### 3. sync
Blockchain synchronization utilities.

```bash
# Bulk import blocks from a leader to catch up quickly
aitbc sync bulk --source http://leader-url:8006 --import-url http://localhost:8006 --batch-size 100

# Options:
# --source: Source RPC URL (leader node)
# --import-url: Local RPC URL for import
# --batch-size: Blocks per batch (default: 100)
# --poll-interval: Seconds between batches (default: 0.2)
```

### 4. account
Account information and management.

```bash
# Show account info
aitbc account info

# List accounts
aitbc account list
```

### 5. messaging
Messaging system and forum operations.

```bash
# Send message
aitbc messaging send <recipient> <message>

# List messages
aitbc messaging list

# Create forum topic
aitbc messaging topic create <title> <description>
```

### 6. network
Peer connectivity and network operations.

```bash
# Check network status
aitbc network status

# List connected peers
aitbc network peers

# Test connectivity
aitbc network test <peer>
```

### 7. market
Marketplace listings and offers.

```bash
# List offers
aitbc market offers

# Create offer
aitbc market offer create <type> <price>

# List bids
aitbc market bids

# Place bid
aitbc market bid <offer_id> <amount>
```

### 8. ai
AI job submission and inspection.

```bash
# Submit AI job
aitbc ai submit --wallet <wallet> --type <type> --prompt <prompt> --payment <amount>

# Check job status
aitbc ai status <job_id>

# List jobs
aitbc ai list
```

### 9. analytics
Blockchain analytics and statistics.

```bash
# Get analytics
aitbc analytics stats

# Generate report
aitbc analytics report <type>
```

### 10. script
Script execution and automation.

```bash
# Run script
aitbc script run <script_name>

# List scripts
aitbc script list
```

### 11. mining
Mining lifecycle and rewards.

```bash
# Start mining
aitbc mining start

# Stop mining
aitbc mining stop

# Check mining status
aitbc mining status

# View rewards
aitbc mining rewards
```

### 12. system
System health and overview.

```bash
# Check system status
aitbc system status

# Show system info
aitbc system info

# Check health
aitbc system health
```

### 13. economics
Economic intelligence and modeling.

```bash
# Get economic stats
aitbc economics stats

# Analyze trends
aitbc economics analyze <metric>
```

### 14. cluster
Cluster management operations.

```bash
# Check cluster status
aitbc cluster status

# List nodes
aitbc cluster nodes
```

### 15. performance
Performance optimization and metrics.

```bash
# Get performance metrics
aitbc performance metrics

# Optimize
aitbc performance optimize
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
Compliance checking and reporting.

```bash
# Check compliance
aitbc compliance check

# Generate report
aitbc compliance report
```

### 18. simulate
Simulation utilities and testing.

```bash
# Run simulation
aitbc simulate run <scenario>

# List scenarios
aitbc simulate list
```

### 19. agent
AI agent workflow orchestration.

```bash
# Start agent
aitbc agent start <agent_id>

# Stop agent
aitbc agent stop <agent_id>

# List agents
aitbc agent list
```

### 20. hermes-training
hermes agent training operations.

```bash
# Start training
aitbc hermes-training start <config>

# Check training status
aitbc hermes-training status
```

### 21. workflow
Workflow templates and execution.

```bash
# Run workflow
aitbc workflow run <workflow_name>

# List workflows
aitbc workflow list
```

### 22. resource
Resource utilization and allocation.

```bash
# Check resources
aitbc resource check

# Allocate resources
aitbc resource allocate <type> <amount>
```

### 23. genesis
Genesis block and wallet generation.

```bash
# Generate genesis block
aitbc genesis generate

# Create genesis wallet
aitbc genesis wallet create
```

### 24. pool-hub
Pool hub management for SLA monitoring and billing.

```bash
# Check pool status
aitbc pool-hub status

# Monitor SLA
aitbc pool-hub sla monitor
```

### 25. bridge
Blockchain event bridge management.

```bash
# Start bridge
aitbc bridge start

# Check bridge status
aitbc bridge status
```

### 26. contract
Smart contract operations.

```bash
# Deploy contract
aitbc contract deploy <contract_name>

# Call contract
aitbc contract call <contract_address> <method>
```

## Examples

### Basic Wallet Operations

```bash
# Create wallet and check balance
aitbc wallet create my_wallet --password secret123
aitbc wallet balance
```

### AI Job Submission

```bash
# Submit text generation job
aitbc ai submit --wallet my_wallet --type text-generation --prompt "Hello world" --payment 1
```

### Blockchain Operations

```bash
# Check blockchain status and recent blocks
aitbc blockchain status
aitbc blockchain blocks --limit 10
```

### Marketplace Operations

```bash
# List available offers and place a bid
aitbc market offers
aitbc market bid offer123 10
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

- Coordinator API URL: `http://localhost:8011`
- Blockchain RPC: `http://localhost:8006`
- Wallet Daemon: `http://localhost:8015`

For authoritative port configuration, see [Service Ports Reference](./SERVICE_PORTS.md).
