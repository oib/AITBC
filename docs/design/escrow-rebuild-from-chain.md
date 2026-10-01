# Escrow rebuild from sealed chain history (SD-1)

**Status**: design — not implemented
**Date**: 2026-10-01
**Target**: the `escrow` table in `chain.db` (`aitbc_chain.base_models.Escrow`);
the agent-coordinator `task_escrows` table is covered as a secondary target
in §7.

## 1. Problem

An `escrow` row is written by `POST /rpc/escrow/lock` **after** the
ESCROW_LOCK transaction is accepted
(`apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py`). Consequences:

- The row exists only on the node that served the RPC. Followers hold the
  sealed transactions but no rows.
- A crash between tx submission and the row write leaves value locked
  on-chain with no bookkeeping row (the handler comment acknowledges this).
- Rows written before metered settlement exist without `released_amount` /
  `refunded_amount`, and a release whose change leg was mined last reads
  back as `refunded`.

Two lazy healers already exist — `_reconstruct_escrow_from_chain` (per-job,
read-triggered, commits immediately) and `backfill_settlement_legs` (fills
NULL leg amounts on read) in
`apps/blockchain-node/src/aitbc_chain/contracts/escrow.py`. They patch rows
one at a time, write without a proof step, and produce no report of what was
missing. SD-1 replaces this with a deterministic full-scan rebuild whose
write phase is gated on a reconciliation proof.

The sealed `transaction` table is the only record guaranteed to exist on
every node — the rebuild treats it as canonical and the `escrow` table as a
derived cache.

## 2. Canonical source

The `transaction` table (`base_models.Transaction`) holds the sealed facts:

| Column | Use in rebuild |
|---|---|
| `type` | `ESCROW_LOCK` / `ESCROW_RELEASE` / `ESCROW_REFUND` |
| `payload["job_id"]` | groups legs into one escrow |
| `payload["action"]` | `escrow_lock` / `escrow_release` / `escrow_refund` — must match `type` |
| `payload["provider"]`, `payload["buyer"]` | parties (buyer falls back to `sender` on old locks) |
| `payload["energy_quote_id" / "energy_quote_digest" / "settlement_route" / "settlement_asset" / "settlement_unit_scale"]` | `protected` lock fields |
| `sender`, `recipient` | payer / payee of the leg |
| `value` | compute-units moved (36,000,000 per AIT) |
| `tx_hash` | `lock_tx_hash` / `release_tx_hash` / `refund_tx_hash` |
| `block_height` | seal marker — `NULL` = mempool-only, excluded |
| `chain_id` | every row and join is chain-scoped |

Only **sealed** transactions feed the rebuild: `block_height IS NOT NULL`
and the referenced `block` row exists. Ordering is by
`(block_height, transaction.id)`, not `id` alone — `id` order is local
insertion order, which is not mining order on a synced node.

A metered release settles as **two legs for one job_id** — an
ESCROW_RELEASE paying the provider plus an ESCROW_REFUND returning the
buyer's unbilled change — and mining order between them is arbitrary.
`settlement_legs_from_chain()` already encodes the correct aggregation:
sum both legs independently and let a release leg win the status. The
rebuild must reuse that function (extracted to a shared helper if needed),
not re-implement it.

## 3. Derivation rules

For each `job_id` with at least one sealed ESCROW_LOCK (latest lock wins —
a second lock for the same job_id is a re-lock and overwrites, matching the
RPC handler):

| `escrow` column | Derivation |
|---|---|
| `job_id` | lock `payload.job_id` |
| `chain_id` | lock `chain_id` |
| `buyer` | `payload.buyer` else lock `sender`, canonicalised |
| `provider` | `payload.provider`, canonicalised |
| `amount` | lock `value` |
| `status` | `released` if a release leg exists; else `refunded` if a refund leg exists; else `locked` |
| `created_at` | **the including block's `timestamp`** — not `transaction.created_at`, which is this node's row-insert time and differs per node |
| `released_at` / `refunded_at` | block timestamp of the *latest* leg of that kind; `refunded_at` stays NULL when a release exists |
| `lock_tx_hash` / `release_tx_hash` / `refund_tx_hash` | tx hashes of the respective legs |
| `released_amount` / `refunded_amount` | `Σ value` per leg kind (NULL only for a `locked` row — settled rows always carry concrete sums) |
| `protected`, `energy_quote_id`, `energy_quote_digest`, `energy_settlement_route`, `energy_settlement_asset`, `energy_settlement_unit_scale` | lock payload fields, verbatim |

`energy_net_floor_units`, `energy_provider_credit_units`,
`energy_fee_basis_points`, `energy_quote_snapshot`, and `job_tx_hash` are
**not in the lock payload** — they come from the quote evaluation / release
request at RPC time. The rebuild leaves them NULL and lists the affected
job_ids in the report (optionally re-deriving the floor fields from the
frozen quote via `NativeEnergyOracle` when the quote id resolves).

