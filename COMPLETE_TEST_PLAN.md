# AITBC Complete Test Plan - Genesis to Full Operations
# Using OpenClaw Skills and Workflow Scripts

## 🎯 Test Plan Overview
Sequential testing from genesis block generation through full AI operations using OpenClaw agents and skills.

## 📋 Prerequisites Check
```bash
# Verify OpenClaw is running
openclaw status

# Verify all AITBC services are running
systemctl list-units --type=service --state=running | grep aitbc

# Check wallet access
ls -la /var/lib/aitbc/keystore/
```

## 🚀 Phase 1: Genesis Block Generation (OpenClaw)

### Step 1.1: Pre-flight Setup
**Skill**: `openclaw-agent-testing-skill`
**Script**: `01_preflight_setup_openclaw.sh`

```bash
# Create OpenClaw session
SESSION_ID="genesis-test-$(date +%s)"

# Test OpenClaw agents first
openclaw agent --agent main --message "Execute openclaw-agent-testing-skill with operation: comprehensive, thinking_level: medium" --thinking medium

# Run pre-flight setup
/opt/aitbc/scripts/workflow-openclaw/01_preflight_setup_openclaw.sh
```

### Step 1.2: Genesis Authority Setup
**Skill**: `aitbc-basic-operations-skill`
**Script**: `02_genesis_authority_setup_openclaw.sh`

```bash
# Setup genesis node using OpenClaw
openclaw agent --agent main --message "Execute aitbc-basic-operations-skill to setup genesis authority, create genesis block, and initialize blockchain services" --thinking medium

# Run genesis setup script
/opt/aitbc/scripts/workflow-openclaw/02_genesis_authority_setup_openclaw.sh
```

### Step 1.3: Verify Genesis Block
**Skill**: `aitbc-transaction-processor`

```bash
# Verify genesis block creation
openclaw agent --agent main --message "Execute aitbc-transaction-processor to verify genesis block, check block height 0, and validate chain state" --thinking medium

# Manual verification
curl -s http://localhost:8006/rpc/head | jq '.height'
```

## 🔗 Phase 2: Follower Node Setup

### Step 2.1: Follower Node Configuration
**Skill**: `aitbc-basic-operations-skill`
**Script**: `03_follower_node_setup_openclaw.sh`

```bash
# Setup follower node (aitbc1)
openclaw agent --agent main --message "Execute aitbc-basic-operations-skill to setup follower node, connect to genesis, and establish sync" --thinking medium

# Run follower setup (from aitbc, targets aitbc1)
/opt/aitbc/scripts/workflow-openclaw/03_follower_node_setup_openclaw.sh
```

### Step 2.2: Verify Cross-Node Sync
**Skill**: `openclaw-agent-communicator`

```bash
# Test cross-node communication
openclaw agent --agent main --message "Execute openclaw-agent-communicator to verify aitbc1 sync with genesis node" --thinking medium

# Check sync status
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq ".height"'
```

## 💰 Phase 3: Wallet Operations

### Step 3.1: Cross-Node Wallet Creation
**Skill**: `aitbc-wallet-manager`
**Script**: `04_wallet_operations_openclaw.sh`

```bash
# Create wallets on both nodes
openclaw agent --agent main --message "Execute aitbc-wallet-manager to create cross-node wallets and establish wallet infrastructure" --thinking medium

# Run wallet operations
/opt/aitbc/scripts/workflow-openclaw/04_wallet_operations_openclaw.sh
```

### Step 3.2: Fund Wallets & Initial Transactions
**Skill**: `aitbc-transaction-processor`

```bash
# Fund wallets from genesis
openclaw agent --agent main --message "Execute aitbc-transaction-processor to fund wallets and execute initial cross-node transactions" --thinking medium

# Verify transactions
curl -s http://localhost:8006/rpc/balance/<wallet_address>
```

## 🤖 Phase 4: AI Operations Setup

### Step 4.1: Coordinator API Testing
**Skill**: `aitbc-ai-operator`

```bash
# Test AI coordinator functionality
openclaw agent --agent main --message "Execute aitbc-ai-operator to test coordinator API, job submission, and AI service integration" --thinking medium

# Test API endpoints
curl -s http://localhost:8000/health
curl -s http://localhost:8000/docs
```

### Step 4.2: GPU Marketplace Setup
**Skill**: `aitbc-marketplace-participant`

```bash
# Initialize GPU marketplace
openclaw agent --agent main --message "Execute aitbc-marketplace-participant to setup GPU marketplace, register providers, and prepare for AI jobs" --thinking medium

# Verify marketplace status
curl -s http://localhost:8000/api/marketplace/stats
```

