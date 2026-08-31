# AITBC Release Notes Summary

**Last Updated**: 2026-08-24
**Version**: 1.2

This document provides a user-friendly summary of AITBC releases, organized by major themes and tracks. For detailed release notes and agent task assignments, see the individual version directories.

## Quick Navigation

- [Infrastructure Track](#infrastructure-track) - Multi-chain foundation, database, network, sync
- [Product Track](#product-track) - Agent coordination, marketplace, governance
- [Bridge & Trading Track](#bridge--trading-track) - Cross-chain bridge, atomic settlement
- [Latest Releases](#latest-releases) - Most recent releases
- [Version History](#version-history) - Complete version list

---

## Infrastructure Track

Multi-chain foundation, database optimization, network improvements, and synchronization.

### v0.6.x - Multi-Chain Foundation

| Version | Theme | Status | Key Features |
|---------|-------|--------|--------------|
| **v0.6.0** | Database & Network Optimization | ✅ Complete | Query indexing, connection pooling, N+1 elimination, batch writes, block header caching, network compression |
| **v0.6.1** | Parallel Processing | ✅ Complete | Parallel tx validation via dependency analysis, deterministic scheduling, pure state transitions |
| **v0.6.2** | Sync & Gossip Optimization | 🚧 Planned | Gossip protocol versioning, message prioritization, compact blocks, parallel sync, delta sync |
| **v0.6.3** | Multi-Island Node Support | 🚧 Planned | Multi-island node configuration, island isolation, cross-island communication |
| **v0.6.4** | Multi-Chain Per Island | 🚧 Planned | Multiple blockchains per island, chain isolation, cross-chain routing |

---

## Product Track

Agent coordination, compute marketplace, pool hub, and governance features.

### v0.6.x - Product Features

| Version | Theme | Status | Key Features |
|---------|-------|--------|--------------|
| **v0.6.5** | Agent Coordination Service | ✅ Complete | Chain_id/island_id awareness, PaymentEscrow, chain-aware task distribution |
| **v0.6.6** | Compute Marketplace | 🚧 Planned | GPU provider testing, transaction tracking, verification procedures |
| **v0.6.7** | Pool Hub & Mining | 🚧 Planned | Mining pool management, reward distribution, pool coordination |

---

## Bridge & Trading Track

Cross-chain bridge, governance, and atomic settlement features.

### v0.7.x - Bridge & Governance

| Version | Theme | Status | Key Features |
|---------|-------|--------|--------------|
| **v0.7.0** | Bridge Basics | ✅ Complete | Cross-chain bridge implementation, asset transfer, bridge RPC endpoints |
| **v0.7.1** | Bridge Security | ✅ Complete | Security hardening, signature verification, attack mitigation |
| **v0.7.2** | Bridge Verification | ✅ Complete | In-process crypto verification, bridge transaction validation |
| **v0.7.3** | Governance | ✅ Complete | On-chain proposals, voting, parameter changes (same-chain) |
| **v0.7.4** | Deferred v0.7.x Items | ✅ Complete | External oracle, cross-chain governance, parameter automation, emergency proposals |
| **v0.7.5** | Consensus Activation | ⚠️ Code Complete | MultiValidatorPoA + PBFT (security review fixes complete, soak test pending) |

### v0.8.x - Trading & Settlement

| Version | Theme | Status | Key Features |
|---------|-------|--------|--------------|
| **v0.8.0** | Inter-Chain Trading Basics | ✅ Complete | Cross-chain trading service, offer management, trade matching |
| **v0.8.1** | Cross-Chain Offer Sync | ✅ Complete | Polling-based sync, local offer cache (Redis), staleness detection, conflict resolution |
| **v0.8.2** | Advanced Offer Sync | ✅ Complete | Subscription-based sync, real-time notifications, gossip propagation, optional search index |
| **v0.9.0** | Atomic Cross-Chain Settlement | ✅ Complete | HTLC-based atomic settlement, cross-chain escrow, timeout handling |

---

## Version History

### Completed Releases

| Version | Theme | Release Date | Status |
|---------|-------|--------------|--------|
| v0.5.11 | Type Safety Hardening | - | ✅ Complete |
| v0.5.12 | Duplication Elimination | - | ✅ Complete |
| v0.5.13 | Coordinator-API Bounded Context | - | ✅ Complete |
| v0.5.14 | Cross-Context Dependency Elimination | - | ✅ Complete |
| v0.5.15 | Flat-to-Context Migration | - | ✅ Complete |
| v0.5.16 | Security Hardening & Multi-Chain Preparation | - | ✅ Complete |
| v0.5.17 | Test Infrastructure | - | ✅ Complete |
| v0.5.18 | Test Suite Repair | - | ✅ Complete |
| v0.5.19 | Tech Debt Cleanup | - | ✅ Complete |
| v0.6.0 | Database & Network Optimization | - | ✅ Complete |
| v0.6.1 | Parallel Processing | - | ✅ Complete |
| v0.6.2 | Sync & Gossip Optimization | - | ✅ Complete |
| v0.6.3 | Multi-Island Node Support | - | ✅ Complete |
| v0.6.4 | Multi-Chain Per Island | - | ✅ Complete |
| v0.6.5 | Agent Coordination Service | - | ✅ Complete |
| v0.6.6 | Compute Marketplace | - | ✅ Complete |
| v0.6.7 | Pool Hub & Mining | - | ✅ Complete |
| v0.7.0 | Bridge Basics | - | ✅ Complete |
| v0.7.1 | Bridge Security | - | ✅ Complete |
| v0.7.2 | Bridge Verification | - | ✅ Complete |
| v0.7.3 | Governance | - | ✅ Complete |
| v0.7.4 | Deferred v0.7.x Items | - | ✅ Complete |
| v0.7.5 | Consensus Activation | - | ⚠️ Code Complete |
| v0.8.0 | Inter-Chain Trading Basics | - | ✅ Complete |
| v0.8.1 | Cross-Chain Offer Sync | - | ✅ Complete |
| v0.8.2 | Advanced Offer Sync | - | ✅ Complete |
| v0.9.0 | Atomic Cross-Chain Settlement | - | ✅ Complete |
| v0.10.0 | Runtime Bug Fixes & Service Modernization | - | ✅ Complete |
| v0.10.1 | Gap Fill for v0.6.0–v0.8.2 | - | ✅ Complete |
| v0.10.2 | Mock & Placeholder Elimination | - | ✅ Complete |
| v0.10.3 | Bug Fix & Hardening | - | ✅ Complete |
| v0.10.4 | Performance, Correctness & Cleanup | - | ✅ Complete |
| v0.10.5 | JWT/Auth Consolidation | - | ✅ Complete |
| v0.10.6 | Dead Code Elimination & Decimal Migration Completion | - | ✅ Complete |
| v0.10.7 | Dead Code Elimination (coordinator-api + agent-management) | - | ✅ Complete |
| v0.10.8 | Config Consolidation & Dead Retry Helper Cleanup | - | ✅ Complete |
| v0.10.9 | Dead Code Elimination & Status Drift Cleanup | - | ✅ Complete |
| v0.10.10 | Code Quality & Testing Roadmap | - | ✅ Complete |
| v0.10.11 | Bug Fixes & Code Quality Continuation | - | ✅ Complete |
| v0.10.12 | Quality Hardening | - | ✅ Complete |
| v0.10.13 | Security & Correctness Hardening | - | ✅ Complete |
| v0.10.14 | Legacy Code & Stub Elimination | - | ✅ Complete |
| v0.10.15 | Router/Module Decomposition & Settlement Config Wiring | - | ✅ Complete |
| v0.10.16 | Security & Correctness Hardening | - | ✅ Complete |
| v0.10.17 | Security & Auth Hardening (bugfix) | - | ✅ Complete |
| v0.10.18 | Update Deployment Stabilization | - | ✅ Complete |
| v0.24.0 | Hub Node Development Special | - | ✅ Complete |
| v0.25.0 | On-chain Liquidity, Sync Consolidation and MCP Expansion | - | ✅ Complete |
| v0.25.1 | Open follow-ups and design notes | - | ✅ Complete |
| v0.25.2 | Compute-unit re-denomination (36,000,000 per AIT) | 2026-08-24 | 🚧 In Progress |

### Planned Releases

| Version | Theme | Status |
|---------|-------|--------|
| v1.0.0 | Production Readiness | 🚧 Planned |

### Future Vision (Post-v1.0)

| Version | Theme | Status |
|---------|-------|--------|

---

## Release Sequence

The release sequence is monotonic - each release has a higher version than the one before it:

```
v0.5.16 → v0.5.17 → v0.5.18 → v0.5.19
  → v0.6.0 → v0.6.1 → v0.6.2 → v0.6.3 → v0.6.4
  → v0.6.5 → v0.6.6 → v0.6.7
  → v0.7.0 → v0.7.1 → v0.7.2 → v0.7.3 → v0.7.4 → v0.7.5
  → v0.8.0 → v0.8.1 → v0.8.2 → v0.9.0
  → v1.0.0 (production readiness)
```

---

## Documentation Structure

Each release has detailed documentation split into topic-focused files:

- **AGENTS.md** - Main release notes with task assignment
- **overview.md** - Release overview, status baseline, task split overview
- **agent-a.md** - Agent A tasks (shared core implementation)
- **agent-b.md** - Agent B tasks (apps & infrastructure implementation)

For detailed information about a specific release, navigate to the corresponding version directory.

---

## Agent Roles

- **Agent A** - Shared core (`aitbc/`) - Types, config, db, logging, queues, crypto, network
- **Agent B** - Apps & infrastructure - All `apps/`, `cli/`, systemd config

See AGENTS.md for detailed agent role definitions and coordination protocols.

---

## Verification Commands

```bash
# Type check (shared core)
./venv/bin/python -m mypy --show-error-codes aitbc/

# Lint (whole repo)
./venv/bin/python -m ruff check .

# Tests (unit)
./venv/bin/python -m pytest tests/unit -q

# Tests (integration)
./venv/bin/python -m pytest tests/integration -q
```

---

## Additional Resources

- Master AGENTS.md - Project conventions and verification commands
- [Release Status Overview](./STATUS.md) - All releases, config defaults, audit summary
- [Security Audit Summary](./AUDIT.md) - Bridge security audit status
- [Writing Docs Guide](../meta/writing-docs.md) - Documentation standards and guidelines

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
