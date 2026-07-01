# AITBC Feature Catalog

**Complete inventory of AITBC features with links to dedicated documentation.**

**Last Updated:** 2026-07-01
**Version:** 1.0

---

## How to Use This Catalog

Each feature is listed with its dedicated documentation file (if one exists).
Features without a dedicated doc are marked **No dedicated doc** — see the
linked source file or the relevant release changelog for details.

**Status legend:**
- ✅ Complete and active
- 🚧 Planned / in progress
- ⚠️ Code complete but not activated (requires external audit)
- 🅿️ Parked for re-evaluation
- ~~Deprecated~~

---

## 1. Blockchain Core

### Node Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Block Query | Query blocks by height, get chain head, genesis allocations | [docs/blockchain/0_readme.md](blockchain/0_readme.md) | ✅ | — |
| Transaction Submission | Submit transactions to the blockchain via RPC | [docs/blockchain/10_api-blockchain.md](blockchain/10_api-blockchain.md) | ✅ | — |
| Account Management | Create accounts, get balances, state snapshots | [docs/blockchain/0_readme.md](blockchain/0_readme.md) | ✅ | — |
| Faucet | Request test tokens for development | No dedicated doc | ✅ | — |
| Auto Sync | Automatic bulk sync to detect and resolve block gaps | [docs/blockchain/operational-features.md](blockchain/operational-features.md) | ✅ | — |
| Force Sync | Manual triggering of blockchain data synchronization | [docs/blockchain/operational-features.md](blockchain/operational-features.md) | ✅ | — |
| Export/Import Blocks | Export/import blockchain data for backup or recovery | [docs/blockchain/operational-features.md](blockchain/operational-features.md) | ✅ | — |

### Consensus

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Multi-Validator PoA | Multiple validators with PROPOSER, VALIDATOR, STANDBY roles | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ⚠️ | v0.7.5 |
| PBFT Consensus | Byzantine fault tolerance via PBFT protocol | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ⚠️ | v0.7.5 |
| Validator Rotation | Automatic rotation by stake, reputation, or round-robin | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ✅ | — |
| Proposer Selection | Round-robin, stake-weighted, reputation-based, hybrid | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ✅ | — |
| Network Partition Handling | Partition detection with 5-second cooldown | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ✅ | — |
| Fork Selection | Longest chain rule with reorgs within last 10 blocks | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ✅ | — |
| Slashing Conditions | Validator slashing for Byzantine behavior | [docs/blockchain/4_consensus.md](blockchain/4_consensus.md) | ✅ | — |

### Networking

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Federated Mesh | Independent mesh islands with UUID-based IDs | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |
| Island Management | Create, join, leave islands with separate chain IDs | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | v0.6.3 |
| Hub Registration | Any node can register as a hub to provide peer lists | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |
| Island Bridging | Optional connections between islands (mutual approval) | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |
| NAT Traversal | STUN, AutoNAT for public IP discovery behind NAT | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |
| Bootstrap Nodes | Configurable bootstrap nodes for P2P discovery | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |
| Peer Management | Connection limits, peer scoring by latency/availability | [docs/blockchain/6_networking.md](blockchain/6_networking.md) | ✅ | — |

### Multi-Chain

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| MultiChainManager | Manage multiple chains simultaneously with shared ports | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Lifecycle | Start/stop DEFAULT, BILATERAL, MICRO chain types | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Status Tracking | Track chain states: STOPPED, STARTING, RUNNING, ERROR | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Health Monitoring | Background health checks for chain instances | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Cross-Chain Sync | Synchronization between chains via CrossChainSync | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | — |
| Multi-Chain Consensus | Consensus handling across chains | [docs/blockchain/7_multichain.md](blockchain/7_multichain.md) | ✅ | — |

### Sync & Gossip

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Gossip Protocol | P2P gossip for block/tx propagation with versioning | [docs/releases/v0.6.2/change.log](releases/v0.6.2/change.log) | ✅ | v0.6.2 |
| Delta Sync | Sync only changed blocks instead of full chain | [docs/releases/v0.6.2/change.log](releases/v0.6.2/change.log) | ✅ | v0.6.2 |
| Parallel Sync | Sync from multiple peers concurrently | [docs/releases/v0.6.2/change.log](releases/v0.6.2/change.log) | ✅ | v0.6.2 |
| Compact Blocks | Compressed block propagation | [docs/releases/v0.6.2/change.log](releases/v0.6.2/change.log) | ✅ | v0.6.2 |
| HTTP RPC Compression | GZip middleware for RPC responses | No dedicated doc | ✅ | v0.10.1 |

