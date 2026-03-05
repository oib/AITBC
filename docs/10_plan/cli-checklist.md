# AITBC CLI Command Checklist

## Overview

This checklist provides a comprehensive reference for all AITBC CLI commands, organized by functional area. Use this to verify command availability, syntax, and testing coverage.

## 📋 Command Groups Summary

| Group | Commands | Purpose |
|--------|-----------|---------|
| **admin** | 8+ | System administration |
| **agent** | 8 | Advanced AI agent workflow and execution |
| **agent-comm** | 9 | Cross-chain agent communication |
| **analytics** | 6 | Chain analytics and monitoring |
| **auth** | 7 | API key and authentication management |
| **blockchain** | 15 | Blockchain queries and operations |
| **chain** | 10 | Multi-chain management |
| **client** | 14 | Job submission and management |
| **config** | 12 | CLI configuration management |
| **deploy** | 8 | Production deployment and scaling |
| **exchange** | 5 | Bitcoin exchange operations |
| **genesis** | 8 | Genesis block generation and management |
| **governance** | 4 | Governance proposals and voting |
| **marketplace** | 10 | GPU marketplace operations |
| **miner** | 12 | Mining operations and job processing |
| **monitor** | 7 | Monitoring, metrics, and alerting |
| **multimodal** | 9 | Multi-modal agent processing |
| **node** | 7 | Node management |
| **optimize** | 4 | Autonomous optimization and predictive operations |
| **plugin** | 4 | CLI plugin management |
| **simulate** | 6 | Simulations and test user management |
| **swarm** | 6 | Swarm intelligence and collective optimization |
| **test** | 9 | Testing and debugging commands |
| **version** | 1 | Version information |
| **wallet** | 24 | Wallet and transaction management |

**Total: 184 commands across 24 groups**

---

## 🔧 Core Commands Checklist

### **admin** — System Administration
- [ ] `admin` (help)
- [ ] `admin backup` — System backup operations
- [ ] `admin logs` — View system logs
- [ ] `admin monitor` — System monitoring
- [ ] `admin restart` — Restart services
- [ ] `admin status` — System status overview
- [ ] `admin update` — System updates
- [ ] `admin users` — User management

### **agent** — Advanced AI Agent Workflow
- [ ] `agent create` — Create new AI agent workflow
- [ ] `agent execute` — Execute AI agent workflow
- [ ] `agent learning` — Agent adaptive learning and training
- [ ] `agent list` — List available AI agent workflows
- [ ] `agent network` — Multi-agent collaborative network
- [ ] `agent receipt` — Get verifiable receipt for execution
- [ ] `agent status` — Get status of agent execution
- [ ] `agent submit-contribution` — Submit contribution via GitHub

### **agent-comm** — Cross-Chain Agent Communication
- [ ] `agent-comm collaborate` — Create multi-agent collaboration
- [ ] `agent-comm discover` — Discover agents on specific chain
- [ ] `agent-comm list` — List registered agents
- [ ] `agent-comm monitor` — Monitor cross-chain communication
- [ ] `agent-comm network` — Get cross-chain network overview
- [ ] `agent-comm register` — Register agent in cross-chain network
- [ ] `agent-comm reputation` — Update agent reputation
- [ ] `agent-comm send` — Send message to agent
- [ ] `agent-comm status` — Get detailed agent status

### **analytics** — Chain Analytics and Monitoring
- [ ] `analytics alerts` — View performance alerts
- [ ] `analytics dashboard` — Get complete dashboard data
- [ ] `analytics monitor` — Monitor chain performance in real-time
- [ ] `analytics optimize` — Get optimization recommendations
- [ ] `analytics predict` — Predict chain performance
- [ ] `analytics summary` — Get performance summary for chains

### **auth** — API Key and Authentication Management
- [ ] `auth import-env` — Import API key from environment variable
- [ ] `auth keys` — Manage multiple API keys
- [ ] `auth login` — Store API key for authentication
- [ ] `auth logout` — Remove stored API key
- [ ] `auth refresh` — Refresh authentication (token refresh)
- [ ] `auth status` — Show authentication status
- [ ] `auth token` — Show stored API key

