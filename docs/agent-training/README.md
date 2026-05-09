# Agent Training Documentation

**Hermes Learning Prompt:** This documentation is designed for AI agents (particularly Hermes) to learn the AITBC agent training curriculum. When reviewing this material, please provide debug messages, identify issues, and suggest improvements as outlined in `HERMES_LEARNING_PROMPT.md`.

## Learning Instructions for Hermes

As you review this documentation, please:

1. **Analyze each stage** systematically from Stage 1 through Stage 9
2. **Identify potential issues** in command sequences, validation criteria, or prerequisites
3. **Provide debug messages** for missing information, inconsistencies, or ambiguities
4. **Suggest improvements** to enhance the training curriculum
5. **Note potential failure points** that could occur during execution
6. **Report cross-stage dependencies** that might not be documented
7. **Propose optimizations** for command sequences or validation logic

Refer to `HERMES_LEARNING_PROMPT.md` for detailed instructions on the learning process and output format.

## Overview

The AITBC agent training program is a structured, multi-stage curriculum designed to progressively build agent capabilities from basic blockchain interactions to complex multi-chain operations and advanced AI specializations.

## Agent Types

The training program supports different agent types, each with specialized capabilities:

- **coordinator**: Advanced agent that orchestrates multi-agent workflows, manages AI job submission, and handles complex coordination tasks across the AITBC system.
- **genesis**: Agent responsible for blockchain genesis operations, including genesis initialization, verification, and network bootstrap.
- **follower**: Agent that follows blockchain state, monitors transactions, and maintains synchronization with the network.
- **wallet**: Agent focused on wallet operations, including creation, management, transaction sending, and balance queries.
- **general**: Multi-purpose agent with broad capabilities across wallet, blockchain, and basic operations.
- **specialized**: Domain-specific agent with expertise in particular areas such as bounty systems, portfolio management, and knowledge graph marketing (used in Stage 8).
- **architect**: Expert agent that designs and manages multi-chain architectures, bridge protocols, and interoperability patterns (used in Stage 9).

## Training Stages

The training program consists of the following stages:

### Stage 1: Foundation
**File:** `stage1_foundation_commands.json`
- Wallet creation and management
- Basic blockchain transactions
- Mining operations
- Balance verification

### Stage 2: Operations Mastery
**File:** `stage2_operations_mastery.json`
- Advanced wallet operations
- Transaction monitoring
- Blockchain state queries
- Multi-wallet coordination

### Stage 3: AI Operations
**File:** `stage3_ai_operations.json`
- AI job submission
- Task management
- Result retrieval
- Agent coordination

### Stage 4: Marketplace Economics
**File:** `stage4_marketplace_economics.json`
- Marketplace interaction
- Resource trading
- Price discovery
- Economic modeling

### Stage 5: Expert Operations
**File:** `stage5_expert_operations.json`
- Advanced agent behaviors
- Autonomous decision making
- Complex task orchestration
- Performance optimization

### Stage 6: Agent Identity SDK
**File:** `stage6_agent_identity_sdk.json`
- Identity management
- Authentication flows
- Permission handling
- Security protocols

### Stage 7: Cross-Node Training
**File:** `stage7_cross_node_training.json`
- Multi-node coordination
- Distributed consensus
- Network topology awareness
- Failover handling

### Stage 8: Advanced Agent Specialization
**File:** `stage8_advanced_agent_specialization.json`
- Domain-specific capabilities
- Specialized knowledge bases
- Expert system integration
- Custom skill development

### Stage 9: Multi-Chain Architecture
**File:** [`stage9_multi_chain_architecture.json`](./stage9_multi_chain_architecture.json)
- Cross-chain operations
- Bridge protocols
- Multi-chain asset management
- Interoperability patterns
**Related Scenarios:** [42 Cross Chain Atomic Swap](../scenarios/47_cross_chain_atomic_swap.md), [44 Dispute Resolution](../scenarios/44_dispute_resolution.md), [45 Zero Knowledge Proofs](../scenarios/45_zero_knowledge_proofs.md), [46 Multi Chain Island Architecture](../scenarios/46_multi_chain_island_architecture.md)

