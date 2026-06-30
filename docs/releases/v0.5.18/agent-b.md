# v0.5.18 Test Suite Repair — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Blockchain-Node Test Fixes)

**Scope**: Update the 16 stale/infra test files to current APIs and apply Agent A's markers. No production source changes.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | `test_rpc_router.py` (12) — rebuild tx dicts to v0.5.16 `TransactionRequest` schema (top-level `to`/`amount`/`signature`); update error-message assertions. | 🔴 P0 | `test_rpc_router.py` | ✅ DONE |
| B2 | `test_guardian_contract.py` (14) — use valid 0x checksum addresses; align `reason`/`message` keys + status values. | 🔴 P0 | `test_guardian_contract.py` | ✅ DONE |
| B3 | `test_mempool.py` (8) — pass `sqlite:///{path}` URL to `DatabaseMempool`. | 🔴 P0 | `test_mempool.py` | ✅ DONE |
| B4 | Monkeypatch-target drift — `test_hub_manager.py` (6, `redis`), `test_force_sync_endpoints.py` (3, `session_scope`). | High | `network/test_hub_manager.py`, `test_force_sync_endpoints.py` | ✅ DONE |
| B5 | Quarantine infra tests with A's markers — `test_gossip_network.py` (7), `test_websocket.py` (4), `test_database_security.py` (1). | High | `test_gossip_network.py`, `test_websocket.py`, `security/test_database_security.py` | ✅ DONE |
| B6 | Remaining stale assertions — `test_staking.py` (6), `test_models.py` (2), `test_sync.py` (2), `test_consensus.py` (2), `test_gossip_broadcast.py` (2), `test_escrow.py` (1), `test_multi_validator_poa.py` (1), `test_island_join.py` (1). | Medium | (8 files) | ✅ DONE |
| B7 | Full-suite green run + correct v0.5.17 Final Test Results table. | Medium | `docs/releases/v0.5.17/change.log` | ✅ DONE |
| B8 | (Optional) Add CI collect-only guard note/script. | Low | docs / CI | ⬜ |

---

## B1: test_rpc_router (12)

- Tests build `TransactionRequest(...)` with the old shape (nested `recipient`/`value` in `payload`, no top-level `to`/`amount`/`signature`). The model now requires `to`, `amount`, `signature` (and accepts `chain_id`).
- Rebuild each test's tx dict to the current schema (mirror `apps/blockchain-node/tests/test_signing_round_trip.py`, which is green). For tests asserting validation rejection, assert against the **current** error messages.
- 2 failures are `AssertionError: Regex pattern did not match` — update the expected error-message regex.

---

## B2: test_guardian_contract (14)

- `initiate_transaction()` now calls `to_checksum_address(to_address)`; placeholder addresses (`"0xrecipient"`) are rejected with `{"status":"rejected","reason":...}` — no `message` key → `KeyError: 'message'`.
- Replace placeholder addresses with valid 0x checksum addresses (e.g. `0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C`).
- Align assertions to current response keys (`reason` on rejection vs `message` on approval) and status strings (`approved`/`time_locked`/`rejected`). Verify the spending-limit-message tests against `_check_spending_limits` (source line ~270).

---

## B3: test_mempool (8)

- `DatabaseMempool(db_path, ...)` is given a raw filesystem path; the constructor builds a SQLAlchemy engine → `Could not parse SQLAlchemy URL`.
- Pass `f"sqlite:///{tmp_path / 'mempool.db'}"` (check the current `DatabaseMempool.__init__` signature in `apps/blockchain-node/src/aitbc_chain/mempool.py` ~line 174 for the exact expected arg).

---

## B4: Monkeypatch-target drift (9)

- `test_hub_manager.py`: `monkeypatch.setattr(hub_manager, "redis", ...)` fails — module has no top-level `redis`. Patch the actual seam used by the current `hub_manager` (lazy import / client attribute). Tests that genuinely need Redis → tag `requires_redis` (B5).
- `test_force_sync_endpoints.py`: `monkeypatch.setattr(rpc_router, "session_scope", ...)` fails — `rpc.router` no longer exposes `session_scope`. Patch the current DB/session seam.

---

## B5: Quarantine infra tests (12)

- Apply Agent A's markers (must be merged first):
  - `test_gossip_network.py` → `@pytest.mark.requires_redis` / `@pytest.mark.requires_postgres` per test (Redis URL scheme + Postgres 5432 auth errors).
  - `test_websocket.py` → `requires_redis` (pub/sub backed) where applicable.
  - `security/test_database_security.py` → `requires_postgres`.
- After tagging, these **skip** (not fail) in a no-infra environment.

---

## B6: Remaining stale assertions (17)

- `test_staking.py` (6): messages/values drifted (`'self stake must be at least 1000.0'` vs `'insufficient stake'`, staked totals, active validators). **Verify current StakingManager behavior before editing** — if logic genuinely regressed, escalate.
- `test_models.py` (2): construct `Block` with `chain_id` (NOT NULL); fix hash-validation message.
- `test_sync.py` (2): add `skip_state_root_validation` kwarg to the `fake_import_block` double; fix `'Invalid hash length'` message assertion.
- `test_consensus.py` (2): proposer start/stop — may need a `requires_genesis` mark or a genesis fixture (the `Genesis file required for chain test-chain` RuntimeError). Classify and apply A's marker if infra-bound.
- `test_gossip_broadcast.py` (2): update to current `BroadcastGossipBackend` API (`_broadcast`, async-CM `TopicSubscription`).
- `test_escrow.py` (1): `EscrowManager.verify_milestone` renamed — use current method.
- `test_multi_validator_poa.py` (1), `test_island_join.py` (1): verify + update assertions.

---

## B7: Green run + fix v0.5.17 docs

- Run the full suite; confirm 0 failed / 0 errors (infra skipped). Then correct the Final Test Results table in `docs/releases/v0.5.17/change.log` (it measured only 3 of 17 blockchain-node files).

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared test config & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.18 — Test Suite Repair
**Agent**: Agent B (Blockchain-Node Test Fixes)
