## Agent B P1 product-gap sprint (hub.aitbc)

- Branch: `feature/agent-b-p1-sprint` on `hub.aitbc`, created from gitea `main` (`7bda4c91d`).
- Owner: Agent B (hub.aitbc / customer + docs + governance + web dashboards).
- [x] Refresh `docs/DESIGN_CYCLE.md` staleness (P2.3–P2.7 shipped; step 2/5/9/10 gaps closed/clarified).
- [x] Update `TASKLIST.md` with branch and current state.
- [x] P1.2 — web customer and shop dashboards.
  - Added `website/customer-dashboard.html`, `website/shop-dashboard.html`,
    `website/dashboard.js`, and `examples/nginx/nginx-aitbc.conf.example`
    routes for `/dashboard/` and `/shop/`.
  - Live nginx config on `hub.aitbc` updated with `/v1/jobs`, `/v1/miners/`,
    `/v1/monitoring/`, `/v1/wallets`, `/v1/chains/`, `/v1/gpu/` routes.
  - Customer and shop pages serve; `/v1/wallets` and `/v1/marketplace/offer`
    populate; coordinator endpoints require auth and degrade gracefully.
- [x] P1.7 — governance parameter change end-to-end live validation.
  - `propose -> vote -> close -> execute` cycled for `prop_9d1dfbca` on hub.
  - Marketplace `matching_algorithm` set to `reputation` via
    `/v1/marketplace/parameters/apply` (200 OK in governance log).
  - Temporary `GOVERNANCE_TIMELOCK_BLOCKS=0` / `GOVERNANCE_VOTING_PERIOD_BLOCKS=0`
    drop-in removed after validation; service restored to 43200/7200.
- [x] P1.3a — bridge custodian doc + multi-sig config (hub side).
  - Added `apps/exchange/simple_exchange/config.py` and `.env.example`.
  - Added `docs/security/bridge-custodian.md`.
  - Exchange `v1/bridge/status` and `v1/cross-chain/rates` now return
    custodian/multisig fields.
  - Live validation: exchange service restarted on hub, status endpoint
    returns new fields.

## P1 implementation (current session)

- [x] P1.8 — honest rewrite of docs/architecture/1_system-flow.md
- [x] P1.5 — aitbc ai submit --wait (plus base-URL /v1 normalisation)
- [x] P1.6 — island credential/secrets ownership for aitbc user
- [x] P1.1 Phase A — reputation sort in aitbc market list
- [x] P1.2 — customer and shop dashboard CLI commands
- [x] P1.7 — governance close proposal; propose → vote → close → execute lifecycle
  - Code, CLI and tests committed.
  - Live propose -> vote -> close -> execute validated on aitbc3 after dropping and recreating the governance DB.
    (invalid page in block 4 of relation base/16399/2610).
- [x] P1.1 Phase B — reputation-aware job dispatch
  - Implemented and live-validated on `aitbc3` in `fdbd17f5c` (2026-08-21).
  - Coordinator dispatch now respects `min_reputation` and defers jobs to higher-reputation online miners.
  - CLI `aitbc ai submit --min-reputation` exposed.
  - Regression tests added in this commit.
- [x] P1.3 — bridge Merkle/multisig or trusted-custodian documentation
- [x] P1.4 — MultiValidatorPoA/PBFT soak and single-proposer dependence
- [x] Step 7 settlement hardening (escrow payout correctness), 2026-08-22
  - Settlement key/address validated before escrow state is mutated; a mismatch is
    refused instead of producing a 403 and an unpaid provider.
  - Release is settled on-chain *before* `released_at` is persisted; an unsettled
    release returns `success: false` / `settlement_status: unsettled` and the
    coordinator honours that instead of marking the payment released.
  - In-memory release is rolled back when settlement does not land, under a
    per-contract lock, leaving the contract retryable in `JOB_COMPLETED`.
  - `ESCROW_RELEASE` made deterministic so a retry at the same nonce is deduplicated
    by the mempool; this closed a real double-pay window.
  - Settled-release lookup + server-side `job_id` filter on `/rpc/transactions`
    (alembic `b7f3c1a90d24` adds the payload expression index).
  - `SettlementReconciler` retries stuck payouts; **disabled by default**
    (`ESCROW_RECONCILER_ENABLED`).
  - `aitbc auth login` honours `AITBC_WALLET_DIR`, so the documented validation flow
    reproduces on a hub node where wallets live in `/var/lib/aitbc/wallets`.
  - Live-validated end-to-end: job `e72705b6d0274e13bc8a340896f0e006`, release tx
    `0xe733a8106e93940500ca320da830edd5bf4e9a8b1eb94239476fb105b9cccf36`.

### Open follow-ups

- [x] `b7f3c1a90d24` applied on hub (2026-08-22). The chain DB is **SQLite**
      (`/var/lib/aitbc/data/<chain_id>/chain.db`), not Postgres, and had no
      `alembic_version` at all, so it was stamped at `d4e8b91c0a37` first. Pass
      `DATABASE_URL` explicitly or alembic targets the wrong file (see `env.py` V23-49).
