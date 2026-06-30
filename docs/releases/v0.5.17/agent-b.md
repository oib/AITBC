# v0.5.17 Test Infrastructure Repair — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Bug Fixes, Infrastructure & Apps)

**Scope**: Register the multi-chain/multi-node fixtures in conftest, fix the CLI integration test collection error, delete dead handler test files, close the `chain_id`-not-signed gap on the verifier side, triage remaining skipped tests, and update the change.log.

**Working directory**: `/opt/aitbc/` (cross-cutting)

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit tests/cli tests/test_multi_chain_fixtures.py -q -o addopts="" && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | **Bug:** Multi-chain and multi-node fixtures not registered in conftest — 33 tests error with "fixture not found". | 🔴 P0 | `tests/conftest.py` | ✅ DONE |
| B2 | **Bug:** `test_cli_integration.py` imports non-existent `app.deps` module — collection error breaks entire `tests/cli/` suite. | 🔴 P0 | `tests/cli/test_cli_integration.py` | ✅ DONE |
| B3 | Delete 15 dead `test_handlers_*.py` files — they test a `handlers/` package removed in v0.5.15. 25+ permanently skipped tests. | Medium | `tests/cli/test_handlers_*.py` (15 files) | ✅ DONE |
| B4 | **Security:** Add `chain_id` to `tx_data_dict` in `submit_transaction` — verifier side of the B6 chain_id signing gap. | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` | ✅ DONE |
| B5 | Update `test_signing_round_trip.py` — test that cross-chain replay is rejected after A2+B4. | High | `apps/blockchain-node/tests/test_signing_round_trip.py` | ✅ DONE |
| B6 | Triage remaining ~127 skipped CLI tests — categorize, fix, or delete. | Low | `tests/cli/` (various) | ✅ DONE |
| B7 | Update `change.log` with accurate test results after all fixes. | Low | `docs/releases/v0.5.17/change.log` | ✅ DONE |

---

## B1: Register multi-chain and multi-node fixtures

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
- **Verify**: `pytest tests/test_multi_chain_fixtures.py -q -o addopts=""` — all 33 tests collect and pass (previously errored with "fixture not found").

---

## B2: Fix CLI integration test collection error

- **Problem**: `tests/cli/test_cli_integration.py` line 6 does `from app.deps import get_settings`. The `app/` package was removed in v0.5.15 (bounded contexts migration). The import fails with `ModuleNotFoundError`, breaking the entire `tests/cli/` suite.
- **Fix**: Replace the import with the correct bounded context import: `from apps.coordinator-api.src.app.core.config import get_settings`. If the test doesn't actually need coordinator-api settings, replace with a mock or remove the import entirely.
- **Verify**: `pytest tests/cli/test_cli_integration.py -q -o addopts=""` collects and passes.

---

## B3: Delete dead handler test files

- **Problem**: 15 files in `tests/cli/test_handlers_*.py` test a `handlers/` package that was removed in v0.5.15. These files contain 25+ permanently skipped tests (`@pytest.mark.skip(reason="...")`). They clutter the test suite and mislead contributors.
- **Fix**: Delete all 15 files:
  - `tests/cli/test_handlers_agent.py`
  - `tests/cli/test_handlers_blockchain.py`
  - `tests/cli/test_handlers_coin.py`
  - `tests/cli/test_handlers_gpu.py`
  - `tests/cli/test_handlers_marketplace.py`
  - `tests/cli/test_handlers_mining.py`
  - `tests/cli/test_handlers_network.py`
  - `tests/cli/test_handlers_staking.py`
  - `tests/cli/test_handlers_swarm.py`
  - `tests/cli/test_handlers_transaction.py`
  - `tests/cli/test_handlers_wallet.py`
  - `tests/cli/test_handlers_workflow.py`
  - `tests/cli/test_handlers_*.py` (any others matching the pattern)
- **Verify**: `pytest tests/cli/ -q -o addopts=""` — no collection errors, skipped test count drops by 25+.

---

## B4: Add chain_id to tx_data_dict (verifier side)

- **Problem**: `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` line 243-254 constructs `tx_data_dict` from the `TransactionRequest` model. The model has `chain_id` (line 13), but the dict construction omits it. The verifier passes this dict to `TransactionService.verify_transaction_signature`, which checks the signature against the canonical message. If the canonical message doesn't include `chain_id` (A2), the verifier must also not include it — otherwise signatures break.
- **Fix**: Add `"chain_id": req.chain_id` to the `tx_data_dict` construction (after line 248). This coordinates with A2 — once A2 adds `chain_id` to `_SIGNED_FIELDS`, the verifier must also include it in the dict.
- **⚠️ Wire-format contract**: This change MUST be deployed simultaneously with A2 (signer side). See A2 for details.
- **Verify**: `pytest apps/blockchain-node/tests/test_signing_round_trip.py -q -o addopts=""` passes after A2+B4 are both deployed.

---

## B5: Update signing round-trip test

- Update `test_signing_round_trip.py` to include a cross-chain replay test:
  ```python
  def test_cross_chain_replay_rejected(self):
      """Verify that a transaction signed for one chain cannot be replayed on another."""
      # Sign transaction for ait-hub
      tx_data = {..., "chain_id": "ait-hub"}
      signed = transaction_service.generate_signed_transaction(tx_data, private_key)

      # Try to verify with different chain_id in the dict
      tx_data_wrong_chain = {..., "chain_id": "ait-island1"}
      with pytest.raises(InvalidSignatureError):
          transaction_service.verify_transaction_signature(tx_data_wrong_chain, signed["signature"], public_key)
  ```
- **Verify**: Test passes after A2+B4 are both deployed.

---

## B6: Triage remaining skipped CLI tests

- Run `pytest tests/cli/ -v -o addopts=""` and collect all skipped tests.
- Categorize each skipped test:
  - **Fixable**: Test tests a feature that exists but the test is broken (e.g., wrong import, missing fixture). Fix the test.
  - **Obsolete**: Test tests a feature that was removed (e.g., `handlers/` package). Delete the test.
  - **Infrastructure**: Test requires external dependencies (e.g., running blockchain node). Keep as skipped with clear reason.
- **Verify**: Skipped test count is minimized, all remaining skips have clear, accurate reasons.

---

## B7: Update change.log

- Update the test results table in `docs/releases/v0.5.17/change.log` to reflect the actual state after all fixes:
  - Multi-chain fixtures: 33 tests now pass (previously errored)
  - `test_core.py`: now collects and passes (previously collection error)
  - `test_cli_integration.py`: now collects and passes (previously collection error)
  - Dead handler tests: 25+ tests removed (previously permanently skipped)
  - Cross-chain replay: now rejected (security fix)
- **Verify**: Change.log accurately describes the shipped state.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.17 — Test Infrastructure Repair
**Agent**: Agent B (Bug Fixes, Infrastructure & Apps)
