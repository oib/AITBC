# v0.7.2 Bridge Verification — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Bridge Verification — In-Process Cryptographic Proof Verification, Block Header Verification, Validator Set Tracking, Oracle Client Stub

**Goal**: Replace the current trivially forgeable bridge proof validation (`_validate_proof` in `cross_chain/bridge.py:399-475`, which only checks field equality + signature format) with cryptographic Merkle proof verification using the existing `merkle_patricia_trie.verify_proof()`. Verify block header proposer signatures against the v0.7.1 validator set registry. Track block finality per chain. Include an abstract oracle client interface for future external oracle integration.

> **Rescope from original change.log**: The original v0.7.2 plan assumed external oracle infrastructure (`oracle1.aitbc.bubuit.net`, `oracle2.aitbc.bubuit.net`) that **does not exist**. No oracle client code, light client library, or deployed oracle network are present. v0.7.2 is rescoped to use **in-process cryptographic verification** with existing Merkle Patricia Trie infrastructure (`merkle_patricia_trie.verify_proof`). External oracle integration is deferred to v0.8.x or v0.9.x. A stub oracle client interface is included to allow future integration without breaking changes.

> **Hard prerequisite**: v0.7.1 must be **complete and committed** before v0.7.2 implementation starts. v0.7.2's core verification depends on:
> - v0.7.1 Agent A: `ValidatorSetRegistry`, `verify_threshold_signatures`, `ValidatorSet`/`ValidatorInfo` types (✅ committed `1fcf1e829`)
> - v0.7.1 Agent B: `BridgeValidator` SQLModel table, block header `signature` field, `_verify_threshold_signatures` in bridge.py, validator RPC endpoints (🔴 NOT STARTED — v0.7.0 Agent B is still uncommitted)
>
> **Do NOT start v0.7.2 implementation until v0.7.1 Agent B is complete.** This AGENTS.md is a planning document only.

> **Scope constraint**: This release **unfences** the bridge release path. `BRIDGE_RELEASE_ENABLED=false` (config.py:290) is flipped to `true` after Merkle proof verification is operational and tested. This is the single most security-critical change in the v0.7.x series — the fence has been in place since v0.5.16 to prevent unauthorized minting.

> **No external security audit**: All development is in-house. Internal code review + comprehensive test coverage replaces the external audit gate (same as v0.7.1).