## 🧪 Phase 5: Complete AI Workflow Testing

### Step 5.1: Ollama GPU Testing
**Skill**: `ollama-gpu-testing-skill`
**Script**: Reference `ollama-gpu-test-openclaw.md`

```bash
# Execute complete Ollama GPU test
openclaw agent --agent main --message "Execute ollama-gpu-testing-skill with complete end-to-end test: client submission → GPU processing → blockchain recording" --thinking high

# Monitor job progress
curl -s http://localhost:8000/api/jobs
```

### Step 5.2: Advanced AI Operations
**Skill**: `aitbc-ai-operations-skill`
**Script**: `06_advanced_ai_workflow_openclaw.sh`

```bash
# Run advanced AI workflow
openclaw agent --agent main --message "Execute aitbc-ai-operations-skill with advanced AI job processing, multi-modal RL, and agent coordination" --thinking high

# Execute advanced workflow script
/opt/aitbc/scripts/workflow-openclaw/06_advanced_ai_workflow_openclaw.sh
```

## 🔄 Phase 6: Agent Coordination Testing

### Step 6.1: Multi-Agent Coordination
**Skill**: `openclaw-agent-communicator`
**Script**: `07_enhanced_agent_coordination.sh`

```bash
# Test agent coordination
openclaw agent --agent main --message "Execute openclaw-agent-communicator to establish multi-agent coordination and cross-node agent messaging" --thinking high

# Run coordination script
/opt/aitbc/scripts/workflow-openclaw/07_enhanced_agent_coordination.sh
```

### Step 6.2: AI Economics Testing
**Skill**: `aitbc-marketplace-participant`
**Script**: `08_ai_economics_masters.sh`

```bash
# Test AI economics and marketplace dynamics
openclaw agent --agent main --message "Execute aitbc-marketplace-participant to test AI economics, pricing models, and marketplace dynamics" --thinking high

# Run economics test
/opt/aitbc/scripts/workflow-openclaw/08_ai_economics_masters.sh
```

## 📊 Phase 7: Complete Integration Test

### Step 7.1: End-to-End Workflow
**Script**: `05_complete_workflow_openclaw.sh`

```bash
# Execute complete workflow
openclaw agent --agent main --message "Execute complete end-to-end AITBC workflow: genesis → nodes → wallets → AI operations → marketplace → economics" --thinking high

# Run complete workflow
/opt/aitbc/scripts/workflow-openclaw/05_complete_workflow_openclaw.sh
```

### Step 7.2: Performance & Stress Testing
**Skill**: `openclaw-agent-testing-skill`

```bash
# Stress test the system
openclaw agent --agent main --message "Execute openclaw-agent-testing-skill with operation: comprehensive, test_duration: 300, concurrent_agents: 3" --thinking high
```

## ✅ Verification Checklist

### After Each Phase:
- [ ] Services running: `systemctl status aitbc-*`
- [ ] Blockchain syncing: Check block heights
- [ ] API responding: Health endpoints
- [ ] Wallets funded: Balance checks
- [ ] Agent communication: OpenClaw logs

### Final Verification:
- [ ] Genesis block height > 0
- [ ] Follower node synced
- [ ] Cross-node transactions successful
- [ ] AI jobs processing
- [ ] Marketplace active
- [ ] All agents communicating

## 🚨 Troubleshooting

### Common Issues:
1. **OpenClaw not responding**: Check gateway status
2. **Services not starting**: Check logs with `journalctl -u aitbc-*`
3. **Sync issues**: Verify network connectivity between nodes
4. **Wallet problems**: Check keystore permissions
5. **AI jobs failing**: Verify GPU availability and Ollama status

### Recovery Commands:
```bash
# Reset OpenClaw session
SESSION_ID="recovery-$(date +%s)"

# Restart all services
systemctl restart aitbc-*

# Reset blockchain (if needed)
rm -rf /var/lib/aitbc/data/ait-mainnet/*
# Then re-run Phase 1
```

## 📈 Success Metrics

### Expected Results:
- Genesis block created and validated
- 2+ nodes syncing properly
- Cross-node transactions working
- AI jobs submitting and completing
- Marketplace active with providers
- Agent coordination established
- End-to-end workflow successful

### Performance Targets:
- Block production: Every 10 seconds
- Transaction confirmation: < 30 seconds
- AI job completion: < 2 minutes
- Agent response time: < 5 seconds
- Cross-node sync: < 1 minute
