# v0.5.17 Test Infrastructure Repair — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Test Infrastructure Repair — fix the verified gaps from the v0.5.17 suggestions.md investigation. The release shipped with 33 multi-chain fixture tests that all error (fixtures not registered), a collection error in `tests/unit/test_core.py` (imports a removed symbol), a collection error in `tests/cli/test_cli_integration.py` (imports non-existent module), 15 dead `test_handlers_*.py` files (25+ permanently skipped tests against a removed package), and an inaccurate change.log test results table. Additionally, close the `chain_id`-not-signed security gap (v0.5.16 B6 follow-up) that allows cross-chain transaction replay.

**Goal**: Make the test infrastructure that v0.6.x and v0.7.x depend on actually work — zero collection errors, multi-chain fixtures discoverable, dead test files removed, and the signed message covers `chain_id` so cross-chain replay is impossible.

> **Scope note**: The 40+ CLI stub-to-functional conversions and the bridge/regression test suites from the original v0.5.17 are genuinely done and solid (1165 CLI tests pass, 62 bridge+regression tests pass). This is a repair pass, not a rebuild.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Type safety & shared core implementation (logging alias, chain_id signing, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Bug fixes, infrastructure & apps (fixture registration, collection errors, dead files, verifier side)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--already-done-verified-do-not-redo)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [BlockchainTextFormatter backward-compat alias](./agent-a.md#a1-blockchaintextformatter-backward-compat-alias)
- [Add chain_id to signed message](./agent-a.md#a2-add-chain_id-to-signed-message-signer-side)
- [Update transaction service unit tests](./agent-a.md#a3-update-transaction-service-unit-tests)
- [Fix test_core.py collection error](./agent-a.md#a4-fix-test_corepy-collection-error)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Register multi-chain and multi-node fixtures](./agent-b.md#b1-register-multi-chain-and-multi-node-fixtures)
- [Fix CLI integration test collection error](./agent-b.md#b2-fix-cli-integration-test-collection-error)
- [Delete dead handler test files](./agent-b.md#b3-delete-dead-handler-test-files)
- [Add chain_id to tx_data_dict](./agent-b.md#b4-add-chain_id-to-tx_data_dict-in-submit_transaction)
- [Update signing round-trip test](./agent-b.md#b5-update-test_signing_round_trippy)
- [Triage remaining skipped CLI tests](./agent-b.md#b6-triage-remaining-127-skipped-cli-tests)
- [Update change.log](./agent-b.md#b7-update-changelog)

---

## Status Baseline — Already Done (verified, do NOT redo)

| Item | Evidence | Status |
|------|----------|--------|
| 40+ CLI stub tests converted to functional | `tests/cli/test_commands_*.py` — 1165 pass, 0 fail | ✅ DONE |
| Bridge test suite (15 tests) | `apps/blockchain-node/tests/test_bridge_suite.py` | ✅ DONE |
| v0.5.16 regression tests (45 tests) | `apps/blockchain-node/tests/test_v0516_regression.py` | ✅ DONE |
| Signing round-trip test (4 tests) | `apps/blockchain-node/tests/test_signing_round_trip.py` | ✅ DONE |
| Multi-chain fixture code written | `tests/fixtures/multi_chain.py` (6 fixtures) | ✅ DONE (but not registered — see B1) |
| Multi-node harness code written | `tests/harness/multi_node.py` (2 fixtures) | ✅ DONE (but not registered — see B1) |
| CLI mock fixtures | `tests/fixtures/cli_mocks.py` (8 fixtures) | ✅ DONE |
| HTTPException swallowing fix | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` | ✅ DONE |
| Genesis key migration to secp256k1 (B9) | `apps/blockchain-node/scripts/*.py`, `cli/aitbc_cli/`, `aitbc/utils/validation.py` | ✅ DONE (commit `596097c89`) |
| TransactionService secp256k1 signing (A1) | `aitbc/crypto/transaction_service.py` | ✅ DONE (commit `e2556edec`) |

---

## Task Split Overview

| Agent | Domain | Tasks | Files Touched |
|-------|--------|-------|---------------|
| **Agent A** | Type safety & shared core (`aitbc/`) | 4 items | `aitbc/aitbc_logging.py`, `aitbc/crypto/transaction_service.py`, `tests/unit/test_core.py`, `tests/unit/test_transaction_service.py` |
| **Agent B** | Bug fixes, infrastructure & apps | 7 items | `tests/conftest.py`, `tests/cli/test_cli_integration.py`, `tests/cli/test_handlers_*.py` (delete 15), `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py`, `apps/blockchain-node/tests/test_signing_round_trip.py`, `tests/cli/` (triage), `docs/releases/v0.5.17/change.log` |

**Conflict boundary** (from root `AGENTS.md`): Agent A owns all files under `aitbc/` except `aitbc/constants.py` and `aitbc/log_utils/`. Agent B owns `aitbc/constants.py`, `aitbc/log_utils/`, all `apps/` files, `cli/` files, docs, and systemd config. Both agents must not edit the same file. The `chain_id`-signing change (A2 ↔ B4) is split across two different files joined by a shared wire-format contract — see Coordination Protocol.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Bug fixes, infrastructure & apps implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.17 — Test Infrastructure Repair
