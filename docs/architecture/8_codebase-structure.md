# AITBC Codebase Structure

> Monorepo layout for the AI Token Blockchain platform.

## Top-Level Overview

```
aitbc/
├── apps/                    # Core microservices and web applications
├── assets/                  # Shared frontend assets (CSS, JS, fonts)
├── cli/                     # Command-line interface tools
├── contracts/               # Solidity smart contracts (standalone)
├── dev/                     # Development tools and configuration
├── docs/                    # Markdown documentation (10 numbered sections)
├── extensions/              # Browser extensions (Firefox wallet)
├── packages/                # Shared libraries and SDKs
├── plugins/                 # Plugin integrations (Ollama)
├── scripts/                 # All scripts, organized by purpose
│   ├── agent/               # Agent CLI helper scripts
│   ├── benchmarking/        # Performance benchmarking
│   ├── ci/                  # CI/CD pipeline scripts
│   ├── dependency-management/ # Dependency update scripts
│   ├── deployment/          # Deployment scripts
│   ├── development/         # Dev tools, local services
│   ├── git/                 # Git synchronization scripts
│   ├── github/              # GitHub PR automation
│   ├── maintenance/         # System maintenance scripts
│   ├── monitoring/          # Monitoring and health checks
│   ├── multi-node/          # Multi-node blockchain testing
│   ├── notifications/       # Notification configuration
│   ├── plan/                # Infrastructure planning scripts
│   ├── security/            # Security scanning
│   ├── service-management/  # Service lifecycle management
│   ├── services/            # Service-specific scripts
│   ├── setup/               # Installation scripts
│   ├── sync/                # Data synchronization
│   ├── testing/             # Test runners and verification
│   └── workflow/            # Multi-node workflow scripts
├── tests/                   # Pytest test suites (unit, integration, e2e, security, load)
├── website/                 # Public-facing website and HTML documentation
├── .gitignore
├── .editorconfig
├── .secrets.baseline        # detect-secrets baseline
├── LICENSE                  # MIT License
├── pyproject.toml           # Python project configuration, incl. all pytest settings
├── poetry.lock              # Poetry lock file
├── uv.lock                  # uv lock file
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
│   ├── consensus/           # Consensus implementations (poa.py, multi_validator_poa.py, pbft.py)
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
│   ├── services/            # Business logic (jobs, miners, payments, receipts, ZK proofs, encryption, HSM, blockchain, ethereum wallet)
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

### blockchain-explorer

Agent-first blockchain explorer built with Python FastAPI and built-in HTML interface.

```
apps/blockchain-explorer/
├── main.py                   # FastAPI application entry
└── systemd service           # Production service file
```

### exchange

Ethereum/AITBC trading exchange with order book, price ticker, and admin panel.

```
apps/exchange/
├── server.py                # WebSocket price server
├── simple_exchange_api.py   # Exchange REST API (SQLite)
├── simple_exchange_api_pg.py # Exchange REST API (PostgreSQL)
├── exchange_api.py          # Full exchange API
├── ethereum-wallet.py        # Ethereum on-ramp integration
├── database.py              # Database layer
├── build.py                 # Production build script
├── index.html               # Exchange frontend
├── admin.html               # Admin panel
└── scripts/                 # PostgreSQL migration
```

### wallet

Wallet service with receipt verification and ledger management.

```
apps/wallet/
├── src/app/
│   ├── main.py              # FastAPI entry point
│   ├── settings.py          # Configuration
│   ├── ledger_mock/         # Mock ledger with PostgreSQL adapter
│   └── receipts/            # Receipt verification service
├── scripts/                 # PostgreSQL migration
├── tests/                   # Wallet API and receipt tests
└── pyproject.toml
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

### agent-coordinator

Agent coordination and management service.

```
apps/agent-coordinator/
├── src/app/
│   ├── main.py              # FastAPI entry point
│   ├── monitoring/          # Monitoring and alerting
│   └── services/            # Agent coordination services
└── tests/                   # Agent coordination tests
```

### ai-engine

AI/ML inference engine for agent tasks.

```
apps/ai-engine/
├── src/
│   └── main.py              # AI engine entry point
└── models/                  # Model storage
```

### api-gateway

API gateway for routing and load balancing.

```
apps/api-gateway/
├── src/
│   └── main.py              # Gateway entry point
└── config/                  # Routing configuration
```

### blockchain-event-bridge

Event bridge for blockchain event processing.

