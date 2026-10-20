# bc-2 Drain Checklist — old-chain items to settle or clear

The old chain (`ait-hub.aitbc.bubuit.net`) must be drained before the cut
(plan W3, gate A5/A5a in `bc2-reset-runbook.md`). This file is the per-item
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
| A8 | agent coin request `req-hub2.aitbc.bubuit.net-94Bb6b87-1788974409` — PENDING, 100 AIT | `ssh hub 'aitbc --output=json coin-requests list'` → 1 `pending` row | `aitbc coin-requests list` shows no `pending` row | `aitbc coin-requests reject <id>` (bookkeeping, class B) **or** `approve` + `execute` (moves 100 AIT → class A) | operator decision D1 below; if executed it is an AIT-moving chain write (grant, needs the funding wallet context) | before the cut; independent | executed-at-freeze it would grant 100 AIT; otherwise dies with the DB under D5 |

## Class B — service-DB dispositions (no AIT moves, nothing signed)

Skipping any class-B row does **not** block the cut unless the row says so —
it leaves ledger noise that the offline backup preserves. "Mandatory" is not
claimed anywhere here; the plan requires the drain *checks* to read clean.

| id | item | today's read (2026-10-20, exact command) | zero-check read (at B5) | action tool | who names it | order dependency | if skipped |
|---|---|---|---|---|---|---|---|
| B1 | pending agent coin request (same row as A8) | `ssh hub 'aitbc --output=json coin-requests list'` → 1 `pending` | no `pending` row | `aitbc coin-requests reject req-hub2.aitbc.bubuit.net-94Bb6b87-1788974409` | operator decision D1 — **recommend reject**: the sender's `hub2` hostname is retired and unreachable; cost of approve+execute: 100 AIT to a stale requester | with A8, before the cut | noise only; the row archives with the DB under D5 |
| B2 | `hermes_coin_requests.db` — 13 `APPROVED` (4 already granted on-chain, 9 never sealed, 5 holding stored envelopes whose sender has no account/balance on-chain), 7 rejected, 2 EXPIRED; task_escrows all terminal | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/hermes_coin_requests.db?mode=ro' -header -column \"SELECT status,count(*) FROM coin_requests GROUP BY status\""` → 13 APPROVED / 7 REJ / 2 EXP | `SELECT count(*) FROM coin_requests WHERE status='APPROVED'` → 0 (or the kept rows waived) | no CLI (parked gap `GAP-CLI-READS-1`); void = DB status update `APPROVED→voided` on the 9 unsealed rows; stored envelopes are dead letters — their sender has no balance to spend | service-DB write by whoever the operator names (his own line class for a ledger status change, no chain write) | before the offline backup so the archived DB is clean | noise; envelopes unusable post-cut (nonces and balances die with the chain) |
| B3 | bridge deposit ledger: `bridge_deposits` 1 `failed` (0.05 ETH, 26 Sep); `eth_deposits` 1 `failed`, 1 `funding`, 1 `exchange_prepay` — the last is the *same* obligation as the `prepaid_deposits` row (counted once) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bridge_deposits.db?mode=ro' -header -column \"SELECT status,count(*) FROM bridge_deposits GROUP BY status; SELECT status,count(*) FROM eth_deposits GROUP BY status\""` | `SELECT count(*) FROM eth_deposits WHERE status NOT IN ('completed','written_off','funding')` → 0; `bridge_deposits` non-terminal → 0 | no CLI for the deposit ledger (`bridge-admin.sh` is the payout ledger — gap `GAP-CLI-READS-1`); reconcile/write-off marks in the DB | service-DB write, operator-named | before the backup | unreconciled rows; no funds (Sepolia testnet ETH, no value) |
| B4 | exchange `orders` — 11 `open`, all Jul–Aug test rows (`0xtest33`, `0xCustomer1`, `0xbuyer3x` — invalid addresses, **cannot settle**) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/exchange/exchange.db?mode=ro' -header -column \"SELECT id,order_type,amount,remaining,substr(user_address,1,12),created_at FROM orders WHERE status='open'\""` → 11 | `SELECT count(*) FROM orders WHERE status='open'` → 0 (or the 11 waived) | `aitbc exchange` cancel route, or DB `status→cancelled` | operator decision D2 — **recommend cancel** for a clean zero-check; cost of leaving: 11 known-noise rows the B5 re-read must re-waive | before the freeze is enough (intake stops first anyway) | noise; cannot move funds (no valid maker) |
| B5 | `marketplace_job_payments` — 2 `settlement_failed` (0.01 AIT each; both escrows already `refunded` on-chain — lag only), 2 `pending` (amount 0 — bookkeeping) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/marketplace_service.db?mode=ro' -header -column \"SELECT id,job_id,amount,status FROM marketplace_job_payments WHERE status IN ('pending','settlement_failed')\""` → 4 | same read → 0 non-terminal rows | no CLI; DB status repair (`settlement_failed→refunded`, `pending→voided`) | operator decision D3 — **recommend repair**; cost of leaving: two rows that claim an unpaid 0.01 AIT the chain already refunded | before the backup | noise + a misleading unpaid marker |
| B6 | `bridge_sell_quotes.sellq_8f78078a4ab2` — `locked` but its `bridge_sell_locks` row `sell_6a583da9` is `settled` (settle tx sealed) — status lag, **no AIT locked** | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bridge_deposits.db?mode=ro' -header -column \"SELECT q.id,q.status,l.status FROM bridge_sell_quotes q JOIN bridge_sell_locks l ON l.quote_id=q.id\""` → quote `locked`, lock `settled` | quote row terminal | no CLI; DB status repair `locked→settled` | operator decision D3 — **recommend repair** | before the backup | noise; a `locked` row that implies 0.5 AIT held when it is settled |
| B7 | coordinator `job` — 18 `payment_status='pending'` on terminal jobs, **none has an escrow row** (4 match `escrow_orphan` ids — same failed locks) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/coordinator.db?mode=ro' -header -column \"SELECT state,count(*) FROM job GROUP BY state; SELECT payment_status,count(*) FROM job GROUP BY payment_status\""` → 306 terminal; 18 pending payments | `SELECT count(*) FROM job WHERE payment_status='pending'` → 0 (or waived) | no CLI; DB bookkeeping repair | operator decision D3 — **recommend repair**; cost of leaving: pending flags for funds that never existed | before the backup | noise only |

