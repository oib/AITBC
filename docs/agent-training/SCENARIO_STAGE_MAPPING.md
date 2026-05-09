# Scenario to Training Stage Mapping

## Overview
This document maps the 46 scenarios from `/opt/aitbc/docs/scenarios` to agent training stages.

## Current Training Stages
- Stage 0: Environment Setup (genesis wallet validation, node connectivity, prerequisites)
- Stage 1: Foundation (wallet, blockchain, service status)
- Stage 2: Operations Mastery (wallet operations, blockchain, mining, network)
- Stage 3: AI Operations (AI jobs, fine-tuning)
- Stage 4: Marketplace & Economics (marketplace, economics)
- Stage 5: Expert Operations (workflow, resource, analytics, security)
- Stage 6: Agent Identity & SDK (agent SDK operations)
- Stage 7: Cross-Node Training (cross-node, coordination, swarm, distributed learning)
- Stage 8: Advanced Agent Specialization (bounty, portfolio, knowledge graph, dispute, ZK proofs)
- Stage 9: Multi-Chain Architecture (island setup, gossip sync, multi-chain validator)

## Scenario Mapping

### Stage 0: Environment Setup (Prerequisites)
**Purpose:** Validate genesis wallet configuration, node connectivity, and prerequisites before training begins
**Operations:**
- genesis_wallet_check - Verify genesis wallet exists at /var/lib/aitbc/keystore/genesis.json
- genesis_password_check - Verify password file exists at /var/lib/aitbc/keystore/.genesis_password
- genesis_balance_check - Verify genesis wallet has funds for funding training wallets
- node_connectivity_check - Verify blockchain node is running and accessible
- peer_connectivity_check - Verify network peer connectivity

### Stage 1: Foundation (Beginner Scenarios 1-6)
**Current Coverage:** wallet_create, wallet_balance, blockchain_status, service_status
**Additions:**
- 01_wallet_basics.md - Wallet creation, import, balance checks ✓
- 02_transaction_sending.md - Send transactions, batch transfers
- 03_genesis_deployment.md - Create and deploy genesis blocks
- 04_messaging_basics.md - Send/receive messages via gossip
- 05_island_creation.md - Create and join islands
- 06_basic_trading.md - Simple AIT coin trading

### Stage 2: Operations Mastery (Beginner Scenarios 7-14)
**Current Coverage:** wallet operations, blockchain, mining, network
**Additions:**
- 07_ai_job_submission.md - Submit AI compute jobs (move to Stage 3)
- 08_marketplace_bidding.md - Place bids on marketplace (move to Stage 4)
- 09_gpu_listing.md - List GPU resources on marketplace (move to Stage 4)
- 10_plugin_development.md - Create simple Ollama plugin
- 11_ipfs_storage.md - Store/retrieve data via IPFS
- 12_database_operations.md - Basic database hosting
- 13_mining_setup.md - Start mining operations ✓
- 14_staking_basics.md - Stake tokens and earn rewards

### Stage 3: AI Operations (Beginner Scenario 7 + Intermediate 22, 32, 37)
**Current Coverage:** ai_submit, ai_status, ai_jobs, finetune_submit, finetune_status
**Additions:**
- 07_ai_job_submission.md - Submit AI compute jobs
- 22_ai_training_agent.md - AI job submission + GPU marketplace + payment
- 32_ai_power_advertiser.md - AI job submission + trading + analytics
- 37_distributed_ai_training.md - AI jobs + GPU marketplace + IPFS + messaging + swarm coordination + payments

### Stage 4: Marketplace & Economics (Beginner Scenarios 8-9 + Intermediate 21, 25, 41, 42, 43)
**Current Coverage:** market_list, market_buy, market_sell, market_orders, economics_distributed
**Additions:**
- 08_marketplace_bidding.md - Place bids on marketplace
- 09_gpu_listing.md - List GPU resources on marketplace
- 21_compute_provider_agent.md - GPU listing + marketplace bidding + wallet management
- 25_marketplace_arbitrage.md - Trading + GPU marketplace + analytics
- 41_bounty_system.md - Marketplace bidding + wallet management + agent registration + escrow
- 42_portfolio_management.md - Trading + wallet management + analytics + staking
- 43_knowledge_graph_market.md - IPFS storage + marketplace bidding + agent registration + knowledge graph

### Stage 5: Expert Operations (Beginner Scenarios 10-19 + Intermediate 23, 28-31, 34-35)
**Current Coverage:** workflow, resource, analytics, security
**Additions:**
- 10_plugin_development.md - Create simple Ollama plugin
- 11_ipfs_storage.md - Store/retrieve data via IPFS
- 12_database_operations.md - Basic database hosting
- 15_blockchain_monitoring.md - Monitor blockchain status
- 16_agent_registration.md - Register agent on network
- 17_governance_voting.md - Participate in governance
- 18_analytics_collection.md - Collect analytics data
- 19_security_setup.md - JWT authentication setup
- 23_data_oracle_agent.md - IPFS storage + messaging + transaction sending
- 28_monitoring_agent.md - Blockchain monitoring + analytics + alerting
- 29_plugin_marketplace_agent.md - Plugin development + marketplace + IPFS
- 30_database_service_agent.md - Database hosting + marketplace + security
- 31_federation_bridge_agent.md - Island operations + cross-chain bridge + messaging
- 34_compliance_agent.md - Governance + security + analytics
- 35_edge_compute_agent.md - GPU marketplace + island operations + database

