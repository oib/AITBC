# AITBC — AI Token Blockchain

Decentralized GPU compute marketplace with blockchain-based job coordination, Ollama inference, ZK receipt verification, and token payments.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

AITBC is a full-stack blockchain platform that connects GPU compute providers (miners) with AI workload consumers (clients) through a decentralized marketplace. The system handles job submission, miner matching, GPU inference execution, cryptographic receipt generation, and on-chain payment settlement.

**Key capabilities:**
- **Blockchain nodes** — PoA consensus, gossip relay, WebSocket RPC
- **Coordinator API** — Job lifecycle, miner registry, GPU marketplace, payments, billing, governance
- **GPU mining** — Ollama-based LLM inference with host GPU passthrough
- **Wallet daemon** — Balance tracking, receipt verification, ledger management
- **Trade exchange** — Bitcoin/AITBC trading with order book and price ticker
- **ZK circuits** — Zero-knowledge receipt verification (Circom/snarkjs)
- **Browser wallet** — Firefox extension for AITBC transactions
- **Explorer** — Real-time blockchain explorer (blocks, transactions, addresses, receipts)

## Architecture

```
Client ──► Coordinator API ──► Pool Hub ──► Miner (GPU/Ollama)
              │                                    │
              ▼                                    ▼
         Marketplace                         ZK Receipt
              │                                    │
              ▼                                    ▼
        Wallet Daemon ◄──── Blockchain Nodes ◄─── Settlement
              │
              ▼
        Trade Exchange
```

## Directory Structure

```
aitbc/
├── apps/                    # Core microservices
│   ├── blockchain-node/     # PoA blockchain node (FastAPI + gossip)
│   ├── coordinator-api/     # Job coordination API (FastAPI)
│   ├── explorer-web/        # Blockchain explorer (TypeScript + Vite)
│   ├── marketplace-web/     # GPU marketplace frontend (TypeScript + Vite)
│   ├── pool-hub/            # Mining pool management (FastAPI + Redis)
│   ├── trade-exchange/      # BTC/AITBC exchange (FastAPI + WebSocket)
│   ├── wallet-daemon/       # Wallet service (FastAPI)
│   └── zk-circuits/         # ZK proof circuits (Circom)
├── cli/                     # CLI tools (12 command groups, 90+ subcommands)
├── contracts/               # Solidity smart contracts
├── docs/                    # Documentation (structure, guides, reference, reports)
├── extensions/              # Browser extensions (Firefox wallet)
├── home/                    # Local simulation scripts
├── infra/                   # Infrastructure (nginx, k8s, helm, terraform)
├── packages/                # Shared libraries
│   ├── py/aitbc-crypto/     # Cryptographic primitives
│   ├── py/aitbc-sdk/        # Python SDK
│   └── solidity/aitbc-token/# ERC-20 token contract
├── plugins/ollama/          # Ollama LLM integration
├── scripts/                 # Deployment, GPU, service, and test scripts
├── systemd/                 # Systemd service units
├── tests/                   # Test suites (unit, integration, e2e, security, CLI)
└── website/                 # Public website and HTML documentation
```

See [docs/structure.md](docs/structure.md) for detailed file-level documentation.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for web apps and ZK circuits)
- PostgreSQL (optional, SQLite for development)
- Ollama (for GPU inference)

### Run Services Locally

```bash
# Start all services
./scripts/dev_services.sh

# Or start individually
cd apps/coordinator-api && uvicorn app.main:app --port 8000
cd apps/blockchain-node && python -m aitbc_chain.main
cd apps/wallet-daemon && uvicorn app.main:app --port 8002
```

### Run Tests

```bash
# CLI tests (141 unit + 24 integration)
pytest tests/cli/

# Coordinator API tests (billing + GPU marketplace)
pytest apps/coordinator-api/tests/

# Blockchain node tests
pytest tests/test_blockchain_nodes.py

# All tests together (208 passing)
pytest apps/coordinator-api/tests/ tests/cli/
```

### CLI Usage

```bash
pip install -e .

# Submit a job
aitbc client submit --type inference --prompt "Hello world"

# Register as a miner
aitbc miner register --gpu RTX4090

# GPU marketplace
aitbc marketplace gpu list
aitbc marketplace gpu book <gpu_id> --hours 1

# Wallet and governance
aitbc wallet balance
aitbc governance propose --type parameter_change --title "Update fee"
```

## Deployment

Services run in an Incus container with systemd units. See `systemd/` for service definitions and `scripts/deploy/` for deployment automation.

```bash
# Deploy to container
./scripts/deploy/deploy-to-container.sh

# Deploy blockchain nodes
./scripts/deploy/deploy-blockchain.sh
```

## Test Results

| Suite | Tests | Source |
|-------|-------|--------|
| Blockchain node | 50 | `tests/test_blockchain_nodes.py` |
| ZK integration | 8 | `tests/test_zk_integration.py` |
| CLI unit tests | 141 | `tests/cli/test_*.py` (9 files) |
| CLI integration | 24 | `tests/cli/test_cli_integration.py` |
| Billing | 21 | `apps/coordinator-api/tests/test_billing.py` |
| GPU marketplace | 22 | `apps/coordinator-api/tests/test_gpu_marketplace.py` |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/structure.md](docs/structure.md) | Codebase structure and file layout |
| [docs/components.md](docs/components.md) | Component overview |
| [docs/coordinator-api.md](docs/coordinator-api.md) | Coordinator API reference |
| [docs/cli-reference.md](docs/cli-reference.md) | CLI command reference (560+ lines) |
| [docs/roadmap.md](docs/roadmap.md) | Development roadmap |
| [docs/done.md](docs/done.md) | Completed deployments and milestones |
| [docs/files.md](docs/files.md) | File audit and status tracking |
| [docs/currentTask.md](docs/currentTask.md) | Current task and test results |

## License

[MIT](LICENSE) — Copyright (c) 2025 AITBC
