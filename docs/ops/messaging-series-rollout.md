# Messaging-series combined rollout plan

Release candidate: **`0a4d4ab92`** (MSG-8 Phase 1 + MSG-8e + MSG-15 +
BR-6c + wallet/exchange path changes). One maintenance wave, one pull per
host, one combined verification. This document is the plan only — rollout
decisions and any restart stay operator-named.

*Corrected by MSG-10b: running baselines per unit (reflog ×
`ActiveEnterTimestamp`), minimal restart set, authorization classes
quoted from the ledger, per-unit rollback targets.*

## Running baselines (re-read 16 Oct ~16:15 CEST)

The running SHA of a unit is the reflog entry in effect at its
`ActiveEnterTimestamp`, **not** the current checkout. Checkouts: node2 at
`0a4d4ab92`, the other four at `15729e572` — several units were restarted
onto newer code during the audit window.

| unit | node0 | node1 | node2 | hub | hub1 |
|---|---|---|---|---|---|
| `aitbc-blockchain-node` | `15729e572` 15:49 | `15729e572` 15:57 | `0a4d4ab92` 15:59 ✓ | `1bafeea3e` 07:27 | `1bafeea3e` 07:27 |
| `aitbc-blockchain-rpc` | `15729e572` 16:06 | `2f1dd9a65` 14:19 | `2f1dd9a65` 14:19 | `2f1dd9a65` 14:21 | `2f1dd9a65` 14:20 |
| `aitbc-blockchain-explorer` | `9100f875a` 11:13 | `1ada65b32` 09:23 | `1ada65b32` 09:25 | `d0e49ad1d` 01:50 | `bd10f1606` 08:58 |
| `aitbc-wallet` | `2f1dd9a65` 14:38 | `2f1dd9a65` 14:38 | `2f1dd9a65` 14:38 | `2f1dd9a65` 14:37 | `2f1dd9a65` 14:38 |
| `aitbc-exchange` | — | — | — | `2f1dd9a65` 14:37 | — |
| `aitbc-bridge-monitor` | — | — | — | `ec4acd1cb` 14:42 | — |

`15729e572` already contains MSG-8 Phase 1 (`18740325e`); `2f1dd9a65` does
not — the running rpc on four hosts cannot yet serve the DM routes, and
the running node processes on hub and hub1 predate the MSG-8 predicate.

## Required / optional / none (per-unit import diff vs `0a4d4ab92`)

**Required — 11 restarts:**

| unit | hosts | why |
|---|---|---|
| `aitbc-blockchain-node` | hub, hub1 | `1bafeea3e..0a4d4ab92` touches `aitbc/messaging.py` (predicate), `messaging_index.py`, `rpc/transactions.py` — MSG-8 admission/index. **Validators: named batch go.** |
| `aitbc-blockchain-rpc` | node1, node2, hub, hub1 | `2f1dd9a65..0a4d4ab92` adds the `/rpc/messaging/dm*` routes + index changes. Serial rpc-only restarts — **standing class.** |
| `aitbc-blockchain-explorer` | all five | every explorer SHA predates `routers/messages.py` (MSG-17 routes). Not in the standing classes — **named line per host** (EXPLORER-RESTART-1 precedent: serial, verify each). |

**Optional — pick up at the next natural restart (0 required):**
`aitbc-wallet` ×5, `aitbc-exchange`, `aitbc-bridge-monitor`. Their diffs
(`bridge_db.py`, `exchange.py`, `bridge_monitor/{main,storage}.py`) are
the DATA-LAYOUT-2 default flip + a warning log — runtime-identical where
`BRIDGE_DEPOSITS_DB` is set in the env, and it is set fleet-wide
(`/etc/aitbc/blockchain.env`, verified on all hosts).

**None:** `aitbc-blockchain-node` on node0/node1 (running `15729e572` —
`15729e572..0a4d4ab92` touches only client-side `aitbc/messaging_client.py`
+ `aitbc/dm_client.py`, which nothing under `apps/` imports), node2
(already on `0a4d4ab92`); `aitbc-blockchain-rpc` on node0 (`15729e572`,
same reasoning); coordinator-api, agent-coordinator, event-bridge,
monitoring (no files in delta); CLI/SDK/MCP and
`scripts/ops/bridge_outbound_collect.py` (no service or timer runs it —
pull-only, picks up at next invocation); website (re-render only).

**Count: 11 required restarts, down from the 22 in the first plan**
(−5 wallet, −1 exchange, −1 bridge-monitor as pull-only; −2 node and −1
rpc that are already current).

## Authorization classes

Quoted from `TOPOLOGY/2026-10-16-morning-pull-restart-ledger.md` and
`AGENTS.md`:

- **Pulls** — covered: "the standing pull authorization" (workspace
  AGENTS.md: nodes pull/fast-forward routinely).
- **Serial rpc-only restarts after rpc-code pulls** — standing class:
  "falls in the standing serial rpc-restart class" (ledger, 09:02–09:06).
- **Follower restarts one at a time** — standing.
- **Monitoring reloads/restarts** — standing.
- **Validator node-process restarts** — "need a named batch"
  (ledger, 07:25–07:27 row): one go per named batch.