---

## 🔗 Blockchain & Chain Commands

### **blockchain** — Blockchain Queries and Operations
- [ ] `blockchain balance` — Get balance of address across all chains
- [ ] `blockchain block` — Get details of specific block
- [ ] `blockchain blocks` — List recent blocks
- [ ] `blockchain faucet` — Mint devnet funds to address
- [ ] `blockchain genesis` — Get genesis block of a chain
- [ ] `blockchain head` — Get head block of a chain
- [ ] `blockchain info` — Get blockchain information
- [ ] `blockchain peers` — List connected peers
- [ ] `blockchain send` — Send transaction to a chain
- [ ] `blockchain status` — Get blockchain node status
- [ ] `blockchain supply` — Get token supply information
- [ ] `blockchain sync-status` — Get blockchain synchronization status
- [ ] `blockchain transaction` — Get transaction details
- [ ] `blockchain transactions` — Get latest transactions on a chain
- [ ] `blockchain validators` — List blockchain validators

### **chain** — Multi-Chain Management
- [ ] `chain add` — Add a chain to a specific node
- [ ] `chain backup` — Backup chain data
- [ ] `chain create` — Create a new chain from configuration file
- [ ] `chain delete` — Delete a chain permanently
- [ ] `chain info` — Get detailed information about a chain
- [ ] `chain list` — List all available chains
- [ ] `chain migrate` — Migrate a chain between nodes
- [ ] `chain monitor` — Monitor chain activity
- [ ] `chain remove` — Remove a chain from a specific node
- [ ] `chain restore` — Restore chain from backup

### **genesis** — Genesis Block Generation and Management
- [ ] `genesis create` — Create genesis block from configuration
- [ ] `genesis create-template` — Create a new genesis template
- [ ] `genesis export` — Export genesis block for a chain
- [ ] `genesis hash` — Calculate genesis hash
- [ ] `genesis info` — Show genesis block information
- [ ] `genesis template-info` — Show detailed information about template
- [ ] `genesis templates` — List available genesis templates
- [ ] `genesis validate` — Validate genesis block integrity

---

## 👤 User & Client Commands

### **client** — Job Submission and Management
- [ ] `client batch-submit` — Submit multiple jobs from CSV/JSON file
- [ ] `client blocks` — List recent blocks
- [ ] `client cancel` — Cancel a job
- [x] `client history` — Show job history with filtering options
- [x] `client pay` — Create a payment for a job
- [ ] `client payment-receipt` — Get payment receipt with verification
- [x] `client payment-status` — Get payment status for a job
- [x] `client receipts` — List job receipts
- [ ] `client refund` — Request a refund for a payment
- [x] `client result` — Retrieve the result of a completed job
- [x] `client status` — Check job status
- [x] `client submit` — Submit a job to the coordinator
- [ ] `client template` — Manage job templates for repeated tasks

### **wallet** — Wallet and Transaction Management
- [x] `wallet address` — Show wallet address
- [ ] `wallet backup` — Backup a wallet
- [x] `wallet balance` — Check wallet balance
- [x] `wallet create` — Create a new wallet
- [ ] `wallet delete` — Delete a wallet
- [ ] `wallet earn` — Add earnings from completed job
- [ ] `wallet history` — Show transaction history
- [ ] `wallet info` — Show current wallet information
- [ ] `wallet liquidity-stake` — Stake tokens into a liquidity pool
- [ ] `wallet liquidity-unstake` — Withdraw from liquidity pool with rewards
- [x] `wallet list` — List all wallets
- [ ] `wallet multisig-challenge` — Create cryptographic challenge for multisig
- [ ] `wallet multisig-create` — Create a multi-signature wallet
- [ ] `wallet multisig-propose` — Propose a multisig transaction
- [ ] `wallet multisig-sign` — Sign a pending multisig transaction
- [ ] `wallet request-payment` — Request payment from another address
- [ ] `wallet restore` — Restore a wallet from backup
- [ ] `wallet rewards` — View all earned rewards (staking + liquidity)
- [ ] `wallet send` — Send AITBC to another address
- [ ] `wallet sign-challenge` — Sign cryptographic challenge (testing multisig)
- [ ] `wallet spend` — Spend AITBC
- [ ] `wallet stake` — Stake AITBC tokens
- [ ] `wallet staking-info` — Show staking information
- [ ] `wallet stats` — Show wallet statistics
- [ ] `wallet switch` — Switch to a different wallet
- [ ] `wallet unstake` — Unstake AITBC tokens