## Class C — evidence only (not drain items)

Reads proving each surface is already terminal; re-run at B5 as evidence.

| surface | today's read (2026-10-20) | state |
|---|---|---|
| `escrow_orphan` | `SELECT count(*) FROM escrow_orphan` on chain.db | 6 rows, all `no sealed lock leg`; the one `lock_tx_hash` `0x34fad479…` has 0 rows in `'transaction'` — write-offs by nature, D5 archives the table |
| mempool | `aitbc http call blockchain-rpc mempool` (MCP `get_mempool`) | `count: 0` |
| `bridge/pending` | `curl http://127.0.0.1:8202/rpc/bridge/pending` on hub (CLI crashes — `GAP-CLI-READS-1`) | `[]` |
| `cross_chain_transfer` | `SELECT status,count(*) FROM cross_chain_transfer GROUP BY status` | 4 confirmed / 3 refunded — all terminal |
| `bridge_outbound` | `SELECT count(*) FROM bridge_outbound` | 5 — event log, no status to drain |
| `eth_withdrawals` / `exchange_settlements` / `eth_withdrawal_release_attempts` | per-table counts | 2 completed / 2 rows / 1 row — terminal or logs |
| hermes `task_escrows`, sealed hermes grants | status counts | 1 REFUNDED + 1 RELEASED; the 4 granted APPROVED requests already moved their AIT |
| coordinator `job` terminal states | `SELECT state,count(*) FROM job GROUP BY state` | 306 terminal (154 completed / 77 expired / 38 failed / 37 canceled) |
| custody-residue accounts | escrow ops doc §1.4 census | v11-swept history; with D2 clean slate nothing carries |
| `keystore.db`, `admin_nonces.db`, wallet/identity records | file inventory | **custody material for the offline backup step — not drain**; a fresh start must never destroy the only copy |

## Operator decisions (recommendation only — the operator picks)

| id | decision | recommendation | cost of the alternative |
|---|---|---|---|
| D1 | pending coin request: reject, or approve+execute 100 AIT | **reject** — the requester id is the retired `hub2` hostname; the 100 AIT grant has no live claimant | approve+execute is an A8 chain write granting 100 AIT to a stale requester |
| D2 | 11 open exchange test orders: cancel or leave | **cancel** — the B5 zero-check then reads clean; they cannot settle (invalid maker addresses) | leaving keeps 11 noise rows the B5 re-read must re-classify each time |
| D3 | status-lag bookkeeping rows (B5, B6, B7): repair or leave | **repair** — one DB status write each, before the backup | leaving keeps misleading "unpaid"/"locked" markers in the archived DBs; not blocking |

## Not covered here

Allocation numbers, the genesis build, key rotation, and the freeze/final
head reads live in `bc2-reset-runbook.md`; env values in
`bc2-environment-set.md`; consumer flips in `bc2-consumers.md`. The four
read-side CLI/MCP gaps found while building this list are parked as
`GAP-CLI-READS-1`.
