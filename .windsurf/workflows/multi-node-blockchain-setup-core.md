---
description: Core multi-node blockchain setup - prerequisites, environment, and basic node configuration
title: Multi-Node Blockchain Setup - Core Module
version: 1.0
---

# Multi-Node Blockchain Setup - Core Module

This module covers the essential setup steps for a two-node AITBC blockchain network (aitbc as genesis authority, aitbc1 as follower node).

## Prerequisites

- SSH access to both nodes (aitbc1 and aitbc)
- Both nodes have the AITBC repository cloned
- Redis available for cross-node gossip
- Python venv at `/opt/aitbc/venv`
- AITBC CLI tool available (aliased as `aitbc`)
- CLI tool configured to use `/etc/aitbc/.env` by default

## Pre-Flight Setup

Before running the workflow, ensure the following setup is complete:

```bash
# Run the pre-flight setup script
/opt/aitbc/scripts/workflow/01_preflight_setup.sh
```

## Directory Structure

- `/opt/aitbc/venv` - Central Python virtual environment
- `/opt/aitbc/requirements.txt` - Python dependencies (includes CLI dependencies)
- `/etc/aitbc/.env` - Central environment configuration
- `/var/lib/aitbc/data` - Blockchain database files
- `/var/lib/aitbc/keystore` - Wallet credentials
- `/var/log/aitbc/` - Service logs

## Environment Configuration

The workflow uses the single central `/etc/aitbc/.env` file as the configuration for both nodes:

- **Base Configuration**: The central config contains all default settings
- **Node-Specific Adaptation**: Each node adapts the config for its role (genesis vs follower)
- **Path Updates**: Paths are updated to use the standardized directory structure
- **Backup Strategy**: Original config is backed up before modifications
- **Standard Location**: Config moved to `/etc/aitbc/` following system standards
- **CLI Integration**: AITBC CLI tool uses this config file by default

## 🚨 Important: Genesis Block Architecture

**CRITICAL**: Only the genesis authority node (aitbc) should have the genesis block!

```bash
# ❌ WRONG - Do NOT copy genesis block to follower nodes
# scp aitbc:/var/lib/aitbc/data/ait-mainnet/genesis.json aitbc1:/var/lib/aitbc/data/ait-mainnet/

# ✅ CORRECT - Follower nodes sync genesis via blockchain protocol
# aitbc1 will automatically receive genesis block from aitbc during sync
```

**Architecture Overview:**
1. **aitbc (Genesis Authority/Primary Development Server)**: Creates genesis block with initial wallets
2. **aitbc1 (Follower Node)**: Syncs from aitbc, receives genesis block automatically
3. **Wallet Creation**: New wallets attach to existing blockchain using genesis keys
4. **Access AIT Coins**: Genesis wallets control initial supply, new wallets receive via transactions

**Key Principles:**
- **Single Genesis Source**: Only aitbc creates and holds the original genesis block
- **Blockchain Sync**: Followers receive blockchain data through sync protocol, not file copying
- **Wallet Attachment**: New wallets attach to existing chain, don't create new genesis
- **Coin Access**: AIT coins are accessed through transactions from genesis wallets

## Core Setup Steps

### 1. Prepare aitbc (Genesis Authority/Primary Development Server)

```bash
# Run the genesis authority setup script
/opt/aitbc/scripts/workflow/02_genesis_authority_setup.sh
```

### 2. Verify aitbc Genesis State

```bash
# Check blockchain state
curl -s http://localhost:8006/rpc/head | jq .
curl -s http://localhost:8006/rpc/info | jq .
curl -s http://localhost:8006/rpc/supply | jq .

# Check genesis wallet balance
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbcgenesis.json | jq -r '.address')
curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .
```

### 3. Prepare aitbc1 (Follower Node)

```bash
# Run the follower node setup script (executed on aitbc1)
ssh aitbc1 '/opt/aitbc/scripts/workflow/03_follower_node_setup.sh'
```

### 4. Watch Blockchain Sync

```bash
# Monitor sync progress on both nodes
watch -n 5 'echo "=== Genesis Node ===" && curl -s http://localhost:8006/rpc/head | jq .height && echo "=== Follower Node ===" && ssh aitbc1 "curl -s http://localhost:8007/rpc/head | jq .height"'
```

### 5. Basic Wallet Operations

```bash
# Create wallets on genesis node
cd /opt/aitbc && source venv/bin/activate

# Create genesis operations wallet
./aitbc-cli wallet create genesis-ops 123

# Create user wallet
./aitbc-cli wallet create user-wallet 123

# List wallets
./aitbc-cli wallet list

# Check balances
./aitbc-cli wallet balance genesis-ops
./aitbc-cli wallet balance user-wallet
```

### 6. Cross-Node Transaction Test

```bash
# Get follower node wallet address
FOLLOWER_WALLET_ADDR=$(ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet create follower-ops 123 | grep "Address:" | cut -d" " -f2')

# Send transaction from genesis to follower
./aitbc-cli wallet send genesis-ops $FOLLOWER_WALLET_ADDR 1000 123

# Verify transaction on follower node
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet balance follower-ops'
```

## Verification Commands

```bash
# Check both nodes are running
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service'

# Check blockchain heights match
curl -s http://localhost:8006/rpc/head | jq .height
ssh aitbc1 'curl -s http://localhost:8007/rpc/head | jq .height'

# Check network connectivity
ping -c 3 aitbc1
ssh aitbc1 'ping -c 3 localhost'

# Verify wallet creation
./aitbc-cli wallet list
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet list'
```

## Troubleshooting Core Setup

| Problem | Root Cause | Fix |
|---|---|---|
| Services not starting | Environment not configured | Run pre-flight setup script |
| Genesis block not found | Incorrect data directory | Check `/var/lib/aitbc/data/ait-mainnet/` |
| Wallet creation fails | Keystore permissions | Fix `/var/lib/aitbc/keystore/` permissions |
| Cross-node transaction fails | Network connectivity | Verify SSH and RPC connectivity |
| Height mismatch | Sync not working | Check Redis gossip configuration |

## Next Steps

After completing this core setup module, proceed to:

1. **[Operations Module](multi-node-blockchain-operations.md)** - Daily operations and monitoring
2. **[Advanced Features Module](multi-node-blockchain-advanced.md)** - Smart contracts and security testing
3. **[Production Module](multi-node-blockchain-production.md)** - Production deployment and scaling

## Dependencies

This core module is required for all other modules. Complete this setup before proceeding to advanced features.