```
apps/blockchain-event-bridge/
├── src/
│   └── main.py              # Bridge entry point
└── processors/              # Event processors
```

### bridge-monitor

Monitoring service for cross-chain bridges.

```
apps/bridge-monitor/
├── src/
│   └── main.py              # Monitor entry point
└── checks/                  # Bridge health checks
```

### edge

Edge computing service for distributed processing.

```
apps/edge/
├── src/
│   └── main.py              # Edge service entry point
└── nodes/                   # Edge node management
```

### ffmpeg

Video processing service using FFmpeg.

```
apps/ffmpeg/
├── src/
│   └── main.py              # FFmpeg service entry point
└── processors/              # Video processors
```

### governance

Governance and voting system.

```
apps/governance/
├── src/
│   └── main.py              # Governance entry point
└── proposals/               # Proposal management
```

### gpu

GPU computing service for mining and inference.

```
apps/gpu/
├── src/
│   └── main.py              # GPU service entry point
└── miners/                  # GPU miner management
```

### marketplace

Marketplace service for GPU compute trading.

```
apps/marketplace/
├── src/
│   └── main.py              # Marketplace entry point
└── offers/                  # Offer management
```

### miner

Mining service for blockchain consensus.

```
apps/miner/
├── src/
│   └── main.py              # Miner entry point
└── workers/                 # Mining workers
```

### trading

Trading service for asset exchange.

```
apps/trading/
├── src/
│   └── main.py              # Trading entry point
└── orders/                  # Order management
```

### whisper

Audio processing service using Whisper.

```
apps/whisper/
├── src/
│   └── main.py              # Whisper service entry point
└── models/                  # Whisper models
```

---

## packages/ — Shared Libraries

```
packages/
└── py/
    ├── aitbc-agent-core/    # Agent integration service with protocol-based dependency injection
    ├── aitbc-agent-sdk/     # Agent SDK for external integrations
    ├── aitbc-crypto/        # Cryptographic primitives (signing, hashing, key derivation)
    └── aitbc-sdk/           # Python SDK for coordinator API (receipt fetching/verification)
```

---

## scripts/ — Operations

```
scripts/
├── agent/                   # Agent CLI helper scripts
├── benchmarking/            # Performance benchmarking
├── ci/                      # CI/CD pipeline scripts
├── dependency-management/   # Dependency update scripts
├── deployment/              # Deployment scripts
├── development/             # Dev tools, local services
├── git/                     # Git synchronization scripts
├── github/                  # GitHub PR automation
├── maintenance/             # System maintenance scripts
├── monitoring/              # Monitoring and health checks
├── multi-node/              # Multi-node blockchain testing
├── notifications/           # Notification configuration
├── ops/                     # Operational scripts
├── performance/             # Load and performance tests
├── plan/                    # Infrastructure planning scripts
├── security/                # Security scanning
├── testing/                 # Test runners and verification scripts
└── utils/                   # Shared shell helpers
```

---

## scripts/deployment/ — Deployment Scripts

```
scripts/deployment/
├── deploy.sh                # Main deployment / status / rollback script
├── setup.sh                 # Initial host bootstrap
├── update.sh                # Idempotent update path
├── install-profiles.sh      # Declarative Python dependency profiles
├── run-migrations.sh        # Alembic migration runner
├── create_aitbc_user.sh     # Service user creation
├── validate-env.sh          # Environment validation
└── init_proposer.py         # Hub proposer wallet generation
```

---

## tests/ — Test Suites

```
tests/
├── conftest.py              # Shared pytest fixtures
├── smoke/                   # Import smoke tests
├── unit/                    # Unit tests
├── integration/             # Integration tests (needs services)
├── e2e/                     # End-to-end tests
├── security/                # Security tests
├── cli/                     # CLI tests
└── test_*.py                # Top-level test modules
```

Each application also maintains its own `tests/` or `apps/<app>/tests/` directory.

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
| `cli/` | AITBC CLI package (~65 top-level command groups, CI/CD, man page) |
| `mcp-server/` | MCP operation server for live node management |
| `examples/` | Environment and nginx configuration templates |
| `extensions/` | Browser wallet extension source code |
| `contracts/` | Standalone Solidity contracts |
| `systemd/` | Systemd unit files (deprecated; live unit files now live in `apps/<app>/` and `scripts/`) |
| `docs/` | Markdown documentation |
| `assets/` | Shared frontend assets |
