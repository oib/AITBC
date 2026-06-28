## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.5.18 Suggestions

## Status
**BLOCKCHAIN-NODE TEST SUITE IS RED — 64 FAILED + 8 ERRORS (72 total), ALL PRE-EXISTING.** The `apps/blockchain-node/tests/` suite has 72 broken tests across 16 files. Verified via git worktree that the **identical 64 failed + 8 errors exist at commit `3d94338c2`** (the bulk v0.5.16 security fix, before the v0.5.16-closure/v0.5.17 session). This session's work added 67 passing tests (202→269 passed) but did **not** introduce or fix any of the 72 failures. The suite also **hangs** without a per-test timeout (Redis/Postgres connection retries).

## Why this was missed until now
`pyproject.toml` `[tool.pytest.ini_options].testpaths` is:
```toml
testpaths = ["tests/unit", "tests/integration", "tests/e2e", "tests/security"]
```
`apps/blockchain-node/tests/` is **NOT** in `testpaths`. So the default `pytest` invocation never collects the blockchain-node suite. v0.5.17's change.log measured only 3 hand-picked blockchain-node files (`test_bridge_suite`, `test_v0516_regression`, `test_signing_round_trip` — all green) and declared the suite healthy. The other 333 blockchain-node tests (269 pass / 64 fail / 8 error) were never in the gate.

## Blockers (for v0.6.0)
- **v0.6.0 is Database & Network Optimization** — it will heavily refactor exactly the areas these red tests cover: `mempool.py`, `sync.py`, gossip backends, `rpc/router.py`. Starting v0.6.0 on a red suite means there is no reliable baseline to detect regressions.
- The suite **hangs** in CI without a default timeout — at least one test blocks >20s on a Redis/Postgres connection retry.

## Root-cause taxonomy (verified in /opt/aitbc)

All 72 failures trace to the v0.5.16 API/schema changes (secp256k1/0x address migration, `TransactionRequest` requiring `to`/`amount`/`signature`, `Block.chain_id` NOT NULL, mempool/gossip API refactors) where the corresponding tests were never updated. Two distinct groups:

### Group A — Stale tests: API/schema/format drift (test-side fixes, NO source change) — 52 failed + 8 errors

