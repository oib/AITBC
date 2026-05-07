---
description: Multi-node blockchain deployment workflow executed by hermes agents using optimized scripts
title: hermes Multi-Node Blockchain Deployment
version: 4.1
---

# hermes Multi-Node Blockchain Deployment Workflow

Two-node AITBC blockchain setup: **aitbc** (genesis authority) + **aitbc1** (follower node).
Coordinated by hermes agents with AI operations, advanced coordination, and genesis reset capabilities.

## 🆕 What's New in v4.1

- **AI Operations Integration**: Complete AI job submission, resource allocation, marketplace participation
- **Advanced Coordination**: Cross-node agent communication via smart contract messaging
- **Genesis Reset Support**: Fresh blockchain creation from scratch with funded wallets
- **Poetry Build System**: Fixed Python package management with modern pyproject.toml format
- **Enhanced CLI**: All 26+ commands verified working with correct syntax
- **Real-time Monitoring**: dev_heartbeat.py for comprehensive health checks
- **Cross-Node Transactions**: Bidirectional AIT transfers between nodes
- **Governance System**: On-chain proposal creation and voting

## Critical CLI Syntax

```bash
# hermes — ALWAYS use --message (long form). -m does NOT work.
hermes agent --agent main --message "task description" --thinking medium

# Session-based (maintains context across calls)
SESSION_ID="deploy-$(date +%s)"
hermes agent --agent main --session-id $SESSION_ID --message "Initialize deployment" --thinking low
hermes agent --agent main --session-id $SESSION_ID --message "Report progress" --thinking medium

# AITBC CLI — always from /opt/aitbc with venv
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli wallet create wallet-name
./aitbc-cli wallet list
./aitbc-cli wallet balance wallet-name
./aitbc-cli wallet send wallet1 address 100 pass
./aitbc-cli blockchain info
./aitbc-cli network status

# AI Operations (NEW)
./aitbc-cli ai submit --wallet wallet --type inference --prompt "Generate image" --payment 100
./aitbc-cli agent create --name ai-agent --description "AI agent"
./aitbc-cli resource allocate --agent-id ai-agent --memory 8192 --duration 3600
./aitbc-cli market create --type ai-inference --price 50 --description "AI Service" --wallet wallet

# Cross-node — always activate venv on remote
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet list'

# RPC checks
curl -s http://localhost:8006/rpc/head | jq '.height'
ssh aitbc1 'curl -s http://localhost:8007/rpc/head | jq .height'

# Smart Contract Messaging (NEW)
curl -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent", "agent_address": "address", "title": "Topic", "description": "Description"}'

# Health Monitoring
python3 /tmp/aitbc1_heartbeat.py
```

## Standardized Paths

| Resource | Path |
|---|---|
| Blockchain data | `/var/lib/aitbc/data/ait-mainnet/` |
| Keystore | `/var/lib/aitbc/keystore/` |
| Central env config | `/etc/aitbc/.env` |
| Workflow scripts | `/opt/aitbc/scripts/workflow-hermes/` |
| Documentation | `/opt/aitbc/docs/hermes/` |
| Logs | `/var/log/aitbc/` |

> All databases go in `/var/lib/aitbc/data/`, NOT in app directories.

## Unique Node Identity Configuration

Each node must have unique `proposer_id` and `p2p_node_id` for proper P2P network operation. The hermes setup scripts automatically generate UUID-based IDs during initial setup.

### Node Identity Files
- `/etc/aitbc/.env` - Contains `proposer_id` for block signing and consensus
- `/etc/aitbc/node.env` - Contains `p2p_node_id` for P2P network identity

### Identity Generation Utility
```bash
# Generate or update unique node IDs (if missing or duplicate)
python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py

# Run on all nodes for remediation
python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py
ssh aitbc1 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'
ssh gitea-runner 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'
```

### Verification
```bash
# Check node IDs are unique across all nodes
echo "=== aitbc ==="
grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env

echo "=== aitbc1 ==="
ssh aitbc1 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'

echo "=== gitea-runner ==="
ssh gitea-runner 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'
```

### P2P Identity Issues
If hermes agents report P2P connection failures due to duplicate IDs:
1. Run the ID generation utility on affected nodes
2. Restart P2P services: `systemctl restart aitbc-blockchain-p2p`
3. Verify connectivity: `journalctl -u aitbc-blockchain-p2p -n 30`
4. Re-run hermes agent coordination to confirm P2P connectivity

## Quick Start

### Full Deployment (Recommended)
```bash
# 1. Complete orchestrated workflow
/opt/aitbc/scripts/workflow-hermes/05_complete_workflow_hermes.sh

# 2. Verify both nodes
curl -s http://localhost:8006/rpc/head | jq '.height'
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# 3. Agent analysis of deployment
hermes agent --agent main --message "Analyze multi-node blockchain deployment status" --thinking high
```

### Phase-by-Phase Execution
```bash
# Phase 1: Pre-flight (tested, working)
/opt/aitbc/scripts/workflow-hermes/01_preflight_setup_hermes_simple.sh

# Phase 2: Genesis authority setup
/opt/aitbc/scripts/workflow-hermes/02_genesis_authority_setup_hermes.sh

# Phase 3: Follower node setup
/opt/aitbc/scripts/workflow-hermes/03_follower_node_setup_hermes.sh

# Phase 4: Wallet operations (tested, working)
/opt/aitbc/scripts/workflow-hermes/04_wallet_operations_hermes_corrected.sh

# Phase 5: Smart contract messaging training
/opt/aitbc/scripts/workflow-hermes/train_agent_messaging.sh
```

