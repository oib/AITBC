# AITBC Codebase Structure

> Monorepo layout for the AI Token Blockchain platform.

## Top-Level Overview

```
aitbc/
├── apps/                    # Core microservices and web applications
├── assets/                  # Shared frontend assets (CSS, JS, fonts)
├── cli/                     # Command-line interface tools
├── contracts/               # Solidity smart contracts (standalone)
├── dev-utils/               # Developer utilities and path configs
├── docs/                    # Markdown documentation
├── examples/                # Usage examples and demos
├── extensions/              # Browser extensions (Firefox wallet)
├── home/                    # Local workflow scripts (client/miner simulation)
├── infra/                   # Infrastructure configs (nginx, k8s, terraform, helm)
├── packages/                # Shared libraries and SDKs
├── plugins/                 # Plugin integrations (Ollama)
├── protocols/               # Protocol specs and sample data
├── scripts/                 # Operational and deployment scripts
├── src/                     # Shared Python source (cross-site sync, RPC)
├── systemd/                 # Systemd service unit files
├── tests/                   # Pytest test suites (unit, integration, e2e, security, load)
├── website/                 # Public-facing website and HTML documentation
├── .gitignore
├── .editorconfig
├── LICENSE                  # MIT License
├── pyproject.toml           # Python project configuration
├── pytest.ini               # Pytest settings and markers
└── README.md
```

---

## apps/ — Core Applications

### blockchain-node
Full blockchain node implementation with PoA consensus, gossip relay, mempool, RPC API, WebSocket support, and observability dashboards.

```
apps/blockchain-node/
├── src/aitbc_chain/
│   ├── app.py               # FastAPI application
│   ├── main.py              # Entry point
│   ├── config.py            # Node configuration
│   ├── database.py          # Chain storage
│   ├── models.py            # Block/Transaction models
│   ├── mempool.py           # Transaction mempool
│   ├── metrics.py           # Prometheus metrics
│   ├── logger.py            # Structured logging
│   ├── consensus/poa.py     # Proof-of-Authority consensus
│   ├── gossip/              # P2P gossip protocol (broker, relay)
│   ├── observability/       # Dashboards and exporters
│   └── rpc/                 # JSON-RPC router and WebSocket
├── scripts/                 # Genesis creation, key generation, benchmarks
├── tests/                   # Unit tests (models, gossip, WebSocket, observability)
└── pyproject.toml
```

### coordinator-api
Central job coordination API with marketplace, payments, ZK proofs, multi-tenancy, and governance.

```
apps/coordinator-api/
├── src/app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration
│   ├── database.py          # Database setup
│   ├── deps.py              # Dependency injection
│   ├── exceptions.py        # Custom exceptions
│   ├── logging.py           # Logging config
│   ├── metrics.py           # Prometheus metrics
│   ├── domain/              # Domain models (job, miner, payment, user, marketplace, gpu_marketplace)
│   ├── models/              # DB models (registry, confidential, multitenant, services)
│   ├── routers/             # API endpoints (admin, client, miner, marketplace, payments, governance, exchange, explorer, ZK)
│   ├── services/            # Business logic (jobs, miners, payments, receipts, ZK proofs, encryption, HSM, blockchain, bitcoin wallet)
│   ├── storage/             # Database adapters (SQLite, PostgreSQL)
│   ├── middleware/          # Tenant context middleware
│   ├── repositories/        # Data access layer
│   └── schemas/             # Pydantic schemas
├── aitbc/settlement/        # Cross-chain settlement (LayerZero bridge)
├── migrations/              # SQL migrations (schema, indexes, data, payments)
├── scripts/                 # PostgreSQL migration scripts
├── tests/                   # API tests (jobs, marketplace, ZK, receipts, miners)
└── pyproject.toml
```

### explorer-web
Blockchain explorer SPA built with TypeScript and Vite.

```
apps/explorer-web/
├── src/
│   ├── main.ts              # Application entry
│   ├── config.ts            # API configuration
│   ├── components/          # UI components (header, footer, data mode toggle, notifications)
│   ├── lib/                 # Data models and mock data
│   └── pages/               # Page views (overview, blocks, transactions, addresses, receipts)
├── public/                  # Static assets (CSS themes, mock JSON data)
├── tests/e2e/               # Playwright end-to-end tests
├── vite.config.ts
└── tsconfig.json
```

### marketplace-web
GPU compute marketplace frontend built with TypeScript and Vite.

```
apps/marketplace-web/
├── src/
│   ├── main.ts              # Application entry
│   ├── lib/                 # API client and auth
│   └── style.css            # Styles
├── public/                  # Mock data (offers, stats)
├── vite.config.ts
└── tsconfig.json
```

### wallet-daemon
Wallet service with receipt verification and ledger management.

```
apps/wallet-daemon/
├── src/app/
│   ├── main.py              # FastAPI entry point
│   ├── settings.py          # Configuration
│   ├── ledger_mock/         # Mock ledger with PostgreSQL adapter
│   └── receipts/            # Receipt verification service
├── scripts/                 # PostgreSQL migration
├── tests/                   # Wallet API and receipt tests
└── pyproject.toml
```

