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
│   ├── agent/               # Agent management scripts
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
├── pyproject.toml           # Python project configuration
├── poetry.lock              # Poetry lock file
├── pytest.ini               # Pytest settings and markers
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

### blockchain-explorer
Agent-first blockchain explorer built with Python FastAPI and built-in HTML interface.

```
apps/blockchain-explorer/
├── main.py                   # FastAPI application entry
├── systemd service           # Production service file
└── EXPLORER_MERGE_SUMMARY.md # Architecture documentation
```

### exchange
Bitcoin/AITBC trading exchange with order book, price ticker, and admin panel.

```
apps/exchange/
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

### agent-daemon
Background agent daemon for task execution.

```
apps/agent-daemon/
├── src/
│   └── main.py              # Daemon entry point
└── config/                  # Agent configuration
```

### agent-management
Agent lifecycle management and plugin system.

```
apps/agent-management/
├── src/app/
│   ├── main.py              # FastAPI entry point
│   ├── services/            # Agent integration services
│   └── examples/            # Plugin examples
└── tests/                   # Agent management tests
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

### agent
Message passing and communication service.

```
apps/agent/
├── src/
│   └── main.py              # Agent entry point
└── handlers/                # Message handlers
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

## scripts/deployment/ — Deployment Scripts

```
scripts/deployment/
├── deploy/                  # Deployment automation scripts
├── deploy.sh                # Main deployment script
├── setup_postgresql_databases.sh  # PostgreSQL setup
└── backup/restore scripts   # Backup and restore utilities
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
| `cli/` | AITBC CLI package (12 command groups, 90+ subcommands, 141 unit + 24 integration tests, CI/CD, man page) |
| `examples/nginx/` | Nginx reverse-proxy configuration for production |
| `extensions/` | Firefox wallet extension source code |
| `contracts/` | Standalone Solidity contracts (ZKReceiptVerifier) |
| `scripts/systemd/` | Systemd unit files for all AITBC services |
| `docs/` | Markdown documentation (10 numbered sections, guides, reference, architecture) |
| `assets/` | Shared frontend assets (Tailwind CSS, FontAwesome, Lucide icons, Axios) |
