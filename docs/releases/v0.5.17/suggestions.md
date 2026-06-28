## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.5.17 Suggestions

## Status
**RELEASE MARKED COMPLETE BUT HAS VERIFIED GAPS** — The change.log claims 33 multi-chain fixture tests pass and 1317 CLI tests run with 1165 passing. Reality: the 33 multi-chain fixture tests **all error** (fixture not registered), `test_core.py` has a **collection error** (imports removed symbol), and 15 `test_handlers_*.py` files (25+ tests) skip against a **non-existent `handlers/` package**. The bridge and regression suites do pass (62 tests). The stub-to-functional conversion of 40+ CLI command files is genuinely done and solid (1165 pass, 0 fail).

## Blockers
- **Multi-chain fixtures are broken** — `tests/conftest.py` line 29 has a comment "Register multi-chain and multi-node fixtures so they're available to all tests" but **no code follows it**. The fixtures in `tests/fixtures/multi_chain.py` and `tests/harness/multi_node.py` are never imported, so `multi_chain_setup`, `sync_source_map`, `island_registry`, `multi_chain_mempool`, `multi_node_harness`, and `three_node_network` are all unresolvable. Every test in `tests/test_multi_chain_fixtures.py` errors with `fixture 'multi_chain_setup' not found`. This blocks v0.6.3, v0.6.4, v0.7.0, and v0.9.0 which depend on these fixtures.
- **`test_core.py` collection error** — `tests/unit/test_core.py` imports `BlockchainTextFormatter` from `aitbc.aitbc_logging`, which was removed in v0.5.11 B9 (logging consolidation — `BlockchainTextFormatter` became alias `JournalFormatter` but the alias was never exported). This causes a collection-level ImportError that prevents the entire `tests/unit/` suite from running unless `--ignore=tests/unit/test_core.py` is passed. Same issue in `tests/test_imports.py` lines 18 and 31.
- **`test_cli_integration.py` collection error** — `tests/cli/test_cli_integration.py` line 35 imports `from app.deps import APIKeyValidator` which doesn't exist in the coordinator-api `app` module. This causes a collection error that prevents the entire `tests/cli/` suite from running unless `--ignore=tests/cli/test_cli_integration.py` is passed.

## Confirmed Issues (verified in /opt/aitbc)

### 1. Multi-chain fixture registration missing (P0 — blocks all downstream releases)
- `tests/conftest.py` line 29: comment says "Register multi-chain and multi-node fixtures" but no import or `@pytest.fixture` registration follows
- `tests/fixtures/multi_chain.py` defines 6 fixtures (`multi_chain_setup`, `sync_source_map`, `island_registry`, `multi_chain_mempool`, `mock_settings`, `multi_island_setup`) — none are registered
- `tests/harness/multi_node.py` defines 2 fixtures (`multi_node_harness`, `three_node_network`) — none are registered
- `tests/test_multi_chain_fixtures.py`: all 33 tests error with `fixture not found`
- **Fix**: Add to `tests/conftest.py` after line 29:
  ```python
  from tests.fixtures.multi_chain import (  # noqa: E402,F401
      multi_chain_setup, sync_source_map, island_registry,
      multi_chain_mempool, mock_settings,
  )
  from tests.harness.multi_node import multi_node_harness, three_node_network  # noqa: E402,F401
  ```

### 2. `BlockchainTextFormatter` removed but still imported (P1 — breaks unit test collection)
- `aitbc/aitbc_logging.py` line 17: class is now `JournalFormatter` (renamed in v0.5.11 B9)
- `tests/unit/test_core.py` line 5: `from aitbc.aitbc_logging import BlockchainTextFormatter, StructuredFormatter, configure_logging, get_logger, setup_logger` — `BlockchainTextFormatter` does not exist
- `tests/test_imports.py` lines 18, 31: imports `BlockchainTextFormatter` and asserts it's not None
- **Fix**: Either (a) add `BlockchainTextFormatter = JournalFormatter` alias to `aitbc/aitbc_logging.py` for backward compat, or (b) update `test_core.py` and `test_imports.py` to import `JournalFormatter` instead. Option (a) is safer — other consumers may also reference the old name.

### 3. `test_cli_integration.py` imports non-existent module (P1 — breaks CLI test collection)
- `tests/cli/test_cli_integration.py` line 35: `from app.deps import APIKeyValidator` — `app.deps` does not exist in coordinator-api
- Line 36: `from app.main import create_app` — may also fail depending on path setup
- **Fix**: Either fix the import path to the correct module, or mark the file with `pytest.skip(allow_module_level=True)` and a clear reason. The test was likely written against an older coordinator-api structure.

