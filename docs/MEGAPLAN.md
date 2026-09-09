# MEGAPLAN — executing the 2026-09-06 cross-artifact reconciliation register

> **IDE-local working document** (`/home/oib/windsurf/aitbc/docs/MEGAPLAN.md`). Do not sync
> or commit it to the canonical AITBC repo. Source register: `TASKLIST.md` section
> "2026-09-06 — Cross-artifact reconciliation register" (originally 54 items, 7 lanes).
> Prepared 2026-09-06 against `/opt/aitbc` at `5bea3c6de3` plus read-only fleet checks.
> **Review incorporated 2026-09-07:** canonical code/Gitea at `ff6ef76347`, CI run
> `19635`, and read-only fleet RPC observations. This is a pinned review snapshot,
> not a claim about later commits or deployments. The operator's subsequent Tier-7
> cleanup entries are retained separately. No code, tests, services, credentials,
> or TASKLIST entries were changed as part of this document update.
>
> **2026-09-07 live exercise + CI closure update:** candidate `b62637a792` passed
> Gitea CI run `19639`; the redacted bridge-status MCP tool, C901 ratchet wiring,
> and the node1 `aitbc-blockchain-node` outage/recovery exercise were completed.
>
> **2026-09-08 independent verification (§16):** an agent-run, read-only audit of
> this document's claims against Gitea `main`, the authenticated Gitea Actions API,
> and all five live hosts. It confirms most code and CI claims, retires the §9/§3
> fleet snapshot as superseded by an unrecorded deployment, narrows O-3, re-derives
> D-2 as closed on `main` (same tree as the cited branch commit), and records that
> CI was red for 162 consecutive runs (19477–19638) before the green gate at 19639.
> Nothing was built, tested, restarted, or committed to produce it.

## 1. Scope and shape

The original register has 54 IDs across seven lanes. Execution expanded to eight
numbered tiers (0–7), an operator lane, D-1…D-4 follow-ups, and a separate flagged-item
cleanup batch. Tier tasks, split findings, and review actions are not additional
unique original-register IDs and must not be summed as if they were.

**Current verdict: fully closed 8 Sep at `aef0b5099` (Gitea CI 19673 green).**
All 58 register IDs now have a dated, explicit disposition (see §16.8 and §18).
F1/F2 are closed in `aef0b5099` and verified from both the IDE and `node2`.
§14 acceptance has been re-asserted at the current tip. The only residual is R10's
recorded manifest evidence gap: a per-pull approval log and a service-level networked
rejoin restore test are not establishable and were not manufactured. Remaining
operator-only credentials/identity items are recorded as accepted or operator-blocked,
not agent work. Historical execution history below is retained for traceability.

| Tier | Contents | Current use |
|---|---|---|
| 0 | Re-verification & closures | Historical re-derivation evidence |
| 1 | Mechanical fixes | Recorded completions; stale statuses corrected |
| 2 | Code fixes with tests | Implementation history plus reopened S-3 / CI gates |
| 3 | Investigations | Historical findings; C-2 live retest completed 7 Sep |
| 4 | Decision-bound | Decisions retained; S-4 / B-8 closed in code 8 Sep, A-2 closed 7 Sep |
| 5 | Fleet deploy (F-1) | Recorded deployment; old runbook retired, new actions require approval |
| 6 | F-5, C-1 tracing, A-1 research | Python coverage retained; Solidity coverage added 8 Sep; C-1 phase diagnosis **closed** 8 Sep (R7, `7ccdabf9b`) |
| 7 | Deferred and flagged cleanup | Operator-supplied records retained; not a blanket CI sign-off |
| O | Operator-only | Credential actions remain operator-owned; O-1 confirmed 8 Sep |

### Current review follow-ups

These are review actions, not a replacement count of open original-register items.
`TASKLIST.md` was not edited in this pass; its "3 open" header and zero-item lane
summaries still need reconciliation against explicit IDs and evidence.

| Review ID | Register item | Current disposition | Owner / next gate |
|---|---|---|---|
| R1 | S-3 | Closed 8 Sep: client constraints separated from server-owned spot-check evidence; `6651dc3b1` on gitea `main`; `aitbc-coordinator-api` on `hub.aitbc` restarted to `c79462f3e`, health OK, live OpenAPI `Constraints` has no `shadow_mode` | node2 dev; server-owned evidence and forgery regressions |
| R2 | S-4 | Closed 8 Sep: v3 activation rule, per-escrow beneficiary/signer validation, v2→v3 cross-activation handling, pure-path release/refund, parallel caller wiring, and tests; `d119e8ca9`/`2baf883f3`/`fe5f4a451`/`e75e7355b` on gitea `main`; CI 19668 green. Block 5470 stamped `state_transition_version=3` on all five hosts 8 Sep 16:52 UTC; `parallel_tx_validation` defaults off | node2 dev + operator; full versioned custody and transition tests |
| R3 | B-3 / CI sign-off | Closed 7 Sep: `c901-ratchet` wired in both workflows; Gitea run 19639 green at `b62637a`; CI runs 19600–19638 were consecutive failures, so earlier Tier 4/6 evidence came from node2 local `make`, not CI | Recorded; rerun required for next candidate |
| R4 | F-5f | Closed 8 Sep: added `contracts/test/EscrowService.test.js` (23 tests) and `contracts/contracts/mocks/MockEnergyPricing.sol`; `EscrowService.createEscrow` `releaseTime` persistence bug fixed; `npx hardhat test` passes 182 tests; Gitea CI 19646 green at `8cb48178d` | node2 dev; contract-specific coverage evidence |
| R5 | B-8 | Closed 8 Sep: `3d09e8105` makes `001_initial_migration` and the B-8 test import `coordinator_api.models.multitenant`; `make test-apps` now includes `apps/coordinator-api/tests/integration`; the B-8 fix commit `3d09e81054` had Gitea run 19642 failing; the follow-up `c79462f3e` (run 19643) is green; historical-schema-to-head regression closed by `0c460fe9f` (run 19661) | node2 dev; historical-schema upgrade regression closed 8 Sep |
| R6 | C-2 | Closed 7 Sep: live node1 `aitbc-blockchain-node` outage produced blocks 4619/4620/4621 with 3-of-4 validators and full rejoin | Recorded; exercise logs in `/tmp/node1_outage_evidence_20260907_225846.log` |
| R7 | C-1 | Closed 8 Sep: `_propose_phase` tracks the active proposal phase; watchdog ERROR and per-phase metric include the phase; new `test_proposer_watchdog.py` passes at `LOG_LEVEL=INFO`; `7ccdabf9b` on gitea `main` | node2 dev; active phase in watchdog ERROR, tested without DEBUG |
| R8 | O-1 | Closed 8 Sep: operator confirmed the node2 GitHub PAT is revoked at github.com/settings/tokens; attestation only — the token was not requested, read, copied, or tested | Recorded; dated operator confirmation |
| R9 | A-2 | Closed 7 Sep: full ETH→AIT round-trip on node2 bridge — 0.001 Sepolia ETH deposited, 2.49425 AIT minted to `0x3Ed42960a36489Fe1BA39ceCcbbd6F87C8551Ebf` in AIT block 4640 | Recorded; deposit tx `0xb417…d3dd`, AIT tx `0xd13b…3068`, bridge config live on `node2` |
| R10 | F-1 / register evidence | Closed 8 Sep with recorded residual: manifest refreshed (§16.2) — fleet at tip `6e6bb21615` (CI 19651 green), converged 5246, coordinator schema `f53990f9d6cc`, daily backups present; TASKLIST reconciled against R1–R10 with operator approval; per-pull approval log remains not establishable and was not manufactured; DB-level restore test added 8 Sep (20260908_010420 dumps → scratch sqlite: chain 4,711 blocks + coordinator 166 tables, integrity_check ok) — service-level networked rejoin/restore test completed post-close on node0 — hub online SQLite snapshot copied to node0 via IDE bridge, node0 restored and rejoined consensus at fleet head 5581 / `0xfab1122fe72f11`, `fleet-config-check.sh` exit 0 | Recorded; evidence attached, reconciliation done |

## 2. Ground rules (from AGENTS.md — non-negotiable)

- **No builds, test suites, or services on the IDE host.** This authorized change
  edits the IDE-local working document only.
- **Dev work belongs on `node2` / `hub2.aitbc`**; hub2 remains pull-only.
  `hub.aitbc` is a small VPS — keep inspection and hub-specific checks light.
- Repository commits and pushes follow the workspace's node/remote rules and
  require their own authorization; updating this plan authorizes neither.
- **Every `inherited` item is re-derived before it is scheduled.** Use the source
  SHA and symbol as well as the path; line numbers in older passes are historical
  and must be resolved again before implementation.
- **Register hygiene:** record the disposition, closing SHA, verification evidence,
  and date. Do not mark a register item closed merely because a subtask landed.
- **No secrets handling.** Credential actions and confirmations are operator items.
- Commits follow repo convention (`type(scope): description`); never `--no-verify`,
  never force-push, never push to `github` from a live node.
- Every service-disrupting action, credential/configuration change, or destructive
  restore requires explicit per-action approval. Review follow-ups grant none.

## 3. Historical corrections found during planning (6 Sep)

These were verified read-only while preparing the original plan. They are retained
as the planning snapshot, not as current pending work; later dispositions follow:

1. **O-5 is done, not pending.** `c4a5b26299` scoped `VALIDATOR_KEYS`/`PROPOSER_KEY`
   into `/etc/aitbc/validator-secrets.env` (0600 root, loaded only by the three
   blockchain services); `5bea3c6de3` hardened `setup.sh`/`update.sh`/the migration
   script against regression. `/etc/aitbc/validator-secrets.env` exists on hub
   (created 2026-09-06 20:17). Action: confirm on node0 (the one host not named in
   the commit message), then close.
2. **P-8 is stale.** `apps/api-gateway/pyproject.toml:12-13` already declares
   `slowapi = ">=0.1.9"` and `pydantic = ">=2.13.0"`. Close.
3. **A-5 is partially landed.** `escrow.py:82-84` already carries
   `energy_quote_snapshot` / `energy_quote_id` / `energy_quote_digest`, and the
   pending deploy contains Alembic revision `...3c5e9b1d2_add_energy_quote_digest_settlement`.
   The item narrows to: verify the `ESCROW_LOCK` path actually records the digest
   (state transition + RPC), then close or narrow.
4. **F-4 retitle.** The missed file is `.devin/mcp_config.json` (no
   `AITBC_MCP_AITBC_CLI`, and it points at `/opt/aitbc/venv/bin/python` which does
   not exist on the IDE host). The workspace `.mcp.json` is already correct.
   No `.mcp.json` exists in the repo at all.
5. **P-4 is half-done.** `pyproject.toml` already has `[project]` at :1 alongside
   `[tool.poetry]` at :9 — the task is deduplication, not a fresh migration.
6. **F-1 widened by 2.** node2 is at `ee2583b28` — behind tip `5bea3c6de3` by the
   two secrets-scoping commits. The four other hosts remain at `b0d5fc1a5`
   (~96 commits behind tip now, not 94).
   **Superseded 8 Sep (§16.2):** all five hosts are now at `d119e8ca90`, clean and
   on `main`. This item is a historical snapshot, not a current inventory. Note also
   that `b0d5fc1a5` is *not* an ancestor of `main` (63 commits unique to it, 145 to
   `main`), so "commits behind" was never the right relation — the fleet was on a
   divergent line.

## 4. Tier 0 — Re-verification & closures (execution history)

Original goal: shrink the register to what was actually open before writing code.

- [x] **T0-1 · Sweep all `inherited` items** — done 6 Sep. Three subagent batches
  re-derived every inherited item against `/opt/aitbc@5bea3c6de3` + live hosts;
  9 items moved to the closed table, 8 narrowed, 3 marked unreproducible.
- [x] **T0-2 · F12 determination** — done 6 Sep: gate run on node2 reports "no new
  type errors (8 known)"; the relocated baseline is fresh. Resolved.
- [x] **T0-3 · S-7 arithmetic** — done 6 Sep: refund = `amount − released_amount`
  on net principal, clamped to locked; closed in code.
