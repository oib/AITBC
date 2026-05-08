---
name: aitbc-cli
description: Complete guide for using the AITBC CLI tool - wallet management, transactions, blockchain analytics, marketplace, AI jobs, mining, agent operations, simulations
category: software-development
---

# AITBC CLI Tool Skill

Complete guide for Hermes agent to use the AITBC CLI tool (`/opt/aitbc/aitbc-cli`) for blockchain operations, wallet management, marketplace, AI jobs, mining, and simulations. **This skill ships with AITBC software repository.**

## Trigger Conditions

Load this skill when:
- User asks to use "aitbc-cli" or "AITBC CLI"
- Need to manage wallets (create, import, export, delete, rename, list)
- Need to send transactions or check balances
- Need blockchain analytics or network status
- Need marketplace operations (listings, create, buy)
- Need AI compute job operations
- Need mining operations (start, stop, status)
- Need agent operations (create, execute, list, message)
- Need to run simulations (blockchain, wallets, price, network, AI jobs)

## Prerequisites

- AITBC software installed at `/opt/aitbc`
- Python 3.13+ with required dependencies
- Blockchain RPC service running (default: `http://localhost:8006`)
- Wallet keystore directory: `/var/lib/aitbc/keystore/`

## CLI Location

**Main CLI:** `/opt/aitbc/aitbc-cli`

**Usage:**
```bash
cd /opt/aitbc
./aitbc-cli [command] [options]
```

## Step-by-Step Instructions

### 1. Wallet Management

#### Create Wallet
```bash
./aitbc-cli create --name <wallet_name> --password <password>
```

**Example:**
```bash
./aitbc-cli create --name my-wallet --password "securepassword123"
```

**Result:** Creates wallet with Ed25519 keypair, AES-256-GCM encryption, returns address

#### Import Wallet
```bash
./aitbc-cli import --name <wallet_name> --private-key <hex_key> --password <password>
```

**Example:**
```bash
./aitbc-cli import --name imported-wallet --private-key "abc123..." --password "securepassword123"
```

#### Export Wallet (Private Key)
```bash
./aitbc-cli export --name <wallet_name> --password <password>
```

#### Delete Wallet
```bash
./aitbc-cli delete --name <wallet_name>
```

#### Rename Wallet
```bash
./aitbc-cli rename --old <old_name> --new <new_name>
```

#### List Wallets
```bash
./aitbc-cli list --format [table|json]
```

**Result:** Lists all wallets from keystore or wallet daemon

---

### 2. Transaction Operations

#### Send Transaction
```bash
./aitbc-cli send \
  --from <wallet_name> \
  --to <recipient_address> \
  --amount <amount> \
  --fee <fee> \
  --password <password> \
  --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli send \
  --from my-wallet \
  --to ait1abc123... \
  --amount 100.0 \
  --fee 10.0 \
  --password "securepassword123" \
  --rpc-url http://localhost:8006
```

**Result:** Returns transaction hash

#### Check Balance
```bash
./aitbc-cli balance --name <wallet_name> --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli balance --name my-wallet --rpc-url http://localhost:8006
```

**Result:** Returns balance, nonce, address

#### Get Transaction History
```bash
./aitbc-cli transactions --name <wallet_name> --limit <limit> --format [table|json] --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli transactions --name my-wallet --limit 10 --format table --rpc-url http://localhost:8006
```

---

### 3. Blockchain Analytics

#### Get Chain Information
```bash
./aitbc-cli chain --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli chain --rpc-url http://localhost:8006
```

**Result:** Chain ID, height, hash, timestamp, proposer ID, supported chains

#### Get Network Status
```bash
./aitbc-cli network --rpc-url <rpc_url>
```

**Result:** Head block information, network health

#### Blockchain Analytics
```bash
./aitbc-cli analytics --type [blocks|supply|accounts] --limit <limit> --rpc-url <rpc_url>
```

**Types:**
- `blocks`: Recent blocks analytics
- `supply`: Total supply information
- `accounts`: Account statistics

