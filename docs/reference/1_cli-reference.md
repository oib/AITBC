# AITBC CLI Reference

> **Note**: This document describes the current 70+ command CLI structure. For authoritative port configuration, see [Service Ports Reference](./SERVICE_PORTS.md).

## Overview

The AITBC CLI provides a comprehensive command-line interface with 70+ command groups for interacting with the AITBC network. It supports wallet management, blockchain operations, AI job submission, marketplace operations, agent orchestration, system administration, advanced analytics, enterprise integration, and regulatory compliance.

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
aitet network test <peer>
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

### 27. admin
System administration commands.

```bash
# Show system status
aitbc admin status
```

### 28. advanced_analytics
Advanced analytics and market insights commands.

```bash
# Start advanced analytics monitoring
aitbc advanced_analytics start --symbols BTC,ETH

# Get analytics summary
aitbc advanced_analytics summary
```

### 29. agent_comm
Cross-chain agent communication commands.

```bash
# Register an agent in the cross-chain network
aitbc agent_comm register <agent_id> <name> <chain_id> <endpoint> --capabilities <list>

# Send message to agent
aitbc agent_comm send <agent_id> <message>
```

### 30. ai_surveillance
AI-powered surveillance and behavioral analysis commands.

```bash
# Start AI surveillance
aitbc ai_surveillance start --symbols BTC,ETH

# Get surveillance summary
aitbc ai_surveillance summary

# Analyze behavior patterns
aitbc ai_surveillance analyze <user_id>
```

### 31. ai_trading
AI-powered trading and analytics commands.

```bash
# Initialize AI trading engine
aitbc ai_trading init

# Train trading strategies
aitbc ai_trading train

# Generate trading signals
aitbc ai_trading signals
```

### 32. arbitrage
Market arbitrage and price analysis commands.

```bash
# Analyze arbitrage opportunities between markets
aitbc arbitrage analyze --market-a <market_a> --market-b <market_b> --token <token>
```

### 33. auth
Manage API keys and authentication.

```bash
# Store API key for authentication
aitbc auth login <api_key> --environment <env>

# Logout from current session
aitbc auth logout
```

### 34. chain
Multi-chain management commands.

```bash
# List all available chains
aitbc chain list --type all --show-private

# Get chain info
aitbc chain info <chain_id>

# Create new chain
aitbc chain create <chain_type> <name>
```

### 35. client
Submit and manage jobs.

```bash
# Submit job
aitbc client submit --type <job_type> --prompt <prompt>

# List jobs
aitbc client list

# Get job status
aitbc client status <job_id>
```

### 36. config
Manage CLI configuration.

```bash
# Show current configuration
aitbc config show

# Set configuration value
aitbc config set <key> <value>

# Get configuration value
aitbc config get <key>
```

### 37. cross_chain
Cross-chain trading operations.

```bash
# Get cross-chain rates
aitbc cross_chain rates --from-chain <chain> --to-chain <chain>

# Execute cross-chain swap
aitbc cross_chain swap --from-chain <chain> --to-chain <chain> --amount <amount>
```

### 38. dao
Hermes DAO governance commands.

```bash
# Deploy Hermes DAO contract
aitbc dao deploy --token-address <address> --timelock-address <address>

# Create proposal
aitbc dao proposal create <description>

# Vote on proposal
aitbc dao vote <proposal_id> <vote>
```

### 39. deployment
Production deployment guidance and setup.

```bash
# Get deployment setup instructions
aitbc deployment setup --service <service> --environment <env>
```

### 40. edge
Edge computing commands.

```bash
# Initialize edge node
aitbc edge init --name <name> --location <location> --capacity <capacity>

# List edge nodes
aitbc edge list
```

### 41. enterprise_integration
Enterprise API gateway and multi-tenant architecture commands.

```bash
# Create tenant
aitbc enterprise_integration create-tenant <name> --admin <admin>

# Generate API key
aitbc enterprise_integration generate-api-key <tenant_id>

# List integrations
aitbc enterprise_integration list-integrations
```

