# Messaging-series combined rollout plan

Release candidate: **`0a4d4ab92`** (MSG-8 Phase 1 + MSG-8e + MSG-15 +
BR-6c + wallet/exchange path changes). One maintenance wave, one pull per
host, one combined verification. This document is the plan only — every
restart below is a named, operator-gated line; nothing here is executed by
this task.

## Operator checklist (required restart lines)

Standing authorisation scope (per workspace `AGENTS.md`): checkouts may be
pulled/fast-forwarded routinely. **Service restarts are not covered by any
standing authorisation** — the 22 restart lines below each need explicit
go-ahead at execution time.

| # | host  | restart lines required |
|---|-------|------------------------|
| 1 | node0 | node, rpc, explorer, wallet |
| 2 | node1 | node, rpc, explorer, wallet |
| 3 | node2 | node, rpc, explorer, wallet |
| 4 | hub1  | node, rpc, explorer, wallet |
| 5 | hub   | node, rpc, explorer, wallet, exchange, bridge-monitor |

Total: **22 restarts, 5 pulls, 1 website re-render** (static, no service).

**Restart comparison — combined vs. piecemeal:** the delta carries two
independent deployable sets — the messaging series (node + rpc +
explorer = 15 restarts) and the bridge/wallet path changes (wallet ×5 +
exchange + bridge-monitor = 7 restarts). Deployed separately that is the
same 22 restarts but across **two** pull waves, two checkout flips per
host, and two verification rounds — plus a window where messaging code
and bridge code disagree across the fleet. Combined saves a full wave and
removes that intermediate state; restart count itself is unchanged
because the sets are disjoint.

## Preconditions (verify before step 1)

- `origin/main` still = `0a4d4ab92`; if it moved, re-run the delta audit
  or confirm the new commits are additive before proceeding.
- All five hosts healthy: `systemctl is-active` green on the units above,
  head agreement ±1 across `/rpc/head`, no active alert log entries.
- `BRIDGE_DEPOSITS_DB` present in `blockchain.env` (already true).
- No `dm_key`/`dm` envelopes may be submitted during the rollout — hold
  until every host runs the candidate (see DM gate below).

## Sequence

**Step 0 — pull (all hosts, any order).**
`cd /opt/aitbc && git fetch origin && git merge --ff-only 0a4d4ab92`.
Checkout ≠ running code; no service impact. This mixed state is already
live on node2 and verified harmless.

Per-host steps below run **one follower at a time**; do not start the next
host until the previous one's checks pass. Follower order: node0 → node1
→ node2 → hub1. **Proposer (hub) last.**

**Step N.a — restart `aitbc-blockchain-node`.**
`systemctl restart aitbc-blockchain-node`. Expect ~90 s before first
proposal/follower resync — do not alarm inside that window.
Checks: `MainPID` changed; `ActiveEnterTimestamp` new; `journalctl -u`
shows no crash loop; follower re-catches head within ~2 min
(`/rpc/head` on the host vs hub's head — allow ±1 while catching up).

**Step N.b — restart `aitbc-blockchain-rpc`.**
Checks: `MainPID`/`ActiveEnterTimestamp` new; `GET /rpc/head` returns;
`GET /rpc/messaging/stats` reports `index_height` catching up to head
with `index_lag_blocks → 0`; `/rpc/messaging/dm-keys/{addr}` 404s
cleanly on an empty address (endpoint live, not 500).

**Step N.c — restart `aitbc-blockchain-explorer`.**
Checks: `MainPID` new; explorer `/messages` page/API returns rows.

**Step N.d — restart `aitbc-wallet`.**
Checks: `MainPID` new; wallet status endpoint healthy.

**Digest check (after N.a–N.d):** `checkpoint_digest` from
`/rpc/messaging/stats` should match hub's once both are on the candidate —
compare only between fully-upgraded pairs (mixed-code digests can
legitimately differ; see progress doc matrix). Head hashes across all
hosts must agree regardless.

**Step 5 — hub (proposer), same order plus:**
- `aitbc-exchange` restart — check status endpoint.
- `aitbc-bridge-monitor` restart — check `bridge_monitor.admin status`
  heartbeat and that outbound collection resumed next cycle.
- Re-render website: `scripts/ops/render-website.sh` (static; no service).

**Step 6 — fleet verification.**
Head agreement all hosts; `messaging/stats` identical totals on the two
highest-value pairs (hub vs each follower); a read pass of the messaging
endpoints; alert log review. Only after this may `dm_key` publication be
scheduled — DM envelopes can only seal once the proposer admits them
(hub is last), so the gate holds structurally until step 5 completes.

## Stop conditions (any → halt, do not continue to next host)

- Node process crash-loops or fails to re-catch head within ~5 min.
- `index_lag_blocks` non-decreasing after rpc restart (> ~10 min).
- Head hash divergence vs hub after catch-up (fork suspicion).
- Alert log entries attributable to the restart.
- Any `dm`-kind envelope observed in the index during the rollout
  (premature DM traffic — pause and reassess the gate).

## Rollback (per step)

All index tables are additive-derived; there are no migrations — rollback
is checkout-revert + restart, no data surgery:

1. `cd /opt/aitbc && git checkout 15729e572` (previous running SHA).
2. Restart the same units on that host in the same order.
3. Re-run that host's checks. If a *completed* host must roll back after
   later hosts upgraded, roll back later hosts first.
4. If `dm`/`dm_key` envelopes were ever sealed before rollback (only
   possible after step 5 + a gate breach), old index code will surface
   them in forum aggregates — cosmetic mislabel, not corruption; the
   correct fix is re-upgrade, not data edits.

## Risk register

| risk | residual | owner | mitigation |
|---|---|---|---|
| ~90 s dead window on each node restart (devnet-observed) | low | operator | expected; monitor `ActiveEnterTimestamp`, don't double-restart |
| Old index mislabels `dm` rows after a post-DM rollback | low | operator | DM gate: no `dm_key` publish until all hosts on candidate; rollback = re-upgrade path |
| Digest mismatch alarms during mixed-code window | low | operator | compare digests only between fully-upgraded pairs |
| Explorer read errors against index mid-upgrade | low | — | devnet showed additive index reads; restart explorer after node+rpc per host |
| Bridge-monitor restart gap misses a deposit poll | low | operator | collector is ledger-first/idempotent; verify heartbeat post-restart |
| `checkpoint_digest` stays at empty-hash sentinel | open | follow-up row | observed in devnet (checkpoint_height 0); confirm arming threshold on fleet before relying on it in step-6 checks |

## Recommendation: **go-with-conditions**

Evidence: both upgrade orders rehearsed end-to-end on a scratch devnet at
the exact O→N pair; zero lost messages; index continuous through both
restart orders; `--wait` verified on both code versions; the riskiest
cell (new rpc serving a still-running old node) verified live; no
migrations, no env additions, no consensus/state_root changes. The fleet
already tolerates the checkout/process split.

Conditions: (a) restarts happen per the named lines above — nothing
implicit; (b) one host fully verified before the next starts; (c) hub
strictly last; (d) the `dm_key` gate holds until step 6; (e) if
`origin/main` moved past `0a4d4ab92` before execution, re-validate the
delta first.