**Example:**
```bash
./aitbc-cli analytics --type blocks --limit 10 --rpc-url http://localhost:8006
```

---

### 4. Mining Operations

#### Start Mining
```bash
./aitbc-cli mine start --wallet <wallet_name> --threads <threads> --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli mine start --wallet my-wallet --threads 1 --rpc-url http://localhost:8006
```

**Result:** Mining started with specified wallet

#### Stop Mining
```bash
./aitbc-cli mine stop --rpc-url <rpc_url>
```

#### Get Mining Status
```bash
./aitbc-cli mine status --rpc-url <rpc_url>
```

**Result:** Mining active status, current height, blocks mined, rewards earned

---

### 5. Marketplace Operations

#### List Marketplace Items
```bash
# Via aitbc-cli
./aitbc-cli marketplace --action list --rpc-url <rpc_url>

# Via unified_cli.py
python3 cli/unified_cli.py market list --marketplace-url http://aitbc1:8102
```

**Result:** List of available marketplace items

#### Create Marketplace Listing
```bash
# Via aitbc-cli
./aitbc-cli marketplace \
  --action create \
  --name <item_name> \
  --price <price> \
  --description <description> \
  --wallet <wallet_name> \
  --rpc-url <rpc_url>

# Via unified_cli.py (localhost)
python3 cli/unified_cli.py market create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price_in_AIT> \
  --description <optional_desc>

# Via unified_cli.py (aitbc1 node)
python3 cli/unified_cli.py market create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price_in_AIT> \
  --description <optional_desc> \
  --marketplace-url http://aitbc1:8102
```

**Example (unified_cli.py):**
```bash
python3 cli/unified_cli.py market create \
  --wallet hermes-final \
  --type "complete-demo" \
  --price 999 \
  --description "Full demo" \
  --marketplace-url http://aitbc1:8102
```

**Result:** Returns offer ID (e.g., `0423942b3d4f4ec88968adc52fe4ba36`), provider, price, status (open)

#### Buy/Create Bid
```bash
python3 cli/unified_cli.py market buy \
  --item <offer_id> \
  --wallet <wallet_name> \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://aitbc1:8102
```

**Example:**
```bash
python3 cli/unified_cli.py market buy \
  --item "0423942b3d4f4ec88968adc52fe4ba36" \
  --wallet hermes-final \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://aitbc1:8102
```

**Result:** Bid ID (e.g., `dc74b16ab952432e8cb9ff7a3f97df3d`), status (pending), message

#### List Bids/Orders
```bash
python3 cli/unified_cli.py market orders \
  --wallet <wallet_name> \
  --marketplace-url http://aitbc1:8102
```

**Result:** JSON array of bids/orders

---

### 6. AI Compute Operations

#### Submit AI Job
```bash
./aitbc-cli ai-ops submit \
  --wallet <wallet_name> \
  --type <job_type> \
  --prompt <prompt> \
  --payment <payment> \
  --password <password> \
  --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli ai-ops submit \
  --wallet my-wallet \
  --type "inference" \
  --prompt "Analyze this data" \
  --payment 50 \
  --password "securepassword123" \
  --rpc-url http://localhost:8006
```

**Result:** Job ID, estimated time, payment amount

#### Check AI Job Status
```bash
./aitbc-cli ai-ops status --job-id <job_id> --rpc-url <rpc_url>
```

---

### 7. Messaging Operations

#### List Topics
```bash
python3 cli/unified_cli.py messaging topics --rpc-url http://aitbc1:8006
```

**Result:** Topic ID (e.g., `topic_a89f0525b357a8aa`), title, total topics

#### Create Topic
```bash
python3 cli/unified_cli.py messaging create-topic \
  --title "<title>" \
  --content "<content>" \
  --rpc-url http://aitbc1:8006
```

#### Post Message to Topic
```bash
python3 cli/unified_cli.py messaging post \
  --topic-id <topic_id> \
  --content "<message>" \
  --rpc-url http://aitbc1:8006
```

