# bc-2 Reset Runbook

Status: **plan only.** Nothing here is authorized, scheduled, or run. The
window is an operator field — "within about two weeks" (operator, 20 Oct),
no date named. Every fleet-affecting step is a named gate; the gate classes
below come from the AGENTS.md live-ops rules and are restated, not relaxed.

Companion documents (values live there, not restated here):
`bc2-environment-set.md` (per-unit env names + node0 pins),
`bc2-consumers.md` (everything outside env that assumes the old chain),
`bc2-drain-checklist.md` (drain order, `RESET-DRAIN-1`),
`bc2-host-inventory.md` (per-host unit lists, timers and store files —
C1 and C2 act on it),
`apps/blockchain-node/tests/golden/GATES.md` (why every gate height is `1`).

## Gate wording and evidence rules

Classes used in this document:

- **operator-named** — the operator's own message naming the action; for
  validator-interrupting steps (node units on hub, hub1, node1, node2,
  plus hub's `aitbc-blockchain-p2p` — the only p2p unit in the fleet)
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
| A1 | validator set for bc-2 — **decided (card 20 Oct): "No rotation for this reset"** ("this is not a v1 bc reset. after bc reset we are still on eth testnet"; the earlier "rotate, done ≥3 days before the freeze" answer is withdrawn). The bc-2 validator set is the four **current** validators (the set rotated in KR-5, `docs/releases/STATUS.md`) — no key task precedes the genesis build | operator confirms list | the four addresses match each host's live `VALIDATOR_SET`; a coder proposes the list, the operator confirms it | decided; address list outstanding |
| A2 | allocation file + address list | operator | file parses; totals match the operator's figures — **decided (card 20 Oct): "Confirmed final"**: treasury 100M AIT (36,000,000 units/AIT), 256 AIT floats outside it, 11 service ×1 AIT, 3 retired ×0, faucet 0, bond accounts ×2 at 0 — supply 100,000,256 AIT. Addresses: treasury "**New address, will supply**"; every other account "**Same as live today**" — a coder proposes the list, the operator confirms it | figures final; **both address lists outstanding** |
| A3 | drain executed | operator, per item | the drain **actions** — escrow refunds, the gap57 proposal, coin-request dispositions, Sepolia ledger reconciliation — run **days before the window** as operator-named steps per `bc2-drain-checklist.md`; the **zero-check reads** run again after the freeze (B5) and any new row found there is a new drain item that stops the cut | open |
| A4 | `RESET-ROLLBACK-1` rehearsed | done 20 Oct | rehearsal ledger green against §E's acceptance list | **rehearsed 20 Oct on the node2 scratch harness — green (§E)** |
| A5 | `RESET-REHEARSAL-4` run — one final harness run on node2 at the release-candidate commit; its document dependencies all landed (`GAP-GENESIS-INIT-1` #322, `RESET-ENV-NODE0-1` #323, `RESET-DRAIN-1`, this runbook) (operator: "Yes, one final run"; registered parked row) | director schedules | rehearsal ledger green | registered, not run — waits on the release-candidate commit |
| A6 | genesis write path | decided (card 20 Oct): "Scratch path is enough" — scratch build + `verify-genesis-root.py` + named per-host distribution; `RESET-GENESIS-LIVE-1` is not a blocker and stays parked | decided |
| A7 | reset release commit named; diff-audit deployed→release | director | audit lists every runtime-visible change under unchanged env (see "First window action — code convergence") | open |
| A8 | address lists proposed and confirmed | coder proposes, operator confirms | the four `bc-2` validator addresses match each host's live validator set; the allocation-address list names every allocation row's address (treasury the operator supplies, the rest "same as live today"). **Treasury ruling (20 Oct): a single-key address the operator creates off the fleet** — spendability is proven by a signed challenge (`check-alloc-file.py --treasury-proof`). Multisig is not possible on this chain without a consensus feature — ruled out, not discussed further | **done 20 Oct** — treasury `0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0` supplied off-fleet with a verified `personal_sign` proof; the final pair is committed at `docs/deployment/bc2-genesis/` (`allocations.json` sha256 `ca4a1500…`, `classes.json` `836ae037…`, both fully pinned in `tests/unit/test_bc2_genesis_files.py`); `check-alloc-file.py --classes --require-classes --treasury-proof` → all PASS |
| A9 | offline backups + `.pre-reset` capacity | operator-named for the copies | sizes below; checksums verified against live files; per-host store-file list in `bc2-host-inventory.md` | sized; copies not made |
| A10 | consumer changes staged not live | repo | `bc2-consumers.md` rows ready: v9 alert removal staged, `WEBSITE_CHAIN_ID=bc-2` line prepared, `BACKUP_GOOD_CHAIN_GLOB` value prepared | staged per consumers doc |
| A11 | public maintenance notice live **about 3 days ahead** of the window (operator card; publishes only on his word; comes down after the first seal — §D). Served on the hub website — a website session stages the text from `tasks/CHAIN-RESET-NOTICE-DRAFT.md` into the site rendered by `scripts/ops/render-website.sh` | operator-named | notice page serves the window text | drafted (`tasks/CHAIN-RESET-NOTICE-DRAFT.md`), unpublished |
| A12 | capacity re-check at freeze | ungated | fresh `df`/`du` per host at freeze time (today's reads below drift) | read once today |
| A13 | window named | operator | — | blank field — decided placement: "After rehearsal 4" (card 20 Oct); the ~3-day notice lead (A11) counts back from it |

### A9/A12 host sizes — measured (read-only `du`/`df`, 2026-10-20 ~07:03 CEST, per-host `date` reads recorded in the ledger)

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

- **FF1.** Fast-forward every host's `/opt/aitbc` to the named reset commit —
  **operator-named** (this *is* the deploy of the reset release, not a
  routine pull), **no restart**. Working tree only. Host order:
  **node0 → hub1 → node1 → node2 → hub** — canary on the largest
  range class without validator duty first, the proposer hub last so
  its mixed-code gap before the restart wave is shortest. Per host, in
  order:
  1. *before*: `git -C /opt/aitbc rev-parse HEAD`; `git -C /opt/aitbc
     status --short` must be empty; snapshot `systemctl show -p
     ActiveEnterTimestamp,MainPID` for every `aitbc-*` unit (the
     before/after sheet — a later restart is attributable to the new
     code by comparing `ExecMainStartTimestamp`/`MainPID` against it).
  2. `git fetch origin && git merge --ff-only <named commit>` — a
     dirty or non-fast-forwardable host is **skipped, not cleaned**:
     record its HEAD and the dirty paths in the window ledger and
     continue; a host left behind stays cut-eligible because every
     later step is per-host. Never `checkout`, `stash`, or `clean` on
     a host.
  3. *after*: `rev-parse HEAD` equals the named commit, `status
     --short` is still empty, and the unit PID/timestamp map is
     identical to the snapshot — a changed entry means that unit
     self-restarted onto new code; record it and treat the unit as
     governed by the restart table below.

Rule for the gap between that step and the env flip — both inside the
window: a service that restarts on a not-yet-cut host runs the new code
against the old chain. Per the release contents to date (the A7 diff-audit
re-verifies this at cut time — a consensus-path change landing before the
cut voids the first row):

| unit | safe to restart pre-cut? | evidence |
|---|---|---|
| `aitbc-blockchain-node` | yes, if A7 shows zero consensus diff | every gate resolves from env; the range now also touches `consensus/poa.py`, `consensus/pbft.py`, `genesis_builder.py`, `database.py`, `multi_chain_manager.py`, `cross_chain/settlement*.py` — not removal-of-paths only, so the A7 diff carries the verdict, not this cell |
| `aitbc-blockchain-rpc` | yes — tighter, never looser | retired bodies and removed unsigned routes refuse where flag-on code already refused (`47f3d85bd`, `166885512`, replay-guard series); callers see the same 410s |
| `aitbc-blockchain-p2p` — hub only (no such unit on hub1/node0/node1/node2) | **no** | verified 20 Oct: hub env pins `P2P_BIND_HOST=127.0.0.1` (port unset → wrapper default 7070). Old binary ignores the env and binds 0.0.0.0:7070; a restart on new code **rebinds to loopback and drops external gossip on the old chain** — the intended post-cut binding firing early. Do not restart this unit inside the gap |
| `aitbc-coordinator-api` | **conditional** | `ExecStartPre` runs `alembic upgrade head` — a restart auto-migrates the **old** service DB if the release adds revisions; zero new revisions in the range as of 20 Oct, but the A7 audit must diff alembic heads |
| other services | yes, pending A7 | they read env at start; the range now carries real `market_service`, `wallet_app`, `bridge_monitor`, and `coordinator_api` context diffs — A7 must justify per file, not by this blanket row |

Auto-restart trap: `Restart=`/`WatchdogSec=` act without a named line — a
crash-looping unit restarts on the new code silently (hub's
`aitbc-coordinator-api` carries `Restart=on-failure`, one of the two
conditional rows above; every `aitbc-blockchain-node` unit carries
`Restart=on-failure` on all five hosts as read 20 Oct — an `is-active`
result of `active` is therefore not proof of a clean start). The same
verdicts apply wherever a unit does auto-restart.

Timer caveat: "no restart" does not mean "no new code". Timer-executed
repo files re-read the file at every tick — between the fast-forward and
B0's suspension they run the *new* version against the old services
(`aitbc-backup.sh`, `backup-textfile.py`, `escrow-residue-textfile.py`
are in the release range as of 20 Oct; `escrow-settlements-textfile.py`
is not). The gap is minutes inside the window and the alert-window doc
lists their failure noise as expected.

An earlier fast-forward would stretch this gap — the restart table and
the timer exposure alike — to days; the operator has not chosen that.

## B. Freeze — stop accepting writes, in order

Each step is **operator-named** (env flips and service stops); each ends
with an **ungated** verify read.

| # | action | class | verify read |
|---|---|---|---|
| B0 | timers suspended — per `bc2-host-inventory.md`: `aitbc-escrow-settlements.timer` first, then `aitbc-backup.timer`, `aitbc-native-energy-rate-refresh.timer` (hub) and the read-only monitor timers | operator-named | `systemctl list-timers 'aitbc-*'` shows the named timers inactive; restoration happens in §F |
| B1 | faucet + coin-request intake parked — env edit `COIN_REQUEST_AUTO_APPROVE_MAX=0` in the file declaring it for `aitbc-agent-coordinator` on hub (resolve with `aitbc system env-names --service aitbc-agent-coordinator --names COIN_REQUEST_AUTO_APPROVE_MAX`; add to `aitbc-agent-coordinator.env` if unset) + restart `aitbc-agent-coordinator`. New requests park `PENDING` (policy `coin_request_policy.py`: the max-0 path returns "automatic approval is disabled on this hub"); a PENDING row still writes, so the sameness check is on **non-PENDING** statuses | operator-named | `SELECT status, count(*)` on `agent_coin_requests` + `hermes_coin_requests` — APPROVED/EXECUTED counts frozen after the edit. Plus the probe: one register POST lands `PENDING` with reason "automatic approval is disabled on this hub" — **the probe is a write; it runs only on the operator's line, and the operator rejects that row immediately after to restore the baseline** |
| B2 | market + exchange order intake stopped — service stops: `aitbc-market` (hub + node2), `aitbc-exchange` (hub). A stopped unit answers connection refused, not a route-level refusal — that is the mechanism (no pause flag exists on these services). Accepted cost: website exchange/marketplace pages error during the window — cosmetic, no drain dependency | operator-named | `systemctl is-active` = `inactive` on all three units; `ss -ltn` shows the market/exchange ports gone; a POST to each route exits curl rc 7 (connection refused) |
| B3 | `BRIDGE_LOCKS_PAUSED=true` (env edit + restart `aitbc-blockchain-node` + `aitbc-blockchain-rpc` on all five). The name sits in **two** env files on hub (`blockchain.env` + `bootstrap.env`) — edit and verify every file holding it per host | operator-named — validator-interrupting, all five | `grep '^BRIDGE_LOCKS_PAUSED' /etc/aitbc/*.env` — every file carrying the name shows `true`; the bridge GET reads answer (the 503 lock refusal is proven by the POST probe, which `post-cut-verify.py` runs only under `--probe` on the operator's line). Decided: the new chain launches paused too — C3 writes `true`; the unpause waits for `SEPOLIA-REDEPLOY-1` |
| B4 | escrow creation stopped — stop `aitbc-coordinator-api` on hub (the upstream surfaces `/v1/market/*`, `/api/orders`, `POST /jobs` → `escrow/create` are already dead under B2; the coordinator's own job/payment path is the last live leg). Stopping is safe pre-cut: the alembic-at-start trap is on *restart*, which next happens under release code on a fresh DB (C5/C6). Residual leg: direct `POST /rpc/escrow/create` on the node is API-key-gated internal — covered by the last-moment re-read | operator-named | `systemctl is-active aitbc-coordinator-api` = `inactive` on hub; **and the last-moment pending-count re-read** — escrow + job pending counts re-read immediately before C1 (any non-zero = stop the cut) |
| B5 | record heads + roots **and re-run the drain zero-checks** | ungated | `sqlite3 "file:///var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" "SELECT max(height), hash, state_root FROM block"` on all five — all equal; head hash + `state_root` written to the ledger. Plus the `bc2-drain-checklist.md` zero-check reads re-run here — a row that appeared since A3 is a **new drain item and stops the cut** |

Lift: the B2/B4 service stops have **no separate lift row** — those units
come back under the existing C6 restart order, on release code, against
the fresh bc-2 stores. B1's `COIN_REQUEST_AUTO_APPROVE_MAX=0` revert is
an operator-named env edit inside the post-PONR unfreeze row (§H).

Timing: unmeasured (window is D7-tolerant — "a day or more is fine", D7).

## C. Cut — per host class, in order

Host classes: **hub** (proposer + coordinator/exchange/wallet/governance/
bridge-monitor/prometheus/website/nginx), **hub1, node1, node2**
(proposers + follower services), **node0** (customer follower,
non-validator — always last).

| # | action | class | verify (read-only) | rehearsed as | timing |
|---|---|---|---|---|---|
| C1 | stop services in dependency order: customer-facing → coordinator/exchange/market → rpc → node last (p2p on hub) — the **ordered per-host unit list** lives in `bc2-host-inventory.md` | operator-named; node stops on hub/hub1/node1/node2 are validator-interrupting | `systemctl is-active` inactive; timestamp fields recorded | — | unmeasured |
| C2 | move every chain + service store to dated `.pre-reset` copies (no deletion) — **destination `/var/lib/aitbc/.pre-reset-<YYYY-MM-DD>/`, a sibling of `data/`, never inside it** (`data/*/chain.db` scanners must never see an archived store; same filesystem keeps the move a rename and the §D move-back fast). The **per-host store-file list** (chain dir, service DBs, stray top-level `chain.db` and `*.bak` residue — all move into the same `.pre-reset` tree) lives in `bc2-host-inventory.md` | operator-named per host | `du -s` per moved entry equals its pre-move size; `.pre-reset` tree listing covers the whole inventory list; `data/` holds no `chain.db` afterwards | — | unmeasured (sizes in A9) |
| C3 | apply the env set on every unit. Before starting, check **each env name's file count** — names occur in multiple files (`CHAIN_ID` in 18 files on hub, `BRIDGE_LOCKS_PAUSED` in 2) — every file holding a name gets the value, not just `blockchain.env`. `TRUSTED_PROPOSERS` is an **add** (absent from every env file today), not an edit of an existing line | operator-named | anchored `grep` of each name in `bc2-environment-set.md` across **all** matching env files; node0 pins per `RESET-ENV-NODE0-1` (#323). Decided values on all five: `BRIDGE_LOCKS_PAUSED=true` (stays paused until `SEPOLIA-REDEPLOY-1`), `TRUSTED_PROPOSERS=genesis,<the four current validators>`, `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=256` | — | unmeasured (~101 chain-id assignments across five hosts) |
| C4 | build genesis on scratch → `verify-genesis-root.py` → distribute `genesis.json` into `data/bc-2/` on **all five** hosts — allocation inputs are the committed pair `docs/deployment/bc2-genesis/allocations.json` + `classes.json` (see the C4 detail below). **First, the proof hand-off:** before the pre-build checker can run, the operator places the treasury proof JSON on the build host out of band (mode `0600`, deleted right after the checker run — it is never committed and never distributed) | build/verify ungated (scratch); the proof hand-off and the distribution are operator-named | per-host `sha256sum` equals the verified build output; the consumed `allocations.json`/`classes.json` match the pinned sha256 (`ca4a1500…`/`836ae037…` — full digests in `docs/deployment/bc2-genesis/README.md`); the checker run ends `alloc-file check: PASS` incl. `treasury proof PASS`, then the proof file is gone | `rehearsal.py genesis` (REHEARSAL-3) | estimate 20–90 s |
| C5 | node units: **the rehearsed shape — all four validator node units up inside one short window**, then followers, node0 last. A serial "catch-up proof between hosts" has nothing to prove at height 0: with attestation minimum 2 and file-loaded block 0, no block can seal until a second validator is up — so validators start together as rehearsed, and the rejoin proof happens **after** sealing begins (stop one validator, watch it catch up — rehearsed `rejoin`). **Before the first unit starts:** `TRUSTED_PROPOSERS` on every host resolves to `genesis` plus the four genesis validator addresses — the membership check then governs every imported block. The first produced block lands shortly after the second validator is up — **that first seal is §D's point of no return, inside this step** | operator-named, validator-interrupting per host | `journalctl -u aitbc-blockchain-node --since <recorded start>` shows `Successfully created genesis block from genesis.json` exactly once and `Initializing databases for chains: ['bc-2']` per host (fleet units log to journald — `node.log` was a scratch-harness artifact); heads advancing. **Crash-loop warning:** `Restart=on-failure` is set on every node unit — `is-active` = `active` alone proves nothing; only the journal lines after the recorded start do | `up`, `wait`, `check`, `rejoin`, `skip` | **measured:** `up` ~11 s for all five units (journal 05:47:36→~47); rejoin-catch-up ~1.4 m (journal 05:53:49→05:55:03); fleet window 9 m 46 s (journal 05:47:36→05:57:22, REHEARSAL-3 ledger) |
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

C4 inputs — the committed allocation pair: `build-genesis.py` consumes
`docs/deployment/bc2-genesis/allocations.json` (sha256
`ca4a150085cff31e9388ab504c2ed0e855e6f963bbdcbde8875b94872d281fcb`) and the
checker binds it against `docs/deployment/bc2-genesis/classes.json`
(sha256 `836ae03716a97b130476c8983eb6a8d3dabf9c9eeb03530d85f6cfa69f6cbcb5`);
`tests/unit/test_bc2_genesis_files.py` pins both digests. Re-verify before
the build, exactly as A8 ran it:

```bash
venv/bin/python scripts/ops/check-alloc-file.py \
  --allocations docs/deployment/bc2-genesis/allocations.json \
  --classes docs/deployment/bc2-genesis/classes.json \
  --require-classes \
  --treasury-proof <operator-held proof file>
```

The treasury proof JSON is operator custody — it is a verification input,
never committed (see `docs/deployment/bc2-genesis/README.md`). The
hand-off is an explicit beat of C4: the operator places it on the build
host out of band at mode `0600`, the checker consumes it, and it is
deleted right after — never distributed with the genesis file.

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

C3 coverage limits (21 Oct window findings): the env apply sweeps only
`/etc/aitbc/*.env` names. `Environment=` keys inside unit and drop-in
files (`/etc/systemd/system/aitbc-*.service`, `*.service.d/*.conf` — the
window's live example was `AITBC_CHAIN_DB` pins in escrow-settlement
drop-ins and hub's bridge-set unit) are outside that set and need their
own anchored `grep -rn 'Environment=' /etc/systemd/system/aitbc-*` pass.
The apply also never *removes* a name: stale values persist until a
manual unset, so after apply, sweep for the **absence** of the old chain
id (`grep -rn 'ait-hub\|ait-mainnet' /etc/aitbc/`), not only the presence
of the new one. A remove/repoint path in the planner remains a tooling
gap — until it exists, both sweeps are manual checklist rows.

C5→C6 ordering note (21 Oct window finding): mesh-mode validators reach
the attestation topics through `aitbc-blockchain-rpc` — a fleet sitting
at height 0 in `consensus_gates` while C6's rpc leg is still down is
expected, not a stall. Prefer starting the rpc units **with or right
after** the validator units in C5 rather than waiting for the whole C6
service block.

C7 checks: five heads equal and advancing; all four proposers sealing in
rotation (`SELECT DISTINCT proposer FROM block WHERE height>0`);
attestation quorum ≥2 on **every** produced block (the sweep: per height,
`len(json.loads(block_metadata)["attestations"]) >= 2` — rehearsed 8/8);
read paths answer for `bc-2` — named sources: the `aitbc-blockchain-rpc`
units (head/status routes), `aitbc-blockchain-explorer` (service active
+ page serving `bc-2` heights), the hub website (rendered site reflects
the new chain), the bridge route (`GET /rpc/bridge/pending` on the rpc
listener answers); **`data/` holds no old-chain store** —
`find /var/lib/aitbc/data -name chain.db` lists only
`data/bc-2/chain.db`, and no `ait-hub*` store or `.pre-reset` residue
sits under `data/` (the `.pre-reset` tree lives outside `data/`; fresh
service DBs alongside `bc-2/` are expected once C6 starts services);
alerts quiet — checked in the
`aitbc-prometheus-watch` journal and `/var/log/aitbc/alerts.log` (the
public alerts page reads the same source).

## D. Point of no return — the first block sealed on bc-2

"Sealed" means a block **above height 0 produced by a proposer** and
recorded with its attestations. Block 0 is file-loaded at node start and
sits **before** the point — a fleet that has only file-loaded genesis has
committed nothing. Ledger ids: the seal itself is **PONR**; each abort
row below is an **ABORT** entry keyed by the step reached.

| reached | abort action | cost |
|---|---|---|
| freeze only (§B) | unpause every intake | drain settlements already made stand — they were owed; downtime only |
| C1 services stopped | restart old env/units | downtime only |
| C2 stores moved | **move `.pre-reset` copies back first** — a bare restart finds empty dirs and restores nothing (§E: current code refuses without `genesis.json`, old code stalls without a hub) | a named move-back step per host, then restart |
| C3 env applied | revert env edits | env edit + restart per unit |
| C4 genesis distributed | delete `data/bc-2/` files | per-host file removal; the old chain's dir is untouched by construction |
| C5 units started, nothing sealed yet (e.g. only one validator up) | stop the started units, delete `data/bc-2/` files, revert env, then the earlier rows | prove nothing sealed: `max(height)=0` on every started host's `bc-2` chain.db — rehearsal-evidenced (`RESET-ROLLBACK-1`: 130 s, 13 polls, all 0); nothing produced, nothing to abandon |
| C5+ first seal | — | **the point**: abandoning bc-2 is a second reset-class event, not an abort |

After the first seal the abort table no longer applies — post-PONR
failure modes and the two-minute decision tree live in
`bc2-post-ponr-failures.md`.

**F1 (post-PONR unfreeze).** After the point, never before: unfreeze
writes — market/exchange reopen, `aitbc-coordinator-api` restarted on
hub (undoes B4's stop — its `ExecStartPre` alembic upgrade runs on
restart against the fresh service DB, expected no-op), B1's env edit
reverted, B0 timers restored (§F). The website maintenance-notice takedown is its **own F1
sub-item (F1a)** — it modifies public content. The bridge-lock unpause is **not**
in this list — decided: locks stay paused until `SEPOLIA-REDEPLOY-1`
(operator placed the redeploy "in the week after the cut"), a separate
gated step outside the cut.

## E. Rollback before the point — **scratch-rehearsed (`RESET-ROLLBACK-1`), live-path residuals unproven**

Venue decided: the node2 scratch harness (operator card). The rehearsal
ran 20 Oct on `scripts/reset-harness/rollback.py` and proved every
acceptance item on scratch; what it could not prove on live data is
listed as residual, not as a blocker.

What the scratch run recorded:

1. Every cut step §C reverted individually and in order — stops,
   `.pre-reset` store moves, env swap and byte-exact env revert, genesis
   distribution — on scratch instances (`systemd-run` services).
2. Byte-equal restore verified from **both** the moved-aside copies and a
   separate backup copy (sha256 manifest recorded before the cut; zero
   diffs on both legs).
3. A bare restart on empty dirs restores **nothing** on either code
   generation — old code (`6966658c1`) stalls without a hub to sync
   block 0 from (head −1); current code refuses startup at
   `consensus/poa.py:1641` with "Genesis file required". The explicit
   `.pre-reset` move-back is the load-bearing step.
4. The fresh-start detection rule fired: after a restart,
   `ActiveEnterTimestamp`/`ExecMainStartTimestamp`/`MainPID` all differed
   and the unit read as "a prior run already completed".
5. The old chain resumed at the frozen head (recorded from the
   pre-escrow-repair dump: height 44749) with the same head hash and
   state root.
6. The partial-start proof: one validator up for 130 s (13 polls, 15 s
   attestation timeout) — `max(height)=0` throughout. Nothing seals
   before a second validator joins, so the point cannot be crossed
   early.

Residual the harness cannot prove (accepted, not blocking): real systemd
units vs transient scopes, real data-dir sizes (304–534 M vs scratch MB),
live-path writes under `/var/lib/aitbc` (the harness writes only under
`AITBC_RESET_SCRATCH`), and the five-host serial order.

## F. After the reset

Soak — **3 days** (decided 20 Oct): the post-cut observation window in
which a restore of the old chain stays an operator option; nothing is
deleted while it runs. Consumer changes go live per `bc2-consumers.md`
(v9 alert removal,
`WEBSITE_CHAIN_ID=bc-2` render, `BACKUP_GOOD_CHAIN_GLOB`, genesis-builder
refusal-list addition); **restore the timers suspended at B0**
(`aitbc-escrow-settlements.timer`, `aitbc-backup.timer`,
`aitbc-native-energy-rate-refresh.timer` and the monitor timers per
`bc2-host-inventory.md`) — suspended timers show as `*Stale` alerts until
resumed; the register and ledgers keep old heights as
history; the bridge-lock unpause lands with `SEPOLIA-REDEPLOY-1`
(operator: "in the week after the cut") as its own gated step — **F5**
below; **F2** — write the reset record in `TOPOLOGY/`; **F3** —
`.pre-reset` copies and offline backups retire **after the 3-day soak has
ended, on a per-item operator word**; **F4** — after the soak ends and
**before locks are unpaused**: fund the sell-escrow account `0x40c7…` and
the bridge payout account `0x356d…` from the treasury — two
operator-named chain writes, amounts per the operator's card.

**F5** — bridge-lock unpause (operator-named env edit; the restart leg
is the standing rpc class, **not** validator-interrupting). Preconditions:
the soak-end gate green (`bc2-post-cut-owed.md` §2), F4 sealed, and
`SEPOLIA-REDEPLOY-1` complete — the new contract on Sepolia, Safe-owned
(the operator checklist is `bc2-sepolia-redeploy-checklist.md`).
`scripts/ops/unpause-precheck.py` must print **GO** before the operator's
line; it reads the saved post-cut report, F4 balances, the pause flag on
every carrier, `BRIDGE_CONTRACT_ADDRESS` in the monitor env, the Sepolia
contract (code / `owner()` / `getThreshold()`), and head agreement.

- **Edits**: `BRIDGE_LOCKS_PAUSED=false` in every file holding it —
  `blockchain.env` on all five hosts plus `bootstrap.env` on hub (six
  files; `bootstrap.env` is edit-only — no unit reads it at runtime, but
  a re-bootstrap must not resurrect `true`).
- **Restart**: `aitbc-blockchain-rpc` only, serial across the five
  hosts — the flag is evaluated **only inside the RPC app**
  (`rpc/routers/cross_chain.py:158`, `rpc/bridge.py:126`,
  `cross_chain/bridge_transfer.py:113`; the bridge service is created in
  `app.py`, which only the rpc unit runs). The node unit loads the name
  into `settings` but never evaluates it — the validators keep sealing
  through the flip, and any later routine node restart picks up `false`
  harmlessly. `aitbc-bridge-monitor` on hub restarts on the same line to
  load the redeployed `BRIDGE_CONTRACT_ADDRESS`.
- **Verify**: anchored greps show `false` on all six carriers; the
  pause probe **inverts** — the fence sits *before* signature validation
  (`cross_chain.py:158` refuses 503 ahead of the signature path at
  `:175`), so the same well-shaped unsigned POST that answered 503 now
  reaches signature checking and answers **403**; `env-names --process`
  shows the live flag; monitor `--process` shows the contract address; a
  real lock POST only on the operator's own line (it is a chain write).
- **Rollback**: set `true` in the same six files and serial-restart rpc
  again. A lock that already sealed stays sealed — refund/status routes
  were never fenced, so in-flight transfers keep resolving.
- **Exchange note**: `aitbc-exchange.env` does **not** carry
  `BRIDGE_CONTRACT_ADDRESS` today; without it the exchange's bridge
  config holds an empty contract address (its status reads blank).
  Adding the name there is an operator-named env edit in the F5
  checklist, not a prep-side change.

Everything the cut leaves undone — the gated rows below plus the
consumer flips and the register pointers — is collected, ordered, and
verify-read in `bc2-post-cut-owed.md`; nothing on that sheet proceeds
until the post-cut verifier is green again after the soak.

Post-reset operating rule (decided): `TRUSTED_PROPOSERS` is set. Any later
validator-set change must update the list on **every host in the same
change** — the membership check governs every imported block, so a
proposer not yet in the list has its blocks refused fleet-wide.

Second standing rule (21 Oct incident, `EDGE-REG-CONSENSUS-1`): no write
to a committed side-table may happen outside block apply. An RPC path
that writes a `COMMITTED_TABLES` row on one host diverges that host's
committed aux root from the fleet — node2's `edge_node_registration`
register-write did exactly that and stalled the node on aux mismatch.
The CI guard `tests/unit/test_rpc_committed_writes.py` fails on any new
RPC write site against a committed table; the v15 rung removes that
anomaly table from the committed set at its (operator-named) activation
height.

Window-proven ops rules (21 Oct, `RESET-RUNBOOK-GAPS-1`):

- `.prom` textfile writers must `chmod 0644` the temp file **before** the
  atomic rename — `mkstemp`+`os.replace` lands mode 0600 and
  node-exporter then cannot read it (fixed in the attestation/residue
  writers, `f5651b648`; `native-energy-rate-refresh.sh` was already
  correct).
- Alert-rules changes: build the new rules file from `/etc`'s current
  content plus the named hunk only, `diff` it exactly,
  `promtool check rules`, then `systemctl reload` prometheus — the drift
  behind the stale `BackupNoGoodChain` came from regenerating the file by
  hand.
- Miner-authenticated CLI calls: coordinator logins mint only
  admin/client JWTs — miner-role endpoints accept a miner-role JWT or
  `X-Api-Key` from `MINER_API_KEYS`. The CLI path is
  `aitbc --api-key <MINER_API_KEYS[0]> …`; a 401 there means a missing
  header, not a broken login.
- Coordinator singletons do not self-heal: on a fresh `coordinator.db`,
  re-set `native_energy_rates` and re-register `native_energy_profiles`
  (operator-set rows) — until then `NativeEnergyRateStale` and the
  refresh oneshot's failure fire exactly as they did in this window.

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

Harness deviation from the decided env set, by design: the scratch
profile runs `BLOCK_TIME_SECONDS=10` (code default) against the fleet
value `60`, and leaves `PARALLEL_TX_VALIDATION` at its default (`false`)
against the fleet `true` — inert on bc-2 where every produced height
resolves v14, outside the flag's 2–8 window (`bc2-environment-set.md`).

## H. Gate table

| step | who names it | evidence to record |
|---|---|---|
| FF1 ff to reset commit (first window action) | operator-named — the reset-release deploy | per-host `git rev-parse HEAD` + `ExecMainStartTimestamp` baseline |
| freeze B0–B4 | operator-named | operator line verbatim + `list-timers` + refuse-read outputs |
| B5 head record | ungated | 5× head+hash+state_root in ledger |
| C1 stops | operator-named (validator-interrupting on 4 hosts) | operator line verbatim; `is-active` + timestamp fields |
| C2 `.pre-reset` | operator-named per host | `du -s` pairs per store; `find /var/lib/aitbc/data -name chain.db` empty |
| C3 env apply | operator-named per host | anchored greps per env-set |
| C4 genesis | ungated build; operator-named distribution | builder verdict + verify output + 5× sha256 |
| C5 node starts | operator-named per host (validator-interrupting) | file-load line ×1, resolved-id line, timestamp fields |
| C6 rpc + stores | rpc standing; stores operator-named | table counts, redis-backend evidence |
| C7 checks | ungated | heads, proposer set, per-block quorum sweep, read-path results, `find data/ -name chain.db` lists only `data/bc-2/chain.db` and no `ait-hub*` store |
| post-PONR unfreeze (F1) | operator-named | operator line verbatim + accept-read outputs; `aitbc-coordinator-api` active and `/health` answering on hub |
| `.pre-reset` deletion (F3) | per-item word, after the 3-day soak | operator line verbatim per item |
| post-soak funding (F4) | operator-named, gated at soak-end | operator line verbatim + treasury→`0x40c7…`/`0x356d…` sealed txs + new balances |
| bridge-lock unpause (F5) | operator-named env edit; serial rpc restart is the standing class | `unpause-precheck.py` GO + operator line verbatim + `false` grep ×6 + probe 503→403 inversion |

### Operator line shapes — proposal (the operator writes his own lines)

Shapes to pick from, not authorizations — nothing here is a go line until
the operator writes it. Validator-interrupting steps (C1, C5) keep the
rule that the operator's own message names action **and** hosts.

| step | proposed shape | one line covers |
|---|---|---|
| FF1 | "Fast-forward all five hosts to `<sha>` in order node0, hub1, node1, node2, hub." | all five (order is procedure, not authorization) |
| B0 | "Suspend `aitbc-escrow-settlements.timer` and `aitbc-backup.timer` on all five hosts — hub, hub1, node0, node1, node2 — plus `aitbc-native-energy-rate-refresh.timer` on hub, and the monitor timers fleet-wide." | all |
| B1 | "Park coin-request intake on hub; run the PENDING probe and reject that row." | hub — probe+reject inside one line |
| B2 | "Stop `aitbc-market` on hub and node2 and `aitbc-exchange` on hub." | hub + node2 |
| B3 | "Set `BRIDGE_LOCKS_PAUSED=true` in every file holding it and restart node+rpc on all five." | all five — validator-interrupting |
| B4 | "Stop `aitbc-coordinator-api` on hub." | hub |
| C1 | "Stop services in inventory order on hub, hub1, node0, node1, node2." | all five |
| C2 | "Move the inventory store list to `/var/lib/aitbc/.pre-reset-<YYYY-MM-DD>/` on `<host>`." | one host — per-host granularity is decided |
| C3 | "Apply the bc-2 env set on `<host>`." | one host |
| C4 | "Distribute the verified `genesis.json` into `data/bc-2/` on all five hosts." | all five (build itself ungated) |
| C5 | "Start the four validator node units now: hub, hub1, node1, node2." then "Start node0." | **two lines** — the simultaneous validator start is one action; node0 deliberately last |
| C6 | "Start rpc units and the remaining service units fleet-wide." | all five (rpc leg already standing) |
| F1 | "Post-PONR unfreeze: restore timers, reopen market/exchange incl. `aitbc-coordinator-api`, revert B1." **plus its own line (F1a)** "Take the maintenance notice down." | two parts — the takedown modifies public content |
| F3 | "Delete `<path>` on `<host>`." | never shared — per-item word by design |
| F4 | "Fund sell-escrow `0x40c7…` and bridge payout `0x356d…` from the treasury — `<amount>` AIT each." | two chain writes — gated at soak-end, before locks unpause |
| F5 | "Set `BRIDGE_LOCKS_PAUSED=false` in every file holding it — `blockchain.env` on all five plus `bootstrap.env` on hub — and restart `aitbc-bridge-monitor` on hub." | env edit names the unpause; the serial rpc restart rides the standing class — validators keep sealing |
| ABORT | "Abort at `<step>`: run the §D abort row." | per event |

## I. Decisions

Taken (operator card, 20 Oct — answers in his words):

| item | answer | carried into |
|---|---|---|
| `TRUSTED_PROPOSERS` | "Set it" — `genesis` plus the four current validators | C3/C5 check + post-reset operating rule in §F |
| `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` | "256 on all five" | C3 decided value (`bc2-environment-set.md` carries it) |
| bridge locks after the cut | "Stay paused until redeploy" (redeploy placed "in the week after the cut") | B3, C3 decided value, §D/§F notes — `BRIDGE_LOCKS_PAUSED=true` launches with bc-2; unpause is a separate gated step after `SEPOLIA-REDEPLOY-1` |
| rollback rehearsal venue | "node2 scratch harness" | §E acceptance list + residual |
| node0 `STATE_SYNC_MAX_GAP` | `-1` (fleet value) | `RESET-ENV-NODE0-1` (#323) |
| key rotation | "No rotation for this reset" ("this is not a v1 bc reset. after bc reset we are still on eth testnet") — the earlier ≥3-day rotation answer is withdrawn; bc-2 is a testnet-era reset, Ethereum stays on Sepolia; the validator set is the four current validators | A1, C3, §F, `bc2-environment-set.md` operator rows |
| allocation figures | "Confirmed final"; treasury "New address, will supply", all other addresses "Same as live today" | A2 — both address lists still outstanding |
| bridge/escrow identities + lock cap | "Keep live + 1000 AIT" | `bc2-environment-set.md` operator rows — `BRIDGE_ADMIN_ADDRESSES`, `BRIDGE_RELEASE_AUTHORITY`, `ESCROW_*`, `BOND_*`, `BRIDGE_MAX_LOCK_AMOUNT` |
| `.pre-reset` deletion | "Leave as owed item" — per-item word after the post-cut soak, nothing pre-authorised | §H gate row |
| public maintenance notice | "about 3 days ahead" of the window | A11, §D |
| final rehearsal | "Yes, one final run" → `RESET-REHEARSAL-4` | A5, §G |
| node start order | "Short simultaneous start" | C5 |
| deploy timing | "First step of the window" | "First window action — code convergence" |
| genesis write path | "Scratch path is enough" | A6, C4 — `RESET-GENESIS-LIVE-1` parked, not a blocker |
| window placement | "After rehearsal 4" | A13 |

The env-set rows now carry the decided values (`RESET-ENV-DECIDED-1`
#325, `988ac35e2`); its operator-table identity rows are decided by the
20 Oct card answers above.

Still owed (nothing pre-authorised):

| decision | state | cost |
|---|---|---|
| treasury address | supplied 20 Oct — `0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0`, single-key off-fleet, `personal_sign` proof verified (A2/A8) | resolved — no longer blocks the genesis cut |
| address lists — validators and accounts | confirmed 20 Oct — the four current validators; the account list is the committed pair `docs/deployment/bc2-genesis/{allocations,classes}.json`, sha256-pinned (A1/A2/A8) | resolved — no longer blocks the genesis cut |
| window date | placement decided "After rehearsal 4" (A13); the date itself is blank | the freeze window cannot be scheduled |
