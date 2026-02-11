# AITBC — AI Token Blockchain

Decentralized GPU compute marketplace with blockchain-based job coordination, Ollama inference, ZK receipt verification, and token payments.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

AITBC is a full-stack blockchain platform that connects GPU compute providers (miners) with AI workload consumers (clients) through a decentralized marketplace. The system handles job submission, miner matching, GPU inference execution, cryptographic receipt generation, and on-chain payment settlement.

**Key capabilities:**
- **Blockchain nodes** — PoA consensus, gossip relay, WebSocket RPC
- **Coordinator API** — Job lifecycle, miner registry, marketplace, multi-tenancy
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
├── cli/                     # CLI tools (client, miner, wallet)
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
├── tests/                   # Test suites (unit, integration, e2e, security, load)
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
# Full test suite
pytest tests/

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# CI script (all apps)
./scripts/ci/run_python_tests.sh
```

### CLI Usage

```bash
# Submit a job as a client
python cli/client.py submit --model llama3 --prompt "Hello world"

# Start mining
python cli/miner.py start --gpu 0

# Check wallet balance
python cli/wallet.py balance
```

## Deployment

Services run in an Incus container with systemd units. See `systemd/` for service definitions and `scripts/deploy/` for deployment automation.

```bash
# Deploy to container
./scripts/deploy/deploy-to-container.sh

# Deploy blockchain nodes
./scripts/deploy/deploy-blockchain.sh
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/structure.md](docs/structure.md) | Codebase structure and file layout |
| [docs/files.md](docs/files.md) | File audit and status tracking |
| [docs/roadmap.md](docs/roadmap.md) | Development roadmap |
| [docs/components.md](docs/components.md) | Component overview |
| [docs/infrastructure.md](docs/infrastructure.md) | Infrastructure guide |
| [docs/full-documentation.md](docs/full-documentation.md) | Complete technical documentation |

## License

[MIT](LICENSE) — Copyright (c) 2025 AITBC
