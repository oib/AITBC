# AITBC Release Status Overview

**Last updated:** 2026-08-24
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
>
> **Bridge trust model — verified and documented:** the bridge is trust-minimised in design; custodian mode is the honest default; Merkle and multi-sig verification are implemented and off by default. This is documented in `docs/security/bridge-custodian.md` and labelled clearly for operators.

## Trust root

The current live deployment is a single-node, SQLite-backed proof-of-authority chain:

- One `PoAProposer` produces every block and writes it to a local SQLite `chain.db`.
- Followers (e.g. `aitbc3`) replay the hub's chain; the shop is not an independent consensus party.
- `multi_validator_consensus_enabled` defaults to `False`; enabling it requires a non-empty `validator_set` and per-validator keys. The existing `MultiValidatorPoA + PBFT` soak test passed, but it has not been activated in production.
- The coordinator will not create an on-chain escrow without a buyer-supplied `ESCROW_LOCK` signature. The `PAYMENT_BUYER_PRIVATE_KEY` fallback has been removed: the hub no longer signs the buyer's half of the escrow. In the default operator flow a priced job must be submitted with `buyer_lock_signature`, `buyer_lock_nonce`, and `buyer_lock_fee` (via `POST /v1/jobs` or `POST /v1/payments`), or the payment remains `pending`/`skipped` and the job is not dispatched.

## Continuous integration

- **Gitea Actions runner active:** the runner at `gitea-runner` is active and pulls `.gitea/workflows/ci.yml` on push to `main`.
- **Workflow uses `make`:** `ci.yml` now invokes `make lint`, `make no-float-money`, `make typecheck`, `make test`, `make test-apps`, `make test-cli`, `make live-dry-run` and `make openapi-check`, so the gates match the `Makefile` and are reproducible both locally and on the runner.
- **Ruff is present but not yet gating:** `make lint` runs `ruff check . --exit-zero` to report the existing backlog without failing the build; the remaining findings must be fixed before ruff can be made a hard gate.
- **README badge fixed:** the old GitHub Actions badge (which pointed to a non-existent workflow) was replaced with a Gitea Actions badge.

## Economic loop verification

| Property | Verdict | Notes |
|---|---|---|
| The result is verifiable | **FORMALLY** | ZK and TEE gates block escrow release on high-value/confidential jobs (`_zk_required_for`, `_tee_required_for` in `apps/coordinator-api/.../routers/miner.py`; `zk_status != "verified"` / `tee_status != "verified"` blocks release). The proof/attestation is generated from data supplied by the party being paid (the miner's result/receipt or TEE quote), so formal correctness of the proof does not by itself guarantee correctness of the underlying computation. |
| A bad provider loses something | **HOLDS, UNTESTED LIVE** | `ProviderBond` slashing conditions `downtime` (10%), `bad_result` (30%) and `fraud` (50%) are implemented in `apps/coordinator-api/.../marketplace/services/bond_slashing.py` (G5). The fraud slash is gated on an operator ruling via `POST /v1/admin/disputes/{job_id}/resolve` with `outcome=refund` (D1). Downtime and bad-result slashing have regression tests, but no live slash has fired on the network yet. |
| Settlement is trust-minimised | **DOES NOT HOLD** | The live chain has one `PoAProposer` writing to a local SQLite `chain.db`; `multi_validator_consensus_enabled` defaults to `False`. Hub-held keys remain on both sides of the operator flow (single operator controls deposit/payout paths), so settlement remains custodian until multi-validator consensus and a bridge multi-sig are activated and a soak test is completed. |

## Closed design-cycle findings

| Finding | Root cause | Fix | Status |
|---|---|---|---|
| D2 | G2 and G3 were enforced in code but inert in production. The visible half was `aitbc-miner-1` having no `wallet_address`; the hidden half was `POST /v1/payments` falling through the route security matrix to `AuthLevel.DENY` because `fnmatch("/v1/payments", "/v1/payments/*")` is `False`. | `MINER_WALLET_ADDRESS` set on `aitbc3` and registered in `capabilities`; bare `/v1/payments` (CLIENT) and `/v1/blocks` (CLIENT) entries added to `security_matrix.py`; `test_route_security_matrix.py` added. | **Closed 2026-08-24** — commit `870c109e9`, live on hub.aitbc. |
| D5 | Blockchain router proxy handlers imported `coordinator_api.contexts.blockchain.config` (does not exist) instead of `....config`. The import is function-local, so `except NetworkError` did not catch `ImportError` and every proxy route answered 500. | Imports corrected in all six handlers; block routes now return 404 for missing heights and 502 for unreachable nodes; transaction route now calls `/rpc/transaction/{hash}`; `test_blockchain_block_routes.py` added. | **Closed 2026-08-24** — commit `39b510c`, live on hub.aitbc. |
| D6 | `[tool.pytest.ini_options].pythonpath` listed fourteen app source directories but not `apps/blockchain-node/src`, though `mypy_path` had it. `apps/blockchain-node/tests` was uncollectable from the repo root because its `conftest.py` imports `aitbc_chain` at module scope. | Added `apps/blockchain-node/src` to `pythonpath` in `pyproject.toml`. | **Closed 2026-08-24** — commit `0117c2d`. 709 blockchain-node tests now run and pass from the repo root; `test_blockchain_client_paths.py` now executes and validates coordinator URLs against the real node route table. Root `tests/` suite still aborts on 4 pre-existing collection errors. |

## Live economic-loop validation

Job `6a20fdb7aedf4abb8e8218c5e3cd893a` ran end-to-end on live hub/aitbc balances:

| Stage | Finding | Result |
|---|---|---|
| G4 | Unpriced/unsuccessful escrow should not dispatch. | Job stayed `QUEUED` and unassigned for 45s of live miner polling. |
| Escrow | Buyer-signed `ESCROW_LOCK` debits real funds. | 201 `escrowed`; buyer 4636 → 1000 (3600 compute-seconds + 36 fee debited on-chain). |
| G2 | Payee must be the worker's wallet. | Dispatched to `aitbc-miner-1` within 5s, the wallet the escrow named. |
| Execution | GPU inference runs. | `llama3.2:3b` via Ollama, 71.7s. |
| G3 | Result opens an acceptance window instead of releasing. | Job moved to `COMPLETED` / `pending_acceptance`; provider unpaid; 300s per-job window honoured. |
| Release | Sweeper releases on expiry. | Provider wallet went from *Account not found* to **3510** compute-seconds. |

**Limitation:** only the accept-by-expiry branch was exercised on live traffic. The reject and operator dispute-ruling branches remain test-verified only.
