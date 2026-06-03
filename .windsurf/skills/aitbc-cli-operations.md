---
description: AITBC CLI tool operations for wallet management, transactions, blockchain analytics, marketplace, AI jobs, mining, simulations
title: aitbc-cli-operations-skill
version: 1.0
---

# AITBC CLI Operations Skill

## Purpose
Execute AITBC CLI tool operations for wallet management, transaction processing, blockchain analytics, marketplace operations, AI compute jobs, mining operations, agent operations, and simulations.

## Activation
Activate when user requests AITBC CLI operations: wallet management (create, import, export, list, delete, rename), transactions (send, balance, history), blockchain analytics (chain info, network status, analytics), marketplace operations (list, create), AI jobs (submit, status), mining (start, stop, status), agent operations (create, execute, list, message), or simulations (blockchain, wallets, price, network, AI jobs).

## Input
```json
{
  "operation": "wallet-create|wallet-import|wallet-export|wallet-list|wallet-delete|wallet-rename|transaction-send|balance-check|transaction-history|chain-info|network-status|analytics|marketplace-list|marketplace-create|ai-job-submit|ai-job-status|mine-start|mine-stop|mine-status|agent-create|agent-execute|agent-list|agent-message|agent-messages|simulate-blockchain|simulate-wallets|simulate-price|simulate-network|simulate-ai-jobs",
  "wallet_name": "string (for wallet operations)",
  "password": "string (for wallet operations requiring password)",
  "password_file": "string (path to password file, optional)",
  "to_address": "string (for transaction-send)",
  "amount": "number (for transaction-send)",
  "fee": "number (for transaction-send, optional, default: 10)",
  "rpc_url": "string (optional, default: http://localhost:8006)",
  "analytics_type": "string (for analytics, optional, default: blocks)",
  "limit": "number (for analytics/transaction-history, optional, default: 10)",
  "item_name": "string (for marketplace-create)",
  "item_price": "number (for marketplace-create)",
  "item_description": "string (for marketplace-create)",
  "job_type": "string (for ai-job-submit)",
  "prompt": "string (for ai-job-submit)",
  "payment": "number (for ai-job-submit)",
  "job_id": "string (for ai-job-status)",
  "threads": "number (for mine-start, optional, default: 1)",
  "agent_name": "string (for agent operations)",
  "agent_address": "string (for agent-message/agent-messages)",
  "message_content": "string (for agent-message)",
  "verification": "string (for agent-create, optional, default: basic)",
  "max_execution_time": "number (for agent-create, optional)",
  "max_cost_budget": "number (for agent-create, optional)",
  "priority": "string (for agent-execute, optional, default: medium)",
  "simulation_blocks": "number (for simulate-blockchain)",
  "simulation_transactions": "number (for simulate-blockchain)",
  "simulation_delay": "number (for simulate-blockchain, optional)",
  "simulation_wallets": "number (for simulate-wallets)",
  "simulation_balance": "number (for simulate-wallets)",
  "simulation_tx_count": "number (for simulate-wallets)",
  "simulation_amount_range": "string (for simulate-wallets, format: min-max)",
  "simulation_price": "number (for simulate-price)",
  "simulation_volatility": "number (for simulate-price)",
  "simulation_timesteps": "number (for simulate-price)",
  "simulation_nodes": "number (for simulate-network)",
  "simulation_network_delay": "number (for simulate-network)",
  "simulation_failure_rate": "number (for simulate-network)",
  "simulation_jobs": "number (for simulate-ai-jobs)",
  "simulation_models": "string (for simulate-ai-jobs, comma-separated)",
  "simulation_duration_range": "string (for simulate-ai-jobs, format: min-max)"
}
```

## Output
```json
{
  "summary": "AITBC CLI operation completed",
  "operation": "string (operation type)",
  "success": "boolean",
  "result": {
    "wallet_address": "string (for wallet-create)",
    "balance": "number (for balance-check)",
    "nonce": "number (for balance-check)",
    "transaction_hash": "string (for transaction-send)",
    "chain_id": "string (for chain-info)",
    "height": "number (for chain-info)",
    "hash": "string (for chain-info)",
    "timestamp": "string (for chain-info)",
    "tx_count": "number (for chain-info)",
    "offers": "array (for marketplace-list)",
    "listing_id": "string (for marketplace-create)",
    "job_id": "string (for ai-job-submit)",
    "job_status": "string (for ai-job-status)",
    "mining_status": "string (for mine-status)",
    "blocks_mined": "number (for mine-status)",
    "agent_id": "string (for agent-create)",
    "execution_id": "string (for agent-execute)",
    "agents": "array (for agent-list)",
    "message_status": "string (for agent-message)",
    "simulation_results": "object (for simulation operations)"
  },
  "error": "string (if operation failed)",
  "cli_output": "string (raw CLI output)",
  "execution_time_ms": "number"
}
```

## CLI Location
**Main CLI:** `/opt/aitbc/aitbc-cli` (shim that delegates to venv binary)