### Disputes & Arbitration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| File Dispute | File a new dispute for resolution | No dedicated doc | ✅ | — |
| Submit Evidence | Submit evidence for a dispute | No dedicated doc | ✅ | — |
| Verify Evidence | Verify evidence (arbitrator only) | No dedicated doc | ✅ | — |
| Arbitration Voting | Submit arbitration vote (arbitrator only) | No dedicated doc | ✅ | — |
| Authorize Arbitrator | Authorize an arbitrator (admin only) | No dedicated doc | ✅ | — |
| Query Disputes | Get active, arbitrator, or user disputes | No dedicated doc | ✅ | — |

### Smart Contracts

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Deploy Contract | Deploy a smart contract to the blockchain | No dedicated doc | ✅ | — |
| Call Contract | Call a contract method | No dedicated doc | ✅ | — |
| Verify ZK Proof | Verify a zero-knowledge proof | [docs/apps/crypto/zk-circuits.md](apps/crypto/zk-circuits.md) | ✅ | — |
| List Contracts | List deployed contracts | No dedicated doc | ✅ | — |
| Messaging Contracts | Deploy messaging contracts for forum topics | No dedicated doc | ✅ | — |
| Forum Topics | Create topics, post messages, vote on messages | No dedicated doc | ✅ | — |
| Agent Reputation | Get agent reputation from messaging contracts | No dedicated doc | ✅ | — |
| Message Moderation | Moderate messages in forums | No dedicated doc | ✅ | — |

### Staking & Identity

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Stake Tokens | Stake tokens for enhanced voting power (2x multiplier) | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.4.12 |
| Unstake Tokens | Unstake tokens to release locked funds | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Staking Info | Get staking information for an address | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Register Agent Identity | Register agent identity on-chain | No dedicated doc | ✅ | — |
| Get Agent Identity | Get agent identity information | No dedicated doc | ✅ | — |
| Verify Agent Identity | Verify agent identity | No dedicated doc | ✅ | — |

### GPU Resources (On-Chain)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| GPU Registration | Register GPU with immutable specs on blockchain | No dedicated doc | ✅ | — |
| GPU Allocation | Record GPU allocation/booking on-chain | No dedicated doc | ✅ | — |
| GPU Query | Query GPU registrations and allocations | No dedicated doc | ✅ | — |
| Edge Node Registration | Register edge node on blockchain | No dedicated doc | ✅ | v0.10.1 |
| Edge Node Query | Query edge node registration from blockchain | No dedicated doc | ✅ | v0.10.1 |

### Subscription / Lease

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Subscription | Register for block subscription with lease | No dedicated doc | ✅ | — |
| Heartbeat | Extend subscription lease via heartbeat | No dedicated doc | ✅ | — |
| Get Lease Status | Get lease status for a subscriber | No dedicated doc | ✅ | — |
| Get Subscribers | Get all valid subscribers | No dedicated doc | ✅ | — |

---

## 2. Bridge / Cross-Chain

### Bridge Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Bridge Lock | Lock funds for cross-chain transfer | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Bridge Confirm | Confirm and release cross-chain transfer | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Bridge Unlock | Refund a pending bridge transfer | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Get Transfer | Get transfer status by ID | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| List Pending Transfers | List pending bridge transfers | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Bridge Balance | Get bridge balance for a chain | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Bridge Health | Bridge health check | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |
| Batch Lock/Confirm | Batch lock or confirm multiple transfers | [docs/releases/v0.7.0/change.log](releases/v0.7.0/change.log) | ✅ | v0.7.0 |

### Bridge Security

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Validator | Register a bridge validator | [docs/releases/v0.7.1/change.log](releases/v0.7.1/change.log) | ✅ | v0.7.1 |
| Get Validator Set | Get validator set for a chain | [docs/releases/v0.7.1/change.log](releases/v0.7.1/change.log) | ✅ | v0.7.1 |
| Multi-Sig Verification | Multi-signature verification for transfers | [docs/releases/v0.7.1/change.log](releases/v0.7.1/change.log) | ✅ | v0.7.1 |
| Time-Locks | Time-locked transfers with refund windows | [docs/releases/v0.7.1/change.log](releases/v0.7.1/change.log) | ✅ | v0.7.1 |
| Bridge Security Status | Bridge security status check | [docs/releases/v0.7.1/change.log](releases/v0.7.1/change.log) | ✅ | v0.7.1 |
| Bridge Threat Model | Threat modeling for bridge security | [docs/architecture/bridge-threat-model.md](architecture/bridge-threat-model.md) | ✅ | v0.7.1 |