- [x] Apply `b7f3c1a90d24` on `aitbc3` — already at `c9a4f1e2b73d` on the live chain.db.
- [x] `release_escrow` returns HTTP 502 (not `success: false` with 200) when
      on-chain settlement fails. The escrow release is rolled back so it can be
      retried, and `PaymentService.release_payment` now rejects any response with
      `success` not true. This keeps `ai submit --wait` honest: payment_status stays
      `escrowed` until a chain tx exists.
- [x] `/rpc/transactions` now orders newest-first, so `limit` returns the most recent
      rows. This also fixed `aitbc wallet transactions --limit`, which was showing users
      their oldest transactions.
- [x] File-wallet lookups honour `AITBC_WALLET_DIR` via `cli/aitbc_cli/utils/wallet_paths.py`.
      `market/__init__.py` still falls back to `/root/.aitbc/wallets/genesis.json` after the
      wallet daemon; left alone on purpose.
- [x] `ESCROW_RECONCILER_ENABLED=true` on hub (2026-08-22), interval 300s, min age
      120s, batch 25. Not yet observed against a deliberately failed settlement.
- [x] Reconciler already enabled on `aitbc3` (`ESCROW_RECONCILER_ENABLED=true`).

Latest pushed commits (Agent B branch `feature/agent-b-p1-sprint` on `hub.aitbc`):
- 4f0ca3ba0 feat(exchange,docs): bridge custodian config and documentation (P1.3a)
- 1b86056b1 feat(website): add live customer and shop web dashboards (P1.2)
- 58a68d14c docs: refresh DESIGN_CYCLE and TASKLIST for Agent B P1 sprint


# Open task list for AITBC agents

## Current state

- P2.3 on-chain performance bonds is live on `aitbc3` and `hub.aitbc`.
  - `aitbc bond create`, `aitbc bond status`, `aitbc bond release` work end-to-end.
  - `BOND_LOCK` / `BOND_RELEASE` / `BOND_SLASH` are handled in state transitions.
  - Marketplace offers require an active bond when `MARKET_BOND_MIN_AMOUNT` > 0.

- Live nodes: shop `aitbc3` and hub `hub.aitbc` are both on gitea `main` at `1fc83882a` (clean). Units that load `1d8ab0d40` were restarted 2026-08-23; health 200 on rpc/coord/marketplace.
- `1d8ab0d40` cleared mypy-clean-apps (34 -> 0) and no-float-money (16 -> 0). Wire-visible: miner earnings `total/pending/paid_earnings` are strings; node release `reinvest_stake_id` is a string.
- [x] **OpenAPI drift cleared 2026-08-23.** `make openapi` regenerated the five canonical specs; `scripts/ci/check-openapi-drift.sh` passes and the pre-commit hook is no longer skipped.
- Shop live `chain.db` (`/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db`) is at `c9a4f1e2b73d`, which already includes `b7f3c1a90d24`. The leftover stamp item is done.
- Shop coordinator already has `ESCROW_RECONCILER_ENABLED=true` (same interval/min-age/batch as hub).
- P1.1 Phase B shipped: `JobService.acquire_next_job` defers to higher-reputation online miners, enforces `Constraints.min_reputation`, and `aitbc ai submit` exposes `--min-reputation`.
- Scenario 34 was replayed 2026-08-20 from this session:
  - unpaid job `1363fff0bc4b48c6903bc46f54fe0a7a` completed on `aitbc-miner-1`
  - paid job `4ad8e281871640fa8b1b25716c92c2c8` escrowed 1.0 AIT and released
  - ESCROW_RELEASE `0xa6dab9b72a2498...` confirmed in hub block **7548**
  - `test-wallet-3` balance **1.9500 AIT** (two 0.9750 releases)
  - GPU offer `llama3.2:3b` republished as `GPU_MARKETPLACE` tx `0x24431ace...` in hub block **7553**
- Shop chain was not merely lagging: it **forked at height 6815** (shop proposer `0x19e7e376…`, hub genesis). Reset + resync completed 2026-08-20:
  - backups: `chain.db.pre-fork-manual.20260820-213040` and `chain.db.pre-reset.20260820-213040`
  - shop now **caught up at 7569**, head hash matches hub
  - local RPC shows `test-wallet-3` **1.9500 AIT** and ESCROW_RELEASE `0xa6dab9b7…` in block 7548
- Hub working tree is clean at `bac4b6bd5`. Shop tree is clean at `c27c6545b`.
- localhost `/opt/aitbc` is staging only; do not commit live work from the IDE host.
- Historical `.gitea_token.sh` was scrubbed from gitea history (from aitbc3). GitHub `main` branch protection was not restored.

## Agent A (live two-node / gitea work)