---

## 🏪 Marketplace & Miner Commands

### **marketplace** — GPU Marketplace Operations
- [ ] `marketplace agents` — OpenClaw agent marketplace operations
- [ ] `marketplace bid` — Marketplace bid operations
- [ ] `marketplace governance` — OpenClaw agent governance operations
- [x] `marketplace gpu` — GPU marketplace operations
- [x] `marketplace offers` — Marketplace offers operations
- [x] `marketplace orders` — List marketplace orders
- [x] `marketplace pricing` — Get pricing information for GPU model
- [ ] `marketplace review` — Add a review for a GPU
- [ ] `marketplace reviews` — Get GPU reviews
- [ ] `marketplace test` — OpenClaw marketplace testing operations

### **miner** — Mining Operations and Job Processing
- [ ] `miner concurrent-mine` — Mine with concurrent job processing
- [ ] `miner deregister` — Deregister miner from the coordinator
- [ ] `miner earnings` — Show miner earnings
- [ ] `miner heartbeat` — Send heartbeat to coordinator
- [ ] `miner jobs` — List miner jobs with filtering
- [ ] `miner mine` — Mine continuously for specified number of jobs
- [ ] `miner mine-ollama` — Mine jobs using local Ollama for GPU inference
- [ ] `miner poll` — Poll for a single job
- [ ] `miner register` — Register as a miner with the coordinator
- [ ] `miner status` — Check miner status
- [ ] `miner update-capabilities` — Update miner GPU capabilities

---

## 🏛️ Governance & Advanced Features

### **governance** — Governance Proposals and Voting
- [ ] `governance list` — List governance proposals
- [ ] `governance propose` — Create a governance proposal
- [ ] `governance result` — Show voting results for a proposal
- [ ] `governance vote` — Cast a vote on a proposal

### **deploy** — Production Deployment and Scaling
- [ ] `deploy auto-scale` — Trigger auto-scaling evaluation for deployment
- [ ] `deploy create` — Create a new deployment configuration
- [ ] `deploy list-deployments` — List all deployments
- [ ] `deploy monitor` — Monitor deployment performance in real-time
- [ ] `deploy overview` — Get overview of all deployments
- [ ] `deploy scale` — Scale a deployment to target instance count
- [ ] `deploy start` — Deploy the application to production
- [ ] `deploy status` — Get comprehensive deployment status

### **exchange** — Bitcoin Exchange Operations
- [ ] `exchange create-payment` — Create Bitcoin payment request for AITBC purchase
- [ ] `exchange market-stats` — Get exchange market statistics
- [ ] `exchange payment-status` — Check payment confirmation status
- [ ] `exchange rates` — Get current exchange rates
- [ ] `exchange wallet` — Bitcoin wallet operations

---

## 🤖 AI & Agent Commands

### **multimodal** — Multi-Modal Agent Processing
- [ ] `multimodal agent` — Create multi-modal agent
- [ ] `multimodal attention` — Cross-modal attention analysis
- [ ] `multimodal benchmark` — Benchmark multi-modal agent performance
- [ ] `multimodal capabilities` — List multi-modal agent capabilities
- [ ] `multimodal convert` — Cross-modal conversion operations
- [ ] `multimodal optimize` — Optimize multi-modal agent pipeline
- [ ] `multimodal process` — Process multi-modal inputs with agent
- [ ] `multimodal search` — Multi-modal search operations
- [ ] `multimodal test` — Test individual modality processing