### 42. exchange
Exchange integration and trading management commands.

```bash
# Add exchange
aitbc exchange add --name <name> --api-key <key> --secret-key <secret>

# List exchanges
aitbc exchange list

# Get exchange status
aitbc exchange status <exchange_name>
```

### 43. explorer
Blockchain explorer commands.

```bash
# Search blocks
aitbc explorer blocks --limit 10

# Search transactions
aitbc explorer transactions <address>

# Get block details
aitbc explorer block <block_hash>
```

### 44. genesis_protection
Genesis block protection and verification commands.

```bash
# Verify genesis block integrity
aitbc genesis_protection verify --chain <chain_id> --genesis-hash <hash>

# Protect genesis block
aitbc genesis_protection protect <chain_id>
```

### 45. global_ai_agents
Global AI agents management commands.

```bash
# Get AI agent network status
aitbc global_ai_agents status --agent-id <agent_id>

# Deploy global agent
aitbc global_ai_agents deploy <agent_id> --region <region>
```

### 46. global_infrastructure
Global infrastructure management commands.

```bash
# Deploy new global region
aitbc global_infrastructure deploy-region --region-id <id> --name <name> --location <location>

# List regions
aitbc global_infrastructure list-regions
```

### 47. governance
Governance proposals and voting commands.

```bash
# Create proposal
aitbc governance create <title> <description>

# List proposals
aitbc governance list

# Vote on proposal
aitbc governance vote <proposal_id> <vote>
```

### 48. hermes
Hermes integration with edge computing deployment.

```bash
# Deploy hermes agent
aitbc hermes deploy <agent_id>

# List hermes agents
aitbc hermes list

# Get hermes status
aitbc hermes status <agent_id>
```

### 49. ipfs
IPFS distributed storage commands.

```bash
# Upload file to IPFS
aitbc ipfs upload --file <file> --pin

# Download from IPFS
aitbc ipfs download <cid> --output <path>

# List pinned content
aitbc ipfs list
```

### 50. island
Island computing commands.

```bash
# Create island
aitbc island create --name <name> --capacity <capacity>

# Join island
aitbc island join <island_id>

# List islands
aitbc island list
```

### 51. keystore
Keystore operations (create wallets/keystores).

```bash
# Create wallet keystore
aitbc keystore create --address <address> --password-file <file>

# List keystores
aitbc keystore list
```

### 52. market_maker
Market making bot management commands.

```bash
# Start market maker
aitbc market_maker start --exchange <exchange> --pair <pair> --spread <spread>

# Stop market maker
aitbc market_maker stop <bot_id>

# List market makers
aitbc market_maker list
```

### 53. marketplace
Marketplace listings and offers.

```bash
# List GPU offers
aitbc marketplace gpu list

# Register GPU
aitbc marketplace gpu register --name <name> --memory <memory>

# Book GPU
aitbc marketplace gpu book <gpu_id> --duration <duration>
```

### 54. marketplace_advanced
Advanced marketplace operations.

```bash
# List model NFTs
aitbc marketplace_advanced models list

# Create model NFT
aitbc marketplace_advanced models create <name> --version <version>
```

### 55. miner
Mining operations and rewards.

```bash
# Register as miner
aitbc miner register

# Start mining
aitbc miner start

# Stop mining
aitbc miner stop

# View rewards
aitbc miner rewards
```

### 56. monitor
Monitoring, metrics, and alerting commands.

```bash
# Real-time system dashboard
aitbc monitor dashboard --refresh 5

# List alerts
aitbc monitor alerts

# Get metrics
aitbc monitor metrics
```

### 57. multi_region_load_balancer
Multi-region load balancer management commands.

```bash
# Get load balancer status
aitbc multi_region_load_balancer status

# Configure load balancer
aitbc multi_region_load_balancer configure <config>
```

### 58. multimodal
Multimodal AI operations.