### Bridge Verification

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Store Block Header | Store a remote chain block header | [docs/releases/v0.7.2/change.log](releases/v0.7.2/change.log) | ✅ | v0.7.2 |
| Get Block Header | Get a block header with finality status | [docs/releases/v0.7.2/change.log](releases/v0.7.2/change.log) | ✅ | v0.7.2 |
| Merkle Proof Verification | In-process Merkle proof verification | [docs/releases/v0.7.2/change.log](releases/v0.7.2/change.log) | ✅ | v0.7.2 |
| Bridge Oracle Status | Bridge oracle/verification status | [docs/releases/v0.7.2/change.log](releases/v0.7.2/change.log) | ✅ | v0.7.2 |

### Atomic Settlement

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Escrow | Create cross-chain escrow for atomic settlement | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| Lock Escrow Funds | Lock escrow funds | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| Verify Lock Proof | Verify lock proof | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| Execute Trade | Execute trade on destination chain | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| HTLC Contract | Hashed timelock contract integration | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |

### Cross-Chain Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Cross-Chain Reputation | Unified reputation across EVM chains | [docs/blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md](blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md) | ✅ | — |
| Reputation Aggregation | Unified scores with configurable weighting | [docs/blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md](blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md) | ✅ | — |
| Anomaly Detection | Automatic detection of reputation changes | [docs/blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md](blockchain/cross-chain/CROSS_CHAIN_REPUTATION_FINAL_INTEGRATION.md) | ✅ | — |

---

## 3. Marketplace

### Core Marketplace

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Offers | List offers with filters (status, region, gpu_model, chain_id) | [docs/api/marketplace-api.md](api/marketplace-api.md) | ✅ | — |
| Get Offer | Get a specific offer by ID | [docs/api/marketplace-api.md](api/marketplace-api.md) | ✅ | — |
| Create Offer | Create a new marketplace offer | [docs/api/marketplace-api.md](api/marketplace-api.md) | ✅ | — |
| Cancel Offer | Cancel a marketplace offer | [docs/api/marketplace-api.md](api/marketplace-api.md) | ✅ | — |
| Book Offer | Book/purchase an offer with escrow creation | [docs/api/marketplace-api.md](api/marketplace-api.md) | ✅ | — |
| Offer History | Get offer history | No dedicated doc | ✅ | — |
| Match Request | Match a compute request to best GPU offer (price-time priority) | No dedicated doc | ✅ | v0.6.6 |
| Marketplace Analytics | Get marketplace analytics and performance metrics | No dedicated doc | ✅ | — |
| Dynamic Pricing | Apply dynamic pricing strategies to offers | No dedicated doc | ✅ | — |

### Edge Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Edge Advertise | Advertise edge node GPU capabilities to marketplace | No dedicated doc | ✅ | v0.6.6 |
| List Edge Nodes | List all registered edge nodes | No dedicated doc | ✅ | v0.6.6 |
| Edge Health | Get edge node health status | No dedicated doc | ✅ | v0.6.6 |

### Ratings & Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Rate Offer | Rate a marketplace offer/service | No dedicated doc | ✅ | — |
| Get Ratings | Get ratings for an offer | No dedicated doc | ✅ | — |
| Sync Ratings | Sync ratings to blockchain | No dedicated doc | ✅ | — |
| Service Reputation | Service reputation system | [docs/marketplace/service-reputation-system.md](marketplace/service-reputation-system.md) | ✅ | — |

### Knowledge Graph

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Knowledge Graph | Create a knowledge graph | No dedicated doc | ✅ | — |
| Add Nodes/Edges | Add nodes and edges to a knowledge graph | No dedicated doc | ✅ | — |
| Get Knowledge Graph | Get a knowledge graph | No dedicated doc | ✅ | — |

### Plugin System

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Plugins | List marketplace plugins | No dedicated doc | ✅ | — |
| Install Plugin | Install a marketplace plugin | No dedicated doc | ✅ | — |
| Plugin Offers | Get offers from specific plugins | No dedicated doc | ✅ | — |

### Parameter Automation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Apply Parameters | Apply governance-approved parameters to marketplace | No dedicated doc | ✅ | v0.10.1 |