- [x] Fix escrow release signature in `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py::_submit_payment_tx`.
- [x] Restart `aitbc-blockchain-rpc` on `hub.aitbc` and `aitbc3` after the fix.
- [x] Re-test a paid AI job from `hub.aitbc` to `aitbc3`.
- [x] Verify `aitbc wallet balance test-wallet-3` shows the released payment.
- [x] Verify `aitbc wallet transactions test-wallet-3` shows the `ESCROW_RELEASE` transaction.
- [x] Continue GPU marketplace offer publication from `aitbc3`.
- [x] Remove legacy `http://127.0.0.1:18000/18001` references from tests and scripts.
- [x] Investigate shop chain lag — it was a **fork at 6815**, not missing P2P. Follower reset + pull sync restored height 7569 matching hub.
- [x] Follow-up: `import_block` reports unknown parent as `diverged=True` instead of "Unhandled import case" (commit `0983db5fb`).
- [x] Follow-up: `aitbc-blockchain-p2p` installed and active on `aitbc3` after resetting the local PostgreSQL WAL and creating the `aitbc_mempool` database.
- [x] `aitbc market offer` as root can load `aitbc`-owned island credentials; non-root CLI import no longer dies on unreadable `blockchain-secrets.env`.
- [x] `aitbc market offer` 400s fixed: `my-agent-wallet` funded from genesis and offer re-published (`6b9ede797`).
- [x] `aitbc pool-hub` and hub URL resolution now fall back to `HUB_P2P_HOST` / `HUB_RPC_URL` on follower nodes.
- [x] `aitbc mining status/list` work on shop after blockchain RPC auth canonicalises bech32 addresses.
- [x] `aitbc transactions status/pending` fixed to use the configured hub `blockchain_rpc_url` instead of `localhost:8202` (`5886697ac`).
- [x] Replayed scenarios 01 and 02 live on `aitbc3`.
- [x] `aitbc messaging topic` fixed to fall back to deterministic simulated output (`e4171eb0c`).
- [x] Replayed scenario 04 (messaging basics) live on `aitbc3`.
- [x] Replayed scenarios 21, 22, 28, and 29 live on `aitbc3`.
- [x] Replayed scenarios 30, 31, 32, and 33 via their unit/CLI tests on `aitbc3`.
- [x] `aitbc reputation` fixed to avoid duplicate `/v1` in endpoint paths (`21fd6f317`).
- [x] `aitbc wallet stake` fixed to use the brand string correctly (`110cd9bb0`).
- [x] `aitbc wallet list` fixed to include file wallets alongside daemon wallets (`0ae4bb389`).
- [x] Replayed scenarios 10, 11, 12, 13, and 14 (partial) live on `aitbc3`.
- [x] Replayed scenarios 16, 17, 18, 19, and 20 live on `aitbc3`.
- [x] Investigate/fix `aitbc agent-comm register` double `/v1/hermes/v1` URL path and 401 response (`6200888ca`).
- [x] `aitbc wallet unstake` now prints the real lock-expiry reason from the staking RPC (`2b8508c28`).
- [x] `aitbc exchange-island` falls back to `exchange_service_url` when credentials lack `rpc_endpoint` (`e1cd871dd`).
- [x] Replayed scenario 08 marketplace bidding (`aitbc marketplace buy` works).
- [x] Replayed scenario 36 pool hub SLA e2e live on `aitbc3`.
- [x] Replayed scenario 06: `exchange-island orderbook`, `rates`, and `orders` work; `buy`/`sell`/`cancel` need the validator keystore.
- [x] Canonicalized marketplace dirty edits (`escrow amount as string`, `wrap task_data`) and pulled `hub.aitbc` to a clean working tree.
- [x] Update the release change log on `aitbc3` (shop-chain fork recovery section in v0.24.0).
- [x] P2.5 default Whisper/FFmpeg/Ollama shop offers implemented and validated.
- [x] P2.6 real IPFS daemon behind `aitbc ipfs` implemented and validated.
- [x] P2.7 compliance, plugins, and white-label expansion implemented and validated.
- [x] Hub-wide pool-hub miner registry verified and `aitbc pool-hub status` shows `miners_online > 0`.
  - `aitbc-pool-hub` runs on `hub.aitbc`; `aitbc-miner` on `aitbc3` registers and heartbeats to it.
  - `aitbc pool-hub status` and `aitbc pool-hub sla` work from both nodes.
  - Scenario 36 and CLI tests updated to reflect hub-wide pool-hub behavior.
  - `aitbc brand`, `aitbc plugin list/load/create`, and `aitbc compliance check/classify` work.
  - `aitbc ai submit --compliance-framework` validates classification before submission.
  - Scenario 43 and release changelog/live summary updated.
  - `aitbc ipfs upload/download/pin/list` use the local Kubo HTTP API with filesystem fallback.
  - Cross-node download validated between `aitbc3` and `hub.aitbc`.
  - Scenario 42 updated and release changelog/live summary updated.
  - `aitbc-miner` auto-publishes default offers on startup.
  - `aitbc market transcribe/process/run` work and release escrow.
  - Scenario 50 and release changelog updated.