**Note:** Messaging requires agent registration first (see Agent Registration section)

---

### 8. Agent Operations

#### Create Agent
```bash
./aitbc-cli agent create \
  --name <agent_name> \
  --verification <basic|advanced> \
  --max-execution-time <seconds> \
  --max-cost-budget <amount>
```

#### Execute Agent
```bash
./aitbc-cli agent execute \
  --name <agent_name> \
  --priority [low|medium|high]
```

#### List Agents
```bash
./aitbc-cli agent list --status [active|completed|failed]
```

**Note:** Uses coordinator API at `http://localhost:9001` for real agent discovery

#### Send Message to Agent
```bash
./aitbc-cli agent message \
  --agent <agent_address> \
  --message <message_content> \
  --wallet <wallet_name> \
  --password <password> \
  --rpc-url <rpc_url>
```

**Example:**
```bash
./aitbc-cli agent message \
  --agent ait1abc123... \
  --message "Hello agent" \
  --wallet my-wallet \
  --password "securepassword123" \
  --rpc-url http://localhost:8006
```

**Result:** Message sent via blockchain transaction, returns transaction hash

#### Retrieve Agent Messages
```bash
./aitbc-cli agent messages --agent <agent_address> --rpc-url <rpc_url>
```

**Result:** Lists all messages sent to the agent from blockchain

#### Register Agent (via CLI)
```bash
# CLI method for agent registration
python3 cli/unified_cli.py agent register \
  --agent-id <agent_id> \
  --agent-type worker \
  --endpoint <endpoint> \
  --capabilities marketplace,messaging
```

**Note:** For API-based registration, see aitbc.md skill

---

### 8. Hermes Training Operations

#### Deploy Hermes Agent
```bash
./aitbc-cli hermes deploy --environment [dev|prod]
```

#### Monitor Hermes Agent
```bash
./aitbc-cli hermes monitor --agent-id <agent_id> --metrics [all|performance|cost]
```

#### Train Agent
```bash
./aitbc-cli hermes train \
  --train-action agent \
  --agent-id <agent_id> \
  --stage <stage_name> \
  --training-data <training_data_file>
```

**Example:**
```bash
./aitbc-cli hermes train \
  --train-action agent \
  --agent-id hermes-001 \
  --stage stage1_foundation \
  --training-data /opt/aitbc/docs/agent-training/stage1_foundation.json
```

**Note:** Executes training operations via hermes agent with allowlist enabled

---

### 9. Workflow Operations

#### Create Workflow
```bash
./aitbc-cli workflow create --name <workflow_name> --template [custom|standard]
```

#### Run Workflow
```bash
./aitbc-cli workflow run --name <workflow_name> --async-exec
```

---

### 10. Resource Operations

#### Check Resource Status
```bash
./aitbc-cli resource status --type [all|cpu|memory|storage]
```

#### Allocate Resources
```bash
./aitbc-cli resource allocate \
  --agent-id <agent_id> \
  --cpu <cores> \
  --memory <gb> \
  --duration <minutes>
```

#### Optimize Resources
```bash
./aitbc-cli resource optimize --target [all|cpu|memory] --agent-id <agent_id>
```

#### Benchmark Resources
```bash
./aitbc-cli resource benchmark --type [all|cpu|memory|network]
```

---

### 11. Simulation Operations

#### Simulate Blockchain
```bash
./aitbc-cli simulate blockchain \
  --blocks <number> \
  --transactions <per_block> \
  --delay <seconds>
```

**Example:**
```bash
./aitbc-cli simulate blockchain --blocks 10 --transactions 5 --delay 0.5
```

**Result:** Simulates block production with transactions, shows statistics

#### Simulate Wallets
```bash
./aitbc-cli simulate wallets \
  --wallets <number> \
  --balance <initial_balance> \
  --transactions <number> \
  --amount-range <min-max>
```

