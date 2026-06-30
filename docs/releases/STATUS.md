# AITBC Release Status Overview

**Last updated:** 2026-06-18
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
| v0.6.2 | Sync & gossip optimization | 🚧 Planned | Gossip versioning, compact blocks, delta sync |
| v0.6.3 | Multi-island node support | 🚧 Planned | |
| v0.6.4 | Multi-chain per island | 🚧 Planned | |
| v0.6.5 | Agent coordination service | ✅ Complete | Chain-aware task distribution, PaymentEscrow |
| v0.6.6 | Compute marketplace | 🚧 Planned | |
| v0.6.7 | Pool hub & mining | 🚧 Planned | |
| v0.7.0 | Bridge basics | ✅ Complete | Lock/unlock, RPC |
| v0.7.1 | Bridge security | ✅ Complete | Multi-sig, signature verification, time-locks |
| v0.7.2 | Bridge verification | ✅ Complete | Merkle proofs, block headers, finality |
| v0.7.3 | Governance | ✅ Complete | |
| v0.7.4 | Deferred v0.7.x items | ✅ Complete | External oracle, cross-chain governance, parameter automation |
| v0.7.5 | Consensus activation | ⚠️ Code complete, NOT activated | MultiValidatorPoA + PBFT; soak test pending |
| v0.8.0 | Inter-chain trading basics | ✅ Complete | Trade requests, matching, agreements |
| v0.8.1 | Cross-chain offer sync (polling) | ✅ Complete | |
| v0.8.2 | Advanced offer sync | ✅ Complete | Subscription, real-time, search index |
| v0.9.0 | Atomic cross-chain settlement | 🚧 In Progress | B1-B5 complete; chaos testing + external audit pending |
| v1.0.0 | Production readiness | 🚧 Planned | Requires all v0.5.16–v0.9.0 complete |
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