**Usage:** Execute from `/opt/aitbc` directory

**API Version:** All business logic endpoints use `/v1` prefix (coordinator-api, agent-coordinator, marketplace-service, governance-service, trading-service, wallet service, edge-api, agent-management, pool-hub)

**Infrastructure endpoints** (health, ready, live, metrics, docs) do not use `/v1` prefix.

## Operations

### Wallet Management

**wallet-create:** Create new wallet with Ed25519 keypair and AES-256-GCM encryption
```bash
./aitbc-cli create --name <wallet_name> --password <password>
```

**wallet-import:** Import wallet from private key
```bash
./aitbc-cli import --name <wallet_name> --private-key <hex_key> --password <password>
```

**wallet-export:** Export private key from wallet
```bash
./aitbc-cli export --name <wallet_name> --password <password>
```

**wallet-list:** List all wallets
```bash
./aitbc-cli list --format [table|json]
```

**wallet-delete:** Delete wallet
```bash
./aitbc-cli delete --name <wallet_name>
```

**wallet-rename:** Rename wallet
```bash
./aitbc-cli rename --old <old_name> --new <new_name>
```

### Transaction Operations

**transaction-send:** Send AIT transaction
```bash
./aitbc-cli send --from <wallet_name> --to <to_address> --amount <amount> --fee <fee> --password <password> --rpc-url <rpc_url>
```

**balance-check:** Check wallet balance
```bash
./aitbc-cli balance --name <wallet_name> --rpc-url <rpc_url>
```

**transaction-history:** Get transaction history
```bash
./aitbc-cli transactions --name <wallet_name> --limit <limit> --format [table|json] --rpc-url <rpc_url>
```

### Blockchain Analytics

**chain-info:** Get blockchain information
```bash
./aitbc-cli chain --rpc-url <rpc_url>
```

**network-status:** Get network status
```bash
./aitbc-cli network --rpc-url <rpc_url>
```

**analytics:** Get blockchain analytics (blocks, supply, accounts)
```bash
./aitbc-cli analytics --type [blocks|supply|accounts] --limit <limit> --rpc-url <rpc_url>
```

### Mining Operations

**mine-start:** Start mining with specified wallet
```bash
./aitbc-cli mine start --wallet <wallet_name> --threads <threads> --rpc-url <rpc_url>
```

**mine-stop:** Stop mining
```bash
./aitbc-cli mine stop --rpc-url <rpc_url>
```

**mine-status:** Get mining status
```bash
./aitbc-cli mine status --rpc-url <rpc_url>
```

### Marketplace Operations

**marketplace-list:** List marketplace items
```bash
./aitbc-cli marketplace --action list --rpc-url <rpc_url>
./aitbc-cli market-list --rpc-url <rpc_url>
```

**marketplace-create:** Create marketplace listing
```bash
./aitbc-cli marketplace --action create --name <item_name> --price <price> --description <description> --wallet <wallet_name> --rpc-url <rpc_url>
./aitbc-cli market-create --wallet <wallet_name> --type <service_type> --price <price> --description <description> --password <password> --rpc-url <rpc_url>
```

**marketplace-search:** Search marketplace
```bash
./aitbc-cli marketplace --action search --name <search_term> --rpc-url <rpc_url>
```

**marketplace-my-listings:** List my listings
```bash
./aitbc-cli marketplace --action my-listings --wallet <wallet_name> --rpc-url <rpc_url>
```

### AI Compute Operations

**ai-job-submit:** Submit AI compute job
```bash
./aitbc-cli ai-ops submit --wallet <wallet_name> --type <job_type> --prompt <prompt> --payment <payment> --password <password> --rpc-url <rpc_url>
```

**ai-job-status:** Check AI job status
```bash
./aitbc-cli ai-ops status --job-id <job_id> --rpc-url <rpc_url>
```

### Agent Operations

**agent-create:** Create agent
```bash
./aitbc-cli agent create --name <agent_name> --verification <basic|advanced> --max-execution-time <seconds> --max-cost-budget <amount>
```

**agent-execute:** Execute agent
```bash
./aitbc-cli agent execute --name <agent_name> --priority [low|medium|high]
```

**agent-list:** List agents
```bash
./aitbc-cli agent list --status [active|completed|failed]
```

**agent-message:** Send message to agent via blockchain
```bash
./aitbc-cli agent message --agent <agent_address> --message <message_content> --wallet <wallet_name> --password <password> --rpc-url <rpc_url>
```

**agent-messages:** Retrieve agent messages from blockchain
```bash
./aitbc-cli agent messages --agent <agent_address> --rpc-url <rpc_url>
```

**agent-register:** Register agent via CLI
```bash
python3 cli/unified_cli.py agent register --agent-id <agent_id> --agent-type worker --endpoint <endpoint> --capabilities marketplace,messaging
```

### Simulation Operations

