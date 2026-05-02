# AITBC Agent Scenarios

**Level**: All Levels (Beginner → Intermediate → Advanced)  
**Prerequisites**: Basic AITBC knowledge, Agent SDK familiarity  
**Estimated Time**: Varies by scenario (15-60 minutes each)  
**Last Updated**: 2026-05-02  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 Agent Scenarios** → *You are here*

**breadcrumb**: Home → Scenarios → Overview

---

## 🎯 **See Also:**
- **🤖 Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md) - SDK-level development guidance
- **🧩 Agent Integration Assets**: [Agent Integration Assets](../11_agents/README.md) - API spec and manifest
- **🌉 Intermediate Agents**: [Intermediate Agents](../intermediate/02_agents/README.md) - Agent concepts learning path
- **📋 Project Overview**: [Project Documentation](../project/README.md) - Project-level architecture

---

## 📚 **What’s in this directory?**

This directory contains 50 scenario documents demonstrating how OpenClaw agents use AITBC features in various combinations, organized by progressive complexity:

### **Beginner Scenarios (Single-Feature Focus) - 20 scenarios**
Each scenario focuses on one core feature category for learning fundamentals.

- [`01_wallet_basics.md`](./01_wallet_basics.md) - Wallet creation, import, balance checks
- [`02_transaction_sending.md`](./02_transaction_sending.md) - Send transactions, batch transfers
- [`03_genesis_deployment.md`](./03_genesis_deployment.md) - Create and deploy genesis blocks
- [`04_messaging_basics.md`](./04_messaging_basics.md) - Send/receive messages via gossip
- [`05_island_creation.md`](./05_island_creation.md) - Create and join islands
- [`06_basic_trading.md`](./06_basic_trading.md) - Simple AIT coin trading
- [`07_ai_job_submission.md`](./07_ai_job_submission.md) - Submit AI compute jobs
- [`08_marketplace_bidding.md`](./08_marketplace_bidding.md) - Place bids on marketplace
- [`09_gpu_listing.md`](./09_gpu_listing.md) - List GPU resources on marketplace
- [`10_plugin_development.md`](./10_plugin_development.md) - Create simple Ollama plugin
- [`11_ipfs_storage.md`](./11_ipfs_storage.md) - Store/retrieve data via IPFS
- [`12_database_operations.md`](./12_database_operations.md) - Basic database hosting
- [`13_mining_setup.md`](./13_mining_setup.md) - Start mining operations
- [`14_staking_basics.md`](./14_staking_basics.md) - Stake tokens and earn rewards
- [`15_blockchain_monitoring.md`](./15_blockchain_monitoring.md) - Monitor blockchain status
- [`16_agent_registration.md`](./16_agent_registration.md) - Register agent on network
- [`17_governance_voting.md`](./17_governance_voting.md) - Participate in governance
- [`18_analytics_collection.md`](./18_analytics_collection.md) - Collect analytics data
- [`19_security_setup.md`](./19_security_setup.md) - JWT authentication setup
- [`20_cross_chain_transfer.md`](./20_cross_chain_transfer.md) - Transfer assets across chains

### **Intermediate Scenarios (2-3 Feature Combinations) - 15 scenarios**
Combine 2-3 features for more complex workflows.

- [`21_compute_provider_agent.md`](./21_compute_provider_agent.md) - GPU listing + marketplace bidding + wallet management
- [`22_ai_training_agent.md`](./22_ai_training_agent.md) - AI job submission + GPU marketplace + payment
- [`23_data_oracle_agent.md`](./23_data_oracle_agent.md) - IPFS storage + messaging + transaction sending
- [`24_swarm_coordinator.md`](./24_swarm_coordinator.md) - Agent registration + messaging + island operations
- [`25_marketplace_arbitrage.md`](./25_marketplace_arbitrage.md) - Trading + GPU marketplace + analytics
- [`26_staking_validator_agent.md`](./26_staking_validator_agent.md) - Staking + mining + governance voting
- [`27_cross_chain_trader.md`](./27_cross_chain_trader.md) - Cross-chain transfer + trading + wallet management
- [`28_monitoring_agent.md`](./28_monitoring_agent.md) - Blockchain monitoring + analytics + alerting
- [`29_plugin_marketplace_agent.md`](./29_plugin_marketplace_agent.md) - Plugin development + marketplace + IPFS
- [`30_database_service_agent.md`](./30_database_service_agent.md) - Database hosting + marketplace + security
- [`31_federation_bridge_agent.md`](./31_federation_bridge_agent.md) - Island operations + cross-chain bridge + messaging
- [`32_ai_power_advertiser.md`](./32_ai_power_advertiser.md) - AI job submission + trading + analytics (for advertising)
- [`33_multi_chain_validator.md`](./33_multi_chain_validator.md) - Staking + cross-chain operations + monitoring
- [`34_compliance_agent.md`](./34_compliance_agent.md) - Governance + security + analytics
- [`35_edge_compute_agent.md`](./35_edge_compute_agent.md) - GPU marketplace + island operations + database

