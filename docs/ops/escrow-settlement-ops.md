# Escrow settlement operations — pipeline and alert response

How a marketplace job's escrow moves from lock to settled money, which moving
parts can lie about it, and what to do when the settlement or fork alerts
fire. Mechanisms verified against the code; where the repo does not say
enough to be sure, the entry says "not verified".

Companion doc: `docs/ops/escrow-routing.md` (why escrow rows exist only on
the node that accepted the create call — every read below is per-host for
the same reason).

## 1. The settlement pipeline

### 1.1 Lock

`POST /rpc/escrow/create` (submitted by the coordinator — `payments.py`
posts to `/rpc/escrow/create` or, on the wallet-mediated path,
`/api/v1/escrow/create`) signs and submits an `ESCROW_LOCK`
transaction paying the buyer's funds to a per-job **custody address**
(`escrow_routes.py:_build_lock_tx`). Admission is a signature + balance
check; the lock lands when a proposer seals the block containing it.

The custody address is **keyless** —
`pure_state_transition.py:_escrow_address(job_id)` derives it deterministically:
`keccak("aitbc.escrow.<job_id>")[:20]`, checksummed. No private key exists;
the account is spendable only through the consensus apply path for
`ESCROW_RELEASE`/`ESCROW_REFUND`. Same derivation every node uses, so any
host can compute a job's account from the id alone.

### 1.2 The sealed-lock gate (HTTP 425)

Before building the settlement tx, `release`/`refund` call
`escrow_routes.py:_ensure_lock_sealed(job_id)`, which probes the hub RPC's
sealed `transaction` table for the job's `ESCROW_LOCK`. Absent →
`HTTPException(425)` with `Retry-After: 5` and "retry after the ESCROW_LOCK
lands". Rationale (the S-8 disease): a settlement evaluated before its
lock's block is dropped at apply time, while the route would still mark the
local row settled — the row then serves a dead hash forever. The gate makes
the route defer exactly the settlements production would have dropped.

Callers see "not yet, retry": the coordinator returns False and re-attempts
on its next sweep (`payments.py:_submit_release` treats any non-success as
unsettled and leaves the payment escrowed). The retry consumes a release
attempt — `meta[META_RELEASE_ATTEMPTS]` is incremented before the submit,
so each 425 spends one of `COORDINATOR_RELEASE_MAX_ATTEMPTS` (default 20,
`acceptance.py:max_release_attempts`); exhausting the budget marks the
payment `settlement_failed`, which the admin retry-release route can
re-drive once the blocker is fixed.

### 1.3 Release and refund routes

`POST /rpc/escrow/{job_id}/release` and `/refund`
(`escrow_routes.py`) — each runs the 425 gate, then the **v2-era guard**
(`_refuse_v2_lock`, see §1.4), then the idempotency lookups
(`_find_existing_release`/`_find_existing_refund`: a sealed settlement for
the same `job_id` returns that tx instead of re-paying), then signs the
settlement tx with the settlement-authority key and submits it to the hub
RPC. On acceptance the local escrow row is **marked at once** —
`released_at`/`refunded_at` set to now, `status` to `released`/`refunded`,
the leg's `*_tx_hash` stored. The mark claims settled from RPC acceptance
onward; it is *not* proof the transaction sealed.

### 1.4 The v2/v3 boundary (`state_transition_v3_height`)

`pure_state_transition.py:_escrow_release_refund_delta` dispatches on the
lock's era (`lock_version`, defaulting to `block_version >= 3 → 3`):

- **v3 (locks sealed at/above `state_transition_v3_height`)** —
  `_escrow_v3_release_refund_delta`: the value comes *out of the keyless
  escrow account* (`extra_debits`); the signing settlement authority pays
  only the tx fee. The sender must equal the chain parameter
  `escrow_settlement_authority` (env fallback `ESCROW_RELEASE_ADDRESS`;
  fail-closed at `block_version >= 5`), and when the apply context carries
  `expected_beneficiary` the recipient must match it. Money safety: a
  release cannot pay from anywhere but the job's own locked funds, an
  underfunded escrow fails the delta, and only the authority can sign one.