### Advanced Marketplace (Deprecated)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| ~~Pricing Strategies~~ | ~~TIME_BASED, REPUTATION_BASED, MULTI_FACTOR, PREDICTIVE~~ | [docs/marketplace/advanced-marketplace/02-pricing-strategies.md](marketplace/advanced-marketplace/02-pricing-strategies.md) | ~~Deprecated~~ | v0.5.0 |
| ~~ML-Based Search~~ | ~~Advanced search and recommendations~~ | [docs/marketplace/advanced-marketplace/04-ml-search.md](marketplace/advanced-marketplace/04-ml-search.md) | ~~Deprecated~~ | v0.5.0 |
| ~~External Providers~~ | ~~AWS/GCP/Azure integrations~~ | [docs/marketplace/advanced-marketplace/06-external-providers.md](marketplace/advanced-marketplace/06-external-providers.md) | ~~Deprecated~~ | v0.5.0 |

---

## 4. Governance

### Proposals

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Proposal | Create a governance proposal | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.7.3 |
| List Proposals | List proposals with filters (status, category, proposer) | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Proposal | Get a specific proposal by ID | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Execute Proposal | Execute a passed proposal with logging and timelock | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.4.12 |
| Parameter Automation | Apply parameter changes to target service after execution | [docs/governance/01-ARCHITECTURE.md](governance/01-ARCHITECTURE.md) | ✅ | v0.10.1 |

### Voting

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Cast Vote | Cast a governance vote on a proposal | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.7.3 |
| List Votes | List votes with optional filters | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Voting Power | Get voting power (includes staking 2x multiplier) | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.4.12 |
| Delegate Voting Power | Delegate voting power to another address | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | v0.4.12 |

### Emergency Proposals

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Emergency Proposals | Accelerated timelock, 80% quorum, 2/3 supermajority | [docs/releases/v0.7.4/change.log](releases/v0.7.4/change.log) | ✅ | v0.7.4 |

### On-Chain Submission

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| On-Chain Proposal Submission | Submit proposals to blockchain | [docs/governance/01-ARCHITECTURE.md](governance/01-ARCHITECTURE.md) | ✅ | v0.7.3 |
| On-Chain Vote Submission | Submit votes to blockchain | [docs/governance/01-ARCHITECTURE.md](governance/01-ARCHITECTURE.md) | ✅ | v0.7.3 |

### Profiles & Treasury

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Profile | Create a governance profile | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| List Profiles | List governance profiles | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Treasury | Get DAO treasury information | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Analytics | Get governance analytics by time period | [docs/governance/04-API_ENDPOINTS.md](governance/04-API_ENDPOINTS.md) | ✅ | — |

### Smart Contracts

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| AITBCGovernanceToken | ERC20 token with staking and 2x voting multiplier | [docs/governance/03-SMART_CONTRACTS.md](governance/03-SMART_CONTRACTS.md) | ✅ | — |
| AITBCVoting | Proposal creation, token-weighted voting, quorum | [docs/governance/03-SMART_CONTRACTS.md](governance/03-SMART_CONTRACTS.md) | ✅ | — |

---

## 5. Mining & Pool Hub

### Miner Registration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Miner | Register GPU miner with network | [docs/mining/2_registration.md](mining/2_registration.md) | ✅ | — |
| Miner Status | Get registration status, GPU availability, current jobs | [docs/mining/2_registration.md](mining/2_registration.md) | ✅ | — |
| Update Registration | Update miner settings (price, max-concurrent) | [docs/mining/2_registration.md](mining/2_registration.md) | ✅ | — |
| Deregister Miner | Remove miner from network | [docs/mining/2_registration.md](mining/2_registration.md) | ✅ | — |

### Job Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Poll for Jobs | Poll coordinator for next job | [docs/mining/3_job-management.md](mining/3_job-management.md) | ✅ | — |
| Submit Job Result | Submit job result to coordinator | [docs/mining/3_job-management.md](mining/3_job-management.md) | ✅ | — |
| Report Job Failure | Report job failure | [docs/mining/3_job-management.md](mining/3_job-management.md) | ✅ | — |
| List Jobs | List jobs for a miner | [docs/mining/3_job-management.md](mining/3_job-management.md) | ✅ | — |

### Earnings

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Get Earnings | Get miner earnings | [docs/mining/4_earnings.md](mining/4_earnings.md) | ✅ | — |
| Update Capabilities | Update miner capabilities | No dedicated doc | ✅ | — |

### Pool Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Pool | Create a new mining pool | No dedicated doc | ✅ | v0.6.7 |
| Get Pool | Get pool information | No dedicated doc | ✅ | v0.6.7 |
| List Pools | List all pools with pagination | No dedicated doc | ✅ | v0.6.7 |
| Update Pool | Update pool settings | No dedicated doc | ✅ | v0.6.7 |
| Delete Pool | Delete a pool (must have no miners) | No dedicated doc | ✅ | v0.6.7 |
| Pool Stats | Get pool statistics | No dedicated doc | ✅ | v0.6.7 |
| Join Pool | Join a miner to a pool | No dedicated doc | ✅ | v0.6.7 |
| Leave Pool | Remove a miner from a pool | No dedicated doc | ✅ | v0.6.7 |
| Pool Miners | Get miners in a pool | No dedicated doc | ✅ | v0.6.7 |

