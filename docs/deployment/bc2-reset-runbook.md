# bc-2 Reset Runbook

Status: **plan only.** Nothing here is authorized, scheduled, or run. The
window is an operator field — "within about two weeks" (operator, 20 Oct),
no date named. Every fleet-affecting step is a named gate; the gate classes
below come from the AGENTS.md live-ops rules and are restated, not relaxed.

Companion documents (values live there, not restated here):
`bc2-environment-set.md` (per-unit env names + node0 pins),
`bc2-consumers.md` (everything outside env that assumes the old chain),
`bc2-drain-checklist.md` (drain order; produced by `RESET-DRAIN-1` — may
not be merged yet), `GATES.md` (why every gate height is `1`).

## Gate wording and evidence rules

Classes used in this document:

- **operator-named** — the operator's own message naming the action; for
  validator-interrupting steps (node/p2p units on hub, hub1, node1, node2)
  it also names the hosts. Words relayed by anyone else do not authorize.
  The ledger quotes the operator's line verbatim. This document describes
  the class of line each step needs; it contains no ready-made go phrase.
- **standing** — pulls, serial rpc-only restarts, the bridge-repair class.
- **per-item word** — deletions of operator-staged paths (`.pre-reset`
  copies, offline backups); each removal waits for its own word.
- **ungated** — reads.

Restart evidence is `ActiveEnterTimestamp`, `ExecMainStartTimestamp`, and a
new `MainPID` — `NRestarts` does not count manual restarts. Fresh-start
detection: if a unit's timestamp is newer than the baseline recorded for
that run, a prior run already completed — stop and report; do not restart
again.

## Timings key

Every duration carries one label: **measured** (journal timestamp; ledger
line cited), **estimate**, or **unmeasured**. The rehearsal numbers bound
the chain-formation phase only; nothing here is a downtime budget.

## A. Preconditions — critical path, in order