- **v2 (locks sealed below that height)** — `_escrow_v2_release_refund_delta`:
  the sender pays `value + fee` outright; there was no custody account to
  debit. Money safety: the authority's own balance funds the payment, and
  there is no apply-time dedup between a dropped first submission and a
  re-drive — a late-sealing original *and* the retry both pay. That is why
  `_refuse_v2_lock` refuses route settlement for locks sealed below the v3
  height with `409` ("operator repair only") and why re-driving a v2 row
  through the normal routes is impossible by design.

The fleet pins `state_transition_v3_height=5470` via `blockchain.env`
(code default `0` = inert); see `docs/ops/v5-replay-inventory.md`.

### 1.5 The unlanded-settlement detector

`scripts/monitoring/escrow-settlements-textfile.py`, run every minute by
`aitbc-escrow-settlements.timer` (one systemd unit per host). It opens each
`data/*/chain.db` under `AITBC_DATA_DIR` **read-only** (`mode=ro`) and flags
every escrow leg that claims settled — by `status`, by a settlement
timestamp, or by a stored `*_tx_hash` (a hash is itself a claim) — whose
stored hash is absent from the sealed `transaction` table and whose mark is
older than `AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS` (default 900 s; sealed
with a *failed* status still counts as landed — that is an apply-side
disease, not this one). Output is the node-exporter textfile
`aitbc_escrow_settlements.prom` with the per-job
`aitbc_escrow_unlanded_settlement{job_id,kind}` series plus
`scrape_success{db}` and `scrape_timestamp_seconds` health metrics — a DB
that cannot be read reports failure, never "all clear".

### 1.6 The lite settlement sweeper

`escrow_settlement_sweeper.py` runs inside `aitbc-blockchain-rpc` (the app
starts it via `start_settlement_sweeper()`; the service runs
`--workers 1`, so exactly one sweeper per host, each reading its own
node-local escrow table). Interval `settings.escrow_settlement_sweep_interval`
(default 60 s), age threshold `_MAX_AGE_SECONDS = 900` — the same 900 the
detector uses, so the two never disagree. Demote-only, never submits:

- a marked leg whose stored hash is sealed → *verified*, row untouched;
- an unmarked leg whose sealed settlement exists (found by hash, then by
  `(job_id, tx_type)` job-id probe) → *re-marked* with the seal record's
  `created_at` (mark-from-seal);
- a claimed leg older than 900 s whose hash is absent from the sealed table
  **and** absent from the proposer's mempool → *demoted*: timestamp
  cleared, status re-derived (`settlement_failed` when no leg remains).
  The dead hash stays on the row so the detector keeps firing — demotion
  changes the claim, not the audit trail.
- The proposer-mempool probe
  (`HUB_BLOCKCHAIN_RPC_URL` → `/rpc/mempool`, else `_HUB_RPC_URL`)
  **fails closed**: non-200, unreachable, or a truncated answer
  (`count >= limit`) means "no demotion this tick" — a still-pending leg
  is never treated as dead.

### 1.7 Where the fee goes

A v3 lock funds the custody account with the full locked amount; the
release moves only the settlement legs — the platform's fee share has no
leg and **stays behind as residue in the per-job account**. There is no
sweep today; residue accumulates in keyless accounts the consensus code
alone can debit. (A fee-sweep design — an authority-signed `ESCROW_FEE_SWEEP`
type behind a future transition height — exists as an operator-local
proposal and is deliberately not described further here: it is not built.)

## 2. Alert response

Severity and expressions below are the repo's `scripts/monitoring/aitbc_rules.yml`.
"Confirm" commands are read-only. **Agent-safe** = read and report only.
**Operator-only** = anything that mutates a host, restarts a service,
submits a transaction, or touches a key.

### EscrowSettlementUnlanded — critical

