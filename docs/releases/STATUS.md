# AITBC Release Status Overview

**Last updated:** 2026-09-03
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
| v0.14.1 | TEE-Backed Verification & Confidential Compute (Phase 1) | ⏸️ Deferred to v2.0 | Simulated path (`SIMULATED_TEE=1`) is live and gated; real attestation deferred until TEE hardware is available — see [Deferred to v2.0](#deferred-to-v20--hardware-backed-tee) |
| v0.14.2 | TEE-Backed Verification & Confidential Compute (Phase 2) | ⏸️ Deferred to v2.0 | ZK+TEE dual verification, confidential transactions, healthcare/finance reference enclaves; blocked on the same hardware dependency as v0.14.1 |
| v0.15.1 | Compliance-Ready Modules (Phase 1) | 🚧 Planned | Policy framework, data classification, encryption, immutable audit logging, HIPAA |
| v0.15.2 | Compliance-Ready Modules (Phase 2) | 🚧 Planned | Compliance containers/sub-networks, financial regulatory module, middleware, CLI |
| v0.16.1 | Platform Builder Tooling (Phase 1) | 🚧 Planned | CLI config tool, developer registry, DAO grants, local dev helpers, builder docs |
| v0.16.2 | Platform Builder Tooling (Phase 2) | 🚧 Planned | SDK, SDK reference docs, white-label/plugin architecture |
| v0.17.0 | Accessibility & Theme Engine | 🚧 Planned | Light/dark/high-contrast/system modes, reduced motion, WCAG focus, user preference persistence |
| v1.0.0 | Production readiness | 🚧 Planned | Requires all v0.5.16–v0.10.x complete |
| v2.0.0 | Hardware-backed TEE attestation | 🚧 Planned (no date) | Holds the deferred v0.14.1/v0.14.2 scope. Cannot start until SGX/TDX-capable hardware is available to the fleet. |
| v0.24.0 | Hub node development special | ✅ Complete | See [v0.24.0 overview](v0.24/v0.24.0_change.log); details split into v0.24.1–v0.24.18 |
| v0.25.0 | On-chain liquidity, sync consolidation and MCP expansion | ✅ Complete | AIT-only on-chain liquidity pool, MCP server expansion; see v0.25.0_change.log |
| v0.25.1 | Open follow-ups and design notes | ✅ Complete | Post-v0.25.0 live-validation gaps and operational tasks; see v0.25.1_change.log |

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
| `bridge_release_enabled` | `True` (live since 2026-08-25) | **Trust-minimized mode** on `hub.aitbc` and `aitbc3`: `release_enabled=true`, `multisig_enabled=true`, `require_merkle_proof=true`. Fresh deployments should keep `False` until a multi-sig validator set and Merkle proof ingestion are operational. |
| `bridge_multisig_enabled` | `False` | Enable for multi-validator networks |
| `bridge_require_merkle_proof` | `False` | **Set to `True`** for production |
| `bridge_block_signature_required` | `True` | Keep enabled |
| `escrow_enabled` | `True` | **Keep enabled** — B4 HTLC contract integration is complete; paid job escrow/create/release is live; cross-chain bridge settlement is active. |
| `multi_validator_consensus_enabled` | `False` | Soak test added (1000 rounds + partition/PBFT). Enable only after configuring a validator set and per-validator signing keys; the live `PoAProposer` still uses the single `PROPOSER_ID` while this flag is `False`. |

> **Escrow scope:** `escrow_enabled` now defaults to `True`. The job-payment escrow path (`/rpc/escrow/create` and `/escrow/{job_id}/release`) is live. Cross-chain bridge HTLC settlement is also gated by this flag; operators who want trust-minimized bridge operation should additionally enable `bridge_require_merkle_proof`, `bridge_multisig_enabled`, and `multi_validator_consensus_enabled` and complete a soak test.
>
> **Bridge security defaults (2026-08-25):** `bridge_release_enabled` is now `True` live on `hub.aitbc` and `aitbc3`; `aitbc bridge security-status` reports `release_enabled: true`, `multisig_enabled: true`, and `require_merkle_proof: true`. However, a live consensus stall prevents safe confirmations: see the Open design-review gaps table and the bridge/live-validation section below.
>
> **Bridge trust model — verified and documented (2026-08-25):** Merkle and multi-sig verification are implemented and live-enabled on `hub.aitbc` / `aitbc3`. Custodian mode remains the honest fallback. Bridge `confirm` should not be invoked while the two-validator chain is stalled; the safe path is to clear the consensus stall first. See `docs/security/bridge-custodian.md`.

## Trust root

**Superseded 2026-08-24 (see below):** earlier the same day, "multi-key consensus" meant both validator keys living on this single hub node (documented in the original version of this section as local proposer rotation, not real distributed consensus). That is no longer the live topology — `aitbc1` (a separate, independently-administered host) is now a genuine second validator, not `aitbc3` as earlier text here said.

- One proposer produces a block at a time under round-robin `MultiValidatorPoA`; each block is written to that node's own SQLite `chain.db` and gossiped to the other.
- Live env on `hub.aitbc` (`/etc/aitbc/blockchain.env`): `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, `VALIDATOR_SET` = `0xEb9F1F86FA4D6cacb4d97E0766679E602977e95F` and `0x78046b9677c724FdF0af59c58439d67B210AD71b`, `MULTI_VALIDATOR_MIN_ATTESTATIONS=1`. Hub does not hold the private key for the second validator address anywhere on its filesystem — it lives only on `aitbc1`, which is the actual evidence this is now a real two-key, two-host setup and not co-located rotation.
- Confirmed live 2026-08-24 17:38 CEST: `hub.aitbc` and `aitbc1` report the identical head (height 13774, same block hash) via cross-node gossip (Redis broker on hub, consumed and re-broadcast to aitbc1's WebSocket gossip endpoint) — this is real block propagation between two independently-operated processes, not a single node talking to itself.
- **This is not yet BFT or fault-tolerant.** `PBFTConsensus` in `pbft.py` still is not wired into the block-production path; with a two-validator set and `MULTI_VALIDATOR_MIN_ATTESTATIONS=1`, either validator being unreachable can still stall the chain (see the incident below) — a third validator or an activated PBFT flow is still required for that property. `aitbc3` remains a passive follower and is not a validator in `VALIDATOR_SET`.
- **Operational-hygiene gap addressed, partially:** the current `VALIDATOR_SET` keypair was written into `/etc/aitbc/node.env` (hub) and `/etc/aitbc/blockchain.env` by hand during same-day incident recovery and still exists nowhere in git history. Per-node backups of `/etc/aitbc` are now stored under `/var/lib/aitbc/secrets/etc-aitbc-<timestamp>.tar.gz` (`0600`, full `/etc/aitbc` tree) on hub, aitbc1, and aitbc3 -- independently confirmed present, correctly permissioned, and matching each host's live filesystem exactly. **They are not interchangeable, though: each node's tarball only ever contains the key material that already lived on that node**, so the line above ("the backup on any of the three nodes can be used to restore it") was wrong and is corrected here:
  - Hub's tarball has the full keypair for validator `0xEb9F1F86FA4D6cacb4d97E0766679E602977e95F` in `node.env`, plus the genesis/settlement keys (`GENESIS_PRIVATE_KEY`, `GENESIS_WALLET_PRIVATE_KEY`, `ESCROW_RELEASE_PRIVATE_KEY`) -- none of which exist in any form on aitbc1 or aitbc3.
  - aitbc1's tarball has the private key for validator `0x78046b9677c724FdF0af59c58439d67B210AD71b`, but it lives in `aitbc-blockchain-node.env`, not `node.env`.
  - aitbc3's tarball has neither active validator's private key -- only their public addresses, via `blockchain.env`'s `VALIDATOR_SET`. Its own `aitbc-blockchain-node.env` instead holds an unrelated bridge-admin key, and `island-secrets.json` holds a separate set of five unrelated keys.

  Net effect: if hub is lost, its validator key and the genesis/settlement keys are unrecoverable from either other node -- there is no backup redundancy for them at all. If aitbc1 is lost, its validator key is likewise not recoverable elsewhere. Only aitbc3's backup is currently redundant with anything, and it isn't protecting a validator key. Also: `/var/lib/aitbc/secrets` itself is `755` (`750`+setgid group `aitbc` on aitbc3) rather than `700` -- the directory listing is world-readable even though the `0600` tarballs inside it are not.

## Multi-validator incident and key rotation — 2026-08-24

`MULTI_VALIDATOR_CONSENSUS_ENABLED` was flipped on with `aitbc1` as a genuinely independent second validator (not the earlier same-node experiment described below). The chain stalled: hub stuck at height 13490 and `aitbc1` at 13491, no new block on either host for 21+ minutes. A same-day restart of `aitbc-blockchain-node.service` on both hosts did not recover it. Root cause, code-confirmed: (1) hub's gossip backend is Redis, host-local only, while `aitbc1`'s is WebSocket, and `aitbc1`'s WS handshake to hub failed with HTTP 502 because hub's nginx `/rpc/` block was missing `Upgrade`/`Connection: upgrade` headers; (2) hub's periodic HTTP sync pulled from itself (`default_source=http://hub.aitbc.bubuit.net`), so it could structurally never learn `aitbc1`'s head; (3) the "Forcing heartbeat block" fallback logged unconditionally but was immediately vetoed by the proposer-turn gate on the node whose turn it wasn't, so it could not break the deadlock.

Recovery was performed by rotating the validator keypair to the current `VALIDATOR_SET` above and restarting the service (16:15–16:16 CEST); blocks resumed rotating cleanly shortly after. The gossip-backend mismatch and self-referential sync source that caused the stall were not fixed in code — the key rotation worked around the symptom, not the root cause, so the same class of stall can recur. Fixing it for real means: adding `Upgrade`/`Connection: upgrade` to hub's nginx `/rpc/` block, and pointing hub's periodic sync `default_source` at `aitbc1` instead of itself.
### Consensus stall recurrence and recovery — 2026-08-25

The same stall class recurred at height 14547/14548: `aitbc1` produced block 14548 but hub could not learn it because `hub.aitbc`'s `default_peer_rpc_url` was still `http://hub.aitbc.bubuit.net` (itself), and the `aitbc1` reverse proxy was not publicly reachable.

Recovery steps:

1. Updated `aitbc1`'s active nginx site (`aitbc-loadbalancer`) to proxy `/rpc` to the blockchain node on `127.0.0.1:8202` instead of the dead `8006` backend.
2. Enabled the reverse proxy on the `at1` Incus host for `node1.aitbc.bubuit.net`, terminating TLS and forwarding to the `aitbc1` container.
3. Set `hub.aitbc` `default_peer_rpc_url=https://node1.aitbc.bubuit.net` in `/etc/aitbc/blockchain.env`.
4. Restarted both `aitbc-blockchain-node` services. Hub pulled block 14548 from `aitbc1` and both heads converged at 14550.
5. Verified the chain advances every ~60s with round-robin proposers and each block carrying a valid cross-validator attestation in `block_metadata`.

Current live topology:

- `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`
- `VALIDATOR_SET` = `0xEb9F1F86FA4D6cacb4d97E0766679E602977e95F` (hub) and `0x78046b9677c724FdF0af59c58439d67B210AD71b` (`aitbc1`)
- `MULTI_VALIDATOR_MIN_ATTESTATIONS=1` (restored)
- Hub's `default_peer_rpc_url` = `https://node1.aitbc.bubuit.net`
- `aitbc1`'s `gossip_websocket_url` = `wss://hub.aitbc.bubuit.net/rpc/gossip/ws`

**Residual gaps:** `PBFTConsensus` is still not wired into block production, so a two-validator, `min-attestations=1` setup remains non-BFT and can stall if either validator is unreachable. `aitbc3` remains a passive follower, not a validator.


### Earlier, superseded: local multi-key validation — 2026-08-24 (morning)

Before the `aitbc1` deployment above, the hub was briefly activated with a two-validator `VALIDATOR_SET` (`ait1fe2d63...`, `ait1ffbda...`) with **both private keys held on the same hub node** — genuine round-robin proposer rotation with real per-block attestations, but not independent distributed consensus, since a single operator controlled both keys and `PBFTConsensus` was not wired into block production. This configuration was superseded within the same day by the real `aitbc1` deployment above and no longer reflects the live setup.

- The coordinator will not create an on-chain escrow without a buyer-supplied `ESCROW_LOCK` signature. The `PAYMENT_BUYER_PRIVATE_KEY` fallback has been removed: the hub no longer signs the buyer's half of the escrow. In the default operator flow a priced job must be submitted with `buyer_lock_signature`, `buyer_lock_nonce`, and `buyer_lock_fee` (via `POST /v1/jobs` or `POST /v1/payments`), or the payment remains `pending`/`skipped` and the job is not dispatched.

## Bridge multi-signature and Merkle enforcement — 2026-08-24

The cross-island bridge was activated with multi-signature and Merkle-proof enforcement on `hub.aitbc` and `aitbc3`.

Configuration (`/etc/aitbc/blockchain.env` on both nodes):

- `BRIDGE_RELEASE_ENABLED=true` was set during the validation window and then returned to `false`.
- `BRIDGE_MULTISIG_ENABLED=true`
- `BRIDGE_REQUIRE_MERKLE_PROOF=true`
- `BRIDGE_MULTISIG_THRESHOLD=2`
- `BRIDGE_MULTISIG_VALIDATORS=2`
- `BRIDGE_ADMIN_ADDRESSES=0xfe2d63fe87db282083b9159e5857cac788af9e03`
- `BRIDGE_SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net,ait-shop-island.aitbc.bubuit.net`

Validator set (`POST /rpc/bridge/validators/register`):

- Two bridge validators were registered on `ait-hub.aitbc.bubuit.net` for both the hub and the shop node:
  - `0xffbda3398a7b1e016fddd509834b07dc8f4034e6`
  - `0xfe2d63fe87db282083b9159e5857cac788af9e03`
- A 2-of-2 threshold was enforced for proof confirmation.

**Update, later the same day -- registration has not kept up with configuration:** `BRIDGE_MULTISIG_VALIDATORS` was subsequently raised to `3` in `/etc/aitbc/blockchain.env` on hub (confirmed live against the running process's own environment, not just the file on disk). `aitbc bridge security-status` reports `"validators_configured": 3, "validator_count": 2, "threshold": 2` -- the config change did not register a third validator. Direct query of `ait-hub.aitbc.bubuit.net`'s `bridge_validators` table confirms exactly the same two rows as the original activation above, `is_active=1`, nothing more. The second chain is worse off: `bridge_validators` on `ait-shop-island.aitbc.bubuit.net` has **zero rows** -- not a shortfall against a threshold, an empty validator set. A bridge confirmation requiring a validator attestation would fail outright on the island side today. Neither gap was previously written up anywhere in this repo; this paragraph is that write-up.

Live validation performed:

1. Lock 1 compute-second on `ait-hub.aitbc.bubuit.net` → target `ait-shop-island.aitbc.bubuit.net`.
2. Anchor the lock in a real block with a non-zero `bridge_state_root`.
3. Build a Merkle inclusion proof (`GET /rpc/bridge/transfer/{id}/proof`).
4. Store the source block header on the target node (`POST /rpc/bridge/block-headers`) with an admin signature.
5. Confirm the transfer on `ait-shop-island` (`POST /rpc/bridge/confirm`) with:
   - a valid confirmer signature,
   - the block proposer signature,
   - a validator attestation signature,
   - the Merkle inclusion proof.
6. Verify the recipient balance increased on `ait-shop-island`.

Negative cases validated:

- Confirm with an empty `merkle_proof` → rejected (`400 Invalid transfer proof`).
- Confirm with only the proposer signature (threshold 2 not met) → rejected (`400 Invalid transfer proof`).
- Confirm with an invalid confirmer signature → rejected (`403 Invalid confirmer signature`).
- `POST /rpc/bridge/block-headers` with an invalid admin signature → rejected (`403 Invalid or unauthorized bridge admin signature`).

Bugs found and fixed during validation:

- `BlockHeaderRequest` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py` was missing the `bridge_state_root` field, so ingested headers could not be used for Merkle proof verification. Added the field.
- `BridgeValidatorMixin.register_validator` did not update `registered_at` on re-registration, causing `_check_validator_set_freshness` to reject otherwise valid validator sets. Updated `registered_at` to the current UTC time on re-registration.

`BRIDGE_RELEASE_ENABLED=true` is live on `hub.aitbc` and `aitbc3`; `aitbc1` (validator/follower) still has `BRIDGE_RELEASE_ENABLED=false`. Multi-signature and Merkle-proof enforcement remain configured and active in the code path. Five bridge transfers remain pending; no `aitbc bridge confirm` is run while the chain was stalled, and confirmation requires explicit authorization only after consensus is verified robust and transaction-sealing prerequisites are met.

Honest assessment: the cryptographic enforcement was successfully activated and live-validated on real 1-compute-second hub→island transfers. The live cross-island bridge remains trust-minimised in design. The release path is enabled (`bridge_release_enabled=true`) on the hub/shop nodes, but the validator `aitbc1` is not yet configured for release, and the five pending transfers have not been confirmed pending a stable consensus and explicit authorization.


## Continuous integration

- **Gitea Actions runner active:** the runner at `gitea-runner` is active and pulls `.gitea/workflows/ci.yml` on push to `main`.
- **Workflow uses `make`:** `ci.yml` now invokes `make lint`, `make no-float-money`, `make typecheck`, `make test`, `make test-apps`, `make test-cli`, `make live-dry-run` and `make openapi-check`, so the gates match the `Makefile` and are reproducible both locally and on the runner.
- **Ruff is present but not yet gating:** `make lint` runs `ruff check . --exit-zero` to report the existing backlog without failing the build; the remaining findings must be fixed before ruff can be made a hard gate.
- **README badge fixed:** the old GitHub Actions badge (which pointed to a non-existent workflow) was replaced with a Gitea Actions badge.

## Economic loop verification

| Property | Verdict | Notes |
|---|---|---|
| The result is verifiable | **IMPROVED, NOT FULLY INDEPENDENT** | ZK and TEE gates now enforce stronger checks: `receipt_model` proves a committed deterministic model executed on committed input/output and `computation_correct` is only `True` when public signals match coordinator-derived values; TEE requires a registered enclave from an owner-locked allowlist and rejects `auto_attested` / unregistered / self-consistent quotes for release. The hardware-rooted half of TEE is deferred to release 2.0 until TEE-capable hardware is available (see [Deferred to v2.0](#deferred-to-v20--hardware-backed-tee)), so this row cannot improve before then. Both still depend on data supplied by the party being paid and do not establish an independent manufacturer/root-of-trust or semantic correctness of open-ended responses. |
| A bad provider loses something | **HOLDS, LIVE TESTED** | A 50% `fraud` slash was exercised end-to-end in a previous session (operator dispute `refund` -> on-chain `BOND_SLASH` tx -> coordinator metadata updated). The `BondSlashingService` nonce lookup was also corrected to use the blockchain RPC `/rpc/accounts/{address}` endpoint (`fbb1fa54d`). |
| Settlement is trust-minimised | **PARTIALLY HOLDS (live two-validator consensus recovered, not BFT)** | `MULTI_VALIDATOR_CONSENSUS_ENABLED=true` with a real second, independently-keyed host (`aitbc1`) is live and recovered from the 2026-08-25 stall after fixing `hub.aitbc`'s sync source to `https://node1.aitbc.bubuit.net` and exposing `aitbc1` through the `at1` reverse proxy. Blocks 14548+ advance every ~60s with round-robin proposers and valid cross-validator attestations in `block_metadata`. Independent live verification confirmed 15 consecutive blocks (14592–14612) with every proposer and attestation signature checking out and correctly attributed. `PBFTConsensus` is still not wired into production, and a two-validator, `min-attestations=1` setup can still stall if one validator is unreachable, so fault tolerance is not yet proven. Bridge multi-sig/Merkle enforcement is implemented and was live-tested; `bridge_release_enabled=true` on `hub.aitbc`/`aitbc3` but `aitbc1` (validator) still has `false`. Settlement is meaningfully less centralized than before, but not yet trust-minimised in a way this pass can certify as robust. |

## Deferred to v2.0 — hardware-backed TEE

**Decision (2026-09-03):** the TEE work is moved to **release 2.0** and held there
until TEE-capable hardware is available. Nothing is being reverted or removed — the
simulated path stays live and gated; only the hardware-rooted half is deferred.

**What is live today.** The confidential-compute path runs under `SIMULATED_TEE=1`.
Attestation, enclave registration, the owner-locked allowlist, confidential
messaging and the release gate are all implemented and live-validated: a released
escrow with `tee_status: verified` and `confidential: true`, plus a negative-case
matrix that rejects `auto_attested`, unregistered and self-consistent quotes.

**What is deferred.** Real SGX/TDX attestation — a quote signed by a chain that
terminates at a hardware root of trust, rather than one generated by the same party
that runs the workload. Without it the TEE gate raises the cost of lying but does
not establish an independent root of trust, which is exactly the caveat recorded in
the economic loop verdict below and in
`docs/scenarios/46_tee_confidential_jobs.md`.

**Blocking dependency.** No SGX/TDX-capable host in the fleet. All four validators
(`hub.aitbc`, `hub2.aitbc`, `node1`, `node2`) are ordinary VMs with no enclave
runtime — `aitbc tee launch` reports "no TEE runtime present". This is a hardware
procurement dependency, not an engineering backlog item, so it carries no date.

**Scope parked under v2.0.0:** v0.14.1 (Phase 1 — attestation, enclaves,
confidential messaging, TEE-backed data processing) and v0.14.2 (Phase 2 — ZK+TEE
dual verification, confidential transactions, healthcare/finance reference
enclaves).

**Re-entry criteria.** When hardware lands: obtain a real quote on that host, verify
the certificate chain to the vendor root, pin the measurement of a reproducibly
built enclave, and only then allow `tee_status: verified` to depend on a
hardware-signed quote rather than a simulated one. Until then the release gate must
keep treating simulated attestation as simulated.

## Closed design-cycle findings

| Finding | Root cause | Fix | Status |
|---|---|---|---|
| D1 | `POST /v1/jobs/{job_id}/reject` slashed the provider bond at the 50% fraud rate on the customer's word alone, before anyone had ruled — the unilateral power the acceptance window exists to withhold, pointed the other way. | Slash moved to the refund branch of the admin ruling, and only after the refund has actually settled. `test_bond_slashing.py` covers reject, refund ruling, release ruling, and a refund that fails to settle. | **Closed 2026-08-24** — commit `650b1bb89`, live on hub.aitbc. Live-proven the same day: reject → dispute → admin refund ruling → on-chain `BOND_SLASH` (jobs `4b1ddf2d…`, `17b801d7…`, tx `0x40c37dd0…` confirmed at block 13102). |
| D2 | G2 and G3 were enforced in code but inert in production. The visible half was `aitbc-miner-1` having no `wallet_address`; the hidden half was `POST /v1/payments` falling through the route security matrix to `AuthLevel.DENY` because `fnmatch("/v1/payments", "/v1/payments/*")` is `False`. | `MINER_WALLET_ADDRESS` set on `aitbc3` and registered in `capabilities`; bare `/v1/payments` (CLIENT) and `/v1/blocks` (CLIENT) entries added to `security_matrix.py`; `test_route_security_matrix.py` added. | **Closed 2026-08-24** — commit `870c109e9`, live on hub.aitbc. |
| D3 | G1 binds an offer's price and payee at submission, but dispatch still matched on miner capabilities alone — an offer-bound job could be dispatched to any capable miner, not the quoted provider. | `Job` gained `offer_id`/`provider_address`; `_satisfies_constraints` now consults the quoted offer's provider before falling through to capability checks; fails closed if `provider_address` is missing. | **Closed 2026-08-24** — commit `d80c0dcd5`, live on hub.aitbc. Live-tested against offer `ollama-llama3.2-3b`: the gate correctly refused 4 real dispatch attempts because no online miner held the quoted wallet — the safety property holds, but a full offer→escrow→dispatch→execute→payout cycle has not yet completed live. |
| D4 | `JobService.to_view` did one `session.get(JobPayment, ...)` per job, so `GET /v1/jobs`, `/v1/jobs/history`, and `POST /v1/miners/{id}/jobs` were N+1. | New `to_views()` batch-loads all `JobPayment` rows for the list in one `IN` query; the three list routers switched to it. | **Closed 2026-08-24** — commit `b2b52006c`, live on hub.aitbc. Shipped with zero test coverage; `apps/coordinator-api/tests/test_job_list_batch_loading.py` added same day to close that gap (functional parity with `to_view()`, per-job payment mapping, and a regression guard that fails if `to_views()` ever calls `session.get(JobPayment, ...)` again). |
| D5 | Blockchain router proxy handlers imported `coordinator_api.contexts.blockchain.config` (does not exist) instead of `....config`. The import is function-local, so `except NetworkError` did not catch `ImportError` and every proxy route answered 500. | Imports corrected in all six handlers; block routes now return 404 for missing heights and 502 for unreachable nodes; transaction route now calls `/rpc/transaction/{hash}`; `test_blockchain_block_routes.py` added. | **Closed 2026-08-24** — commit `39b510c`, live on hub.aitbc. |
| D6 | `[tool.pytest.ini_options].pythonpath` listed fourteen app source directories but not `apps/blockchain-node/src`, though `mypy_path` had it. `apps/blockchain-node/tests` was uncollectable from the repo root because its `conftest.py` imports `aitbc_chain` at module scope. | Added `apps/blockchain-node/src` to `pythonpath` in `pyproject.toml`. | **Closed 2026-08-24** — commit `0117c2d`. 709 blockchain-node tests now run and pass from the repo root; `test_blockchain_client_paths.py` now executes and validates coordinator URLs against the real node route table. Root `tests/` suite still aborts on 4 pre-existing collection errors. |

**TEE identity-pinning fix (2026-08-24, not previously in this table):** `QuoteGenerator` no longer derives a signing key from `enclave_id`, and the coordinator can pin verification to a registered `EnclaveIdentity` (commits `e464e662d`, `e74356605`, `6ef963746`, plus follow-up `8239e39ed` adding stable-key plumbing to `aitbc tee attest`/`keygen` and the miner). 38 tests pass live. Honestly incomplete: no live miner has been given a stable signing key yet (no `aitbc-miner.service` was running against the coordinator at fix time), so registry-pinning has no live caller — the mechanism is verified, not yet exercised by real production traffic.

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

**Limitation (updated 2026-08-24):** the accept-by-expiry branch above was exercised on live traffic first. The reject and operator dispute-ruling branch has since also been proven live and end-to-end, separately (jobs `4b1ddf2d…`, `17b801d7…`; on-chain `BOND_SLASH` tx `0x40c37dd0…` confirmed at block 13102) — see D1 in "Closed design-cycle findings" above. Both branches of the acceptance window are now live-verified, not test-only.

## Performance bond floor (2026-08-24)

The provider-bond surface previously allowed an active/locked bond of any amount to satisfy any high-value job. `JobService._satisfies_constraints` now reads `job.constraints.min_bond_amount` and rejects a miner whose `ProviderBond.amount` is below that floor. `is_provider_eligible` checks the same `min_amount` and falls back to the provider's own `required_amount` or a global `COORDINATOR_BOND_MIN_AMOUNT` default (1 AIT). The `POST /marketplace/providers/{id}/bonds` endpoint raises the supplied `required_amount` to the global floor and leaves under-funded bonds in `PENDING` until they are topped up. This makes the slash/stake mechanism economically meaningful: a job can no longer be taken by a provider whose posted bond is trivial compared with the job's value.

**Remaining gap:** the floor is a scalar amount, not a percentage of `payment_amount`, and it does not yet distinguish per-job risk classes. The ZK/TEE result-verification paths discussed in the 2026-08-24 analysis still require a non-vacuous ZK constraint and a deterministic decoding flag before they can be wired into the dispatch gate.

## ML inference ZK constraint (2026-08-24)

The deployed `ml_inference_verification` circuit in the coordinator tree used `verified <== 1 - (diff * diff)`, which computed a value but never constrained it. A non-zero difference could still make the equation true in the field, so the proof carried no correctness guarantee. The authoring tree in `apps/zk-circuits` had the correct `IsZero` implementation; it was promoted to the coordinator circuit directory, the r1cs/wasm and key material were regenerated, and `build-circuits.sh` now includes `ml_inference_verification` in its rebuild list. `zk_proofs.py` now decodes the per-circuit success public signal: for `ml_inference_verification` `public_signals[0]` must be `"1"`; for the training circuits the last public signal (`training_complete`) must be `"1"`. The new tests in `test_v2394_zk_circuit_constraints.py` cover a correct inference, a wrong inference with `verified == 0`, and a tampered public signal that breaks Groth16 verification.

**Closed (2026-08-25):** the `computation_correct` signal is wired into `_attach_zk_proof` and `PaymentService.release_payment`; the function fails closed before the blockchain client is invoked. The TEE decoding flag remains unconnected and is now the only remaining piece in this path.

## Open design-review gaps (2026-08-25)

These are the live-design verdicts that follow the economic-loop verification above.

| Gap | Verdict | Notes |
|---|---|---|
| G3 — dispatch/acceptance-gate wiring | **LIVE** | `computation_correct` is wired and loaded; `aitbc-coordinator-api` on `hub.aitbc` was restarted and `/proc/<pid>/environ` confirms `BRIDGE_RELEASE_ENABLED=true`. A false value stamps `zk_status="computation_incorrect"` and `release_payment` fails closed before touching the blockchain client. |
| G6 — settlement/trust-minimization | **PARTIALLY CLOSED (Option A live)** | MultiValidatorPoA now runs with four `0x`-format validators, all four private keys configured on `hub.aitbc`, `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, `PBFT_CONSENSUS_ENABLED=false`, and `MULTI_VALIDATOR_MIN_ATTESTATIONS=1`. Round-robin proposer rotation and cross-node sync were live-validated across blocks 1392-1399. A one-validator-down simulation (removed `0x43641ca248D38406c52CF1D6B235948DF27bfCF0`) kept the chain advancing with the remaining three validators; the removed validator was then restored and the chain resumed four-validator round-robin. `docs/operations/validator-key-rotation.md` and `docs/operations/validator-key-rotation.env.example` define a git-tracked template and a live-key-free runbook. The two-validator stall that recurred on 2026-08-25 was recovered by fixing `hub.aitbc`'s sync source to `https://node1.aitbc.bubuit.net` and exposing `aitbc1` through the `at1` reverse proxy. `PBFTConsensus` wiring and true BFT/fault tolerance remain open. |
| G5 — dispute-ruling paths | **RESIDUAL, LIVE-PROVEN** | Reject and dispute-ruling are now live-proven (not just test-covered), per the earlier correction — smaller residual gap than previously listed. |
| Bridge — multi-sig/Merkle enforcement | **ENABLED, VALIDATORS REGISTERED** | `BRIDGE_RELEASE_ENABLED=true` is live on `hub.aitbc`, `aitbc3`, and `aitbc1`. `aitbc bridge security-status` reports `release_enabled: true`, `multisig_enabled: true`, `require_merkle_proof: true`, `validators_configured: 2`, `validator_count: 2`, and `threshold: 2` on all three nodes. Two bridge validators are registered: the new hub proposer and the existing bridge-only key. No bridge transfers are pending after the 2026-08-27 reset; `bridge/health` shows `pending_transfer_count: 0` on all three nodes. T1/T9 were completed on 2026-08-31: `GENESIS_PRIVATE_KEY`, `GENESIS_WALLET_PRIVATE_KEY`, `BOND_SLASH_PRIVATE_KEY`, `ESCROW_RELEASE_PRIVATE_KEY`, and `PROPOSER_KEY` were replaced, balances were migrated, old bridge validators were inactivated, and logs/journal were cleared. |
| G8 — doc debt | **CLOSED** | The `--show-deprecated` visibility gate is removed: `cli/aitbc_cli/core/validated_group.py` and `surface_policy.py` are deleted, `main.py` no longer filters the help surface, and canonical top-level groups are visible. `aitbc market` and `aitbc governance` are canonical; `aitbc marketplace` and `aitbc operations` (including `operations marketplace` and `operations governance`) are deprecated. `test_cli_surface.py` covers the visibility and deprecation behavior. Legacy `marketplace` subcommands remain invocable for backward compatibility. |

## Consensus recovery and bridge-validation hold (2026-08-25)

Independent verification confirmed the bridge release flag is live and the
two-validator chain recovered:

- `hub.aitbc` `/proc/<pid>/environ` for `aitbc-coordinator-api` reads
  `BRIDGE_RELEASE_ENABLED=true` after an explicit post-config-edit restart.
- The `default_peer_rpc_url` on `hub.aitbc` was changed to
  `https://node1.aitbc.bubuit.net` and the `aitbc1` reverse proxy was enabled on
  the `at1` Incus host.
- After restarting both blockchain nodes, hub pulled block 14548 from `aitbc1`
  and the chain resumed advancing with round-robin proposers.
- `MULTI_VALIDATOR_MIN_ATTESTATIONS=1` was restored. All three live nodes
  (`hub.aitbc`, `aitbc1`, `aitbc3`) now report the same head height and hash
  and every produced block carries a valid cross-validator attestation in
  `block_metadata`. Independent live verification ran `verify_block_signature()`
  against 15 consecutive blocks (heights 14592–14612) and confirmed every
  proposer signature and every attestation signature, with each attestation
  correctly attributed to the non-proposing validator.

`confirm_transfer` still credits the recipient synchronously and marks the
source `CrossChainTransfer` `completed` without checking that a `BRIDGE_RELEASE`
transaction is sealed in a produced block. The 5 pending transfers remain
pending; `aitbc bridge confirm` is not run without explicit authorization. The
larger root cause — `PBFTConsensus` not wired into production and a
`min-attestations=1` two-validator set being non-BFT — is still open.

## T5 / G6 multi-validator fault-tolerance validation — 2026-08-31

Option A (pragmatic 4-validator multi-key PoA) was activated and live-validated on `hub.aitbc`, `aitbc1`, and `aitbc3`.

### Validator set

- Preserved proposer / validator-1: `0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76` (also the bridge admin / proposer).
- Generated three new extra validators on `hub.aitbc`:
  - `0x241D3e44d42b6d4c270d0231780913f14386d90C`
  - `0x65568673B3cf7D614Edd97a94b3Ff757246dAe22`
  - `0x43641ca248D38406c52CF1D6B235948DF27bfCF0`
- `VALIDATOR_SET` (public) and `VALIDATOR_KEYS` (private) updated on `hub.aitbc`.
- Followers `aitbc1` and `aitbc3` received the public `VALIDATOR_SET` and `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`; `VALIDATOR_KEYS={}` and `PBFT_CONSENSUS_ENABLED=false`.

### Configuration changes

- `max_empty_block_interval=60` on all three nodes so empty blocks produce every 60 s during the test.
- `AUTO_SYNC_THRESHOLD=0` on `aitbc1` and `aitbc3` so the SyncManager bulk-pulls for any positive height gap (previously small gaps were only handled by gossip/subscription, which missed blocks on restart).
- `MULTI_VALIDATOR_MIN_ATTESTATIONS=1` (proposer + one attestation for the 4-validator set).

### Validation results

- Round-robin block production observed for heights 1392–1399 with four distinct proposers in order:
  - 1392: `0x241D...`
  - 1393: `0x6556...`
  - 1394: `0xab07...`
  - 1395: `0x241D...`
  - 1396: `0x241D...` (same modulo index as 1392; not a bug)
  - 1397: `0x4364...`
  - 1398: `0x6556...`
  - 1399: `0xab07...`
- All three nodes converged to the same head height and hash at each check.

### One-validator-down simulation

1. Removed validator `0x43641ca248D38406c52CF1D6B235948DF27bfCF0` from the active set and restarted `aitbc-blockchain-node` on `hub.aitbc`.
2. Chain continued producing blocks with the remaining three validators.
3. Restored the removed validator from a backup and restarted.
4. Chain resumed four-validator round-robin production.

### Operational issues found

- `aitbc-blockchain-rpc.service` can hang in `deactivating (stop-sigterm)`. During the test it failed to stop and the RPC port (8202) was not re-bound after `systemctl restart aitbc-blockchain-node.service`; the old `uvicorn aitbc_chain.app:app` process had to be killed with `kill -9` before the service could restart. A stale `aitbc_chain.main` process from 2026-08-27 (PIDs 612930/612932) was also still running and was killed.
- Follower `aitbc1` initially missed the gossip push for block 1389 and, with the default `AUTO_SYNC_THRESHOLD=10`, did not bulk-pull small gaps, so it stayed one block behind until `AUTO_SYNC_THRESHOLD=0` was set. This suggests the SyncManager should bulk-pull any positive gap by default when no recent gossip block is received.

### Remaining open work

- `PBFTConsensus` is still not wired into production. The live setup is multi-key PoA, not BFT; a 4-validator `f=1` PBFT deployment would require four independent validator hosts and `MULTI_VALIDATOR_MIN_ATTESTATIONS=3` (or a full PBFT round). This remains an open architecture item.

## 2026-09-02 validation — five-node mesh, rolling restarts, and gossip package refactor

### Hosts and roles

The live network was clarified and reconfigured as five distinct hosts:

- `hub.aitbc` — validator, IP `192.168.100.10`
- `hub2.aitbc` — validator, IP `10.177.61.28`
- `node1.aitbc.bubuit.net` (formerly `aitbc1`) — validator, IP `10.1.223.40`
- `node2.aitbc.bubuit.net` (formerly `aitbc3`) — validator, IP `10.1.223.136`
- `node0.aitbc.bubuit.net` — follower, IP `10.1.223.93`

The four validators form a 3-of-4 quorum. `node0` does not produce blocks (`enable_block_production=false`) and participates only as a follower via the mesh gossip backend.

### Work completed

- **Bridge-monitor efficiency:** `apps/wallet/src/wallet_app/bridge/bridge_monitor.py` now batches bridge-block fetches and tracks the last scanned block, and `aitbc/network/http_pool.py` provides a shared `SharedHttpClient` pool. This eliminated the repeated Infura/Sepolia requests that were hitting the wallet node.
- **Proposer-rotation fix:** `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` now rotates the proposer when the scheduled one is unavailable (`cb8cfbf25e`).
- **Human-readable transaction-query logs:** `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` was updated (`c6d71d4fb7`).
- **Nginx worker and WebSocket fixes:**
  - Added `worker_rlimit_nofile 8192`, `worker_connections 4096`, and `real_ip` config where applicable.
  - Fixed `node0` nginx: renamed the active server block from the dead `aitbc.bubuit.net` to `node0.aitbc.bubuit.net`, corrected the `/rpc/` upstream from `8006` to `8202`, and added WebSocket upgrade headers to both `/rpc/` locations.
  - Verified `wss://node0.aitbc.bubuit.net/rpc/gossip/ws` returns `101 Switching Protocols` through nginx.
- **Node0 recovery:** `node0` was on old commit `33a0f8a28` and did not support `GOSSIP_BACKEND=mesh`. It was pulled to current `main`, its chain database was backed up and reset, `GOSSIP_BACKEND=mesh` was restored, and it resynced to the validator head. Its chain now follows the live network.
- **Node identity / DNS:**
  - `aitbc3` is now `node2.aitbc.bubuit.net`; peer URLs and nginx configs were updated.
  - `node0` is a separate fifth machine, not the former `aitbc3`.
- **Gossip package refactor:** the monolithic `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` was split into a package:
  - `gossip/backends/base.py`, `in_memory.py`, `broadcast.py`, `websocket.py`, `mesh.py`
  - `gossip/_internal.py` for shared serialization/metrics helpers
  - thin `gossip/broker.py` and `gossip/__init__.py` preserving the public API
  - 54 gossip tests passed on a `node2` temp checkout; Ruff was clean.

### Rolling pull/restart results

A rolling `git pull` and restart was performed across `node0`, `node2`, `hub.aitbc`, `hub2.aitbc`, and `node1` (in that order) to load the new gossip package (`a620e1334`) without a chain stall.

| Node | From commit | To commit | Services active | Final height |
|---|---|---|---|---|
| `node0` | `c6d71d4fb7` | `a620e1334` | `aitbc-blockchain-node`, `aitbc-blockchain-rpc` | 3183 |
| `node2` | `cb8cfbf25e` | `a620e1334` | both | 3183 |
| `hub.aitbc` | `c6d71d4fb7` | `a620e1334` | both | 3183 |
| `hub2.aitbc` | `cb8cfbf25e` | `a620e1334` | both | 3183 |
| `node1` | `cb8cfbf25e` | `a620e1334` | both | 3183 |

All five nodes converged at height **3183** and continued producing new blocks. No `Unsupported gossip backend`, `ModuleNotFoundError`, or gossip WebSocket 404 errors were observed after the restarts.

### Consensus and fault-tolerance assessment

- Four validators, 3-of-4 quorum: one validator failure is tolerated; two simultaneous validator failures are not guaranteed to make progress.
- A service-level restart of any single validator is safe; the remaining three keep producing.
- A **host-level outage** (RPC and gossip disappearing together) is still untested and is an honest gap.
- A proposer that dies **after collecting prepares but before commit** still needs a genuine PBFT NEW-VIEW protocol carrying prepared certificates. This is not implemented and remains a liveness limitation.
- `PBFTConsensus` is still not wired into production block production; the live network is multi-key PoA, not full PBFT.

### Open items

- Implement genuine PBFT NEW-VIEW with prepared certificates.
- Run a host-level validator outage test (network partition / power-off, not just `systemctl restart`).
- Investigate and clean historical `chain.db.pre*` and `predeploy` backups.
- Continue watching the stale node1 worker process (`aitbc_chain.main` / `uvicorn` hanging in `deactivating`).
- Consider reducing the 300-second round timeout after safety testing.
- Push the `docs/releases/STATUS.md` updates to `main` and, separately, update `docs/releases/v0.25/v0.25.2_change.log` on the shop node.
