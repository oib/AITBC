# PG-MIGRATIONS-1 — progress ledger (append only)

Prompt: `tasks/PG-MIGRATIONS-1-prompt.md`. Throwaway Postgres on node2 scratch only; no live database touched. Repo baseline `465f39eeb`. Gitea is down — scratch clone on node2 comes from its local `/opt/aitbc` (same commit), not a fetch.

## 2026-10-19 ~10:1x CEST — Phase 0 inventory (read-only; report before any run)

### The seven trees (all single heads — no broken/multi-head finding)

| service | tree dir | revs | head | env.py URL source | target_metadata |
|---|---|---|---|---|---|
| blockchain-node | `migrations/` | 17 | `f7a3c5e9b1d2` | `DATABASE_URL` / `SQLITE_URL` else `settings.db_path` (sqlite, **not the live path**) | `chain_metadata` |
| coordinator-api | `alembic/` | 41 | `c3a91f7e5b02` | `DATABASE_URL`/`SQLITE_URL` override of `app_settings.database.effective_url` | `SQLModel.metadata` |
| edge | `alembic/` | 1 | `e1c47b09f2a6` | `settings.database.effective_url` — **explicitly does NOT read `DATABASE_URL`** (env.py docstring) | `SQLModel.metadata` |
| governance | `alembic/` | 3 | `003` | `DB_TYPE=postgresql`+`DB_HOST/PORT/NAME/USER/PASS`, else `DATABASE_URL` | `governance_metadata` |
| gpu | `alembic/` | 2 | `4d6e9c8a1b52` | `DATABASE_URL` else `DATA_DIR/data/gpu_service.db` | `gpu_metadata` |
| pool-hub | `migrations/` | 7 | `21da5cfdcc95` | `DATABASE_URL`/`SQLITE_URL`/`POOLHUB_POSTGRES_DSN` | `Base.metadata` |
| trading | `alembic/` | 4 | `004_v024_exchange_payment` | `DB_TYPE`+`DB_*` or `DATABASE_URL` | `trading_metadata` |

### Dialect-aware revisions (Postgres constructs or dialect branches)

- **blockchain-node**: `b7f3c1a90d24` (`payload ->> 'job_id'` expression index), `d4e8b91c0a37` v23 NUMERIC w/ `postgresql_using`
- **coordinator-api**: `c7d1f4a9e230`, `f2b6c04a91d8`, `a3e7c15b8d94` (v23 NUMERIC w/ `postgresql_using`), `2024_01_10` (JSONB), +9 more with `dialect.name` branches
- **edge**: `e1c47b09f2a6` (v23 NUMERIC) — the only revision in the tree
- **governance**: `001`, `002` dialect branches
- **gpu**: `b8f3a2c91d04` (v23 NUMERIC)
- **pool-hub**: `e5d4f8a9b0c1` dialect branch
- **trading**: `002` dialect branch

### How schemas actually get built (who applies what)

- Canonical migrator: `scripts/deployment/run-migrations.sh` (update.sh step 5 / deploy.sh) — per service it reads `DATABASE_URL` from `/etc/aitbc/aitbc-<svc>.env`, stops the service, `alembic upgrade head`. **blockchain-node is skipped unless `DATABASE_URL` is explicitly named** (V23-49: its default `settings.db_path` points at a path no node uses; a bare upgrade "succeeds" on an empty file).
- **coordinator-api additionally migrates at every start** — hub unit `ExecStartPre=… alembic upgrade head` confirmed live; no other unit on hub carries an ExecStartPre alembic (edge/governance/gpu/pool-hub/trading/blockchain-node all 0).
- Live schema truth per service:
  - coordinator-api: **alembic only** (`storage/db.py` comment: "Schema management is Alembic's job. Do not call create_all here").
  - edge: **`create_all` at startup** (`storage.py:40`) — its alembic tree is not the live builder.
  - governance: `create_all` for SQLite, alembic for PostgreSQL (`storage.py:68-73`).
  - gpu: `create_all` + ALTER-TABLE add-column fix-ups (`storage.py:80-93`).
  - pool-hub: `create_all` in `main.py:37` + alembic (its PG DB is at head — below).
  - trading: **alembic only** (`storage.py:27` comment).
  - blockchain-node: **three layers** — `chain_metadata.create_all` (new tables) + `_migrate_existing_columns` add-missing-column fix-up (`database.py:~333`) + alembic (the rest: indexes/constraints). Alembic alone does NOT reproduce the live chain schema — confirms the director's suspicion.

