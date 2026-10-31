# bc-3 Drain/Waive Checklist — bc-2 items to migrate or archive-then-decommission

bc-2 must be drained before the bc-3 cut (runbook E6 in
`reset2-runbook.md`). This file is the per-item checklist: what each item
read on 2026-10-31, which tool disposes of it, which class of operator
line the action needs, and the read that proves it is settled or stable.
Per the bc-2-fate decision (#410) every row lands in one of two buckets:
**migrate** (value or obligation must reach bc-3) or
**archive-then-decommission** (the offline backup keeps it; nothing is
re-created on bc-3).

**Timing.** The drain **actions** run days before the freeze window as
operator-named steps (runbook gate A3-equivalent for this cut). Every
*zero-check read* below is run again **after the freeze** at the reset-day
precheck; a row that appears between the drain day and the precheck is a
**new drain item and stops the cut**.

**Classes.** (a) **AIT-moving chain writes** — each is a separate
operator-named chain write, one item per message, after the day-of
prechecks; (b) **service-DB dispositions** — bookkeeping writes inside a
service database, no AIT moves, nothing is signed; the offline backup
keeps the row either way; (c) **not drain items** — terminal surfaces
listed once as evidence, no action exists. Each row also declares
**migrate** vs **archive**.

**Reads.** All reads are read-only: aitbc CLI/MCP first, then
`sqlite3 'file:<db>?mode=ro'` on hub (the only host holding the service
ledger DBs; chain.db exists on all five but hub is canonical for reads).
Short-address forms only; no keys, tokens, signatures, or wallet files.

## Class A — AIT-moving chain writes

| id | item | bucket | today's read (2026-10-31, command) | zero-check re-run (reset-day precheck) | action tool | who names it | order dependency | if skipped |
|---|---|---|---|---|---|---|---|---|
| A1 | escrow `61598e4e…` — 360,000 u, locked 31 Oct (buyer `0x08aB…`) | migrate-or-refund | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bc-2/chain.db?mode=ro' \"SELECT job_id,status,amount FROM escrow WHERE status='locked'\""` → 8 locked rows, all 360,000 u, all created 31 Oct (stress-3 lifecycle legs) | `escrow` count `status='locked'` = 0 | settlement-authority release/refund per `docs/ops/escrow-settlement-ops.md` — each lock's own tool (job completion → release, abort → refund) | one operator-named chain write per row (or a single line waiving the batch as transient stress traffic that settles before the freeze) | day-of prechecks per the ops doc: no earlier settlement for the job, authority balance covers value+fee | locked value stays locked; the buyers' ~0.08 AIT is unreturned |
| A2 | escrow `6d6e8a86…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same query → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A3 | escrow `aca9dfc3…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A4 | escrow `128597ee…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A5 | escrow `f0e09e49…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A6 | escrow `fe0ddbae…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A7 | escrow `616fd58a…` — 360,000 u (buyer `0xBdDF…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A8 | escrow `695bf058…` — 360,000 u (buyer `0xAbD0…`) | migrate-or-refund | same → locked | same | same as A1 | same as A1 | same as A1 | ~0.01 AIT locked |
| A9 | governance `prop_0b91289d` — `active`, EXECUTE-eligible @18437 (~Nov-06) | archive (decided: let it land or die — see note) | `ssh hub 'aitbc --output=json governance list'` → `active`, ends_block 18437 | status not `active` (EXECUTE applied or window passed) or an explicit waive line | `aitbc governance execute prop_0b91289d` post-window, or record as dead-on-archive | one operator-named chain write OR one waive line | window @18437 must pass before the cut per the post-Nov-07 ruling | stale `active` row archives with the chain; no obligation |
| A10 | governance `prop_bfc73030` / `prop_b84b545e` / `prop_6bbc21b3` — `active`, EXECUTE-eligible @19525/19534/19541 (~Nov-07) | archive | same read → 3 `active` rows | same | same as A9 | same as A9 | same as A9 | same as A9 |
| A11 | agent stake `stress-op-1793349281` + `stress-op-1793349286` — `active`, 36,000 u each, `locked_until` 2026-11-29 | archive (stress exercise positions — not customer value) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bc-2/chain.db?mode=ro' \"SELECT stake_id,status,amount,locked_until FROM agent_stake WHERE status='active'\""` → 2 rows | `agent_stake` count `status IN ('active','unbonding')` = 0 on the row-owning host(s) | agent-staking unbond→complete (wall-clock gated to 29 Nov — cannot accelerate; waive or wait) | one operator-named line: unbond-after-window (impossible pre-cut) OR waive-as-archive | unbond cannot run before 2026-11-29 — the only options are wait or waive | locked stake value archives; the operator's own exercise wallets, no customer loss |
| A12 | liquidity stake rows `liq_0x8a3c…` (180,000 u, `0x08aB…`), `liq_0xf6b9…`/`liq_0x1776…`/`liq_0x6ffa…`/`liq_0x363b…` (100–180 u, `0x4A5b…`/`0xBdDF…`) — 5 `active` | archive (exercise positions; the 180k row is the only material one) | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/bc-2/chain.db?mode=ro' \"SELECT * FROM liquidity_stake WHERE status='active'\""` → 5 rows | `liquidity_stake` count `status='active'` = 0, or waived | `liquidity-unstake` / `liquidity-claim` wallet legs, or waive line | one operator-named line per owner or a batch waive | withdraw semantics per the liquidity pool's own maturity rules | pool share archives; ~0.005 AIT principal unclaimed |

## Class B — service-DB dispositions (no AIT moves, nothing signed)

| id | item | bucket | today's read (2026-10-31, command) | zero-check re-run | action tool | who names it | order dependency | if skipped |
|---|---|---|---|---|---|---|---|---|
| B1 | coin request `req-node0.aitbc.bubuit.net-48Caf435-1793083474` — PENDING, 36,000,000 units | archive | `ssh hub "sqlite3 'file:/var/lib/aitbc/data/hermes_coin_requests.db?mode=ro' \"SELECT id,status,amount FROM coin_requests WHERE status='PENDING'\""` → 3 PENDING | no `PENDING` rows | `aitbc coin-requests reject <id>` (bookkeeping only) | one operator-named line per row or a batch-reject line | before the cut; independent | pending row archives with the DB |
| B2 | coin request `req-node0.aitbc.bubuit.net-48Caf435-1793088928` — PENDING, 108,000,000 u | archive | same → PENDING | same | same as B1 | same as B1 | same as B1 | same |
| B3 | coin request `req-node0.aitbc.bubuit.net-Bc306DfF-1793098741` — PENDING, 108,000,000 u | archive | same → PENDING | same | same as B1 | same as B1 | same as B1 | same |

## Class C — evidence only (not drain items; re-read as sameness checks)

**Waived-baseline rows** — these keep today's counts as the accepted
baseline. Their precheck re-read is a **sameness check**: a count that
*grew* is a new drain item and stops the cut; the listed rows are waived.

| id | surface (baseline) | bucket | today's read (2026-10-31) | precheck sameness check |
|---|---|---|---|---|
| C1 | `escrow_fee_recipient` burn accrual — **0x34FFfAd1… balance 36,279,209 u (~0.00101 AIT) across ~19 ESCROW_FEE_SWEEP txs** | archive (burn address — keyless by audit; R8 replaces it with a custodied key on bc-3) | `sqlite3 'file:/var/lib/aitbc/data/bc-2/chain.db?mode=ro' "SELECT balance FROM account WHERE address='0x34FFfAd14Af6ba258DC63eBf38a2f48F4589f267'"` → 36279209; `SELECT count(*) FROM "transaction" WHERE type='ESCROW_FEE_SWEEP' AND block_height IS NOT NULL` → 19 | same balance + count; any growth is more sweep residue landing pre-cut — accepted, burns with the chain. **Waive decision quantified: ~0.001 AIT is written off.** |
| C2 | coin requests APPROVED — **baseline 3** (108M, 36M, 108M — all node0 test rows; envelopes unexecuted) | archive | `sqlite3 'file:.../hermes_coin_requests.db?mode=ro' "SELECT status,count(*) FROM coin_requests GROUP BY status"` → 3 APPROVED / 3 PENDING | still 3 APPROVED after B1–B3 rejects; any new row is a drain item |
| C3 | `bond` — **baseline 1 `slashed`** (amount 0, terminal) | archive | `sqlite3 ... "SELECT status,count(*) FROM bond GROUP BY status"` → 1 slashed | still 1 |
| C4 | `cross_chain_transfer` — **baseline 8 completed + 8 refunded** (all terminal) | archive | `sqlite3 ... "SELECT status,count(*) FROM cross_chain_transfer GROUP BY status"` | same split |
| C5 | `ipfs_subscription` — **baseline 7 rows** (bc-2-island ×5 expiring @101459–101635 — *already past*; bc-2-island-1 ×2 @12187/12428 — past) | archive | `sqlite3 ... "SELECT island_id,member_address,expires_at_block FROM ipfs_subscription"` → 7 rows, all expiry heights < head | still 7; all expiry blocks already behind head at read — lapsed subscriptions, no live entitlement |
| C6 | escrow terminal rows — **baseline 20 refunded + 22 released** | archive | `sqlite3 ... "SELECT status,count(*) FROM escrow GROUP BY status"` | locked count is the drain item (A1–A8); terminal counts are baseline only |
| C7 | mempool pending rows — **baseline ~36 pending at read** | archive (dies with the chain) | `sqlite3 ... "SELECT count(*) FROM \"transaction\" WHERE block_height IS NULL"` → ~36 | expect ~0 at freeze precheck; nonzero = new drain item |
| C8 | `keystore.db`, `admin_nonces.db`, wallet/identity records | archive — **custody material for the offline backup, not drain**; a fresh start must never destroy the only copy | file inventory on each host | unchanged convention from the bc-2 table |
| C9 | island `bc-2-island-1` chain + its 2-validator set on hub1/node1 | archive — decommissions alongside bc-2 (island fate follows the parent cut; `bc-3-island-1` is a fresh genesis per the R-answer) | `curl -sf http://127.0.0.1:8302/rpc/status` on hub1 → head ~4078 | evidence row only |
| C10 | committed-table rows completed: `agent_stake` completed ×2+7, `liquidity_stake` withdrawn ×5, `bounty_*` terminal | archive | per-table status counts | sameness |

**Operator note on waived Class-A items:** the maturity-gated rows (A11
stakes locked until 2026-11-29; A12 liquidity positions) cannot be drained
before their windows — the waive-vs-wait decision is the operator's word
at freeze-planning, default **waive-as-archive** since every owner is an
exercise/operator wallet, not a customer.
