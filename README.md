# AITBC — AI Token Blockchain

Decentralized GPU compute marketplace with blockchain-based job coordination, Ollama inference, ZK receipt verification, and token payments.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## The Idea

AITBC creates a decentralized marketplace where GPU providers can earn tokens by running AI inference workloads, while clients pay for compute access through a transparent blockchain system. The platform eliminates centralized cloud providers by using cryptographic proofs and smart contracts to ensure fair payment and verifiable computation.

## Technical Overview

**Core Components:**
- **Blockchain Layer** — Proof-of-Authority consensus with transaction receipts
- **Coordinator API** — Job marketplace, miner registry, and payment processing  
- **GPU Mining** — Ollama-based inference with zero-knowledge receipt generation
- **Wallet System** — Token management and receipt verification
- **Exchange Platform** — Bitcoin/AITBC trading with order matching

**Key Innovations:**
- Zero-knowledge proofs for verifiable computation receipts
- GPU marketplace with capability-based matching
- Cryptographic payment settlement without trusted intermediaries
- Open-source alternative to centralized AI cloud services

## Architecture Flow

```
Clients submit jobs → Coordinator matches miners → GPU inference executes → 
ZK receipts generated → Blockchain records payments → Tokens transferred
```

## Technology Stack

- **Backend**: FastAPI, PostgreSQL, Redis, systemd services
- **Blockchain**: Python-based nodes with PoA consensus
- **AI Inference**: Ollama with GPU passthrough
- **Cryptography**: Circom ZK circuits, Solidity smart contracts
- **Frontend**: TypeScript, Vite, React components
- **Infrastructure**: Incus containers, nginx reverse proxy

## Documentation

| Section | Path | Focus |
|---------|------|-------|
| Getting Started | [docs/0_getting_started/](docs/0_getting_started/) | Installation & basic usage |
| Clients | [docs/2_clients/](docs/2_clients/) | Job submission & payments |
| Miners | [docs/3_miners/](docs/3_miners/) | GPU setup & earnings |
| Architecture | [docs/6_architecture/](docs/6_architecture/) | System design & flow |
| Development | [docs/8_development/](docs/8_development/) | Contributing & setup |

## License

[MIT](LICENSE) — Copyright (c) 2026 AITBC