### Postgres support in service code / SQLite-only code

- PG-capable engines: coordinator-api (`postgresql+asyncpg` URL translation), edge (`+asyncpg`), governance (`DB_TYPE=postgresql` → `+asyncpg`), gpu (`DATABASE_URL` into `create_async_engine`), pool-hub (**Postgres-first default** `postgresql+asyncpg://…127.0.0.1:5432/aitbc`, models import `PGUUID`), trading (`DATABASE_URL` → `create_async_engine`).
- SQLite-only markers (`PRAGMA`/`INSERT OR`/`sqlite_master`/`rowid`): **blockchain-node only** — 15 hits (`database.py`×7, `side_root_shadow`×3, `guardian_contract`×2, `mempool`, `messaging_metrics`, `block_deltas`). All six service trees clean.

### node2 throwaway feasibility

`/usr/lib/postgresql/17/bin/initdb` + `pg_ctl` present; `psql 17.11`; live `postgresql` service active; venv has alembic 1.18.4, psycopg2, asyncpg, SQLAlchemy 2.0.50. `initdb` refuses root — will run as the `postgres` user into a `/tmp` scratch dir, unix socket + high port, trust on loopback. Feasible without touching the live cluster.

### hub Postgres names-and-sizes (peer auth via `su postgres`; names + counts only)

| database | size | tables | contents |
|---|---|---|---|
| aitbc | 7998 kB | 10 | poolhub-layout tables, **all 0 rows** (legacy duplicate) |
| aitbc_ai | 7582 kB | 0 | empty shell |
| aitbc_coordinator | 7582 kB | 0 | empty shell |
| aitbc_exchange | 7582 kB | 0 | empty shell |
| aitbc_governance | 7582 kB | 0 | empty shell |
| aitbc_gpu | 7582 kB | 0 | empty shell |
| aitbc_marketplace | 8478 kB | 14 | legacy marketplace tables, **all 0 rows** |
| aitbc_mempool | 7734 kB | 1 | `mempool` 0 rows |
| aitbc_poolhub | **12 MB** | 11 | **live**: `sla_metrics` 10227, `capacity_snapshots` 10227, `sla_violations` 11, `miner_status` 1, `service_configs` 1, `miners` 1, `alembic_version` = **`21da5cfdcc95` (= head)** |
| aitbc_trading | 7582 kB | 0 | empty shell |
| aitbc_wallet | 7582 kB | 0 | empty shell |

**Phase 0 conclusion for D8:** production Postgres usage = **pool-hub only**, and its tree is verifiably at head. The "eight service databases" on hub are empty shells plus two stale legacy schemas — the PG estate is vestigial except pool-hub. The readiness question is therefore about *trees*, not *databases*: which trees CAN run on PG if a service moves.

## 2026-10-19 09:4x-10:05 CEST — Phases 1-3 results

