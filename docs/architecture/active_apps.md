# Active AITBC Applications

This document lists all active AITBC applications as of v0.5.0.

## Core Services

### Agent Coordinator
**Path**: `apps/agent-coordinator`
**Status**: active
**Purpose**: Agent lifecycle management
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-agent-coordinator.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Coordinator API
**Path**: `apps/coordinator-api`
**Status**: active
**Purpose**: Main REST API for AITBC platform
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-coordinator-api.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Blockchain Node
**Path**: `apps/blockchain-node`
**Status**: active
**Purpose**: Blockchain node with RPC, P2P, and sync services
**Maintainer**: @aitbc-blockchain
**Service Files**: `aitbc-blockchain-node.service`, `aitbc-blockchain-p2p.service`, `aitbc-blockchain-rpc.service`, `aitbc-blockchain-sync.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

## AI/ML Services

### GPU Service
**Path**: `apps/gpu`
**Status**: active
**Purpose**: GPU resource management and marketplace
**Maintainer**: @aitbc-gpu
**Service File**: `aitbc-gpu.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### AI Engine
**Path**: `apps/ai-engine`
**Status**: under development
**Purpose**: AI model training and inference
**Maintainer**: @aitbc-public
**Service Files**: `aitbc-ai.service`, `aitbc-learning.service`, `aitbc-modality-optimization.service`, `aitbc-multimodal.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Whisper
**Path**: `apps/whisper`
**Status**: active
**Purpose**: Speech-to-text transcription service
**Maintainer**: @aitbc-public
**Recent Activity**: Active development (last commit: 2025-06-18)

### FFmpeg
**Path**: `apps/ffmpeg`
**Status**: active
**Purpose**: Video transcoding service
**Maintainer**: @aitbc-public
**Recent Activity**: Active development (last commit: 2025-06-18)

## Marketplace & Trading

### Marketplace
**Path**: `apps/marketplace`
**Status**: active
**Purpose**: GPU and compute resource marketplace
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-marketplace.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Exchange
**Path**: `apps/exchange`
**Status**: active
**Purpose**: Cross-chain exchange and trading
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-exchange.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Trading
**Path**: `apps/trading`
**Status**: active
**Purpose**: Trading and order management
**Maintainer**: @aitbc-internal
**Recent Activity**: Active development (last commit: 2025-06-18)

### Pool Hub
**Path**: `apps/pool-hub`
**Status**: active
**Purpose**: Liquidity pool management
**Maintainer**: @aitbc-public
**Recent Activity**: Active development (last commit: 2025-06-18)

## Infrastructure Services

### Wallet
**Path**: `apps/wallet`
**Status**: active
**Purpose**: Wallet management service
**Maintainer**: @aitbc-wallet
**Service File**: `aitbc-wallet.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Governance
**Path**: `apps/governance`
**Status**: active
**Purpose**: Governance and voting mechanisms
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-governance.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Agent Management
**Path**: `apps/agent-management`
**Status**: active
**Purpose**: Agent SDK and management
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-agent-management.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Miner
**Path**: `apps/miner`
**Status**: active
**Purpose**: Mining operations
**Maintainer**: @root
**Service File**: `aitbc-miner.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

## Network Services

### Blockchain Event Bridge
**Path**: `apps/blockchain-event-bridge`
**Status**: active
**Purpose**: Cross-chain event bridging
**Maintainer**: @aitbc-public
**Service File**: `aitbc-blockchain-event-bridge.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Blockchain Explorer
**Path**: `apps/blockchain-explorer`
**Status**: active
**Purpose**: Blockchain explorer interface
**Maintainer**: @root
**Service File**: `aitbc-blockchain-explorer.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

### Bridge Monitor
**Path**: `apps/bridge-monitor`
**Status**: active
**Purpose**: Cross-chain bridge monitoring
**Maintainer**: @root
**Recent Activity**: Active development (last commit: 2025-06-18)

### Edge
**Path**: `apps/edge`
**Status**: active
**Purpose**: Edge computing service
**Maintainer**: @aitbc-public
**Recent Activity**: Active development (last commit: 2025-06-18)

### API Gateway
**Path**: `apps/api-gateway`
**Status**: under development
**Purpose**: API gateway for external access
**Maintainer**: @aitbc-public
**Service File**: `aitbc-api-gateway.service`
**Recent Activity**: Active development (last commit: 2025-06-18)

## Shared Libraries

### Shared Core
**Path**: `apps/shared-core`
**Status**: shared library
**Purpose**: Shared core utilities for applications
**Maintainer**: @root
**Recent Activity**: Active development (last commit: 2025-06-18)

### Shared Domain
**Path**: `apps/shared-domain`
**Status**: shared library
**Purpose**: Shared domain models for applications
**Maintainer**: @root
**Recent Activity**: Active development (last commit: 2025-06-18)

## Experimental

### ZK Circuits
**Path**: `apps/zk-circuits`
**Status**: experimental
**Purpose**: Zero-knowledge circuit implementations
**Maintainer**: @root
**Recent Activity**: Last activity: 2025-05-23

## Archived Applications

### PeerTube Transcoder
**Path**: `apps/archive/peertube-transcoder`
**Status**: archived
**Reason**: Planned for reactivation after v0.5
**Note**: See [DEPRECATED.md](apps/archive/peertube-transcoder/DEPRECATED.md) for details

## Summary

- **Total Applications**: 25
- **Active**: 22
- **Under Development**: 2
- **Shared Libraries**: 2
- **Experimental**: 1
- **Archived**: 1

All active applications have recent git activity (within the last 6 months) and are either:
- Referenced in CI workflows
- Have systemd service files
- Are core services required for platform operation

## Version Information

- **Current Version**: 0.5.0 (as per pyproject.toml)
- **Last Updated**: 2026-06-19
- **Documentation Version**: v0.5.0
