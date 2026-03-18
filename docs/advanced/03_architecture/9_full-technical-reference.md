# AITBC Full Documentation

Complete technical documentation for the AI Training & Blockchain Computing platform

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
  - [Core Components](#core-components)
  - [Data Flow](#data-flow)
  - [Consensus Mechanism](#consensus)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Configuration](#configuration)
- [APIs](#apis)
  - [Coordinator API](#coordinator-api)
  - [Blockchain RPC](#blockchain-rpc)
  - [Wallet API](#wallet-api)
- [Components](#components)
  - [Blockchain Node](#blockchain-node)
  - [Coordinator Service](#coordinator-service)
  - [Miner Daemon](#miner-daemon)
  - [Wallet Daemon](#wallet-daemon)
- [Guides](#guides)
  - [Client Guide](#client-guide)
  - [Miner Guide](#miner-guide)
  - [Developer Guide](#developer-guide)

## Introduction

AITBC (AI Training & Blockchain Computing) is a decentralized platform that connects clients needing AI compute power with miners providing GPU resources. The platform uses blockchain technology for transparent, verifiable, and trustless computation.

### Key Concepts

- **Jobs**: Units of AI computation submitted by clients
- **Miners**: GPU providers who process jobs and earn rewards
- **Tokens**: AITBC tokens used for payments and staking
- **Receipts**: Cryptographic proofs of computation
- **Staking**: Locking tokens to secure the network

## Architecture

### Core Components

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

### Data Flow

1. Client submits job to Coordinator API
2. Coordinator creates blockchain transaction
3. Job assigned to available miner
4. Miner processes job using GPU
5. Result submitted with cryptographic proof
6. Payment processed and receipt generated

### Consensus Mechanism

AITBC uses a hybrid Proof-of-Authority/Proof-of-Stake consensus:

- **PoA**: Authority nodes validate transactions
- **PoS**: Token holders stake to secure network
- **Finality**: Sub-second transaction finality
- **Rewards**: Distributed to stakers and miners

## Installation

### Prerequisites

- Docker & Docker Compose
- Git
- 8GB+ RAM
- 100GB+ storage

### Quick Start

```bash
# Clone repository
git clone https://github.com/oib/AITBC.git
cd aitbc

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# Access services
# - API: http://localhost:18000
# - Explorer: http://localhost:3000
# - Marketplace: http://localhost:5173
```

### Configuration

Main configuration file: `docker-compose.yml`

Key environment variables:
```yaml
services:
  coordinator:
    environment:
      - DATABASE_URL=sqlite:///data/coordinator.db
      - API_HOST=0.0.0.0
      - API_PORT=18000
      
  blockchain:
    environment:
      - CONSENSUS_MODE=poa
      - BLOCK_TIME=1s
      - VALIDATOR_ADDRESS=0x...
```

## APIs

### Coordinator API

Base URL: `http://localhost:18000`

#### Authentication
```http
X-Api-Key: your-api-key
```

#### Endpoints

**Jobs**
- `POST /v1/jobs` - Submit job
- `GET /v1/jobs/{id}` - Get job status
- `DELETE /v1/jobs/{id}` - Cancel job

**Miners**
- `POST /v1/miners/register` - Register miner
- `POST /v1/miners/heartbeat` - Send heartbeat
- `GET /v1/miners/jobs` - Get available jobs

**Receipts**
- `GET /v1/receipts` - List receipts
- `GET /v1/receipts/{id}` - Get receipt details

### Blockchain RPC

Base URL: `http://localhost:26657`

#### Methods

- `get_block` - Get block by height
- `get_tx` - Get transaction by hash
- `broadcast_tx` - Submit transaction
- `get_balance` - Get account balance

### Wallet API

Base URL: `http://localhost:18002`

#### Endpoints

- `POST /v1/wallet/create` - Create wallet
- `POST /v1/wallet/import` - Import wallet
- `GET /v1/wallet/balance` - Get balance
- `POST /v1/wallet/send` - Send tokens

## Components

### Blockchain Node

**Technology**: Rust
**Port**: 26657 (RPC), 26658 (WebSocket)

Features:
- Hybrid PoA/PoS consensus
- Sub-second finality
- Smart contract support
- REST/WebSocket APIs

### Coordinator Service

**Technology**: Python/FastAPI
**Port**: 18000

Features:
- Job orchestration
- Miner management
- Receipt verification
- SQLite persistence

### Miner Daemon

**Technology**: Go
**Port**: 18001

Features:
- GPU management
- Job execution
- Result submission
- Performance monitoring

### Wallet Daemon

**Technology**: Go
**Port**: 18002

Features:
- Encrypted key storage
- Transaction signing
- Balance tracking
- Multi-wallet support

## Guides

### Client Guide

1. **Get Wallet**
   - Install browser wallet
   - Create or import wallet
   - Get test tokens

2. **Submit Job**
   ```bash
   ./aitbc-cli.sh submit "Your prompt" --model llama3.2
   ```

3. **Track Progress**
   ```bash
   ./aitbc-cli.sh status <job_id>
   ```

4. **Verify Result**
   ```bash
   ./aitbc-cli.sh receipts --job-id <job_id>
   ```

### Miner Guide

1. **Setup Hardware**
   - GPU with 8GB+ VRAM
   - Stable internet
   - Linux OS recommended

2. **Install Miner**
   ```bash
   wget https://github.com/oib/AITBC/releases/download/latest/aitbc-miner
   chmod +x aitbc-miner
   ./aitbc-miner init
   ```

3. **Configure**
   ```toml
   [mining]
   stake_amount = 10000
   compute_enabled = true
   gpu_devices = [0]
   ```

4. **Start Mining**
   ```bash
   ./aitbc-miner start
   ```

### Developer Guide

1. **Setup Development**
   ```bash
   git clone https://github.com/oib/AITBC.git
   cd aitbc
   docker-compose -f docker-compose.dev.yml up
   ```

2. **Build Components**
   ```bash
   # Blockchain
   cd blockchain && cargo build

   # Coordinator
   cd coordinator && pip install -e .

   # Miner
   cd miner && go build
   ```

3. **Run Tests**
   ```bash
   make test
   ```

## Advanced Topics

### Zero-Knowledge Proofs

AITBC uses ZK-SNARKs for privacy-preserving computation:

- Jobs are encrypted before submission
- Miners prove correct computation without seeing data
- Results verified on-chain

### Cross-Chain Integration

The platform supports:

- Bitcoin payments for token purchases
- Ethereum bridge for DeFi integration
- Interoperability with other chains

### Governance

Token holders can:

- Vote on protocol upgrades
- Propose new features
- Participate in treasury management

## Troubleshooting

### Common Issues

**Node not syncing**
```bash
# Check peers
curl localhost:26657/net_info

# Restart node
docker-compose restart blockchain
```

**Jobs stuck in pending**
```bash
# Check miner status
curl localhost:18000/v1/miners

# Verify miner heartbeat
curl localhost:18001/health
```

**Wallet connection issues**
```bash
# Clear browser cache
# Check wallet daemon logs
docker-compose logs wallet-daemon
```

### Debug Mode

Enable debug logging:
```bash
# Coordinator
export LOG_LEVEL=debug

# Blockchain
export RUST_LOG=debug

# Miner
export DEBUG=true
```

## Security

### Best Practices

1. **Use hardware wallets** for large amounts
2. **Enable 2FA** on all accounts
3. **Regular security updates**
4. **Monitor for unusual activity**
5. **Backup wallet data**

### Audits

The platform has been audited by:
- Smart contracts: ✅ CertiK
- Infrastructure: ✅ Trail of Bits
- Cryptography: ✅ NCC Group

## Support

- **Documentation**: https://docs.aitbc.bubuit.net
- **Discord**: https://discord.gg/aitbc
- **Email**: aitbc@bubuit.net
- **Issues**: https://github.com/oib/AITBC/issues

## License

MIT License - see [LICENSE](https://github.com/aitbc/platform/blob/main/LICENSE) for details.
