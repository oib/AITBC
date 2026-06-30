# v0.5.17 Test Infrastructure Repair — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Fix the `BlockchainTextFormatter` backward-compat alias in the canonical logging module, close the `chain_id`-not-signed security gap on the signer side, and update unit tests accordingly.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | **Bug:** `BlockchainTextFormatter` alias missing in `aitbc/aitbc_logging.py` — `test_core.py` imports it directly and gets `ImportError`. The alias exists in `aitbc/log_utils/logging.py` (v0.5.11 B9) but not in the canonical module. | 🔴 P0 | `aitbc/aitbc_logging.py` | ✅ DONE |
| A2 | **Security:** Add `chain_id` to `_SIGNED_FIELDS` in `TransactionService` — currently `chain_id` is in the POST body but NOT in the signed message, allowing cross-chain replay. | 🔴 P0 | `aitbc/crypto/transaction_service.py` | ✅ DONE |
| A3 | Update `tests/unit/test_transaction_service.py` — pin `chain_id` in the canonical message, test cross-chain replay rejection. | High | `tests/unit/test_transaction_service.py` | ✅ DONE |
| A4 | Fix `tests/unit/test_core.py` — verify A1 alias resolves the collection error (or update import to `JournalFormatter` if alias is rejected). | Medium | `tests/unit/test_core.py` | ✅ DONE |

---

## A1: BlockchainTextFormatter backward-compat alias

- **Problem**: `tests/unit/test_core.py` line 5 does `from aitbc.aitbc_logging import BlockchainTextFormatter, ...`. The class was renamed to `JournalFormatter` in `aitbc/aitbc_logging.py` (v0.5.11). The backward-compat alias `BlockchainTextFormatter = JournalFormatter` was added to `aitbc/log_utils/logging.py` (line 24) but NOT to `aitbc/aitbc_logging.py` itself. Any code importing directly from the canonical module breaks.
- **Fix**: Add `BlockchainTextFormatter = JournalFormatter` after the `JournalFormatter` class definition in `aitbc/aitbc_logging.py`. Also add it to `__all__` if the module has one.
- **Verify**: `python -c "from aitbc.aitbc_logging import BlockchainTextFormatter; print(BlockchainTextFormatter)"` succeeds. `pytest tests/unit/test_core.py -q -o addopts=""` collects and passes.

---

## A2: Add chain_id to signed message (signer side)

- **Problem**: `aitbc/crypto/transaction_service.py` line 23: `_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type")` — `chain_id` is excluded. Line 147-149 has an explicit comment: "chain_id is included in the POST body for routing, but is intentionally NOT in the signed message. See v0.5.16 task B6."
- **Risk**: An attacker can take a valid signed transaction from chain `ait-hub`, change `chain_id` to `ait-island1` in the body, and submit it to the island1 node. The signature still validates because `chain_id` wasn't signed. This is a cross-chain replay attack.
- **Fix**: Add `"chain_id"` to `_SIGNED_FIELDS`. The `generate_signed_transaction` method already puts `chain_id` into the `transaction` dict (line 150), so `_canonical_signing_message` will pick it up automatically once it's in `_SIGNED_FIELDS`.
- **⚠️ Wire-format contract**: This change MUST be deployed simultaneously with B4 (verifier side). If A2 ships without B4, the signer includes `chain_id` in the message but the verifier doesn't — all signatures break. If B4 ships without A2, the verifier expects `chain_id` in the message but the signer doesn't include it — all signatures break. See Coordination Protocol.
- **Verify**: `_canonical_signing_message` output includes `chain_id` in the JSON. `test_canonical_message_is_pinned_to_node_format` test must be updated (A3) to include `chain_id` in the expected string.

---

## A3: Update transaction service unit tests

- Update `test_canonical_message_is_pinned_to_node_format`: add `"chain_id": "ait-hub"` to the tx dict and to the expected JSON string. The expected message becomes:
  ```
  {"amount":100,"chain_id":"ait-hub","fee":36,"from":"0x...","nonce":0,"payload":{"amount":100},"to":"0x...","type":"TRANSFER"}
  ```
- Update `test_signed_transaction_is_accepted_by_real_node_verifier`: the `tx_data_dict` construction (lines 72-81) must now include `"chain_id": req.chain_id` (the `TransactionRequest` model has this field). This coordinates with B4 — the endpoint will also start including `chain_id` in the dict.
- Add a new test: `test_cross_chain_replay_rejected` — sign a tx with `chain_id="ait-hub"`, then verify it with `chain_id="ait-island1"` in the dict. The signature must NOT validate because the signed message differs.

---

## A4: Fix test_core.py collection error

- After A1, verify `pytest tests/unit/test_core.py -q -o addopts=""` collects and passes.
- If any test in `test_core.py` asserts on `BlockchainTextFormatter` behavior (e.g., format output), verify the alias produces the same behavior as `JournalFormatter` (it should — it IS `JournalFormatter`).
- If the test has stale assertions that don't match current `JournalFormatter` behavior, update the assertions. Do NOT delete the tests.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Bug fixes, infrastructure & apps implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.17 — Test Infrastructure Repair
**Agent**: Agent A (Shared Core)