### Mining RPC

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Start/Stop Mining | Start/stop mining via RPC | [docs/mining/7_api-miner.md](mining/7_api-miner.md) | ✅ | — |
| Mining Status | Get mining status (aggregated from coordinator-api) | [docs/mining/6_monitoring.md](mining/6_monitoring.md) | ✅ | v0.10.1 |
| List Miners | List active miners (from coordinator-api) | [docs/mining/6_monitoring.md](mining/6_monitoring.md) | ✅ | v0.10.1 |

---

## 6. Agent Coordination

### Agent Registry

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Agent | Register agent with type, capabilities, services | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Discover Agents | Discover agents with filtering | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Get Agent | Get agent information by ID | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Update Agent Status | Update agent status (active, inactive, busy, stale) | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Agent Health Score | Health score based on heartbeat frequency | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |

### Load Balancing

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Least Connections | Select agent with fewest active connections (default) | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Round Robin | Distribute tasks in circular order | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Weighted Round Robin | Based on agent performance weights | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Resource Based | Based on CPU/memory metrics | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Geographic | Based on agent location | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Task Priority Queues | Urgent, critical, high, normal, low | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |

### Task Distribution

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Submit Task | Submit task for distribution with priority | [docs/agent-coordinator/ARCHITECTURE.md](agent-coordinator/ARCHITECTURE.md) | ✅ | v0.6.5 |
| Chain-Aware Distribution | Distribute tasks with chain_id/island_id awareness | [docs/releases/v0.6.5/change.log](releases/v0.6.5/change.log) | ✅ | v0.6.5 |
| Payment Escrow | PaymentEscrow for task distribution | [docs/releases/v0.6.5/change.log](releases/v0.6.5/change.log) | ✅ | v0.6.5 |

### Agent Communication

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Send Message | Send messages between agents | [docs/agent-sdk/AGENT_COMMUNICATION_GUIDE.md](agent-sdk/AGENT_COMMUNICATION_GUIDE.md) | ✅ | v0.6.5 |
| Message Types | DIRECT, BROADCAST, HIERARCHICAL, PEER_TO_PEER, etc. | [docs/agent-sdk/AGENT_COMMUNICATION_GUIDE.md](agent-sdk/AGENT_COMMUNICATION_GUIDE.md) | ✅ | v0.6.5 |
| Hierarchical Protocol | Master-agent to sub-agent communication | [docs/agent-sdk/AGENT_COMMUNICATION_GUIDE.md](agent-sdk/AGENT_COMMUNICATION_GUIDE.md) | ✅ | v0.6.5 |

### Agent Autonomy

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Distributed Decision Making | Consensus-based voting with weighted decisions | [docs/agents/agent-autonomy-features.md](agents/agent-autonomy-features.md) | ✅ | — |
| Self-Healing | Automatic error detection and recovery | [docs/agents/agent-autonomy-features.md](agents/agent-autonomy-features.md) | ✅ | — |
| Autonomous Resource Management | Dynamic resource allocation and pricing | [docs/agents/agent-autonomy-features.md](agents/agent-autonomy-features.md) | ✅ | — |

### Agent SDK

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Agent SDK | Python SDK for agent integration | [docs/agent-sdk/README.md](agent-sdk/README.md) | ✅ | — |
| Agent Identity SDK | Identity verification and registration | [docs/agent-sdk/AGENT_IDENTITY_SDK_DEPLOYMENT_CHECKLIST.md](agent-sdk/AGENT_IDENTITY_SDK_DEPLOYMENT_CHECKLIST.md) | ✅ | — |

### Agent Types

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Compute Provider | Sell computational resources | [docs/agents/compute-provider.md](agents/compute-provider.md) | ✅ | — |
| Compute Consumer | Rent computational power | [docs/agents/compute-consumer-onboarding.md](agents/compute-consumer-onboarding.md) | ✅ | — |
| Platform Builder | Contribute code improvements | [docs/agents/platform-builder-onboarding.md](agents/platform-builder-onboarding.md) | ✅ | — |
| Swarm Coordinator | Participate in collective intelligence | [docs/agents/swarm-coordinator-onboarding.md](agents/swarm-coordinator-onboarding.md) | ✅ | — |