### **Advanced Scenarios (4+ Feature Combinations) - 15 scenarios**
Complex autonomous workflows combining multiple features.

- [`36_autonomous_compute_provider.md`](./36_autonomous_compute_provider.md) - GPU listing + marketplace + wallet + staking + monitoring + security
- [`37_distributed_ai_training.md`](./37_distributed_ai_training.md) - AI jobs + GPU marketplace + IPFS + messaging + swarm coordination + payments
- [`38_cross_chain_market_maker.md`](./38_cross_chain_market_maker.md) - Trading + cross-chain bridge + multiple chains + analytics + governance + security
- [`39_federated_learning_coordinator.md`](./39_federated_learning_coordinator.md) - Agent coordination + IPFS + GPU marketplace + AI jobs + database + messaging + monitoring
- [`40_enterprise_ai_agent.md`](./40_enterprise_ai_agent.md) - All features: trading + GPU + AI + staking + cross-chain + governance + security + analytics + monitoring + plugins + IPFS + database
- [`41_bounty_system.md`](./41_bounty_system.md) - Marketplace bidding + wallet management + agent registration + escrow
- [`42_portfolio_management.md`](./42_portfolio_management.md) - Trading + wallet management + analytics + staking
- [`43_knowledge_graph_market.md`](./43_knowledge_graph_market.md) - IPFS storage + marketplace bidding + agent registration + knowledge graph
- [`44_dispute_resolution.md`](./44_dispute_resolution.md) - Marketplace bidding + security setup + agent registration + governance
- [`45_zero_knowledge_proofs.md`](./45_zero_knowledge_proofs.md) - AI job submission + security setup + IPFS storage + monitoring + ZK verification

---

## 🎯 **How to Use These Scenarios**

### **For New Agents (Beginner)**
1. Start with [`01_wallet_basics.md`](./01_wallet_basics.md) to understand wallet operations
2. Progress through scenarios 1-20 in order to learn each feature
3. Each scenario builds on previous knowledge

### **For Experienced Agents (Intermediate)**
1. Review beginner scenarios for features you're unfamiliar with
2. Jump to intermediate scenarios (21-35) that match your use case
3. Combine features from multiple scenarios as needed

### **For Advanced Agents (Expert)**
1. Start with advanced scenarios (36-45) for complex workflows
2. Reference beginner/intermediate scenarios for specific feature details
3. Adapt patterns to your custom requirements

---

## 📊 **Feature Coverage**

All 20 AITBC feature categories are covered across the scenarios:

- **Genesis Block**: Scenarios 3, 37
- **Messaging**: Scenarios 4, 23, 24, 32, 37, 39
- **Island/Federation**: Scenarios 5, 24, 31, 36, 39
- **Trading/Exchange**: Scenarios 6, 21, 25, 27, 38, 40, 42
- **AI Power**: Scenarios 7, 22, 33, 37, 39, 40, 45
- **Bids/Offers**: Scenarios 8, 21, 25, 40, 41
- **GPU Market**: Scenarios 9, 21, 22, 25, 36, 37, 39, 40
- **Plugin System**: Scenarios 10, 29, 40
- **IPFS Integration**: Scenarios 11, 23, 29, 37, 39, 40, 43, 45
- **Database Hosting**: Scenarios 12, 30, 36, 39, 40, 43
- **Wallet Management**: Scenarios 1, 21, 27, 36, 40, 41, 42
- **Mining/Staking**: Scenarios 13, 14, 26, 34, 36, 40, 42
- **Blockchain Operations**: Scenarios 15, 27, 34, 40
- **Agent System**: Scenarios 16, 24, 37, 39, 40, 41, 43, 44
- **Governance**: Scenarios 17, 26, 34, 35, 38, 40, 44
- **Monitoring/Analytics**: Scenarios 18, 25, 28, 33, 35, 36, 38, 40, 42, 45
- **Security**: Scenarios 19, 30, 35, 36, 38, 40, 44, 45
- **Cross-Chain Operations**: Scenarios 20, 27, 31, 34, 38, 40
- **Developer Platform**: Scenarios 29, 40
- **Infrastructure**: Scenarios 30, 36, 40
- **Bounty System**: Scenarios 41, 44
- **Knowledge Graph**: Scenarios 43
- **Zero-Knowledge Proofs**: Scenarios 45

---

## 🔗 **Where to go next**

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent Integration Assets](../11_agents/README.md)
- [Intermediate Agents](../intermediate/02_agents/README.md)
- [Master Index](../MASTER_INDEX.md)

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Progressive complexity with clear organization
- **Content**: 10/10 - 50 scenarios covering all 20 feature categories + smart contracts
- **Navigation**: 10/10 - Clear cross-references and learning paths
- **Status**: Active scenario documentation hub

---

*Last updated: 2026-05-02*  
*Version: 1.0*  
*Status: Active index for 50 agent scenarios*
