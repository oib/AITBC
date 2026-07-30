# AITBC — AI Trusted Blockchain Computing

![AITBC Logo](website/AITBC.svg)

[![CI](https://github.com/oib/aitbc/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/oib/aitbc/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Poetry](https://img.shields.io/badge/packaging-poetry-1a1a1a?logo=python)](https://python-poetry.org/)
[![Version](https://img.shields.io/badge/version-v0.20.4-blue?style=flat-square)]()

> **Decentralized marketplace for AI compute, powered by PoA consensus, agents, and verifiable task execution.**

AITBC lets GPU providers offer compute, AI agents discover and rent it, and clients submit inference or training jobs that are paid, executed, and settled on a multi-island blockchain network. A public hub is already running.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Client    │────▶│ Coordinator  │◀────│    Miner     │
│ (job submit) │     │   (dispatch) │     │(GPU provider)│
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │Marketplace│     │Blockchain│     │  Wallet  │
    │  (offers) │     │(settle)  │     │ (escrow) │
    └──────────┘     └──────────┘     └──────────┘
```

## What works today

| Component | Status | Notes |
|-----------|--------|-------|
| Blockchain node (PoA, sync, gossip, multi-island) | ✅ | MultiValidatorPoA/PBFT gated for soak testing |
| Agent coordinator & job dispatch | ✅ | JWT + API-key auth, rate limiting |
| GPU marketplace & offer matching | ✅ | Listing, booking, dynamic pricing, edge advertise |
| Wallet & escrow | ✅ | Server-side encrypted wallets; HTLC settlement wired |
| Bridge & cross-chain settlement | ✅ | Multi-sig, Merkle proofs, block-header finality |
| CLI (`aitbc_cli`) | ✅ | 50+ command groups |
| Public hub | ✅ | `http://hub.aitbc.bubuit.net` |
| Test suite | 🚧 | Target 85% coverage; core green, B2–B4 tests in flight |

For the full release roadmap, see [docs/releases/STATUS.md](docs/releases/STATUS.md).

## Join the public network

A public AITBC island is running at **http://hub.aitbc.bubuit.net/**:

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

```bash
# 1. Clone
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc

# 2. Install dependencies (Poetry)
pip install poetry
poetry install

# 3. Run verification
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q

# 4. Start the coordinator API
cd apps/coordinator-api
PYTHONPATH=src poetry run uvicorn coordinator_api.main:app --reload
```

For detailed setup, see [docs/getting-started/SETUP.md](docs/getting-started/SETUP.md).

## Run an end-to-end GPU inference job

See [`examples/gpu_inference_miner.py`](examples/gpu_inference_miner.py) and [`examples/gpu_inference_client.py`](examples/gpu_inference_client.py) for a self-contained miner/client pair that uses Ollama (or a mock fallback) to execute inference jobs.

```bash
# Terminal 1 — start a GPU-capable miner
python examples/gpu_inference_miner.py --api-key "$MINER_API_KEY" --miner-id my-miner

# Terminal 2 — submit a job and poll for the result
python examples/gpu_inference_client.py \
  --jwt-secret "$JWT_SECRET" \
  --coordinator http://localhost:8203 \
  --prompt "Explain zero-knowledge proofs in one paragraph."
```

## Documentation

- [Master Index](docs/MASTER_INDEX.md) — every doc, scenario, and reference file
- [Documentation Home](docs/README.md) — learning paths and navigation
- [Release Status](docs/releases/STATUS.md) — what is complete vs. in flight
- [Setup Guide](docs/getting-started/SETUP.md) — installation and configuration
- [API Examples](docs/api/examples/) — curl, Python SDK, and JavaScript snippets
- [Agent SDK Examples](docs/agent-sdk/examples/) — agent identity and compute agents

## Key features

- **Blockchain** — PoA consensus, adaptive sync, multi-island federation, state-root validation, gossip with Redis backend.
- **Agents** — registry, identity, cross-chain reputation, communication, job dispatch.
- **Compute marketplace** — GPU/edge listing, offer matching, dynamic pricing, escrow-backed payments.
- **Security** — JWT/RBAC, multi-sig wallets, encrypted keystores, Merkle-proof bridge verification, rate limiting.
- **CLI & ops** — unified `aitbc_cli`, systemd units, Prometheus metrics, deployment scripts.

## Media

- [Video walkthroughs on PeerTube](https://peertube.bubuit.net/c/aitbc/videos)
- [Gemini NotebookLM companion notebook](https://notebooklm.google.com/notebook/e3ca6fea-5f40-4932-9df5-71843e61ff95)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and the PR process.

## License

[MIT License](LICENSE) — Copyright (c) 2025 AITBC.
