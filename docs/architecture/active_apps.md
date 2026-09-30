# Active AITBC Applications

This document lists AITBC applications and their status. Per-app dates were dropped — they were stale stamps, not signal; check `git log` for real activity.

## Core Services

### Agent Coordinator

**Path**: `apps/agent-coordinator`
**Status**: active
**Purpose**: Agent lifecycle management
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-agent-coordinator.service`

### Coordinator API

**Path**: `apps/coordinator-api`
**Status**: active
**Purpose**: Main REST API for AITBC platform
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-coordinator-api.service`

### Blockchain Node

**Path**: `apps/blockchain-node`
**Status**: active
**Purpose**: Blockchain node with RPC, P2P, and sync services
**Maintainer**: @aitbc-blockchain
**Service Files**: `aitbc-blockchain-node.service`, `aitbc-blockchain-p2p.service`, `aitbc-blockchain-rpc.service`

## AI/ML Services

### GPU Service

**Path**: `apps/gpu`
**Status**: active
**Purpose**: GPU resource management and market
**Maintainer**: @aitbc-gpu
**Service File**: `aitbc-gpu.service`

### AI Engine

**Path**: `apps/ai-engine`
**Status**: deployed (aitbc-api-gateway is in the live fleet)
**Purpose**: AI model training and inference
**Maintainer**: @aitbc-public
**Service Files**: `aitbc-ai.service`, `aitbc-learning.service`, `aitbc-modality-optimization.service`, `aitbc-multimodal.service`

### Whisper

**Path**: `apps/whisper`
**Status**: active
**Purpose**: Speech-to-text transcription service
**Maintainer**: @aitbc-public

### FFmpeg

**Path**: `apps/ffmpeg`
**Status**: active
**Purpose**: Video transcoding service
**Maintainer**: @aitbc-public

## Market & Trading

### Market

**Path**: `apps/market`
**Status**: active
**Purpose**: GPU and compute resource market
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-market.service`

### Exchange

**Path**: `apps/exchange`
**Status**: active
**Purpose**: Cross-chain exchange and trading
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-exchange.service`

### Trading

**Path**: `apps/trading`
**Status**: active
**Purpose**: Trading and order management
**Maintainer**: @aitbc-internal

### Pool Hub

**Path**: `apps/pool-hub`
**Status**: active
**Purpose**: Liquidity pool management
**Maintainer**: @aitbc-public

## Infrastructure Services

### Wallet

**Path**: `apps/wallet`
**Status**: active
**Purpose**: Wallet management service
**Maintainer**: @aitbc-wallet
**Service File**: `aitbc-wallet.service`

### Governance

**Path**: `apps/governance`
**Status**: active
**Purpose**: Governance and voting mechanisms
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-governance.service`

### Hermes Agent

**Path**: `apps/hermes_agent`
**Status**: active
**Purpose**: Background agent daemon and task execution
**Maintainer**: @aitbc-public
**Service File**: `aitbc-hermes-agent.service`

### IPFS

**Path**: `apps/ipfs`
**Status**: active
**Purpose**: Local content-addressed storage and rental gateway
**Maintainer**: @aitbc-public
**Service Files**: `aitbc-ipfs.service`, `aitbc-island-ipfs.service`

### Memory

**Path**: `apps/memory`
**Status**: under development
**Purpose**: Memory / context service for agent tasks
**Maintainer**: @aitbc-public

### Agent Management (deprecated)

**Path**: `apps/agent-management`
**Status**: deprecated
**Purpose**: Agent SDK and management
**Maintainer**: @aitbc-internal
**Service File**: `aitbc-agent-management.service` (no longer deployed)
**Recent Activity**: Deprecated; agent SDK moved to `packages/py/aitbc-agent-sdk/` and `aitbc agent` CLI commands

### Miner

**Path**: `apps/miner`
**Status**: active
**Purpose**: Mining operations
**Maintainer**: @root
**Service File**: `aitbc-miner.service`

## Network Services

### Blockchain Event Bridge

**Path**: `apps/blockchain-event-bridge`
**Status**: active
**Purpose**: Cross-chain event bridging
**Maintainer**: @aitbc-public
**Service File**: `aitbc-blockchain-event-bridge.service`

### Blockchain Explorer

**Path**: `apps/blockchain-explorer`
**Status**: active
**Purpose**: Blockchain explorer interface
**Maintainer**: @root
**Service File**: `aitbc-blockchain-explorer.service`

### Bridge Monitor

**Path**: `apps/bridge-monitor`
**Status**: active
**Purpose**: Cross-chain bridge monitoring
**Maintainer**: @root

### Edge

**Path**: `apps/edge`
**Status**: active
**Purpose**: Edge computing service
**Maintainer**: @aitbc-public

### API Gateway

**Path**: `apps/api-gateway`
**Status**: under development
**Purpose**: API gateway for external access
**Maintainer**: @aitbc-public
**Service File**: `aitbc-api-gateway.service`

## Shared Libraries

### Shared Core

**Path**: `apps/shared-core`
**Status**: shared library
**Purpose**: Shared core utilities for applications
**Maintainer**: @root

### Shared Domain

**Path**: `apps/shared-domain`
**Status**: shared library
**Purpose**: Shared domain models for applications
**Maintainer**: @root

## Experimental

### ZK Circuits

**Path**: `apps/zk-circuits`
**Status**: experimental
**Purpose**: Zero-knowledge circuit implementations
**Maintainer**: @root

## Summary

- **Total Applications**: 26
- **Active**: see per-app rows — the historical 24/2 split does not reconcile with the rows (19+3+2+1+1)
- **Under Development**: 2
- **Shared Libraries**: 2
- **Experimental**: 1
- **Deprecated**: 1

## Version Information

- **Current Version**: see `aitbc --version` on a live node (docs lag releases)
- **Last Updated**: 2026-08-21
- **Documentation Version**: v0.10.18

### Deprecated / parked entries

- `apps/agent-management` — deprecated; agent SDK and lifecycle moved to `aitbc agent` and `packages/py/aitbc-agent-sdk/`. The service file is no longer deployed on the live nodes.
- `apps/ai-engine` — under development; not part of the default Ollama shop loop.
- `apps/zk-circuits` — experimental; circuits exist but are not wired into job verification.