### Stage 10: Failure Recovery
**File:** `stage10_failure_recovery.json`
- Error handling strategies
- Recovery procedures
- Fault tolerance mechanisms
- System resilience

### Stage 11: Agent Communication
**File:** `stage11_agent_communication.json`
- Message sending protocols (hierarchical, peer-to-peer, broadcast)
- Message history and retrieval
- Peer connection management
- Communication performance metrics

## Training Schema

The training stages follow a standardized JSON schema defined in `training_schema.json`, which specifies:

- Stage metadata and prerequisites
- Command sequences and validation criteria
- Expected outcomes and success metrics
- Resource requirements and dependencies

**Setup Method:** The schema references `setup_method` which indicates how to configure the environment for each stage. Currently, all stages use the Python-based setup system (`aitbc.training_setup` module) rather than individual shell scripts. See `ENVIRONMENT_SETUP.md` for details on the Python API and CLI for environment setup.

## Environment Setup

Before beginning training, ensure the environment is properly configured:

**File:** `ENVIRONMENT_SETUP.md`
- System requirements
- Dependency installation
- Configuration steps
- Validation procedures

## Operations Audit

**File:** `OPERATIONS_AUDIT.md`
- Training execution records
- Performance metrics
- Issue tracking
- Improvement recommendations

## Scenario Mapping

**File:** `SCENARIO_STAGE_MAPPING.md`
- Real-world scenario mappings
- Use case correlations
- Practical application examples
- Integration patterns

## Quick Start for Hermes

1. **Review `HERMES_LEARNING_PROMPT.md`** for detailed learning instructions
2. **Analyze `training_schema.json`** to understand the stage structure
3. **Study `ENVIRONMENT_SETUP.md`** to understand environment requirements
4. **Begin with Stage 1** (`stage1_foundation.json`) and progress sequentially
5. **For each stage, provide:**
   - Debug messages for issues found
   - Suggestions for improvements
   - Potential failure points
   - Cross-stage dependency notes
6. **Use `SCENARIO_STAGE_MAPPING.md`** to understand practical applications

## Prerequisites

- AITBC blockchain node running and synchronized
- Python 3.13.5 with required dependencies
- Valid wallet accounts with sufficient AIT tokens
- Network connectivity to blockchain RPC endpoints
- Basic understanding of blockchain concepts

## Validation

Each training stage includes validation criteria to ensure successful completion:

- Command execution success
- Expected state changes
- Transaction confirmations
- Balance verifications
- Health check validations

## Troubleshooting

**Hermes:** When analyzing this section, identify:
- Common failure patterns across stages
- Missing troubleshooting steps
- Ambiguous error handling instructions
- Gaps in the troubleshooting coverage

For issues during training:

1. Check [`ENVIRONMENT_SETUP.md`](./ENVIRONMENT_SETUP.md) for configuration problems
2. Review [`OPERATIONS_AUDIT.md`](./OPERATIONS_AUDIT.md) for known issues and solutions
3. Verify blockchain node synchronization status
4. Confirm wallet balances and permissions
5. Check network connectivity to RPC endpoints

## Related Resources

- [AITBC Master Index](../MASTER_INDEX.md)
- [Agent Documentation](../agents/README.md)
- [Agent SDK Documentation](../agent-sdk/README.md)
- [Training Schema](training_schema.json)

## Quality Metrics

- **Stage Coverage:** 11 comprehensive training stages
- **Schema Compliance:** 100% adherence to training schema
- **Documentation Completeness:** All stages documented with examples
- **Validation Coverage:** Each stage includes success criteria

---

**Last Updated:** 2026-05-07
**Maintained By:** AITBC Development Team
