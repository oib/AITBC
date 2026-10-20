# bc-2 Drain Checklist — old-chain items to settle or clear

The old chain (`ait-hub.aitbc.bubuit.net`) must be drained before the cut
(plan W3, gate A3 in `bc2-reset-runbook.md`). This file is the per-item
checklist: what each item read today, which tool disposes of it, which class
of operator line the action needs, and the read that proves it is zero.

**Timing.** The drain **actions** run days before the freeze window as
operator-named steps (runbook gate A3). Every *zero-check read* below is run
again **after the freeze** at runbook step B5; a row that appears between A3
and B5 is a **new drain item and stops the cut**.

**Classes.** (a) **AIT-moving chain writes** — each is a separate
operator-named chain write, one item per message, after the day-of
prechecks; (b) **service-DB dispositions** — bookkeeping writes inside a
service database, no AIT moves, nothing is signed; the offline backup keeps
the row either way; (c) **not drain items** — terminal surfaces listed once
as evidence, no action exists.

**Reads.** All reads are read-only: aitbc CLI/MCP first, then
`sqlite3 'file:<db>?mode=ro'` on hub (the only host holding the service
ledger DBs). Short-address forms only; no keys, tokens, signatures, or
wallet files. Deposit rows are counted once: `prepaid_deposits` and the
`exchange_prepay` `eth_deposits` row are the same obligation.

## Class A — AIT-moving chain writes

| id | item | today's read (2026-10-20, exact command) | zero-check read (run again at B5) | action tool | who names it | order dependency | if skipped |
|---|---|---|---|---|---|---|---|
| A1 | escrow `sw_job_20260910163039_207d09b8` — 60,912 u, lock height 1262 | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro' \"SELECT job_id,status,amount FROM escrow WHERE job_id='sw_job_20260910163039_207d09b8'\""` → `locked` | `escrow` row `refunded`/`released`, or job absent from `WHERE status='locked'`; sealed tx in `'transaction'` | operator-repair path of `docs/ops/escrow-settlement-ops.md` §1.4 — a settlement tx signed with the settlement-authority key (`ESCROW_RELEASE_PRIVATE_KEY`) submitted to the hub RPC; the `/rpc/escrow/{id}/release\|refund` routes answer 409 for v2-era locks and cannot be used | one operator-named chain-write line per escrow (policy: refund to buyer `0x08aB8011…`); write-off stays available if a precheck fails | day-of prechecks per §1.4: no earlier settlement for the job in `'transaction'` or mempool, authority balance covers value+fee, no coordinator/sweeper re-drive; then one block per escrow | ~0.0017 AIT owed to the buyer stays locked; row unresolved |
| A2 | escrow `sw_job_20260910163341_207d09b8` — 25,056 u, 1265 | same query, `job_id='sw_job_20260910163341_207d09b8'` → `locked` | same | same as A1 | same as A1 | same as A1 | ~0.0007 AIT locked |
| A3 | escrow `sw_job_20260910163355_88d364d9` — 18,000 u, 1265 | same query, `job_id='sw_job_20260910163355_88d364d9'` → `locked` | same | same as A1 | same as A1 | same as A1 | ~0.0005 AIT locked |
| A4 | escrow `ipfs_rental_20260910144545_e01131a8` — 36,000,000 u (**99.4% of the total**), 1277 | same query, `job_id='ipfs_rental_20260910144545_e01131a8'` → `locked` | same | same as A1 | same as A1 | same as A1 | 1.0000 AIT locked |
| A5 | escrow `sw_job_20260910203053_207d09b8` — 60,500 u, 1501 | same query, `job_id='sw_job_20260910203053_207d09b8'` → `locked` | same | same as A1 | same as A1 | same as A1 | ~0.0017 AIT locked |
| A6 | escrow `edge-test-002` — 36,000 u, 1598 | same query, `job_id='edge-test-002'` → `locked` | same | same as A1 | same as A1 | same as A1 | ~0.0010 AIT locked |
| A7 | governance proposal `gap57-aux-sync-test` — `active`, 0 votes, window ended 2026-09-23 | `ssh hub 'aitbc http call blockchain-rpc governance/proposal/gap57-aux-sync-test --method=GET'` → `"status": "active"` | same read → status not `active` (or the expected refusal/no-op recorded) | `aitbc governance execute gap57-aux-sync-test` (or `close`) — expected to refuse or no-op: 0 votes, window long past | one operator-named chain-write line (execution signs on-chain); record the apply-result read | independent; before the cut | stale `active` row if the old chain ever restarts; else none |
| A8 | agent coin request `req-hub2.aitbc.bubuit.net-94Bb6b87-1788974409` — PENDING, 100 AIT | `ssh hub 'aitbc --output=json coin-requests list'` → 1 `pending` row | `aitbc coin-requests list` shows no `pending` row | **decided (D1): reject** — `aitbc coin-requests reject <id>`, bookkeeping only; the approve+execute path is **not** taken, so nothing here moves AIT | decided — the reject is the class-B disposition at B1 | before the cut; independent | decided — a kept pending row would be noise under the plan's D5 (fresh start) |