### **swarm** — Swarm Intelligence and Collective Optimization
- [ ] `swarm consensus` — Achieve swarm consensus on task result
- [ ] `swarm coordinate` — Coordinate swarm task execution
- [ ] `swarm join` — Join agent swarm for collective optimization
- [ ] `swarm leave` — Leave swarm
- [ ] `swarm list` — List active swarms
- [ ] `swarm status` — Get swarm task status

### **optimize** — Autonomous Optimization and Predictive Operations
- [ ] `optimize disable` — Disable autonomous optimization for agent
- [ ] `optimize predict` — Predictive operations
- [ ] `optimize self-opt` — Self-optimization operations
- [ ] `optimize tune` — Auto-tuning operations

---

## 🔧 System & Configuration Commands

### **config** — CLI Configuration Management
- [x] `config edit` — Open configuration file in editor
- [ ] `config environments` — List available environments
- [ ] `config export` — Export configuration
- [ ] `config get-secret` — Get a decrypted configuration value
- [ ] `config import-config` — Import configuration from file
- [ ] `config path` — Show configuration file path
- [ ] `config profiles` — Manage configuration profiles
- [ ] `config reset` — Reset configuration to defaults
- [x] `config set` — Set configuration value
- [ ] `config set-secret` — Set an encrypted configuration value
- [x] `config show` — Show current configuration
- [ ] `config validate` — Validate configuration

### **monitor** — Monitoring, Metrics, and Alerting
- [ ] `monitor alerts` — Configure monitoring alerts
- [ ] `monitor campaign-stats` — Campaign performance metrics (TVL, participants, rewards)
- [ ] `monitor campaigns` — List active incentive campaigns
- [x] `monitor dashboard` — Real-time system dashboard (partially working, 404 on coordinator)
- [ ] `monitor history` — Historical data analysis
- [ ] `monitor metrics` — Collect and display system metrics
- [ ] `monitor webhooks` — Manage webhook notifications

### **node** — Node Management Commands
- [ ] `node add` — Add a new node to configuration
- [ ] `node chains` — List chains hosted on all nodes
- [ ] `node info` — Get detailed node information
- [x] `node list` — List all configured nodes
- [ ] `node monitor` — Monitor node activity
- [ ] `node remove` — Remove a node from configuration
- [ ] `node test` — Test connectivity to a node

---

## 🧪 Testing & Development Commands

### **test** — Testing and Debugging Commands for AITBC CLI
- [x] `test api` — Test API connectivity
- [ ] `test blockchain` — Test blockchain functionality
- [x] `test diagnostics` — Run comprehensive diagnostics (100% pass)
- [ ] `test environment` — Test CLI environment and configuration
- [ ] `test integration` — Run integration tests
- [ ] `test job` — Test job submission and management
- [ ] `test marketplace` — Test marketplace functionality
- [x] `test mock` — Generate mock data for testing
- [ ] `test wallet` — Test wallet functionality

### **simulate** — Simulations and Test User Management
- [x] `simulate init` — Initialize test economy
- [ ] `simulate load-test` — Run load test
- [ ] `simulate results` — Show simulation results
- [ ] `simulate scenario` — Run predefined scenario
- [ ] `simulate user` — Manage test users
- [ ] `simulate workflow` — Simulate complete workflow

### **plugin** — CLI Plugin Management
- [ ] `plugin install` — Install a plugin from a Python file
- [x] `plugin list` — List installed plugins
- [ ] `plugin toggle` — Enable or disable a plugin
- [ ] `plugin uninstall` — Uninstall a plugin

---

## 📋 Utility Commands

### **version** — Version Information
- [ ] `version` — Show version information

### **config-show** — Show Current Configuration
- [ ] `config-show` — Show current configuration (alias for config show)

---

## 🚀 Testing Checklist

### ✅ Basic CLI Functionality
- [x] CLI installation: `pip install -e .`
- [x] CLI help: `aitbc --help`
- [x] Version check: `aitbc --version`
- [x] Configuration: `aitbc config show`