- [x] **T0-4 · S-6 gate check** — done 6 Sep: 0 of 48 refunded rows lack a hash on
  hub; closed. (Gate coverage note folded into S-2's entry.)
- [x] **T0-5 · B-7 reconcile** — done 6 Sep: API returns exactly 3 open (#32, #482,
  #509); #934 confirmed gone; count reconciles. **Closed 7 Sep (Tier-4):** all 4
  alerts (#32, #482, #509, #800) dismissed as not-exploitable on GitHub.
- [x] **T0-6 · O-5 confirm-and-close** — done 6 Sep: node0 residual confirmed
  (no `validator-secrets.env`; keys still in shared env). Subsequently recorded
  closed 7 Sep; see the operator lane for the scoped-secrets deployment record.
- [x] **T0-7 · A-5 narrowing and closure** — re-derived 6 Sep; the digest was
  already signed, validated, and persisted. **Both residuals closed 7 Sep by
  `7fecd759d2`:** `load_from_db` restores all ten E1 columns, and the
  `lock_signature` reconstruction binds quote id/digest and settlement
  route/asset/scale. The 7 Sep code review confirms these fixes; the earlier
  missing-digest wording is historical, not new work.
- [x] **T0-8 · P-8 close** — done in the planning pass.
- [x] **T0-9 · C-7 / B-8 / S-4 classification** — done 6 Sep: C-7 closed (bridge
  flags `true` on all five hosts — production is not inert); B-8 confirmed
  decision-bound (dynamic `create_all` baseline); S-4 confirmed design item.
- [x] **T0-10 · F-5 unparked in Tier-6** — all six items re-derived. F-5a
  clarified (proposer identity, not a provider-level filter), F-5b fixed
  (`7839be1bb`), F-5c documented disabled-by-design (`7839be1bb`), F-5d
  `AITBC_HOSTNAME` fallback (`7839be1bb`), F-5e already removed (`743c11ddf9`).
  **F-5f's Solidity closure is reopened by R4:** `210a02a23` added 102 Python
  manager tests, not coverage of the named Solidity contracts.

## 5. Tier 1 — Mechanical fixes (execution history)

Recorded commits and live operations follow. Future changes use the venue and
approval rules in §2; these completion records are not authorization to repeat them.

- [x] **T1-1 · P-1** — `8cff16db7`: relative `-e ./packages/aitbc-shared` +
  `export-requirements.sh` rewrites `file://$REPO_ROOT/` on regen.
- [x] **T1-2 · P-2** — `8cff16db7`: `packages/README.md` written.
- [x] **T1-3 · P-6** — `260db8d07`: declaration was already removed by
  `891d40472`; residual stale lockfile regenerated (poetry 2.4.3).
- [x] **T1-4 · P-7** — closed upstream by `891d40472` (override already removed).
- [x] **T1-5 · P-9** — closed upstream by `891d40472` (README rewritten to match
  the implemented context).
- [x] **T1-6 · P-10** — fully closed 7 Sep (`7a53a6a1c9`): `introduction.md`
  no longer duplicates port numbers (defers to SERVICE_PORTS.md) and the
  "Designed" labels on AI Trading/Analytics/Compliance are corrected to
  "Partial" — all three ship real surface. Earlier passes: root specs
  `3e5da1d89`, `introduction.md:84` fix `891d40472`, nested `docs/api/`
  duplicates removed in Tier-1.
- [x] **T1-7 · P-11** — `8cff16db7`: policy deleted + unlinked (the feature it
  governed does not exist).
- [x] **T1-8 · B-6** — `90ef51488`: `.secrets.baseline` regenerated on node2 via
  `detect-secrets scan --baseline` (audit state preserved; 772 findings, all
  `is_verified: False`, same as before).
- [x] **T1-9 · B-5** — `8cff16db7`: audit now scores `utils/security.py` +
  `validators/` (both real).
- [x] **T1-10 · F-4** — `8cff16db7`: `AITBC_MCP_AITBC_CLI=/usr/local/bin/aitbc`
  added. (Interpreter path left as-is: correct on live nodes, which is where the
  config runs.)
- [x] **T1-11 · F-6** — done 6 Sep (live op): all five hosts' `/opt/aitbc`
  repo-local config now `AITBC System <system@aitbc.net>`.
- [x] **T1-12 · F-2** — done 6 Sep: backup now on three disks (hub,
  IDE `backups/`, node2), all sha256 `10a647bb…decb`.
- [x] **T1-13 · C-6** — `8cff16db7`: trap comment added at `config.py:600`;
  default unchanged.
- [x] **T1-14 · P-5** — `8cff16db7`: `packages/py/aitbc-agent-core/pyproject.toml`
  and root `pyproject.toml` both pin mypy to `2.1.0`; confirmed in the review.

P-3 and P-4 were deferred when first assessed, but neither remains pending:
**P-3 closed 7 Sep** (`de0def218`, install-profile mapping); **P-4 closed 7 Sep**
(`c341087843`, scalar metadata deduplicated into `[project]`). Dependencies remain
in `[tool.poetry.dependencies]` with `dynamic = ["dependencies"]`; this is not an
unstarted PEP 621 migration. **P-3 follow-up closed 8 Sep** (`596d73844`):
`install-profiles.sh` now keeps Poetry >=2.4.1, and `sqlcipher3-binary` is
marked `platform_machine == 'x86_64'` so the aarch64 fleet no longer falls back
to `requirements.txt`. **Deployment follow-up closed 8 Sep** (`04fbbcc8a`):
`update.sh` Step 0 links `aitbc-backup.service` on demand if it is missing,
instead of skipping the pre-update backup. **Deployment follow-up closed 8 Sep**
(`976cec9e9`): `update.sh` `get_node_role()` now reads both UPPER_CASE and
lower_case profile env keys, and defaults `HARDWARE_PROFILE` to the detected
hardware instead of warning about an override. The GPU-detected warning is gone
on node0/node1; `node0` `BOND_BURN_ADDRESS` was also set to the fleet value.

## 6. Tier 2 — Code fixes with tests (node2)

Heavier items. Each: branch-free commit on `main` per repo convention, tests added
or updated, live-verified where cheap.

- [x] **T2-1 · C-4** — done in `a7dd35c85a`. The write phase
  (`apply_deltas_to_db` + the `session.add` loop) is wrapped; on failure it
  rolls back and returns `success=False`, matching the other `_propose_block`
  failure exits. `tests/consensus/test_parallel_txs.py` covers mid-write
  failure, `session.add` failure, and the happy path (3 tests, green on node2).
- [x] **T2-2 · C-3** — done in `3e9a648bab`. No Phase-1.3 spec exists and the
  real gate turned out to be `sync_state_root_validation_enabled` (default
  True) — the flag was a dead duplicate, so it was deleted; the test's
  monkeypatch was dropped (the test still exercises the real check via
  `skip_state_root_validation=False`), and `ENVIRONMENT_CONFIGURATION.md` now
  names the live env var.
- [x] **T2-3 · S-2 (dedupe half)** — done in `53c1b6d608`. Added
  `_find_existing_lock` mirroring the release/refund lookups, an idempotency
  guard in `create_escrow` (409 on param mismatch, 200 + settled state on a
  true retry), and a double-lock refusal in `_create_token_escrow`. The
  coordinator refund path was re-verified as guarded-by-design (chain-side
  `_find_existing_refund` + B-residue reconciliation — a local short-circuit
  would *skip* that reconciliation, so it was left alone). **Residual carried
  to a new item below: the sweeper lock.**
- [x] **T2-3b · S-2 (sweeper lock)** — done in `374988beeb`. `run_once` now
  runs under a `filelock` (`COORDINATOR_ZK_REFUND_SWEEP_LOCK_PATH`, default
  `/var/lib/aitbc/zk_refund_sweeper.lock`); a losing worker skips the pass
  (test: held lock → `skipped=1`, no PaymentService call). Missing/unwritable
  lock file degrades to the pre-lock behaviour with a warning.
- [x] **T2-4 · S-3 — closed 7 Sep in `6651dc3b1`**. Removed `shadow_mode`,
  `spot_check_for`, and `spot_check_result` from the client `Constraints` model;
  `JobService.create_job` strips any smuggled values; `SpotCheckService` writes
  the authoritative record only to the server-created shadow `Job`; and
  `PaymentService.get_dispute_evidence` verifies the completed shadow job and
  its binding to the original before `auto_adjudicate_disputes` can refund or
  slash. Added the negative regression `test_client_forged_spot_check_result_is_ignored`.
  Lint, `no-float-money`, typecheck, and `test-apps` passed on `node2`.
- [x] **T2-5 · S-2 gate coverage** — done in `53c1b6d608`. The reconciler's
  `escrowed_at IS NOT NULL` gate was dropped: `status=='escrowed'` is the
  sufficient key, and the timestamp gate is what let inconsistently-stamped
  rows escape the sweep. `release_payment` re-verifies on-chain state, so the
  wider query is safe.
- [x] **T2-6 · B-2** — done in `eb83fbcfbe`. `lint` is strict (alias of
  `lint-strict`); the soft mode survives as `lint-report`. Nothing in CI called
  the soft target.
- [x] **T2-7a · B-3 ratchet — closed 7 Sep**. `eb83fbcfbe` added the ratchet
  and baseline (169 files); commits `39881c7830` and `b62637a792` wired
  `make c901-ratchet` into both `.gitea/workflows/ci.yml` and
  `.github/workflows/ci.yml`. Gitea CI run 19639 at `b62637a` executed the
  ratchet successfully; no complexity growth.
- [x] **T2-7b · B-3 `_propose_block` split** — **done 7 Sep**. Four commits:
  `69ef77460c` + `b9c855f5c7` (`_process_txs_sequential`,
  `_collect_and_gate_attestations`), then `6f27f25e8a` (early-gate, mempool,
  collect/commit/broadcast seams) and `24b6c88660` (the final phase split —
  `_passes_early_gates`, `_resolve_proposal_head`, `_select_round_proposer`,
  `_process_proposal_txs`, `_reject_if_all_invalid`, `_assemble_proposal_block`,
  `_run_consensus_gates`). `_propose_block` is now a seven-phase pipeline at
  ~CC 7 — **under the C901 threshold** (was ~88); poa.py's baseline drops 4→3
  (`_ensure_genesis_block` 13, `_process_txs_sequential` 19,
  `_process_txs_parallel` 15 remain as ratchet-held debt). 87/87 consensus
  tests, ruff/format/mypy clean on node2 at that historical verification.
- [x] **T2-8 · B-1** — **done 7 Sep** (`075d56f204` triage + `addb50293e`
  burn-down). All 126 quarantined IDs resolved: most were the same
  positional→option signature drift and help-text rewrites; the
  `marketplace_cmd` module, `operations marketplace` subgroup, and the
  chain-listing `marketplace create` surfaces were deleted outright along
  with their tests. The sweep also caught 4 *non-quarantined* `ai submit`
  tests that were silently red (the command now requires
  `--provider-address` for paid jobs and fails submissions whose escrow
  was not secured). `quarantined.txt` and the conftest collection filter
  are removed; `tests/cli` is back in the normal run — **1067/1067 reported
  green on node2 at that pass**. CI wiring is also present: both workflows
  invoke `make test-cli`, which includes `tests/cli`. The prior unwired-CI
  tail was stale; current run health is tracked separately in R3.
- [x] **T2-9 · B-4** — done across `4a5cc7b8df` + `600412a448`, all 7 closed:
  5 were committed specs running up to 4745 lines behind the apps (regen via
  `extract_openapi_specs.py`); the port-binding check pointed at a moved
  service file; and the order-dependent signature-metrics failure was real
  pollution — every alembic `env.py` called `fileConfig()` with the default
  `disable_existing_loggers=True`, so the in-process migrations test muted all
  pre-existing loggers for the rest of the suite (all 7 env.py files fixed).
  Full `tests/unit` suite green on node2.
- [x] **T2-10 · S-8** — closed 6 Sep: the allowlist already exists on hub
  (`sites-enabled/aitbc:261`, `limit_except GET` + explicit allows + `deny all`).
  The register's claim predated the block being written.

## 7. Tier 3 — Investigations (bounded; deliverable is a write-up)

- [x] **T3-1 · C-1** — done 7 Sep. hub `syslog.1` + hub2 journal deliver both
  halves: the proposer task hung silently at 20:09:31 (pre-1804, pre-restart),
  and the gossip collapse at 20:10:48 was a manual root-session
  `systemctl restart` of `aitbc-blockchain-rpc` (1012), not nginx capacity.
  The alerting half shipped: `227bb9e10` adds `_propose_block_with_watchdog` —
  a stalled iteration logs an error + `poa_proposer_stalled_iterations_total`
  after `max(60s, 4×interval)`.
- [x] **T3-2 · C-2 — closed 7 Sep**. Operator-approved live exercise: node1
  `aitbc-blockchain-node.service` was stopped at 2026-09-07T22:58:51+02:00,
  leaving the validator set active on hub/hub2/node2. Blocks 4619 (23:01:19),
  4620 (23:01:58), and 4621 (23:02:33) were produced with matching hashes
  across the surviving validators. node1 was restarted at 23:01:25 and
  rejoined: it caught up to 4620 within 33 s and to 4621 within ~95 s. Final
  fleet state at 23:03:51: hub, hub2, node1, node2, and node0 all at height
  4621 with hash `0xef6bfd518cb20c10776fe9f4731bcc94f561ae720623c8263052c3ef56527415`.
  Raw evidence: `/tmp/node1_outage_evidence_20260907_225846.log` (local) and
  the same path on the orchestrating host.
- [x] **T3-3 · S-5 — operator write-off, not technical reconciliation**.
  Recorded 7 Sep: the Sep-3 `fork-export/chain.fork-source.db` on hub is the
  pre-recovery ledger; 43-of-48 coordinator refunds matched on-chain refunds
  to the house wallet (4 to a buyer, 1 post-recovery). Receipt drift was fixed
  by `7a3e664eb` (`execute_job` no longer lets caller receipts displace the
  signed copy). The operator formally wrote off the historical figures
  (5.593 unaccounted, 1.4625 settled-on-drifted, 22.156875 refunded to house).
  That accounting disposition is retained; it is not proof that every
  settlement mechanism is correct. S-3 and S-4 remain subject to R1/R2.
- [x] **T3-4 · S-1** — closed 6 Sep: sweeper refunds DO settle on-chain
  (`refund_payment` → `POST /rpc/escrow/{job}/refund` → `_submit_refund_tx`
  signs an `ESCROW_REFUND`; sweeper requires the tx hash). The original finding
  predated the rpc settlement path.
- [x] **T3-5 · A-8** — inventory delivered 7 Sep (`6ee9e5c74`):
  `docs/architecture/coordinator-context-map.md` recorded 36 contexts, 48
  `include_router` calls, 72 APIRouters, flag-gated mounts, duplication
  clusters, and two API-dead contexts at that SHA. The later disposition and
  removal follow-up are recorded under Tier-7 / D-1.
- [x] **T3-6 · F-3 — recorded operator closure, 7 Sep**. The earlier worker
  and allowlist checks are retained. TASKLIST's F-3 entry records the
  operator's confirmation that the tightened rule excludes no legitimate
  caller. This corrects the stale unchecked item; the review did not repeat
  the live caller/allowlist exercise.

## 8. Tier 4 — Decision-bound (decisions and implementation history)

Existing decisions are retained. New design changes or live actions still require
an operator answer; the review is not permission to activate incomplete features.

- [x] **T4-1 · A-1 — implementation plus accepted research limitation**.
  Option B landed 7 Sep (`d42be7c76`): `dispute_payment` schedules a
  `SpotCheckService` re-execution for deterministic jobs and `resolve_dispute`
  surfaces evidence for manual ruling. The non-deterministic "proven false"
  oracle is an accepted research limitation, not solved by that implementation.
  The later automatic-adjudication path is separately reopened under S-3/R1.
- [x] **T4-2 · A-2 — end-to-end ETH→AIT round-trip closed 7 Sep**.
  `0.001` Sepolia ETH deposited from hub `test-bridge-deposit` wallet
  (tx `0xb417…d3dd`); bridge monitor on `node2` minted `2.49425` AIT to
  `0x3Ed42960a36489Fe1BA39ceCcbbd6F87C8551Ebf` (AIT tx `0xd13b…3068`,
  AIT block **4640**). Bridge was enabled and `ETH_RPC_URL` / `BLOCKCHAIN_RPC_URL`
  corrected for the live test.
- [x] **T4-3 · A-3** — closed 7 Sep (Tier-5): CLI bugs fixed (`9879293c1`) —
  GPU marketplace commands now use `/v1/` prefix and send Authorization
  headers. `/v1/marketplace/gpu/quote` added to security matrix. DynamicPricing
  contract deployed on Sepolia (`0xCC80D7…AcEa`), energy profile + rate
  configured. ABI fix (`b71d38bb3`): struct returns needed tuple ABI format.
  Coordinator configured with contract address + Sepolia RPC. Quote endpoint
  returns HTTP 200 with full operator-signed, provider-bound, energy-floor
  enforced energy quote.
- [x] **T4-4 · A-4** — closed 7 Sep (Tier-3): fail-closed implemented
  (`cc920a779`). Missing `ENERGY_OPERATOR_ADDRESS` rejects with 503; missing
  oracle config rejects with 503 instead of falling back to self-attested
  values. 3 tests pass.
- [x] **T4-5 · A-6** — closed 7 Sep: §4.3 (settlement asset/scale validation
  on escrow release) and §4.7 (miner GPU-registry ownership check at dispatch)
  were already in main via `e6d602cd65` (6 Sep); P1 tests green. The register's
  "unstarted" was stale.
- [x] **T4-6 · A-7** — closed 7 Sep (Tier-5): operator confirmed all sections
  implemented. Verified against code: §5.2 (profile enabled + provider/model
  match, `AIPowerRental.sol:455-465`), §5.3 (rate validity via `getEnergyFloor`,
  `:468-473`), §5.5 (rate enabled + funding snapshot, `:475-485`), §5.6 (struct
  fields internal across 5 contracts). v0.25.4 tag re-pointed to `e6d602cd65`.
- [x] **T4-7 · B-8 — closed 8 Sep**. `001_initial_migration` and the B-8 test
  now import `coordinator_api.models.multitenant`, so a fresh `alembic upgrade head`
  creates all declared tables and the test compares the same metadata on both sides.
  `make test-apps` includes `apps/coordinator-api/tests/integration`; Gitea 19643
  green at `c79462f3e`. Historical-schema-to-head regression closed by `0c460fe9f`
  (Gitea 19661 green): new head migration `e7f2a9c4b1d0` creates the eight `tenant_*`
  tables on historical upgrades, `5d8339a13a12` default fixed to `'[]'`, and the
  new `test_b8_historical_upgrade.py` freezes a pre-multitenant DB and asserts
  `alembic upgrade head` converges.
- [x] **T4-8 · S-4 — CLOSED 8 Sep: v3 live at block 5470** (all five hosts stamped `state_transition_version=3`, converged; later blocks verified with `parallel_tx_validation=true` enabled fleet-wide). Pure-path modeling landed via `38acca737` (lock) + `1df6eb365`/`1c8df3a50` (release/refund); `2baf883f3`/`fe5f4a451`/`e75e7355b` wire `escrow_context` prefetch into both parallel callers, pre-fetch per-escrow accounts, and keep `c901-ratchet` green (CI 19668). Live fleet converged at 5503 with identical hashes after activation.
- [x] **T4-9 · C-7 (production half)** — closed 6 Sep: `BRIDGE_RELEASE`,
  `BRIDGE_MULTISIG`, `BRIDGE_REQUIRE_MERKLE` are `true` on all five hosts — the
  production enablement already happened; the `False` code defaults are the
  intended ship posture.
  **Confirmed 8 Sep (§16.1).** The live variable names are the longer
  `BRIDGE_RELEASE_ENABLED` / `BRIDGE_MULTISIG_ENABLED` / `BRIDGE_REQUIRE_MERKLE_PROOF`
  in `/etc/aitbc/blockchain.env`. hub's running `aitbc-blockchain-node` process
  environment carries all three as `true`. Code defaults remain `False` at
  `config.py:459,481,507`. Both halves of the apparent contradiction are correct.

## 9. Tier 5 — Fleet deploy F-1 (historical record; old runbook retired)

**Superseded in part, 8 Sep (§16.2).** The pre-deploy snapshot below is historical.
All five hosts are now at `d119e8ca90` (CI-green, run 19645), clean, on `main`, zero
failed `aitbc-*` units, converged at height 5087. That deployment is not recorded
anywhere in this document; §16.2 supplies the manifest R10 asked for. The
requirements in "Requirements before any future deployment or rollback" still stand
for the *next* deployment, and the retired `b0d5fc1a5` rollback target is not merely
stale — it is on a divergent history and cannot be fast-forwarded to.

**No new deployment is scheduled or authorized by this section.** TASKLIST records
F-1 as executed on 7 Sep, targeting `6ee9e5c74`, with the fleet converged at height
4400, hash `0xbdc5e38b…`. That is a recorded historical outcome, not a fresh per-host
Git/process-version verification. R10 tracks the missing manifest/audit evidence.

### Historical pre-deploy snapshot (7 Sep)

The original plan described four hosts at `b0d5fc1a5`, 121 commits behind
`6ee9e5c74`, with node2 already at that target. Its diff was 155 files,
+12428/−24455. These figures are not a current deployment inventory.

- **Coordinator Alembic target:** `f53990f9d6cc`. hub, node0, and node2 were
  recorded at head; hub2 and node1 were at `4e8b7c2d1f0a`, requiring
  `5d8339a13a12` → `1c58c844d95e` → `f53990f9d6cc`. The three revisions had
  idempotence guards after `20d972cf7f`; this does not replace a current schema
  inventory or an upgrade/restore test.
- **Unit changes:** the three blockchain units gained the scoped validator-secrets
  EnvironmentFile; island-ipfs gained coordinator ordering/dependency entries.
- **Recorded execution:** node0 → node1 → hub2 → hub, with backups, code updates,
  migrations/schema repair, unit reloads, and restarts. TASKLIST also records
  chain-DB energy-quote column repair, which the original coordinator-only
  migration checklist did not fully describe.

### Requirements before any future deployment or rollback

The former floating-tip `reset --hard` sequence and hard-coded `b0d5fc1a5` rollback
are retired, not reusable instructions. An additive schema change alone does not
make old code compatible with blocks finalized under newer consensus/state rules.

1. **Pin and inventory:** obtain read-only per-host manifests: clean Git state,
   target/current SHA, running-service version evidence, resolved DB paths,
   schema revisions, non-secret configuration, activation rules, and a common
   block height/hash/state root. Do not skip node2 because an older plan called
   it "at tip". Use a clean fast-forward-only update to the approved SHA; stop
   on dirty/diverged state rather than discarding it.
2. **Back up consistently:** use SQLite online backups or an approved quiesced
   snapshot of all relevant databases. Abort if the required backup fails.
   A copied historical F-2 file, a checksum, or `SELECT count(*) FROM block`
   alone is not a restore test. Verify integrity and an isolated restore on an
   allowed dev/test host, including coordinator and chain databases.
3. **Approve the actual blast radius:** `scripts/deployment/update.sh` already
   fetches/merges, reloads units, runs migrations, and restarts all currently
   running `aitbc-*` services. Its backup/health warnings are not hard success
   gates. Review the exact version of the driver, use `--no-pull` when applying
   a pre-pinned checkout, and schedule migrations/restarts once rather than
   repeating the old manual steps. Migration-related service stops also count
   as disruptive actions. Each needs explicit approval.
4. **Canary and gate:** choose the sequence from the current validator/service
   roster, not this historical order. Before advancing, verify service health,
   logs, settlement invariants, matching hashes/state roots at a common height,
   and sustained block progress. All-node convergence is not the separate C-2
   one-down fault-tolerance test.
5. **Plan rollback before approval:** specify the compatible code/schema/state-rule
   combination, handling of newly finalized blocks, writer quiescence, and exact
   restore source. Any destructive restore requires separate explicit approval;
   never overwrite a live chain DB or assume an old snapshot can safely replace
   finalized state. Operator-managed configuration recovery must not resurrect
   revoked credentials or require secret contents in this document.
6. **Retain evidence:** attach the approved action record, per-host manifests,
   backup/restore verification, CI SHA/run, activation height where applicable,
   and before/after chain observations to the dated validation record. No new
   `LIVE_VALIDATION_DAYS/2026-09-07.md` was found during the review; this update
   does not create one or manufacture missing historical evidence.

## 10. Tier 6 — F-5 unpark, C-1 tracing, A-1 research note (7 Sep)

Recorded authorization covered unparking the six F-5 items, C-1 tracing, and an
A-1 research disposition. The three cited commits were pushed to gitea `main`
from the non-active IDE clone. The review retains that execution history but
narrows the C-1 and F-5f completion claims below.

- [x] **T6-1 · C-1 per-phase tracing — closed 8 Sep (R7)**.
  `7ccdabf9b` added `self._propose_phase` in `PoAProposer.__init__`, tracked
  it through every proposal phase, and included the active phase in the
  watchdog ERROR and stalled-iteration metric. `test_proposer_watchdog.py`
  verifies stalled-phase scenarios at `LOG_LEVEL=INFO` (no global DEBUG). The
  exact historical 1804 await cannot be reconstructed from existing logs, but
  future stalls are now loud and located; the register records that as a
  verified operational-observability fix, not a proof of the original failure.
- [x] **T6-2 · A-1 — accepted research limitation**. The register's research
  disposition records that TEE/ZK gates verify self-consistency, not truth.
  The optimistic challenge path exists (`SpotCheckService`, `d42be7c76`);
  the non-deterministic "proven false" oracle remains a design limitation.
  Research directions: economic security, reputation-weighted attestation,
  hardware-attested execution measurement. This accepted-risk closure is not
  a code fix or evidence that automatic adjudication is safe; see S-3/R1.
- [x] **T6-3 · F-5a (hub→hub2 provider-level block filter)** — clarification,
  not a code fix. No provider-address-based block filter exists in the source
  tree. The existing mechanisms operate on proposer identity: self-proposed
  block skipping (`sync_manager.py`), trusted-proposer authorization
  (`sync_validator.py`), and multi-validator proposer-schedule validation. The
  original wording was a confusion between provider identity and proposer
  identity.
- [x] **T6-4 · F-5b (`fetch_blocks_range` exception logging)** — `7839be1bb`.
  Exceptions were swallowed by putting error details in the log `extra` dict,
  which the default `JournalFormatter` does not render. Fix: put
  start/end/source/error in the log message itself. 31 sync tests pass.
- [x] **T6-5 · F-5c (`_parallel_bulk_import`)** — `7839be1bb`. Documented as
  disabled-by-design (not dormant). The gate requires
  `sync_parallel_enabled=True` *and* >1 registered peer; v0.6.2 only registers
  one peer. Added a comment so it is not mistaken for dead code.
- [x] **T6-6 · F-5d (`gethostname()` fallback)** — `7839be1bb`. `AITBC_HOSTNAME`
  env added as an intermediate override before `socket.gethostname()` in
  `_build_join_credentials`, with a warning when the fallback is used.
  `RPC_PUBLIC_ENDPOINT` remains authoritative for the final RPC endpoint.
- [x] **T6-7 · F-5e (RegionalPricing setters)** — already removed in
  `743c11ddf9` ("refactor(contracts): remove dead RegionalPricing machinery
  from DynamicPricing"). No additional code change needed.
- [x] **T6-8 · F-5f — CLOSED 8 Sep (§16.5); was reopened by R4**. `210a02a23` added
  62 Python `EscrowManager` tests and 40 Python `StakingManager` tests,
  reported passing. That completed subtask covers validation, milestone
  lifecycle, state guards, protected energy-floor, billing, reassignment,
  staking, withdrawal, slashing, rewards, and error paths in those Python
  classes. It does not establish branch coverage of Solidity
  `EscrowService.sol` / `AgentStaking.sol`. Keep the Python accomplishment;
  require separate contract-specific coverage evidence for the original gap.
  **Narrowed and in progress, 8 Sep (§16.5).** `AgentStaking.sol` already has four
  Hardhat suites (`AgentStaking{,Distribution,Security,Slashing}.test.js`); the real
  gap was `EscrowService.sol`, which had only `contracts/test/fuzz/EscrowService.t.sol`.
  Closed by `8cb48178d5` (09:48 on 8 Sep); **Gitea run 19646 green**, and
  `.gitea/workflows/ci.yml:47` runs `npx hardhat test`, so that run exercises the new
  suite. See §15 R4 for the full entry. R4's exit gate — contract-specific coverage
  with results at a candidate SHA — is met.

## 11. Tier 7 — Deferred cleanup (authorized 7 Sep)

The four deferred items and the later operator-supplied flagged-item cleanup are
recorded below. A-8's inventory/dead-context follow-up is recorded complete through
D-1. D-4's older workflow-presence findings are distinct from the failed reviewed CI
run and missing verification gates in R3–R5; this section is not a blanket sign-off.

- [x] **T7-1 · D-1 — Remove API-dead contexts** — `ff6ef7634`. Removed
  `agent_economics` (yield_adapter.py, 109 lines, never imported) and
  `preferences` (redis_cache.py, 75 lines, never imported). Three files, 184
  lines of dead code.
- [x] **T7-2 · D-2 — Mesh gossip auth gap — CLOSED 8 Sep (re-derived on `main`).**
  The challenge/response validator auth, restricted/public topic gating, rate
  limiting, and connection limits are present on `main`. The cited
  `761b887837` exists only on `origin/feat/open-island-gossip-remediation`, but
  it has an identical tree to `252469f3b`, which **is** on `main`. The two
  subsequent fixes `b990194ed7` and `20257c5975` are also on `main`. Relevant
  tests (`test_websocket.py`, `test_gossip_broadcast.py`, `test_network_info.py`)
  pass on `node2`. The `feat/open-island-gossip-remediation` branch carries six
  commits ahead of `main`; three are tree-duplicates of work already on `main`
  (`761b887837` → `252469f3b` for D-2; `1484e614f5` → `f8a09b547c` for the CLI
  escrow guard; `f3f33a8c6d` → `886b10b79` for its test). The three genuinely
  unmerged commits are `d3693d01ab`, `5fbe633c7f`, and `ffe0669023` (contracts
  CI pipeline changes). The escrow guard is **closed on `main`** at `f8a09b547c`
  with regression test `886b10b79`; `cli/tests/test_ai_tee_submit.py` passes on
  `node2`.
- [x] **T7-3 · D-3 — hub.aitbc resource limits** — already resolved. MemoryMax
  raised to 1GB via `systemctl set-property` drop-in; recorded usage ~156MB.
  mypy not installed on hub; dev tooling belongs on node2/hub2, not the small VPS.
- [x] **T7-4 · D-4 — CI/test hygiene gaps** — already resolved. 159 Hardhat
  tests pass on node2; GitHub Actions already has `make lint-strict`,
  `npx hardhat test`, `forge test -vvv`. gitea-local tea login verified
  working on gitea-runner.
  **Scope:** retained as the operator's workflow-presence/test-run record, not
  proof that the reviewed candidate passes CI or covers the Solidity gaps.
  R3–R5 track those separate findings; the working tea login is not reopened.
  **Corrected 8 Sep (§16.6):** across the five hosts, `tea` is installed only on
  node2 (0.15.1) and hub (0.14.2). hub's `aitbc-gitea` login authenticates and was
  used for the §16 CI audit. node2's `bubuit` login points at
  `http://gitea.bubuit.net:3000` and its token is rejected as
  "invalid username, password or token" for both the user and root. If the original
  record referred to the separate `gitea-runner` host, that host is outside these
  five and was not inspected.
- [x] **T7-5 · Flagged items cleanup** — five items investigated and resolved:
  hub.aitbc connectivity (transient CPU/IO stall, self-resolved), node2
  key-audit false-positive fix (`c16ccb95a`), gitea-local tea login verified
  working, Duplicate Operation ID fixed (`2b112f9f46`), shop-wallet.json
  verified as properly encrypted (not a bug).

## 12. Operator lane (O-1…O-6 — never executed by the agent)

**Operator posture, stated 8 Sep:** this fleet is a fast-forward dev
environment, not a production-hardened deployment. Credential-hygiene findings
(exposed keys in backups, rotation schedules, purge cycles) are recorded, not
automatically remediated — they are fixed only when they break function or the
operator explicitly asks. Under this posture the `BOND_SLASH_PRIVATE_KEY`
transcript exposure is accepted risk and the "rotate + purge backups" residual
is **not planned work**; it closes as recorded.

The historical records below are retained. This review did not inspect secrets or
repeat credential actions. O-1 was resolved by dated operator confirmation on
8 Sep, not another local cache cleanup.

| ID | Action | Status note |
|---|---|---|
| O-1 | Revoke node2's GitHub token at github.com/settings/tokens | **closed 8 Sep (R8):** operator confirmed the specific PAT is revoked at github.com/settings/tokens. Recorded as dated operator attestation — the token was not requested, read, copied, or tested. Local cache clearance / no stored credentials on node2 was recorded 7 Sep. |
| O-2 | Rotate `PROPOSER_KEY` or scrub hub auth.log/journal (key was grep-logged) | **closed 7 Sep (Tier-4):** key scrubbed from auth.log/auth.log.1, journal vacuumed. Key rotated: new address `0xe738…d225`, VALIDATOR_SET updated on all 5 nodes, fleet converged at 4446 |
| O-3 | Rotate hub Redis password; create `/etc/aitbc/redis.env` | **closed 8 Sep — needed, now wired fleet-wide:** the file supplies `REDISCLI_AUTH` to `aitbc-cache-monitor.service` (EnvironmentFile is optional by design). Correction to the earlier audit: redis-server **runs on all five hosts** (gossip backend); auth is configured only on hub + node2, which is why `redis.env` exists only there. The real gap was that the monitor unit was never installed **and** the role-aware relink silently removed it — `link-systemd.sh` deletes all `aitbc-*` links and relinks only role services. Fixed in `7d93b678a`: `aitbc-cache-monitor` is now allowed whenever a `redis-server` unit exists (gated via `systemctl cat`, avoiding a pipefail SIGPIPE trap), `setup.sh` creates `redis.env` on Redis hosts and enables the timer in `setup_autostart`. Monitor installed + running on all 5 hosts; first runs succeed. |
| O-4 | Amend mislabeled commits `ba01001d0` / `f3e0d3816e` | **closed 7 Sep (Tier-3):** amended on feature branches, force-pushed; main untouched |
| O-5 | `VALIDATOR_KEYS` scope | **closed 7 Sep:** node0 confirmed; all five hosts have scoped validator secrets |
| O-6 | Correct the "with your approval" record | **closed 7 Sep (Tier-5):** correction recorded in the register. The recovery report's claim is incorrect — no approval was given. External report not in repo; correction stands in the register. |

## 13. Suggested order & dependencies (review follow-up)

The tiers above are execution history, not a queue to replay.

1. **R1 / S-3:** establish trusted dispute evidence before relying on automatic
   adjudication. Add negative regressions before changing the implementation.
2. **R2 / S-4:** complete custody authorization, version propagation, and the
   v2→v3 transition design. A metadata/version flip alone is not a fix.
3. **R3–R5:** restore green CI for the exact candidate SHA; wire the C901 and
   migration guards into real workflows; collect coverage for the correct
   Solidity components. R7 observability work can proceed independently.
4. **R6 / C-2:** after the candidate is verified and usable diagnostics are
   available, obtain per-action approval for the post-fix outage/rejoin exercise.
   Do not confuse restored all-node convergence with progress during an outage.
5. **R9 / A-2:** perform the ETH→AIT validation only when the operator supplies
   prerequisites and explicitly approves the test transactions.
6. **R10:** capture non-secret deployment/source evidence and reconcile the
   register. Any new deployment or S-4 activation first needs the §9 gates and
   fresh explicit approval; neither is scheduled by this document.

**Independent operator action:** R8 / PAT revocation was confirmed by the
operator on 8 Sep and is closed. Already-completed P-4/P-5/A-5/B-1/F-3 items are
not rescheduled.

## 14. Acceptance criteria

**Met at the 8 Sep final reviewed SHA `aef0b5099` (Gitea CI 19673 green). The register
is fully closed.** All 58 IDs carry a dated disposition and evidence; see §16.8 and
§18 for the summary table. The remaining residual is R10's manifest evidence gap
(no per-pull approval log; the service-level networked rejoin/restore test was completed
post-close on `node0`, so only the approval-log residual remains, recorded as not
establishable and not manufactured), which is closed as a recorded residual rather than an
open register item. TASKLIST reconciliation is completed in this edit.

- Every ID has a dated, explicit disposition: **closed with evidence**, **stale**,
  **implementation/activation pending**, **verification pending**, **operator
  confirmation blocked**, or **accepted risk / written off**. Accepted-risk and
  write-off dispositions do not imply technical remediation.
- For each applicable item, retain this status shape:
  `ID | disposition | closing SHA | test/CI evidence | deployed/activated | live evidence | owner | residual`.
- Evidence names the tested SHA, command/suite, node, result, date, and CI run;
  skipped checks are not passes. Historical counts cannot certify newer commits.
- Deployment and protocol activation are separate gates. S-4 requires all relevant
  production/replay paths and pre-activation escrows to be covered before any
  approved activation. Live monetary or service-disrupting checks require explicit
  per-action approval, even when tests or code review pass.
- No inherited item enters implementation without fresh re-derivation. Code paths
  and source line references must be resolved at the candidate SHA.
- TASKLIST reconciliation remains a separate follow-up: map the original 54 IDs,
  split sub-items, D-lane additions, and flagged cleanup separately; derive counts
  from that mapping rather than hand-edited summary numbers. This edit changes
  MEGAPLAN only and does not claim the other artifacts are synchronized.
- Preserve operator decisions and historical evidence without turning an old
  approval into permission for a new action. Never include secret values in any
  completion or verification record.

## 15. Review findings and closure gates (7 Sep)

### Review scope and evidence boundary

The review read this plan, relevant TASKLIST entries and local artifact summaries,
canonical code at `ff6ef763472cbcf8732951766c18825859169a79`, Gitea metadata/CI, and
read-only fleet RPC responses. It did not rerun test suites, execute transactions,
restart services, inspect credentials, or independently repeat every historical
closure. Later operator-supplied cleanup in T7-5 is retained, not re-audited here.

At common height **4544**, all five queried nodes returned block hash
`0x93d084d42db2788f791f596acf53e4871ce26551909c9a282c6aca77655655bc`, state root
`0x0bb76ce60d47630c426e790fc4efeb705f125b3c4d82bd202da612c1ba4127a8`, and
`state_transition_version=2`. This is a consistency spot-check, not a sustained
fault-tolerance test or proof of identical deployed Git SHAs.

Source references below are within `/opt/aitbc`; shortened paths refer to the
named component. Line numbers belong to the pinned review snapshot. Re-resolve
paths, symbols, and lines before implementing a follow-up.

### R1 — S-3: closed 7 Sep — client constraints separated from server-owned spot-check evidence

- **Evidence (original):** public `Constraints` in
  `apps/coordinator-api/src/coordinator_api/custom_types.py:57-62` accepted
  `spot_check_result` and shadow-job fields. `JobService.create_job` persisted
  request constraints directly; `PaymentService.get_dispute_evidence` read the
  stored dictionary without provenance checks. The admin router's
  `auto_adjudicate_disputes` trusted that value to refund and, when a bond was
  required, slash.
- **Fix (commit `6651dc3b1`):**
  - Removed `shadow_mode`, `spot_check_for`, and `spot_check_result` from the
    client `Constraints` Pydantic model and added `extra="ignore"`.
  - `JobService.create_job` now strips the same server-only keys from any
    incoming constraints dict as a defense in depth.
  - `SpotCheckService.complete_spot_check` stores the authoritative spot-check
    result on the server-created shadow `Job` row only; it no longer writes
    `spot_check_result` back to the original job's client-writable `constraints`.
  - `PaymentService.get_dispute_evidence` looks up the completed shadow job by
    `spot_check_for`, verifies `shadow_mode`, and confirms the record's
    `spot_check_job_id` and `original_job_id` match the shadow and original jobs.
    Client-forged `spot_check_result` on the original job is ignored.
- **Regression tests:**
  - `test_s3_auto_adjudicate.py` updated to create a server-owned shadow job as
    the evidence source.
  - New `test_client_forged_spot_check_result_is_ignored` proves a client-supplied
    `spot_check_result` cannot trigger auto-adjudication.
  - `test_a1_dispute_spot_check.py` updated to use the shadow job for
    `get_dispute_evidence`.
- **Verification:** `make lint-strict`, `make no-float-money`, `make typecheck`,
  and `make test-apps` all passed on `node2` before the commit. The OpenAPI spec
  was regenerated because the `Constraints` schema changed.
- **CI:** Gitea run **19640** on `6651dc3b1` completed successfully.
- **Deployment:** `aitbc-coordinator-api.service` on `hub.aitbc` restarted 8 Sep; process is at `c79462f3e`, `/health` returns `ok`, and the live OpenAPI `Constraints` schema no longer contains `shadow_mode`.
- **Limitation:** This is a static/CI closure. A live dispute-to-spot-check
  end-to-end exercise (dispute, shadow re-run, auto-adjudication) has not been
  performed; that remains a separately approved live validation step.
- **Status:** Closed 7 Sep.

### R2 — S-4: closed in code, activated live, and parallel-wired 8 Sep

- **Original evidence:** `apps/blockchain-node/src/aitbc_chain/consensus/poa.py:654`
  stamped version 2; transaction application also passed `block_version=2`
  (`poa.py:1579,1667`); `config.py` / `get_block_version` provided only a v1/v2
  fallback; `state/pure_state_transition.py::compute_state_delta` had no version
  parameter. v3 release/refund checked job id and escrow balance but did not bind
  the recipient to the chain-derived buyer/provider or establish a settlement
  authority, and there was no cross-activation settlement rule for outstanding
  v2 escrows.
- **Fix (commit `d119e8ca9`; initial S-4 implementation at `f1b0d465a`):**
  - Added `state_transition_v3_height` to `ChainSettings`; `get_block_version` now
    falls back through v3/v2/v1, and `get_block_version_for_height` lets the
    proposer stamp the correct `state_transition_version` for a *new* block.
  - The proposer now stamps `metadata_dict["state_transition_version"] =
    get_block_version_for_height(next_height)` and applies the block's
    transactions with that same `block_version`.
  - `ESCROW_LOCK` v3 validation requires `job_id` and `provider` in the payload.
  - `ESCROW_RELEASE`/`ESCROW_REFUND` now look up the original lock transaction and:
    - enforce the recipient matches the provider (release) or buyer (refund);
    - enforce the sender matches the configured settlement authority when
      `escrow_settlement_authority`/`ESCROW_RELEASE_ADDRESS` is set;
    - take funds from the per-escrow address only when the lock itself was a v3
      per-escrow lock, otherwise keep the legacy node-wallet path (v2→v3
      cross-activation rule).
- **Residual (progressively closed 8 Sep):** `f7262cc64` made
  `state/pure_state_transition.py::compute_state_delta` block-version aware and
  disabled the parallel paths for v3 blocks. `38acca737` models v3 `ESCROW_LOCK`
  in the pure path: funds go to the deterministic per-escrow address, `job_id` and
  `provider` are validated, and the provider account is created as an
  `extra_account` in both the in-memory map and the DB. `1c8df3a50` models v3
  `ESCROW_RELEASE` and `ESCROW_REFUND` in the pure path: `compute_state_delta`
  takes an `escrow_context` with `lock_version`, `expected_beneficiary` and
  `escrow_addr`; v3 release/refund debits the per-escrow address, credits the
  provider/buyer, validates the settlement authority, and charges only the fee to
  the sender; v2 release/refund keeps the generic value+fee path.
  `2baf883f3`/`fe5f4a451`/`e75e7355b` wire `escrow_context` into `poa.py` and
  `sync_block_import.py`, pre-fetch per-escrow accounts, build the context for
  v2/v3 release/refund, and widen the parallel gate to `block_version in (2, 3)`
  so the `parallel_tx_validation` feature flag is safe to enable across the v3
  activation boundary. Gitea CI run **19668** on `e75e7355b` completed
  successfully.
- **Verification:** `make lint-strict`, `make typecheck`, `make no-float-money`,
  and `make test-apps` passed on `node2`. Gitea CI run **19662** on `38acca737`
  completed successfully. Gitea CI run **19665** on `1c8df3a50` completed
  successfully; focused blockchain-node tests
  (`test_pure_state_transition_version.py`, `test_s4_per_escrow.py`,
  `test_parallel_txs.py`, `test_parallel_determinism.py`,
  `test_parallel_performance.py`) passed on `node2`.
- **Status:** Closed 8 Sep in code, activated live, and parallel-callers wired:
  v3 escrow rules (`ESCROW_LOCK`, `ESCROW_RELEASE`, `ESCROW_REFUND`) are modeled
  in the sequential and pure state-transition paths, the proposer and block-import
  parallel paths build and pass `escrow_context`, and block 5470 is stamped
  `state_transition_version=3` on all five hosts. The `parallel_tx_validation`
  flag still defaults to off; it is now safe to enable across v2/v3 blocks.

### R3 — CI health and B-3: closed

- **Evidence:** [Gitea run 19639](https://gitea.bubuit.net/oib/aitbc/actions/runs/19639)
  on `b62637a792` completed successfully (8m). It covered `lint-strict`,
  `c901-ratchet`, `no-float-money`, `typecheck`, `test`, `test-apps`, `test-cli`,
  `test-governance`, OpenAPI drift, version consistency, and the CLI live dry-run.
- **Wiring:** commits `39881c7830` and `b62637a792` added `make c901-ratchet` to
  both `.gitea/workflows/ci.yml` and `.github/workflows/ci.yml`, and `make test`
  now includes `mcp-server/tests`. The C901 ratchet passed with 169 baselined files.
- **Note:** the typecheck gate required a small MyPy baseline adjustment for two
  per-file `unused-ignore` patterns in coordinator RL/fusion modules (reported when
  `torch` is absent) and an `opentelemetry.trace` import style fix in
  `apps/blockchain-node/src/aitbc_chain/observability/exporters.py`.
- **Exit gate met:** green CI at the candidate SHA covering the required checks.
  Next candidate still requires its own rerun.
- **Widened 8 Sep (§16.5).** Run 19639 is green, and so is every run this document
  cites. What it does not say is that **runs 19477–19638 are 162 consecutive
  failures**: the entire Tier-6 execution window, and most of Tier 4, merged to
  `main` on red CI. `b62637a792` — the "candidate" — is the commit that *repaired*
  CI. The per-commit `make lint-strict / typecheck / test-apps` results recorded on
  node2 for those commits were therefore never corroborated by a passing pipeline.
  R3 remains closed as written; the surrounding history is not the green record the
  tier entries imply.

### R4 — F-5f: closed 8 Sep (EscrowService named coverage; releaseTime bug fixed)

- **Original evidence:** `apps/blockchain-node/tests/test_escrow_branches.py`
  imports Python `aitbc_chain.contracts.escrow.EscrowManager`;
  `test_staking_branches.py` imports Python
  `aitbc_chain.economics.staking.StakingManager`. The 62 + 40 tests target those
  Python classes, not `contracts/contracts/EscrowService.sol` /
  `AgentStaking.sol`. Hardhat tests existed for `AgentStaking` but not for
  `EscrowService`.
- **Fix (commit `8cb48178d`):**
  - Added `contracts/contracts/mocks/MockEnergyPricing.sol` so protected-compute
    escrow tests can exercise `EscrowService.createComputeEscrow` without
    requiring the full `DynamicPricing` deployment.
  - Added `contracts/test/EscrowService.test.js` (23 tests) covering
    constructor zero-address guards, `createEscrow` validation and fee
    collection, `releaseEscrow` (arbiter, time-based, multi-sig,
    unauthorized), `refundEscrow` (before/after release time, arbiter),
    `freezeEscrow`/`unfreezeEscrow`, `createComputeEscrow` with and without
    energy pricing, emergency release with arbiters and voting thresholds, and
    view/enumeration functions.
  - Fixed `EscrowService.createEscrow` so it persists `_releaseTime` into
    `escrowAccounts[escrowId].releaseTime`. The previous code left the field at
    its default (0), which made time-based release checks always pass and
    refund checks always fail. This bug was caught by the new tests.
- **Verification:** `npx hardhat test` in `contracts/` passes **182** mocha
  tests, up from 159. `make lint-strict`, `make typecheck`, and
  `make no-float-money` on `node2` pass. Gitea CI run **19646** on `8cb48178d`
  completed successfully.
- **Residual:** the remaining Solidity contracts have no named coverage yet.
  `AgentStaking` already has 53 hardhat tests; other contracts can receive
  similar focused suites as needed.

### R5 — B-8: closed 8 Sep (fresh schema); historical upgrade regression remains

- **Original evidence:** `apps/coordinator-api/alembic/versions/001_initial_migration.py:28`
  called `SQLModel.metadata.create_all` after importing `coordinator_api.main`.
  `models.multitenant` was not imported by `main`, so a fresh `alembic upgrade head`
  created only the subset of tables that `main` happened to load.
  `apps/coordinator-api/tests/integration/test_b8_schema_conformance.py:53-61`
  derived expected columns from the same process metadata as the test, so whether
  the test saw the missing tables depended on the pytest collection order. The
  `Makefile::test-apps` target also selected only flat `tests/test_*.py` files,
  excluding the integration test from CI.
- **Fix (commit `3d09e8105`):**
  - Added `import coordinator_api.models.multitenant` to both the
    `001_initial_migration` upgrade/downgrade and to the B-8 test's model loader.
    The migration and the test now use the same full metadata, so the 8
    `tenant_*` tables (`tenants`, `tenant_users`, `tenant_quotas`,
    `usage_records`, `invoices`, `tenant_api_keys`, `tenant_audit_logs`,
    `tenant_metrics`) are created and verified deterministically.
  - Added `apps/coordinator-api/tests/integration` to `Makefile::test-apps` so
    the schema-conformance and migration-graph tests run in CI.
- **Verification:** `make lint-strict`, `make typecheck`, `make no-float-money`,
  and `make test-apps` all passed on `node2`. Gitea CI run **19643** on
  `c79462f3e` completed successfully.
- **Residual closed 8 Sep (`0c460fe9f`):** exercised the real historical path
  against the 2026-08-09 `chain_coordinator.db` backup (stamped `236edfbd9728`).
  It caught two genuine bugs: `5d8339a13a12` used a non-constant
  `server_default=sa.text("[]")` that sqlite rejects on `ALTER TABLE ADD COLUMN`
  (fixed to `'[]'`), and the eight `tenant_*` tables were never created on
  historical upgrades because they only come from `001_initial`'s `create_all` —
  new head migration `e7f2a9c4b1d0` creates them with `checkfirst`. Post-fix the
  real backup upgrades `236edfbd9728 → e7f2a9c4b1d0` cleanly with all 24
  historical rows intact and zero model drift. Regression test
  `test_b8_historical_upgrade.py` freezes a DB at the pre-head revision, drops
  the tenant tables, upgrades, and asserts convergence + sentinel survival.
- **Status:** B-8 fully closed 8 Sep (fresh schema + historical upgrade).

### R6 — C-2: node1 `aitbc-blockchain-node` outage — closed

- **Approved scope:** stop only `aitbc-blockchain-node.service` on node1; keep
  `aitbc-blockchain-rpc` and other services running.
- **Candidate / configuration:** Gitea `main` at `b62637a792` (post CI-green
  commit) with live node env `BLOCK_TIME=60`, `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`,
  PBFT active, validator set 4-of-4.
- **Evidence:**
  - Stop at 2026-09-07T22:58:51+02:00; service reported `inactive`.
  - Surviving validators (hub/hub2/node2) produced block 4619 at 23:01:19,
    block 4620 at 23:01:58, and block 4621 at 23:02:33; hashes matched across all.
  - Restart at 23:01:25; node1 reached 4620 by 23:01:58 and 4621 by 23:03:07.
  - Final fleet check at 23:03:51: hub, hub2, node1, node2, and node0 all at
    height 4621, hash `0xef6bfd518cb20c10776fe9f4731bcc94f561ae720623c8263052c3ef56527415`.
- **Log:** `/tmp/node1_outage_evidence_20260907_225846.log`.

### R7 — C-1: closed 8 Sep — active phase in watchdog ERROR and metric

- **Fix (commit `7ccdabf9b`):**
  - Added `self._propose_phase` in `PoAProposer.__init__` and updated
    `_propose_block` to set it before each await-bearing and synchronous phase
    (`idle`, `early_gates`, `resolve_head`, `collect_txs`, `assemble_block`,
    `consensus_gates`, `broadcast`).
  - Updated `_propose_block_with_watchdog` to read the active phase when the
    watchdog fires and include it in the ERROR log:
    `(phase=<name>)`. The message is now actionable at `LOG_LEVEL=INFO`.
  - Added a per-phase metric counter
    `poa_proposer_stalled_iterations_total_phase_<phase>` alongside the existing
    total counter.
  - Made `watchdog_after` an optional test-only parameter so tests can run at
    millisecond scale without changing production thresholds.
- **Tests:** added `apps/blockchain-node/tests/consensus/test_proposer_watchdog.py`
  covering `early_gates`, `consensus_gates`, and `broadcast` stalls at
  `LOG_LEVEL=INFO`; total and per-phase metric increments; and the `_propose_phase`
  attribute being set before the await-bearing call.
- **Verification:** `make lint-strict`, `make typecheck`, `make no-float-money`,
  and `make test-apps` pass on `node2`; Gitea CI **19652** on `7ccdabf9b` green, **19653** on `79769fb57` green.

### R8 — O-1: local cleanup vs token revocation — closed 8 Sep

- **Evidence:** local cache clearance was recorded 7 Sep; on 8 Sep the operator
  confirmed the specific node2 GitHub PAT is revoked at
  github.com/settings/tokens. Recorded as dated operator attestation; the token
  was not requested, read, copied, or tested.
- **Exit gate:** met — dated operator confirmation obtained 8 Sep. This is
  attestation, not independent verification; no token value exists in the record.

### R9 — A-2: end-to-end ETH→AIT bridge round-trip closed 7 Sep

- **Evidence:**
  - Bridge enabled on `node2` by setting `BRIDGE_ENABLED=true` in
    `/etc/aitbc/exchange.env` and restarting `aitbc-wallet`.
  - `GENESIS_WALLET_ADDRESS` set to the address matching the private key in
    `/etc/aitbc/node.env` (`0xbDCd234aCB32cDd876CD3691515ea91a620793e2`) so the
    monitor can sign mint transactions; `BLOCKCHAIN_RPC_URL=https://hub.aitbc.bubuit.net`
    added so mint transactions are submitted to the proposer.
  - `ETH_RPC_URL` corrected to `https://ethereum-sepolia-rpc.publicnode.com` in
    `/etc/aitbc/exchange.env` because `eth.llamarpc.com` returned SSL 525 from node2.
  - Sepolia ETH deposit: `0.001` ETH sent from hub `test-bridge-deposit` wallet
    (`0x72184bFF2Ad4081347a00B26712D90bf49644E97`) to bridge deposit address
    `0x322996afC154312E04F76d241F972DfF011Af7df`.
    - Sepolia tx hash: `0xb417a0f715c3b89ae2ef6afb57f73e5099fa7b85954f69be73310a56d0ecd3dd`
    - Confirmed in Sepolia block `0xb1de2a`, status `0x1`.
  - Bridge monitor on `node2` detected the deposit and minted `2.49425` AIT to
    `0x3Ed42960a36489Fe1BA39ceCcbbd6F87C8551Ebf`.
    - AIT tx hash: `0xd13b9cf19f9796405a77e7c255f6b5c759d82ed98978598916bbe4ba6f073068`
    - Included in AIT block **4640**.
  - On-chain confirmation:
    - Recipient `0x3Ed4…1Ebf` balance: `89,793,000` compute-units = 2.49425 AIT.
    - Mint source `0xbDCd…93e2` nonce advanced from 3 to 4; balance decreased by
      `90,153,000` compute-units (amount + fee).
  - `/v1/bridge/deposits` on node2 shows the deposit as `completed`.
  - Redacted MCP bridge-status tool (`get_eth_bridge_status_redacted`) deployed from
    `b62637a792` and verified; it returns the safe bridge status fields and omits
    `rpc_url`. The wallet's raw `GET /v1/bridge/status` endpoint still returns `rpc_url`
    (`https://ethereum-sepolia-rpc.publicnode.com`, no API key).
- **Status:** Closed 7 Sep.
- **Limitations / follow-up:**
  - The hub `genesis` wallet (`0xFe2d63FE87Db282083b9159e5857Cac788af9E03`) had
    **0** Sepolia ETH, so `test-bridge-deposit` was used as the sender.
  - Bridge config changes are live in `/etc/aitbc/exchange.env` on `node2`; they
    must be preserved when the wallet service is next upgraded/restarted.

### R10 — F-1 and register evidence: complete the audit trail, not another deploy

- **Evidence:** TASKLIST records F-1 executed, but the old MEGAPLAN still prescribed
  a floating-tip update and hard-coded rollback. §9 now retires those instructions.
  No dated `LIVE_VALIDATION_DAYS/2026-09-07.md` was found during the review, and
  matching RPC blocks do not prove the deployed Git/process-version manifest.
  **Refreshed 8 Sep (§16.2 second pass):** per-host manifest re-captured — fleet
  at tip `6e6bb21615` (CI 19651 green), converged at height 5246; coordinator
  `alembic_version = f53990f9d6cc` (the §9 target head); daily
  `/var/backups/aitbc` snapshots present on all five hosts. node2 carries two
  uncommitted R7 files.
- **Exit gate:** partly met — manifest, schema inventory, backup-existence, and
  CI evidence are now attached, and historical records are distinguished from
  fresh observations. Still not established: a per-pull approval log for the
  advance to tip, and a backup restore test — neither is manufactured. §9's
  safeguards still govern any separately approved future deployment.
- **Register follow-up:** ~~reconcile TASKLIST separately with these dispositions;~~
  **done 8 Sep with operator approval** — TASKLIST's stale "3 open / 0
  operator-only / 7 lanes" header is struck and replaced with an explicit-ID
  count (58 IDs: 54 original + D-1–D-4), and the item texts that disagreed with
  the 8 Sep dispositions were corrected or annotated (O-1, O-3, A-2, C-1, S-3,
  S-4, B-8, F-1, A-1, D-2, sources availability). Retained as completed: A-5
  (`7fecd759d2`), P-4 (`c341087843`), P-5 (`8cff16db7`), B-1 CI wiring, and
  F-3's recorded operator closure. A-1 is classified as accepted research risk
  and S-5 as an operator write-off. The working tea login and the operator's
  T7-5 cleanup remain recorded as supplied.


## 16. Independent verification (2026-09-08)

### Scope and method

A read-only audit of this document's claims, run on 8 Sep from the IDE host against
three sources: Gitea `main` in `/opt/aitbc` (fetched, not modified), the authenticated
Gitea Actions API via `tea api --login aitbc-gitea` executed on `hub.aitbc`, and
`ssh` reads plus RPC `GET`s on all five hosts. No builds, no test runs, no service
actions, no writes to any host, no commits, and no token value was read, printed, or
copied — `tea` supplied its own credential. Findings below take precedence over §15
wherever the two disagree on live or CI state.

Every SHA this document names was checked for existence and reachability: **all
resolve**, and all are ancestors of `origin/main` except three — `761b887837`
(§16.3), and `ba01001d0` / `f3e0d3816e`, whose absence from `main` is consistent
with O-4's "amended on feature branches, main untouched".

### 16.1 Confirmed as written

- **T2-2 / C-3** — `enforce_state_root_validation` is gone from the code; only a
  test comment, an `ENVIRONMENT_CONFIGURATION.md` row, and a changelog line remain.
- **T7-1 / D-1** — `yield_adapter.py` and the `preferences` `redis_cache.py` are
  absent from the tree at tip.
- **T2-6 / B-2** — `Makefile:34` is `lint: lint-strict`; `lint-report` survives as
  the soft target.
- **T2-7a / B-3** — `make c901-ratchet` appears in both `.gitea/workflows/ci.yml`
  and `.github/workflows/ci.yml`.
- **T2-8 / B-1** — no `quarantined.txt` anywhere in the tree; `make test-cli`
  includes `tests/cli`.
- **R5 / B-8** — `import coordinator_api.models.multitenant` is present at
  `001_initial_migration.py:32`; `apps/coordinator-api/tests/integration` is in
  `Makefile::test-apps`.
- **P-4 / P-8** — root `pyproject.toml` has a single canonical `[project]` block
  with `dynamic = ["dependencies"]`; `apps/api-gateway/pyproject.toml:12-13`
  declares `slowapi` and `pydantic`.
- **R2 residual** — v3 `ESCROW_LOCK` is modeled in the pure path
  (`38acca737`) and v3 `ESCROW_RELEASE`/`ESCROW_REFUND` are modeled in the pure
  path (`1c8df3a50`): `compute_state_delta` takes `block_version` and
  `escrow_context`; the per-escrow address is debited, the provider/buyer is
  credited, and the settlement authority is validated. The parallel paths remain
  disabled for v3 blocks because `poa.py` and `sync_block_import.py` still call
  `compute_state_delta` without `escrow_context` and the enable condition remains
  `block_version == 2`. **Superseded 8 Sep (evening):** both callers now build and
  pass `escrow_context` and the gate reads `block_version in (2, 3)` — verified at
  `poa.py:843,845,850` and `sync_block_import.py:404,406,493` (note: the file is at
  `aitbc_chain/sync_block_import.py`, not `aitbc_chain/sync/`). Activation is no
  longer pending: block 5470 was stamped v3 on all five hosts.
- **S-4 activation posture** — `STATE_TRANSITION_V3_HEIGHT=5470` is set in
  `/etc/aitbc/blockchain.env` on all five nodes. Block **5470** was reached and
  stamped `state_transition_version=3` on all five hosts with an identical hash
  (`0x7af8de9c…88a7af`) at 2026-09-08T16:52:18Z. Live v3 rules are now active.
- **T4-9 / C-7** — see the note on T4-9. Code defaults `False`, production `true`,
  verified in hub's running process environment. Both halves are correct.
- **CI claims** — all four green runs verified on the correct SHAs: 19639
  (`b62637a792`), 19640 (`6651dc3b13`), 19643 (`c79462f3e2`), 19644 (`f1b0d465a4`).
  Run 19635 (`ff6ef76347`) is a **failure**, matching this document's own
  description of it as the failed reviewed run.

### 16.2 Fleet manifest — the deployment this document does not record

Collected 8 Sep, read-only, from all five hosts. This is the per-host evidence R10
asked for.

| Host | HEAD | Branch | Dirty | Failed `aitbc-*` units | Chain head |
|---|---|---|---|---|---|
| node0 | `d119e8ca90` | main | 0 | 0 | 5087 `0x3ee54d9abae49bd327…` |
| node1 | `d119e8ca90` | main | 0 | 0 | 5087 `0x3ee54d9abae49bd327…` |
| node2 | `d119e8ca90` | main | 0 | 0 | 5087 `0x3ee54d9abae49bd327…` |
| hub.aitbc | `d119e8ca90` | main | 0 | 0 | 5087 `0x3ee54d9abae49bd327…` |
| hub2.aitbc | `d119e8ca90` | main | 0 | 0 | 5088 `0x5a22f285250d6042c8…` |

All five `/health` endpoints on `:8202` return `ok`. hub2 leading by one block is
ordinary proposer timing, not divergence.

`d119e8ca90` ("fix(s4): new blocks default to v2, not v1") is **CI-green — Gitea run
19645, success**. It was committed at 09:23 on 8 Sep, two minutes after this
document's last edit, which is why §9 does not mention it.

**Superseded 10:40 on 8 Sep.** An operator-requested `sync.sh pull` of `8cb48178d5`
to all five hosts was a no-op: a concurrent session had already advanced them past
it. All five are now at **`ae7dd6b9be`** ("docs(v0.25.5): post-audit corrections"),
clean, on `main`, zero failed units, converged at height 5135 hash
`0xd8ad222afd3a14…`. `8cb48178d5` is an ancestor, so the requested target is
deployed. `pull` is fast-forward-only and restarts nothing (`deploy` is the
restarting verb), so no service was disrupted.

Consequences:

1. §3 item 6 and §9's pre-deploy snapshot are historical, not current. The fleet is
   at tip, not ~96 or 121 commits behind.
2. **`b0d5fc1a5` is not an ancestor of `main`** — `git rev-list --left-right --count`
   gives 63 commits unique to it against 145 unique to `main`. The retired rollback
   target is on a divergent history. §9's rule 1 ("clean fast-forward-only update to
   the approved SHA") cannot be satisfied from that SHA at all. Record the reason as
   divergence, not staleness.
3. R10's exit gate is partly met by this table for the *current* state. It does not
   supply the approval record, backup evidence, or schema inventory for whichever
   deployment moved the fleet here, and this audit does not manufacture them.

**Refreshed ~13:15 CEST on 8 Sep (R10 evidence pass).** Read-only re-sweep; the
fleet has advanced past `ae7dd6b9be` to gitea `origin/main` tip `6e6bb21615`.

| Host | HEAD | Branch | Dirty | Failed `aitbc-*` units | Chain head |
|---|---|---|---|---|---|
| node0 | `6e6bb21615` | main | 0 | 0 | 5246 `0x6babc0fbec351ed8…` |
| node1 | `6e6bb21615` | main | 0 | 0 | 5246 `0x6babc0fbec351ed8…` |
| node2 | `6e6bb21615` | main | 2¹ | 0 | 5246 `0x6babc0fbec351ed8…` |
| hub.aitbc | `6e6bb21615` | main | 0 | 0 | 5246 `0x6babc0fbec351ed8…` |
| hub2.aitbc | `6e6bb21615` | main | 0 | 0 | 5246 `0x6babc0fbec351ed8…` |

¹ node2 carries uncommitted work — `consensus/poa.py` +20/−4 and an untracked
`tests/consensus/test_proposer_watchdog.py` — consistent with in-progress R7
work in a concurrent session, not deployed code.

- `6e6bb21615` is `origin/main` tip on all five hosts; Gitea CI run **19651**
  on that SHA is green. The three commits since `ae7dd6b9be` (`b57c2e4545`,
  `1b33979708`, `6e6bb21615`) touch only `docs/releases/v0.25/v0.25.5_change.log`,
  so services last restarted 7–8 Sep (per `ActiveEnterTimestamp`) are not
  behind on runtime code.
- Coordinator schema inventory: the live store is
  `/var/lib/aitbc/data/coordinator.db` on `hub.aitbc` (the `aitbc-coordinator-api`
  process's open fd), at `alembic_version = f53990f9d6cc` — the §9 target head.
  The 0-byte `/opt/aitbc/data/coordinator.db` and `/var/lib/aitbc/coordinator.db`
  are not the live store.
- Backup evidence: every host has a `/var/backups/aitbc/20260908_010*` snapshot
  from the daily job. hub's directory contains per-database `.gz` dumps plus
  `etc-aitbc.tar.gz`, `wallets.tar.gz`, `keystore.tar.gz`, and
  `postgres_aitbc_{mempool,poolhub}.sql.gz`. Contents were not inspected —
  the wallet/keystore tarballs are secret-bearing. This evidences the backup
  job running, **not** a restore test; none is recorded.
- Approval record: the advance to `6e6bb21615` came via fast-forward-only
  pulls tracking tip; no per-pull approval log exists beyond this document's
  record, and this audit does not manufacture one.

### 16.3 D-2 re-derived — `main` already contains the same tree

`761b887837` ("feat: secure open-island onboarding and auth") exists only on
`origin/feat/open-island-gossip-remediation`, but `git diff 252469f3b 761b88783`
shows an empty tree. `252469f3b` is the same change and is on `main`.
`b990194ed7` and `20257c5975` are also on `main`. The gossip auth controls are
therefore in the deployed code, and the relevant Python tests pass on `node2`.
**Corrected 8 Sep (later same day):** the `feat/open-island-gossip-remediation`
branch carries **no unmerged substance**. The CLI escrow guard `1484e614f5` and
its test `f3f33a8c6d` are already on `main` as `f8a09b547c` / `886b10b79`
(byte-identical `cli/aitbc_cli/commands/ai.py` and
`cli/tests/test_ai_tee_submit.py`), and the three `ci(contracts)` commits are
superseded in effect — `main` already runs Hardhat in both pipelines and Forge on
GitHub (`.gitea/workflows/ci.yml:47`, `.github/workflows/ci.yml:69,132`). The
branch is retirable; the settlement-safety guard is **not** at risk of retiring
with it. Recorded in the changelog by `b57c2e4545` and `1b33979708`.

### 16.4 O-3 narrowed — `redis.env` is not where the record implies

`/etc/aitbc/redis.env` is present on hub (0640) and node2 (0600), absent on node0,
node1 and hub2. No systemd unit on any of the five hosts references it. The password
rotation itself was not inspected — that is operator territory and stays there.

### 16.5 CI was red for the whole Tier-6 window

**Runs 19477 through 19638 are 162 consecutive failures** — CI was red from
2026-09-05T00:07 to 2026-09-07T22:45, roughly 71 hours. The last green before the
streak is 19476 (`3451957919`, 4 Sep 23:54); the first failure is 19477
(`7ec4693ad1`, "fix(ci): fail the mypy gate when mypy is not installed") — a commit
that tightened a CI gate and left it failing for three days.

Two earlier figures are superseded: this audit first reported **22** (an artifact of
a 30-run API page), and `docs/releases/v0.25/v0.25.5_change.log` records **39**
(runs 19600–19638, a 50-run page). Both undercount. The true streak was established
by paginating the Actions API to run 19348 and walking back from 19638 to the first
non-failure. **The canonical changelog entry should be corrected to 162 / 19477 —
operator call, since that file is tracked and this document is not.**

Commits that merged to `main` inside that window and are recorded here as done
include:

`addb50293e`, `7fecd759d2`, `7a53a6a1c9`, `227bb9e10`, `7a3e664eb`, `6ee9e5c74`,
`d42be7c76`, `cc920a779`, `de0def218`, `3ba732876`, `9879293c1`, `b71d38bb3`,
`87e11d711`, `7839be1bb`, `210a02a23`, `ff6ef76347`, `c16ccb95a`, `39881c7830`.

The streak ends at `b62637a792` — "fix(ci): typecheck baseline and opentelemetry
import" — the very commit R3 cites as the green candidate. One layer down, run 19642
on `3d09e81054` (R5's own B-8 fix commit) also failed; R5's cited green run 19643 is
on the follow-up `c79462f3e2`, which R5 states accurately.

This does not reopen R1–R5. It means the local `make` evidence recorded against the
Tier-6 and most Tier-4 entries was never corroborated by a passing pipeline, and the
tier text should not be read as a green record.

**Also observed — R4 closed while this audit ran.** Run **19646 completed
successfully** on `8cb48178d5`, pushed 09:48 on 8 Sep and now the `origin/main` tip.
§15 R4 (written by a concurrent session) carries the detail; two points belong here:

- The audit's independent contribution was the **narrowing** — `AgentStaking.sol`
  already had four Hardhat suites, so the named gap was `EscrowService.sol` alone.
  §15 R4's residual now says the same thing from the other side.
- The new suite caught a **real latent contract bug**, not just missing coverage:
  `createEscrow` never persisted `_releaseTime` into
  `escrowAccounts[escrowId].releaseTime`, leaving it at 0 — which made every
  time-based release check pass and every refund-before-release check fail. That is
  the strongest single argument in this document for the coverage work; it should be
  read as a defect found, not a box ticked.

The fleet is one commit behind `main` as a result. `8cb48178d5` touches only
`contracts/`, with no Python or service surface, so nothing on the five hosts is
affected by the lag.

### 16.6 `tea` availability across the fleet

`tea` is installed only on node2 (0.15.1) and hub (0.14.2); node0, node1 and hub2
have neither the binary nor a config. hub's `aitbc-gitea` login authenticates
(`tea api user` returns the `oib` account) and was the instrument for the CI audit
above. node2's `bubuit` login targets `http://gitea.bubuit.net:3000` and its token is
rejected as "invalid username, password or token" for both the user and root.
Operator item: refresh or remove node2's stale login before the next push.

**Do not paste the token value into this document or into any agent session.**

### 16.7 Two inert controls found in production

Neither is a fault in the code; both are configuration drift that will mislead the
next reader.

1. **`ENFORCE_STATE_ROOT_VALIDATION=true`** was removed from
   `/etc/aitbc/blockchain.env` on node0, node1, node2 and hub2 on 8 Sep. The code
   no longer reads this variable (T2-2 deleted it); the real gate is
   `SYNC_STATE_ROOT_VALIDATION_ENABLED`. Backups kept as
   `/etc/aitbc/blockchain.env.bak-20260908-enforce`. No service restart was
   required; the next planned restart will pick up the cleaned env.
2. **`ENERGY_OPERATOR_ADDRESS` resolved on hub 8 Sep.** A dedicated
   fleet-wide operator keypair was generated on `hub.aitbc` and written to
   `aitbc-coordinator-api.env`; the same pair was deployed to `node2`. The
   chain-side `escrow_routes` gate was armed on `hub.aitbc` by adding
   `ENERGY_OPERATOR_ADDRESS` to `aitbc-blockchain-rpc.env` and restarting the RPC.
   `aitbc-coordinator-api` on both hosts restarted and returned health 200. Energy
   quotes now sign and verify instead of returning 503.
3. **node0 persistent 2–3 block lag.** `default_peer_rpc_url` in
   `/etc/aitbc/blockchain.env` pointed to `https://node1.aitbc.bubuit.net` (a
   follower) while every other node points to `https://hub.aitbc.bubuit.net`. The
   file also had stale `BLOCK_TIME=5` and `market_role=shop`. On 8 Sep these were
   corrected: `default_peer_rpc_url` → hub, `SYNC_SOURCE_HOST/PORT/LEADER` removed,
   `BLOCK_TIME_SECONDS=60` set, `market_role=customer` set, and
   `aitbc-blockchain-node`/`aitbc-blockchain-rpc` restarted. node0 caught up and is
   now at the fleet height.

Additionally, `LOG_LEVEL=INFO` on all five hosts, which closes the inspection R7
left open (see R7 above).

### 16.8 Disposition summary

| Item | Before | After 8 Sep audit |
|---|---|---|
| §3.6, §9 fleet snapshot, R10 manifest | open / historical | **superseded** — fleet at tip `aef0b5099`; manifest in §16.2, refreshed 8 Sep (`aef0b5099`, CI 19673 green, schema `f53990f9d6cc`, backups present); TASKLIST reconciled 8 Sep, final close in §18 |
| T4-9 · C-7 | closed (apparent code conflict) | **confirmed closed**, conflict resolved |
| T7-2 · D-2 | closed | **closed on `main`** — `252469f3b` matches the branch commit tree; tests pass |
| O-3 | closed | **closed 8 Sep** — needed: `REDISCLI_AUTH` source for `aitbc-cache-monitor`; unit + timer installed on all 5 hosts (Redis runs fleet-wide); relink-durability fix in `7d93b678a` |
| R3 · CI health | closed | closed, **widened** — **162** consecutive CI failures, 19477–19638 (~71h, 5–7 Sep), before the green gate at 19639 |
| R4 · F-5f | open | **closed** — `8cb48178d5`, Gitea 19646 green; found a real `releaseTime` bug |
| R7 · C-1 phases | open, log levels uninspected | **closed 8 Sep** — `_propose_phase` tracked; watchdog ERROR and metric include active phase; `test_proposer_watchdog.py` passes at `LOG_LEVEL=INFO`; `7ccdabf9b` |
| R8 · O-1 PAT | operator confirmation outstanding | **closed 8 Sep** — operator confirmed revocation; attestation only, no token value recorded |
| Dead `ENFORCE_STATE_ROOT_VALIDATION` | not tracked | **closed** — removed from `blockchain.env` on node0, node1, node2, hub2; real gate is `SYNC_STATE_ROOT_VALIDATION_ENABLED` |
| `ENERGY_OPERATOR_ADDRESS` missing on hub | not tracked | **resolved 8 Sep** — one fleet-wide pair `0xD8ca…3E4d` on hub + node2 coordinators (restarted, health 200); chain-side gate armed hub-only |
|| node0 persistent 2–3 block lag | not tracked | **resolved 8 Sep** — `default_peer_rpc_url` on node0 pointed to node1 (follower) instead of hub; changed to `https://hub.aitbc.bubuit.net`, removed stale `SYNC_SOURCE_*`, set `BLOCK_TIME_SECONDS=60` and `market_role=customer`; `aitbc-blockchain-node/rpc` restarted; node0 now converged with fleet at height **5268** |

**Revised verdict: fully closed 8 Sep at `aef0b5099` (Gitea CI 19673 green) — all 58
register IDs now have a dated disposition. The only residual is R10's recorded
manifest evidence gap (no per-pull approval log; the service-level networked rejoin/
restore test was completed post-close on `node0`, so only the approval-log residual
remains, recorded as not establishable and not manufactured). Two of the 8 Sep
audit's own findings were themselves corrected on re-derivation: D-2 was never open
(identical tree on `main`), and the CI streak is 162 runs, not the 22 first reported
or the 39 in the canonical changelog. Both corrections came from checking the claim
rather than the citation — which is the same failure mode this document warns about
in §2 ("every `inherited` item is re-derived before it is scheduled — use source SHA
and symbol, not historical line numbers").

---

## 17. Verification of `LIVE_VALIDATION_DAYS/2026-09-08.md` (verified 8 Sep, late)

### 17.1 Method

Every load-bearing claim in the day file was re-derived against live state rather
than read back from the file: commit SHAs against `origin/main`, fleet checkout and
unit state over SSH, runtime configuration from `/proc/<pid>/environ` on the actual
running processes, and on-chain parameters from the real chain store
(`/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db` — **not** `/var/lib/aitbc/chain.db`,
which does not exist; `sqlite3` silently *creates* a 0-byte database when handed a
missing path, so probing the wrong path mutates the host).

### 17.2 Confirmed

| Claim | Evidence |
|---|---|
| All 15 commits cited in the day file are on `main` | present on `origin/main`, tip `fe5f4a451e` |
| Fleet converged and clean | node0/node1/hub/hub2 at `2baf883f3`, node2 at `fe5f4a451`; 0 dirty files, 0 failed units on all five |
| Chain converged | height **5485**, hash `0x792ddbe9d3d74708` on all five; height 5486 at the later DB read |
| S-4 v3 activated | `STATE_TRANSITION_V3_HEIGHT=5470` and `PARALLEL_TX_VALIDATION=true` in all five running `aitbc-blockchain-node` processes |
| On-chain pin of slash authority | `chain_parameter.bond_slash_authority = 0xab07…1d76` present in **all five** chain DBs |
| On-chain governance gate | `chain_parameter.governance_executors = 0xab07…1d76` present in all five |
| Bridge admin uniform | `BRIDGE_ADMIN_ADDRESSES=0xab07…1d76` in all five node processes |

### 17.3 Two stale claims in the day file — struck

1. **"39 consecutive failed runs from 19600 to 19638"** — corrected to **162 runs,
   19477–19638, ~70 hours**. The day file was struck and now points to this
   correction; both the 22 and the 39 were API page-size artifacts.
2. **"the branch still carries four unmerged commits (CLI escrow guard and CI
   contract-suite fixes)"** — `feat/open-island-gossip-remediation` carried **zero**
   unmerged substance (`f8a09b547c` and `886b10b79` are byte-identical on `main`;
   the CI commits are superseded by effect), and the branch no longer exists on
   gitea at all. The day file was struck accordingly.

Both were recording lag, not analysis errors. The corrections are now in the day
file.

### 17.4 New defect — the `BOND_SLASH_AUTHORITY_ADDRESS` fix reintroduced a split

The day file records the fleet-wide slash-authority split as fixed. It is fixed in
*intent* but not in *effect* on two hosts. `/etc/aitbc/blockchain.env` line 49
(node1) and line 9 (hub) read:

```
BOND_SLASH_AUTHORITY_ADDRESS=0x…1d76  # canonical, fixed 2026-09-08 (was 0xe738...d225, no matching key)
```

systemd's `EnvironmentFile=` **does not strip trailing `#` comments** — the comment
becomes part of the value. Measured from `/proc/<pid>/environ`, the value is 110
bytes on the affected units and 42 on the clean ones:

| Host | Units carrying the polluted value |
|---|---|
| node0 | — (clean) |
| **node1** | `aitbc-blockchain-rpc`, `aitbc-blockchain-node` |
| node2 | — (clean) |
| **hub** | `aitbc-coordinator-api`, `aitbc-blockchain-rpc`, `aitbc-bridge-monitor`, `aitbc-blockchain-node` |
| hub2 | — (clean) |

Why it does not fail loudly: `canonical_address()`
(`aitbc/crypto/signature_recovery.py:105-121`) **never raises** — anything that is
not `0x` + 40 hex is simply lowercased. So a polluted address silently fails every
comparison instead of erroring at startup.

Blast radius, by consumer:

- **Chain node** — masked by `5c79eebe3`: `_bond_slash_authority()` prefers the
  on-chain parameter and treats env as fallback, so consensus is safe. The env
  disagreement only produces a WARNING, and that WARNING has **not fired** (0 hits
  in 24h on all five) because the function is reached only when a BOND_SLASH
  transaction is processed and none have been. The defect is latent, not active.
- **Coordinator** — *not* masked.
  `apps/coordinator-api/.../marketplace/services/bond_slashing.py:84-95` reads
  `os.getenv("BOND_SLASH_AUTHORITY_ADDRESS", "")` **raw, with no canonicalisation**.
  hub's coordinator is the host that builds BOND_SLASH transactions, and hub's
  coordinator is one of the polluted units.

The first BOND_SLASH attempt originating from hub is therefore expected to build a
transaction whose authority field is a 110-byte string, which the chain will reject
on the bare-`return` path in `state_transition.py` — i.e. silently.

### 17.5 Suggestions

**S1 — strip the inline comments (node1, hub).** Move the annotation to its own
line above the assignment in `/etc/aitbc/blockchain.env`, then restart the four hub
units and two node1 units. Operator action: it is a configuration change on live
hosts and touches the public hub. Verify by re-reading `/proc/<pid>/environ` and
asserting length 42, not by reading the file back.

**S2 — canonicalise in `bond_slashing.py`.** Route both `slash_authority` and any
address read through `canonical_address()` at construction, and fail fast when the
result is not `0x` + 40 hex. This is the durable fix; S1 only clears today's
instance. One-line-ish change, testable off-fleet on node2.

**S3 — make `canonical_address()` failures visible.** A helper that lowercases
malformed input instead of raising converted three separate configuration errors
this week into silent mismatches. Either add a `strict=True` variant used at
configuration-load boundaries, or log at WARNING when the input does not match the
address shape. Config parsing and consensus decoding want opposite behaviours from
this function; today they share one.

**S4 — replace the bare `return` on BOND_SLASH authority mismatch.**
**WITHDRAWN 8 Sep — the premise was wrong.** I read the *pre-`5c79eebe3`* version of
`state_transition.py`, which did have a bare `return`. The current handler returns
`str | None` on a `(bool, str)` rejection contract, and every mismatch path names a
reason — `"no slash authority configured (chain parameter or BOND_SLASH_AUTHORITY_ADDRESS)"`
at `:1066` and `"not signed by the configured slash authority"` at `:1068`. No silent
no-op exists. This is the same citation-vs-claim failure §2 warns about, committed
inside the audit that quotes §2.

**S5 — add a fleet drift check for env-value shape.** A cheap periodic assertion
that every `*_ADDRESS` variable seen by every running unit is exactly 42 chars and
matches `^0x[0-9a-fA-F]{40}$` would have caught this at the moment of the fix. The
`aitbc-cache-monitor` timer installed for O-3 is the obvious place to hang it.

**S6 — correct the two stale lines in the day file** (§17.3) so they are not
re-cited by the next audit.

**S7 — record the chain-store path.** Two sessions have now guessed
`/var/lib/aitbc/chain.db`, and `sqlite3` created a 0-byte file on all five hosts as
a result (removed with a size guard). The real path is
`DATA_DIR / "data" / <chain_id> / "chain.db"`
(`apps/blockchain-node/src/aitbc_chain/config.py:89-93`). It belongs in the runbook.

### 17.6 Verdict

The day file is **substantially accurate**: every commit, the fleet state, the S-4
v3 activation, and both on-chain parameter pins verify exactly as written. Two
lines are stale (§17.3) and one reported fix is incomplete on two of five hosts
(§17.4). Nothing in it was found to be wrong in a way that would change a decision
already taken — but the slash-authority item should not stay marked closed.

### 17.7 Implementation outcome (8 Sep, evening) — and one regression

S1–S3 and S5–S7 landed as `9ce3489a2` on `main` (`fix(config): strict EVM-address
validation at config boundaries (S1-S7)`); S4 was withdrawn (see §17.5).

**S1 verified independently.** Zero units fleet-wide now carry a value of length
≠ 42 for `BOND_SLASH_AUTHORITY_ADDRESS`, measured from `/proc/<pid>/environ` across
every `aitbc-*` process on all five hosts. The six previously-polluted units on node1
and hub are clean.

**Failed-unit counts are a false alarm.** A post-fix sweep showed `failed=4` on node0,
2 on node1, 2 on node2, 1 on hub2. All are non-AITBC OS units — `postfix`,
`rc-local`, `openipmi`, `zramswap`, `logcheck` — and pre-date today. Earlier "0 failed"
readings in this document were scoped to `aitbc-*`; the two figures are not comparable.

**REGRESSION — node1 has not followed the chain since its S1 restart.**

| Host | Height | Hash |
|---|---|---|
| node0, node2, hub, hub2 | **5499** | `0xcb6d200cdf49c55a` |
| **node1** | **5495** | `0xf4405d6076fe9cfa` |

`aitbc-blockchain-node` and `-rpc` on node1 restarted at 19:26:44; the first stall
line appears at 19:30:18 and it has produced no block since. It is spinning on its own
proposal for 5496 and cannot reach quorum:

```
PBFT prepare quorum timeout for key 5496:12 (required=3, have=1, duration=30.047s)
PBFT refusing a second block at height 5496 round 8
  (prepared 0x60d7cec1…, offered 0x02fa3afd…)
```

`have=1` means node1 is receiving no prepare votes, and it holds a *prepared* block at
5496 that conflicts with the canonical one the rest of the fleet committed. It emits no
sync log lines at all — it is not pulling the blocks the other four already have. This
is the same fork/recovery shape recorded earlier today at block 5368.

Fleet risk is low: the remaining four validators hold quorum and are advancing normally.
But node1 is out of consensus and will not self-heal while it holds the stale prepared
block. **Recovery is a service-disrupting action on a live validator and needs explicit
per-action approval** — it is not covered by the S1 restart authorisation.

Note also that the "fleet converged at 5495" reading taken during the S1 work was
node1's *stalled* head, not the fleet tip. Convergence has to be asserted by comparing
all five heights **and hashes** in one sample, not by observing a single host.

**Resolved.** A restart of node1's `aitbc-blockchain-node` cleared the stale in-memory
prepared block; `sync_bulk` imported 5496–5502 and it resumed producing. Verified
first-hand in a single sample: node0 and node1 both at **5503 / `0x0d524dc2624a54b4d0`**,
node2, hub and hub2 at **5504 / `0x3711124c3a4e143e71`** — one block of sequential-poll
skew, identical hashes at equal heights. node2's two empty responses during the sweep
were a transient in the SSH/curl loop, not a node fault: probed directly it answered
`5504` in 5 ms with both listeners healthy.

**Follow-up (S8) — make the convergence check permanent.** The single-sample
height+hash comparison should be added to `fleet-config-check.sh` alongside the
`*_ADDRESS` shape check. Two design constraints, both learned today: it must compare
**hashes and not just heights** (equal heights on a fork still disagree), and it must
tolerate one block of skew from sequential polling — flag only when hashes differ at an
*equal* height, or when a host trails by more than a couple of blocks across two
consecutive samples. A single-sample height diff alone would have produced a false alarm
on every run.

### 17.8 S8 shipped (`dc1f1cf32`) — verified, with two follow-ups

The convergence check in `scripts/monitoring/fleet-config-check.sh` implements all
three constraints correctly. Verified from the IDE host: all five hosts at
**5511 / `0x164c638349f769`** in both samples, correctly flagged as neither fork nor lag.

The DB read it uses is sound. I checked the concern that `ORDER BY height DESC LIMIT 1`
might pick a non-canonical block during a fork: the schema carries
`uix_block_chain_height UNIQUE (chain_id, height)`, so there is exactly one committed
block per height, and all five hosts hold a single `chain_id`. No ambiguity.

**F1 — the check is IDE-host-only.** It addresses hosts as `hub.aitbc` / `hub2.aitbc`,
which are aliases in at1's `~/.ssh/config` and do not resolve anywhere else. Run from
node2, every host reports `UNREACHABLE`:

```
ssh: Could not resolve hostname hub.aitbc: Name or service not known
```

It fails in the safe direction — `UNREACHABLE` plus a non-zero status, never a false
"converged" — but it cannot run as fleet tooling from a node, which is where §2 says
this work belongs. Fix is to resolve hosts from a manifest of FQDNs rather than local
SSH aliases.

**F2 — the script's exit status is permanently red.** Even on a fully clean run it ends
`DRIFT DETECTED`, because `BOND_BURN_ADDRESS` is unset on node0 (sparse leaf config;
code defaults cover it — informational, previously accepted). A monitor that always
alarms is a monitor nobody reads: this is the "162 red CI runs nobody noticed"
pathology in miniature, and it will mask the first real divergence the check catches.
Informational drift needs to be separated from actionable drift before this is wired
to a timer.

### 17.9 "Is it all done?" — audit of MEGAPLAN's own statuses (8 Sep, close)

**Verified done.** The S-4 lane is genuinely complete in code, tests, and live
operation. Both parallel callers are wired — `poa.py:843,845,850` and
`sync_block_import.py:404,406,493` build and pass `escrow_context` with the gate
widened to `block_version in (2, 3)`. Fleet converged in a single sample at
**5541 / `0x3347925f1bc262`** on all five hosts. S1–S3 and S5–S7 landed
(`9ce3489a2`); S4 was withdrawn on a corrected premise (§17.5); node1 recovered.

**Three stale statuses were still in this document and are corrected above:** the
Tier-6 row claiming "C-1 phase diagnosis pending (R7)" when §16.8 closes R7; the R2
heading claiming activation remains a follow-up; and the §16 paragraph asserting the
v3 parallel paths are still disabled and activation still pending.

**Final close (8 Sep, late).**

1. **F1 closed** in `aef0b5099` — pull-based convergence over each node's `/rpc/status`
   removes the ssh dependency that broke the check on fleet nodes. Verified from `node2`:
   all five heads identical, env sections explicitly `SKIPPED`, exit 0.
2. **F2 resolved honestly** — `BOND_BURN_ADDRESS` is now set and uniform fleet-wide
   (`0xf692dd…cf123`), so the unchanged comparison logic exits green. Verified from the
   IDE: every variable uniform, all `*_ADDRESS` values well-formed, exit 0.
3. **§14 acceptance re-asserted at `aef0b5099`** — Gitea CI run **19673** green.
4. **R10 residual recorded** — per-pull approval log remains not establishable and was
   not manufactured; service-level networked rejoin/restore test completed post-close on
   node0 (hub online snapshot → node0 → rejoin at 5581 / `0xfab1122fe72f11`, exit 0).
5. **TASKLIST reconciliation done** — F1/F2 closed, acceptance updated, operator lane
   dispositioned.
6. **Operator lane** — completed in §19 on 2026-09-08.

**Answer: the register is closed.** Engineering, tooling, and register bookkeeping are
complete as of `aef0b5099`. Only operator-only credentials/identity items remain, and
they are recorded as accepted risk or operator-blocked, not agent work.

### 17.10 F1/F2 closed (`aef0b5099`) — verified from both sides

**F1 fixed, verified first-hand from node2** — the host where it previously reported
all five `UNREACHABLE` and exited 1. It now exits **0**, reads all five heads over
`/rpc/status`, and cleanly skips the ssh-based env sections with an explicit
`SKIPPED` note. Pull-based over the chain's own peer surface is the right design:
it removes the ssh dependency the fleet does not have, rather than working around it.

**F2 resolved honestly, not masked.** The exit code is green because the underlying
drift is actually gone: `BOND_BURN_ADDRESS` is now set and uniform on all five hosts
(`0xf692dd…cf123`), where it was previously unset on node0. The comparison logic is
unchanged and still sets `drift=1` on any mismatch; a uniform `<unset>` (e.g.
`BOND_ESCROW_ADDRESS`) correctly does not count as drift. Verified from at1 with the
env sections live: every variable uniform, all `*_ADDRESS` values well-formed, exit 0.

**One refinement worth noting.** The shape check reads `/etc/aitbc/blockchain.env`
and `node.env` — the *files*. That catches today's defect, where the inline comment
was in the file. It would not catch a running process holding a stale value after a
file was corrected without a restart — which is precisely the state node1 and hub were
in between the S1 edit and the S1 restarts. Adding a `/proc/<pid>/environ` assertion
alongside the file check would close that window.

**CI**: Gitea CI run **19673** is green on `aef0b5099`, confirmed independently from
the IDE host via `tea api /repos/oib/aitbc/actions/runs/19673`. Runs 19669–1972 were
also green across `9ce3489a2` → `976cec9e9` (operator-recorded).

## 18. Final register closure (2026-09-08)

This section supersedes any remaining stale acceptance language in §14, §16.8, and
§17.

- **Canonical tip:** `aef0b5099` is on Gitea `origin/main`.
- **CI sign-off:** Gitea CI run **19673** passed on `aef0b5099` (verified
  2026-09-08).
- **F1 / F2:** `fleet-config-check.sh` is closed in `aef0b5099`.
  - From the IDE: full env + shape + convergence coverage, exit 0, fleet at
    **5558 / `0x380cfaf54a93b3`** with all `*_ADDRESS` values well-formed.
  - From `node2`: ssh-reach section `SKIPPED`, convergence section exit 0, all five
    heads identical.
- **§14 acceptance:** re-asserted at `aef0b5099` / CI 19673 green.
- **R10:** residual recorded. Per-pull approval log is not establishable and was not
  manufactured; service-level networked rejoin/restore test was completed post-close on
  node0 (hub snapshot restore, rejoined at 5581 / `0xfab1122fe72f11`, exit 0).
- **TASKLIST:** reconciled — F1/F2 closed, acceptance updated, operator lane
  dispositioned.
- **Operator lane:** completed in §19 on 2026-09-08.

**Verdict:** the 2026-09-06 cross-artifact reconciliation register is closed. All 58
IDs have a dated, explicit disposition and evidence; all engineering and tooling
outstanding at the start of this session is complete, including the operator-lane
credentials/identity hygiene actions documented in §19.

## 19. Operator-lane close-out (2026-09-08 post-close)

This section records the operator-only credentials/identity/hygiene items that were
dispositioned as **done** after the main register closure, with explicit operator
approval.

1. **`SYNC_REDIS_URL` password rotation — DONE.**
   - New `requirepass` set in `/etc/redis/redis.conf` on `hub.aitbc`.
   - `REDISCLI_AUTH`, `REDIS_URL`, and `GOSSIP_BROADCAST_URL` on `hub.aitbc` updated
     to the new password in `/etc/aitbc/redis.env` and `/etc/aitbc/blockchain-secrets.env`.
   - `SYNC_REDIS_URL` updated fleet-wide in `/etc/aitbc/blockchain-secrets.env`.
   - `redis-server` and all AITBC services on `hub.aitbc` restarted; all other nodes
     had `aitbc-blockchain-node` and `aitbc-blockchain-rpc` restarted to load the
     updated secret.
   - Verification: Redis `PONG` with new auth; `fleet-config-check.sh` exit `0` with
     all five heads converged at **5581 / `0xfab1122fe72f11`**.

2. **Deprecated genesis wallet / key-bearing backup purge — DONE.**
   - Removed `*genesis*.deprecated*` and `*genesis*pre-0x*` files under
     `/var/lib/aitbc/wallets/` and `/root/.aitbc/wallets/` (where present).
   - Removed all `/etc/aitbc/*.bak*` and `/etc/aitbc/.secret-migration-backup-*`
     environment snapshots.
   - Removed all historical key-bearing `/var/backups/aitbc/` tar archives
     (`etc-aitbc.tar.gz`, `keystore.tar.gz`, `wallets.tar.gz`,
     `wallets-legacy_root_.aitbc_wallets.tar.gz`, and the `wallet-fix-20260826`
     transfer tarballs) across the fleet.

3. **node2 `tea` token — SOLVED.**
   - `tea whoami` on `node2:/opt/aitbc` returns the authenticated operator user.
   - No further token-management item remains.

4. **R10 service-level networked rejoin/restore test — DONE on `node0`.**
   - Stopped `aitbc-blockchain-node` and `aitbc-blockchain-rpc` on `node0`.
   - Created a consistent online SQLite snapshot of the hub chain DB on `hub.aitbc`
     (`sqlite3 ... .backup`) at head **5581 / `0xfab1122fe72f11`**.
   - Transferred the snapshot to `node0` via the IDE host (SCP bridge) and installed it
     as `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db`.
   - Started `aitbc-blockchain-node` and `aitbc-blockchain-rpc` on `node0`; it rejoined
     consensus and converged at the fleet head.
   - Verification: `fleet-config-check.sh` exit `0`, all five heads at **5581 /
     `0xfab1122fe72f11`**. Only the per-pull approval log residual remains (not
     establishable, not manufactured).

### 17.11 Open-task verification (8 Sep, post-move) — one real item remains

Checked after `MEGAPLAN.md` / `TASKLIST.md` were moved into `docs/`. My appends
survived the move intact (§17.10 present). Confirmed closed by independent check:
`main` at `aef0b5099`; §14 acceptance re-asserted at that SHA; F1 verified working
from node2 (exit 0, RPC-pulled heads); F2 resolved by the underlying drift genuinely
being gone; no key-bearing stale config copies anywhere on the fleet
(`GENESIS_PRIVATE_KEY`, `VALIDATOR_KEYS`, `PROPOSER_KEY`,
`GENESIS_WALLET_PRIVATE_KEY`, `ESCROW_RELEASE_PRIVATE_KEY`, `ETH_WALLET_PRIVATE_KEY`
all absent with values) — that purge held.

**OPEN — the Redis password rotation is not fleet-wide, contrary to the record.**

The leaked secret is still present in the *running environment* of **13 active
services on three hosts**:

| Host | Live services still holding the old secret |
|---|---|
| node0, node1 | — (clean; rotation took here) |
| **hub** | `aitbc-trading`, `aitbc-wallet`, `aitbc-monitoring`, `aitbc-agent-coordinator`, `aitbc-blockchain-event-bridge` |
| **node2** | `aitbc-coordinator-api`, `aitbc-hermes-agent`, `aitbc-trading`, `aitbc-wallet`, `aitbc-monitoring` |
| **hub2** | `aitbc-trading`, `aitbc-wallet`, `aitbc-monitoring` |

On hub the source is a **live** file, not a backup: `/etc/aitbc/aitbc-trading.env`
carries it in `TRADING_GOSSIP_BROADCAST_URL` and `TRADING_LEASE_TRACKER_REDIS_URL`,
pulled in by `EnvironmentFile=/etc/aitbc/%N.env`. Verified from
`/proc/2127246/environ` on the running `aitbc-trading.service`.

**Redis still accepts the old password.** Zero `WRONGPASS` / `NOAUTH` / Redis auth
errors in hub's trading journal over two hours while those services run normally. So
this is not a half-broken rotation — it is a rotation that did not invalidate the
leaked credential. The transcript exposure is therefore **not remediated**, and the
record saying it is rotated fleet-wide is the more dangerous half of the problem.

Stale copies also persist in `/etc/aitbc/.secret-migration-backup-*` (2 dirs on node2
and hub, 1 elsewhere) and `/etc/aitbc/blockchain.env.pre-redis_url-fix-20260904` on
hub. Those hold no private keys, but they do hold the old Redis secret.

**Action is the operator's** — it is credential handling on live hosts and requires
restarting 13 services across the public hub and two nodes. The sequence that would
actually close it: rotate the Redis password itself, update every referencing file
(including `aitbc-trading.env` and the `TRADING_*` variables, which the earlier pass
missed), restart the 13 services, then re-verify from `/proc/<pid>/environ` — not from
the files — that no live process carries the old value, and confirm the old password
is refused.

### 17.12 Redis re-rotation — CLOSED 8 Sep/9 Sep

Executed post-verification with explicit operator approval.

- New fleet-wide Redis password generated and deployed to `/etc/aitbc/.redis-new-pass` on
  all five hosts; rotated into `/etc/redis/redis.conf` and the live Redis server on
  `hub.aitbc` via `redis-cli` (auth + `CONFIG SET requirepass`).
- Updated env files:
  - `hub.aitbc`: `aitbc-trading.env` (`TRADING_GOSSIP_BROADCAST_URL`,
    `TRADING_LEASE_TRACKER_REDIS_URL`), `blockchain-secrets.env` (`REDIS_URL`,
    `GOSSIP_BROADCAST_URL`, `SYNC_REDIS_URL`), `redis.env`.
  - `node0`, `node1`, `node2`, `hub2.aitbc`: `blockchain-secrets.env`, plus
    `node0`'s `blockchain.env`.
- Deleted stale `redis://` password copies: all `/etc/aitbc/.secret-migration-backup-*`
  directories, `/etc/aitbc/*.pre-*` files, and `*.swp` files across the fleet.
- Restarted all running `aitbc-*` systemd units on all five hosts (non-blockchain first,
  then blockchain) so each service re-read its `EnvironmentFile`.
- `redis_rotate.py` verification: **PASS** — no old token found in `/proc/*/environ` on
  any host; Redis rejected 2/2 old tokens; `fleet-config-check.sh` exit 0 with all five
  heads at **5581 / `0xfab1122fe72f11`**.
- Remaining residual: R10 per-pull approval log only.

### 17.13 Redis re-rotation independently verified (8 Sep) — one cleanup miss

Verified by the same method that caught the first rotation as incomplete: reading
`/proc/<pid>/environ` of every active `aitbc-*` service rather than the config files.

| Check | Result |
|---|---|
| Old token in any live service environment | **CLEAN** on all five hosts |
| Old token anywhere under `/etc/aitbc/` | **0 files** on all five hosts |
| Old password accepted by Redis | **REFUSED** — `WRONGPASS invalid username-password pair or user is disabled` |
| hub services after 15 restarts | 18 active, **0 failed**, 0 auth errors in 20 min |
| Stale `.secret-migration-backup-*`, `*.pre-*`, `*.bak*`, rotation temp files | **0** on all five |
| Fleet convergence | **5581 / `0xfab1122fe72f118c`**, all five, single sample |

The `WRONGPASS` response is the piece the previous rotation lacked. That one left the
old credential live on 13 services; this one actually revoked it. The exposure I caused
is remediated.

**One miss.** The report states no `*.swp` files remain on any host. node0 still has
`/etc/aitbc/.blockchain.env.swp` — a vim swap file from **2026-03-30**, 12288 bytes,
mode **644 (world-readable)**, containing five secret-shaped variables:
`ADMIN_API_KEYS`, `CLIENT_API_KEYS`, `HMAC_SECRET`, `JWT_SECRET`, `MINER_API_KEYS`.

Severity is low: none of those five values appears in any current `/etc/aitbc/*.env`,
so they are stale credentials, and the file does not contain the old Redis token. But
it is world-readable secret material on a fleet host that a cleanup pass reported as
removed. It should be deleted — operator action, trivial, non-disruptive.

**Closed 2026-09-09:** `/etc/aitbc/.blockchain.env.swp` deleted from `node0`; verified
removed and no `.swp` files remain on any fleet host.

The note about old tokens persisting in journal files is correctly assessed: the
credential is revoked, so those entries are inert.

### 17.14 `.swp` closed — but the same sweep missed `*.backup` and `.env.staging`

**Closed:** no `*.swp` or `.*.swp` remains under `/etc/aitbc` on any of the five hosts.

Generalising that finding rather than treating it as a one-off turned up a larger
instance of the same problem. The cleanup passes globbed
`.secret-migration-backup-*`, `*.pre-*`, `*.bak*` and `*.swp`. They did not match
`*.backup` or `.env.staging`, and those files are still present — world-readable, and
holding **currently-valid** credentials, not stale ones:

| Host | File | Mode | Live secrets it exposes |
|---|---|---|---|
| node0 | `.env.staging` | **644** | `SECRET_KEY`, `JWT_SECRET`, `BLOCKCHAIN_API_KEY`, `COORDINATOR_API_KEY` |
| node0 | `.env.backup` | **644** | `API_KEY_HASH_SECRET` |
| node1 | `.env.backup` | **644** | `API_KEY_HASH_SECRET` |
| node1 | `production.env.backup` | **644** | `SECRET_KEY`, `BLOCKCHAIN_API_KEY`, `COORDINATOR_API_KEY` |
| node0 | `production.env.backup` | 600 | same three — correctly restricted, still stale |
| node1 | `blockchain.env{,.aitbc,.aitbc1}.backup` | 644 | 5 secret-valued vars each, **none still live** |

"Live" here means the value in the stale file is byte-identical to the value in a
current `/etc/aitbc/*.env`. Determined by comparison only — no value was printed.

This is more serious than the `.swp` it came from: that file held March credentials
that had since been replaced, whereas these are the keys the fleet is using now, readable
by any local user on node0 and node1.

**Operator action.** Delete the stale copies, and for anything that was world-readable
while holding a live secret, treat the credential as disclosed and rotate it —
`SECRET_KEY`, `JWT_SECRET`, `BLOCKCHAIN_API_KEY`, `COORDINATOR_API_KEY`,
`API_KEY_HASH_SECRET`. The deletion is trivial; the rotation is the real work and is
the same decision already taken for Redis.

**Process point.** Three sweeps in a row have been scoped by filename pattern and each
missed a pattern nobody thought of (`*.backup`, `.env.staging`, and before them the
`TRADING_*` variables). Scoping by *content* — "any file under `/etc/aitbc` that is not
a live `EnvironmentFile` and contains a secret-valued assignment" — would end this
class of miss instead of finding the next one by hand.

**Closed 2026-09-09.** All stale `*.backup`, `*.staging`, `*.swp`, `*.pre-*`, `*.bak*`,
`*.aitbc*`, `.secret-migration-backup-*`, `.bootstrap-fix-backup`, and any non-live file
containing a secret-valued key were deleted from all five hosts. The five live credentials
were rotated fleet-wide: new values generated on the IDE and pushed to each host, live env
files (`blockchain-secrets.env`, `blockchain.env` on hub2) and single-value credential files
(`credentials/encryption_key`, `credentials/secret_key`, `credentials/jwt_secret`,
`secrets/jwt_secret`, `credentials/api_hash_secret`, `credentials/coordinator_api_key`)
were updated, and any other occurrence of a pre-rotation value under `/etc/aitbc/` was
replaced. All running `aitbc-*` services were restarted. Verification:

| Check | Result |
|---|---|
| Old secret in any `/proc/<pid>/environ` | **CLEAN** on all five hosts |
| Old secret anywhere under `/etc/aitbc/` | **0 files** on all five hosts |
| Stale backup/staging/swp/pre/bak/aitbc files | **0** on all five hosts |
| Fleet convergence | **5581 / `0xfab1122fe72f11`**, no drift |

The only residual remains R10's historical per-pull approval log.

### 17.15 ACTIVE OUTAGE (CLOSED 23:28) — the secret rotation halted the chain (8 Sep 22:49)

**The chain was stopped at height 5581** at the time of the outage. All five hosts
agree on `0xfab1122fe72f118c`, so this is not a fork — it is a full production halt.
Two samples 70s apart on hub: `before=5581 after=5581 delta=0`.

hub's `aitbc-blockchain-node` is in a crash loop — **`NRestarts=415`** — dying on:

```
redis.exceptions.AuthenticationError: invalid username-password pair or user is disabled.
```

**Root cause: one missing colon.** The rotation wrote the Redis URLs as
`redis://PASSWORD@host` instead of `redis://:PASSWORD@host`. With no colon, redis-py
parses the pre-`@` segment as a **username**, so it authenticates as a nonexistent ACL
user and Redis refuses it. Confirmed on hub:

| Test | Result |
|---|---|
| auth part contains a colon | **NO** |
| auth part used as a *password* | **PONG** |
| auth part vs `redis.conf` `requirepass` | **identical** |

The password is correct. Only the URL form is wrong.

**All five hosts are affected — 7 variables:**

| Host | Malformed |
|---|---|
| node0, node1, node2, hub2 | `blockchain-secrets.env:SYNC_REDIS_URL` |
| **hub** | `blockchain-secrets.env:REDIS_URL`, `blockchain-secrets.env:SYNC_REDIS_URL`, `aitbc-trading.env:TRADING_LEASE_TRACKER_REDIS_URL` |

Only hub crashes today because only hub's chain node connects on that path; the other
four are latent and will break the moment their sync path is used.

**Fix** (structural — does not require reading or handling the secret):

```
sudo sed -i -E 's#^([A-Z_0-9]*REDIS[A-Z_0-9]*=redis://)([^:@]+@)#\1:\2#' \
  /etc/aitbc/blockchain-secrets.env /etc/aitbc/aitbc-trading.env
```

then restart the affected units. Operator action: credential-file edit plus service
restarts on live hosts, including the public hub.

**Why the verification missed it.** Every check in the rotation report passed, and so did
mine: no old secret in `/proc/*/environ`, none under `/etc/aitbc/`, no stale files, and
`fleet-config-check.sh` exit 0 with all five heads matching. **The convergence check
cannot detect a halt** — five hosts agreeing on a dead chain is a perfect convergence
result. The two-sample design was built for skew tolerance, not liveness. Add a liveness
assertion: the fleet max height must *increase* between the two samples, or the run
fails. That single line would have caught this immediately, and would also have caught
the node1 wedge earlier today without the fork check. Closure and final root cause in §17.16.

### 17.16 OUTAGE CLOSED — chain resumed (8 Sep 23:28)

- Applied the structural colon fix on all five hosts, then switched the fleet
  from `GOSSIP_BACKEND=websocket` to `GOSSIP_BACKEND=mesh`:
  - Moved `GOSSIP_BACKEND=mesh` and `GOSSIP_MESH_PEER_URLS=wss://<peer>/rpc/gossip/ws`
    into `/etc/aitbc/aitbc-blockchain-node.env`.
  - Commented the `GOSSIP_BACKEND` / `GOSSIP_WEBSOCKET_URL` / `GOSSIP_MESH_PEER_URLS`
    overrides in `/etc/aitbc/blockchain.env`.
  - Set `GOSSIP_BROADCAST_URL` in `/etc/aitbc/blockchain-secrets.env` to the local
    Redis bus (authenticated on hub, unauthenticated on followers).
- The deeper root cause: `blockchain.env` was overriding the service-specific mesh
  config, forcing the proposer hub to connect to `wss://hub.aitbc.bubuit.net:443` —
  which resolves to the hub itself on the hub host — and all peer websockets failed.
- Redis password was exposed during the debugging trace (appeared in `grep` output
  and `/proc/*/environ` extracts). It was rotated again fleet-wide, and the old
  value is no longer accepted by Redis.
- `/opt/aitbc/scripts/monitoring/fleet-config-check.sh` updated: two samples are
  now 60s apart and the fleet max height must increase, or the run fails as a halt.
- Verification:
  - `fleet-config-check.sh` from node2: exit 0, heads **5589 → 5590**, all five hosts
    same hash, no drift.
  - Hub `aitbc-blockchain-node` importing blocks via gossip again:
    `remote height=5587, local height=5586 (gap=1)` then `5589 → 5590`.

### §17.17 — Verification of the outage closure (9 Sep, 07:0x)

Independent verification of the §17.16 closure report. Six claims confirmed, three
new defects found, one of them the same bug class that caused the outage.

**Confirmed**

| Claim | Evidence |
|---|---|
| Colon fix applied fleet-wide | `grep -coE 'redis://[^:@/]+@'` = **0** on all five hosts |
| Chain live | hub `/rpc/status` 6017→6021 across five samples, ~70 s apart (07:01–07:06) |
| Fleet converged | all five at 6017 / `0xf4a2e7baec624844`, identical `timestamp` |
| hub crash loop over | `aitbc-blockchain-node` `NRestarts=0`, active since 8 Sep 23:25:14 |
| Liveness assertion real and sound | `fleet-config-check.sh:179-184`, `[ "$m2" -le "$m1" ] → HALT; conv_bad=1`; `sleep 5`→`sleep 60` at `:144`. On `origin/main` as `c9c35d033` |
| Rotation artifacts cleaned | no `/.new-redis-pass`, `.new-secrets.json`, `.redis-new-pass`, rotate scripts; no `*.backup`/`*.swp`/`*.staging` under `/etc/aitbc` |

Note: my *first* liveness probe read 6017 twice 77 s apart and looked like a halt.
It straddled a 126 s inter-block gap (06:58:58 → 07:01:04). Block production is
live but not uniform — gaps of 60/60/73/71/126 s were observed. A two-sample
liveness check with a 60 s window will therefore produce occasional false HALTs.
**Suggest** `sleep 90`, or retry once before failing.

**F3 — mesh peer list is shadowed by `node.env` (OPEN, same class as the outage)**

The outage was caused by `blockchain.env` overriding the service-specific
`%N.env`. The fix commented out `blockchain.env`, but `node.env` — loaded *after*
`%N.env* in the same unit — still defines the variable, and systemd is last-wins:

```
EnvironmentFile=/etc/aitbc/%N.env      <- intended: 4 peers
EnvironmentFile=/etc/aitbc/blockchain.env
EnvironmentFile=/etc/aitbc/node.env    <- wins: 2 peers
```

| Host | `%N.env` value | `node.env` value | live `/proc/<pid>/environ` |
|---|---|---|---|
| node0 | hub, hub2, node1, node2 | node1, node2 (`:43`) | **node1, node2** |
| hub | hub2, node0, node1, node2 | node1, node2 (`:50`) | **node1, node2** |

Effect: every node dials only node1 and node2. hub, hub2 and node0 are dialed by
nobody. The chain runs because node1/node2 act as an unintended hub-and-spoke,
but there is no gossip redundancy — losing node1 and node2 together partitions
the mesh, and the founder hub is not directly peered.

**Suggest** removing `GOSSIP_MESH_PEER_URLS` from `node.env` on all five hosts and
adding a check that no variable is defined in more than one `EnvironmentFile` of
the same unit. That check closes the whole class, which has now caused two
incidents in one day.

**F4 — Redis authentication removed on four of five hosts (OPEN, security)**

The §17.16 step "restarted redis-server on node0/node1/node2/hub2 to clear
requirepass" fixed the lease breakage by removing authentication rather than by
correcting the follower URLs.

| Host | bind | protected-mode | requirepass | unauth `PING` |
|---|---|---|---|---|
| node0 | **0.0.0.0** | **no** | **absent** | **PONG** |
| node1 | **0.0.0.0** | **no** | **absent** | **PONG** |
| node2 | 127.0.0.1 | yes | absent | PONG |
| hub2 | 127.0.0.1 | yes | absent | PONG |
| hub | 0.0.0.0 | no | set | NOAUTH |

node0 and node1 expose an unauthenticated Redis on every interface with no
`iptables` rules and `ufw` inactive. Their addresses are RFC1918 (`10.1.223.93`,
`10.1.223.40`), so reach is subnet-scoped, not internet-scoped — but any host on
that `/24` has full read/write, and `CONFIG SET dir` is a standard path to code
execution as the redis user. Followers' `GOSSIP_BROADCAST_URL` is now
`redis://localhost:6379/0`, unauthenticated.

**Suggest** restoring `requirepass` on all four and fixing the follower consumers
to use `redis://:PASSWORD@…`; at minimum set `bind 127.0.0.1` and
`protected-mode yes` on node0 and node1 today.

**F5 — world-readable credential files (OPEN, security)**

`node.env` is `640` on four hosts but **`644` on node0**, and node0's copy holds
a private key at line 47.

| Host | File | Mode | Secret |
|---|---|---|---|
| node0 | `node.env:47` | **644** | `GENESIS_WALLET_PRIVATE_KEY` (66 chars = `0x`+64 hex) |
| node0 | `credentials/postgres_poolhub_password` | **644** | password |
| node0 | `aitbc-exchange.env:1`, `aitbc-wallet.env:1` | 644 | `DATABASE_URL` (DSN with password) |
| node0 | `aitbc-pool-hub.env:1` | 644 | `POOLHUB_POSTGRES_DSN` |
| node0 | `aitbc-miner.env:1` | 644 | `MINER_AUTH_TOKEN` |
| node0 | `aitbc-coordinator-api.env:2` | 644 | `MINER_API_KEYS` |
| hub2 | `blockchain.env:11` | 644 | `BLOCKCHAIN_API_KEY` |

`blockchain.env` is `644` on all five; only hub2's copy carries a secret.
Values were never read or printed — detection was by variable name and length.

**Suggest** `chmod 640` + `chgrp aitbc` on the seven files, then rotate the
affected credentials, since world-readable means any local account could have
read them. Operator action; a per-file approval list can be produced on request.

**Minor** — node2's `/opt/aitbc` is still at `aef0b5099` with
`fleet-config-check.sh` dirty; the file content matches `c9c35d033` but the node
has not run `sync.sh pull`.

### §17.18 — F3/F4/F5 remediation applied (9 Sep, 09:30)

F3, F4, and the file-permission part of F5 were applied after operator approval.

- **F3 closed**: removed `GOSSIP_MESH_PEER_URLS`, `GOSSIP_BROADCAST_URL`, and
  `GOSSIP_WEBSOCKET_URL` from `/etc/aitbc/node.env` on all five hosts.
  `aitbc-blockchain-node` and `aitbc-blockchain-rpc` were restarted. Live
  `/proc/<pid>/environ` on every host now shows the full four-peer mesh list
  (`hub`, `hub2`, `node0`, `node1`, `node2` as appropriate).
- **F4 closed**: all five `redis.conf` now have `bind 127.0.0.1`,
  `protected-mode yes`, and a fresh `requirepass`; `redis-server` was restarted.
  `/etc/aitbc/redis.env` was created (640, group `aitbc`) with `REDISCLI_AUTH`
  so `aitbc-cache-monitor` authenticates. All `redis://` consumer URLs under
  `/etc/aitbc` (`REDIS_URL`, `GOSSIP_BROADCAST_URL`, `SYNC_REDIS_URL`,
  `POOLHUB_REDIS_URL`) now use `redis://:<localpass>@127.0.0.1:6379`. Unauth
  local Redis access is denied everywhere.
- **F5 partially closed**: the seven world-readable files are now `640`
  `root:aitbc`; the stale `BLOCKCHAIN_API_KEY` line was removed from hub2's
  `blockchain.env`. The remaining credentials (`GENESIS_WALLET_PRIVATE_KEY`,
  Postgres DSNs, `MINER_AUTH_TOKEN`/`MINER_API_KEYS`) are covered by the new
  permissions but have not yet been rotated — the genesis wallet requires a
  chain-state migration and the Postgres DSNs require database password changes,
  so those are left for an explicit follow-up.
- **Monitoring fix**: `scripts/monitoring/fleet-config-check.sh` `sleep 60` was
  changed to `sleep 90`, committed as `58d8dca1f5`, pushed to gitea, and
  `git checkout origin/main -- scripts/monitoring/fleet-config-check.sh` was run
  on all five live nodes. The 60s false-HALT window observed during verification
  is now a 90s window.
- **node2 pulled**: `/opt/aitbc` on node2 now reports `58d8dca1f5`.
- **Verification after changes**: `fleet-config-check.sh` from node2:
  **6031 → 6032**, all five hosts same hash, exit 0; all `aitbc-blockchain-*`
  and `redis-server` units are active.