---

## 7. Trading

### Trade Requests

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Request | Create a new trade request | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Requests | List trade requests with filters | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| Get Request | Get a specific trade request by ID | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |

### Trade Matches & Agreements

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Match | Create a new trade match | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Matches | List trade matches with filters | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| Create Agreement | Create a trade agreement | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Agreements | List trade agreements with filters | [docs/architecture/6_trade-exchange.md](architecture/6_trade-exchange.md) | ✅ | v0.8.0 |

### Inter-Chain Trading

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Inter-Chain Trade | Create trade between source and destination chains | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |
| Match Trade | Attempt to match a trade | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |
| Match All Trades | Match all pending trades | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |
| Inter-Chain Trade History | View cross-chain trade history | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |

### Offer Sync

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Discover Offers | Discover offers across chains (polling) | [docs/releases/v0.8.1/change.log](releases/v0.8.1/change.log) | ✅ | v0.8.1 |
| Sync Offers | Sync offers from other chains (polling) | [docs/releases/v0.8.1/change.log](releases/v0.8.1/change.log) | ✅ | v0.8.1 |
| Sync Status | Get offer sync status | [docs/releases/v0.8.1/change.log](releases/v0.8.1/change.log) | ✅ | v0.8.1 |
| Offer Cache | Get cached offers | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.8.2 |
| Search Offers | Search offers with filters | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.8.2 |

### Offer Subscription

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Subscribe to Offers | Subscribe to real-time offer updates via gossip | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.8.2 |
| Heartbeat | Extend subscription lease via heartbeat | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.8.2 |
| Subscription Status | Get subscription status | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.8.2 |
| Polling Fallback | Automatic fallback to polling when gossip is silent | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.10.1 |
| Lease Tracker | Redis-based lease tracking for subscription auth | [docs/releases/v0.8.2/change.log](releases/v0.8.2/change.log) | ✅ | v0.10.1 |

### Atomic Settlement (Trading)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Lock Escrow | Lock escrow funds for atomic settlement | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| Settle Trade | Execute atomic cross-chain settlement | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |
| Settlement Status | Get settlement status for a trade | [docs/releases/v0.9.0/change.log](releases/v0.9.0/change.log) | ⚠️ | v0.9.0 |

### Chain Management (Trading)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Chains | List registered trading chains | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |
| Register Chain | Register a new chain for trading | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |
| Chain Health | Check chain health | [docs/releases/v0.8.0/change.log](releases/v0.8.0/change.log) | ✅ | v0.8.0 |

### Exchange Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Payment | Create exchange payment | No dedicated doc | ✅ | — |
| Payment Status | Get payment status | No dedicated doc | ✅ | — |
| Exchange Rates | Get exchange rates | No dedicated doc | ✅ | — |
| Market Stats | Get market statistics | No dedicated doc | ✅ | — |
| Wallet Balance/Info | Get exchange wallet balance and info | No dedicated doc | ✅ | — |

---

## 8. Edge / GPU

### GPU Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List GPUs | List all GPUs with filters | No dedicated doc | ✅ | — |
| Get GPU Listing | Get GPU listing details by ID | No dedicated doc | ✅ | — |
| Remove GPU Listing | Remove GPU listing | No dedicated doc | ✅ | — |
| Scan GPUs | Scan GPUs for a miner | No dedicated doc | ✅ | — |
| GPU Metrics | Get GPU metrics | No dedicated doc | ✅ | — |
| Advertise to Marketplace | Advertise edge GPU capabilities to marketplace | No dedicated doc | ✅ | v0.6.6 |

### Edge Compute

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Submit Compute Request | Submit compute request with optional payment verification | No dedicated doc | ✅ | v0.6.6 |
| List Compute Requests | List compute requests with filters | No dedicated doc | ✅ | — |
| Get Compute Request | Get a specific compute request | No dedicated doc | ✅ | — |
| Compute Result Cache | Cache compute results with TTL | No dedicated doc | ✅ | — |
| Escrow Verification | Verify escrow payment before serving (job_id-based) | No dedicated doc | ✅ | v0.10.1 |

### Edge GPU Setup

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| NVIDIA Driver Installation | Install NVIDIA drivers for GPU support | [docs/architecture/edge_gpu_setup.md](architecture/edge_gpu_setup.md) | ✅ | — |
| CUDA Toolkit Installation | Install CUDA Toolkit for GPU computing | [docs/architecture/edge_gpu_setup.md](architecture/edge_gpu_setup.md) | ✅ | — |
| Ollama Installation | Install Ollama GPU inference engine | [docs/architecture/edge_gpu_setup.md](architecture/edge_gpu_setup.md) | ✅ | — |
| Edge GPU Optimization | Configure edge optimization (region, latency, power) | [docs/architecture/edge_gpu_setup.md](architecture/edge_gpu_setup.md) | ✅ | — |

