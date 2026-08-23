# AITBC Release Status Overview

**Last updated:** 2026-08-21
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
| v0.7.1 | Bridge security | ✅ Complete | Multi-sig, signature verification, time-locks — implemented and regression-tested, but `bridge_multisig_enabled` defaults to `False`; live bridge is trusted-custodian unless enabled. |
| v0.7.2 | Bridge verification | ✅ Complete | Merkle proofs, block headers, finality — implemented and regression-tested, but `bridge_require_merkle_proof` defaults to `False`; live bridge is trusted-custodian unless enabled. |
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
| v0.10.12 | Quality hardening | ✅ Complete | mypy completeness, test suite repair, production assert removal, dependency/version cleanup |
| v0.10.13 | Security & correctness hardening | ✅ Complete | credential hygiene, auth boundaries, signature verification, fake payments, file permissions, migration integrity, test coverage |
| v0.10.14 | Legacy code & stub elimination | ✅ Complete | shadow packages, legacy routers, fake implementations, duplicate stacks |
| v0.10.15 | Router/module decomposition & settlement config wiring | ✅ Complete | sync/bridge/trading/developer-platform decomposition; per-chain block times |
| v0.10.16 | Security & correctness hardening | ✅ Complete | bridge trust boundaries, wallet auth, financial exactness, migrations, CI/deployment |
| v0.10.17 | Security & auth hardening (bugfix) | ✅ Complete | auth bypass, hardcoded defaults, feature flags, pool-hub reward signing, wiring bug |
| v0.10.18 | Update deployment stabilization | ✅ Complete | market_metrics migration conflict, wallet keystore restore, update.sh/health_check.sh fixes, poetry switch, schema-drift reconciliation |
| v0.11.0 | Phase 4 & 2026 Roadmap Foundations | 🚧 Planned | OpenClaw autonomous economics, decentralized AI memory/storage, developer ecosystem & DAO grants, Phase 4 criteria, compliance modules |
| v0.12.0 | OpenClaw Autonomous Economics | 🚧 Planned | Agent wallets/escrow, performance bonds, automated rebalancing, dynamic fee market, OpenClaw DAO economic governance |
| v0.13.0 | Mature Autonomous Economic Infrastructure | 🚧 Planned | Automated staking/rebalancing, performance bond lifecycle, provider reinvestment, risk/solvency engine, cross-chain yield, slashing appeals |
| v0.14.1 | TEE-Backed Verification & Confidential Compute (Phase 1) | 🚧 Planned | Attestation, enclaves, confidential messaging, TEE-backed data processing |
| v0.14.2 | TEE-Backed Verification & Confidential Compute (Phase 2) | 🚧 Planned | ZK+TEE dual verification, confidential transactions, healthcare/finance reference enclaves |
| v0.15.1 | Compliance-Ready Modules (Phase 1) | 🚧 Planned | Policy framework, data classification, encryption, immutable audit logging, HIPAA |
| v0.15.2 | Compliance-Ready Modules (Phase 2) | 🚧 Planned | Compliance containers/sub-networks, financial regulatory module, middleware, CLI |
| v0.16.1 | Platform Builder Tooling (Phase 1) | 🚧 Planned | CLI config tool, developer registry, DAO grants, local dev helpers, builder docs |
| v0.16.2 | Platform Builder Tooling (Phase 2) | 🚧 Planned | SDK, SDK reference docs, white-label/plugin architecture |
| v0.17.0 | Accessibility & Theme Engine | 🚧 Planned | Light/dark/high-contrast/system modes, reduced motion, WCAG focus, user preference persistence |
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
| — | Medium | ✅ Soaked | Multi-validator consensus not activated by default; soak test passes (1000 rounds, validator changes, partition tolerance, PBFT) |

## Key Configuration Defaults

| Flag | Default | Production Recommendation |
|------|---------|--------------------------|
| `bridge_release_enabled` | `False` | **Trusted-custodian mode by default** — operator release path. Set to `True` only after a multi-sig validator set and Merkle proof ingestion are operational. |
| `bridge_multisig_enabled` | `False` | Enable for multi-validator networks |
| `bridge_require_merkle_proof` | `False` | **Set to `True`** for production |
| `bridge_block_signature_required` | `True` | Keep enabled |
| `escrow_enabled` | `True` | **Keep enabled** — B4 HTLC contract integration is complete; paid job escrow/create/release is live; cross-chain bridge settlement is active. |
| `multi_validator_consensus_enabled` | `False` | Soak test added (1000 rounds + partition/PBFT). Enable only after configuring a validator set and per-validator signing keys; the live `PoAProposer` still uses the single `PROPOSER_ID` while this flag is `False`. |

> **Escrow scope:** `escrow_enabled` now defaults to `True`. The job-payment escrow path (`/rpc/escrow/create` and `/escrow/{job_id}/release`) is live. Cross-chain bridge HTLC settlement is also gated by this flag; operators who want trust-minimized bridge operation should additionally enable `bridge_require_merkle_proof`, `bridge_multisig_enabled`, and `multi_validator_consensus_enabled` and complete a soak test.
>
> **Bridge security defaults:** `bridge_release_enabled=False` means the live bridge still operates as a trusted custodian. Merkle-proof and multi-sig verification are implemented and covered by regression tests, but they are **disabled by default** and must be explicitly enabled for a trust-minimized configuration.
