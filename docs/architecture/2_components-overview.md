# AITBC System Components

Overview of all components in the AITBC platform, their status, and documentation links.

## Core Components

### Blockchain Node

● Live

Multi-validator Proof-of-Authority consensus with optional PBFT finality, REST/WebSocket RPC, real-time gossip layer, and comprehensive observability. Production-ready with devnet tooling.

[Learn More →](../development/1_overview.md#blockchain-node)

### Coordinator API

● Live

FastAPI service for job submission, miner registration, and receipt management. SQLite persistence with comprehensive endpoints.

[Learn More →](../development/1_overview.md#coordinator-api)

### Marketplace Web

● Live

Vite/TypeScript market with offer/bid functionality, stats dashboard, and mock/live data toggle. Production UI ready.

[Learn More →](../blockchain/0_readme.md)

### Blockchain Explorer

● Live

Agent-first Python FastAPI blockchain explorer with complete API and built-in HTML interface. TypeScript frontend merged and deleted for simplified architecture. Production-ready on port 8100.

[Learn More →](../18_explorer/)

### Wallet Daemon

● Live

Encrypted keystore with Argon2id + XChaCha20-Poly1305, REST/JSON-RPC APIs, and receipt verification capabilities.

[Learn More →](7_wallet.md)

### Trade Exchange

● Live

Ethereum-to-AITBC exchange with QR payments, user management, and real-time trading. Buy tokens with ETH instantly.

[Learn More →](6_trade-exchange.md)

### ZK Circuits Engine

● Live

Zero-knowledge proof circuits for privacy-preserving ML operations. Includes inference verification, training verification, and cryptographic proof generation using Groth16.

[Learn More →](../releases/v0.4/v0.4.2_zk-circuits.md)

### FHE Service

● Development

Fully Homomorphic Encryption service for encrypted computation on sensitive ML data. TenSEAL integration with CKKS/BFV scheme support. Not yet wired into the production job pipeline.

[Learn More →](../development/fhe-service.md)

### Enhanced Edge GPU

● Live

Consumer GPU optimization with dynamic discovery, latency measurement, and edge-aware scheduling. Supports Turing, Ampere, and Ada Lovelace architectures.

[Learn More →](edge_gpu_setup.md)

### Pool Hub

● Live

Miner registry with scoring engine, Redis/PostgreSQL backing, and comprehensive metrics. Live matching API deployed.

[Learn More →](../development/1_overview.md#pool-hub)

## Architecture Overview

The AITBC platform consists of 8 core components working together to provide a complete AI blockchain computing solution:

### Infrastructure Layer

- **Blockchain Node** - Distributed ledger with multi-validator PoA (optional PBFT)
- **Coordinator API** - Job orchestration and management
- **Wallet Daemon** - Secure wallet management

### Application Layer

- **Market Web** - GPU compute market
- **Trade Exchange** - Token trading platform
- **Explorer Web** - Blockchain explorer
- **Pool Hub** - Miner coordination service

### CLI & Tooling

- **AITBC CLI** - top-level command groups are shown by default (`aitbc --help`); hidden and deprecated groups can be listed with `aitbc --show-deprecated`
  - Canonical groups include: `account`, `ai`, `auth`, `bond`, `bridge`, `config`, `market`, `node`, `transactions`, `wallet`, and others
  - `aitbc market` is the default GPU/software marketplace command; the legacy `aitbc marketplace` group has been removed
  - CI/CD via Gitea Actions, man page, shell completion

## Component Interactions

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Clients   │────▶│ Coordinator  │────▶│ Blockchain  │
│             │     │     API      │     │    Node     │
└─────────────┘     └──────────────┘     └─────────────┘
       │                     │                     │
       ▼                     ▼                     ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Wallet    │     │   Pool Hub   │     │   Miners    │
│   Daemon    │     │              │     │             │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Quick Links

[Trade Exchange](https://aitbc.bubuit.net/Exchange/)
[Market](https://aitbc.bubuit.net/market/)
[Explorer](https://aitbc.bubuit.net/explorer/)
[API Docs](https://aitbc.bubuit.net/api/docs)

## Status Legend

- ● Live - Production ready and deployed
- ● Beta - In testing, limited availability
- ● Development - Under active development

## Deployment Information

Production deployments use systemd unit files under `apps/<service>/` and `scripts/` (see `systemctl` commands in the deployment guides). Docker Compose is not used.

## Support

For component-specific issues:

- Check individual documentation pages
- Visit the [GitHub repository](https://github.com/aitbc/platform)
- Contact: [aitbc@bubuit.net](mailto:aitbc@bubuit.net)