### 4. 15 `test_handlers_*.py` files test non-existent package (P2 — 25+ permanently skipped tests)
- `cli/aitbc_cli/handlers/` directory does not exist — handlers were consolidated into `cli/aitbc_cli/commands/` in v0.5.15
- 15 test files remain: `test_handlers_account.py`, `test_handlers_ai.py`, `test_handlers_analytics.py`, `test_handlers_blockchain.py`, `test_handlers_bridge.py`, `test_handlers_contract.py`, `test_handlers_market.py`, `test_handlers_messaging.py`, `test_handlers_network.py`, `test_handlers_performance.py`, `test_handlers_pool_hub.py`, `test_handlers_resource.py`, `test_handlers_sync.py`, `test_handlers_wallet.py`, `test_handlers_workflow.py`
- Each skips with "Cannot import X handlers: No module named 'handlers.X'" or "handlers package no longer exists"
- **Fix**: Delete all 15 files. They test code that was intentionally removed. Keeping them inflates skip counts and obscures real gaps.

### 5. `chain_id` still excluded from signed message (P2 — transaction malleability risk, tracked as B6)
- `aitbc/crypto/transaction_service.py` line 147-149: comment explicitly says `chain_id` is intentionally NOT in the signed set, with a TODO for B6
- A transaction can be replayed on a different chain by swapping `chain_id` in the body — the signature still validates because `chain_id` isn't covered
- The B6 round-trip test (`apps/blockchain-node/tests/test_signing_round_trip.py`) passes but only tests that the current (incomplete) wire format round-trips — it does not test chain_id inclusion
- **Fix**: Add `chain_id` to `_SIGNED_FIELDS` in `aitbc/crypto/transaction_service.py`, update the verifier in `apps/blockchain-node/src/aitbc_chain/rpc/utils.py` to include `chain_id` in the reconstructed message, and update the round-trip test to verify cross-chain replay is rejected. This is a coordinated A/B change — see v0.5.16 tasks.md Coordination Protocol.

### 6. Remaining 152 skipped CLI tests — categories and recommendations
- **48 tests**: Require live coordinator-api (25) or edge-api (23) — these are integration tests, not stubs. **Recommend**: Move to `tests/integration/` and mark with `@pytest.mark.integration` so they only run with `--run-integration`.
- **25 tests**: `test_handlers_*.py` — see issue 4 above. **Recommend**: Delete.
- **3 tests**: `test_utils_dual_mode_wallet_adapter.py` — "File mode wallet creation has import issues". **Recommend**: Fix the import or delete if file-mode wallet creation is no longer supported.
- **~10 tests**: Legitimate behavior differences (CLI delegates to RPC, not local file). **Recommend**: Update test expectations to match actual CLI behavior.
- **~63 tests**: Misc (ChainInfo validation complexity, deployment module missing, auth module missing). **Recommend**: Triage individually — some test non-existent features and should be deleted; others need mock fixtures.

### 7. Change.log test results table is inaccurate (P3 — documentation)
- `docs/releases/v0.5.17/change.log` lines 292-296: claims 33 multi-chain fixture tests pass, 1317 CLI tests run
- Reality: 33 multi-chain tests **error** (fixture not found), CLI tests are 1165 passed / 152 skipped (not 1317 run — 1317 is the collected count including errors)
- The bridge suite (15 tests) and regression suite (45 tests) numbers are accurate
- **Fix**: Re-run the full suite after fixing issues 1-3, then update the table with actual numbers

## Recommendations
- **Fix issue 1 (fixture registration) first** — it's a one-line conftest fix that unblocks 33 tests and all downstream multi-chain releases. The fixtures are already written and correct; they just aren't wired up.
- **Fix issue 2 (BlockchainTextFormatter) second** — either add the alias or update the two test files. This unblocks `tests/unit/` collection without `--ignore`.
- **Fix issue 3 (test_cli_integration.py) third** — fix or skip the import. This unblocks `tests/cli/` collection without `--ignore`.
- **Delete the 15 `test_handlers_*.py` files** — they're dead weight from a pre-v0.5.15 architecture. Removing them reduces skip count from 152 to ~127 and makes the remaining skips more meaningful.
- **Triage the remaining 127 skips** in a follow-up — categorize as "integration (needs live service)", "dead code (test non-existent feature)", or "fixable (needs mock fixture)". Set a target to get skips under 50.
- **Close the chain_id signing gap (B6)** — this is a security issue (cross-chain replay), not just a test issue. It should be prioritized for v0.6.0 or a v0.5.18 patch.
- **Add a CI guard** that runs `pytest tests/ --collect-only` and fails if there are any collection errors. This would have caught issues 1-3 immediately.
- **Consider `pytest --strict-markers`** and registering custom markers (`@pytest.mark.integration`, `@pytest.mark.slow`) to formalize the skip categories.
