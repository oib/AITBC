# v0.7.5 Consensus Activation — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Consensus Activation — Fix all 12 security review findings (6 Critical + 6 High), then activate MultiValidatorPoA + PBFT.

**Goal**: Transform the scaffolding MultiValidatorPoA and PBFT implementations into production-grade consensus, satisfying all gating criteria from the [security review](../v0.7.4/security-review-multivalidator-poa.md), then remove the RuntimeError guards and activate multi-validator consensus.

> **Prerequisites**: [v0.7.4](../v0.7.4/change.log) ✅ (Agent A `feat(v0.7.4-a)`, Agent B pending — but v0.7.5 Agent A only needs v0.7.2/v0.7.3 which are ✅).

> **Risk**: High. Consensus bugs = chain splits. All changes must be tested with multi-node integration tests before activation. Testnet soak test (≥48h) is a mandatory operational requirement before mainnet activation.

> **Not on the critical path**: v0.8.x (trading) and v0.9.0 (atomic settlement) do not depend on v0.7.5. Single-validator PoA remains active until v0.7.5 ships.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (consensus signing utilities, shared types)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (security fixes, consensus activation, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Consensus Signing Utilities](./agent-a.md#a1-consensus-signing-utilities)
- [Shared Consensus Types](./agent-a.md#a2-shared-consensus-types)
- [Unit Tests](./agent-a.md#a3-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Config](./agent-b.md#b1-config)
- [KeyManager rewrite](./agent-b.md#b2-keymanager-rewrite-to-secp256k1)
- [MultiValidatorPoA fixes](./agent-b.md#b3-multivalidatorpoa-fixes)
- [PBFT fixes](./agent-b.md#b4-pbft-fixes)
- [SlashingManager wiring](./agent-b.md#b5-wire-slashingmanager-into-multivalidatorpoa)
- [ValidatorRotation wiring](./agent-b.md#b6-wire-validatorrotation-into-multivalidatorpoa)
- [Gossip-based PBFT transport](./agent-b.md#b7-gossip-based-pbft-transport)
- [Validator persistence](./agent-b.md#b8-validator-persistence)
- [Metrics](./agent-b.md#b9-metrics)
- [CLI commands](./agent-b.md#b10-cli-commands)
- [Tests](./agent-b.md#b11-tests)
- [Testnet soak test](./agent-b.md#b12-testnet-soak-test)
- [Mainnet activation](./agent-b.md#b13-mainnet-activation)
- [Documentation](./agent-b.md#b14-documentation)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.5 Target |
|-----------|----------|---------------|---------------|
| **MultiValidatorPoA** | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (294 lines) | SCAFFOLDING — RuntimeError guard at L45-49, no signature verification, no slashing, no rotation | Fix all 6 findings (C1-C3, C6, H1-H3), remove guard |
| **PBFT** | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (202 lines) | SCAFFOLDING — RuntimeError guard at L60-64, no message signatures, no-op network layer, unsafe view change | Fix all 5 findings (C4-C5, H4-H6), remove guard |
| **SlashingManager** | `apps/blockchain-node/src/aitbc_chain/consensus/slashing.py` (146 lines) | IMPLEMENTED but NOT WIRED — has detect/apply methods, not called from MultiValidatorPoA | Wire into MultiValidatorPoA (C2) |
| **ValidatorRotation** | `apps/blockchain-node/src/aitbc_chain/consensus/rotation.py` (140 lines) | IMPLEMENTED but NOT WIRED — has round-robin/stake/rep/hybrid strategies, not called | Wire into MultiValidatorPoA (C3) |
| **KeyManager** | `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` (173 lines) | WRONG CRYPTO — uses RSA 2048-bit, should use secp256k1 (matching PoA block signatures) | Rewrite to secp256k1 via `eth_keys` |
| **Consensus crypto** | `aitbc/crypto/crypto.py` | EXISTS — `sign_transaction_hash()`, `verify_signature()`, `recover_signer()` use secp256k1 | Add consensus message signing utility (Agent A) |
| **Gossip broker** | `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` | WORKING — `publish()`/`subscribe()` with InMemory + Redis backends, topic-based | Wire PBFT messages to gossip topics (C5) |
| **PoA block signing** | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py:944-999` | WORKING — `_sign_block_hash()` + `verify_block_signature()` via `eth_keys` (secp256k1) | MultiValidatorPoA reuses this pattern |
| **Block model** | `apps/blockchain-node/src/aitbc_chain/base_models.py:25-82` | EXISTS — has `signature`, `proposer`, `state_root`, `parent_hash` fields | No changes needed |
| **BridgeValidator model** | `apps/blockchain-node/src/aitbc_chain/base_models.py:219-239` | EXISTS — validator registration with epoch tracking | Adapt for consensus validator persistence |
| **Config** | `apps/blockchain-node/src/aitbc_chain/config.py` | NO `MULTI_VALIDATOR_CONSENSUS_ENABLED` setting — only env var check in code | Add to ChainSettings |
| **Consensus tests** | `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py` (166 lines) | BASIC — 11 tests for CRUD only, no security/consensus tests | Full test suite: Byzantine, forgery, view change, multi-node |
| **PBFT tests** | — | NONE — only threshold guard tests in `test_v064_multi_chain.py` | Full PBFT test suite |

### Already Implemented (needs wiring, not rewriting)

1. ✅ **SlashingManager** (`slashing.py`) — `detect_double_sign()`, `detect_unavailability()`, `detect_invalid_block()`, `apply_slashing()`, `should_slash()`, `get_slashing_history()` — all implemented, not called from MultiValidatorPoA
2. ✅ **ValidatorRotation** (`rotation.py`) — `should_rotate()`, `rotate_validators()`, 4 strategies (round-robin, stake-weighted, reputation, hybrid) — all implemented, not called
3. ✅ **PoA block signature verification** (`poa.py:969-999`) — `verify_block_signature()` via `eth_keys` secp256k1 — pattern to follow for MultiValidatorPoA
4. ✅ **PoA block creation** (`poa.py:218-518`) — `_compute_block_hash()` (SHA-256 of chain_id|height|parent_hash|timestamp|tx_hashes), `_sign_block_hash()`, state root via Merkle Patricia Trie — pattern to follow
5. ✅ **Gossip broker** (`gossip/broker.py`) — `publish()`/`subscribe()` with topic-based routing, InMemory + Redis backends — ready for PBFT message transport
6. ✅ **Crypto functions** (`aitbc/crypto/crypto.py`) — `sign_transaction_hash()`, `verify_signature()`, `recover_signer()` (secp256k1 via eth_keys/eth_account) — ready for consensus message signing

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/crypto/consensus_signing.py` (new), `aitbc/consensus/` (new types), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 14 items | `apps/blockchain-node/src/aitbc_chain/consensus/`, `apps/blockchain-node/src/aitbc_chain/config.py`, `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/tests/consensus/`, `cli/` |

**Conflict boundary**: Agent A owns `aitbc/crypto/` and `aitbc/consensus/` (new). Agent B owns `apps/blockchain-node/` and `cli/`. Agent B consumes Agent A's consensus signing utilities.

**Sequencing**: Agent A goes first (shared consensus crypto). Agent B starts after Agent A A1 completes (signing utilities needed for C1, C4). Agent B B1 (config) and B2 (keys.py rewrite) can proceed independently in parallel with Agent A.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.5 — Consensus Activation