## Class B — service-DB dispositions (no AIT moves, nothing signed)

Skipping any class-B row does **not** block the cut unless the row says so —
it leaves ledger noise that the offline backup preserves. "Mandatory" is not
claimed anywhere here; the plan requires the drain *checks* to read clean.

| id | item | today's read (2026-10-20, exact command) | zero-check read (at B5) | action tool | who names it | order dependency | if skipped |
|---|---|---|---|---|---|---|---|
| B1 | pending agent coin request (same row as A8) | `ssh hub 'aitbc --output=json coin-requests list'` → 1 `pending` | no `pending` row | `aitbc coin-requests reject req-hub2.aitbc.bubuit.net-94Bb6b87-1788974409` | **decided (D1): reject** — the sender's `hub2` hostname is retired and unreachable | with A8, before the cut | noise only; the row archives with the DB under the plan's D5 (fresh start) |
| B2 | `hermes_coin_requests.db` — 13 `APPROVED` (4 already granted on-chain, 9 never sealed, 5 holding stored envelopes whose sender has no account/balance on-chain), 7 rejected, 2 EXPIRED; task_escrows all terminal | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/hermes_coin_requests.db?mode=ro' -header -column \"SELECT status,count(*) FROM coin_requests GROUP BY status\""` → 13 APPROVED / 7 REJ / 2 EXP | `SELECT count(*) FROM coin_requests WHERE status='APPROVED'` → 0 (or the kept rows waived) | no CLI (parked gap `GAP-CLI-READS-1`); void = DB status update `APPROVED→voided` on the 9 unsealed rows; stored envelopes are dead letters — their sender has no balance to spend | **open decision D4** — recommend void; see the decisions table | before the offline backup so the archived DB is clean | noise; envelopes unusable post-cut (nonces and balances die with the chain) |
| B3 | bridge deposit ledger: `bridge_deposits` 1 `failed` (0.05 ETH, 26 Sep); `eth_deposits` 1 `failed`, 1 `funding`, 1 `exchange_prepay` — the last is the *same* obligation as the `prepaid_deposits` row (counted once) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bridge_deposits.db?mode=ro' -header -column \"SELECT status,count(*) FROM bridge_deposits GROUP BY status; SELECT status,count(*) FROM eth_deposits GROUP BY status\""` | `SELECT count(*) FROM eth_deposits WHERE status NOT IN ('completed','written_off','funding')` → 0; `bridge_deposits` non-terminal → 0 | no CLI for the deposit ledger (`bridge-admin.sh` is the payout ledger — gap `GAP-CLI-READS-1`); reconcile/write-off marks in the DB | **open decision D5** — recommend reconcile; see the decisions table | before the backup | unreconciled rows; no funds (Sepolia testnet ETH, no value) |

## Class C — evidence only (not drain items)

Reads proving each surface is already terminal; re-run at B5 as evidence.

**Waived-baseline rows** (decided "leave all" — D2/D3): these rows keep
today's counts as the accepted baseline. Their B5 re-read is not a zero
check but a **sameness check** — a count that *grew* since A3 is a new
drain item and stops the cut; the listed rows themselves are waived.

