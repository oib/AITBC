# AITBC Release Status Overview

**Last updated:** 2026-07-07
**Audit report:** [AUDIT.md](AUDIT.md)

## Release Status Table

| Release | Scope | Status | Notes |
|---------|-------|--------|-------|
| v0.5.16 | Security hardening + multi-chain prep | ✅ Complete | secp256k1 key migration, signing-scheme fix |
| v0.5.17 | Test infrastructure | ✅ Complete | Multi-chain fixtures, multi-node harness |
| v0.5.18 | Test suite repair (blockchain-node) | ✅ Complete | 64 failed + 8 errors fixed, suite green + gated |
| v0.5.19 | Tech debt cleanup | ✅ Complete | Cross-context imports, dead pricing models, fakeredis |
| v0.6.0 | Database & network optimization | ✅ Complete | Query indexing, connection pooling, N+1 elimination |
| v0.6.1 | Parallel processing | ✅ Complete | Parallel tx validation, deterministic scheduling |
| v0.6.2 | Sync & gossip optimization | ✅ Complete | Gossip versioning, compact blocks, delta sync |
| v0.6.3 | Multi-island node support | ✅ Complete | |
| v0.6.4 | Multi-chain per island | ✅ Complete | MultiValidatorPoA/PBFT in THRESHOLD for security review |
| v0.6.5 | Agent coordination service | ✅ Complete | Chain-aware task distribution, PaymentEscrow |
| v0.6.6 | Compute marketplace | ✅ Complete | |
| v0.6.7 | Pool hub & mining | ✅ Complete | |
| v0.7.0 | Bridge basics | ✅ Complete | Lock/unlock, RPC |
| v0.7.1 | Bridge security | ✅ Complete | Multi-sig, signature verification, time-locks |
| v0.7.2 | Bridge verification | ✅ Complete | Merkle proofs, block headers, finality |
| v0.7.3 | Governance | ✅ Complete | |
| v0.7.4 | Deferred v0.7.x items | ✅ Complete | External oracle, cross-chain governance, parameter automation |
| v0.7.5 | Consensus activation | ✅ Complete | MultiValidatorPoA + PBFT enabled for homebrew testing in v0.10.0 (no external audit) |
| v0.8.0 | Inter-chain trading basics | ✅ Complete | Trade requests, matching, agreements |
| v0.8.1 | Cross-chain offer sync (polling) | ✅ Complete | |
| v0.8.2 | Advanced offer sync | ✅ Complete | Subscription, real-time, search index |
| v0.9.0 | Atomic cross-chain settlement | ✅ Complete | A1-A6, B1-B12 complete; external security audit skipped (no budget) |
| v0.10.0 | Runtime bug fixes & service modernization | ✅ Complete | Consensus state root, SharedHttpClient, DB migration, consensus + settlement enabled |
| v0.10.1 | Gap fill for v0.6.0–v0.8.2 | ✅ Complete | 20 tasks: CLI endpoints, island ID, node CLI, RPC compression, feature flags |
| v0.10.2 | Mock & placeholder elimination | ✅ Complete | 17 categories replaced with real queries or honest errors |
| v0.10.3 | Bug fix & hardening | ✅ Complete | 28 issues: exchange financial safety, resource leaks, concurrency, security |
| v0.10.4 | Performance, correctness & cleanup | ✅ Complete | Decimal migration, N+1 elimination, indexes, race conditions, dead code, infra consolidation |
| v0.10.5 | JWT/auth consolidation | ✅ Complete | Shared aitbc/auth/ module; old app auth → re-export shims |
| v0.10.6 | Dead code elimination & Decimal migration completion | ✅ Complete | ~1,570 lines deleted from aitbc/; Decimal migration completed for wallet/trading/marketplace/pool-hub; N+1 + missing indexes fixed; circuit breakers/address validation/config classes/health endpoints consolidated |
| v0.10.7 | Dead code elimination (coordinator-api + agent-management) | ✅ Complete | ~5,800 lines deleted; agent-management deprecated; RPC clients/CLI/DB init consolidated |
| v0.10.8 | Config consolidation & dead retry helper cleanup | ✅ Complete | config.py vs hierarchical_config.py resolved; 3 dead retry helpers deleted |
| v0.10.9 | Dead code elimination & status drift cleanup | ✅ Complete | ~2,900 lines deleted; status drift fixed; stale ports cleaned; auth shims migrated |
| v0.10.10 | Code quality & testing roadmap | ✅ Complete | mypy coverage expanded to 851 files (0 errors), coverage gate 46%, property-based tests, perf regression, dep pinning, dev script, integration fixtures |
| v0.10.11 | Bug fixes & code quality continuation | ✅ Complete | Stub implementations, Pydantic v2 migration, SQLAlchemy patterns, type safety, concurrency safety |
| v1.0.0 | Production readiness | 🚧 Planned | Requires all v0.5.16–v0.10.x complete |
| v2.0.0 | Vision/questionable features | 🅿️ Parked | For re-evaluation after v1.0.0 |

## Security Audit Summary

See [AUDIT.md](AUDIT.md) for the full bridge security audit report.

| Bug | Severity | Status | Summary |
|-----|----------|--------|---------|
| #3 | Critical | ✅ Fixed | Proposer signature not checked against validator set |
| #4 | High | ✅ Fixed | Merkle proof verification silently skipped |
| — | Low | ✅ Resolved | Dead config flag `escrow_require_proof_verification` removed |
| — | Medium | ✅ Implemented | HTLC contract integration (B4) — Python-native HTLCContract wired into settlement |
| — | Medium | 📝 Known | Multi-validator consensus not activated (soak test pending) |

## Key Configuration Defaults

| Flag | Default | Production Recommendation |
|------|---------|--------------------------|
| `bridge_release_enabled` | `True` | Keep enabled (verification now hardened) |
| `bridge_multisig_enabled` | `False` | Enable for multi-validator networks |
| `bridge_require_merkle_proof` | `False` | **Set to `True`** for production |
| `bridge_block_signature_required` | `True` | Keep enabled |
| `escrow_enabled` | `False` | Keep disabled until B4 complete |
| `multi_validator_consensus_enabled` | `False` | Enable after soak test passes |
