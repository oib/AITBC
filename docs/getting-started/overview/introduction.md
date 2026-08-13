# What is AITBC?

**Last Updated:** 2026-08-13

> **Note:** This document describes the current AITBC platform. For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md). For the implementation status of each major feature, see [Release Status](../../releases/STATUS.md).

AITBC is a decentralized marketplace for AI compute, powered by a multi-island PoA blockchain. GPU providers (shops) sell compute, clients submit inference or training jobs, and the network handles matching, execution, payment, and settlement on-chain.

## Key components

| Component | Purpose |
|-----------|---------|
| **Hub** | `BLOCKCHAIN_MODE=hub` — produces and broadcasts blocks, runs coordinator, exchange, and discovery endpoints. |
| **Shop** | `MARKET_ROLE=shop` — provides GPU, edge, marketplace, and mining services. |
| **Client** | `MARKET_ROLE=customer` — consumes compute, submits jobs, and syncs as a follower. |
| **Blockchain node** | PoA consensus, P2P gossip, RPC API, and lease-based block sync. |
| **Coordinator API** | Job lifecycle, miner matching, marketplace endpoints, and signed receipts. |
| **Wallet daemon** | Multi-chain wallet management and escrow-backed payments. |
| **CLI** | `aitbc` command-line interface for node, wallet, market, AI, and mining operations. |

## Quick start by role

Use the role that matches what you want to do. Service startup is done through `systemctl` after `setup.sh` installs the appropriate profile.

### Client (consume compute)

```bash
# Submit a text-generation job to the hub's coordinator
aitbc ai submit --wallet my-wallet --type text-generation \
  --prompt "Explain zero-knowledge proofs in one paragraph." \
  --payment 10

# Check the result
aitbc ai status --job-id <job-id>
aitbc ai results --job-id <job-id>
```

See [CLI Guide](cli-guide.md) and [customer↔hub end-to-end scenario](../../scenarios/34_hub_customer_node_e2e.md) for more.

### Shop (provide GPU compute)

```bash
# List a GPU offer and start mining
aitbc market offer --gpu-id gpu-0 --memory 24 --price 100
aitbc mining start --wallet my-wallet
```

See [Miner Quick Start](../mining/miner-quick-start.md) for the full shop path.

### Hub (run an island)

```bash
# Install and start the hub profile
sudo /opt/aitbc/scripts/deployment/setup.sh \
  --open-island https://hub.aitbc.bubuit.net \
  --node-id <unique-node-id>

# Start the blockchain node
sudo systemctl start aitbc-blockchain-node
```

See [Service Selection](../setup-service-selection.md) for the hub service matrix.

## Multi-chain architecture

> **Port Reference:** For authoritative port assignments, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

- **Layer 1**: Wallet Daemon (8108) — Multi-chain wallet management
- **Layer 2**: Coordinator API (8203) — Job and transaction coordination
- **Layer 3**: Blockchain RPC (8202) — Transaction processing and consensus
- **Layer 4**: Consensus (8202) — PoA block validation
- **Layer 5**: P2P Network (7070) — Gossip relay on hub nodes
- **Layer 6**: Blockchain Explorer API (8100) — Block/transaction search
- **Layer 7**: Marketplace / GPU (8102, 8101, 8111) — Compute marketplace and job dispatch

## Feature status

The following areas are on the roadmap and are partially implemented or aspirational. See [Release Status](../../releases/STATUS.md) for exact completeness.

| Feature | Status | Notes |
|---------|--------|-------|
| AI Trading Engine | 🟡 Designed | ML-based trading and portfolio optimization (Phase 4.1). |
| Advanced Analytics Platform | 🟡 Designed | Real-time analytics dashboard and KPI tracking (Phase 4.2). |
| AI-Powered Surveillance | 🟡 Designed | Behavioral analysis and automated alerts (Phase 4.3). |
| Compliance Framework | 🟡 Designed | KYC/AML and regulatory reporting modules (Phase 4). |

## Chain-specific token system

AITBC uses chain-specific tokens for isolation:

- **AITBC-AIT-DEVNET**: devnet tokens for testing
- **AITBC-AIT-TESTNET**: testnet tokens
- **AITBC-MAINNET**: mainnet tokens

Tokens are chain-specific and non-transferable between chains.

## Next steps

- [CLI Guide](cli-guide.md) — Complete command reference
- [Service Selection](../setup-service-selection.md) — Choose your node profile
- [Multi-Chain Operations](../blockchain/cross-chain/) — Cross-chain functionality
- [Security & Compliance](../security/) — Security framework
- [Production Deployment](../deployment/) — Production setup