| id | surface (baseline) | today's read (2026-10-20, exact command) | B5 sameness check |
|---|---|---|---|
| B4 | exchange `orders` `open` — **baseline 11** (all Jul–Aug test rows with invalid maker addresses — cannot settle) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/exchange/exchange.db?mode=ro' -header -column \"SELECT count(*) FROM orders WHERE status='open'\""` → 11 | still 11 and the same ids; any new `open` row is a new drain item |
| B5 | `marketplace_job_payments` non-terminal — **baseline 4** (2 `settlement_failed`, escrows already refunded on-chain; 2 `pending` amount 0) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/marketplace_service.db?mode=ro' -header -column \"SELECT status,count(*) FROM marketplace_job_payments WHERE status IN ('pending','settlement_failed')\""` → 4 | still 4 |
| B6 | `bridge_sell_quotes` `locked` — **baseline 1** (`sellq_8f78078a4ab2`; its lock is `settled` — status lag, no AIT held) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bridge_deposits.db?mode=ro' -header -column \"SELECT count(*) FROM bridge_sell_quotes WHERE status='locked'\""` → 1 | still 1 |
| B7 | coordinator `job` `payment_status='pending'` — **baseline 18** (none has an escrow row — funds never locked) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/coordinator.db?mode=ro' -header -column \"SELECT count(*) FROM job WHERE payment_status='pending'\""` → 18 | still 18 |

| surface | today's read (2026-10-20) | state |
|---|---|---|
| `escrow_orphan` | `SELECT count(*) FROM escrow_orphan` on chain.db | 6 rows, all `no sealed lock leg`; the one `lock_tx_hash` `0x34fad479…` has 0 rows in `'transaction'` — write-offs by nature, the plan's D5 (fresh start) archives the table |
| mempool | `aitbc http call blockchain-rpc mempool` (MCP `get_mempool`) | `count: 0` |
| `bridge/pending` | `curl http://127.0.0.1:8202/rpc/bridge/pending` on hub (CLI crashes — `GAP-CLI-READS-1`) | `[]` |
| `cross_chain_transfer` | `SELECT status,count(*) FROM cross_chain_transfer GROUP BY status` | 4 confirmed / 3 refunded — all terminal |
| `bridge_outbound` | `SELECT count(*) FROM bridge_outbound` | 5 — event log, no status to drain |
| `eth_withdrawals` / `exchange_settlements` / `eth_withdrawal_release_attempts` | per-table counts | 2 completed / 2 rows / 1 row — terminal or logs |
| hermes `task_escrows`, sealed hermes grants | status counts | 1 REFUNDED + 1 RELEASED; the 4 granted APPROVED requests already moved their AIT |
| coordinator `job` terminal states | `SELECT state,count(*) FROM job GROUP BY state` | 306 terminal (154 completed / 77 expired / 38 failed / 37 canceled) |
| custody-residue accounts | escrow ops doc §1.4 census | v11-swept history; with the plan's D2 (clean slate) nothing carries |
| `keystore.db`, `admin_nonces.db`, wallet/identity records | file inventory | **custody material for the offline backup step — not drain**; a fresh start must never destroy the only copy |

## Operator decisions

| id | decision | state | detail |
|---|---|---|---|
| D1 | pending coin request: reject, or approve+execute 100 AIT | **decided: reject** | the requester id is the retired `hub2` hostname — no live claimant for the grant; carried as disposition B1 |
| D2 | 11 open exchange test orders: cancel or leave | **decided: leave all** | cannot settle (invalid maker addresses); B4 is now a waived-baseline evidence row |
| D3 | status-lag bookkeeping rows (B5, B6, B7): repair or leave | **decided: leave all** | the lag markers archive with the DBs under the plan's D5 (fresh start); B5–B7 are now waived-baseline evidence rows |
| D4 | hermes `coin_requests` — void the 9 unsealed APPROVED rows, or leave | **open — recommend void** | void = one DB status update per row before the backup; cost of leaving: 13 APPROVED rows archived, 5 dead envelopes preserved (sender has no on-chain balance — harmless) |
| D5 | bridge deposit-ledger reconcile — write off the `failed`/`funding`/`exchange_prepay` rows, or leave | **open — recommend reconcile** | reconcile = DB marks before the backup; cost of leaving: unreconciled failed rows archived — no funds at risk (Sepolia testnet ETH) |

## Not covered here

Allocation numbers, the genesis build, key rotation, and the freeze/final
head reads live in `bc2-reset-runbook.md`; env values in
`bc2-environment-set.md`; consumer flips in `bc2-consumers.md`. The four
read-side CLI/MCP gaps found while building this list are parked as
`GAP-CLI-READS-1`.