**Example:**
```bash
./aitbc-cli simulate wallets --wallets 5 --balance 1000 --transactions 20 --amount-range 1-100
```

#### Simulate Price
```bash
./aitbc-cli simulate price \
  --price <starting_price> \
  --volatility <percentage> \
  --timesteps <number> \
  --delay <seconds>
```

**Example:**
```bash
./aitbc-cli simulate price --price 100.0 --volatility 0.05 --timesteps 50 --delay 0.1
```

#### Simulate Network
```bash
./aitbc-cli simulate network \
  --nodes <number> \
  --network-delay <seconds> \
  --failure-rate <percentage>
```

**Example:**
```bash
./aitbc-cli simulate network --nodes 10 --network-delay 0.5 --failure-rate 0.1
```

#### Simulate AI Jobs
```bash
./aitbc-cli simulate ai-jobs \
  --jobs <number> \
  --models <model_list> \
  --duration-range <min-max_seconds>
```

**Example:**
```bash
./aitbc-cli simulate ai-jobs --jobs 20 --models "llama2,mistral,gemma" --duration-range 30-300
```

---

## Default Configuration

**Default RPC URL:** `http://localhost:8006`

**Default Keystore Directory:** `/var/lib/aitbc/keystore/`

**Default Wallet Daemon URL:** `http://localhost:8003`

**CLI Version:** 2.1.0

---

## Authentication

### Wallet Password
- Required for: create, import, export, send, ai-ops submit, agent message
- Can be provided via `--password` or `--password-file`
- Genesis password location: `/var/lib/aitbc/keystore/.genesis_password`

### Password File Usage
```bash
# Using password file
./aitbc-cli send --from my-wallet --to ait1abc... --amount 100 --password-file /var/lib/aitbc/keystore/.genesis_password
```

---

## Chain ID Handling

**Auto-Detection:** CLI automatically detects chain ID from blockchain RPC health endpoint

**Override:** Use `--chain-id` to override auto-detection
```bash
./aitbc-cli --chain-id ait-mainnet [command]
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
**Fix:** Verify address format (starts with `ait1`)

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
**Fix:** Ensure private key is valid hex string (64 hex characters for Ed25519)

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
./aitbc-cli create --name <name> --password <password>
./aitbc-cli list --format [table|json]
./aitbc-cli balance --name <name>
./aitbc-cli send --from <name> --to <address> --amount <amount> --password <password>

# Blockchain
./aitbc-cli chain --rpc-url http://localhost:8006
./aitbc-cli network --rpc-url http://localhost:8006
./aitbc-cli analytics --type blocks --limit 10

# Mining
./aitbc-cli mine start --wallet <name> --threads 1
./aitbc-cli mine status
./aitbc-cli mine stop

# Marketplace
./aitbc-cli marketplace --action list
./aitbc-cli marketplace --action create --name <name> --price <price>

# AI Jobs
./aitbc-cli ai-ops submit --wallet <name> --type inference --prompt <text> --payment <amount>

# Agents
./aitbc-cli agent list --status active
./aitbc-cli agent message --agent <address> --message <text> --wallet <name> --password <password>

# Simulations
./aitbc-cli simulate blockchain --blocks 10 --transactions 5
./aitbc-cli simulate wallets --wallets 5 --balance 1000
./aitbc-cli simulate price --price 100 --volatility 0.05
```

---

## Status

**AITBC CLI Tool: FULLY OPERATIONAL**

- Version: 2.1.0
- All wallet operations working
- Blockchain analytics functional
- Marketplace operations supported
- AI job submission available
- Mining operations operational
- Agent operations with coordinator integration
- Simulation tools for testing and development
- **This skill ships with AITBC software repository**

---

**Generated by:** Hermes Instructor (localhost)  
**Date:** 2026-05-08  
**Purpose:** Single comprehensive skill for AITBC CLI tool operations  
**Location:** `/opt/aitbc/skills/aitbc-cli/SKILL.md`
