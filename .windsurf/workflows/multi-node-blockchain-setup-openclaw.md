---
description: Multi-node blockchain deployment workflow executed by OpenClaw agents using optimized scripts
title: OpenClaw Multi-Node Blockchain Deployment
version: 4.1
---

# OpenClaw Multi-Node Blockchain Deployment Workflow

Two-node AITBC blockchain setup: **aitbc** (genesis authority) + **aitbc1** (follower node).
Coordinated by OpenClaw agents with AI operations, advanced coordination, and genesis reset capabilities.

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
# OpenClaw — ALWAYS use --message (long form). -m does NOT work.
openclaw agent --agent main --message "task description" --thinking medium

# Session-based (maintains context across calls)
SESSION_ID="deploy-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Initialize deployment" --thinking low
openclaw agent --agent main --session-id $SESSION_ID --message "Report progress" --thinking medium

# AITBC CLI — always from /opt/aitbc with venv
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli create --name wallet-name
./aitbc-cli list
./aitbc-cli balance --name wallet-name
./aitbc-cli send --from wallet1 --to address --amount 100 --password pass
./aitbc-cli chain
./aitbc-cli network

# AI Operations (NEW)
./aitbc-cli ai-submit --wallet wallet --type inference --prompt "Generate image" --payment 100
./aitbc-cli agent create --name ai-agent --description "AI agent"
./aitbc-cli resource allocate --agent-id ai-agent --gpu 1 --memory 8192 --duration 3600
./aitbc-cli marketplace --action create --name "AI Service" --price 50 --wallet wallet

# Cross-node — always activate venv on remote
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli list'

# RPC checks
curl -s http://localhost:8006/rpc/head | jq '.height'
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

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
| Workflow scripts | `/opt/aitbc/scripts/workflow-openclaw/` |
| Documentation | `/opt/aitbc/docs/openclaw/` |
| Logs | `/var/log/aitbc/` |

> All databases go in `/var/lib/aitbc/data/`, NOT in app directories.

## Quick Start

### Full Deployment (Recommended)
```bash
# 1. Complete orchestrated workflow
/opt/aitbc/scripts/workflow-openclaw/05_complete_workflow_openclaw.sh

# 2. Verify both nodes
curl -s http://localhost:8006/rpc/head | jq '.height'
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# 3. Agent analysis of deployment
openclaw agent --agent main --message "Analyze multi-node blockchain deployment status" --thinking high
```

### Phase-by-Phase Execution
```bash
# Phase 1: Pre-flight (tested, working)
/opt/aitbc/scripts/workflow-openclaw/01_preflight_setup_openclaw_simple.sh

# Phase 2: Genesis authority setup
/opt/aitbc/scripts/workflow-openclaw/02_genesis_authority_setup_openclaw.sh

# Phase 3: Follower node setup
/opt/aitbc/scripts/workflow-openclaw/03_follower_node_setup_openclaw.sh

# Phase 4: Wallet operations (tested, working)
/opt/aitbc/scripts/workflow-openclaw/04_wallet_operations_openclaw_corrected.sh

# Phase 5: Smart contract messaging training
/opt/aitbc/scripts/workflow-openclaw/train_agent_messaging.sh
```

## Available Scripts

```
/opt/aitbc/scripts/workflow-openclaw/
├── 01_preflight_setup_openclaw_simple.sh       # Pre-flight (tested)
├── 01_preflight_setup_openclaw_corrected.sh    # Pre-flight (corrected)
├── 02_genesis_authority_setup_openclaw.sh      # Genesis authority
├── 03_follower_node_setup_openclaw.sh          # Follower node
├── 04_wallet_operations_openclaw_corrected.sh  # Wallet ops (tested)
├── 05_complete_workflow_openclaw.sh            # Full orchestration
├── fix_agent_communication.sh                  # Agent comm fix
├── train_agent_messaging.sh                    # SC messaging training
└── implement_agent_messaging.sh                # Advanced messaging
```

## Workflow Phases

### Phase 1: Pre-Flight Setup
- Verify OpenClaw gateway running
- Check blockchain services on both nodes
- Validate SSH connectivity to aitbc1
- Confirm data directories at `/var/lib/aitbc/data/ait-mainnet/`
- Initialize OpenClaw agent session

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
openclaw agent --agent main --message "Teach me AITBC Agent Messaging Contract for cross-node communication" --thinking high
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
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# Wallets
cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli list
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli list'

# Services
systemctl is-active aitbc-blockchain-{node,rpc}.service
ssh aitbc1 'systemctl is-active aitbc-blockchain-{node,rpc}.service'

# Agent health check
openclaw agent --agent main --message "Report multi-node blockchain health" --thinking medium

# Integration test
/opt/aitbc/.windsurf/skills/openclaw-aitbc/setup.sh test
```

## Documentation

Reports and guides are in `/opt/aitbc/docs/openclaw/`:
- `guides/` — Implementation and fix guides
- `reports/` — Deployment and analysis reports
- `training/` — Agent training materials