### ✅ Core Workflow Testing
- [x] Wallet creation: `aitbc wallet create`
- [x] Miner registration: `aitbc miner register` (localhost)
- [x] GPU marketplace: `aitbc marketplace gpu register`
- [x] Job submission: `aitbc client submit` (aitbc1)
- [x] Job result: `aitbc client result` (aitbc1)
- [x] Ollama mining: `aitbc miner mine-ollama` (localhost)

### ✅ Advanced Features Testing
- [ ] Multi-chain operations: `aitbc chain list`
- [ ] Agent workflows: `aitbc agent create`
- [ ] Governance: `aitbc governance propose`
- [ ] Swarm operations: `aitbc swarm join`
- [ ] Analytics: `aitbc analytics dashboard`
- [ ] Monitoring: `aitbc monitor metrics`

### ✅ Integration Testing
- [ ] API connectivity: `aitbc test api`
- [x] Blockchain sync: `aitbc blockchain sync-status` (Expected fail - no node)
- [ ] Payment flow: `aitbc client pay`
- [ ] Receipt verification: `aitbc client payment-receipt`
- [ ] Multi-signature: `aitbc wallet multisig-create`

---

## 📊 Command Coverage Matrix

| Category | Total Commands | Implemented | Tested | Documentation |
|----------|----------------|-------------|---------|----------------|
| Core Commands | 58 | ✅ | 🔄 | ✅ |
| Blockchain | 33 | ✅ | 🔄 | ✅ |
| Marketplace | 22 | ✅ | 🔄 | ✅ |
| AI & Agents | 27 | ✅ | ❌ | ✅ |
| System & Config | 26 | ✅ | 🔄 | ✅ |
| Testing & Dev | 19 | ✅ | ❌ | ✅ |
| **TOTAL** | **184** | **✅** | **🔄** | **✅** |

**Legend:**
- ✅ Complete
- 🔄 Partial/In Progress
- ❌ Not Started

---

## 🔍 Command Usage Examples

### End-to-End GPU Rental Flow
```bash
# 1. Setup
aitbc wallet create --name user-wallet
aitbc miner register --gpu "RTX-4090" --memory 24 --miner-id "miner-01"

# 2. Marketplace
aitbc marketplace gpu register --name "RTX-4090" --price-per-hour 1.5
aitbc marketplace gpu list
aitbc marketplace gpu book gpu_123 --hours 2

# 3. Job Execution
aitbc client submit --prompt "What is AI?" --model gemma3:1b
aitbc miner mine-ollama --jobs 1 --model gemma3:1b
aitbc client result <job-id> --wait

# 4. Payment
aitbc client pay --job-id <job-id> --amount 3.0
aitbc client payment-receipt --job-id <job-id>
```

### Multi-Chain Setup
```bash
# Chain management
aitbc chain create --config chain.yaml
aitbc chain list
aitbc node add --name node2 --endpoint http://localhost:8001

# Blockchain operations
aitbc blockchain status
aitbc blockchain sync-status
aitbc blockchain faucet <address>
```

### Agent Workflow
```bash
# Agent creation and execution
aitbc agent create --name "ai-assistant" --config '{"model": "gpt4"}'
aitbc agent execute ai-assistant --input '{"prompt": "Hello"}'

# Cross-chain communication
aitbc agent-comm register --agent-id agent-01 --chain-id devnet
aitbc agent-comm send --to agent-02 --message "Data ready"
```

---

## 📝 Notes

1. **Command Availability**: Some commands may require specific backend services or configurations
2. **Authentication**: Most commands require API key configuration via `aitbc auth login` or environment variables
3. **Multi-Chain**: Chain-specific commands need proper chain configuration
4. **Testing**: Use `aitbc test` commands to verify functionality before production use
5. **Documentation**: Each command supports `--help` flag for detailed usage information

---

*Last updated: March 5, 2026*  
*Total commands: 184 across 24 command groups*
