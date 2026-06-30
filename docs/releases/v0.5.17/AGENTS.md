# v0.5.17 — Agent Task Assignment

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
- [Status Baseline](./overview.md#status-baseline--already-done-verified-do-not-redo)
- [Task Split Overview](./overview.md#task-split-overview)

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

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.17 — Test Infrastructure Repair

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Fix the `BlockchainTextFormatter` backward-compat alias in the canonical logging module, close the `chain_id`-not-signed security gap on the signer side, and update unit tests accordingly.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | **Bug:** `BlockchainTextFormatter` alias missing in `aitbc/aitbc_logging.py` — `test_core.py` imports it directly and gets `ImportError`. The alias exists in `aitbc/log_utils/logging.py` (v0.5.11 B9) but not in the canonical module. | 🔴 P0 | `aitbc/aitbc_logging.py` | ✅ DONE |
| A2 | **Security:** Add `chain_id` to `_SIGNED_FIELDS` in `TransactionService` — currently `chain_id` is in the POST body but NOT in the signed message, allowing cross-chain replay. | 🔴 P0 | `aitbc/crypto/transaction_service.py` | ✅ DONE |
| A3 | Update `tests/unit/test_transaction_service.py` — pin `chain_id` in the canonical message, test cross-chain replay rejection. | High | `tests/unit/test_transaction_service.py` | ✅ DONE |
| A4 | Fix `tests/unit/test_core.py` — verify A1 alias resolves the collection error (or update import to `JournalFormatter` if alias is rejected). | Medium | `tests/unit/test_core.py` | ✅ DONE |

### Agent A — Detailed Instructions

#### A1: BlockchainTextFormatter backward-compat alias

- **Problem**: `tests/unit/test_core.py` line 5 does `from aitbc.aitbc_logging import BlockchainTextFormatter, ...`. The class was renamed to `JournalFormatter` in `aitbc/aitbc_logging.py` (v0.5.11). The backward-compat alias `BlockchainTextFormatter = JournalFormatter` was added to `aitbc/log_utils/logging.py` (line 24) but NOT to `aitbc/aitbc_logging.py` itself. Any code importing directly from the canonical module breaks.
- **Fix**: Add `BlockchainTextFormatter = JournalFormatter` after the `JournalFormatter` class definition in `aitbc/aitbc_logging.py`. Also add it to `__all__` if the module has one.
- **Verify**: `python -c "from aitbc.aitbc_logging import BlockchainTextFormatter; print(BlockchainTextFormatter)"` succeeds. `pytest tests/unit/test_core.py -q -o addopts=""` collects and passes.

#### A2: Add chain_id to signed message (signer side)

- **Problem**: `aitbc/crypto/transaction_service.py` line 23: `_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type")` — `chain_id` is excluded. Line 147-149 has an explicit comment: "chain_id is included in the POST body for routing, but is intentionally NOT in the signed message. See v0.5.16 task B6."
- **Risk**: An attacker can take a valid signed transaction from chain `ait-hub`, change `chain_id` to `ait-island1` in the body, and submit it to the island1 node. The signature still validates because `chain_id` wasn't signed. This is a cross-chain replay attack.
- **Fix**: Add `"chain_id"` to `_SIGNED_FIELDS`. The `generate_signed_transaction` method already puts `chain_id` into the `transaction` dict (line 150), so `_canonical_signing_message` will pick it up automatically once it's in `_SIGNED_FIELDS`.
- **⚠️ Wire-format contract**: This change MUST be deployed simultaneously with B4 (verifier side). If A2 ships without B4, the signer includes `chain_id` in the message but the verifier doesn't — all signatures break. If B4 ships without A2, the verifier expects `chain_id` in the message but the signer doesn't include it — all signatures break. See Coordination Protocol.
- **Verify**: `_canonical_signing_message` output includes `chain_id` in the JSON. `test_canonical_message_is_pinned_to_node_format` test must be updated (A3) to include `chain_id` in the expected string.

#### A3: Update transaction service unit tests

- Update `test_canonical_message_is_pinned_to_node_format`: add `"chain_id": "ait-hub"` to the tx dict and to the expected JSON string. The expected message becomes:
  ```
  {"amount":100,"chain_id":"ait-hub","fee":36,"from":"0x...","nonce":0,"payload":{"amount":100},"to":"0x...","type":"TRANSFER"}
  ```
- Update `test_signed_transaction_is_accepted_by_real_node_verifier`: the `tx_data_dict` construction (lines 72-81) must now include `"chain_id": req.chain_id` (the `TransactionRequest` model has this field). This coordinates with B4 — the endpoint will also start including `chain_id` in the dict.
- Add a new test: `test_cross_chain_replay_rejected` — sign a tx with `chain_id="ait-hub"`, then verify it with `chain_id="ait-island1"` in the dict. The signature must NOT validate because the signed message differs.

#### A4: Fix test_core.py collection error

- After A1, verify `pytest tests/unit/test_core.py -q -o addopts=""` collects and passes.
- If any test in `test_core.py` asserts on `BlockchainTextFormatter` behavior (e.g., format output), verify the alias produces the same behavior as `JournalFormatter` (it should — it IS `JournalFormatter`).
- If the test has stale assertions that don't match current `JournalFormatter` behavior, update the assertions. Do NOT delete the tests.

---

## Agent B — Bug Fixes, Infrastructure & Apps

**Scope**: Register the multi-chain/multi-node fixtures in conftest, fix the CLI integration test collection error, delete dead handler test files, close the `chain_id`-not-signed gap on the verifier side, triage remaining skipped tests, and update the change.log.

**Working directory**: `/opt/aitbc/` (cross-cutting)

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit tests/cli tests/test_multi_chain_fixtures.py -q -o addopts="" && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | **Bug:** Multi-chain and multi-node fixtures not registered in conftest — 33 tests error with "fixture not found". | 🔴 P0 | `tests/conftest.py` | ✅ DONE |
| B2 | **Bug:** `test_cli_integration.py` imports non-existent `app.deps` module — collection error breaks entire `tests/cli/` suite. | 🔴 P0 | `tests/cli/test_cli_integration.py` | ✅ DONE |
| B3 | Delete 15 dead `test_handlers_*.py` files — they test a `handlers/` package removed in v0.5.15. 25+ permanently skipped tests. | Medium | `tests/cli/test_handlers_*.py` (15 files) | ✅ DONE |
| B4 | **Security:** Add `chain_id` to `tx_data_dict` in `submit_transaction` — verifier side of the B6 chain_id signing gap. | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` | ✅ DONE |
| B5 | Update `test_signing_round_trip.py` — test that cross-chain replay is rejected after A2+B4. | High | `apps/blockchain-node/tests/test_signing_round_trip.py` | ✅ DONE |
| B6 | Triage remaining ~127 skipped CLI tests — categorize, fix, or delete. | Low | `tests/cli/` (various) | ✅ DONE |
| B7 | Update `change.log` with accurate test results after all fixes. | Low | `docs/releases/v0.5.17/change.log` | ✅ DONE |

### Agent B — Detailed Instructions

#### B1: Register multi-chain and multi-node fixtures

- **Problem**: `tests/conftest.py` line 29 has the comment `# Register multi-chain and multi-node fixtures so they're available to all tests` but no code follows. The fixtures defined in `tests/fixtures/multi_chain.py` and `tests/harness/multi_node.py` are never imported, so pytest can't discover them.
- **Fix**: Add after line 29 in `tests/conftest.py`:
  ```python
  # Register multi-chain and multi-node fixtures so they're available to all tests
  from tests.fixtures.multi_chain import (  # noqa: E402,F401
      island_registry,
      mock_settings,
      multi_chain_mempool,
      multi_chain_setup,
      sync_source_map,
  )
  from tests.harness.multi_node import (  # noqa: E402,F401
      multi_node_harness,
      three_node_network,
  )
  ```
  Order imports alphabetically (ruff isort). The `# noqa: E402` suppresses import-not-at-top (needed because of the sys.path manipulation above). The `# noqa: F401` suppresses unused-import (fixtures are registered by import side-effect).
- **Verify**: `pytest tests/test_multi_chain_fixtures.py -q -o addopts=""` — all 33 tests should pass (or skip if they require async fixtures not yet configured). Zero `fixture not found` errors.

#### B2: Fix test_cli_integration.py collection error

- **Problem**: `tests/cli/test_cli_integration.py` line 35: `from app.deps import APIKeyValidator` — `app.deps` does not exist in the coordinator-api. Line 36: `from app.main import create_app` — may also fail. This file was likely written against an older coordinator-api structure.
- **Fix options** (pick one):
  1. **If the test is still relevant**: Fix the import path to the correct module (check `apps/coordinator-api/src/app/` for where `APIKeyValidator` and `create_app` now live). Update `sys.path` setup at the top of the file if needed.
  2. **If the test is stale**: Add `pytest.skip("coordinator-api structure changed — test needs rewrite", allow_module_level=True)` at the top of the file (after imports that work). This prevents the collection error without losing the test file.
- **Verify**: `pytest tests/cli/ -q -o addopts=""` (without `--ignore`) collects successfully. Zero collection errors.

#### B3: Delete dead test_handlers_*.py files

- **Problem**: 15 test files in `tests/cli/` test a `cli/aitbc_cli/handlers/` package that was consolidated into `cli/aitbc_cli/commands/` in v0.5.15. Every test in every file skips with "Cannot import X handlers: No module named 'handlers.X'" or "handlers package no longer exists".
- **Files to delete** (15 files):
  ```
  tests/cli/test_handlers_account.py
  tests/cli/test_handlers_ai.py
  tests/cli/test_handlers_analytics.py
  tests/cli/test_handlers_blockchain.py
  tests/cli/test_handlers_bridge.py
  tests/cli/test_handlers_contract.py
  tests/cli/test_handlers_market.py
  tests/cli/test_handlers_messaging.py
  tests/cli/test_handlers_network.py
  tests/cli/test_handlers_performance.py
  tests/cli/test_handlers_pool_hub.py
  tests/cli/test_handlers_resource.py
  tests/cli/test_handlers_sync.py
  tests/cli/test_handlers_wallet.py
  tests/cli/test_handlers_workflow.py
  ```
- **Verify**: `pytest tests/cli/ -q -o addopts="" --ignore=tests/cli/test_cli_integration.py` — skip count drops by ~25 (from 152 to ~127). No new failures.

#### B4: Add chain_id to verifier tx_data_dict (verifier side)

- **Problem**: `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` lines 95-103 constructs `tx_data_dict` with fields `{from, to, amount, fee, nonce, payload, type, signature}` — no `chain_id`. The verifier (`verify_transaction_signature` in `rpc/utils.py` line 31) builds the signed message from all fields except `signature`, so `chain_id` is currently NOT in the verifier's message. This is consistent with the signer (A2) currently NOT signing `chain_id` — but it means cross-chain replay is possible.
- **Fix**: Add `"chain_id": chain_id` to the `tx_data_dict` construction at line 95-103. The `chain_id` variable is already in scope (it's resolved earlier in the function and used at line 110).
  ```python
  tx_data_dict = {
      "from": tx_data.sender,
      "to": tx_data.recipient,
      "amount": tx_data.amount,
      "fee": tx_data.fee,
      "nonce": tx_data.nonce,
      "payload": tx_data.payload,
      "type": tx_data.type,
      "chain_id": chain_id,  # NEW — must match signer (A2)
      "signature": tx_data.sig,
  }
  ```
- **⚠️ Wire-format contract**: This change MUST be deployed simultaneously with A2 (signer side). If B4 ships without A2, the verifier includes `chain_id` in the message but the signer doesn't — all signatures break. See Coordination Protocol.
- **Verify**: `pytest apps/blockchain-node/tests/test_signing_round_trip.py -q -o addopts=""` — all tests pass (after B5 update). `pytest apps/blockchain-node/tests/test_v0516_regression.py -q -o addopts=""` — no regressions.

#### B5: Update signing round-trip test for chain_id

- Update existing tests in `apps/blockchain-node/tests/test_signing_round_trip.py` to include `chain_id` in the `tx_data_dict` construction (matching B4).
- Add a new test: `test_cross_chain_replay_rejected` — sign a transaction for `chain_id="ait-hub"`, then construct a `tx_data_dict` with `chain_id="ait-island1"` and verify `verify_transaction_signature` returns `False`.
- **Verify**: All 4 existing tests still pass + 1 new test passes = 5 total.

#### B6: Triage remaining ~127 skipped CLI tests

After B1-B3, the skip count should be ~127. Categorize and triage:

| Category | Count (est.) | Action |
|----------|-------------|--------|
| Require live coordinator-api | ~25 | Move to `tests/integration/` with `@pytest.mark.integration` marker. Skip unless `--run-integration` flag is passed. |
| Require live edge-api | ~23 | Same as above. |
| `test_utils_dual_mode_wallet_adapter.py` import issues | 3 | Fix the import or delete if file-mode wallet creation is no longer supported. |
| Legitimate behavior differences (CLI delegates to RPC) | ~10 | Update test expectations to match actual CLI behavior. Remove skip. |
| ChainInfo validation complexity | ~5 | Add mock fixture for ChainInfo, remove skip. |
| Misc (auth module missing, deployment module missing) | ~61 | Triage individually. Delete tests for non-existent features. Fix tests for features that exist but need mocks. |

- **Target**: Reduce skips from ~127 to under 50.
- **Verify**: `pytest tests/cli/ -q -o addopts="" --ignore=tests/cli/test_cli_integration.py` — report new skip count.

#### B7: Update change.log with accurate test results

- After all fixes (A1-A4, B1-B6), run the full test suite:
  ```bash
  ./venv/bin/python -m pytest tests/unit tests/cli tests/test_multi_chain_fixtures.py apps/blockchain-node/tests/ -q -o addopts=""
  ```
- Update `docs/releases/v0.5.17/change.log` lines 288-304 (Final Test Results table) with actual numbers.
- Update the "Remaining Skipped CLI Tests" breakdown to reflect post-triage reality.
- Note the chain_id signing fix (A2+B4) as a production code change, not just test infrastructure.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/aitbc_logging.py` | Agent A | A1: add BlockchainTextFormatter alias |
| `aitbc/crypto/transaction_service.py` | Agent A | A2: add chain_id to _SIGNED_FIELDS |
| `tests/unit/test_core.py` | Agent A | A4: verify collection fix |
| `tests/unit/test_transaction_service.py` | Agent A | A3: update canonical message test |
| `tests/conftest.py` | Agent B | B1: register fixtures |
| `tests/cli/test_cli_integration.py` | Agent B | B2: fix or skip import |
| `tests/cli/test_handlers_*.py` | Agent B | B3: delete 15 files |
| `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` | Agent B | B4: add chain_id to tx_data_dict |
| `apps/blockchain-node/tests/test_signing_round_trip.py` | Agent B | B5: update round-trip test |
| `docs/releases/v0.5.17/change.log` | Agent B | B7: update test results |

### Shared Wire-Format Contract (A2 ↔ B4)

The `chain_id`-signing change is the only coordinated change in this release. Both sides must ship together.

**Current signed message** (before):
```json
{"amount":100,"fee":36,"from":"0x...","nonce":0,"payload":{"amount":100},"to":"0x...","type":"TRANSFER"}
```

**New signed message** (after A2+B4):
```json
{"amount":100,"chain_id":"ait-hub","fee":36,"from":"0x...","nonce":0,"payload":{"amount":100},"to":"0x...","type":"TRANSFER"}
```

**Execution order**:
1. **Phase 1 (parallel)**: A1, A4, B1, B2, B3 can all proceed independently — no shared files, no wire-format dependency.
2. **Phase 2 (sequential, coordinated)**: A2 and B4 must be developed together and committed in the same push. A2 goes first (signer), B4 follows immediately (verifier). A3 and B5 (test updates) follow after both code changes are in.
3. **Phase 3 (parallel)**: B6 (triage) and B7 (change.log) can proceed after all other tasks are done.

**Compatibility note**: This is a **breaking change** for any existing signed transactions in mempools or databases. A transaction signed with the old format (no `chain_id` in the signed set) will fail verification with the new verifier (which includes `chain_id`). This is acceptable because:
1. v0.5.16 just shipped — no production transactions are in-flight yet.
2. The security improvement (cross-chain replay prevention) outweighs the breakage.
3. The genesis key migration (B9) already broke compatibility for existing ed25519 wallets.

---

## Execution Order

```
Phase 1 (parallel — no dependencies):
  Agent A: A1 (BlockchainTextFormatter alias)
  Agent A: A4 (verify test_core.py fix)
  Agent B: B1 (register fixtures in conftest)
  Agent B: B2 (fix test_cli_integration.py)
  Agent B: B3 (delete 15 handler test files)

Phase 2 (sequential — wire-format contract):
  Agent A: A2 (add chain_id to _SIGNED_FIELDS)  ← goes first
  Agent B: B4 (add chain_id to tx_data_dict)     ← follows immediately
  Agent A: A3 (update unit tests)                ← after both code changes
  Agent B: B5 (update round-trip test)           ← after both code changes

Phase 3 (parallel — after all above):
  Agent B: B6 (triage remaining skips)
  Agent B: B7 (update change.log)
```

---

## Success Criteria

- ✅ `pytest tests/unit -q -o addopts=""` — zero collection errors, all tests pass (no `--ignore` needed)
- ✅ `pytest tests/cli -q -o addopts=""` — zero collection errors (no `--ignore` needed)
- ✅ `pytest tests/test_multi_chain_fixtures.py -q -o addopts=""` — all 33 tests pass (zero "fixture not found" errors)
- ✅ `pytest apps/blockchain-node/tests/ -q -o addopts=""` — all bridge + regression + round-trip tests pass
- ✅ Cross-chain replay test: signing with `chain_id="ait-hub"` fails verification when `chain_id="ait-island1"` is substituted
- ✅ 15 `test_handlers_*.py` files deleted
- ✅ CLI skip count reduced from 152 to under 100 (stretch: under 50)
- ✅ `change.log` test results table matches actual numbers
- ✅ `ruff check .` and `mypy aitbc/` both clean