```bash
# Create multi-modal agent
aitbc multimodal agent --name <name> --modalities <modalities>

# List multi-modal agents
aitbc multimodal list
```

### 59. multisig
Multi-signature wallet management commands.

```bash
# Create multi-signature wallet
aitbc multisig create --threshold <n> --owners <addresses>

# Sign transaction
aitbc multisig sign <wallet_id> <tx_id>

# Submit transaction
aitbc multisig submit <wallet_id> <tx_id>
```

### 60. node
Node management commands.

```bash
# Get node information
aitbc node info <node_id>

# List nodes
aitbc node list

# Add node
aitbc node add <node_id> --endpoint <endpoint>
```

### 61. optimize
Autonomous optimization and predictive operations.

```bash
# Run self-optimization
aitbc optimize self_opt run

# Get optimization status
aitbc optimize status
```

### 62. oracle
Oracle price discovery and management commands.

```bash
# Set price for trading pair
aitbc oracle set-price --pair <pair> --price <price>

# Get oracle prices
aitbc oracle prices <pair>
```

### 63. plugin
Plugin marketplace and management commands.

```bash
# Publish plugin to marketplace
aitbc plugin publish --name <name> --version <version> --file <file>

# List plugins
aitbc plugin list

# Install plugin
aitbc plugin install <plugin_id>
```

### 64. plugin_analytics
Plugin analytics management commands.

```bash
# View plugin analytics dashboard
aitbc plugin_analytics dashboard --plugin-id <plugin_id> --days 30

# Get plugin usage stats
aitbc plugin_analytics stats <plugin_id>
```

### 65. plugin_marketplace
Plugin marketplace commands.

```bash
# Browse plugins in marketplace
aitbc plugin_marketplace browse --category <category> --limit 20

# Purchase plugin
aitbc plugin_marketplace purchase <plugin_id>
```

### 66. plugin_registry
Plugin registry management commands.

```bash
# Register plugin
aitbc plugin_registry register --name <name> --version <version> --author <author>

# List registered plugins
aitbc plugin_registry list
```

### 67. plugin_security
Plugin security management commands.

```bash
# Scan plugin for vulnerabilities
aitbc plugin_security scan <plugin_id>

# Get security report
aitbc plugin_security report <plugin_id>
```

### 68. production_deploy
Production deployment management commands.

```bash
# Deploy to production
aitbc production_deploy deploy --environment <env> --version <version> --region <region>

# Get deployment status
aitbc production_deploy status <deployment_id>
```

### 69. regulatory
Regulatory compliance reporting commands.

```bash
# Generate SAR report
aitbc regulatory generate-sar --type <type>

# Generate compliance summary
aitbc regulatory compliance-summary

# List reports
aitbc regulatory list
```

### 70. staking
Staking and validator management commands.

```bash
# Manage staking operations
aitbc staking manage --action <action> --amount <amount> --validator-id <validator_id>

# Get staking status
aitbc staking status
```

### 71. surveillance
Trading surveillance and market manipulation detection commands.

```bash
# Start surveillance
aitbc surveillance start --symbols <symbols>

# Get alerts
aitbc surveillance alerts

# Get surveillance summary
aitbc surveillance summary
```

### 72. swarm
Swarm intelligence and collective optimization commands.

```bash
# Create agent swarm
aitbc swarm create --name <name> --max-agents <n>

# List swarms
aitbc swarm list

# Deploy swarm
aitbc swarm deploy <swarm_id>
```

### 73. transfer_control
Advanced transfer control and limit management commands.

```bash
# Set transfer limits for wallet
aitbc transfer_control set-limit --wallet <wallet> --max-daily <amount>

# Get transfer limits
aitbc transfer_control get-limits <wallet>
```

### 74. validator
Staking validator management commands.

```bash
# Initialize validator
aitbc validator init --stake-amount <amount> --wallet <wallet>

# Get validator status
aitbc validator status <validator_id>

# List validators
aitbc validator list
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
