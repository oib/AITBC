---
name: aitbc-cli
description: Complete guide for using the AITBC CLI tool - wallet management, transactions, blockchain analytics, marketplace, AI jobs, mining, agent operations, simulations
category: software-development
---

# AITBC CLI Tool Skill

Complete guide for Agent agent to use the AITBC CLI tool (`aitbc`, installed at `/usr/local/bin/aitbc`) for blockchain operations, wallet management, marketplace, AI jobs, mining, and simulations. **This skill ships with AITBC software repository.**

## Trigger Conditions

Load this skill when:
- User asks to use "aitbc" or "AITBC CLI"
- Need to manage wallets (create, import, export, delete, list)
- Need to send transactions or check balances
- Need blockchain analytics or network status
- Need marketplace operations (listings, offers, jobs)
- Need AI compute job operations
- Need mining operations (start, stop, status)
- Need agent operations (create, list, message)
- Need to run simulations (blockchain, wallets, price, network, AI jobs)

## Prerequisites

- AITBC software installed at `/opt/aitbc`
- Python 3.13+ with required dependencies
- Blockchain RPC service running (default: `http://localhost:8202`)
- Wallet keystore directory: `/var/lib/aitbc/keystore/`

## CLI Location

**Main CLI:** `aitbc` — installed at `/usr/local/bin/aitbc` (shell wrapper exec'ing `python -m aitbc_cli.core.main` inside `/opt/aitbc/venv`)

**Usage:**
```bash
aitbc [command] [options]
```

## Step-by-Step Instructions

### 1. Wallet Management

#### Create Wallet
```bash
aitbc wallet create --name <wallet_name>
```

**Example:**
```bash
aitbc wallet create --name my-wallet
```

**Result:** Creates wallet, returns address. Use `--no-encrypt` to skip password encryption (not recommended).

#### Import Wallet
```bash
aitbc wallet import-wallet --file-path <json_file> --name <wallet_name>
```

**Example:**
```bash
aitbc wallet import-wallet --file-path /var/lib/aitbc/wallets/genesis.json --name imported-wallet
```

#### Export Wallet
```bash
aitbc wallet --wallet-name <wallet_name> export --destination <path>
```

#### Delete Wallet
```bash
aitbc wallet delete --name <wallet_name> --confirm
```

#### List Wallets
```bash
aitbc wallet list
aitbc --output json wallet list
```

**Note:** `aitbc list` is kept as a legacy alias for `aitbc wallet list`.

**Result:** Lists all wallets from keystore or wallet daemon

---

### 2. Transaction Operations

#### Send Transaction
```bash
aitbc transactions send \
  --from <wallet_name> \
  --to <recipient_address> \
  --amount <amount> \
  --fee <fee> \
  --password <password> \
  --rpc-url <rpc_url>
```

**Example:**
```bash
aitbc transactions send \
  --from my-wallet \
  --to 0x... \
  --amount 100.0 \
  --fee 10.0 \
  --password "securepassword123" \
  --rpc-url http://localhost:8202
```

**Result:** Returns transaction hash

#### Check Balance
```bash
aitbc wallet balance --name <wallet_name>
```

**Example:**
```bash
aitbc wallet balance --name my-wallet
```

**Result:** Returns balance, nonce, address

#### Get Transaction History
```bash
aitbc wallet transactions --name <wallet_name> --limit <limit>
```

**Example:**
```bash
aitbc wallet transactions --name my-wallet --limit 10
```

---

### 3. Blockchain Analytics

#### Get Chain Status
```bash
aitbc blockchain status [--chain-id <chain_id>] [--node-url <rpc_url>]
```

**Example:**
```bash
aitbc blockchain status --node-url http://localhost:8202
```

**Result:** Chain ID, height, and status for all chains (or one chain with `--chain-id`)

#### Get Blockchain Height
```bash
aitbc blockchain height --node-url <rpc_url>
```

#### Get Network Status
```bash
aitbc network status --rpc-url <rpc_url>
```

**Result:** Head block information, network health

#### Blockchain Analytics
```bash
aitbc analytics summary [--chain-id <chain_id>] [--hours <hours>]
```

**Other analytics subcommands:** `monitor`, `predict`, `optimize`, `alerts`, `dashboard`

**Example:**
```bash
aitbc analytics summary --chain-id ait-mainnet --hours 12
```

---

### 4. Mining Operations

#### Start Mining
```bash
aitbc mining start --wallet-name <wallet_name> --threads <threads> --rpc-url <rpc_url>
```

**Example:**
```bash
aitbc mining start --wallet-name my-wallet --threads 1 --rpc-url http://localhost:8202
```

**Result:** Mining started with specified wallet

#### Stop Mining
```bash
aitbc mining stop --rpc-url <rpc_url>
```

#### Get Mining Status
```bash
aitbc mining status --rpc-url <rpc_url>
```

**Result:** Mining active status, current height, blocks mined, rewards earned

---

### 5. Marketplace Operations

#### List Marketplace Offers
```bash
aitbc market list
```

**Result:** List of available marketplace offers

#### Create Marketplace Offer
```bash
aitbc market offer \
  --service-type <ollama|whisper|ffmpeg|ipfs|hermes> \
  --model-or-variant <model> \
  --price <price> \
  --unit <unit> \
  --description <description>
```

**Example:**
```bash
aitbc market offer \
  --service-type ollama \
  --model-or-variant llama3 \
  --price 100 \
  --description "AI training compute"
```

**Result:** Returns offer ID, provider, price, status

#### List My Offers
```bash
aitbc market offer-list
```

#### List Marketplace Jobs
```bash
aitbc market jobs
```

---

### 6. AI Compute Operations

#### Submit AI Job
```bash
aitbc ai submit \
  --wallet <wallet_name> \
  --type <job_type> \
  --prompt <prompt> \
  --payment <payment> \
  --password <password> \
  --rpc-url <rpc_url>
```

**Example:**
```bash
aitbc ai submit \
  --wallet my-wallet \
  --type "inference" \
  --prompt "Analyze this data" \
  --payment 50 \
  --password "securepassword123" \
  --rpc-url http://localhost:8202
```

**Result:** Job ID, estimated time, payment amount

#### Check AI Job Status
```bash
aitbc ai status --job-id <job_id>
```

#### List AI Jobs
```bash
aitbc ai jobs [--status <status>] [--limit <n>]
```

---

### 7. Agent Operations

#### Create Agent
```bash
aitbc agent create \
  --name <agent_name> \
  --type <provider|consumer> \
  [--max-jobs <n>] [--specialization <spec>]
```

#### List Agents
```bash
aitbc agent list
```

**Note:** Uses the Agent Coordinator at `http://localhost:8107` (`POST /v1/agents/discover`) for real agent discovery — coordinator-api on 8203 has no agent routes

#### Send Message to Agent
```bash
aitbc agent-msg send "<message_content>" \
  --to-agent <agent_id> \
  --wallet <wallet_name> \
  --password <password>
```

**Example:**
```bash
aitbc agent-msg send "Hello agent" \
  --to-agent agent-2 \
  --wallet my-wallet \
  --password "securepassword123"
```

**Result:** Message sent via the Agent Coordinator

#### Retrieve Agent Messages
```bash
aitbc agent-msg receive [--from-agent <agent_id>] [--unread-only] [--limit <n>]
```

**Result:** Lists messages in the agent's inbox

#### Register Agent
```bash
aitbc agent register --agent-id <agent_id>
```

**Note:** For API-based registration, see aitbc.md skill

---

### 8. Workflow Operations

#### Run Workflow
```bash
aitbc workflow run --workflow-name <workflow_name> [--config <file>] [--dry-run]
```

#### List / Inspect Workflows
```bash
aitbc workflow list
aitbc workflow status --workflow-name <workflow_name>
aitbc workflow stop --workflow-name <workflow_name>
```

---

### 9. Resource Operations

#### Check Resource Status
```bash
aitbc resource status [--agent-id <agent_id>] [--limit <n>]
```

#### Allocate Resources
```bash
aitbc resource allocate \
  --agent-id <agent_id> \
  --cpu-cores <cores> \
  --memory-gb <gb> \
  [--gpu-count <n>] [--priority <level>]
```

#### Optimize Resources
```bash
aitbc resource optimize --agent-id <agent_id> --target-metric <latency|accuracy>
```

---

### 10. Simulation Operations

#### Simulate Blockchain
```bash
aitbc simulate blockchain \
  --blocks <number> \
  --transactions <per_block> \
  --delay <seconds>
```

**Example:**
```bash
aitbc simulate blockchain --blocks 10 --transactions 5 --delay 0.5
```

**Result:** Simulates block production with transactions, shows statistics

#### Simulate Wallets
```bash
aitbc simulate wallets \
  --wallets <number> \
  --balance <initial_balance> \
  --transactions <number> \
  --amount-range <min-max>
```

**Example:**
```bash
aitbc simulate wallets --wallets 5 --balance 1000 --transactions 20 --amount-range 1-100
```

#### Simulate Price
```bash
aitbc simulate price \
  --price <starting_price> \
  --volatility <percentage> \
  --timesteps <number> \
  --delay <seconds>
```

**Example:**
```bash
aitbc simulate price --price 100.0 --volatility 0.05 --timesteps 50 --delay 0.1
```

#### Simulate Network
```bash
aitbc simulate network \
  --nodes <number> \
  --network-delay <seconds> \
  --failure-rate <percentage>
```

**Example:**
```bash
aitbc simulate network --nodes 10 --network-delay 0.5 --failure-rate 0.1
```

#### Simulate AI Jobs
```bash
aitbc simulate ai-jobs \
  --jobs <number> \
  --models <model_list> \
  --duration-range <min-max_seconds>
```

**Example:**
```bash
aitbc simulate ai-jobs --jobs 20 --models "llama2,mistral,gemma" --duration-range 30-300
```

---

## Default Configuration

**Default RPC URL:** `http://localhost:8202`

**Default Keystore Directory:** `/var/lib/aitbc/keystore/`

**Default Wallet Daemon URL:** `http://localhost:8108`

---

## Authentication

### Wallet Password
- Required for: send, ai submit, agent-msg send (when signing)
- Can be provided via `--password` or `--password-file`
- Genesis password location: `/var/lib/aitbc/keystore/.genesis_password`

### Password File Usage
```bash
# Using password file
aitbc transactions send --from my-wallet --to 0x... --amount 100 --password-file /var/lib/aitbc/keystore/.genesis_password
```

---

## Chain ID Handling

**Auto-Detection:** CLI automatically detects chain ID from blockchain RPC health endpoint

**Override:** Use `--chain-id` to override auto-detection
```bash
aitbc --chain-id ait-mainnet [command]
```

---

## Pitfalls & Common Errors

### 1. Wallet Not Found
**Error:** `Wallet 'wallet_name' not found`
**Fix:** Check wallet name spelling, verify keystore directory

### 2. Invalid Password
**Error:** `Error decrypting wallet`
**Fix:** Verify password, check password file permissions

### 3. Invalid Address
**Error:** `Invalid recipient address`
**Fix:** Verify address format (starts with `0x`)

### 4. Insufficient Balance
**Error:** Transaction failed (insufficient balance)
**Fix:** Check wallet balance before sending

### 5. RPC Connection Failed
**Error:** `Network error`
**Fix:** Verify blockchain RPC service is running, check RPC URL

### 6. Chain ID Mismatch
**Error:** Transaction rejected (wrong chain)
**Fix:** Use `--chain-id` to specify correct chain or verify auto-detection

### 7. Nonce Issues
**Error:** Transaction rejected (invalid nonce)
**Fix:** CLI automatically fetches actual nonce from blockchain

### 8. Private Key Format
**Error:** `Invalid private key`
**Fix:** Ensure private key is valid hex string

### 9. Keystore Encryption
**Error:** `Unsupported cipher`
**Fix:** CLI supports AES-256-GCM (blockchain-node standard) and Fernet (scripts/utils standard)

### 10. Agent Registration Required
**Error:** Agent operations fail
**Fix:** Register agent via coordinator before using agent commands

---

## Quick Reference

```bash
# Wallet Management
aitbc wallet create --name <name>
aitbc wallet list
aitbc wallet balance --name <name>
aitbc transactions send --from <name> --to <address> --amount <amount> --password <password>

# Blockchain
aitbc blockchain status --node-url http://localhost:8202
aitbc blockchain height --node-url http://localhost:8202
aitbc network status --rpc-url http://localhost:8202
aitbc analytics summary

# Mining
aitbc mining start --wallet-name <name> --threads 1
aitbc mining status
aitbc mining stop

# Marketplace
aitbc market list
aitbc market offer --service-type ollama --model-or-variant <model> --price <price>

# AI Jobs
aitbc ai submit --wallet <name> --type inference --prompt <text> --payment <amount>

# Agents
aitbc agent list
aitbc agent-msg send "<text>" --to-agent <agent> --wallet <name> --password <password>

# Simulations
aitbc simulate blockchain --blocks 10 --transactions 5
aitbc simulate wallets --wallets 5 --balance 1000
aitbc simulate price --price 100 --volatility 0.05
```

---

## Status

**AITBC CLI Tool: FULLY OPERATIONAL**

- All wallet operations working
- Blockchain analytics functional
- Marketplace operations supported
- AI job submission available
- Mining operations operational
- Agent operations with coordinator integration
- Simulation tools for testing and development
- **This skill ships with AITBC software repository**

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Purpose:** Single comprehensive skill for AITBC CLI tool operations
**Location:** `/opt/aitbc/skills/aitbc-cli.md`