| File | # | Root cause | Fix |
|------|---|-----------|-----|
| `test_rpc_router.py` | 12 | `TransactionRequest` rejects old payload format — tests omit top-level `to`/`amount`/`signature` (nested `recipient`/`value` in `payload`). 2 are error-message regex assertions. | Rebuild test tx dicts to the v0.5.16 `TransactionRequest` schema; update expected messages. |
| `test_guardian_contract.py` | 14 | `initiate_transaction` now calls `to_checksum_address()` → placeholder addrs like `"0xrecipient"` return `{"status":"rejected","reason":...}` (no `message` key). Spending-limit messages/response keys drifted. | Use valid 0x checksum addresses; align `reason`/`message` + status assertions. |
| `test_mempool.py` | 8 (5 ERROR + 3 FAIL) | `DatabaseMempool(db_path, ...)` passes a raw filesystem path; constructor now builds a SQLAlchemy engine and needs a URL → `Could not parse SQLAlchemy URL`. | Pass `sqlite:///{path}` (or use the constructor's current expected arg). |
| `network/test_hub_manager.py` | 6 | `monkeypatch.setattr(hub_manager, "redis", ...)` — module no longer exposes a top-level `redis` attribute (lazy import). | Patch the current import target / inject a fake client via the real seam. |
| `economics/test_staking.py` | 6 | Message/value drift: e.g. `'self stake must be at least 1000.0'` vs expected `'insufficient stake'`; staked-total and active-validator assertions. | Verify current StakingManager behavior; update assertions (likely test-side). |
| `test_force_sync_endpoints.py` | 3 ERROR | `monkeypatch.setattr(rpc_router, "session_scope", ...)` — `rpc.router` no longer has `session_scope`. | Patch the current session/DB seam. |
| `test_gossip_broadcast.py` | 2 | `BroadcastGossipBackend` has no `_broadcast`; `TopicSubscription` is not an async context manager. | Update to current gossip backend API. |
| `test_consensus.py` | 2 | `test_start_stop_proposer` / `test_start_already_running` — proposer lifecycle. May need genesis fixture (see env note). | Verify; likely needs genesis fixture or updated lifecycle assertions. |
| `test_models.py` | 2 | `NOT NULL constraint failed: block.chain_id` (Block now requires `chain_id`); hash-validation message. | Construct `Block` with `chain_id`; update message assertion. |
| `test_sync.py` | 2 | `fake_import_block()` missing new `skip_state_root_validation` kwarg; `'Invalid hash length: 7'` vs `'Invalid block hash'`. | Update the test double's signature + message assertion. |
| `contracts/test_escrow.py` | 1 | `EscrowManager` has no `verify_milestone` (renamed/removed). | Update to current method name. |
| `consensus/test_multi_validator_poa.py` | 1 | `test_update_validator_reputation` assertion. | Verify + update. |
| `network/test_island_join.py` | 1 | `test_send_join_request_success` assertion. | Verify + update. |

**Subtotal: 60 (52 failed + 8 errors) — mechanical, test-side, low risk.**

### Group B — Environment-dependent: need real Redis/Postgres (quarantine behind markers) — 12 failed

| File | # | Root cause | Fix |
|------|---|-----------|-----|
| `test_gossip_network.py` | 7 | `ValueError: Redis URL must specify scheme (redis://...)` and `psycopg.OperationalError: connection to 127.0.0.1:5432 ... password authentication failed for user "aitbc_mempool"`. | Mark `requires_redis` / `requires_postgres`; auto-skip when unavailable. |
| `test_websocket.py` | 4 | `WebSocketDisconnect`; `publish`/`connect` mock-call assertions (Redis pub/sub backed). | Mark `requires_redis` or provide an in-process fake backend. |
| `security/test_database_security.py` | 1 | `psycopg.OperationalError` (Postgres). | Mark `requires_postgres`; auto-skip when unavailable. |

**Subtotal: 12 — should NOT fail in a no-infra CI; quarantine, don't delete.**

> **Note:** A `RuntimeError: Genesis file required but not found for chain test-chain (.../var/lib/aitbc/data/test-chain/genesis.json)` appears 2× — likely in `test_consensus.py` and/or `test_models.py`. Those tests need a genesis-file fixture (or a `requires_genesis` skip). Classify during implementation.

## Environment facts
- `pytest-timeout` 2.4.0 **is installed** but no default `timeout` is configured → suite can hang.
- `--strict-markers` and `--strict-config` are **on** → any new marker must be registered in `pyproject.toml` `[tool.pytest.ini_options].markers` before use, or collection errors.
- `fakeredis` is **NOT installed**. Prefer marker-based auto-skip over adding a new dependency for this small patch. If an in-process Redis fake is later wanted, add `fakeredis` as a separate, deliberate change (pin a version published >7 days ago).

## Recommendations
- **Keep this patch small and test-only.** No production `aitbc_chain` source changes — every failure is a stale test or a missing skip-guard. If any "stale test" turns out to expose a real behavioral regression (watch `test_staking`, `test_consensus`, `test_guardian_contract`), STOP and escalate rather than weakening the assertion to make it pass.
- **Order matters (`--strict-markers`):** register the new markers + default `timeout` FIRST, then apply them, then fix the stale tests, then (last) add `apps/blockchain-node/tests` to `testpaths` so the suite is actually gated going forward.
- **Add a default per-test `timeout`** (e.g. 60s) to prevent CI hangs.
- **Quarantine, don't delete, the env-dependent tests.** Auto-skip when Redis/Postgres is unreachable so they still run in a full-infra environment.
- **Add `apps/blockchain-node/tests` to `testpaths`** as the final step — this is the change that prevents the suite from silently rotting again. Without it, v0.6.0 could re-break these tests unnoticed.
- **Add a CI collect-only guard** (`pytest --collect-only -q`) that fails on any collection error, so monkeypatch-target drift (`session_scope`, `redis`) is caught immediately.
- Update v0.5.17's change.log Final Test Results table — it overstated suite health by measuring only 3 of 17 blockchain-node test files.
