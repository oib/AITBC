# AITBC — AI Trusted Blockchain Computing

![AITBC Logo](website/AITBC.svg)

[![CI](https://img.shields.io/badge/Gitea%20Actions-CI-blue)](https://gitea.bubuit.net/oib/aitbc/actions)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Poetry](https://img.shields.io/badge/packaging-poetry-1a1a1a?logo=python)](https://python-poetry.org/)
[![Version](https://img.shields.io/badge/version-v0.10.18-blue?style=flat-square)]()

> **Decentralized marketplace for AI compute, powered by PoA consensus, agents, and verifiable task execution.**

Welcome to AITBC. This repo is a Python 3.13 monorepo of FastAPI microservices, a CLI, and shared libraries for running a multi-island blockchain network where GPU providers sell compute and clients submit AI jobs that are paid, executed, and settled on-chain.

You can participate in three ways:

```
     ┌─────────────┐          ┌─────────────┐
     │   Client    │          │    Shop     │
     │ (uses jobs) │          │(sells GPUs) │
     └──────┬──────┘          └──────┬──────┘
            │                        │
            └──────────┬─────────────┘
                       ▼
                ┌─────────────┐
                │     Hub     │
                │ (coordinator│
                │ + chain)    │
                └─────────────┘
```

| Role | What it is | What it does | Typical profile |
|------|------------|--------------|-----------------|
| **Hub** | `BLOCKCHAIN_MODE=hub` | Produces/broadcasts blocks, runs the coordinator, exchange, and public discovery endpoints. | `hub` (full services + dev deps) |
| **Shop** | `MARKET_ROLE=shop` | Provides GPU, edge, marketplace, and mining services; lists compute offers and executes jobs. | `provider-gpu` (GPU) or `server-no-gpu` (no GPU) |
| **Client** | `MARKET_ROLE=customer` | Consumes compute: submits jobs, queries results, trades, and syncs as a follower. | `customer-no-gpu` (lightweight follower) |

A single node can combine roles — a hub can also be a shop, and a follower can be a client or a shop. Services are selected by the two independent axes `BLOCKCHAIN_MODE` and `MARKET_ROLE`. See [Service Selection](docs/getting-started/setup-service-selection.md) for the full matrix.

For a component-by-component status check, see [docs/releases/STATUS.md](docs/releases/STATUS.md).

## Join the public network

A public AITBC island is already running at **http://hub.aitbc.bubuit.net/**:

- **Island ID**: `ait-public`
- **Chain ID**: `ait-public`

```bash
# Fetch dynamic join instructions
curl http://hub.aitbc.bubuit.net/agent/join/ait-public.json

# Network topology, peers, and endpoints
curl http://hub.aitbc.bubuit.net/agent/discovery.json
```

Then start your node:

```bash
sudo systemctl start aitbc-blockchain-node
```

## Quick start (local)

The repository supports both Poetry (`.venv`) and a plain `venv` in the repo root.
The canonical path for a fresh machine is Poetry:

```bash
# 1. Clone
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc

# 2. Install dependencies (Poetry)
pip install poetry
poetry install

# 3. Run verification
poetry run make ci

# 4. Start the coordinator API
cd apps/coordinator-api
PYTHONPATH=src poetry run uvicorn coordinator_api.main:app --reload
```

If you prefer a plain virtual environment, use the same lock-exported requirements
that CI and deployment consume:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . -e cli
make ci
```

For detailed setup, see [docs/getting-started/SETUP.md](docs/getting-started/SETUP.md).

## Run an end-to-end AI job

On a **shop** node, list a GPU offer:

```bash
aitbc market offer --gpu-id gpu-0 --memory 24 --price 100
```

On a **client** node, submit a job to the hub's coordinator:

```bash
aitbc ai submit --wallet my-wallet --type text-generation \
  --prompt "Explain zero-knowledge proofs in one paragraph." \
  --payment 10
```

Check the result:

```bash
aitbc ai status --job-id <job-id>
aitbc ai results --job-id <job-id>
```

See the [CLI README](cli/README.md) for the full command reference and the [customer↔hub end-to-end scenario](docs/scenarios/34_hub_customer_node_e2e.md) for a cross-network walkthrough.

## Documentation

| I want to... | Start here |
|--------------|------------|
| Understand the platform and pick a node profile | [docs/getting-started/README.md](docs/getting-started/README.md) |
| Install and configure a node | [docs/getting-started/SETUP.md](docs/getting-started/SETUP.md) |
| Learn the CLI | [cli/README.md](cli/README.md) |
| Find every doc, scenario, and reference | [docs/MASTER_INDEX.md](docs/MASTER_INDEX.md) |
| Check what is complete vs. in flight | [docs/releases/STATUS.md](docs/releases/STATUS.md) |
| Read the architecture and security deep dives | [docs/blockchain/](docs/blockchain/) and [docs/security/](docs/security/) |

## Key features

- **Blockchain** — PoA consensus, adaptive sync, multi-island federation, state-root validation, gossip with Redis backend.
- **Agents** — registry, identity, cross-chain reputation, communication, job dispatch.
- **Compute marketplace** — GPU/edge listing, offer matching, dynamic pricing, escrow-backed payments.
- **Security** — JWT/RBAC, multi-sig wallets, encrypted keystores, Merkle-proof bridge verification, rate limiting.
- **CLI & ops** — unified `aitbc_cli`, systemd units, Prometheus metrics, deployment scripts.

## Media

- [Gemini NotebookLM companion notebook](https://notebooklm.google.com/notebook/e3ca6fea-5f40-4932-9df5-71843e61ff95)

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, conventions, and the PR process.

## License

[MIT License](LICENSE) — Copyright (c) 2025 AITBC.