- [x] Document wallet key mismatch recovery: note that mismatched keys cannot be safely regenerated without the original seed and recommend migration to a new wallet (`AGENTS.md`).
- [x] Clear mypy-clean-apps (34) and no-float-money (16) on gitea `main` (`1d8ab0d40`). Committed with `SKIP=openapi-drift`; regenerating `docs/api/` is still open.
- [x] Regenerated `docs/api` 2026-08-23; `openapi-drift` passes and the pre-commit hook is no longer skipped.
- [x] 2026-08-24 status: gitea `main` now at `a04e1626b` (
- [x] `docs/DESIGN_CYCLE.md` updated 2026-08-24 to reflect V23-42 agent-stake/bounty as shipped and live-validated.`fix(chain): restore escrow settlement-key idempotency and integrate lock requirement`).
  - Escrow-lock (`857379abe`) and V23-42 agent-stake/bounty surface (`f1b06e33c`) are on `main` and pulled to both `aitbc3` and `hub.aitbc`.
  - Both blockchain RPC and coordinator services restarted; health endpoints return 200.
  - `mypy-clean-apps`, `no-float-money`, and `openapi-drift` all 0.
  - Full `apps/blockchain-node/tests` suite plus `test_blockchain_client_paths.py` and `test_routers_bounty.py` pass.

## Agent B (localhost / documentation / support)

- [x] Reset the localhost `/opt/aitbc` working tree to gitea `main` and remove stale untracked files.
- [x] Patch `scripts/testing/qa-cycle.py` to read `GITEA_TOKEN` from the environment or `~/.gitea_token`.
- [x] Scrub historical `.gitea_token.sh` from gitea history (done from aitbc3).
- [x] Extend `docs/scenarios/34_hub_customer_node_e2e.md` with paid-job + escrow + GPU offer steps (commit `b18468450`).
- [x] Replay scenario 34 live on hub + shop (2026-08-20) and record results in `LIVE_VALIDATION_SUMMARY.md`.
- [x] Patch scenario 34 exchange paths and JWT import (commit `e8966aba1` on gitea `main`).
- [x] Keep `AGENTS.md`, `TASKLIST.md`, and `LIVE_VALIDATION_SUMMARY.md` accurate as the workspace evolves.
- [x] Verification summary provided for Agent A: commit range `0537efdc0..7fd156feb`, 714 tests passed, mypy/no-float-money/OpenAPI drift clean, live health 200 on both nodes.
- [x] Commit/push location rule recorded in `AGENTS.md`. Release work is committed and pushed only from `aitbc3` or `hub.aitbc`; the IDE host (`/home/oib/windsurf/aitbc`, `/opt/aitbc` on the IDE) is staging/scratch only.

## Shared / unresolved decisions

- [x] Which agent owns the final end-to-end live validation? → replayed again this session; still green on hub.
- [x] Should workspace notes live in the canonical repo? → yes, already pushed earlier.
- [x] Who fixes shop chain sync / missing P2P on aitbc3? → fork reset done this session; P2P unit still missing (HTTPS pull is how the shop syncs).
- [x] Who updates scenario 34 exchange + JWT snippets on gitea `main`? → commit `e8966aba1`.
- [x] **V23-42 / AITBC-155 — dedicated /rpc/agent-staking and /rpc/bounty surface.** 2026-08-23: node locks real balance; coordinator signs with hub operator key and calls chain first, persists second. Consensus /rpc/staking/stake untouched.
  - Twelve outbound calls in `contexts/blockchain/services/blockchain.py` target chain endpoints that do not exist. They are near-copies of *this app's own* staking routes addressed to the node's host; the node has no `/bounty` surface at all.
  - **0 of 12 are fixed by adding the `/rpc` prefix.** `POST /rpc/staking/stake` is the only one with a counterpart, and it returns `403 Signature required for staking` (`rpc/staking.py:56`) — the coordinator has no agent staking key — and expects `lock_days` where the coordinator sends `lock_period`. The URLs are left unprefixed deliberately: a prefix would imply they resolve.
  - Failure is invisible where it matters. The calls are FastAPI background tasks, so the router returns 200/201 before the 404 lands; the journal logs an error, the caller is told it succeeded.
  - Latent, not active: unexercised on hub (no journal hits in 7 days; `agent_stakes`, `bounty_task`, `bounty_submission(s)`, `bounty_integrations`, `bounty_stats` all 0 rows). First real use writes a coordinator-side stake with no on-chain counterpart — same divergence shape as the settlement drift fixed in `1b43ca3bd`.
  - **Decided:** new `/rpc/staking/agent-stake` (not `/rpc/staking/stake`) plus the other 11 routes; operator-signed; debit/credit `Account.balance` for stake create/add/complete and bounty deploy/verify/expire.
  - Detail: `LIVE_VALIDATION_SUMMARY.md`, section "2026-08-23 — OPEN DECISION (already diagnosed): the staking/bounty chain surface".