`aitbc_escrow_unlanded_settlements > 0` for 5 m. A node-local escrow row
claims settled but its stored settlement hash never sealed — the row serves
a dead hash while custody (provider pay or buyer refund) is unresolved.

- **Confirm:** the per-job series names the rows:
  `aitbc_escrow_unlanded_settlement{job_id="...",kind="release|refund"}`.
  On the alerting host, inspect the row and the sealed table (read-only):
  `sqlite3 "file:/var/lib/aitbc/data/<chain>/chain.db?mode=ro" \
  "SELECT job_id,status,release_tx_hash,refund_tx_hash,released_at,refunded_at FROM escrow WHERE job_id='<job>'"`
  then `SELECT 1 FROM 'transaction' WHERE tx_hash='<stored hash>'` — absent
  confirms the alert. Also check whether the *sweeper* has since re-marked
  or demoted the leg (a leg younger than 900 s is merely in-flight).
- **Agent-safe:** report the `(job_id, kind, host)` triple; check the
  proposer mempool (`GET /rpc/mempool`) for the stored hash — present means
  slow-settling, absent means dropped.
- **Operator-only:** any repair submission (the remedy path signs with the
  settlement-authority key — env var `ESCROW_RELEASE_PRIVATE_KEY`).

### EscrowSettlementCheckStale — warning

`time() - aitbc_escrow_settlement_scrape_timestamp_seconds > 600` for 10 m:
the textfile stopped updating — the detector isn't running, not necessarily
that settlements are broken.

- **Confirm:** `systemctl status aitbc-escrow-settlements.timer` (and the
  `.service` last-run journal) on the alerting host; the prom file's mtime
  under `AITBC_TEXTFILE_DIR`.
- **Agent-safe:** report which host + when the timer last ran.
- **Operator-only:** restarting the timer/service; editing the unit.

### EscrowSettlementCheckFailed — warning

`aitbc_escrow_settlement_scrape_success{db="..."} == 0` for 10 m: the
detector ran but could not read a chain.db (missing `escrow` table or an
open failure counts as failure by design).

- **Confirm:** the `db` label names the file; try
  `sqlite3 "file:<db>?mode=ro" "SELECT count(*) FROM escrow"` on that host.
- **Agent-safe:** report host + db path + the sqlite error.
- **Operator-only:** fixing the DB path (`AITBC_CHAIN_DB` drop-in),
  permissions, or the database itself.

### RemoteWriteFailing — warning

`rate(prometheus_remote_storage_samples_failed_total[15m]) > 0` for 15 m:
the local Prometheus is having remote-write samples rejected by the
receiver — a rejected batch drops every series in it, including unrelated
ones.

- **Confirm:** the counter is Prometheus's own
  (`prometheus_remote_storage_samples_failed_total`), so it only exists on
  hosts whose prometheus.yml scrapes the `prometheus` job itself — absence
  of the series on a host means the alert is structurally blind there, not
  healthy. On an alerting host: `curl -s localhost:9090/api/v1/query?query=
  prometheus_remote_storage_samples_failed_total` and the Prometheus
  journal for the receiver's rejection message (usually a
  duplicate/out-of-order/timestamp reason).
- **Agent-safe:** report the host, the rejection text, and whether the
  counter is rising (a flat increment is a past incident).
- **Operator-only:** changing remote-write config, relabels, or the
  receiver.

### ForkReorgUndone — warning

`increase(sync_fork_reorg_undone_total[10m]) > 0`: the delta journal
auto-reverted a losing non-empty segment on the node — fork choice did its
job, but confirmed transactions were displaced.

- **Confirm:** the counter
  (`sync_fork_reorg_undone_total` in `metrics.py`, incremented in
  `sync_block_import.py`/`sync_bulk.py`) and the node journal around the
  reorg for the undone segment's height range.
- **Agent-safe:** report which node, the height range, and whether
  `ForkOrphanedTxLost` fired alongside (that is the alert for a displaced
  tx that failed requeue).
