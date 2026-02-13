# What is AITBC?

AITBC is a decentralized GPU computing platform that connects AI workloads with GPU providers through a blockchain-coordinated marketplace.

| Role | What you do |
|------|-------------|
| **Client** | Rent GPU power, submit AI/ML jobs, pay with AITBC tokens |
| **Miner** | Provide GPU resources, process jobs, earn AITBC tokens |
| **Node Operator** | Run blockchain infrastructure, validate transactions |

## Key Components

| Component | Purpose |
|-----------|---------|
| Coordinator API | Job orchestration, miner matching, receipt management |
| Blockchain Node | PoA consensus, transaction ledger, token transfers |
| Marketplace Web | GPU offer/bid UI, stats dashboard |
| Trade Exchange | BTC-to-AITBC trading, QR payments |
| Wallet | Key management, staking, multi-sig support |
| CLI | 90+ commands across 12 groups for all roles |

## Quick Start by Role

**Clients** → [2_clients/1_quick-start.md](../2_clients/1_quick-start.md)
```bash
pip install -e .
aitbc config set coordinator_url http://localhost:8000
aitbc client submit --prompt "What is AI?"
```

**Miners** → [3_miners/1_quick-start.md](../3_miners/1_quick-start.md)
```bash
aitbc miner register --name my-gpu --gpu a100 --count 1
aitbc miner poll
```

**Node Operators** → [4_blockchain/1_quick-start.md](../4_blockchain/1_quick-start.md)
```bash
aitbc-node init --chain-id ait-devnet
aitbc-node start
```

## Next Steps

- [2_installation.md](./2_installation.md) — Install all components
- [3_cli.md](./3_cli.md) — Full CLI usage guide
- [../README.md](../README.md) — Documentation navigation
