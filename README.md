# AITBC — AI Trusted Blockchain Computing

![AITBC Logo](website/AITBC.svg)

[![CI](https://img.shields.io/badge/Gitea%20Actions-CI-blue)](https://gitea.invalid/oib/aitbc/actions)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Poetry](https://img.shields.io/badge/packaging-poetry-1a1a1a?logo=python)](https://python-poetry.org/)
[![Version](https://img.shields.io/badge/version-v0.25.9-blue?style=flat-square)]()

> **Decentralized market for AI compute, powered by PoA consensus, agents, and verifiable task execution.**

Welcome to AITBC — a Python 3.13 monorepo of FastAPI microservices, a CLI, shared libraries, and Solidity contracts for running a multi-island blockchain network where GPU providers sell compute and clients submit AI jobs that are paid, executed, and settled on-chain.

## The network at a glance

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

- **Hub** produces blocks and runs the coordinator, exchange, and public discovery endpoints.
- **Shop** nodes list GPU compute offers and execute jobs.
- **Client** nodes submit AI jobs, query results, and trade — as lightweight followers.

A single node can combine roles. Two independent switches — `BLOCKCHAIN_MODE` and `MARKET_ROLE` — select which services a node runs; see [Service Selection](docs/getting-started/setup-service-selection.md) for the matrix.

For a component-by-component status check, see [docs/releases/STATUS.md](docs/releases/STATUS.md).

## Get involved

- **Join the public island** — `ait-hub.aitbc.bubuit.net` is running and open for new nodes. Bootstrap files and a self-serve peer key: [open-island joining guide](docs/agent/guides/open-island-joining-guide.md).
- **Set up a node** — one command on a fresh host (`scripts/deployment/setup.sh`); walkthrough in the [quick start](docs/getting-started/setup-quick-start.md) and [SETUP.md](docs/getting-started/SETUP.md).
- **Set up a dev checkout** — clone, `poetry install`, `make ci`; conventions in [CONTRIBUTING.md](docs/CONTRIBUTING.md).
- **See a paid job end to end** — the [customer↔hub scenario](docs/scenarios/34_hub_customer_node_e2e.md) walks an AI job from offer to on-chain settlement.
- **Explore the CLI** — `aitbc` covers wallet, market, jobs, bridge, and governance: [cli/README.md](cli/README.md).

## Key features

- **Blockchain** — PoA consensus, adaptive sync, multi-island federation, state-root validation, gossip with Redis backend.
- **Agents** — registry, identity, cross-chain reputation, communication, job dispatch.
- **Compute market** — GPU/edge listing, offer matching, dynamic pricing, escrow-backed payments.
- **Security** — JWT/RBAC, multi-sig wallets, encrypted keystores, Merkle-proof bridge verification, rate limiting.
- **CLI & ops** — unified `aitbc_cli`, systemd units, Prometheus metrics, deployment scripts.

## Documentation

| I want to... | Start here |
|--------------|------------|
| Understand the platform and pick a node profile | [docs/getting-started/README.md](docs/getting-started/README.md) |
| Install and configure a node | [docs/getting-started/SETUP.md](docs/getting-started/SETUP.md) |
| Learn the CLI | [cli/README.md](cli/README.md) |
| Find every doc, scenario, and reference | [docs/MASTER_INDEX.md](docs/MASTER_INDEX.md) |
| Check what is complete vs. in flight | [docs/releases/STATUS.md](docs/releases/STATUS.md) |
| Read the architecture and security deep dives | [docs/blockchain/](docs/blockchain/) and [docs/security/](docs/security/) |

## Media

- [Gemini NotebookLM companion notebook](https://notebooklm.google.com/notebook/e3ca6fea-5f40-4932-9df5-71843e61ff95)

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, conventions, and the PR process.

## License

[MIT License](LICENSE) — Copyright (c) 2025–2026 AITBC.
