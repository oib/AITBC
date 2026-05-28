# AITBC Current Operational State

**Last Updated**: 2026-05-28
**Version**: 1.1 (May 28, 2026 Update - documentation review completion)

---

## Overview

This document describes the actual operational state of the AITBC deployment, distinguishing between designed capabilities and current implementation status. It serves as a companion to the main README and operational skills to provide transparency about what is currently working versus what is aspirational.

## Deployment Architecture

### Multi-Node Configuration

| Node | Hostname | Role | Status |
|------|----------|------|--------|
| Main Node | aitbc (localhost) | Primary development + blockchain | Operational |
| Follower Node | aitbc1 | Secondary blockchain node | Operational |
| CI/CD Node | gitea-runner | CI/CD runner + aitbc2 blockchain | Operational |

### Network Configuration

- **P2P Network**: Port 7070 (peer-to-peer blockchain communication)
- **SSH Access**: Key-based authentication configured between all nodes
- **Git Remotes**: 
  - `origin`: Gitea at `http://gitea.bubuit.net:3000/oib/aitbc.git` (daily development)
  - `github`: GitHub at `https://github.com/oib/AITBC.git` (milestone releases)

## Service Status

### Core Blockchain Services

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| Blockchain RPC | 8006 | 🟢 Operational | Main blockchain node RPC |
| Blockchain P2P | 7000 | 🟢 Operational | P2P networking |
| Coordinator API | 8011 | 🟢 Operational | Agent registry, /v1/* routes |
| Wallet Daemon | 8015 | 🟢 Operational | Wallet management (localhost only) |
| Exchange API | 8001 | 🟢 Operational | Trading (localhost only) |
| Marketplace | 8102 | 🟢 Operational | GPU marketplace |

### Additional Services

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| AI Service | 8005 | 🟡 Partial | Ollama integration functional |
| Learning Service | 8012 | 🔴 Aspirational | Adaptive learning not deployed |
| Multimodal Service | 8020 | 🔴 Aspirational | Multimodal processing not deployed |
| Modality Optimization | 8021 | 🔴 Aspirational | Optimization service not deployed |
| Blockchain Event Bridge | 8204 | 🟡 Partial | Event bridging partially functional |

### Systemd Services

Total systemd services: 23 (all running on main node)

## Known Issues and Limitations

### 1. Port Configuration History

**Resolved Issues:**
- **Wallet API**: Previously documented as 8003 in SETUP.md, corrected to 8015 (actual port from app/main.py)
- **Coordinator API**: Previously documented as 8000 in SETUP.md, corrected to 8011 (actual port from wrapper script)

**Current Configuration:**
- All port configurations are now centralized in [Service Ports Reference](../reference/SERVICE_PORTS.md)
- Port conflicts have been resolved through service wrapper script updates

### 2. SQLite Corruption Prevention

**Root Cause:** SQLite expects stable page writes with overwrite-in-place behavior, but Btrfs uses copy-on-write with delayed allocation. This mismatch caused corruption during SQLite write operations under stress.

**Prevention Fixes Applied:**
- CoW disabled on data directory: `chattr +C /var/lib/aitbc`
- WAL mode enabled for databases

**Current Status:**
- aitbc1: CoW disabled + WAL enabled (database recreated)
- localhost: CoW disabled + WAL enabled
- gitea-runner: CoW disabled (WAL mode needs application-level config)

**WAL Mode Limitation:**
WAL mode set via sqlite3 command doesn't persist after service restart because SQLAlchemy/SQLModel sets journal mode on database connection. WAL mode needs to be enabled at the application level via database connection string or configuration.

### 3. CLI Entry Point Clarification

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Direct Python Invocation:** `python3 cli/unified_cli.py`

Use direct Python invocation for:
- Marketplace operations (GPU provider registration, trading)
- GPU testing and Ollama operations
- Specific module features requiring direct access

### 4. Dependency Gaps

**Python Dependencies:**
- Core dependencies (fastapi, click, uvicorn) are installed and functional
- Some AI/ML dependencies may be missing for advanced features
- GPU provider dependencies require Ollama installation

**Service Dependencies:**
- PostgreSQL: Port 5432, configured for wallet and exchange services
- Ollama: Required for GPU provider operations, installation status varies by node

### 5. Security Considerations

**Known Security Issues:**
- Wildcard CORS with credentials in some services (identified in codebase analysis)
- Some services trust X-Wallet-Address header (placeholder behavior)
- JWT authentication has placeholder behavior in some routes

**Remediation Status:**
- Security scanning CI/CD pipeline is operational
- Bandit and pip-audit scans run on every commit
- Some high-priority security fixes remain outstanding

## Designed vs Current State

### Designed Capabilities (Aspirational)

The AITBC platform is designed to provide:

1. **Multi-Agent Coordination**: Full cross-node agent discovery and messaging
2. **GPU Marketplace**: Complete GPU resource allocation and trading
3. **AI Job Orchestration**: End-to-end AI job submission, monitoring, and results retrieval
4. **Smart Contract Integration**: On-chain dispute resolution and staking
5. **Advanced Learning**: Adaptive learning services for agent optimization
6. **Multimodal Processing**: Support for multi-modal AI operations

### Current Implementation Status

**Fully Operational (🟢):**
- Basic blockchain operations (blocks, transactions, mempool)
- Wallet management (create, list, import, export)
- Service health monitoring
- Multi-node git synchronization
- Basic marketplace operations (listings, bids)
- GPU provider registration (partial)

**Procedure Validated (🟡):**
- AI job submission and monitoring (requires Ollama)
- GPU testing workflows (requires Ollama)
- Cross-node coordination (requires all nodes operational)
- Exchange API operations (localhost only)

**Aspirational (🔴):**
- Adaptive learning services
- Multimodal processing
- Modality optimization
- Complete smart contract integration
- Full GPU marketplace automation

## Operational Skills Status

All operational skills in `skills/aitbc/` have been updated with:

- **Status Indicators**: 🟢 Procedure Validated / 🟡 Procedure Validated / 🔴 Aspirational
- **Port References**: Links to centralized [Service Ports Reference](../reference/SERVICE_PORTS.md)
- **CLI Entry Point Guidance**: Clear guidance on when to use wrapper vs direct Python
- **Prerequisite Validation**: Check blocks to verify dependencies before operations

**Skill Status Summary:**
- aitbc-basic-operations.md: 🟡 Procedure Validated
- aitbc-marketplace.md: 🟡 Procedure Validated
- aitbc-wallet-management.md: 🟡 Procedure Validated
- aitbc-node-coordination.md: 🟡 Procedure Validated
- aitbc-ai-operations.md: 🟡 Procedure Validated
- aitbc-multi-node-operations.md: 🟡 Procedure Validated
- aitbc-blockchain-troubleshooting.md: 🟢 Evergreen Reference

## Troubleshooting Reference

For common issues and resolution steps, see:
- [Blockchain Troubleshooting Skill](../../skills/aitbc/aitbc-blockchain-troubleshooting.md)
- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [Setup Guide](../deployment/SETUP.md)

## Maintenance Notes

### Service Restart Order

When restarting services after code updates:
1. Stop blockchain-node service
2. Stop blockchain-p2p service
3. Apply code changes
4. Start blockchain-p2p service
5. Start blockchain-node service
6. Verify P2P connections (port 7070)
7. Verify RPC endpoints (port 8006)

### Database Maintenance

- Regular integrity checks: `sqlite3 /var/lib/aitbc/data/blockchain.db "PRAGMA integrity_check;"`
- Verify CoW status: `lsattr /var/lib/aitbc`
- Backup before major changes: `cp -r /var/lib/aitbc/data /var/lib/aitbc/data.backup`

### Git Sync Workflow

1. Commit and push from main node to Gitea
2. Pull on follower node (aitbc1)
3. Pull on gitea-runner
4. Restart affected services on all nodes
5. Verify blockchain sync across nodes

## Related Documentation

- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Authoritative port configuration
- [Setup Guide](../deployment/SETUP.md) - Installation and configuration
- [Security Policy](../security/SECURITY.md) - Security practices and reporting
- [Operational Skills](../../skills/aitbc/) - Day-to-day operations

---

**Last Updated**: 2026-05-28
**Maintained By**: AITBC Documentation Team