### Edge Node Registration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Blockchain Registration | Register edge node on blockchain on startup | No dedicated doc | ✅ | v0.10.1 |
| Coordinator Heartbeat | Periodic health reporting to agent-coordinator | No dedicated doc | ✅ | v0.6.6 |

---

## 9. Wallet

### Wallet Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Wallet | Create a new wallet with password and chain ID | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| List Wallets | List all wallets | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Get Wallet | Get wallet details by ID | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Delete Wallet | Delete a wallet | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Unlock/Lock Wallet | Unlock/lock wallet with password | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |

### Wallet Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Get Balance | Get wallet balance | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Sign Transaction | Sign a transaction with wallet | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Send Transaction | Send a transaction from wallet | [docs/architecture/7_wallet.md](architecture/7_wallet.md) | ✅ | — |
| Auto-Import | Auto-import genesis wallet and wallet directory on startup | No dedicated doc | ✅ | — |

### Wallet Bridge Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Bridge Monitoring | Start bridge monitoring on startup | No dedicated doc | ✅ | — |
| Bridge Router | Bridge operations via wallet | No dedicated doc | ✅ | — |

---

## 10. Security

### Secret Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Secret Expiration | Automatic TTL-based expiration for secrets | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Secret Rotation | Version tracking for secret updates | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Encryption Key Rotation | Master key rotation with re-encryption | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |

### Input Validation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Private Key Validation | Format and length checking for Ethereum private keys | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Chain ID Validation | Positive integer validation for chain IDs | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Contract Address Validation | Ethereum address format checking | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Gas Parameter Validation | Reasonable bounds checking for gas price and limit | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |

### Caching & Performance

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Blockchain Caching | Different TTL for accounts, blocks, transactions | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Cache Invalidation | Event-driven cache consistency | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |
| Redis Integration | Distributed caching support | [docs/security/performance-features.md](security/performance-features.md) | ✅ | — |

### Authentication & Authorization

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| JWT Authentication | JWT-based authentication | [docs/security/authentication.md](security/authentication.md) | ✅ | — |
| RBAC | Role-based access control | [docs/security/access-control.md](security/access-control.md) | ✅ | — |
| API Key Management | API key management for service-to-service | [docs/security/api-key-management.md](security/api-key-management.md) | ✅ | — |

### Rate Limiting

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Rate Limiting Middleware | Rate limiting for API endpoints | [docs/security/rate-limiting.md](security/rate-limiting.md) | ✅ | — |
| Custom Key Functions | Custom rate limit key functions | [docs/security/rate-limiting.md](security/rate-limiting.md) | ✅ | — |

### Audit & Monitoring

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Audit Logging | Comprehensive audit logging for security events | [docs/security/logging-monitoring.md](security/logging-monitoring.md) | ✅ | — |
| Security Architecture | Overall security architecture | [docs/security/2_security-architecture.md](security/2_security-architecture.md) | ✅ | — |
| Threat Model | Threat modeling documentation | [docs/security/threat-model.md](security/threat-model.md) | ✅ | — |
| Security Audits | Security audit framework and findings | [docs/security/security-audits.md](security/security-audits.md), [docs/releases/AUDIT.md](releases/AUDIT.md) | ✅ | — |
| Route Security Matrix | Route-level security requirements | [docs/architecture/route_security_matrix.md](architecture/route_security_matrix.md) | ✅ | — |

---

## 11. CLI

### Blockchain & Chain Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Node Operations | Start/stop/status blockchain node | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Chain List | List all available chains | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.6.4 |
| Chain Start/Stop | Start/stop a secondary chain | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.6.4 |
| Sync Operations | Blockchain sync status and control | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.6.2 |

### Node Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Island Create/Join/List | Create, join, list islands | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.6.3 |
| Hub Register/Unregister | Register/unregister as a hub | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Bridge Request/Approve | Request, approve, reject, list bridges | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |

### Governance Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Governance Propose | Create a governance proposal | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.3 |
| Governance Vote | Cast a vote on a proposal | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.3 |
| Governance List/Get/Execute | List, get, execute proposals | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.3 |