### Stage 6: Agent Identity & SDK (Beginner Scenario 16 + Intermediate 24)
**Current Coverage:** agent_sdk operations
**Additions:**
- 16_agent_registration.md - Register agent on network
- 24_swarm_coordinator.md - Agent registration + messaging + island operations

### Stage 7: Cross-Node Training (Beginner Scenario 20 + Intermediate 26-27, 33 + Advanced 36-40)
**Current Coverage:** cross-node, coordination, swarm, distributed learning
**Additions:**
- 20_cross_chain_transfer.md - Transfer assets across chains
- 26_staking_validator_agent.md - Staking + mining + governance voting
- 27_cross_chain_trader.md - Cross-chain transfer + trading + wallet management
- 33_multi_chain_validator.md - Staking + cross-chain operations + monitoring
- 36_autonomous_compute_provider.md - GPU listing + marketplace + wallet + staking + monitoring + security
- 37_distributed_ai_training.md - AI jobs + GPU marketplace + IPFS + messaging + swarm coordination + payments
- 38_cross_chain_market_maker.md - Trading + cross-chain bridge + multiple chains + analytics + governance + security
- 39_federated_learning_coordinator.md - Agent coordination + IPFS + GPU marketplace + AI jobs + database + messaging + monitoring
- 40_enterprise_ai_agent.md - All features: trading + GPU + AI + staking + cross-chain + governance + security + analytics + monitoring + plugins + IPFS + database

## Current Stage Status

### Stage 0: Environment Setup ✅
**Status:** Created - JSON file exists, added to schema
**Scenarios:** References /docs/scenarios/01_genesis_wallet_setup.md, /docs/scenarios/02_node_connectivity.md, /docs/scenarios/03_environment_prerequisites.md (need to be created)

### Stage 8: Advanced Agent Specialization ✅
**Status:** Created - JSON file exists with operations
**Scenarios:**
- 15_blockchain_monitoring.md
- 16_agent_registration.md
- 17_governance_voting.md
- 18_analytics_collection.md
- 19_security_setup.md
- 23_data_oracle_agent.md
- 28_monitoring_agent.md
- 29_plugin_marketplace_agent.md
- 30_database_service_agent.md
- 31_federation_bridge_agent.md
- 34_compliance_agent.md
- 35_edge_compute_agent.md

### Stage 9: Multi-Chain Architecture ✅
**Status:** Created - JSON file exists with operations
**Scenarios:**
- 15_blockchain_monitoring.md
- 16_agent_registration.md
- 17_governance_voting.md
- 18_analytics_collection.md
- 19_security_setup.md
- 23_data_oracle_agent.md
- 28_monitoring_agent.md
- 29_plugin_marketplace_agent.md
- 30_database_service_agent.md
- 31_federation_bridge_agent.md
- 34_compliance_agent.md
- 35_edge_compute_agent.md

## Integration Priority

### ✅ Completed (Phase 2 Stage Mastery Analysis)
1. **Priority 1 Structural Improvements:** Schema validation rules, dependency validator, validation script
2. **Priority 2 Content Enhancements:** Stage 0 created, scenario mappings updated
3. **All Stages 2-9:** Fixed validation errors (wallet_balance checks, currency fields, resource dependencies)

### High Priority (Immediate Integration)
1. **Stage 1:** Add scenarios 1-6 (foundation operations)
2. **Stage 2:** Add scenarios 10-14 (plugin, IPFS, database, staking)
3. **Stage 3:** Add scenario 22 (AI training agent)
4. **Stage 4:** Add scenarios 8-9, 21, 25 (marketplace operations)
5. **Stage 5:** Add scenarios 15-19, 23, 28-31, 34-35 (expert operations)

### Medium Priority (Next Integration)
1. **Stage 6:** Add scenarios 16, 24 (agent registration, swarm coordination)
2. **Stage 7:** Add scenarios 20, 26-27, 33, 36-40 (cross-chain, multi-chain, advanced agents)

### Low Priority (Future Integration)
1. **Stage 8:** ✅ Created - Advanced Agent Specialization (scenarios 41-45)
2. **Stage 9:** ✅ Created - Multi-Chain Architecture (scenario 46)

---

**Last Reviewed:** 2026-05-09  
**Version:** 2.0  
**Changelog:**
- v2.0 (2026-05-09): Added version control metadata and last reviewed date
- v1.0 (2026-05-07): Initial version with scenario mappings
