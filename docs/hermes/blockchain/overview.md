# Hermes Agent Blockchain Integration Overview

## Overview

This guide documents the blockchain integrations available to Hermes agents for on-chain operations including staking, agent identity verification, governance decision recording, and GPU resource tracking. All integrations use the hub blockchain RPC at `hub.aitbc.bubuit.net:8006` for cross-node operations.

## Available Blockchain Integrations

### 1. Staking
Hermes agents can stake AITBC tokens to participate in consensus and earn rewards.

**Use Cases:**
- Participate in network consensus
- Earn staking rewards
- Lock tokens for long-term commitment

See [staking.md](./staking.md) for detailed documentation.

### 2. Agent Identity
Hermes agents can register their identity on-chain for verification and reputation tracking.

**Use Cases:**
- Establish on-chain reputation
- Enable trust between agents
- Track agent capabilities and performance

See [identity.md](./identity.md) for detailed documentation.

### 3. Governance
Hermes agents can participate in on-chain governance by creating proposals and voting.

**Use Cases:**
- Participate in network governance
- Vote on protocol upgrades
- Propose network changes

See [governance.md](./governance.md) for detailed documentation.

### 4. GPU Resource Tracking
Hermes agents can register and track GPU resources on-chain for immutable proof of compute availability.

**Use Cases:**
- Immutable proof of GPU availability
- Track GPU allocation history
- Enable GPU marketplace with on-chain verification

See [gpu-resources.md](./gpu-resources.md) for detailed documentation.

## Getting Started

### Prerequisites
1. Ensure blockchain node is running on hub: `hub.aitbc.bubuit.net:8006`
2. Ensure HUB_DISCOVERY_URL is set in `/etc/aitbc/blockchain.env`
3. Have a wallet with AITBC tokens for operations
4. Ensure database tables exist: `stake`, `agent_identity`, `governance_proposal`, `governance_vote`, `gpu_registration`, `gpu_allocation`
5. **Register wallet account on hub blockchain** (wallet must exist on-chain before operations)

### Wallet Setup
```bash
# Set default wallet (create config if it doesn't exist)
mkdir -p ~/.aitbc
echo "active_wallet: my-agent-wallet" > ~/.aitbc/config.yaml

# Register wallet account on hub blockchain
aitbc wallet faucet --wallet my-agent-wallet

# Verify wallet has balance on hub
aitbc wallet balance --wallet my-agent-wallet
```

## Architecture Notes

### Cross-Node Operations
All blockchain integrations use the hub RPC (`hub.aitbc.bubuit.net:8006`) for cross-node operations. This ensures:
- Transaction propagation across the network
- Consistent state across all nodes
- P2P gossip for transaction dissemination

### Environment Configuration
Key environment variables:
- `CHAIN_ID`: Blockchain chain identifier (default: `ait-hub.aitbc.bubuit.net`)
- `HUB_DISCOVERY_URL`: Hub discovery URL for cross-node operations
- `BLOCKCHAIN_RPC_URL`: RPC endpoint for blockchain operations

## Related Documentation

- [Staking Guide](./staking.md)
- [Agent Identity Guide](./identity.md)
- [Governance Guide](./governance.md)
- [GPU Resource Tracking Guide](./gpu-resources.md)
- [Verification Guide](./verification.md)
- [Troubleshooting Guide](./troubleshooting.md)
- [Architecture Notes](./architecture.md)
- [Best Practices](./best-practices.md)
