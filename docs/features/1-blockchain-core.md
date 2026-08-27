# Blockchain Core

## 1. Blockchain Core

### Node Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Block Query | Query blocks by height, get chain head, genesis allocations | [docs/blockchain/0_readme.md](../blockchain/0_readme.md) | ✅ | — |
| Transaction Submission | Submit transactions to the blockchain via RPC | [docs/blockchain/10_api-blockchain.md](../blockchain/10_api-blockchain.md) | ✅ | — |
| Account Management | Create accounts, get balances, state snapshots | [docs/blockchain/0_readme.md](../blockchain/0_readme.md) | ✅ | — |
| Faucet | Request test tokens for development | [docs/features/faucet.md](./faucet.md) | ✅ | — |
| Auto Sync | Automatic bulk sync to detect and resolve block gaps | [docs/blockchain/operational-features.md](../blockchain/operational-features.md) | ✅ | — |
| Force Sync | Manual triggering of blockchain data synchronization | [docs/blockchain/operational-features.md](../blockchain/operational-features.md) | ✅ | — |
| Export/Import Blocks | Export/import blockchain data for backup or recovery | [docs/blockchain/operational-features.md](../blockchain/operational-features.md) | ✅ | — |

### Consensus

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Multi-Validator PoA | Multiple validators with PROPOSER, VALIDATOR, STANDBY roles | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ⚠️ | v0.7.5 |
| PBFT Consensus | Byzantine fault tolerance via PBFT protocol | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ⚠️ | v0.7.5 |
| Validator Rotation | Automatic rotation by stake, reputation, or round-robin | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ✅ | — |
| Proposer Selection | Round-robin, stake-weighted, reputation-based, hybrid | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ✅ | — |
| Network Partition Handling | Partition detection with 5-second cooldown | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ✅ | — |
| Fork Selection | Longest chain rule with reorgs within last 10 blocks | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ✅ | — |
| Slashing Conditions | Validator slashing for Byzantine behavior | [docs/blockchain/4_consensus.md](../blockchain/4_consensus.md) | ✅ | — |

### Networking

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Federated Mesh | Independent mesh islands with UUID-based IDs | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |
| Island Management | Create, join, leave islands with separate chain IDs | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | v0.6.3 |
| Hub Registration | Any node can register as a hub to provide peer lists | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |
| Island Bridging | Optional connections between islands (mutual approval) | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |
| NAT Traversal | STUN, AutoNAT for public IP discovery behind NAT | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |
| Bootstrap Nodes | Configurable bootstrap nodes for P2P discovery | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |
| Peer Management | Connection limits, peer scoring by latency/availability | [docs/blockchain/6_networking.md](../blockchain/6_networking.md) | ✅ | — |

### Multi-Chain

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| MultiChainManager | Manage multiple chains simultaneously with shared ports | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Lifecycle | Start/stop DEFAULT, BILATERAL, MICRO chain types | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Status Tracking | Track chain states: STOPPED, STARTING, RUNNING, ERROR | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Chain Health Monitoring | Background health checks for chain instances | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | v0.6.4 |
| Cross-Chain Sync | Synchronization between chains via CrossChainSync | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | — |
| Multi-Chain Consensus | Consensus handling across chains | [docs/blockchain/7_multichain.md](../blockchain/7_multichain.md) | ✅ | — |

### Sync & Gossip

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Gossip Protocol | P2P gossip for block/tx propagation with versioning | [docs/releases/v0.6/v0.6.2_change.log](releases/v0.6/v0.6.2_change.log) | ✅ | v0.6.2 |
| Delta Sync | Sync only changed blocks instead of full chain | [docs/releases/v0.6/v0.6.2_change.log](releases/v0.6/v0.6.2_change.log) | ✅ | v0.6.2 |
| Parallel Sync | Sync from multiple peers concurrently | [docs/releases/v0.6/v0.6.2_change.log](releases/v0.6/v0.6.2_change.log) | ✅ | v0.6.2 |
| Compact Blocks | Compressed block propagation | [docs/releases/v0.6/v0.6.2_change.log](releases/v0.6/v0.6.2_change.log) | ✅ | v0.6.2 |
| HTTP RPC Compression | GZip middleware for RPC responses | [docs/features/http-rpc-compression.md](./http-rpc-compression.md) | ✅ | v0.10.1 |