### trade-exchange
Bitcoin/AITBC trading exchange with order book, price ticker, and admin panel.

```
apps/trade-exchange/
├── server.py                # WebSocket price server
├── simple_exchange_api.py   # Exchange REST API (SQLite)
├── simple_exchange_api_pg.py # Exchange REST API (PostgreSQL)
├── exchange_api.py          # Full exchange API
├── bitcoin-wallet.py        # Bitcoin wallet integration
├── database.py              # Database layer
├── build.py                 # Production build script
├── index.html               # Exchange frontend
├── admin.html               # Admin panel
└── scripts/                 # PostgreSQL migration
```

### pool-hub
Mining pool management with job matching, miner scoring, and Redis caching.

```
apps/pool-hub/
├── src/
│   ├── app/                 # Legacy app structure (routers, registry, scoring)
│   └── poolhub/             # Current app (routers, models, repositories, services, Redis)
├── migrations/              # Alembic migrations
└── tests/                   # API and repository tests
```

### zk-circuits
Zero-knowledge proof circuits for receipt verification.

```
apps/zk-circuits/
├── circuits/receipt.circom  # Circom circuit definition
├── generate_proof.js        # Proof generation
├── test.js                  # Circuit tests
└── benchmark.js             # Performance benchmarks
```

---

## packages/ — Shared Libraries

```
packages/
├── py/
│   ├── aitbc-crypto/        # Cryptographic primitives (signing, hashing, key derivation)
│   └── aitbc-sdk/           # Python SDK for coordinator API (receipt fetching/verification)
└── solidity/
    └── aitbc-token/         # ERC-20 AITBC token contract with Hardhat tooling
```

---

## scripts/ — Operations

```
scripts/
├── aitbc-cli.sh             # Main CLI entry point
├── deploy/                  # Deployment scripts (container, remote, blockchain, explorer, exchange, nginx)
├── gpu/                     # GPU miner management (host miner, registry, exchange integration)
├── service/                 # Service lifecycle (start, stop, diagnose, fix)
├── testing/                 # Test runners and verification scripts
├── test/                    # Individual test scripts (coordinator, GPU, explorer)
├── ci/                      # CI pipeline scripts
├── ops/                     # Operational scripts (systemd install)
└── dev/                     # Development tools (WebSocket load test)
```

---

## infra/ — Infrastructure

```
infra/
├── nginx/                   # Nginx configs (reverse proxy, local, production)
├── k8s/                     # Kubernetes manifests (backup, cert-manager, network policies, sealed secrets)
├── helm/                    # Helm charts (coordinator deployment, values per environment)
├── terraform/               # Terraform modules (Kubernetes cluster, environments: dev/staging/prod)
└── scripts/                 # Infra scripts (backup, restore, chaos testing)
```

---

## tests/ — Test Suites

```
tests/
├── cli/                     # CLI tests (141 unit + 24 integration tests)
│   ├── test_cli_integration.py  # CLI → live coordinator integration tests
│   └── test_*.py            # CLI unit tests (admin, auth, blockchain, client, config, etc.)
├── unit/                    # Unit tests (blockchain node, coordinator API, wallet daemon)
├── integration/             # Integration tests (blockchain node, full workflow)
├── e2e/                     # End-to-end tests (user scenarios, wallet daemon)
├── security/                # Security tests (confidential transactions, comprehensive audit)
├── load/                    # Load tests (Locust)
├── conftest.py              # Shared pytest fixtures
└── test_blockchain_nodes.py # Live node connectivity tests
```

---

## website/ — Public Website

```
website/
├── index.html               # Landing page
├── 404.html                 # Error page
├── docs/                    # HTML documentation (per-component pages, CSS, JS)
├── dashboards/              # Admin and miner dashboards
├── BrowserWallet/           # Browser wallet interface
├── extensions/              # Packaged browser extensions (.zip, .xpi)
└── aitbc-proxy.conf         # Nginx proxy config for website
```

---

## Other Directories

| Directory | Purpose |
|-----------|---------|
| `cli/` | AITBC CLI package (12 command groups, 90+ subcommands, 141 unit + 24 integration tests, CI/CD, man page, plugins) |
| `plugins/ollama/` | Ollama LLM integration (client plugin, miner plugin, service layer) |
| `home/` | Local simulation scripts for client/miner workflows |
| `extensions/` | Firefox wallet extension source code |
| `contracts/` | Standalone Solidity contracts (ZKReceiptVerifier) |
| `protocols/` | Protocol sample data (signed receipts) |
| `src/` | Shared Python modules (cross-site sync, RPC router) |
| `systemd/` | Systemd unit files for all AITBC services |
| `dev-utils/` | Developer utilities (Python path config) |
| `docs/` | Markdown documentation (guides, reports, reference, tutorials, operator docs) |
| `assets/` | Shared frontend assets (Tailwind CSS, FontAwesome, Lucide icons, Axios) |
