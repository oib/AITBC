# Proposer failover runbook — promoting hub1 to hub/proposer (drill plan)

> Companion to [failover-runbook.md](failover-runbook.md). That drill
> proved the public read-path flip (hub's nginx → hub1) in ~2 minutes
> with zero traffic gap. This document describes the **heavier** move:
> hub1 becoming the island hub and block proposer when hub is lost.
> Docs and drill plan only — every mutating step needs the operator's
> own typed line on the day. Not rehearsed yet.

## Scope and the honest shape of it

The nginx flip moves *where public reads answer from*. A proposer
failover moves *which host runs the hub role*: block production
leadership, coordinator-api, agent-coordinator, market, api-gateway,
exchange, bridge-monitor, event-bridge, mempool submit paths, and the
`HUB_*` URLs every follower resolves.

Consensus does **not** need to move for the chain to survive hub loss:
hub1 is already a PBFT-style validator with its own
`PROPOSER_ID`/`PROPOSER_KEY`/`VALIDATOR_KEYS` and
`ENABLE_BLOCK_PRODUCTION=true`, and the four-validator set keeps
producing 3-of-4 blocks while hub is down (one extra round window per
hub-owned slot). Promotion is therefore mostly **service and URL
rewiring**, not a consensus rescue — but it touches store files
(`bridge_deposits`, coin_requests, market, coordinator DBs) that the
read-path drill deliberately left behind.

## Preconditions

| check | pass condition |
|---|---|
| hub confirmed down or deliberately demoted | no split-brain: hub must not keep producing/serving hub services while hub1 is promoted |
| heads equal on all four validators | same height+hash on hub1/node1/node2 (hub read if reachable); any fork healed via the deterministic fork-choice + delta-journal machinery first |
| hub1 soak | unit clocks at the accepted baseline; `oom_kill` 0; 0 failed `aitbc-*` units; 8 active + 2 keep-off |
| `VALIDATOR_SET` | identical on all hosts; hub1's own `PROPOSER_ID`/`PROPOSER_KEY`/`VALIDATOR_KEYS` present only in hub1's `validator-secrets.env` (last env file wins) |
| `TRUSTED_PROPOSERS` | unchanged — hub1 is already in the set; a validator-set *change* would need the same edit on every host in one change |
| sync direction | every follower's `DEFAULT_PEER_RPC_URL`/`CHAIN_SYNC_SOURCES` retargetable; hub1's own sync source must point at a *peer* (node1/node2), never itself |
| data stores | decision recorded per store: re-snapshot `bridge_deposits.db` and coin_requests/market/coordinator DBs from hub, or accept divergence (bridge deposits re-snapshot was already marked required for a real cut) |
| funding | bridge payout float on hub1 (`BRIDGE_PAYOUT_*`, different account than hub's) sized for payouts; `BRIDGE_FUNDING_SOURCES` reviewed |
| alerting | hub1 prometheus/alert rules cover the promoted hub's services |

## PBFT 3-of-4 rules that bound the drill

- Every block needs proposer signature + `MULTI_VALIDATOR_MIN_ATTESTATIONS=2`
  remote attestations; the proposer cannot self-attest. **3 of 4
  validators must stay mutually reachable.**
- One validator down: chain continues (~1 extra round window per
  owned height). Two down or a clean partition: production **stalls,
  no fork**.
- Forks only from asymmetric partitions; deterministic fork choice
  (branch weight → length → (round, hash)) plus the delta journal
  heals on rejoin; pre-journal-era forks take the manual
  delete-and-`sync_cli` repair.
- Attestation lock is per-round in-memory: a restarted validator
  refuses to double-sign a round it already attested — restart
  sequences still go through the no-prod drop-in ritual below.
- **Restart/rejoin ritual (every validator restart):** write a runtime
  drop-in `/run/aitbc/no-prod.env` (`ENABLE_BLOCK_PRODUCTION=false`) +
  `no-prod.conf` `[Service] EnvironmentFile=…` — bare `Environment=`
  lines do not win over env files — restart, verify
  `/proc/<MainPID>/environ`, wait for head height+hash to match a
  peer, then remove drop-in+env, daemon-reload, restart again.

## Promote steps (hub1 follower → hub)

1. **Freeze/quiesce hub** (if alive): stop hub services serving writes;
   take final store snapshots (`bridge_deposits.db`, coordinator,
   market, coin_requests). If hub is dead, note last known head.
2. **Store transfer**: copy the snapshots to hub1's `DATA_DIR`
   locations for the services being promoted. This step is what makes
   the promotion non-reversible-cheap — bridge ledger rows must move
   verbatim (ledger-first payout rule).
3. **hub1 env flips** (`/etc/aitbc/*.env`, env edits = typed lines):
   - `BLOCKCHAIN_MODE=follower` → `hub` (node.env / blockchain.env)
   - `CHAIN_SYNC_SOURCES` / `DEFAULT_PEER_RPC_URL` → point hub1 at a
     peer (node1 or node2), never at itself
   - gossip: hub role uses `GOSSIP_BACKEND=redis` + broadcast wiring
     vs the follower's websocket mesh entries (`GOSSIP_*` lives only
     in `blockchain.env`)
   - hub service env files already exist on hub1 (exchange.env,
     coordinator, market, bridge-monitor with hub1's own payout
     `0xB195…` float) — verify each service's required names are set
4. **Service bring-up on hub1** in dependency order:
   `aitbc-blockchain-node` → `aitbc-blockchain-rpc` → `aitbc-blockchain-p2p`
   → `aitbc-coordinator-api` (alembic `ExecStartPre` — check journal if
   it fails) → `aitbc-api-gateway` → `aitbc-market` → `aitbc-agent-coordinator`
   → `aitbc-exchange` → `aitbc-blockchain-event-bridge` →
   `aitbc-bridge-monitor` → `aitbc-blockchain-explorer`. Each start:
   `is-active`, `/health` where it exists, journal tail.
5. **Follower retarget**: every follower's `HUB_*` URLs
   (`HUB_DISCOVERY_URL`, `HUB_RPC_URL`, `HUB_AGENT_URL`,
   `HUB_COORDINATOR_URL`, `HUB_BLOCKCHAIN_RPC_URL`, …) and
   `DEFAULT_PEER_RPC_URL`/`GOSSIP_MESH_PEER_URLS` point at hub1's
   public name — env edits + restarts, serial, one host at a time.
   (`is_hub_self()` hairpin: hub-ward URLs resolve to loopback on the
   new hub itself.)
6. **DNS/edge**: repoint the public `hub.` name at hub1 (or accept the
   new name fleet-wide). Consumer `HUB_RPC_URL` repoint on validators
   restarts them — sequence it after the set is stable.
7. **hub (if alive) demote**: flip it `BLOCKCHAIN_MODE=follower`,
   point its sync at hub1, stop hub-only services, apply the same
   no-prod drop-in ritual for any validator restart.

## Readback

- `/rpc/head` on every host: same height+hash; production resumes
  inside one round window after quorum (watch hub1's proposer logs —
  it already owns sorted `VALIDATOR_SET` slots).
- Public GETs on hub1's vhost for the previously flipped 9 paths +
  the hub-only STAY set (islands/chains/network-info must now answer
  *from hub1 as hub* — expected content changes role hub, not a bug).
- `failover-readback.sh` style UA-tagged read proving serving host.
- Service checks: coordinator-api `/health`, market, agent-coordinator
  metrics, bridge-monitor ledger tail (first payout row lands with
  hub1's payout float — balances minus committed rows).
- Escrow/settlement path: a refused-settlement probe on a follower
  still 503s with the hub hint (the hint now names hub1), and a
  settlement leg lands via hub1's mempool.
- Journal sweep: zero err-level lines on all validators for the
  promotion window.

## Revert

Promotion is revert-heavy — every step above has an inverse but the
stores make it expensive:

- If hub1 was promoted *while stores were copied forward* and hub
  returns quickly: reverse the env flips on both hosts
  (`BLOCKCHAIN_MODE`, sync sources, gossip wiring), stop hub1's hub
  services, re-sync hub1's chain db from a peer, re-copy any
  bridge/coordinator rows written on hub1 back to hub, restore
  follower `HUB_*` URLs, DNS back.
- If hub stays down longer, treat the promotion as the new topology
  and *don't* bounce back until a second planned window — flap is
  worse than one deliberate move.
- Consensus revert is never needed: hub1 produced under its own
  validator identity the whole time — no key moves happened.

## Deliberately not covered

- **No validator-set change** — hub1 is already a validator;
  `VALIDATOR_SET`, `TRUSTED_PROPOSERS`, `VALIDATOR_KEYS` untouched.
- **No key custody moves** — no private key is copied or moved
  anywhere; hub1 uses only its own proposer key. (Store DBs move;
  keys never do.)
- **No scope-B settlement/bridge float migration** beyond sizing the
  existing hub1 float — `BRIDGE_PAYOUT_*` keys stay per-host.
- **No wallet/key rotation, no genesis/treasury change** (#615
  glossary unchanged).
- **No node0 promotion** — it is a non-producing follower by role
  and stays one.
- **No bc-3/other-island work** — parked rows stay parked.
- **Automatic failover** — this runbook is the manual path; there is
  no leader-election automation to flip the hub role.

## Drill plan (every mutating step needs the operator's typed line)

Rehearsal order — same staged shape as drill R6 but longer:

| step | what | mutating? |
|---|---|---|
| P0 | preconditions table re-run (heads, clocks, oom, failed, canary, alerts) | read-only |
| P1 | snapshot hub stores read-only + copy to a hub1 staging dir (not into service paths) | copy only |
| P2 | hub1 env edits staged as diff files under a staging dir — no live apply | staging only |
| P3 | **typed line**: apply hub1 env flips (`BLOCKCHAIN_MODE`, sync, gossip) | yes |
| P4 | **typed line per service unit**: bring up hub1 hub services in the order above; ledger entry per unit | yes (restarts) |
| P5 | readback: heads, public GETs, UA-tagged serving-host proof, health checks | read-only |
| P6 | **typed line**: follower `HUB_*` retarget on one follower first, verify, then serial rest | yes (env+restarts) |
| P7 | **typed line**: DNS repoint | yes |
| P8 | settlement probe + bridge payout ledger check | read-only |
| P9 | hold window: watch heads/oom/alerts every ~10 min | read-only |
| P10 | revert plan armed: inverse env diffs staged; **typed line** to execute | yes |

Abort triggers: any hub1 unit failing to come up healthy after two
read-back checks, heads diverging, `oom_kill`, or the operator
stopping the drill — revert toward the pre-drill env diffs.

Coder: C