### Trade Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Trade Create/List/Get | Create, list, get inter-chain trades | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.8.0 |
| Trade Match/Match-All | Match trades | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.8.0 |
| Trade Discover/Sync | Discover and sync offers | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.8.1 |
| Trade Watch | Watch offers via subscription | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.8.2 |
| Trade Lock-Escrow/Settle | Atomic settlement operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ⚠️ | v0.9.0 |

### Bridge Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Bridge Security-Status | Get bridge security status | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.1 |
| Bridge Register-Validator | Register a bridge validator | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.1 |
| Bridge Oracle-Status | Get bridge oracle/verification status | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.2 |

### Consensus Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Consensus Validators | List consensus validators | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.4 |
| Consensus Status | Get consensus status | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | v0.7.4 |

### Other CLI Commands

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Account Commands | Account management | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Wallet Commands | Wallet management (basic, multisig, staking) | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Marketplace Commands | Marketplace operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| GPU Resources Commands | GPU resource management | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Pool Hub Commands | Pool hub operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Edge Commands | Edge node operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Mining Commands | Start/stop mining | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Monitor Commands | Monitoring operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Analytics Commands | Analytics operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Security Commands | Security operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Config Commands | Configuration management | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |
| Explorer Commands | Blockchain explorer operations | [docs/cli/CLI_DOCUMENTATION.md](cli/CLI_DOCUMENTATION.md) | ✅ | — |

---

## 12. Infrastructure

### Deployment

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Systemd Services | Systemd service configuration for all services | [docs/infrastructure/SYSTEMD_SERVICES.md](infrastructure/SYSTEMD_SERVICES.md) | ✅ | — |
| Production Architecture | Production deployment architecture | [docs/infrastructure/PRODUCTION_ARCHITECTURE.md](infrastructure/PRODUCTION_ARCHITECTURE.md) | ✅ | — |
| Virtual Environment | Python virtual environment configuration | [docs/infrastructure/VIRTUAL_ENVIRONMENT.md](infrastructure/VIRTUAL_ENVIRONMENT.md) | ✅ | — |
| Genesis Generation | Genesis block generation procedures | [docs/infrastructure/genesis_generation.md](infrastructure/genesis_generation.md) | ✅ | — |

### Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Runtime Directories | Directory structure for runtime data | [docs/infrastructure/RUNTIME_DIRECTORIES.md](infrastructure/RUNTIME_DIRECTORIES.md) | ✅ | — |
| Logs Organization | Log file organization and management | [docs/infrastructure/LOGS_ORGANIZATION.md](infrastructure/LOGS_ORGANIZATION.md) | ✅ | — |
| Network Security | Network security recommendations | [docs/infrastructure/NETWORK_SECURITY_RECOMMENDATIONS.md](infrastructure/NETWORK_SECURITY_RECOMMENDATIONS.md) | ✅ | — |
| Microservices Migration | Status of microservices migration | [docs/infrastructure/migration/microservices-migration-status.md](infrastructure/migration/microservices-migration-status.md) | ✅ | — |

### Monitoring

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Health Checks | Health check endpoints for all services | No dedicated doc | ✅ | — |
| Readiness Checks | Readiness checks for database connectivity | No dedicated doc | ✅ | — |
| Prometheus Metrics | Prometheus metrics endpoints | No dedicated doc | ✅ | — |
| Request Logging | Structured request logging with request ID correlation | No dedicated doc | ✅ | — |
| Performance Logging | Request performance timing middleware | No dedicated doc | ✅ | — |

---

## Statistics

| Domain | Total Features | With Dedicated Doc | Without Dedicated Doc |
|--------|---------------|-------------------|----------------------|
| Blockchain Core | 50 | 25 | 25 |
| Bridge / Cross-Chain | 22 | 12 | 10 |
| Marketplace | 20 | 8 | 12 |
| Governance | 18 | 12 | 6 |
| Mining & Pool Hub | 17 | 7 | 10 |
| Agent Coordination | 22 | 10 | 12 |
| Trading | 28 | 12 | 16 |
| Edge / GPU | 14 | 4 | 10 |
| Wallet | 11 | 5 | 6 |
| Security | 20 | 14 | 6 |
| CLI | 30 | 14 | 16 |
| Infrastructure | 12 | 8 | 4 |
| **Total** | **264** | **131** | **133** |

---

## See Also

- [Master Index](MASTER_INDEX.md) — Complete catalog of all documentation files
- [Release Status](releases/STATUS.md) — Release status overview and audit summary
- [Quick Reference](QUICK_REFERENCE.md) — Common commands and operations
- [Architecture](architecture/README.md) — System architecture and design patterns
- [AGENTS.md](../AGENTS.md) — Project rules and agent task plans