**simulate-blockchain:** Simulate blockchain production
```bash
./aitbc-cli simulate blockchain --blocks <number> --transactions <per_block> --delay <seconds>
```

**simulate-wallets:** Simulate wallet operations
```bash
./aitbc-cli simulate wallets --wallets <number> --balance <initial_balance> --transactions <number> --amount-range <min-max>
```

**simulate-price:** Simulate AIT price movements
```bash
./aitbc-cli simulate price --price <starting_price> --volatility <percentage> --timesteps <number> --delay <seconds>
```

**simulate-network:** Simulate network topology
```bash
./aitbc-cli simulate network --nodes <number> --network-delay <seconds> --failure-rate <percentage>
```

**simulate-ai-jobs:** Simulate AI job processing
```bash
./aitbc-cli simulate ai-jobs --jobs <number> --models <model_list> --duration-range <min-max_seconds>
```

## Default Configuration

**Default RPC URL:** `http://localhost:8006`
**Default Keystore Directory:** `/var/lib/aitbc/keystore/`
**Default Wallet Daemon URL:** `http://localhost:8003`
**CLI Version:** 2.1.0

**Service Ports:**
- Coordinator-api: `http://localhost:8011` (uses `/v1` prefix)
- Agent-coordinator: `http://localhost:9001` (uses `/v1` prefix)
- Marketplace-service: `http://localhost:8102` (uses `/v1` prefix)
- Governance-service: `http://localhost:8105` (uses `/v1` prefix)
- Trading-service: `http://localhost:8104` (uses `/v1` prefix)
- Wallet service: `http://localhost:8015` (uses `/v1` prefix)
- Edge-api: `http://localhost:8103` (uses `/v1` prefix)
- Agent-management: `http://localhost:8000` (uses `/v1` prefix)
- Pool-hub: `http://localhost:8012` (uses `/v1` prefix for SLA endpoints)

## Authentication

**Wallet Password:** Required for wallet-create, wallet-import, wallet-export, transaction-send, ai-job-submit, agent-message
**Password File:** Can use `--password-file` instead of `--password`
**Genesis Password Location:** `/var/lib/aitbc/keystore/.genesis_password`

**Chain ID:** Auto-detected from blockchain RPC health endpoint, can override with `--chain-id`

## Common Errors

1. **Wallet Not Found:** Check wallet name spelling, verify keystore directory
2. **Invalid Password:** Verify password, check password file permissions
3. **Invalid Address:** Verify address format (starts with `ait1`)
4. **Insufficient Balance:** Check wallet balance before sending
5. **RPC Connection Failed:** Verify blockchain RPC service is running, check RPC URL
6. **Chain ID Mismatch:** Use `--chain-id` to specify correct chain
7. **Nonce Issues:** CLI automatically fetches actual nonce from blockchain
8. **Private Key Format:** Ensure private key is valid hex string (64 hex characters for Ed25519)
9. **Keystore Encryption:** CLI supports AES-256-GCM and Fernet encryption
10. **Agent Registration Required:** Register agent before using agent commands
11. **Wallet List Import Error:** Pre-existing issue with `utils.dual_mode_wallet_adapter` import (skipped in tests)
12. **GPU List Requires Island Credentials:** Run `aitbc node island join` before using GPU marketplace commands
13. **Blockchain RPC Endpoints:** Use `/rpc` prefix for blockchain RPC operations, not `/v1`

## Recent Updates (May 2026)

**API Standardization:**
- All business logic endpoints now use `/v1` prefix consistently across services
- Infrastructure endpoints (health, ready, live, metrics, docs) remain without `/v1` prefix
- Updated services: coordinator-api, agent-coordinator, marketplace-service, governance-service, trading-service, wallet service, edge-api, agent-management, pool-hub

**Bug Fixes:**
- Fixed blockchain status TypeError by adding `from click import echo` import
- Fixed transactions list by using valid `pending` subcommand instead of non-existent `list` subcommand
- Wallet list import issue documented (pre-existing, unrelated to /v1 prefix work)

**Test Scripts:**
- Created `/opt/aitbc/tests/cli-test-service-health.sh` - Service health check
- Created `/opt/aitbc/tests/cli-test-v1-prefix.sh` - /v1 prefix verification
- Created `/opt/aitbc/tests/cli-test-commands.sh` - CLI command test runner
- Test results: 12/12 CLI tests passing, 9/9 /v1 prefix endpoints responding correctly

## Notes

- `/opt/aitbc/venv/bin/python /opt/aitbc/cli/aitbc_cli.py` is the main CLI entry point
- `cli/unified_cli.py` is a module within the CLI tool for marketplace and messaging operations
- For marketplace operations, prefer `python3 cli/unified_cli.py` (verified working with 7 bugs fixed)
- Messaging commands only available via `python3 cli/unified_cli.py messaging`
- All blockchain RPC operations use HTTP client with timeout handling
- All REST API business logic endpoints use `/v1` prefix for API versioning
- CLI commands that interact with updated services automatically use `/v1` prefix