The lock era matters for the balance proof in §5: `lock_version` is the
block version of the sealing block (`2` below v3). v3 locks park value at
the deterministic per-escrow address `canonical(keccak("aitbc.escrow." +
job_id)[:40])`; v2 locks hold it in the node wallet.

## 4. Non-derivable fields — stated, not guessed

- `Escrow` has no `expires_at`/metadata columns; nothing to fake there.
- `task_escrows` (§7): `escrow_id` is a local UUID — synthesise
  `rebuilt-<lock_tx_hash[:16]>`; `expires_at` := lock block time + the
  configured default timeout; `extra_metadata` := `{"rebuilt_from":
  "<lock_tx_hash>"}` so rebuilt rows are distinguishable forever.
- Any field the chain cannot supply is NULL or a marked synthetic — never an
  unmarked approximation.

## 5. Reconciliation proof — the write gate

Runs entirely read-only and must pass before `--write` is honoured. The
report is printed and saved next to the target DB.

Per-job invariants:

- **R1** every sealed RELEASE/REFUND leg has a sealed LOCK for its job_id
  (orphan legs ⇒ forked settlement or corruption — listed, never written).
- **R2** `released_amount + refunded_amount ≤ amount` per job.
- **R3** derived status matches the §3 mapping; a refund-only job is never
  marked `released`.
- **R4** every referenced tx is sealed and its block is on the canonical
  chain (parent-hash walk from tip, or the node's canonical-head check).
- **R5** against an existing row: every chain-derived field either equals
  the stored value or the stored value is NULL — a non-NULL conflict aborts
  the whole write and is listed (rebuild never silently overrides recorded
  bookkeeping).

Global invariants:

- **G1** `Σ locked = Σ released + Σ refunded + Σ residual` over all jobs.
- **G2** row count = number of distinct job_ids with a sealed lock.
- **G3** *(v3 locks only, when the account table is available)*
  `account(chain_id, escrow_addr(job_id)).balance == amount − released −
  refunded` — the strongest check: the row is proven against the bonded
  balance itself, not just the journal.
- **G4** FK preconditions: `account` rows for `(chain_id, buyer)` and
  `(chain_id, provider)` exist (true on any synced node — accounts are
  auto-created at apply since v0.25.5; a missing account is listed and its
  job is skipped, never fabricated).

`--write` exits non-zero if any invariant fails. A clean proof writes; a
dirty one only reports.

## 6. Write policy

- Single transaction per run (or per-job batches with a manifest, if the
  scan is large) — the write set is exactly the diff the proof approved.
- Insert missing rows; fill NULL `released_*`/`refunded_*`/hash columns on
  existing rows (the `backfill_settlement_legs` case, generalised); touch
  nothing else.
- Idempotent: a second run over the same chain produces a zero-diff proof
  and writes nothing.
- Deterministic: two nodes rebuilding from identical chain.db snapshots
  produce byte-identical rows.

## 7. Secondary target: `task_escrows`

The agent-coordinator `EscrowEntry` store (`task_escrows` in `aitbc.db`)
tracks the PENDING → LOCKED → RELEASED/REFUNDED/EXPIRED lifecycle keyed by a
local UUID. Rebuilding it from the same proof output uses the §4
synthetics; EXPIRED is not derivable (no expiry tx type — the sweeper
settles expiry as ESCROW_REFUND, which rebuilds as REFUNDED). Phase 2,
optional; the chain-table rebuild must not depend on it.

## 8. Tool sketch

```
venv/bin/python scripts/ops/rebuild-escrows.py \
    --db /var/lib/aitbc/data/<chain_id>/chain.db \
    [--job-id <id>] [--write] [--report /tmp/escrow-recon.json]
```

- Default is a dry run: derive → prove → print the report, write nothing.
- DB opened `mode=ro&immutable=1` for the proof (same discipline as
  `replay-chain.py`); `--write` reopens read-write and should run with the
  node stopped or against a `.backup` copy that is then swapped in.
- Exit codes: `0` clean proof (writes applied if requested), `1` invariant
  failure, `2` write conflicts skipped.
- Report: per-job table (job_id, parties, amount, legs, status, action:
  insert / fill / match / conflict), invariant verdicts, totals.

## 9. Out of scope

- No transaction submission, signing, or mempool interaction — the tool is
  read-derive-prove-write against local files only.
- No change to apply-time behaviour; this is bookkeeping repair, not
  consensus.
- In-memory `EscrowManager` contracts rebuild from the fixed table via the
  existing `load_from_db` on restart.

## 10. Acceptance criteria

- Deleting `escrow` rows on a dev node and running the tool reproduces the
  chain-derived state for every job_id, including the two-leg metered
  releases.
- An existing contradictory row makes the proof red and blocks `--write`.
- A second run is a verified no-op.
- The lazy healers (`_reconstruct_escrow_from_chain`,
  `backfill_settlement_legs`) can be retired or left as read-path fallbacks
  — decision recorded in the decision log when the tool lands.
