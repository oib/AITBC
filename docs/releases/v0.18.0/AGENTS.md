# v0.18.0 — Audit Remediation: Chain Integrity, Money Correctness & Auth Defaults

**Last Updated**: 2026-07-28
**Version**: 0.2 — Agent A complete ✅ / Agent B in progress 🚧
**Changelog**: [change.log](change.log)

**Release Theme**: Remediate the 2026-07-28 full-repo audit findings.
Smallest correct diffs; no new dependencies; no new abstractions. Findings
below cite verified file:line locations — fix the shared function once, do
not patch per-caller.

**Prerequisites**: v0.17.0 complete.

**Scale context** (v2.0.0 parking-lot review): 10–50 nodes, thousands of
accounts, 10–100 transfers/day. Do not over-engineer beyond this.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/auth/`, `aitbc/tee/`, `aitbc/caching/`, `aitbc/agent_economics/`, `aitbc/wallet/`, `aitbc/agent_memory/`, `aitbc/compliance/`, `aitbc/risk/`, `aitbc/ethereum_rpc.py`, `aitbc/crypto/secrets.py`, `packages/py/aitbc-agent-sdk` | Timing-safe compares, TEE secret hardening, timezone/datetime fixes, async/concurrency hygiene |
| **Agent B** | `apps/blockchain-node`, `apps/bridge-monitor`, `apps/trading`, `apps/marketplace`, `apps/wallet`, `apps/api-gateway`, `apps/coordinator-api`, `apps/agent-coordinator`, `apps/gpu`, `apps/blockchain-explorer`, `apps/pool-hub` | Chain-import validation, signature verification, replay/nonce persistence, settlement/bridge correctness, Decimal migration, auth defaults, SSRF, rollbacks |

**No file overlap between agents.** `packages/py/aitbc-agent-sdk` is assigned
to Agent A for this release (packages/ is otherwise unassigned in the root
AGENTS.md role table).

---

## Agent A — Shared Core & SDK — ✅ complete (2026-07-28)

Implementation notes recorded in [change.log](change.log). Summary: A1–A6
done; `tee/session.py` needed no change (field defaults already guarded);
`aitbc/models/coin_request.py` utcnow deliberately skipped (SQLAlchemy naive
column — schema decision); `secrets.py` fix narrowed to the two actually
unguarded dict iterations since writer paths already held the lock.
Verification: ruff clean, mypy clean (204 files), 1178 unit tests pass.

### A1: Timing-safe password comparison (P0) — ✅

- File: `aitbc/auth/password.py:116`
- Replace `return new_hash == hashed_password` with
  `hmac.compare_digest(new_hash.encode(), hashed_password.encode())`
  in the legacy PBKDF2 verification path.
- Check for sibling `==` comparisons on hashes/tokens in the same module.

### A2: TEE empty-secret hardening (P1) — ✅

- Files: `aitbc/tee/sealed_storage.py:40-44,62`, `aitbc/tee/session.py:38,66,75`
- Remove `secret: bytes = b""` defaults; raise `ValueError("secret is
  required")` when falsy.
- Update in-repo callers/tests to pass an explicit secret (simulator mode
  included). Do not add a config flag.

### A3: Cache expiry timezone fix (P1) — ✅

- File: `aitbc/caching/cache_entry.py:26-34`
- Current code strips tzinfo from the *aware* `now` to compare with a naive
  `expires_at` — wrong result for non-UTC naive times.
- Fix direction: `expires = self.expires_at.replace(tzinfo=UTC) if
  self.expires_at.tzinfo is None else self.expires_at; return now > expires`.
- One runnable check: a unit test asserting a naive-UTC `expires_at` in the
  past reports expired.

### A4: `datetime.utcnow()` sweep (P2) — ✅

- Files: `aitbc/agent_economics/bonds.py`, `aitbc/agent_economics/swaps.py`,
  `aitbc/wallet/escrow.py`, `aitbc/agent_memory/models.py`,
  `aitbc/compliance/audit.py`, `aitbc/risk/circuit_breaker.py`
- Replace with `datetime.now(UTC)`. Pure mechanical swap; no behavior change
  intended — if a comparison against a naive datetime exists nearby, flag it
  instead of guessing.

### A5: Async/threading hygiene (P2) — ✅

- File: `aitbc/ethereum_rpc.py:221` — add `async def
  wait_for_transaction_async` using `await asyncio.sleep(poll_interval)`;
  keep the sync version for sync callers. Do not refactor callers.
- File: `aitbc/crypto/secrets.py:271-272` — the rotation scheduler thread
  mutates `SecretManager` state; add a `threading.Lock` around shared-state
  access. No asyncio rework.

### A6: SDK task references (P1) — ✅

- Files: `packages/py/aitbc-agent-sdk/src/aitbc_agent/swarm_coordinator.py:93`,
  `compute_provider.py:169,233,455`
- `asyncio.create_task(...)` results are dropped — tasks can be GC'd and the
  loops silently stop. Store references in an instance `set`/`dict` and
  discard on completion (`task.add_done_callback(self._tasks.discard)`).

---

## Agent B — Applications

### B1: `import_block` validation bypass (P0)

- File: `apps/blockchain-node/src/aitbc_chain/rpc/blocks.py:194-270`
- Route imports through the same validation as
  `sync_block_import._append_block()` (signature, parent, state root, txs).
- Remove the delete-on-hash-conflict path at lines 241–249 — a conflicting
  hash must be a 409, never a delete.
- Regression test: importing a block with a bogus proposer/state root fails.

### B2: `import_chain` chain-wipe (P0)

- File: `apps/blockchain-node/src/aitbc_chain/rpc/sync.py:177-187`
- Require admin auth on the endpoint.
- Validate the import payload *before* any deletion.
- Wrap delete+import in a single DB transaction (one commit or full
  rollback).

### B3: Signature verification actually verifies (P0)

- File: `apps/blockchain-node/src/aitbc_chain/sync_validator.py:37-65` —
  verify the block signature via
  `aitbc.crypto.consensus_signing.verify_block_signature`. If the trusted set
  is empty, fail closed (or rename the function `validate_block_format` and
  audit every caller's assumptions — pick one, document the choice).
- File: `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py:287-288` —
  add `pbft_require_signatures` config flag, default True; only accept
  unsigned messages when explicitly disabled for testing.

### B4: Consensus determinism tiebreakers (P1)

- File: `apps/blockchain-node/src/aitbc_chain/consensus/rotation.py:75-119` —
  add `address` as final tiebreaker to every stake/reputation/score sort
  (`key=lambda v: (-v.stake, v.address)` pattern).
- File: `apps/blockchain-node/src/aitbc_chain/mempool.py:165` — eviction
  tiebreak: `key=lambda t: (t.fee, t.received_at, t.tx_hash)`.

### B5: Persistent replay protection (P0)

- File: `apps/blockchain-node/src/aitbc_chain/state/state_transition.py:42-72`
  — check tx hash against the DB (unique constraint already enforced at
  insert), not only `_processed_tx_hashes`.
- File: `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`
  — persist processed proof hashes (table with unique constraint, or dedup on
  the transfer's `target_tx_hash`); keep the in-memory set as a fast path.

### B6: Bridge/HTLC nonce correctness (P0)

- File: `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py:46-64`
  — increment `sender_account.nonce` on lock.
- File: `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py:119-146`
  — increment sender nonce in `_transfer_balance`.
- Files: `bridge_transfer.py:129-151,218-242` — release/refund txs: use the
  account's real nonce and increment; delete the hardcoded `nonce=0`.
- Regression test: lock → release leaves account nonce at expected value.

### B7: Settlement robustness (P1)

- File: `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement_coordinator.py:76-126`
  — on startup, scan for escrows in non-terminal states and resume or refund
  by timeout. Smallest thing that unsticks funds; no framework.
- File: `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py:242`
  — `escrow_id` from `time.time_ns()` + short uuid suffix.
- File: `settlement.py:787-789` — timeout from `locked_at` when set, falling
  back to `created_at`.

### B8: Bridge monitor fund safety (P0)

- File: `apps/bridge-monitor/src/bridge_monitor/main.py:271-290` — advance
  the block cursor only after the AIT transfer succeeds or is explicitly
  marked for retry.
- File: `main.py:114,242` — replace `int(amount)` truncation with
  `quantize(Decimal("1"), rounding=ROUND_HALF_UP)`; reject deposits below a
  documented minimum (`BRIDGE_MIN_DEPOSIT_AIT`, default 1).
- Replace the loop's `time.sleep(self.poll_interval)` (line ~303) with
  `await asyncio.sleep(...)`.

### B9: Decimal migration completion (P0)

- Files: `apps/trading/src/trading_service/domain/trading.py:213,255,270-273`,
  `domain/inter_chain.py:40,53`, `apps/marketplace/src/marketplace_service/main.py:159,189`,
  `apps/marketplace/.../services/matching_service.py`,
  `apps/wallet/src/wallet_app/bridge/bridge_db.py:25-26`,
  `apps/pool-hub/src/poolhub/repositories/miner_repository.py:177`
- Money fields → `Decimal` with `Column(Numeric(20, 8))` (mirror the v0.10.4
  pool-hub pattern); SQLite `REAL` → `NUMERIC`/`TEXT` with an Alembic
  migration where the table is persistent; remove `float(...)` casts on
  Decimal columns.
- Follow the repo rule: existing DBs get an Alembic migration with
  `if_not_exists=True`-style guards, not just `create_all`.

### B10: Trading settlement/matching locking + idempotency (P1)

- Files: `apps/trading/src/trading_service/routers/settlement.py:55-102`,
  `services/matching_engine.py:73-79`
- `SELECT ... FOR UPDATE` (or `BEGIN IMMEDIATE` on sqlite) around trade status
  transitions and escrow field updates.
- Add idempotency-key support to payment creation
  (`routers/exchange_compat.py:36-62`): reject/return existing on replay.
- Validate `amount > 0` on inter-chain trade creation
  (`routers/inter_chain.py:44-55`).

### B11: Missing rollbacks (P1)

- Files: `apps/trading/src/trading_service/routers/settlement.py:71-73,100-102`,
  `apps/gpu/src/gpu_service/main.py:212-229,598-613,687-701`
- Add `await session.rollback()` in exception handlers that catch after a
  failed commit. Check for the same pattern in the same files while there.

### B12: Auth defaults & defense-in-depth (P0)

- File: `apps/api-gateway/src/api_gateway/main.py:63` —
  `API_GATEWAY_REQUIRE_AUTH` default `"true"`.
- File: `apps/coordinator-api/src/coordinator_api/main.py:287-293` — startup
  assert: `environment == "production"` requires `auth_enabled and not
  test_mode`.
- Files: `contexts/compliance/routers/hipaa.py:37-87`,
  `contexts/tee/routers/attestation.py:39-87`,
  `contexts/governance/routers/economic_proposals.py:35-156` — add explicit
  auth dependencies matching the security matrix; do not rely on middleware
  alone.

### B13: SSRF address validation (P1)

- Files: `apps/coordinator-api/src/coordinator_api/contexts/governance/services/governance_service.py:287`,
  `apps/wallet/src/wallet_app/keystore/persistent_service.py:444`,
  `apps/wallet/src/wallet_app/api_rest.py:183`
- Validate the `address` parameter (existing address-validation util if one
  fits — check `aitbc` address validation first, per v0.10.6 consolidation)
  before interpolating into request URLs.

### B14: Timing-safe login comparison (P1)

- File: `apps/agent-coordinator/src/agent_app/routers/auth.py:52-58` —
  `hmac.compare_digest` for the password comparison.

### B15: Robustness sweep (P2)

- `apps/blockchain-explorer/chain_client.py`, `routers/blocks.py`,
  `apps/coordinator-api/.../infrastructure/services/explorer.py:263-320` —
  sqlite connections via context managers.
- `apps/pool-hub/src/poolhub/services/billing_integration.py:85-196` — wrap
  the per-miner sync loop in one transaction; replace sync
  `self.db.execute(...)` in async paths with the async session pattern used
  elsewhere in the service.
- `apps/coordinator-api/.../contexts/compliance/hipaa.py:60-68` — same
  timezone-direction fix as A3 (normalize the naive side to UTC).

### B16: P2 follow-ups (track, fix if trivial while adjacent)

- `sync_block_import.py` — gate `skip_state_root_validation` behind an
  internal-only caller check.
- `state/state_transition.py:177,184` — guard balance updates against
  BigInt overflow (`> 2**63 - 1`).
- `mempool.py:214-248` — DB mempool: evict before insert under the same lock
  so max-size holds under concurrent adds.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
./venv/bin/python -m pytest tests/integration -q -o addopts=""
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

## Coordination Protocol

- **No shared files in this release.** Agent A stays in `aitbc/` +
  `packages/py/aitbc-agent-sdk`; Agent B stays in `apps/`. The standing
  shared-files list (`aitbc/database/replica.py`,
  `aitbc/network/circuit_breaker.py`, `aitbc/agent_bridge/`) is untouched.
- `packages/py/aitbc-agent-sdk` is assigned to Agent A for this release only
  (packages/ is unassigned in the root role table) — declared here per the
  protocol.
- Blockchain-node files are Agent B's; Agent A must not touch them even for
  type fixes without coordinating in this file first.
- Each non-trivial fix leaves ONE runnable check behind (a small test or
  assert-based self-check), per repo rules. Trivial one-liners need none.
- Regression tests for B1/B2/B3/B6 belong in `apps/blockchain-node/tests/`
  (see v0.5.18 green-baseline convention).

## Release Gate

- [ ] `import_block` rejects invalid blocks; conflicting-hash import is a 409,
      never a delete (regression test).
- [ ] `import_chain` requires admin auth and is atomic (regression test).
- [ ] Block signatures verified in sync; PBFT rejects unsigned by default.
- [ ] Validator rotation and mempool eviction are deterministic across nodes.
- [ ] Tx-hash and bridge-proof dedup survive a node restart.
- [ ] Bridge lock/release/refund and HTLC paths maintain nonce sequences
      (regression test).
- [ ] Bridge monitor never loses a deposit on failure; sub-minimum deposits
      rejected.
- [ ] No `float` money fields remain in trading/marketplace/wallet-bridge;
      Alembic migrations applied for existing DBs.
- [ ] Settlement double-match/double-settle not reproducible under concurrent
      requests; idempotency keys honored.
- [ ] API Gateway and coordinator-api fail closed on missing auth config.
- [ ] HIPAA/TEE/economic-proposal routers reject unauthenticated requests
      with middleware disabled.
- [ ] No `==` on secrets/hashes in auth paths; TEE functions require a
      secret.
- [ ] `ruff`, `mypy aitbc/`, unit + integration suites green.

*Generated with [Devin](https://devin.ai)*
