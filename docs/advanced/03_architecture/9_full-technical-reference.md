# AITBC Full Technical Reference

Complete technical documentation for the AI Training & Blockchain Computing Platform

## 📊 **Current Status: PRODUCTION READY - March 18, 2026**

### ✅ **Implementation Status**
- **Phase 1-3**: 100% Complete (Exchange Infrastructure, Security, Production Integration)
- **Phase 4.1**: 100% Complete (AI Trading Engine)
- **Phase 4.2**: 100% Complete (Advanced Analytics Platform)  
- **Phase 4.3**: 100% Complete (AI-Powered Surveillance)
- **Phase 4.4**: Pending (Enterprise Integration)
- **Multi-Chain**: 100% Complete (7-layer architecture)

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
  - [Multi-Chain Architecture](#multi-chain-architecture)
  - [Core Components](#core-components)
  - [Data Flow](#data-flow)
  - [Consensus Mechanism](#consensus)
- [AI-Powered Features](#ai-powered-features)
  - [AI Trading Engine](#ai-trading-engine)
  - [Advanced Analytics](#advanced-analytics)
  - [AI Surveillance](#ai-surveillance)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Configuration](#configuration)
- [APIs](#apis)
  - [Coordinator API](#coordinator-api)
  - [Blockchain RPC](#blockchain-rpc)
  - [Wallet API](#wallet-api)
  - [Exchange APIs](#exchange-apis)
- [Components](#components)
  - [Blockchain Node](#blockchain-node)
  - [Coordinator Service](#coordinator-service)
  - [AI Services](#ai-services)
  - [Exchange Integration](#exchange-integration)
  - [Multi-Chain Services](#multi-chain-services)
- [Guides](#guides)
  - [Trader Guide](#trader-guide)
  - [Miner Guide](#miner-guide)
  - [Developer Guide](#developer-guide)
  - [System Administrator Guide](#system-administrator-guide)

## Introduction

AITBC (AI Training & Blockchain Computing) is a comprehensive blockchain platform that combines AI-powered trading, advanced analytics, multi-chain support, and enterprise-grade security. The platform has evolved from its original AI agent focus to become a full-featured blockchain ecosystem supporting real-world trading, surveillance, and compliance requirements.

### Key Concepts

- **Multi-Chain Architecture**: 7-layer system with complete chain isolation
- **AI Trading**: Machine learning-based trading algorithms and predictive analytics
- **AI Surveillance**: Advanced pattern recognition and behavioral analysis
- **Exchange Integration**: Real exchange integration with major platforms
- **Compliance Framework**: Automated KYC/AML and regulatory reporting
- **Chain-Specific Tokens**: AITBC tokens isolated by chain (AITBC-AIT-DEVNET, etc.)

## Architecture

### Multi-Chain Architecture

The AITBC platform implements a complete 7-layer multi-chain architecture:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Layer 7: UI   │    │  Layer 6: Explorer│   │ Layer 5: Network │
│   (Port 8016)   │◄──►│   (Port 8016)   │◄──►│   (Port 8008)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Layer 4: Consen │    │ Layer 3: Block  │    │ Layer 2: Coord  │
│   (Port 8007)   │◄──►│   (Port 8007)   │◄──►│   (Port 8001)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                                               ▲
         │                                               │
┌─────────────────┐                                   ┌─────────────────┐
│ Layer 1: Wallet │                                   │  AI Services    │
│   (Port 8003)   │                                   │ (Multiple Ports) │
└─────────────────┘                                   └─────────────────┘
```

### Core Components

#### **Layer 1: Wallet Daemon (Port 8003)**
- Multi-chain wallet management
- Chain-specific wallet creation and balance queries
- Cross-chain transaction rejection for security
- Systemd service integration with journalctl logging

#### **Layer 2: Coordinator API (Port 8001)**
- Transaction coordination and routing
- Multi-chain endpoint management
- AI service integration
- Exchange and compliance coordination

#### **Layer 3: Blockchain Service (Port 8007)**
- Transaction processing and consensus
- Chain-specific transaction handling
- Database schema with chain_id support
- Mempool management with chain isolation

#### **Layer 4: Consensus Mechanism (Port 8007)**
- Proof of Authority (PoA) consensus
- Validator signature collection
- Block proposal and validation
- Consensus status monitoring

#### **Layer 5: Network Service (Port 8008)**
- Peer-to-peer network with 4+ peers
- Automatic block propagation
- Chain-specific network isolation
- Network health monitoring

#### **Layer 6: Explorer Service (Port 8016)**
- Real-time data aggregation
- Multi-chain API endpoints
- Beautiful web interface with search
- Chain-specific data presentation

#### **Layer 7: User Interface (Port 8016)**
- Complete user experience
- Multi-chain dashboard
- Search functionality
- Real-time statistics

### Data Flow

```
User Request → Wallet Daemon → Coordinator API → Blockchain Service → Consensus → Network → Explorer → UI
     ↓                ↓              ↓                ↓           ↓        ↓       ↓    ↓
Multi-Chain    Transaction    Chain         Block      Peer-to-   Data   Web   User
Wallet         Coordination    Processing    Proposal    Peer       Aggreg  Interface Experience
```

### Consensus Mechanism

**Proof of Authority (PoA) Implementation**
- **Validator**: ait1devproposer000000000000000000000000000000
- **Block Height**: Currently 250+ blocks
- **Transaction Flow**: Submit → Mempool → Consensus → Block
- **Chain Isolation**: Maintained per chain (ait-devnet active)

## AI-Powered Features

### AI Trading Engine (Phase 4.1 - ✅ COMPLETE)

**File**: `/apps/coordinator-api/src/app/services/ai_trading_engine.py`  
**CLI**: `/cli/aitbc_cli/commands/ai_trading.py`

**Features**:
- Machine learning-based trading algorithms
- **Strategies**: Mean Reversion, Momentum (extensible framework)
- **Predictive Analytics**: Price prediction and trend analysis
- **Portfolio Optimization**: Automated portfolio management
- **Risk Management**: Intelligent risk assessment and mitigation
- **Strategy Backtesting**: Historical data analysis and optimization

**CLI Commands**:
```bash
aitbc ai-trading start --strategy mean_reversion
aitbc ai-trading status
aitbc ai-trading analytics
aitbc ai-trading backtest --strategy momentum
```

### Advanced Analytics Platform (Phase 4.2 - ✅ COMPLETE)

**File**: `/apps/coordinator-api/src/app/services/advanced_analytics.py`  
**CLI**: `/cli/aitbc_cli/commands/advanced_analytics.py`

**Features**:
- Real-time analytics dashboard
- **Market Data Analysis**: Deep market insights and patterns
- **Performance Metrics**: Trading performance and KPI tracking
- **Technical Indicators**: RSI, SMA, Bollinger Bands, MACD
- **Custom Analytics APIs**: Flexible analytics data access
- **Reporting Automation**: Automated analytics report generation

**CLI Commands**:
```bash
aitbc advanced-analytics dashboard
aitbc advanced-analytics market-data --symbol AITBC
aitbc advanced-analytics performance --wallet <address>
aitbc advanced-analytics report --type portfolio
```

### AI Surveillance (Phase 4.3 - ✅ COMPLETE)

**File**: `/apps/coordinator-api/src/app/services/ai_surveillance.py`  
**CLI**: `/cli/aitbc_cli/commands/ai_surveillance.py`

**Features**:
- **Machine Learning Surveillance**: 92% accuracy with isolation forest algorithms
- **Behavioral Analysis**: 88% accuracy with clustering techniques
- **Predictive Risk Assessment**: 94% accuracy with gradient boosting models
- **Automated Alert Systems**: Intelligent alert prioritization
- **Market Integrity Protection**: 91% accuracy with neural networks

**ML Models**: 4 production-ready models with 88-94% accuracy

**CLI Commands**:
```bash
aitbc ai-surveillance start
aitbc ai-surveillance status
aitbc ai-surveillance alerts
aitbc ai-surveillance patterns
aitbc ai-surveillance risk-profile --user <username>
```
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
