# v0.7.1 Bridge Security Layer — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Bridge Security Layer — Multi-Sig Validation, Validator Set Registry, Block Header Signatures

**Goal**: Add the security-critical multi-signature layer to the cross-chain bridge. Replace the current "accepts any valid secp256k1 signer" proof verification (`_verify_proposer_signature` in `cross_chain/bridge.py:477-523`) with proper M-of-N threshold signature validation against a per-chain validator set. Add block header signatures so proposers are cryptographically bound to the blocks they produce. Add CLI commands for security status and validator registration.

> **Rescope from original change.log**: The original v0.7.1 change.log bundled multi-sig + cross-chain sig verification + time-locks + audit trail into one release. This is too much for a single release cycle. Per the release-planning analysis, v0.7.1 is now scoped to **multi-sig core only**:
> - ✅ v0.7.1: Validator set registry, threshold sigs, block header signing, multi-sig lock/confirm, CLI, threat model
> - ➡️ v0.7.2: Time-locks (value-tiered), audit trail (cryptographic chaining), light client verification, Merkle proof verification, finality thresholds, oracle stub
>
> This rescoping aligns with the existing v0.7.2 change.log which already covers Merkle proof verification + block header verification + validator set tracking. Moving validator set tracking to v0.7.1 (where it's needed for multi-sig) and keeping Merkle proof verification in v0.7.2 (where it's needed for release path unfencing) gives a cleaner separation: v0.7.1 establishes the trust foundation (who are validators, how do they sign), v0.7.2 builds the verification layer on top.

> **No external security audit**: All development is in-house. The change.log's "External security audit required before merge" (line 15) and success criterion "External security audit passed" (line 252) are **dropped**. Internal code review + comprehensive test coverage replaces the external audit gate.

> **Scope constraint**: This release does NOT unfence the bridge release path. `BRIDGE_RELEASE_ENABLED=false` (config.py:285-290) remains in place. The confirm/release path stays gated until v0.7.2 completes Merkle proof verification. v0.7.1 adds multi-sig validation to the proof verification path, but the release fence is a separate safety layer that stays until cryptographic proof verification (not just signature verification) is complete.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) — Bridge Basics. v0.7.0 Agent A (shared bridge SDK) is ✅ committed (`35b029852`). v0.7.0 Agent B (RPC endpoints, CLI, monitoring, tests) exists in the working tree but is **uncommitted** — Agent B must commit v0.7.0 work before starting v0.7.1. [v0.5.16](../v0.5.16/change.log) ✅ (bridge proof hardening + release fence).