### Disputes & Arbitration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| File Dispute | File a new dispute for resolution | [docs/features/file-dispute.md](./file-dispute.md) | ✅ | — |
| Submit Evidence | Submit evidence for a dispute | [docs/features/submit-evidence.md](./submit-evidence.md) | ✅ | — |
| Verify Evidence | Verify evidence (arbitrator only) | [docs/features/verify-evidence.md](./verify-evidence.md) | ✅ | — |
| Arbitration Voting | Submit arbitration vote (arbitrator only) | [docs/features/arbitration-voting.md](./arbitration-voting.md) | ✅ | — |
| Authorize Arbitrator | Authorize an arbitrator (admin only) | [docs/features/authorize-arbitrator.md](./authorize-arbitrator.md) | ✅ | — |
| Query Disputes | Get active, arbitrator, or user disputes | [docs/features/query-disputes.md](./query-disputes.md) | ✅ | — |

### Smart Contracts

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Deploy Contract | Deploy a smart contract to the blockchain | [docs/features/deploy-contract.md](./deploy-contract.md) | ✅ | — |
| Call Contract | Call a contract method | [docs/features/call-contract.md](./call-contract.md) | ✅ | — |
| Verify ZK Proof | Verify a zero-knowledge proof | [docs/apps/crypto/zk-circuits.md](../apps/crypto/zk-circuits.md) | ✅ | — |
| List Contracts | List deployed contracts | [docs/features/list-contracts.md](./list-contracts.md) | ✅ | — |
| Messaging Contracts | Deploy messaging contracts for forum topics | [docs/features/messaging-contracts.md](./messaging-contracts.md) | ✅ | — |
| Forum Topics | Create topics, post messages, vote on messages | [docs/features/forum-topics.md](./forum-topics.md) | ✅ | — |
| Agent Reputation | Get agent reputation from messaging contracts | [docs/features/agent-reputation.md](./agent-reputation.md) | ✅ | — |
| Message Moderation | Moderate messages in forums | [docs/features/message-moderation.md](./message-moderation.md) | ✅ | — |

### Staking & Identity

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Stake Tokens | Stake tokens for enhanced voting power (2x multiplier) | [docs/governance/04-API_ENDPOINTS.md](../governance/04-API_ENDPOINTS.md) | ✅ | v0.4.12 |
| Unstake Tokens | Unstake tokens to release locked funds | [docs/governance/04-API_ENDPOINTS.md](../governance/04-API_ENDPOINTS.md) | ✅ | — |
| Get Staking Info | Get staking information for an address | [docs/governance/04-API_ENDPOINTS.md](../governance/04-API_ENDPOINTS.md) | ✅ | — |
| Register Agent Identity | Register agent identity on-chain | [docs/features/register-agent-identity.md](./register-agent-identity.md) | ✅ | — |
| Get Agent Identity | Get agent identity information | [docs/features/get-agent-identity.md](./get-agent-identity.md) | ✅ | — |
| Verify Agent Identity | Verify agent identity | [docs/features/verify-agent-identity.md](./verify-agent-identity.md) | ✅ | — |

### GPU Resources (On-Chain)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| GPU Registration | Register GPU with immutable specs on blockchain | [docs/features/gpu-registration.md](./gpu-registration.md) | ✅ | — |
| GPU Allocation | Record GPU allocation/booking on-chain | [docs/features/gpu-allocation.md](./gpu-allocation.md) | ✅ | — |
| GPU Query | Query GPU registrations and allocations | [docs/features/gpu-query.md](./gpu-query.md) | ✅ | — |
| Edge Node Registration | Register edge node on blockchain | [docs/features/edge-node-registration.md](./edge-node-registration.md) | ✅ | v0.10.1 |
| Edge Node Query | Query edge node registration from blockchain | [docs/features/edge-node-query.md](./edge-node-query.md) | ✅ | v0.10.1 |

### Subscription / Lease

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Subscription | Register for block subscription with lease | [docs/features/register-subscription.md](./register-subscription.md) | ✅ | — |
| Heartbeat | Extend subscription lease via heartbeat | [docs/features/heartbeat.md](./heartbeat.md) | ✅ | — |
| Get Lease Status | Get lease status for a subscriber | [docs/features/get-lease-status.md](./get-lease-status.md) | ✅ | — |
| Get Subscribers | Get all valid subscribers | [docs/features/get-subscribers.md](./get-subscribers.md) | ✅ | — |

---