> **Risk**: High. This release unfences the bridge release path. The Merkle proof verification must be correct — a bug here means an attacker can mint tokens on the destination chain without a real lock on the source chain. The existing `merkle_patricia_trie.verify_proof` is tested but has not been used in the bridge path before.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅ (Agent A committed), [v0.7.1](../v0.7.1/change.log) (Agent A ✅ committed, Agent B 🔴 not started), [v0.5.16](../v0.5.16/change.log) ✅ (bridge proof hardening + release fence).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (verification types, oracle interface, verification utilities, BridgeClient extensions, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (verification config, block header storage, Merkle proof verification, block header verification, finality tracking, validator epoch tracking, unfence release path, CLI, integration tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Already Fixed / Exists](#already-fixed--exists-verified--no-work-needed)
- [Hard Blockers](#hard-blockers-must-be-resolved-before-v072-implementation)
- [Architecture](#architecture-bridge-verification-v072)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Extend Bridge Types](./agent-a.md#a1-extend-bridge-types)
- [Oracle Client Interface](./agent-a.md#a2-oracle-client-interface)
- [Verification Utilities](./agent-a.md#a3-verification-utilities)
- [BridgeClient Extensions + Unit Tests](./agent-a.md#a4-bridgeclient-extensions--unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Bridge Verification Config + Constants](./agent-b.md#b1-bridge-verification-config--constants)
- [Remote Block Header Storage](./agent-b.md#b2-remote-block-header-storage)
- [Merkle Proof Verification](./agent-b.md#b3-merkle-proof-verification)
- [Block Header Signature Verification](./agent-b.md#b4-block-header-signature-verification)
- [Finality Tracking](./agent-b.md#b5-finality-tracking)
- [Validator Set Epoch Tracking](./agent-b.md#b6-validator-set-epoch-tracking)
- [Unfence Release Path + CLI](./agent-b.md#b7-unfence-release-path--cli)
- [Integration Tests](./agent-b.md#b8-integration-tests)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.2 Target |
|-----------|----------|---------------|---------------|
| **Merkle Patricia Trie** | `state/merkle_patricia_trie.py:73-121` | ✅ Complete — `verify_proof(key, value, proof)` + `get_proof(key)` + `get_root()` | Use in bridge `_validate_proof` to verify lock event inclusion against source chain state root |
| **State root computation** | `state/merkle_patricia_trie.py:402-419` | ✅ Complete — `StateManager.compute_state_root(accounts)` | No change — used to compute/verify state roots |
| **State root utils** | `state/state_root_utils.py:17-34` | ✅ Complete — `compute_state_root_full()`, `compute_state_root_incremental()` | No change — bridge uses these to get source chain state root |
| **Bridge proof validation** | `cross_chain/bridge.py:399-475` | ⚠️ PARTIAL — field equality + proposer sig format + block anchor + chain_id. No Merkle proof, no proposer-set membership. | Replace with Merkle proof verification against state root + block header signature verification + finality check |
| **Proposer signature verification** | `cross_chain/bridge.py:477-523` | ⚠️ Accepts ANY valid secp256k1 signer (comment lines 514-517). | v0.7.1 replaces with threshold sig verification. v0.7.2 adds Merkle proof on top. |
| **Block header model** | `base_models.py:25-76` | ⚠️ NO SIGNATURE — `proposer: str` is address only, `state_root: str \| None` exists. No `signature` field. | v0.7.1 B3 adds `signature: str = ""`. v0.7.2 uses it for block header verification. |
| **Remote chain block header storage** | — | ❌ NONE — `Block` table only stores local chain blocks. No `BridgeBlockHeader` or equivalent. | Create `BridgeBlockHeader` SQLModel table: chain_id, height, hash, proposer, state_root, signature, timestamp, finality_confirmed |
| **Finality tracking** | — | ❌ NONE — no confirmation counting, no finality threshold config. | Add finality tracking: count confirmations per chain, configurable threshold, reject non-finalized for large transfers |
| **Finality config** | `config.py` | ❌ NONE — no `bridge_verification_mode`, `bridge_min_confirmations`, `bridge_finality_blocks`, `bridge_large_transfer_threshold`. | Add all four config fields with env var defaults |
| **Validator set tracking (DB)** | — | ❌ NONE — v0.7.1 Agent A has in-memory `ValidatorSetRegistry`, but no SQLModel persistence. | v0.7.1 Agent B creates `BridgeValidator` table. v0.7.2 adds epoch tracking + grace period logic. |
| **Oracle client** | — | ❌ NONE — no abstract interface, no in-process verifier, no external stub. | Create `OracleClient` ABC + `InProcessVerifier` + `ExternalOracleClient` stub |
| **Bridge release fence** | `config.py:290`, `rpc/bridge.py:105` | ✅ EXISTS — `bridge_release_enabled: bool = False` gates confirm/batch_confirm | **UNFENCE** after Merkle proof verification is operational + tested. Flip default to `true`. |
| **Shared bridge SDK** | `aitbc/bridge/` (6 files) | ✅ EXISTS — BridgeClient, types, proof, multisig, validators (v0.7.0 + v0.7.1 Agent A) | Extend with oracle.py, verification.py, finality types |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` | ✅ 9 commands exist (v0.7.0 Agent B) + 2 security commands (v0.7.1 Agent B) | Add `oracle-status` command |
| **Threat model** | `docs/architecture/bridge-threat-model.md` | ⚠️ v0.7.1 B1 creates this. If v0.7.1 Agent B hasn't completed, this is missing. | Extend with v0.7.2-specific threats (Merkle proof forgery, finality bypass, state root manipulation) |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Merkle Patricia Trie** — `verify_proof(key, value, proof)`, `get_proof(key)`, `get_root()` all implemented and tested
2. ✅ **State root computation** — `StateManager.compute_state_root()` + `compute_state_root_full/incremental` utilities
3. ✅ **Block model has `state_root` field** — `Block.state_root: str | None` at line 41
4. ✅ **Bridge release fence active** — `BRIDGE_RELEASE_ENABLED=false` prevents unauthorized minting
5. ✅ **Shared bridge SDK** — BridgeClient, types, proof utilities, multisig, validators (v0.7.0 + v0.7.1 Agent A)
6. ✅ **v0.7.1 Agent A committed** — ValidatorSetRegistry, verify_threshold_signatures, ValidatorSet/ValidatorInfo types

### Hard Blockers (must be resolved before v0.7.2 implementation)

1. 🔴 **v0.7.1 Agent B not started** — Need: `BridgeValidator` SQLModel table, block header `signature` field, `_verify_threshold_signatures` in bridge.py, validator RPC endpoints
2. 🔴 **v0.7.0 Agent B uncommitted** — All v0.7.0 Agent B work (RPC endpoints, CLI, monitoring, tests) is in the working tree but not committed
3. 🔴 **No remote chain block header storage** — Must create `BridgeBlockHeader` table before Merkle proof verification can work (need to store source chain block headers with state roots)
4. 🔴 **Threat model may not exist** — v0.7.1 B1 creates `docs/architecture/bridge-threat-model.md`; if v0.7.1 Agent B hasn't completed, this is missing

---

## Architecture: Bridge Verification (v0.7.2)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — EXTEND + NEW MODULES)                   │
│                                                                      │
│  Verification types (A1 — EXTEND types.py):                          │
│    BridgeBlockHeader — remote chain block header dataclass           │
│    FinalityConfig — finality threshold config dataclass              │
│    ProofVerificationResult — result of proof verification            │
│                                                                      │
│  Oracle client interface (A2 — NEW oracle.py):                       │
│    OracleClient ABC — abstract verification interface                │
│    InProcessVerifier — default, calls MerkleProofVerifier protocol   │
│    ExternalOracleClient — stub for future external oracle            │
│    VerificationMode enum — "in_process" | "oracle"                   │
│                                                                      │
│  Verification utilities (A3 — NEW verification.py):                  │
│    validate_block_header(header, validator_set) — sig check          │
│    check_finality(header, confirmations, config) — threshold check   │
│    build_verification_message(header) — canonical msg for sig        │
│                                                                      │
│  BridgeClient extensions (A4):                                       │
│    get_block_header(chain_id, height) — RPC method                   │
│    oracle_status() — RPC method                                      │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge oracle-status   │    │                                      │
│  Uses BridgeClient (A4) │    │  Remote block header storage (B2):   │
│                         │    │    BridgeBlockHeader SQLModel (NEW)  │
│                         │    │    fields: chain_id, height, hash,   │
│                         │    │    proposer, state_root, signature,  │
│                         │    │    timestamp, finality_confirmed     │
│                         │    │                                      │
│                         │    │  Merkle proof verification (B3):     │
│                         │    │    _validate_proof → use             │
│                         │    │    merkle_patricia_trie.verify_proof │
│                         │    │    against stored state_root         │
│                         │    │                                      │
│                         │    │  Block header verification (B4):     │
│                         │    │    Verify proposer signature on      │
│                         │    │    source chain block header         │
│                         │    │    using v0.7.1 validator set        │
│                         │    │                                      │
│                         │    │  Finality tracking (B5):             │
│                         │    │    Track confirmations per chain     │
│                         │    │    Reject non-finalized for large    │
│                         │    │    transfers                         │
│                         │    │                                      │
│                         │    │  Validator set epoch tracking (B6):  │
│                         │    │    DB-backed epoch history           │
│                         │    │    Grace period for in-flight xfers  │
│                         │    │    Reject stale validator sets       │
│                         │    │                                      │
│                         │    │  Unfence release path (B7):          │
│                         │    │    BRIDGE_RELEASE_ENABLED → true     │
│                         │    │    After all verification is tested  │
│                         │    │                                      │
│                         │    │  Config (B1):                        │
│                         │    │    bridge_verification_mode          │
│                         │    │    bridge_min_confirmations          │
│                         │    │    bridge_finality_blocks            │
│                         │    │    bridge_large_transfer_threshold   │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
│                         │    │    Merkle proof, finality,           │
│                         │    │    block header, validator epoch     │
└─────────────────────────┘    └──────────────────────────────────────┘

Phase 0 (prerequisite — Agent B):
  v0.7.1 Agent B must be complete (BridgeValidator table, block header
  signature field, threshold sig verification in bridge.py)
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/bridge/types.py` (extend), `aitbc/bridge/oracle.py` (new), `aitbc/bridge/verification.py` (new), `aitbc/bridge/__init__.py` (extend), `aitbc/bridge/client.py` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `aitbc/constants.py`, `apps/blockchain-node/src/aitbc_chain/config.py`, `base_models.py`, `cross_chain/bridge.py`, `rpc/bridge.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns `aitbc/bridge/` package. Agent B owns all `apps/`, `cli/`, and `aitbc/constants.py`. Agent B consumes Agent A's `OracleClient`, `InProcessVerifier`, verification types, and `BridgeClient` extensions. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK — oracle interface, types, verification utilities). Agent B starts after Agent A completes A1-A3 (B3 Merkle proof verification depends on A1 types + A3 utilities). B1 (config), B2 (block header table) can proceed in parallel with Agent A.

**Hard dependency**: v0.7.1 Agent B must be complete before either agent starts v0.7.2 implementation.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.2 — Bridge Verification
