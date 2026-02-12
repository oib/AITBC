# AITBC System Components

Overview of all components in the AITBC platform, their status, and documentation links.

## Core Components

### Blockchain Node
<span class="component-status live">● Live</span>

PoA/PoS consensus with REST/WebSocket RPC, real-time gossip layer, and comprehensive observability. Production-ready with devnet tooling.

[Learn More →](blockchain-node.md)

### Coordinator API
<span class="component-status live">● Live</span>

FastAPI service for job submission, miner registration, and receipt management. SQLite persistence with comprehensive endpoints.

[Learn More →](coordinator-api.md)

### Marketplace Web
<span class="component-status live">● Live</span>

Vite/TypeScript marketplace with offer/bid functionality, stats dashboard, and mock/live data toggle. Production UI ready.

[Learn More →](marketplace-web.md)

### Explorer Web
<span class="component-status live">● Live</span>

Full-featured blockchain explorer with blocks, transactions, addresses, and receipts tracking. Responsive design with live data.

[Learn More →](explorer-web.md)

### Wallet Daemon
<span class="component-status live">● Live</span>

Encrypted keystore with Argon2id + XChaCha20-Poly1305, REST/JSON-RPC APIs, and receipt verification capabilities.

[Learn More →](wallet-daemon.md)

### Trade Exchange
<span class="component-status live">● Live</span>

Bitcoin-to-AITBC exchange with QR payments, user management, and real-time trading. Buy tokens with BTC instantly.

[Learn More →](trade-exchange.md)

### Pool Hub
<span class="component-status live">● Live</span>

Miner registry with scoring engine, Redis/PostgreSQL backing, and comprehensive metrics. Live matching API deployed.

[Learn More →](pool-hub.md)

## Architecture Overview

The AITBC platform consists of 7 core components working together to provide a complete AI blockchain computing solution:

### Infrastructure Layer

- **Blockchain Node** - Distributed ledger with PoA/PoS consensus
- **Coordinator API** - Job orchestration and management
- **Wallet Daemon** - Secure wallet management

### Application Layer

- **Marketplace Web** - GPU compute marketplace
- **Trade Exchange** - Token trading platform
- **Explorer Web** - Blockchain explorer
- **Pool Hub** - Miner coordination service

### CLI & Tooling

- **AITBC CLI** - 11 command groups, 80+ subcommands (116/116 tests passing)
  - Client, miner, wallet, auth, blockchain, marketplace, admin, config, monitor, simulate, plugin
  - CI/CD via GitHub Actions, man page, shell completion

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
[Marketplace](https://aitbc.bubuit.net/marketplace/)
[Explorer](https://aitbc.bubuit.net/explorer/)
[API Docs](https://aitbc.bubuit.net/api/docs)

## Status Legend

- <span class="component-status live">● Live</span> - Production ready and deployed
- <span class="component-status beta">● Beta</span> - In testing, limited availability
- <span class="component-status dev">● Development</span> - Under active development

## Deployment Information

All components are containerized and can be deployed using Docker Compose:

```bash
# Deploy all components
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Support

For component-specific issues:
- Check individual documentation pages
- Visit the [GitHub repository](https://github.com/aitbc/platform)
- Contact: [aitbc@bubuit.net](mailto:aitbc@bubuit.net)