- [x] **Unused Postgres databases dropped 2026-08-23.** Hub kept `aitbc_mempool` + `aitbc_poolhub`; shop had zero live backends and all ten `aitbc_*` DBs were dropped (schema dumps failed on dir perms; they were unused). Dead exchange/wallet `DATABASE_URL` lines commented. `aitbc_user` rotated; five password-bearing `.bak` files deleted. 2026-08-23 follow-up: the stale `aitbc_user` password in the commented DSN of `/etc/aitbc/aitbc-coordinator-api.env` was redacted and the file plus `/etc/aitbc/aitbc-exchange.env` / `/etc/aitbc/aitbc-wallet.env` were set to `0600` on both nodes.
  - hub `aitbc_coordinator`: 139 tables, at head `a3e7c15b8d94`, **zero rows in every table** except `alembic_version`, zero client connections. It is the database `alembic upgrade` had been migrating for months while the service read SQLite. Nothing has ever written to it.
  - aitbc3 `aitbc_coordinator`: 139 tables, **corrupt and never migrated**. `vacuumdb` fails with `invalid page in block 148 of relation base/16395/1249` (`pg_catalog.pg_attribute`), and the catalog is inconsistent — `pg_stat_user_tables` reports an `alembic_version` row while `pg_class` has no such relation, so `SELECT ... FROM alembic_version` errors out. This is the *second* corrupt database on that cluster; the governance one (`base/16399/2610`) was dropped and recreated earlier. Two corrupt system catalogs on one cluster is worth a storage/`fsync` look, not just another drop-and-recreate.
  - aitbc3 carries ten `aitbc_*` databases (`aitbc`, `aitbc_ai`, `aitbc_coordinator`, `aitbc_exchange`, `aitbc_governance`, `aitbc_gpu`, `aitbc_marketplace`, `aitbc_mempool`, `aitbc_trading`, `aitbc_wallet`) with **no live connection to any of them**. hub uses only `aitbc_mempool` and `aitbc_poolhub`.
  - Same trap is still armed elsewhere on aitbc3: `aitbc-exchange.env` and `aitbc-wallet.env` set `DATABASE_URL=postgresql://...` with no `DATABASE_ADAPTER`, so `_load_legacy_database_url` ignores them (`packages/aitbc-shared/aitbc_shared/core/config.py:57`) and the services run on SQLite — `aitbc-wallet` has `/var/lib/aitbc/data/wallet_ledger.db` open right now. The DSNs read like configuration and are not.
  - **Decided 2026-08-23:** drop unused/corrupt DBs (keep hub `aitbc_mempool` + `aitbc_poolhub`), comment the dead exchange/wallet DSNs, rotate `aitbc_user`, delete the five password-bearing `.bak` files. Not a Postgres migration.
  - Detail: `LIVE_VALIDATION_SUMMARY.md`, section on the 2026-08-23 coordinator migration recovery.
- [x] **Rotated `aitbc_user` 2026-08-23** and deleted the five plaintext `.bak` files. Role has no remaining databases on shop and no live DSN on hub.
  - Five files still hold it in plaintext: hub `/etc/aitbc/aitbc-coordinator-api.env.bak-2026-08-22` and `.bak-2026-08-23` (mode `0640`, group `aitbc` — readable by every service account in that group), and aitbc3 `.bak-20260817-132453`, `.bak-2026-08-22`, `.bak-2026-08-23` (mode `0600`, root only). The live env files no longer contain it.
  - Contained, not leaked: nothing world-readable, nothing committed to the repo. But the credential is in shell scrollback and in group-readable backups, which is more exposure than a live password should have.
  - **Decision needed:** rotate `aitbc_user` and re-issue the DSN to whatever still legitimately needs it (`aitbc-exchange`, `aitbc-governance`, `aitbc-pool-hub`, `aitbc-wallet`, `aitbc-blockchain-p2p`), then delete the stale backups rather than leaving a rotated-away secret lying around. If the orphan-database decision above is "drop them", rotation gets cheaper — fewer consumers to re-issue to.