## Available Scripts

```
/opt/aitbc/scripts/workflow-hermes/
├── 01_preflight_setup_hermes_simple.sh       # Pre-flight (tested)
├── 01_preflight_setup_hermes_corrected.sh    # Pre-flight (corrected)
├── 02_genesis_authority_setup_hermes.sh      # Genesis authority
├── 03_follower_node_setup_hermes.sh          # Follower node
├── 04_wallet_operations_hermes_corrected.sh  # Wallet ops (tested)
├── 05_complete_workflow_hermes.sh            # Full orchestration
├── fix_agent_communication.sh                  # Agent comm fix
├── train_agent_messaging.sh                    # SC messaging training
└── implement_agent_messaging.sh                # Advanced messaging
```

## Workflow Phases

### Phase 1: Pre-Flight Setup
- Verify hermes gateway running
- Check blockchain services on both nodes
- Validate SSH connectivity to aitbc1
- Confirm data directories at `/var/lib/aitbc/data/ait-mainnet/`
- Initialize hermes agent session

### Phase 2: Genesis Authority Setup
- Configure genesis node environment
- Create genesis block with initial wallets
- Start `aitbc-blockchain-node.service` and `aitbc-blockchain-rpc.service`
- Verify RPC responds on port 8006
- Create genesis wallets

### Phase 3: Follower Node Setup
- SSH to aitbc1, configure environment
- Copy genesis config and start services
- Monitor blockchain synchronization
- Verify follower reaches genesis height
- Confirm P2P connectivity on port 7070

### Phase 4: Wallet Operations
- Create wallets on both nodes
- Fund wallets from genesis authority
- Execute cross-node transactions
- Verify balances propagate

> **Note**: Query wallet balances on the node where the wallet was created.

### Phase 5: Smart Contract Messaging
- Train agents on `AgentMessagingContract`
- Create forum topics for coordination
- Demonstrate cross-node agent communication
- Establish reputation-based interactions

## Multi-Node Architecture

| Node | Role | IP | RPC | P2P |
|---|---|---|---|---|
| aitbc | Genesis authority | 10.1.223.93 | :8006 | :7070 |
| aitbc1 | Follower node | 10.1.223.40 | :8006 | :7070 |

### Wallets
| Node | Wallets |
|---|---|
| aitbc | client-wallet, user-wallet |
| aitbc1 | miner-wallet, aitbc1genesis, aitbc1treasury |

## Service Management

```bash
# Both nodes — services MUST use venv Python
sudo systemctl start aitbc-blockchain-node.service
sudo systemctl start aitbc-blockchain-rpc.service

# Key service config requirements:
#   ExecStart=/opt/aitbc/venv/bin/python -m ...
#   Environment=AITBC_DATA_DIR=/var/lib/aitbc/data
#   Environment=PYTHONPATH=/opt/aitbc/apps/blockchain-node/src
#   EnvironmentFile=/etc/aitbc/.env
```

## Smart Contract Messaging

AITBC's `AgentMessagingContract` enables on-chain agent communication:

- **Message types**: post, reply, announcement, question, answer
- **Forum topics**: Threaded discussions for coordination
- **Reputation system**: Trust levels 1-5
- **Moderation**: Hide, delete, pin messages
- **Cross-node routing**: Messages propagate between nodes

```bash
# Train agents on messaging
hermes agent --agent main --message "Teach me AITBC Agent Messaging Contract for cross-node communication" --thinking high
```

## Troubleshooting

| Problem | Root Cause | Fix |
|---|---|---|
| `--message not specified` | Using `-m` short form | Use `--message` (long form) |
| Agent needs session context | Missing `--session-id` | Add `--session-id $SESSION_ID` |
| `Connection refused :8006` | RPC service down | `sudo systemctl start aitbc-blockchain-rpc.service` |
| `No module 'eth_account'` | System Python vs venv | Fix `ExecStart` to `/opt/aitbc/venv/bin/python` |
| DB in app directory | Hardcoded relative path | Use env var defaulting to `/var/lib/aitbc/data/` |
| Wallet balance 0 on wrong node | Querying wrong node | Query on the node where wallet was created |
| Height mismatch | Wrong data dir | Both nodes: `/var/lib/aitbc/data/ait-mainnet/` |

## Verification Commands

```bash
# Blockchain height (both nodes)
curl -s http://localhost:8006/rpc/head | jq '.height'
ssh aitbc1 'curl -s http://localhost:8007/rpc/head | jq .height'

# Wallets
cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet list
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet list'

# Services
systemctl is-active aitbc-blockchain-{node,rpc}.service
ssh aitbc1 'systemctl is-active aitbc-blockchain-{node,rpc}.service'

# Agent health check
hermes agent --agent main --message "Report multi-node blockchain health" --thinking medium

# Integration test
/opt/aitbc/scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

## Documentation

Reports and guides are in `/opt/aitbc/docs/hermes/`:
- `guides/` — Implementation and fix guides
- `reports/` — Deployment and analysis reports
- `training/` — Agent training materials