> **Risk**: Medium-High. This release touches consensus-critical code (block header signing) and the bridge proof verification path. The `BRIDGE_RELEASE_ENABLED=false` fence prevents unauthorized fund release even if multi-sig has bugs. Block header signature changes are backward-compatible (new optional field, old blocks have empty signature).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (bridge types extension, multi-sig utilities, validator set registry, BridgeClient extensions, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (threat model, config, block header signatures, validator table, RPC endpoints, multi-sig bridge upgrade, CLI, integration tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation-2026-06-29)
- [Already Fixed / Exists](#already-fixed--exists-verified--no-work-needed)
- [Architecture](#architecture-bridge-security-v071)
- [Task Split Overview](#task-split-overview)
- [Phase 0 - Threat Model](#phase-0--threat-model-prerequisite)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Extend Bridge Types](./agent-a.md#a1-extend-bridge-types)
- [Multi-Sig Utilities](./agent-a.md#a2-multi-sig-utilities)
- [Validator Set Registry](./agent-a.md#a3-validator-set-registry)
- [BridgeClient Extensions + Unit Tests](./agent-a.md#a4-bridgeclient-extensions--unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Threat Model Document](./agent-b.md#b1-threat-model-document)
- [Bridge Security Config + Constants](./agent-b.md#b2-bridge-security-config--constants)
- [Block Header Signatures](./agent-b.md#b3-block-header-signatures)
- [BridgeValidator SQLModel Table](./agent-b.md#b4-bridgevalidator-sqlmodel-table)
- [Validator RPC Endpoints](./agent-b.md#b5-validator-rpc-endpoints)
- [Upgrade Bridge Proof Verification to Multi-Sig](./agent-b.md#b6-upgrade-bridge-proof-verification-to-multi-sig)
- [CLI Commands](./agent-b.md#b7-cli-commands)
- [Integration Tests](./agent-b.md#b8-integration-tests)

---

## Status Baseline — Verified Code Targets (from subagent investigation, 2026-06-29)

| Component | Location | Current State | v0.7.1 Target |
|-----------|----------|---------------|---------------|
| **Proposer signature verification** | `cross_chain/bridge.py:477-523` | ⚠️ PARTIAL — `_verify_proposer_signature` recovers signer address but accepts ANY valid secp256k1 key. No proposer-set membership check. Comment (line 485-489) says "deferred to v0.7.2". | Replace with M-of-N threshold verification against validator set. Multiple validator signatures required. |
| **Bridge proof structure** | `cross_chain/bridge.py:38-55`, `aitbc/bridge/types.py:33-48` | ✅ EXISTS — single `proposer_signature: str` field | Add `validator_signatures: list[str]` field (backward-compatible — old proofs with single proposer_signature still work) |
| **Processed proofs tracking** | `cross_chain/bridge.py:73` | ⚠️ IN-MEMORY — `self._processed_proofs: set[str] = set()` | No change in v0.7.1 (persistent audit trail deferred to v0.7.2) |
| **Block header model** | `base_models.py:25-76` | ⚠️ NO SIGNATURE — `proposer: str` field is address string only, no `signature` field | Add `signature: str = ""` field (optional, backward-compatible). PoA signs block headers on proposal. |
| **PoA consensus** | `consensus/poa.py:82-97` | ✅ EXISTS — single proposer from config (`PoAProposer`), tracks `_last_proposer_id` | Add block header signing on proposal + signature verification on validation |
| **Multi-validator PoA** | `consensus/multi_validator_poa.py` (293 lines) | ⚠️ DEAD CODE — gated behind `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, requires security review. Has `Validator` dataclass, `add_validator`, `remove_validator`, `select_proposer` (round-robin). | Do NOT activate. v0.7.1 builds a separate bridge validator set (not consensus validator set). MultiValidatorPoA activation is a separate future release. |
| **Validator set management** | — | ❌ NONE for bridge. Staking has `register_validator` (`economics/staking.py:180`) but for staking economics, not bridge. | Create bridge validator set registry: SQLModel table + in-memory cache + RPC endpoints |
| **Threshold signature utilities** | `aitbc/crypto/crypto.py` | ❌ NONE — only single-signer `recover_signer()`, `verify_signature()`. No threshold/BLS/aggregation. | Add secp256k1 M-of-N threshold verification (collect M sigs, verify each against validator set, check threshold). No BLS — keep it simple, no new dependencies. |
| **Time-locks** | — | ❌ NONE for bridge. Exist for guardian contracts (`test_guardian_contract.py`), escrow (`EscrowService.sol`), governance (`AgentDAO.sol`). | DEFERRED to v0.7.2 |
| **Audit trail** | — | ❌ NONE for bridge. `_processed_proofs` is in-memory only. Other audit logs exist: `AgentAuditLog` (coordinator-api), `PricingAuditLog` (trading), `AuditLogger` (CLI). | DEFERRED to v0.7.2 |
| **Light client** | — | ❌ NONE — only doc references in release plans | DEFERRED to v0.7.2 |
| **Threat model** | `docs/security/threat-model.md` (174 lines) | ⚠️ GENERAL — covers smart contracts, ZK, API, network, economic attacks. Does NOT cover bridge-specific threats (bridge mints, cross-chain replay, validator set attacks, proof forgery). | Create bridge-specific threat model addendum covering bridge attack surfaces |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` (186 lines) | ✅ 7 commands exist (lock, confirm, unlock, status, pending, balance, health) — from v0.7.0 Agent B | Add `security-status` and `register-validator` subcommands |
| **Bridge release fence** | `config.py:285-290`, `rpc/bridge.py:105-110` | ✅ EXISTS — `bridge_release_enabled: bool = False`, gates `/bridge/confirm` and `/bridge/batch/confirm` | No change — fence stays until v0.7.2 |
| **Bridge RPC endpoints** | `rpc/bridge.py` (405 lines) | ✅ 9 endpoints exist (lock, confirm, transfer, pending, unlock, balance, health, batch/lock, batch/confirm) — from v0.7.0 | Add `POST /bridge/validators/register` and `GET /bridge/validators/{chain_id}` endpoints |
| **Shared bridge SDK** | `aitbc/bridge/` (4 files) | ✅ EXISTS — BridgeClient, types, proof utilities (v0.7.0 Agent A, committed `35b029852`) | Extend types with ValidatorInfo, ValidatorSet, ThresholdProof. Add multisig.py module. |
| **Crypto utilities** | `aitbc/crypto/crypto.py` (226 lines) | ✅ EXISTS — `recover_signer()`, `verify_signature()`, `keccak256_hash()` | Reuse `recover_signer()` for threshold sig verification. No new crypto dependencies. |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Bridge core exists** — `CrossChainBridge` with lock/confirm/transfer/pending/unlock flow
2. ✅ **9 bridge RPC endpoints exist** — lock, confirm, transfer, pending, unlock, balance, health, batch/lock, batch/confirm (v0.7.0 Agent B)
3. ✅ **Bridge release fence active** — `BRIDGE_RELEASE_ENABLED=false` gates confirm/batch_confirm
4. ✅ **Shared bridge SDK exists** — `aitbc/bridge/` with BridgeClient, types, proof utilities (v0.7.0 Agent A)
5. ✅ **Single-signer secp256k1 utilities exist** — `recover_signer()`, `verify_signature()` in `aitbc/crypto/crypto.py`
6. ✅ **7 CLI bridge commands exist** — lock, confirm, unlock, status, pending, balance, health (v0.7.0 Agent B)
7. ✅ **General threat model exists** — `docs/security/threat-model.md` (174 lines, no bridge coverage)
8. ✅ **BridgeStatus enum includes REFUNDED** — already has the `refunded` status for unlock/refund flow

---

## Architecture: Bridge Security (v0.7.1)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — EXTEND + NEW MODULES)                   │
│                                                                      │
│  Bridge types (A1 — EXTEND types.py):                                │
│    ValidatorInfo, ValidatorSet, ThresholdProof                       │
│    BridgeProof gains validator_signatures: list[str]                 │
│                                                                      │
│  Multi-sig utilities (A2 — NEW multisig.py):                         │
│    verify_threshold_signatures(proof, validator_set, threshold)      │
│    recover_all_signers(message_data, signatures)                     │
│    check_threshold(signers, validator_set, threshold)                │
│                                                                      │
│  Validator set utilities (A3 — NEW validators.py):                   │
│    ValidatorSetRegistry — in-memory cache with epoch tracking        │
│    get_validator_set(chain_id, epoch)                                │
│    is_member(address, validator_set)                                 │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge security-status │    │                                      │
│  bridge register-       │    │  Block header signing (B3):          │
│    validator            │    │    Block.signature field (NEW)       │
│                         │    │    PoA signs on propose              │
│  Uses BridgeClient (A1) │    │    PoA verifies on validate          │
│  + new SDK methods      │    │                                      │
│                         │    │  Validator set table (B4):           │
│                         │    │    BridgeValidator SQLModel (NEW)    │
│                         │    │    fields: chain_id, address,        │
│                         │    │    pubkey, epoch, is_active          │
│                         │    │                                      │
│                         │    │  Validator RPC (B5):                 │
│                         │    │    POST /bridge/validators/register  │
│                         │    │    GET  /bridge/validators/{chain}   │
│                         │    │                                      │
│                         │    │  Multi-sig bridge (B6):              │
│                         │    │    _verify_proposer_signature →      │
│                         │    │    _verify_threshold_signatures      │
│                         │    │    Uses A2 + A3 + B4 validator set   │
│                         │    │                                      │
│                         │    │  Config (B2):                        │
│                         │    │    bridge_multisig_enabled           │
│                         │    │    bridge_multisig_threshold         │
│                         │    │    bridge_multisig_validators        │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
│                         │    │    multi-sig, validator set,         │
│                         │    │    block signing, CLI                │
└─────────────────────────┘    └──────────────────────────────────────┘

Phase 0 (prerequisite — either agent):
  docs/architecture/bridge-threat-model.md
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/bridge/types.py` (extend), `aitbc/bridge/multisig.py` (new), `aitbc/bridge/validators.py` (new), `aitbc/bridge/__init__.py` (extend), `aitbc/bridge/client.py` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `docs/architecture/bridge-threat-model.md` (new), `apps/blockchain-node/src/aitbc_chain/config.py`, `base_models.py`, `consensus/poa.py`, `cross_chain/bridge.py`, `rpc/bridge.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `aitbc/constants.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns `aitbc/bridge/` package (extends v0.7.0 work). Agent B owns all `apps/`, `cli/`, and `aitbc/constants.py`. Agent B consumes Agent A's `ValidatorSetRegistry`, `verify_threshold_signatures`, and extended types. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B6 multi-sig bridge depends on A2+A3). B1 (config), B2 (threat model), B3 (block header signing) can proceed in parallel with Agent A.

---

## Phase 0 — Threat Model (Prerequisite)

**Either agent can write this first. Recommended: Agent B (owns bridge implementation).**

Create `docs/architecture/bridge-threat-model.md` — bridge-specific threat model addendum to the existing `docs/security/threat-model.md` (which covers general platform threats but NOT bridge-specific ones).

Must cover:
- **Attack surfaces**: bridge RPC endpoints, proof verification path, validator set registry, block header signatures, multi-sig aggregation
- **Attack vectors**:
  - Forged proofs (attacker fabricates lock proof without actual lock) — mitigated by multi-sig + block anchoring
  - Signature replay (reuse valid proof on different chain/transfer) — mitigated by chain_id in proof + `_processed_proofs` tracking
  - Validator key compromise (attacker steals validator private key) — mitigated by M-of-N threshold (single key compromise insufficient)
  - Validator set rotation attack (exploit transition between validator sets) — mitigated by epoch tracking + grace period
  - Below-threshold attack (submit proof with insufficient signatures) — mitigated by threshold check
  - Block header forgery (fake block header to anchor proof) — mitigated by block header signatures (v0.7.1) + Merkle proof verification (v0.7.2)
- **Mitigations**: M-of-N threshold sigs, validator set registry, block header signing, release fence (until v0.7.2)
- **Residual risk** (after v0.7.1, before v0.7.2):
  - Proof verification is still signature-only (no Merkle proof) — a colluding validator majority can forge proofs
  - `_processed_proofs` is in-memory — replay possible after node restart (audit trail deferred to v0.7.2)
  - No time-locks — large transfers have no challenge period (deferred to v0.7.2)
  - Release fence (`BRIDGE_RELEASE_ENABLED=false`) is the primary protection until v0.7.2

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.1 — Bridge Security Layer
