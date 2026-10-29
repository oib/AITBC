# Shared transfer ledger — `cross_chain_transfer` (#696)

> **Status: DESIGN — drafted for operator decision; no implementation.**
> Problem + options first filed in issue #696. Recommendation of record:
> shared PostgreSQL store for the transfer ledger, with a declared
> intake-host fallback and the existing transplant script as the
> repair path during rollout.

## 1. Problem statement

`cross_chain_transfer` is **service-state**: it is not a committed
table, so its rows do not replicate via block sync. Every
bridge-related stall observed in the fleet traces to the same shape:

- A `BRIDGE_LOCK` POST lands on rpc host A → the `pending`
  `cross_chain_transfer` row is written into A's local `chain.db`.
- The relayer that must act on it (`_relay_pending_transfers`, scoped
  to `target_chain == settings.chain_id` since `b86978769`) reads its
  **own** local `chain.db` — which does not have A's row.
- Result: the transfer is invisible to the correct relayer forever.

Observed incidents, all same class:

- **Lock A** — required a manual pending-row transplant from the
  intake host's `bc-2` db into the relayer's before the release could
  build.
- **Orphan `0x078cfcd8`** — a skipped intake left a pending row on
  hub1's `bc-2` db that the island relayer retried forever
  (`build_proof` could not find an unsealed tx).
- **Phantom `0xf75be64a`** — existed only as a `target_tx_hash` on a
  confirmed row; no live mempool/tx row anywhere.

The `bridge-transplant.sh` script encodes today's repair as a
repeatable op, but every invocation is a manual acknowledgment that
the ledger lives in the wrong scope.

## 2. The design — shared store for the transfer ledger

Move `cross_chain_transfer` reads/writes for bridge coordination onto
a **shared PostgreSQL database** reachable by every bridge rpc:

- A single `bridge` schema (`cross_chain_transfer` as the only table
  today; `bridge_release_authority` config or audit rows are optional
  future additions, not required).
- `session_scope`-level routing: opens for the transfer ledger go to
  the shared store; everything else (blocks, txs, accounts,
  service-state) stays per-chain local sqlite.
- Connection string per host:
  `BRIDGE_LEDGER_DB_URL=postgresql://…` env, unset = today's local
  behavior (fallback preserved, see §5).
- Idempotent upsert by `transfer_id` (the row already keys on it):
  intake writes once; any relayer sees the same row.

This is the same source-of-truth split `MEMPOOL_BACKEND=database`
already proves on the fleet — Postgres `aitbc_mempool` is the
durable mempool for rpc processes that serve one logical chain.

## 3. Relay-race question — answered with code evidence

**Does two relayers acting on the same pending row double-release?**
No lease is required, because release queueing is already idempotent
on `tx_hash`:

- `InMemoryMempool.add` — `if tx_hash in chain_transactions: return
  tx_hash  # duplicate` (`mempool.py` ~185).
- `DatabaseMempool.add`/`add_batch` — pre-fetches
  `MempoolEntry.tx_hash.in_(tx_hashes)` and skips entries already
  present (`mempool.py` ~571-572).

So if two relayers process the same `pending` row in a race, both
emit the same `BRIDGE_RELEASE` (same deterministic `target_tx_hash`
derivation — same record fields in, same hash out), and the second
`mempool.add` collapses to a no-op. **At most one release row can
land in the target mempool.**

The remaining race is wasted *work*, not correctness: two relayers
can both mark `confirmed`/`target_tx_hash` on the row. That is
benign — the status transition is monotonic and the values written
are identical (same deterministic hash). If we want to silence the
double-work, a cheap atomic claim suffices:

```sql
UPDATE cross_chain_transfer SET status='relaying'
WHERE transfer_id=? AND status='pending'
```

— the loser sees 0 rows and skips. Optional polish, not a
correctness requirement.

## 4. Migration

The live ledger on each host today has rows in `pending`/`confirmed`/
`refunded` states that matter for audit and for the finalizer sweep:

1. Introduce `BRIDGE_LEDGER_DB_URL` plumbing: `init_db`/`session_scope`
   route `cross_chain_transfer` access to the shared store when set.
2. One-shot backfill script (`scripts/ops/bridge-ledger-backfill.sh`):
   read each host's local `cross_chain_transfer`, upsert into the
   shared store keyed on `transfer_id` — dedupe naturally collapses
   per-host copies of transplanted rows.
3. Deploy env + rpc wave serially per the standard pattern.

## 5. Fallback

`BRIDGE_LEDGER_DB_URL` unset → per-chain sqlite, byte-for-byte today's
behavior. Rollout order therefore carries an honest abort: pull the
env on any host and it returns to local rows. The pg dependency only
affects the bridge coordination surface — a pg outage degrades
releases (finalizer/relayer no-ops on `OperationalError`, already
bounded by `bridge_finalizer_pass_timeout`) but never block sealing.

## 6. Rollout

1. Code lands (shared-store routing + backfill script), unarmed —
   env unset everywhere.
2. Provision the pg (the same instance class the mempool database
   uses; a `bridge` schema, not a new cluster).
3. Backfill all five hosts' local ledgers into the shared store;
   verify row counts and that transplanted duplicates collapse.
4. Set `BRIDGE_LEDGER_DB_URL` on the island rpcs first (hub1+node1 —
   the pair that actually relays), then the bc-2 rpcs.
5. Serial rpc restarts; the relayer scope stays own-chain — hosts now
   simply see the same rows.

## 7. Acceptance criteria

- A `BRIDGE_LOCK` POSTed to any rpc produces a `pending` row visible
  to every relayer within one finalizer pass — no transplant step.
- The orphan-row class cannot recur: a skipped intake still lands in
  the shared ledger and either relays correctly or surfaces via
  #669's rejected-writeback — never a silent rpc-local zombie.
- Replay-safety: shared store holds service-state only; committed
  side roots are untouched, replay is unaffected.
- Fallback verified: unset env on one host → that host's bridge
  surface returns to local-row behavior with no code rollback.
- The relay race stays correct by dedupe: identical `target_tx_hash`
  collapses to one mempool entry even under simultaneous relayers.