- **Operator-only:** anything beyond reading — a fork that needed the
  journal means the validator set partitioned; root cause is operator work.

### ForkOrphanedTxLost — critical

`increase(sync_fork_orphaned_tx_lost_total[10m]) > 0`: a transaction that
lived only on the losing segment failed mempool requeue and is absent from
the winning branch — a user's *confirmed* transaction is gone. The reconcile
pass logs a WARNING with the hash and sender (`block_deltas.py`).

- **Confirm:** journal for the orphan-reconcile warning naming hash+sender;
  verify the hash is absent from the sealed `transaction` table and the
  mempool.
- **Agent-safe:** report the hash, sender, type, and which node.
- **Operator-only:** reconciling/resubmitting — the tx needs a fresh signed
  submission, which only the owner (or the operator acting for them) can
  produce.

### ForkDomainRowOrphaned — warning

`increase(sync_fork_domain_rows_orphaned_total[10m]) > 0`: an RPC-written
domain row (`stake`/`agent_stake`/`bounty_contract`) lost its confirming
lock tx in a reorg and was marked `status='orphaned'`. The same reconcile
pass revives it automatically if the lock confirms on the winning branch,
so this can self-resolve.

- **Confirm:** the domain row's status on the node
  (`SELECT status FROM stake|agent_stake|bounty_contract WHERE ...`) and
  whether the referenced lock hash landed.
- **Agent-safe:** report the row and whether a later read shows it revived.
- **Operator-only:** manually un-orphaning or re-issuing the lock.

### V9ShadowRejection — warning

`increase(v9_would_reject_total[10m]) > 0`: in v9 shadow mode a transaction
*would have* been refused by the v9 authorization rules — nothing was
rejected for real; the counter exists to prove the pinned rules before the
height goes live (`v9_policy.py`).

- **Confirm:** the `v9_would_reject_*` detail counters (the per-reason
  siblings of `v9_would_reject_total`) and the node journal for the
  offending tx hash/type.
- **Agent-safe:** report which rule fired and the tx it would have caught.
- **Operator-only:** the decision the counter feeds — pinning the v9 height.

### V9AttestationRefusal — warning

`increase({__name__=~"v9_would_reject_attest_.*_total"}[10m]) > 0`: a
validator would have refused to attest a block under the v9 rules —
per-reason counters exist for missing signature, not-at-parent, nonce
order, and invalid signature.

- **Confirm:** which `v9_would_reject_attest_*` counter moved, and the
  journal for the refused attestation's block/hash.
- **Agent-safe:** report the reason counter, the validator, the block.
- **Operator-only:** key/validator changes and the v9 pin decision — same
  shadow-mode intent as above.

### Not verified from the repo

- `EscrowSettlementUnlanded` repair mechanics end-to-end (the remedy path
  is an operator-local runbook; the doc above describes only the route and
  apply code).
- Whether any receiver-side remote-write rejection reason beyond the
  generic "samples failed" counter is logged with detail — depends on the
  receiver's log surface, which is not in this repo.
- `ForkReorgUnsafe` (fires alongside the fork family; not in the requested
  list — escalates instead of auto-reverting, per the rule's own
  description).

## 3. Rule annotations

`aitbc_rules.yml` does **not** use a `runbook_url` annotation (no rule in
the file carries one — the only "runbook" string is a comment pointing at
the operator-local fork runbook). Per the no-new-convention instruction,
none is added here; if the convention is adopted later, every alert in the
file currently lacks it — the nine documented above plus
`BlockProposedButNoSubscribers`, `BroadcastSkipped`, `ServiceDown`,
`BlockProcessingTooSlow`, `RpcErrorsSpiking`, `SyncLagHigh`, `MempoolFull`,
`ForkReorgUnsafe`, `FaucetBudgetTripped`, `PrometheusWatchStale`,
`AITBCJournalErrors`, and `AITBCJournalScanStale`.