Scratch: node2 throwaway PG17 cluster (`initdb` as postgres, unix socket `/tmp/pgmig-pg`, port 55432, `listen_addresses=''`, trust auth, `fsync=off`), source exported via `git archive 465f39eeb` to `/tmp/pgmig-repo` (gitea down — LAN clone impossible; note node2's local main is **32 commits behind** `origin/main`, not ahead — the earlier "unpushed" read was wrong).

### Phase 1.1 — `alembic upgrade head` on empty DB

| tree | PostgreSQL | SQLite |
|---|---|---|
| blockchain-node (17) | **FAIL @ `fix_transaction_block_foreign_key`** — emits `DATETIME` literal into `create_table`; PG has no such type | **PASS** (but on empty DB a revision aborts with `Cannot tell which chain the escrow rows belong to` unless `CHAIN_ID` env is set — chain-id inference needs blocks/accounts) |
| coordinator-api (41) | **FAIL @ `add_global_marketplace`** — `001` creates `marketplace_regions` with `sa.Enum('ACTIVE',…)` (`regionstatus`); this revision's `create_table(if_not_exists=True)` skips, then its seed INSERTs lowercase `'active'` → `InvalidTextRepresentation`. Works on sqlite because enums are unchecked VARCHAR | **PASS** to `c3a91f7e5b02` |
| edge (1) | **PASS** (`ADAPTER=postgresql`+`URL=` — ignores `DATABASE_URL` entirely, confirmed; an earlier run silently targeted the node's own `/var/lib/aitbc/data/aitbc_edge.db` — no-op since already at head, mtime unchanged, no live change) | PASS |
| governance (3) | **PASS** | PASS |
| gpu (2) | **FAIL @ `4d6e9c8a1b52`** — raw `PRAGMA table_info(gpu_registry)` | **FAIL** — `ALTER TABLE gpu_registry` on a table no revision creates; the tree assumes `create_all` built the schema first |
| pool-hub (7) | **PASS** — but env.py builds `create_async_engine`, so it **requires `postgresql+asyncpg://`** (psycopg2 URL = InvalidRequestError) | **FAIL @ `d4c3e7f8a9b0`** — unguarded `ALTER COLUMN … SET NOT NULL` (PG syntax) |
| trading (4) | **PASS** | PASS |

### Phase 1.2 — `alembic check` (schema vs models, PG)

- **governance**: heavy drift — DOUBLE_PRECISION vs Numeric(20,8) on money columns, NULL/NOT-NULL diffs, missing indexes (`ix_votes_*`, `ix_delegations_*`), TIMESTAMP vs DateTime.
- **trading**: minor — `exchange_payment.idempotency_key` is a unique index; models want UniqueConstraint.
- **edge**: near-total drift — alembic head creates **zero** tables; the whole model set (~10 tables incl. `marketplaceoffer`, `payment_escrows`, `bridge_requests`, `compute_requests`) exists only via `create_all`. The tree is vestigial.
- **pool-hub**: `service_configs` table missing from alembic (prod DB has it — built by `create_all`), VARCHAR(36)→UUID diffs, index/nullability drift.

### Phase 1.3 — downgrade base → upgrade head (PG)

- governance: **clean round-trip**; edge: clean (trivial).
- trading: **FAIL @ 002→001** — its downgrade `ALTER`s `trade_agreements`, which belongs to 003 and was already dropped by 003's downgrade. Cross-revision coupling bug.
- pool-hub: **FAIL @ b2a1c4d5e6f7→a58c1f3b3e87** — `DROP INDEX ix_sla_violations_created_at` which doesn't exist (name mismatch in the down path).

### Phase 1.4 — create_all vs alembic (same dialect)

governance: identical table sets (9). trading: alembic head ⊇ create_all (plus legacy `inter_chain_trades`,`island_registry`). edge: alembic=0 tables vs create_all=full schema. pool-hub: alembic misses `service_configs` (prod schema = alembic + create_all).

### Phase 1.5 — per-tree migration tests

`test_migration_graph.py` (chain): 2 passed. `test_alembic_stamp_commits.py` (pool-hub): 1 passed. `test_migrations.py` (coordinator): the `test_full_downgrade_roundtrip_sweep` suite ran ~40min, completed with warnings, no failures shown.

### Phase 2 — NUMERIC + `->>` revisions in isolation on PG (single-rev trees, synthetic pre-schemas; no stamping of the real chains, per operator decision)

- `d4e8b91c0a37`, `b8f3a2c91d04`, `a3e7c15b8d94`, `f2b6c04a91d8`: all convert `float8`→`numeric(20,8)` via `postgresql_using "<col>::numeric(20,8)"`, guarded by `_table_exists`/`_column_exists`. Verified on synthetic rows: `0.1`→`0.10000000` (binary noise rounded clean), `59999.99999999` exact, NULL preserved on nullable `market_price_usd`, and the float8-limited `412345678901.12345678`→`412345678901.123` — **the migration preserves exactly what float8 held; the precision loss predates it**.
- `b7f3c1a90d24` (`payload ->> 'job_id'` index): creates `ix_transaction_payload_job_id ON "transaction" ((payload ->> 'job_id'))`; `EXPLAIN` shows `Index Scan using ix_transaction_payload_job_id` — the expression matches the motivating query exactly.

### Phase 3 — service suites "pointed at PG" (operator: run all anyway)

**The suites do not honor PG env vars — by design.** `pg_stat` shows zero test writes in any pgmig_* db.
- `governance/tests/conftest.py:27` — `os.environ.pop("DATABASE_URL")` ("the suite is SQLite").
- `gpu/tests/conftest.py:19-21` — pops `DATABASE_URL`/`DB_TYPE` (V23-74: defends against deployed env pointing at a live DB).
- `edge` — ignores `DATABASE_URL` at the settings layer entirely.
- Only blockchain-node's conftest has a `requires_postgres` marker + TCP probe (`DATABASE_URL`/`MEMPOOL_DB_URL`).
- Results anyway: edge 11✓, governance 110✓, gpu 15✓+1 skip(Redis), pool-hub 45✓, trading suite passed standalone but errored under the PG env block (fixture/env interaction), coordinator 11✓. **No suite exercised a single PG query — there is zero PG test coverage.**

### Phase 4 — readiness table

| service | verdict | blocker |
|---|---|---|
| blockchain-node | **not Postgres-capable** | `DATETIME` literal @ `fix_transaction_block_foreign_key` (rev 3/17, blocks the tree); 15 SQLite-only sites in src; chain stays SQLite anyway |
| coordinator-api | **needs fix** | `add_global_marketplace` enum case (`'active'` vs `'ACTIVE'`); everything downstream incl. NUMERIC trio unverified until fixed |
| edge | **needs fix** | alembic tree vestigial (0 tables); real schema is `create_all` — decide whether the tree is maintained at all |
| governance | **needs fix** | clean upgrade+round-trip but heavy schema↔models drift |
| gpu | **needs fix** | `PRAGMA` @ `4d6e9c8a1b52`; sqlite side also fails (needs `create_all` baseline) |
| pool-hub | **needs fix** | PG-clean upgrade (asyncpg only) but broken `b2a1c4d5e6f7` downgrade, `d4c3e7f8a9b0` sqlite breakage, `service_configs` drift — **production-proven at head anyway** |
| trading | **needs fix** | clean upgrade, minor drift, broken `002` downgrade |

**Nothing is fully "ready"** under the strict definition. Proposed fix rows (separate tasks, none done here): `PG-FIX-CHAIN-1` (DATETIME→dialect-aware/batch), `PG-FIX-COORD-1` (enum case), `PG-FIX-GPU-1` (PRAGMA→inspect), `PG-FIX-POOL-1` (downgrade index name), `PG-FIX-POOL-2` (unguarded SET NOT NULL), `PG-FIX-TRADING-1` (002 downgrade cross-revision), plus a per-service `alembic check` reconciliation row and a "does PG get test coverage" question for D8 (suites strip PG env deliberately).

**D8 implication:** the only service on PG in production is pool-hub, and it got there via alembic+create_all with a broken down-path and drift — i.e. **even the one working deployment wouldn't reproduce from migrations alone**. Any D8 "yes" needs the fixes first; chain.db stays SQLite regardless (deep coupling confirmed).

Cleanup: cluster + scratch dirs to be destroyed next. **No live database, host, or service was changed** — the only unexpected touch was edge's env.py falling back to node2's own `/var/lib/aitbc/data/aitbc_edge.db` on the first run (no-op: already at head, mtime Oct 2 unchanged, verified).

## 2026-10-19 ~10:1x CEST — detailed issue catalogue (SQLite→PG)

### A. Revision files that break on PostgreSQL

| # | tree / revision | defect | PG error | why sqlite hides it | fix sketch |
|---|---|---|---|---|---|
| A1 | chain `fix_transaction_block_foreign_key` (rev 3/17) | `create_table` emits literal `DATETIME` | `Type "datetime" does not exist` | sqlite accepts DATETIME as an affinity name | `sa.DateTime()` type object, or `batch_alter_table` — and everything after rev 3 stays unreachable until this lands |
| A2 | coordinator `add_global_marketplace` | seed INSERT `'active'` vs `regionstatus` enum created by `001` with `'ACTIVE','INACTIVE','MAINTENANCE'` (PG enums case-sensitive); `create_table(if_not_exists=True)` silently skips since the table exists | `InvalidTextRepresentation` | sqlite stores enums as unchecked VARCHAR — any case passes | `'active'`→`'ACTIVE'` in the seed, or lowercase the enum consistently |
| A3 | gpu `4d6e9c8a1b52` | raw `PRAGMA table_info(gpu_registry)` to check column presence | `SyntaxError near "PRAGMA"` | PRAGMA is sqlite-native | `sa.inspect(bind).get_columns()` like the sibling rev's `_column_exists` |
| A4 | chain tree, empty DB | a revision aborts `Cannot tell which chain the escrow rows belong to` unless `CHAIN_ID` env is set | (RuntimeError, sqlite too) | live DBs have blocks/accounts to infer from | doc/env requirement, or default on empty |

### B. Broken down-revisions (PG)

| # | revision | defect | error |
|---|---|---|---|
| B1 | trading `002→001` | downgrades `ALTER COLUMN ... TYPE FLOAT` on `trade_agreements` — a table created by `003`, already dropped by its downgrade | `UndefinedTable` |
| B2 | pool-hub `b2a1c4d5e6f7→a58c1f3b3e87` | `DROP INDEX ix_sla_violations_created_at` — index doesn't exist under that name | `UndefinedObject` |

### C. Schema↔model drift (`alembic check`)

| # | tree | drift |
|---|---|---|
| C1 | governance | money cols still DOUBLE_PRECISION (models want Numeric(20,8)); missing `ix_votes_*`/`ix_delegations_*` indexes; TIMESTAMP vs DateTime; nullability diffs |
| C2 | trading | `exchange_payment.idempotency_key`: unique index vs model UniqueConstraint (minor) |
| C3 | edge | alembic head creates **0 tables**; ~10 model tables (`marketplaceoffer`, `payment_escrows`, `bridge_requests`, `compute_requests`…) exist only via `create_all` — tree is vestigial |
| C4 | pool-hub | `service_configs` missing from alembic (prod has it via `create_all`); VARCHAR(36)→UUID on sla_* ids; index/nullability drift |

### D. Engine/env plumbing traps

| # | service | trap |
|---|---|---|
| D1 | edge | env.py **ignores `DATABASE_URL`** — real vars are `ADAPTER`/`URL` (or `DATABASE_URL`+`DATABASE_ADAPTER` together); V23-47 footgun verified live: a run silently targeted node2's deployed `aitbc_edge.db` (no-op only because already at head) |
| D2 | pool-hub | env.py builds `create_async_engine` — **requires `postgresql+asyncpg://`**; a `+psycopg2` URL raises InvalidRequestError |
| D3 | governance/trading | `DB_TYPE=postgresql` composes URL from `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS` — a unix-socket path can't be expressed as a host; DATABASE_URL path needed for sockets |
| D4 | coordinator | `DATABASE_URL`/`SQLITE_URL` override works but env.py warns it can diverge from `app_settings.database.effective_url` — two sources of truth |

### E. "Migrations alone don't build the schema" (structural)

| # | service | live schema built by |
|---|---|---|
| E1 | blockchain-node | three layers: `chain_metadata.create_all` (new tables) + `_migrate_existing_columns` add-column fix-up (`database.py:~333`) + alembic — alembic alone provably insufficient |
| E2 | gpu | `create_all` + ALTER-TABLE fix-ups (`storage.py:80-93`); alembic tree fails on empty because it assumes `gpu_registry` pre-exists |
| E3 | edge | `create_all` only at `storage.py:40`; alembic vestigial |
| E4 | governance | `create_all` (sqlite) / alembic (PG) — split brain at `storage.py:68-73` |
| E5 | pool-hub | `create_all` (`main.py:37`) + alembic — prod `aitbc_poolhub` at head but would NOT reproduce from migrations alone (`service_configs` missing) |
| E6 | coordinator, trading | declared alembic-only ("Do not call create_all") — but drift (C1/C2) means models evolved past the tree |
| E7 | all | only coordinator-api migrates at service start (`ExecStartPre`, verified on hub); everything else migrates via `run-migrations.sh` at update/deploy time |

### F. SQLite-only runtime code (service, not just migrations)

- **blockchain-node only** — 15 sites: `database.py`×7 (PRAGMA/identifier quoting/ALTER), `side_root_shadow`×3 (PRAGMA table_info), `guardian_contract`×2, `mempool`×1 (`PRAGMA table_info`+`ALTER TABLE mempool ADD COLUMN`), `messaging_metrics`×1, `block_deltas`×1 (`INSERT OR`/sqlite idioms). The six service trees are clean.
- `run-migrations.sh` deliberately **skips blockchain-node unless DATABASE_URL is named** (V23-49: bare upgrade "succeeds" on an empty default path).

### G. Zero PG test coverage (structural)

- `governance/tests/conftest.py:27`: `os.environ.pop("DATABASE_URL")` — "the suite is SQLite".
- `gpu/tests/conftest.py:19-21`: pops `DATABASE_URL`/`DB_TYPE` (V23-74 deliberately defends against deployed env).
- `edge`: ignores `DATABASE_URL` at the settings layer entirely.
- Only `blockchain-node/tests/conftest.py` has a `requires_postgres` marker + TCP probe — the sole mechanism that could run PG-aware tests.
- `tests/conftest_testcontainers.py` has a `PostgresContainer` fixture — needs docker/podman, absent on every node.
- `pg_stat` on the throwaway cluster: **zero test writes** — every suite ran its own sqlite fixtures.

### H. What already works on PG (verified, not just absent-of-failure)

- All four v23 NUMERIC revisions (`d4e8b91c0a37`, `b8f3a2c91d04`, `a3e7c15b8d94`, `f2b6c04a91d8`): `postgresql_using "<col>::numeric(20,8)"`, `_table_exists`/`_column_exists` guards, sqlite `batch_alter_table` fallback. Isolated-run verified: `0.1`→`0.10000000`, `59999.99999999` exact, NULL preserved; only pre-existing float8 loss (`412345678901.12345678`→`...123`) surfaces.
- `b7f3c1a90d24`: dual-dialect `->> 'job_id'` (PG) / `json_extract` (sqlite); `EXPLAIN` shows the planner uses `ix_transaction_payload_job_id`.
- All seven trees have **single heads** — no broken/multi-head chains.
- `governance` tree: clean upgrade AND clean downgrade round-trip on PG (drift is model-side, not migration-side).
- `pool-hub` production `aitbc_poolhub` sits at head `21da5cfdcc95` — the only service actually running PG.

## 2026-10-19 10:21:12 CEST — source audit and corrections to the issue catalogue

Timestamp: `date --iso-8601=seconds` on IDE host `at1` returned `2026-10-19T10:21:12+02:00`. Scope: read-only source review at `465f39eeb6ebe2694829180786633b4ec88f8f65` and review of the saved execution transcript (`/home/oib/.local/share/devin/cli/summaries/history_a69ecd8ca5d04b84.md`). No migration matrix or live-host inspection was repeated. The previous operator verification status remains **verified partly**. This addendum corrects interpretations above; it does not add new PostgreSQL execution evidence.

### Confirmed causes and catalogue corrections

- **Pool-hub B2 is duplicate index ownership, not a spelling mismatch.** `b2a1c4d5e6f7` creates `ix_sla_metrics_miner_id`, `ix_sla_violations_miner_id`, and `ix_sla_violations_created_at`. Its successor `c3b2d6e7f8a9` includes those same names in `_INDEXES`, uses `if_not_exists=True` on upgrade, and unconditionally drops them on downgrade. The later downgrade therefore removes indexes belonging to its predecessor; the predecessor then fails dropping them again. Fix ownership in `c3b2d6e7f8a9`. Merely renaming an index or ignoring the second DROP would leave the intermediate revision missing indexes it is supposed to have. Sources: `apps/pool-hub/migrations/versions/c3b2d6e7f8a9_add_poolhub_indexes.py:23-42`; `b2a1c4d5e6f7_add_sla_and_capacity_tables.py:53-82,106-120`.
- **Edge has an active alteration-only migration, with no bootstrap baseline.** `e1c47b09f2a6` converts money columns on existing tables and skips absent tables. Empty-DB upgrade succeeds because every operation is skipped; this does not make the tree unused or vestigial. Its missing creation baseline is the issue. Source: `apps/edge/alembic/versions/e1c47b09f2a6_v23_edge_money_columns_to_numeric.py:54-95`. GPU has the same baseline gap plus its separately confirmed raw-PRAGMA failure.
- **Edge ignores `DATABASE_URL` alone, not every use of that variable.** The shared `DatabaseConfig._load_legacy_database_url` also accepts `DATABASE_URL` with a matching `DATABASE_ADAPTER` when no explicit `url` is present. A plain `postgresql://...` URL with adapter `postgresql` satisfies that branch. Bare `URL` is the direct setting. The edge env.py/config comments claiming that `DATABASE_URL` has no effect at all overstate the actual code. Source: `packages/aitbc-shared/aitbc_shared/core/config.py:39-77`. Its `_resolved_target` also prints the URL without password redaction (`apps/edge/alembic/env.py:61-68`), unlike pool-hub.
- **A4 is an explicit-chain configuration requirement affecting SQLite too.** The exact revision is `c9a4f1e2b73d`; it infers from blocks/accounts or requires `CHAIN_ID`/`SUPPORTED_CHAINS`. Rehearsal must supply the intended chain id. Adding an arbitrary default would hide a target-selection mistake. Source: `apps/blockchain-node/migrations/versions/c9a4f1e2b73d_escrow_chain_scoped_account_fk.py:88-111,140-143`.
- **Pool-hub's SQLite ALTER failure is a SQLite portability defect.** It does not block its already-passing PostgreSQL upgrade. Keep it separate from PG adoption and from the production PG deployment's recovery defects.
- **Schema drift has different consequences.** Governance's FLOAT-versus-NUMERIC money fields and pool-hub's absent `service_configs` are substantive. A plain unique index versus a unique constraint on trading's `idempotency_key` can enforce the same uniqueness rule; the catalog representation still differs. TIMESTAMP/DateTime names alone do not establish a behavioral mismatch without checking timezone and other attributes. Coordinator's blocked PG upgrade did not yield a completed PG schema/model comparison. The earlier E6 reference to governance's C1 as evidence about coordinator was incorrect.

### Additional source findings

| Area | Finding and implication |
|---|---|
| Trading database selection | `alembic/env.py:25-37` honors `DB_TYPE=postgresql` and `DB_*`, while `src/trading_service/storage.py:16-21` reads only `DATABASE_URL`. With only `DB_TYPE`/`DB_*` supplied, Alembic selects PostgreSQL while the application keeps its SQLite default. If both are supplied inconsistently, they can select different targets. The earlier claim that trading uniformly supports either configuration route was wrong. |
| Governance database selection | Runtime `_build_database_url` percent-encodes `DB_USER`/`DB_PASS`, but Alembic interpolates the raw strings. Reserved URL characters can therefore be parsed differently. Also, startup's `create_all` decision is based on `DB_TYPE`, not the effective dialect: a PG `DATABASE_URL` with `DB_TYPE` unset still takes `create_all`. Sources: `src/governance_service/storage.py:25-73`; `alembic/env.py:16-34`. |
| Chain runtime | `get_engine` explicitly constructs SQLite engines in both branches; changing a migration's `DATETIME` literal cannot switch the chain engine. The original “15 sites” was a search result, not a complete count of independent blockers. Source: `apps/blockchain-node/src/aitbc_chain/database.py:124-173`. |
| Later chain migration | `9f8e7d6c5b4a` uses raw `json_extract` and `INSERT OR IGNORE`. The query path is reached when transaction `type` and `value` columns exist; an Alembic-only empty schema skips it. This is a further PG incompatibility visible in source, not a newly reproduced migration failure. Source: `apps/blockchain-node/migrations/versions/9f8e7d6c5b4a_backfill_escrows_from_lock_tx.py:45-94,134-149`. |
| Actual SQLite-to-PG copying | `apps/coordinator-api/scripts/migrate_to_postgresql.py` is not a validated migration path. It drops target tables and builds a separate hand-written schema (`37-47`); creates indexes on `marketoffer`/`marketbid` although it creates `marketplaceoffer`/`marketplacebid` (`125-148,186-188`); and skips several tables in its own migration list because its allowlist excludes them (`209-288`). `SELECT *` values are passed positionally into fixed INSERT column lists (`292-324`). These are source findings; the script was not executed. Passing Alembic does not validate this data-transfer tool. |

The shared defect is disagreement between schema creation, migration history, and runtime database selection. A migration can report success on the wrong database, or advance to head after skipping all absent tables. A head stamp therefore needs a schema check and an application operation against that same target.

### Evidence limits: NUMERIC and test coverage

The previous claim that the large-value result “preserves exactly what float8 held” is withdrawn. A local standard-library arithmetic check of the stated synthetic input gave:

| Representation | Value |
|---|---|
| Stated synthetic decimal input | `412345678901.12345678` |
| Exact binary64 representation (`Decimal.from_float(float(input))`) | `412345678901.12347412109375` |
| That binary64 value rounded to eight decimal places | `412345678901.12347412` |
| Previously recorded PostgreSQL NUMERIC result | `412345678901.12300000` |

The recorded result differs from that binary64 value by `-0.00047412109375`; float storage alone does not explain the displayed result. This arithmetic check does not reconstruct a missing pre-cast database capture or isolate the conversion step responsible. The existing record supports successful conversion of the tested columns, preservation of the tested NULL, and the displayed small-value outcomes. It does **not** prove losslessness for arbitrary money values or that all large-value loss predates conversion. `NUMERIC(20,8)` rounds to eight fractional digits and has a finite range. Follow-up needs captured before/after values, an explicit expected rounding rule, and boundary/overflow cases.

There is also a **Phase 2 coverage gap**: the prompt specifically named coordinator revision `c7d1f4a9e230`. It was copied into the isolated-test setup, but the recorded successful runs/results cover `d4e8b91c0a37`, GPU `b8f3a2c91d04`, `a3e7c15b8d94`, and `f2b6c04a91d8`. No successful data exercise of `c7d1f4a9e230` is recorded. Do not treat GPU's result as coverage of the coordinator revision, or an isolated revision result as proof of its whole migration chain.

“Zero PostgreSQL coverage anywhere” was too broad. Governance/GPU explicitly sanitize deployed DB variables; coordinator, pool-hub and trading have SQLite fixtures; PG-related test infrastructure also exists. Zero observed test writes alone cannot establish zero SQL reads. The supported conclusion is: **the recorded service-suite runs did not demonstrate PostgreSQL service integration coverage**. Keep the protection against inherited live URLs and add an explicit disposable-PG test path that asserts its dialect/target and exercises real writes and reads. The absence of Docker/Podman was established for node2 in this task, not every host.

### Consequences and proposed order

1. **Reset preparation:** rehearse the actual fresh-SQLite initialization and service-start sequence, including the explicit `bc-2` chain context, GPU/edge schema creation, and coordinator/trading migrations. A no-PG-moves decision does not by itself validate empty-database startup. Pool-hub remains a separate existing-PG case under the D8 recommendation; any chain-specific carry-over still belongs to the reset plan.
2. **Before another PG rehearsal:** make application and migrator target resolution agree, reject unintended targets, and redact target logging. Use disposable databases through explicit fixtures rather than ambient production configuration.
3. **Make schemas reproducible per service:** provide defined empty-DB baselines for GPU/edge; reconcile governance and pool-hub's substantive drift; fix the coordinator enum seed and both downgrade ownership errors. A new revision after a failing historical revision cannot repair empty-to-head execution. Corrections to already-applied history also do not repair existing databases automatically; existing-schema reconciliation needs its own supported path.
4. **Prove behavior and any data transfer:** complete the missing NUMERIC coverage, test both empty and representative populated schemas, verify actual service operations on PG, and rehearse backup/restore and cutover reconciliation. Full downgrade-to-base testing does not substitute for production recovery, especially across lossy NUMERIC-to-FLOAT conversions.

The six proposed fix rows cover individual defects but omit baseline creation, target-resolution mismatches, substantive schema reconciliation, the data-copy tool, and real PG integration coverage. They remain proposals, not registered work. Trading appears to have the narrowest schema repair among new PG candidates, but its target mismatch and missing PG integration evidence still need resolution. Chain PG support is a separate storage-engine project. The evidence continues to support **no new database moves during the reset**; it does not imply that the already-running pool-hub PG service is unusable.