- **Explorer restarts** — no standing class; EXPLORER-RESTART-1 was a
  named line ("node0, then node1, then node2, serial, director verifies
  each before the next"). Treat as named-per-host.

Restart lines sorted by class:

| class | lines | authorization needed |
|---|---|---|
| covered — serial rpc restarts | rpc: node1 → node2 → hub1 → hub (serial, one at a time) | none — standing |
| covered — pull | `git merge --ff-only 0a4d4ab92` ×5 | none — standing |
| needs named batch go | node: hub1 + hub (validator batch) | one go naming both |
| needs named line per host | explorer ×5 (serial, verify each) | named line(s) |

## Sequence

**Step 0 — pull (all hosts, any order).**
`cd /opt/aitbc && git fetch origin && git merge --ff-only 0a4d4ab92`
(on node2: checkout already there — confirm with `git rev-parse HEAD`).

**Step 1 — rpc on the four stale hosts, serial:**
node1 → node2 → hub1 → hub, one at a time.
Checks each: `MainPID`/`ActiveEnterTimestamp` new; `GET /rpc/head` ok;
`/rpc/messaging/stats` lag → 0; `/rpc/messaging/dm-keys/{addr}` 404
cleanly (endpoint live). Standing class — no additional lines needed.

**Step 2 — explorer on all five, serial, verify each:**
node0 → node1 → node2 → hub1 → hub (order can follow the
EXPLORER-RESTART-1 precedent). Checks: `MainPID` new; `/messages` API
returns rows. Needs the named line(s).

**Step 3 — validator node batch (hub1 + hub), named go.**
hub1 first (demoted follower, lowest risk), verify, then hub (proposer —
block production pauses for the restart; expect ~90 s before first
proposal — observed in devnet, do not alarm inside that window).
Checks each: `MainPID` new; head resumes/catches up vs the fleet ±1;
no crash loop.

**Step 4 — fleet verification.**
Head-hash agreement all hosts; `messaging/stats` totals equal on
fully-upgraded pairs; dm-routes live on all rpc; alert log clean.
The `dm_key`/`dm` gate holds structurally until hub's node is upgraded
(proposer admits the kinds) — DM traffic stays parked until step 4
verifies all hosts on candidate.

## Stop conditions (any → halt)

- Node process crash-loops or fails to re-catch head within ~5 min.
- `index_lag_blocks` non-decreasing > ~10 min after an rpc restart.
- Head-hash divergence after catch-up (fork suspicion).
- Alert-log entries attributable to a restart.
- Any `dm`-kind envelope in the index before step 4 (premature gate
  breach — pause and reassess).

## Rollback (per unit)

Checkouts on live hosts track `main`. Roll a unit back by detaching the
checkout onto that unit's **previous running SHA** and restarting only
that unit — use `git checkout --detach <sha>`, which refuses to run over
conflicting local changes (hub's checkout carries a local edit to
`website/messages.html`; `reset --hard` is reserved for the IDE clone
and must not run on a live checkout). After the rollback verify, return
the checkout to `main` before any next pull: `git checkout main &&
git merge --ff-only origin/main`. A detached checkout only breaks pulls
if you forget that return step — include it in the rollback line itself.

| unit → previous running SHA | hosts | command shape |
|---|---|---|
| node → `1bafeea3e` | hub, hub1 | `git checkout --detach 1bafeea3e`, restart `aitbc-blockchain-node`, verify, then `git checkout main && git merge --ff-only origin/main` |
| rpc → `2f1dd9a65` | node1, node2, hub, hub1 | same detach/return shape, restart `aitbc-blockchain-rpc` only — **an rpc rollback needs no node restart** (the node process never depended on rpc code) |
| explorer → its own previous SHA | node0 `9100f875a`, node1/node2 `1ada65b32`, hub `d0e49ad1d`, hub1 `bd10f1606` | same, restart `aitbc-blockchain-explorer` only |

If `dm`/`dm_key` envelopes were sealed before a rollback (only possible
after hub's node is upgraded + gate breach), old index code surfaces them
in forum aggregates — cosmetic mislabel, not corruption; re-upgrade, do
not edit data.

## Risk register

| risk | residual | owner | mitigation |
|---|---|---|---|
| ~90 s dead window on hub node restart (devnet-observed; production pauses block production) | medium | operator | hub last inside the batch; monitor `ActiveEnterTimestamp`; don't double-restart |
| Old index mislabels `dm` rows after a post-DM rollback | low | operator | DM gate until step 4; rollback = re-upgrade |
| Digest mismatch alarms mid-rollout | low | operator | compare digests only between fully-upgraded pairs |
| Explorer read errors mid-upgrade | low | — | additive index reads; explorer serial after rpc |
| MSG-8f absent from candidate: stale `<name>.tmp` wedge in `dm_store_save` + no `fsync` — a crash between temp create and rename blocks later saves with `FileExistsError` | open | future DM row | parked deliberately; fails safe (nothing lost/published); fix = drop `O_EXCL` or unlink stale temp + `fsync` before `os.replace` |
| `checkpoint_digest` stays at empty-hash sentinel (`checkpoint_height: 0`) | open | follow-up row | observed in devnet; confirm arming threshold on the fleet before relying on it in step-4 checks |

## Recommendation: **go-with-conditions** (unchanged)

Evidence stands: both upgrade orders rehearsed end-to-end on a scratch
devnet at the exact O→N pair; zero lost messages; index continuous; the
riskiest cell (new rpc serving a running old node) verified live; no
migrations, no env additions, no consensus/`state_root` changes. The
corrected baseline reduces the blast radius (11 restarts, only one
validator-batch go) without weakening the gates.

Conditions: (a) pulls + serial rpc restarts under standing classes;
explorer per-host lines and the validator node batch named as above;
(b) one unit fully verified before the next on each host; (c) hub's node
strictly last; (d) the `dm_key` gate holds until step 4; (e) re-verify
the running-SHA table at execution time — the fleet restarted several
units during this audit; if any running SHA moved, recompute that row's
diff before naming it.
