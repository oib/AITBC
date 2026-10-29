# Shared transfer ledger — `cross_chain_transfer` (#696)

> **Status: DECIDED — hub-rpc-hosted ledger service; ready for
> implementation. Production target: hub's `aitbc-blockchain-rpc`
> (port 8202). Dev/testing deployment: hub1.**

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

## 2. The design — a ledger service hosted by the rpc

The transfer ledger becomes an **HTTP surface hosted inside the
designated host's existing `aitbc-blockchain-rpc` process** — a
router mount, not a new unit:

- **Production target: hub** — `aitbc-blockchain-rpc` on hub (port
  8202) mounts `/rpc/bridge/ledger/*`. Hub already plays coordinator
  for bridge ops (bridge-admin, the monitor, the payout ledger live
  there); the transfer ledger joins that surface.
- **Dev/testing: hub1** — same mount on hub1's rpc exercises the
  full path before hub cutover.
- **Auth:** the existing rpc API key (`BLOCKCHAIN_RPC_API_KEY`,
  `X-API-Key`) — no new credential class.
- **Store:** the host's own `cross_chain_transfer` table — sharing
  happens over the HTTP surface, not the database. No pg, no new
  unit, no new port.
- **Scope:** the service holds rows for **both** chain pairs
  (bc-2 → island and island → bc-2) — the gap is bidirectional and
  both relayers can reach the host.

### Routes (contract sketch)

| route | caller | purpose |
|---|---|---|
| `POST /rpc/bridge/ledger/register` | intake rpc | upsert the pending row by `transfer_id` (idempotent) |
| `GET /rpc/bridge/ledger/pending?target_chain=…` | relayer | the relay worklist — replaces the local `status='pending'` scan |
| `POST /rpc/bridge/ledger/{id}/status` | relayer | status + `target_tx_hash`/proof writeback (monotonic transitions only) |
| `GET /rpc/bridge/ledger/{id}` | ops/monitor | single-row read (transplant-script replacement) |

Remote rpcs keep their local row as a **write-through cache** —
intake still writes locally (today's code path unchanged), then
registers with the service; the relayer reads its worklist from the
service instead of the local scan.

## 3. Relay-race question — answered with code evidence

**Does two relayers acting on the same pending row double-release?**
No lease is required, because release queueing is already idempotent
on `tx_hash`:

- `InMemoryMempool.add` — `if tx_hash in chain_transactions: return
  tx_hash  # duplicate` (`mempool.py` ~185).
- `DatabaseMempool.add`/`add_batch` — pre-fetches
  `MempoolEntry.tx_hash.in_(tx_hashes)` and skips entries already
  present (`mempool.py` ~571-572).

So if two relayers poll the same `pending` row in a race, both emit
the same `BRIDGE_RELEASE` (same deterministic `target_tx_hash`
derivation — same record fields in, same hash out), and the second
`mempool.add` collapses to a no-op. **At most one release row can
land in the target mempool.**

Double *work* (both relayers status-writeback the row) is benign —
transitions are monotonic and the written values identical. The
service may add a cheap atomic claim (`UPDATE … SET status='relaying'
WHERE status='pending'` → loser sees 0 rows) as polish, not a
correctness requirement.

## 4. Migration

1. Land the ledger router + client helpers unarmed — remote rpcs keep
   local-scan behavior when `BRIDGE_LEDGER_URL` is unset.
2. Deploy to **hub1's rpc first (dev)** — register + poll exercised
   end-to-end against hub1, transplant script still the repair path.
3. Backfill: one-shot script upserts each host's local rows into the
   service keyed on `transfer_id` — transplanted duplicates collapse
   on dedupe.
4. Cutover: set `BRIDGE_LEDGER_URL` fleet-wide, serial rpc restarts —
   relayers switch from local scan to service poll.

## 5. Fallback

`BRIDGE_LEDGER_URL` unset → local-scan behavior, byte-for-byte today.
An unreachable service degrades the same way (register/poll failures
log + skip the pass — the finalizer is already bounded and
error-tolerant). Block sealing is never on this dependency.

## 6. Rollout

1. Code lands unarmed everywhere.
2. **hub1 (dev):** `BRIDGE_LEDGER_URL=http://127.0.0.1:8203` (or the
   hub1 rpc port) on hub1+node1 island rpcs; exercise a full
   lock→release round trip in dev.
3. **hub (prod):** ledger router live on hub:8202;
   `BRIDGE_LEDGER_URL` set on all bridge rpcs (island + bc-2).
4. Serial rpc wave per the standard pattern; transplant script
   remains the manual repair path during burn-in.

## 7. Acceptance criteria

- A `BRIDGE_LOCK` POSTed to any rpc produces a `pending` row visible
  to the correct relayer within one finalizer pass — no transplant.
- The orphan-row class cannot recur: a mis-routed intake still
  registers with the service and either relays correctly or surfaces
  via #669's rejected-writeback — never a silent rpc-local zombie.
- Replay-safety: the service hosts service-state only; committed
  side roots untouched.
- Fallback verified: unset `BRIDGE_LEDGER_URL` on one host → local
  scan resumes, no code rollback.
- The relay race stays correct by dedupe: identical `target_tx_hash`
  collapses to one mempool entry even under simultaneous relayers.
