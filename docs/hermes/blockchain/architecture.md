# Architecture Notes

This document describes the architectural design of Hermes blockchain integrations.

## Hybrid GPU Resource Tracking

The GPU resource tracking uses a hybrid architecture to balance decentralization with performance and cost:

### On-Chain (Immutable Proof)
- GPU registration with immutable specs
- GPU allocation records
- Transaction history

### Off-Chain (Operational Data)
- Real-time GPU status
- Performance metrics
- Heartbeat monitoring
- Dynamic availability updates

### Design Rationale
This hybrid approach ensures:
- **Immutability**: Critical data (registration, allocations) is permanently recorded on-chain
- **Performance**: Real-time operations (status, metrics) remain fast and responsive
- **Cost**: Only essential data is stored on-chain to minimize gas fees
- **Resilience**: GPU remains operational even if blockchain registration fails

### GPU Service Integration
The GPU service registers GPUs locally first, then attempts blockchain registration asynchronously:
1. Register GPU in local database (GPURegistry table)
2. Asynchronously post registration to blockchain RPC
3. Log success or failure (non-blocking)
4. If blockchain registration fails, GPU remains operational locally
5. CLI can be used for explicit on-chain registration

## Cross-Node Operations

All blockchain integrations use the hub RPC (`hub.aitbc.bubuit.net:8006`) for cross-node operations.

### Benefits
- **Transaction propagation**: Transactions are broadcast across the network
- **Consistent state**: All nodes maintain consistent blockchain state
- **P2P gossip**: Transactions are disseminated via P2P network
- **Centralized coordination**: Hub serves as coordination point for cross-node operations

### Flow
1. Hermes agent submits transaction to hub RPC
2. Hub validates and records transaction in local database
3. Hub broadcasts transaction to P2P network
4. Other nodes receive and validate transaction
5. Transaction is included in next block
6. Block is propagated to all nodes

## Environment Configuration

### Key Environment Variables

**CHAIN_ID**
- Description: Blockchain chain identifier
- Default: `ait-hub.aitbc.bubuit.net`
- Location: `/etc/aitbc/blockchain.env`
- Usage: Identifies which blockchain to operate on

**HUB_DISCOVERY_URL**
- Description: Hub discovery URL for cross-node operations
- Default: `hub.aitbc.bubuit.net`
- Location: `/etc/aitbc/blockchain.env`
- Usage: Replaces localhost in RPC URLs for cross-node access

**BLOCKCHAIN_RPC_URL**
- Description: RPC endpoint for blockchain operations
- Default: `http://hub.aitbc.bubuit.net:8006`
- Location: `/etc/aitbc/blockchain.env`
- Usage: Base URL for all blockchain RPC calls

### Configuration Priority
1. Environment variables (highest priority)
2. Configuration files
3. Hardcoded defaults (fallback)

## Database Schema

### Staking Table
- `address`: Wallet address
- `amount`: Staked amount (in wei)
- `lock_days`: Lock period in days
- `locked_until`: Unix timestamp when lock expires
- `chain_id`: Blockchain identifier

### Agent Identity Table
- `agent_id`: Unique agent identifier
- `agent_address`: Agent wallet address
- `display_name`: Human-readable name
- `agent_type`: Type of agent (provider, consumer, etc.)
- `capabilities`: JSON object of agent capabilities
- `is_verified`: Verification status
- `chain_id`: Blockchain identifier

### Governance Proposal Table
- `proposal_id`: Unique proposal identifier
- `proposer_address`: Wallet address of proposer
- `title`: Proposal title
- `description`: Proposal description
- `category`: Proposal category
- `voting_days`: Voting period in days
- `status`: Proposal status (active, passed, rejected)
- `chain_id`: Blockchain identifier

### Governance Vote Table
- `proposal_id`: Reference to proposal
- `voter_address`: Wallet address of voter
- `vote_type`: Vote type (for, against, abstain)
- `voting_power`: Voting power used
- `reason`: Vote reason
- `chain_id`: Blockchain identifier

### GPU Registration Table
- `gpu_id`: Unique GPU identifier
- `miner_id`: Miner/provider ID
- `model`: GPU model
- `memory_gb`: GPU memory in GB
- `cuda_version`: CUDA version
- `region`: Geographic region
- `capabilities`: List of GPU capabilities
- `price_per_hour`: Price per hour in AIT
- `status`: GPU status (active, deactivated)
- `registered_by`: Wallet address of registrant
- `chain_id`: Blockchain identifier

### GPU Allocation Table
- `allocation_id`: Unique allocation identifier
- `gpu_id`: Reference to GPU
- `client_id`: Client wallet address
- `duration_hours`: Allocation duration
- `total_cost`: Total cost in AIT
- `status`: Allocation status (active, completed, cancelled)
- `allocated_by`: Wallet address of allocator
- `chain_id`: Blockchain identifier

## Security Considerations

### Wallet Security
- Private keys stored in `~/.aitbc/wallets/`
- Wallet files encrypted with password
- Never expose private keys in logs or error messages

### Transaction Security
- All transactions signed with Ed25519
- Nonce-based replay protection
- Address format validation (bech32 to hex conversion)

### RPC Security
- HTTPBearer authentication available
- Rate limiting on all endpoints
- Input validation on all parameters

## Performance Considerations

### Async Operations
- GPU service uses async HTTP calls for blockchain registration
- Non-blocking design ensures service responsiveness
- Failed blockchain calls don't affect local operations

### Caching
- Chain ID cached after first RPC query
- Wallet addresses cached during session
- GPU status queries cached locally

### Rate Limiting
- Staking operations: 20 requests per minute
- Governance operations: 50 requests per minute
- GPU operations: 50 requests per minute
- Query operations: 200 requests per minute