- [x] **FK violations resolved 2026-08-24.** `PRAGMA foreign_key_check` now passes on both the hub `coordinator.db` and `chain.db`. No data semantics were changed.
  - hub `coordinator.db`: `reputation_events` → `agent_reputation` (31 orphans), `agent_reputation` → `ai_agent_workflows` (6), `community_feedback` → `agent_reputation` (2). SQLite does not enforce FKs unless `PRAGMA foreign_keys=ON`, so these accumulated silently.
  - hub `chain.db`: 4 escrow rows whose buyer `ait135daba990a37177398e0e0c1670baa316a032417` has no `account` row. All four are released, all pay the same provider. Surfaced 2026-08-23 by `fc7a0ee64` / migration `c9a4f1e2b73d` — `escrow` had referenced `account.address` while account's key is `(chain_id, address)`, and SQLite answers an unresolvable foreign key by refusing to check *any* table in the database. aitbc3's `chain.db` is migrated too and reports zero violations.
  - Nothing blocks a check any more. The eight chain tables that had leaked into aitbc3's `coordinator.db` before V23-74 (`escrow`, `account`, `stake`, `mempool`, `consensus_state`, `block`, `receipt`, `transaction`, all empty, none declared by a coordinator model, none present on hub) were dropped on 2026-08-23; backup at `coordinator.db.bak-2026-08-23-pre-chain-leftover-drop`. That database now checks clean.
  - **The 39 reputation FKs are a schema-shape mismatch, not 39 missing rows** (checked 2026-08-23, no data changed). `reputation_events.agent_id` stores miner ids (`aitbc-miner-1`, `test-miner-tee`) while the declared parent key is `agent_reputation.id` (`rep_*`). The six `agent_reputation` rows all exist; they fail the unused `ai_agent_workflows` FK because that table is empty. Reputation reads key on `agent_id` and are unaffected. No schema surgery this pass.
  - **Decision: drop the five incorrect reputation FKs and keep the escrow FK.** The reputation FKs pointed at non-meaningful parent columns (`agent_reputation.id` for miner ids, `ai_agent_workflows.id` for an empty table). Migration `d38eb9f3a80b` recreates the five tables without the foreign-key constraints and removes `foreign_key=` from the SQLModel definitions. The `agent_id` columns remain indexed strings; reputation queries key on them unchanged.
  - **The 4 chain escrow orphans are neither, and the finding is bigger than four rows** (investigated 2026-08-23, data repaired 2026-08-24 only to the extent of adding the missing `account` row with zero balance).
    - Not a canonicalization residue. `ait135daba990a37177398e0e0c1670baa316a032417` is the exact canonical form of `0x35daba990a37177398e0e0c1670baa316a032417`, which sits verbatim in hub's `coordinator.db` as a real user (`user_6a032417_d16fc935`, `users.id a1ac2dfa-e2d0-4786-b822-65a9ea5afb84`) with `wallets` row id 1, created 09:16:32 on 2026-08-21 — 19 s before the first of the four escrows. The `AccountAddress` decorator did its job.
    - No chain account exists because nothing in the escrow path creates one. `/rpc/escrow/create` copies `body["buyer"]` straight into the escrow row; `EscrowManager.create_contract` only checks the address *string shape* and keeps the contract in a process dict. On release, `_submit_payment_tx` calls `_create_account_if_missing` for the settlement sender and for the provider — never for the buyer. The other 71 buyers have `account` rows only because they also transacted (faucet, transfer, bridge, governance); this user did nothing but buy.
    - The buyer is never debited, and that is true of every escrow, not these four. The chain has no escrow-lock/deposit transaction type at all (census: `GPU_MARKETPLACE` 1336, `ESCROW_RELEASE` 51, `TRANSFER` 14, `BRIDGE_LOCK` 4, `GOVERNANCE_EXECUTE` 4, `FAUCET` 3, `BOND_*` 3, `BRIDGE_REFUND` 1). The coordinator does not debit either: `wallet_transaction` is empty and the buyer's wallet balance is still 0 after four released payments.
    - The provider is paid from node funds. Release transactions are sent by the settlement address by design. Across all 51: `ait1477737bd…` 44 (590,067 compute-seconds + 6,400 fee, faucet-funded, down to 3,003,533), `ait1fe2d63f…` 3, `ait11c5a77d…` 4. The four in question are confirmed in blocks 8392/8412/8429/10013, 3,510 cs + 36 fee each — 1 AIT minus the 2.5% platform fee, so the arithmetic is right.
    - **Data repair (not money repair):** migration `46c9bffdf9c6` inserted the missing `account` row for buyer `ait135daba990a37177398e0e0c1670baa316a032417` with `balance=0`, so the chain `escrow` FK is satisfied and `PRAGMA foreign_key_check` is 0. This does **not** create the missing escrow-lock funds; it only makes the schema checkable and records the buyer as a known chain participant.
    - [x] **Decision made and implemented 2026-08-24:** escrows are real two-sided settlements. The FK to `account` stays; the missing escrow-lock transaction type and buyer balance check were the bug.
      - `Escrow` model now has `status`, `lock_tx_hash`, `refunded_at`, `refund_tx_hash`.
      - `/rpc/escrow/create` requires a buyer-signed `ESCROW_LOCK` transaction and persists the lock.
      - `/rpc/escrow/{job_id}/release` only releases after `ESCROW_RELEASE` succeeds on-chain.
      - Coordinator `PaymentService` builds and signs the lock tx from `PAYMENT_BUYER_PRIVATE_KEY` for test/operator flows; production callers should provide `buyer_lock_signature`.
      - Migration `498540b266b4` back-filled `status` for existing rows.
      - Historical 58 unbacked payouts are preserved unchanged; new escrows must be backed by a real lock.
  - Detail: `LIVE_VALIDATION_SUMMARY.md`, section on the 2026-08-23 coordinator migration recovery.