| # | item | who names it | read-only verify | state |
|---|---|---|---|---|
| A1 | v1 key rotation confirmed complete **at least 3 days before the freeze** (operator card) — the genesis build, root check and rehearsal 4 then run on the real addresses | operator | operator states done; post-rotation addresses exist for every role in `bc2-environment-set.md` "Operator-decision names" | open; blocks the genesis cut |
| A2 | allocation file + address list | operator | file parses; totals match the operator's final figures — working figures: treasury 100M AIT (36,000,000 units/AIT), 256 AIT floats outside it, 11 service ×1 AIT, 3 retired ×0, faucet 0 (plan, operator card answers 19 Oct); bond accounts ×2 at 0 (`bc2-environment-set.md` harness requirement) | working figures exist; final numbers are the operator's |
| A3 | drain executed | operator, per item | the drain **actions** — escrow refunds, the gap57 proposal, coin-request dispositions, Sepolia ledger reconciliation — run **days before the window** as operator-named steps per `bc2-drain-checklist.md`; the **zero-check reads** run again after the freeze (B5) and any new row found there is a new drain item that stops the cut | open |
| A4 | `RESET-ROLLBACK-1` rehearsed | director schedules once this document exists | rehearsal ledger green against §E's acceptance list | **not run** — its ledger is a header stub |
| A5 | `RESET-REHEARSAL-4` run — one final harness run on node2 at the release-candidate commit after this document, `RESET-ENV-NODE0-1`, `RESET-DRAIN-1` and `GAP-GENESIS-INIT-1` land (operator: "Yes, one final run"; registered parked row) | director schedules | rehearsal ledger green | registered, not run |
| A6 | genesis write path | decided (card 20 Oct): "Scratch path is enough" — scratch build + `verify-genesis-root.py` + named per-host distribution; `RESET-GENESIS-LIVE-1` is not a blocker and stays parked | decided |
| A7 | reset release commit named; diff-audit deployed→release | director | audit lists every runtime-visible change under unchanged env (see "First window action — code convergence") | open |
| A8 | offline backups + `.pre-reset` capacity | operator-named for the copies | sizes below; checksums verified against live files | sized; copies not made |
| A9 | consumer changes staged not live | repo | `bc2-consumers.md` rows ready: v9 alert removal staged, `WEBSITE_CHAIN_ID=bc-2` line prepared, `BACKUP_GOOD_CHAIN_GLOB` value prepared | staged per consumers doc |
| A10 | public maintenance notice live **about 3 days ahead** of the window (operator card; publishes only on his word; comes down after the first seal — §D) | operator-named | notice page serves the window text | drafted (`tasks/CHAIN-RESET-NOTICE-DRAFT.md`), unpublished |
| A11 | capacity re-check at freeze | ungated | fresh `df`/`du` per host at freeze time (today's reads below drift) | read once today |
| A12 | window named | operator | — | blank field — decided placement: "After rehearsal 4" (card 20 Oct); the ≥3-day rotation lead (A1) and the ~3-day notice lead (A10) count back from it |

### A8/A11 host sizes — measured (read-only `du`/`df`, 2026-10-20 ~07:03 CEST, per-host `date` reads recorded in the ledger)

| host | root free | `/var/lib/aitbc/data` | old-chain dir | `.pre-reset` copy fits? |
|---|---|---|---|---|
| hub | 362 G | 375 M | 351 M | yes |
| hub1 | **13 G** | 304 M | 297 M | yes (the tightest; re-read at freeze) |
| node0 | 7.8 T | 534 M | 524 M | yes |
| node1 | 7.8 T | 393 M | 384 M | yes |
| node2 | 7.8 T | 428 M | 383 M | yes |

Offline copies land in `/home/oib/windsurf/aitbc/backups` (700/600); the
fleet total is ~2 G — capacity is not a constraint, checksum verification
is the gate.

## First window action — code convergence

The fleet is **not** fast-forwarded before the cut; the reset release
deploys **with** the cut (operator ruling). The fast-forward is therefore
the **first action inside the window**, not a step days ahead:

- Fast-forward every host's `/opt/aitbc` to the named reset commit —
  **operator-named** (this *is* the deploy of the reset release, not a
  routine pull), **no restart**. Working tree only; record the new HEAD
  against each unit's `ExecMainStartTimestamp` so a later restart is
  attributable to the new code.

Rule for the gap between that step and the env flip — both inside the
window: a service that restarts on a not-yet-cut host runs the new code
against the old chain. Per the release contents to date (the A7 diff-audit
re-verifies this at cut time — a consensus-path change landing before the
cut voids the first row):

| unit | safe to restart pre-cut? | evidence |
|---|---|---|
| `aitbc-blockchain-node` | yes, if A7 shows zero consensus diff | config-only collapse: every gate resolves from env; known node changes are removal-of-paths (`d9da6967c` genesis RPC bootstrap — irrelevant to a chain with a block 0; `fd6b5e95f` prefers `CHAIN_ID` — identical when it matches `SUPPORTED_CHAINS`; `bb9dcc2ad` refuses only when `CHAIN_ID` is unset — fleet pins it) |
| `aitbc-blockchain-rpc` | yes — tighter, never looser | retired bodies and removed unsigned routes refuse where flag-on code already refused (`47f3d85bd`, `166885512`, replay-guard series); callers see the same 410s |
| `aitbc-blockchain-p2p` | **conditional** | `25f162a00`: the wrapper now honours `P2P_BIND_PORT`/`P2P_BIND_HOST` (old binary hardcoded 7070/0.0.0.0). If a host's env pins different values, a restart **rebinds a different socket** — verify the env value equals 7070/0.0.0.0 before any p2p restart |
| `aitbc-coordinator-api` | **conditional** | `ExecStartPre` runs `alembic upgrade head` — a restart auto-migrates the **old** service DB if the release adds revisions; the A7 audit must diff alembic heads |
| other services | yes, pending A7 | they read env at start; no service-runtime changes are in the release to date |

Auto-restart trap: `Restart=`/`WatchdogSec=` act without a named line — a
crash-looping unit restarts on the new code silently (hub's
`aitbc-coordinator-api` carries `Restart=on-failure`, one of the two
conditional rows above; hub1's `aitbc-blockchain-p2p` unit shows no
`Restart=` line in the unit as read 20 Oct). The same verdicts apply
wherever a unit does auto-restart.

An earlier fast-forward would stretch this gap to days and make the table
above apply for days; the operator has not chosen that.

## B. Freeze — stop accepting writes, in order

Each step is **operator-named** (env flips and service stops); each ends
with an **ungated** verify read.

| # | action | class | verify read |
|---|---|---|---|
| B1 | faucet + coin-request intake paused | operator-named | faucet/route returns paused; `agent_coin_requests`/`hermes_coin_requests` accept no new PENDING rows |
| B2 | market + exchange order intake stopped | operator-named | order routes refuse; no new rows |
| B3 | `BRIDGE_LOCKS_PAUSED=true` (env edit + restart) | operator-named | `grep '^BRIDGE_LOCKS_PAUSED' /etc/aitbc/<env>`; lock route refuses 503. Decided: the new chain launches paused too — C3 writes `true`; the unpause waits for `SEPOLIA-REDEPLOY-1` |
| B4 | escrow creation stopped | operator-named | lock route refuses new escrows |
| B5 | record heads + roots **and re-run the drain zero-checks** | ungated | `sqlite3 "file:///var/lib/aitbc/data/<chain>/chain.db?mode=ro" "SELECT max(height), hash FROM block"` on all five — all equal; head hash + `state_root` written to the ledger. Plus the `bc2-drain-checklist.md` zero-check reads re-run here — a row that appeared since A3 is a **new drain item and stops the cut** |

Timing: unmeasured (window is D7-tolerant — "a day or more is fine", D7).

## C. Cut — per host class, in order

Host classes: **hub** (proposer + coordinator/exchange/wallet/governance/
bridge-monitor/prometheus/website/nginx), **hub1, node1, node2**
(proposers + follower services), **node0** (customer follower,
non-validator — always last).

| # | action | class | verify (read-only) | rehearsed as | timing |
|---|---|---|---|---|---|
| C1 | stop services in dependency order: customer-facing → coordinator/exchange/market → rpc → node/p2p last | operator-named; node/p2p stops on hub/hub1/node1/node2 are validator-interrupting | `systemctl is-active` inactive; timestamp fields recorded | — | unmeasured |
| C2 | move every chain + service store to dated `.pre-reset` copies (no deletion) | operator-named per host | `du -s` copy equals source; `.pre-reset` dir listing | — | unmeasured (sizes in A8) |
| C3 | apply the env set on every unit | operator-named | anchored `grep` of each name in `bc2-environment-set.md`; node0 pins per `RESET-ENV-NODE0-1` (#323). Decided values on all five: `BRIDGE_LOCKS_PAUSED=true` (stays paused until `SEPOLIA-REDEPLOY-1`), `TRUSTED_PROPOSERS=genesis,<the four post-rotation validator addresses>`, `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=256` | — | unmeasured (~101 chain-id assignments across five hosts) |
| C4 | build genesis on scratch → `verify-genesis-root.py` → distribute `genesis.json` into `data/bc-2/` on **all five** hosts | build/verify ungated (scratch); distribution operator-named (live data-dir writes) | per-host `sha256sum` equals the verified build output | `rehearsal.py genesis` (REHEARSAL-3) | estimate 20–90 s |
| C5 | node units: **the rehearsed shape — all four validator node units up inside one short window**, then followers, node0 last. A serial "catch-up proof between hosts" has nothing to prove at height 0: with attestation minimum 2 and file-loaded block 0, no block can seal until a second validator is up — so validators start together as rehearsed, and the rejoin proof happens **after** sealing begins (stop one validator, watch it catch up — rehearsed `rejoin`). **Before the first unit starts:** `TRUSTED_PROPOSERS` on every host resolves to `genesis` plus the four genesis validator addresses — the membership check then governs every imported block. The first produced block lands shortly after the second validator is up — **that first seal is §D's point of no return, inside this step** | operator-named, validator-interrupting per host | `node.log` shows `Successfully created genesis block from genesis.json` exactly once and `Initializing databases for chains: ['bc-2']` per host; heads advancing | `up`, `wait`, `check`, `rejoin`, `skip` | **measured:** `up` ~11 s for all five units (journal 05:47:36→~47); rejoin-catch-up ~1.4 m (journal 05:53:49→05:55:03); fleet window 9 m 46 s (journal 05:47:36→05:57:22, REHEARSAL-3 ledger) |
| C6 | rpc units + service stores fresh | rpc restarts standing; other first-starts operator-named | `GOSSIP_BACKEND=redis` on rpc units (env-set); coordinator 170 tables, trading 11 (rehearsal counts); `peer_keys.db` re-enrollment for issued-key joiners | `stores` | estimate ~1.25 m incl. golden (REHEARSAL-3 estimate) |
| C7 | checks (below) | ungated | per check | `check` + quorum sweep | estimate ~15 s for the whole check phase (REHEARSAL-3 ledger) |

C4 detail — how the file reaches the live data dirs: the builder writes
**only** under a declared scratch root; `--live` evaluates the reset-day
preconditions and then always refuses the write ("designed, not enabled").
The proven path is scratch build → `verify-genesis-root.py` → per-host file
copy into `data/bc-2/genesis.json` (a gated live-dir write, same class as
C2/C3). Whether `RESET-GENESIS-LIVE-1` (enabling `--live`) is a real
blocker or the scratch+verify+distribute path suffices is an operator
decided ("Scratch path is enough", card 20 Oct): `RESET-GENESIS-LIVE-1`
(enabling `--live`) is not a blocker and stays parked; rehearsal evidence
is that scratch build + verify + distribution produced byte-identical
genesis on all five instances.
`aitbc genesis init` hard-stops with a pointer to this builder
(`GAP-GENESIS-INIT-1`, #322), so no other write path exists to bypass.

C3 detail — the decided bridge-pause value: `BRIDGE_LOCKS_PAUSED` is an
**admission-side** gate (`config.py`: the `initiate_transfer` chokepoint
raises before any lock envelope is signed, so no valid lock reaches the
mempool; the RPC surfaces answer 503). It is not a consensus check — a
lock already in the mempool still seals, and confirm/refund/status paths
are untouched — but the decided value `true` is written **uniformly on all
five hosts'** node envs so no host's lock surface opens early. The flip on
bc-2 is part of the C3 env apply (**operator-named** per host); the
unpause after `SEPOLIA-REDEPLOY-1` is a separate gated env-edit-plus-
restart outside this runbook.

C7 checks: five heads equal and advancing; all four proposers sealing in
rotation (`SELECT DISTINCT proposer FROM block WHERE height>0`);
attestation quorum ≥2 on **every** produced block (the sweep: per height,
`len(json.loads(block_metadata)["attestations"]) >= 2` — rehearsed 8/8);
rpc + explorer + website + bridge read paths answer for `bc-2`; alerts
quiet.

## D. Point of no return — the first block sealed on bc-2

"Sealed" means a block **above height 0 produced by a proposer** and
recorded with its attestations. Block 0 is file-loaded at node start and
sits **before** the point — a fleet that has only file-loaded genesis has
committed nothing.

| reached | abort action | cost |
|---|---|---|
| freeze only (§B) | unpause every intake | drain settlements already made stand — they were owed; downtime only |
| C1 services stopped | restart old env/units | downtime only |
| C2 stores moved | **move `.pre-reset` copies back first** — a bare restart finds empty dirs and re-genesises | a named move-back step per host, then restart |
| C3 env applied | revert env edits | env edit + restart per unit |
| C4 genesis distributed | delete `data/bc-2/` files | per-host file removal; the old chain's dir is untouched by construction |
| C5 units started, nothing sealed yet (e.g. only one validator up) | stop the started units, delete `data/bc-2/` files, revert env, then the earlier rows | prove nothing sealed: `max(height)=0` on every started host's `bc-2` chain.db — nothing produced, nothing to abandon |
| C5+ first seal | — | **the point**: abandoning bc-2 is a second reset-class event, not an abort |

After the point, never before: unfreeze writes, market/exchange reopen,
website maintenance notice taken down. The bridge-lock unpause is **not**
in this list — decided: locks stay paused until `SEPOLIA-REDEPLOY-1`
(operator placed the redeploy "in the week after the cut"), a separate
gated step outside the cut.

## E. Rollback before the point — **unproven until `RESET-ROLLBACK-1`**

Venue decided: the node2 scratch harness (operator card). The acceptance
list below is written so it runs on the harness; what it cannot prove on
live data is listed as residual, not as a blocker.

Acceptance list that rehearsal must prove (the director writes its prompt
from this):

1. Every cut step §C is reverted individually and in order — on the
   harness: file-load, `.pre-reset`-style store moves, env swaps, and
   serial unit stops/starts on the five scratch instances.
2. Byte-equal restore verified from **both** the moved-aside copies and a
   separate backup copy (checksum compare against values recorded before
   the cut).
3. The move-back is an explicit named step — the trap is a bare restart
   finding empty dirs and re-genesis-ing the old id.
4. Restart evidence uses `ActiveEnterTimestamp`/`ExecMainStartTimestamp`/
   new `MainPID`; the fresh-start detection rule is exercised.
5. The old chain resumes at the frozen head with the same head hash
   recorded at B5.

Residual the harness cannot prove (accepted, not blocking): real systemd
units vs transient scopes, real data-dir sizes (304–534 M vs scratch MB),
live-path writes under `/var/lib/aitbc` (the harness writes only under
`AITBC_RESET_SCRATCH`), and the five-host serial order.

## F. After the reset

Soak; consumer changes go live per `bc2-consumers.md` (v9 alert removal,
`WEBSITE_CHAIN_ID=bc-2` render, `BACKUP_GOOD_CHAIN_GLOB`, genesis-builder
refusal-list addition); the register and ledgers keep old heights as
history; the bridge-lock unpause lands with `SEPOLIA-REDEPLOY-1`
(operator: "in the week after the cut") as its own gated step, not part of
this document; write the reset record in `TOPOLOGY/`; `.pre-reset` copies
and offline backups retire **≥7 days later, per-item operator word**.

Post-reset operating rule (decided): `TRUSTED_PROPOSERS` is set. Any later
validator-set change must update the list on **every host in the same
change** — the membership check governs every imported block, so a
proposer not yet in the list has its blocks refused fleet-wide.

## G. Not rehearsed — planned, not proven

Real systemd units vs transient `systemd-run` services; the ~101 chain-id
env edits across five hosts; the five-host spread (rehearsal was one
host, five instances — the simultaneous four-validator start *is* the
rehearsed shape; five separate hosts are not); offline backups; drain
writes; hub1's 13 G root disk under real copies; node0 as a non-validator
customer follower; live service-store fresh starts; the website render on
hub.

`RESET-REHEARSAL-4` (A5) re-runs the same harness scope at the
release-candidate commit — it covers everything the earlier rehearsals
proved, on the exact reset code; it does not shrink this residual list.

## H. Gate table

| step | who names it | evidence to record |
|---|---|---|
| ff to reset commit (first window action) | operator-named — the reset-release deploy | per-host `git rev-parse HEAD` + `ExecMainStartTimestamp` baseline |
| freeze B1–B4 | operator-named | operator line verbatim + refuse-read outputs |
| B5 head record | ungated | 5× head+hash+state_root in ledger |
| C1 stops | operator-named (validator-interrupting on 4 hosts) | operator line verbatim; `is-active` + timestamp fields |
| C2 `.pre-reset` | operator-named per host | `du -s` pairs per store |
| C3 env apply | operator-named per host | anchored greps per env-set |
| C4 genesis | ungated build; operator-named distribution | builder verdict + verify output + 5× sha256 |
| C5 node starts | operator-named per host (validator-interrupting) | file-load line ×1, resolved-id line, timestamp fields |
| C6 rpc + stores | rpc standing; stores operator-named | table counts, redis-backend evidence |
| C7 checks | ungated | heads, proposer set, per-block quorum sweep, read-path results |
| post-PONR unfreeze | operator-named | operator line verbatim + accept-read outputs |
| `.pre-reset` deletion | per-item word, ≥7 d | operator line verbatim per item |

## I. Decisions

Taken (operator card, 20 Oct — answers in his words):

| item | answer | carried into |
|---|---|---|
| `TRUSTED_PROPOSERS` | "Set it" — `genesis` plus the four post-rotation validator addresses | C3/C5 check + post-reset operating rule in §F |
| `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` | "256 on all five" | C3 decided value (the env-set doc line still reads "recommended" — a separate row updates it) |
| bridge locks after the cut | "Stay paused until redeploy" (redeploy placed "in the week after the cut") | B3, C3 decided value, §D/§F notes — `BRIDGE_LOCKS_PAUSED=true` launches with bc-2; unpause is a separate gated step after `SEPOLIA-REDEPLOY-1` |
| rollback rehearsal venue | "node2 scratch harness" | §E acceptance list + residual |
| node0 `STATE_SYNC_MAX_GAP` | `-1` (fleet value) | `RESET-ENV-NODE0-1` (#323) |
| v1 key rotation timing | "at least 3 days before the freeze" | A1 |
| public maintenance notice | "about 3 days ahead" of the window | A10, §D |
| final rehearsal | "Yes, one final run" → `RESET-REHEARSAL-4` | A5, §G |
| node start order | "Short simultaneous start" | C5 |
| deploy timing | "First step of the window" | "First window action — code convergence" |
| genesis write path | "Scratch path is enough" | A6, C4 — `RESET-GENESIS-LIVE-1` parked, not a blocker |
| window placement | "After rehearsal 4" | A12 |

The env-set rows that still contradict the decided values
(`BRIDGE_LOCKS_PAUSED` shown `false`, the gossip cap shown "recommended",
`TRUSTED_PROPOSERS` shown set-or-unset) are `RESET-ENV-DECIDED-1` (#325,
coder B) — not edited here.

Still owed (recommendation + cost; nothing picked):

| decision | recommendation | cost of the recommendation |
|---|---|---|
| `.pre-reset` deletion | keep ≥7 days, per-item word | disk (≤534 M/host — trivial except watched on hub1) |