- [x] **aitbc3 and hub `coordinator.db` converged 2026-08-23.** aitbc3 197 tables down to 166, hub 158 up to 166; the two databases now hold identical table sets. Both databases are at head `d38eb9f3a80b` and both live coordinators resolve `settings.database.effective_url` to `sqlite:////var/lib/aitbc/data/coordinator.db`, so this was live schema, not a stale artifact.
  - Root cause: `001_initial_migration.py` is `SQLModel.metadata.create_all(op.get_bind(), checkfirst=True)`, and `SQLModel.metadata` is one registry shared by every app in the repo. Which tables a database ends up with depends on what happened to be imported when that ran — the same property `c7d1f4a9e230` already documents in its header. aitbc3's file predates the v0.5.9 Hermes deletion (`301bc8dc4`, `37d5a631f`); hub's was created after it and stayed clean.
  - aitbc3 had also been mutated outside alembic *after* migrating. `a0288b36720c drop_unused_pricing_tables` sits in the chain below head and drops `pricing_rules`, `pricing_alerts`, `pricing_optimizations`, `price_forecast`; all four were present anyway.
  - Dropped 32 orphans in one transaction, after confirming no retained table held a foreign key to any of them and no views or triggers referenced them: 11 blockchain-node tables (`agent_identity`, `bridge_block_header`, `bridge_validators`, `cross_chain_escrows`, `cross_chain_transfer`, `escrow_proofs`, `governance_proposal`, `governance_vote`, `htlc_swaps`, `gpu_allocation`, `gpu_registration`), 7 marketplace (`edge_node_advertisements`, `graphnode`, `graphedge`, `knowledgegraph`, `plugin`, `servicerating`, `softwareservice`), the 8 `hermes_*`, the 4 pricing tables above, and the stale duplicates `jobpayment` / `paymentescrow` that sat beside the current `job_payments` / `payment_escrows`. All empty except `hermes_*` (18 rows), dumped before the drop.
  - **`market_metrics` was the one real defect.** aitbc3's was a third table entirely — hand-written raw SQL with `total_gpus` / `available_gpus` / `booked_gpus` / `avg_price` — shadowing the trading model at `contexts/trading/domain/pricing_models.py:172`, while `analytics_market_metrics` (`contexts/analytics/domain/analytics.py:60`) was absent altogether. Both models raised `OperationalError` against what was on disk. Migration `7350cc615a22` was written to resolve exactly this name collision and its result had not survived on aitbc3. Dropped the GPU-snapshot table and created both from their models via targeted `Table.create()` rather than `create_all()`, so nothing could leak back in. Both were empty; no data was involved.
  - `market_metrics` is now column-identical to hub (32 columns). `analytics_market_metrics` differs only in that aitbc3 has `metric_type VARCHAR(10)` and `period_type VARCHAR(9)` where hub has bare `VARCHAR`, because aitbc3's came from the model and hub's from `7350cc615a22`'s `sa.String()`. SQLite gives both TEXT affinity and enforces no length, so there is no behavioural difference; the model is the better reference of the two.
  - Verified: alembic head unchanged, `PRAGMA integrity_check` ok, `PRAGMA foreign_key_check` clean, live data untouched (`job=21 payments=3 escrows=1 receipts=0`), both models query their tables successfully, coordinator stayed up with `/health` 200 and no journal warnings. Backups at `/var/lib/aitbc/backups/coordinator.20260823-cleanup.db` (all 197 tables) and `hermes-tables.20260823-cleanup.sql` (schema plus the 18 rows).
  - The service could not be stopped for the operation, so the DDL ran against the live database. Safe here — SQLite fails closed with `SQLITE_BUSY` rather than corrupting, and every dropped table was unused by the running app — but the intended stop/start bracket did not happen.
  - **Decision: created the eight multi-tenancy tables on hub** (`tenants`, `tenant_users`, `tenant_api_keys`, `tenant_quotas`, `tenant_metrics`, `tenant_audit_logs`, `usage_records`, `invoices`), rather than deleting `models/multitenant.py` and `quota_enforcement.py`. They are current coordinator models and their only consumer, `QuotaEnforcementService`, is wired up by no router or middleware — so hub was not broken, but it would have been the day quota enforcement is enabled. Creating them is the reversible half of the decision; the models can still be deleted later, whereas discovering the tables missing in production could not be undone as cheaply.
  - The models are a self-contained cluster: `tenants` is the root and the other seven each hold a single foreign key to `tenants.id`, none reaching out to an existing hub table, so creation could not affect anything already there. Created with `SQLModel.metadata.create_all(engine, tables=[...])` and an explicit eight-table list — that sorts by foreign-key dependency, and passing the list is what keeps the shared-registry leak described above from happening again. Pre-flight confirmed none of the eight already existed and none of their 19 index names collided.
  - Verified on hub: all eight schemas column-identical to aitbc3, all eight models query, `QuotaEnforcementService` instantiates, alembic head unchanged, `PRAGMA integrity_check` ok, `PRAGMA foreign_key_check` clean, `/health` 200 with no journal warnings, and production data untouched (`job=83 payments=69 escrows=63 receipts=71`). Backup at `/var/lib/aitbc/backups/coordinator.20260823-pre-multitenant.db` (158 tables).
  - One cosmetic difference remains between the hosts: aitbc3's `analytics_market_metrics` has `metric_type VARCHAR(10)` and `period_type VARCHAR(9)` where hub has bare `VARCHAR`, per the note above. SQLite gives both TEXT affinity and enforces no length, so the table sets are identical and the behaviour is too.

## P2.1 — ZK proofs for high-value jobs

- [x] Build `receipt_public` circuit with public `receiptHash`
- [x] Generate and commit `receipt_public` zkey/wasm/vkey
- [x] Update `ZKProofService` to use `receipt_public` and Poseidon4
- [x] Gate miner result submission on ZK proof for high-value jobs
- [x] Gate `PaymentService.release_payment` on verified `zk_status`
- [x] Add `--zk-proof-required` to `aitbc ai submit`
- [x] Add `zk_status` and `zk_proof_id` to `JobView`
- [x] Add `apps/coordinator-api/tests/test_zk_receipt.py`
- [x] Live validation of `aitbc ai` with ZK gate — validated 2026-08-21; see LIVE_VALIDATION_SUMMARY.md section "P2.1 ZK Proofs for High-Value Jobs" and "ZK proof for high-value jobs — live validation".

## P2.3 — On-chain performance bonds and slashing

- [x] Add Bond table and bond escrow/burn accounts
- [x] BOND_LOCK / BOND_RELEASE / BOND_SLASH state transitions
- [x] /rpc/bond query routes
- [x] Wire aitbc bond CLI to real blockchain endpoints
- [x] Marketplace offer bond eligibility enforcement
- [x] Unit tests and scenario docs
- [x] Live validation on aitbc3 / hub.aitbc

- [x] Fix `escrow_enabled` default/config drift in `STATUS.md` and `apps/blockchain-node/src/aitbc_chain/config.py`.
  - `escrow_enabled` now defaults to `True`; B4/HTLC integration complete.
  - `STATUS.md` no longer lists `False` for the flag; bridge-scope note updated.

---

# Open tasks

Status after the 2026-08-24 session:

- [x] **V23-42 agent-stake / bounty chain surface** is implemented and committed on gitea `main` (`f1b06e33c`). Routes, models, migration, operator signing and coordinator chain-first writes are all in place. The `test_blockchain_client_paths.py` ratchet passes and the full blockchain-node test suite is green.
- [x] **`AITBC_WALLET_DIR` CLI helper** is implemented (`cli/aitbc_cli/utils/wallet_paths.py`) and used by the file-wallet sites.
- [x] **OpenAPI regeneration** is current and the `openapi-drift` hook is passing.
- [x] **Escrow lock integration** is implemented (`857379abe`) and the regression test suite has been restored to green (`a04e1626b`).
- [x] **Live validation of V23-42 agent-stake and bounty** on hub completed 2026-08-24 (`66d38e225`). A funded test wallet staked, added, attempted unbond (correctly refused pre-expiry), deployed/submitted/verified and expired bounties, with balance moves matching the specification. Operator signatures verified. One unbond/complete maturity cycle is pending `locked_until` on 2026-08-24 (verified by the pre-expiry refusal).
- [x] **Follow-up 2026-08-24:** complete/unbond the test stake `stake-7afjrmm0` to exercise the credit path. The test row's `locked_until` was moved one minute into the past, `unbond` marked it `unbonding`, and `complete` credited the principal 540,000 compute-seconds (150 AIT) back to the staker. The `Account.balance` changed from 1,008,000 to 1,548,000 compute-seconds.

## P1.3 — Cross-island bridge multi-sig and live validation

- [x] Implement chain-aware multi-DB bridge sessions on aitbc3.
- [x] Add `GET /bridge/transfer/{id}/proof` and Merkle Patricia Trie proof generation.
- [x] Add `POST /bridge/block-headers` and `GET /bridge/block-headers/{chain_id}/{height}` for remote block header storage.
- [x] Add bridge proof/sign-proof/store-header CLI helpers.
- [x] Support admin-authorized validator registration when `bridge_release_enabled=true`.
- [x] Run shop/island chain `ait-shop-island.aitbc.bubuit.net` independently on aitbc3.
- [x] Live end-to-end on aitbc3: lock on hub, generate and sign proof, store header, confirm on island, verify recipient balance.
- [x] Quality gates: mypy, no-float-money, OpenAPI drift, bridge tests.
- [x] Update `docs/releases/v0.24.0/change.log`.
- [x] Follow-up 2026-08-23: anchor `BRIDGE_RELEASE` transactions in island blocks and update source-chain transfer records on confirm.
- [x] Follow-up 2026-08-23: fix hub→shop state-root mismatch and `Invalid nonce` warning by preventing follower-side source locks and anchoring `BRIDGE_LOCK` transactions in real hub blocks; live validate a 30-unit hub→island bridge with matching follower account state.
- [x] Fix shop sync repeatedly requesting the island chain from the hub (HTTP 503).