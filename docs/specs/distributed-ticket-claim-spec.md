# Design Spec — Distributed Ticket Claim (Multi-Orchestrator Coordination)

**Ticket**: ABS-181 · **Status**: DRAFT — revised after review (heartbeat, restart identity, TTL source, pagination) · **Date**: 2026-07-09
**Author role**: BSA / System Architect · **Supersedes nothing** — additive to [ABS-36](ABS-36-orchestrator-spec.md)

Design record for a **cross-machine ticket claim** that lets two or more orchestrator
instances — running on **different machines** against the **same tracker project** — cooperate
without double-spawning the same ticket.

It closes the gap identified on 2026-07-09: the existing per-ticket lock ([`scripts/orchestrator.sh:2300`](../../scripts/orchestrator.sh), §5.2 of ABS-36) is a
local `mkdir` directory under `work/.orchestrator/locks/`. Two machines have independent lock
trees, so `acquire_lock` on machine B always succeeds while machine A holds "the same" lock —
they never see each other, and both spawn a subagent for the same ticket.

This spec is **design only**. No runner code ships under it; it pins the contracts the
implementation stories must not re-decide.

It must not weaken the three standing invariants:

- **Adapter-only tracker access** (ADR-A-0007): the claim speaks only the canonical `TRACKER_CMD`
  operations — never a vendor API or `work/tickets/*.md` directly.
- **Fresh subagent per task** (ADR-A-0002): the claim gates the spawn; it does not change what a spawn does.
- **At-least-once + idempotent** (ABS-36 §1.4): the claim narrows the double-spawn race; the
  existing idempotency re-read guard (`ticket_still_in`, §5.4) remains the final backstop.

---

## 1. Problem statement

| | Today (single-flight local lock) | Required (distributed claim) |
|---|---|---|
| Mutex scope | one runner process | all runners against one tracker |
| Store | local FS (`mkdir`) | the shared tracker (only thing both machines see) |
| Two machines, same ticket | **both spawn** (double work, racing PRs) | exactly one spawns; the other yields |

**Non-goal**: turning the orchestrator into a distributed scheduler. We want *mutual exclusion* per
ticket (whole-ticket affinity, §4.2), not leader election, work-stealing, or a global priority queue.
Prioritization stays inside the spawned `po-agent` (unchanged).

---

## 2. Design — two-tier lock

A dispatch may spawn **only if it holds both tiers**. Cheap-first ordering: local mutex, then the
one network round-trip.

```
dispatch(ticket):
  ... existing gates (kill-switch, outage, budget, iteration) ...
  if not acquire_lock(ticket):              # TIER 1 — local mkdir (UNCHANGED, §5.2)
        SKIP-LOCKED; requeue; return
  if live_spawns >= ORCH_MAX_CONCURRENT:    # concurrency cap FIRST (§4.6 fairness)
        release_lock(ticket); DEFER-CAP; requeue; return    # <- deferred ticket stays UNCLAIMED
  if ORCH_CLAIM_MODE != off:
      if not acquire_remote_claim(ticket):  # TIER 2 — claim only a ticket we can spawn NOW
          release_lock(ticket); SKIP-CLAIMED; requeue; return
  live_spawns++; budget--; spawn(ticket)
```

- **Tier 1 (local `mkdir`)** — unchanged. Still the right tool for the many concurrent *passes*
  and async spawns *within one runner*: zero network, sub-millisecond, self-reclaiming on TTL.
- **Tier 2 (remote claim)** — new. The only tier that can see across machines, because it lives
  in the one store both machines share: the tracker. Default **off** (`ORCH_CLAIM_MODE=off`), so
  single-orchestrator deployments behave exactly as today (backward compatible).

Layering (not replacing) means the common single-machine path pays **zero** extra network cost
until an operator opts in, and Tier 1 still absorbs the high-frequency intra-runner contention so
Tier 2 only fires once per ticket episode.

---

## 3. `#PATH_DECISION` — which tracker primitive is the atomic claim?

Jira/Linear expose **no compare-and-swap**. Three candidates emulate one over the adapter surface
(`get`, `assign`, `transition`, `comment`, `events`):

### Candidate A — Assignee CAS (write-then-read-back)
Set `assign(ticket, myAccountId)`, wait a jitter, re-read; if the assignee is still mine, I won.
- **Pro**: reuses existing `assign` (ABS-126); human-visible (ticket shows who's on it).
- **Con**: needs a **per-instance-unique** Jira accountId. Today's `ORCH_ASSIGNEE` is a *fixed
  per-role* accountId — identical on both machines — so read-back cannot tell A from B. Requires
  provisioning a distinct Jira user per machine. **Probabilistic** (last-writer-wins + jitter),
  not a true total order.

### Candidate B — Claim comment with server ordering  ✅ CHOSEN
Post a `kind: claim` comment carrying an arbitrary `instance:` id and an `episode:` scope; read the
ticket; the claim comment that appears **first in the dump** for that episode wins.
- The adapter renders comments as `### <at> | kind: <k> | actor: <a>` in **creation order** (Jira's
  `/comment` endpoint returns created-ascending; the mock appends) — verified in both
  [`jira-tracker.sh:522`](../../scripts/jira-tracker.sh) and [`mock-tracker.sh:166`](../../scripts/mock-tracker.sh).
  **Dump order is a server-assigned total order** → a deterministic single winner, not a guess.
- Reuses an idiom the codebase already trusts: `kind`+`actor` comment markers as idempotency guards
  (`has_intake_marker`, `has_blocked_marker`).
- **Identity-agnostic**: `instance:` is any unique string; works whether machines share one service
  account or not.
- **Zero workflow-schema change**; stays tracker-neutral behind the adapter.
- **Con**: one extra `comment` + one extra `get` per *contended* dispatch, and mild comment noise
  (mitigated by §3.5 episode-scoping and an optional janitor).

### Candidate C — Transition CAS (workflow-guarded)
Transition the ticket to a dedicated `Claimed`/`Working` substate; Jira validates the `fromStatus`
server-side, so only the first transition succeeds.
- **Pro**: truly atomic, identity-free.
- **Con**: needs a claim-substate for **every** spawn-triggering status, across Jira **and** Linear
  **and** the mock — a heavy, tracker-specific workflow-schema change that perturbs the very status
  machine the orchestrator is built around. Rejected as too invasive; recorded as the
  theoretically-cleanest alternative.

**Decision**: **Candidate B** is the claim of record. **Candidate A** is retained as an *optional,
non-authoritative* human-visibility layer (`ORCH_CLAIM_ASSIGN=1` also stamps the assignee after a
win, purely cosmetic). **Candidate C** rejected.

---

## 4. The claim protocol (Candidate B)

### 4.1 Instance identity — per checkout, NOT per process
Each runner mints a stable id **once per checkout, ever** — on first startup only — and persists it:

```
ORCH_INSTANCE_ID  :=  "${hostname}-${pid}-${short_rand}"     # e.g. mba-raphael-48213-a1c9
```
Stored at `work/.orchestrator/instance-id`. **Every subsequent startup MUST reuse the persisted id
verbatim**; pid and rand are entropy at first mint only, never re-derived per process. Rationale: a
restart that re-minted the id would make the machine treat its *own* live claims as a foreign
holder's — it would yield on every in-flight ticket it owns for up to `ORCH_CLAIM_TTL`, and a peer
could take over tickets whose worktrees live on this very machine. Operator-overridable via env
(the override also wins over the persisted file). Uniqueness need only hold across the machines
sharing one tracker; hostname+pid+rand at first mint is sufficient and needs no registry.

### 4.2 Claim scope — the whole ticket (affinity)  `#PATH_DECISION`
A claim is scoped to the **entire ticket**, not to one status visit. Once a machine wins ticket T it
owns **every** episode of T — Dev, Review, Test, any bounce back to Dev — until T reaches a
**terminal status** (Done / Cancelled). Other machines never touch T while a fresh claim exists.

This is *ticket affinity*, and it is deliberate (see §4.5): it keeps every consecutive role of a
ticket on the machine that holds the branch and the worktree, and — critically — keeps the
machine-local **iteration/bounce guard and budget ledger coherent**, because one machine sees all of
a ticket's episodes. A per-*episode* claim was rejected precisely because it lets the next status hop
machines, splitting those local counters and orphaning the worktree on a bounce.

### 4.3 Algorithm
```
acquire_remote_claim(ticket):
  # 0. pre-check: does a live (non-stale, non-terminal) claim already exist?
  dump   = tracker get ticket
  winner = first_live_claim(dump)                  # first `kind: claim` block with at: within TTL
  if winner is not None:
      if winner.instance == ORCH_INSTANCE_ID:
          refresh_claim(ticket)                    # touch: re-stake to keep MY claim fresh (§4.4)
          return true                              # I already own this ticket — proceed
      return false                                 # someone else owns it — yield

  # 1. stake a claim
  tracker comment ticket --kind claim --actor orchestrator \
        --body "instance: $ORCH_INSTANCE_ID | at: $(now)"

  # 2. settle: let all concurrent stakes land before anyone adjudicates
  sleep ORCH_CLAIM_SETTLE_MS + jitter(0..ORCH_CLAIM_JITTER_MS)

  # 3. adjudicate by server order
  dump   = tracker get ticket
  winner = first_live_claim(dump)                  # earliest = lowest in dump = server-first
  return (winner.instance == ORCH_INSTANCE_ID)
```

- **Adjudication authority = dump order** (creation order). Ties in second-granularity timestamps
  are broken by dump position, which the server assigns. No comment id is needed.
- **Staleness (TTL) authority = the server-assigned comment timestamp**, i.e. the `### <at>` header
  the adapter renders for every comment (Jira-native timestamps are already normalized to UTC `Z`
  form by `jira_ts_to_z` in [`jira-tracker.sh`](../../scripts/jira-tracker.sh); the mock appends its
  own). The body `at:` field is a human-readable signal only and MUST NOT be used for TTL math:
  it is written by the *staking* machine's clock and read by the *judging* machine's clock, so
  cross-machine clock skew (minutes are plausible) would cause premature steals or over-sticky
  claims at a 10-min TTL. Judging on the server header reduces skew to reader-vs-server only,
  which is shared by all readers and therefore consistent.
- **Read-your-writes + settle**: the settle window (default ~2 s, plus per-instance jitter to spread
  writes) guarantees both stakes are visible before either reads in step 3, so both instances
  converge on the same "first" comment.
- **Idempotent**: the holder re-dispatching any later episode of the same ticket re-reads its own live
  claim in step 0 and proceeds (after a refresh) without a fresh adjudication → never double-claims.

### 4.4 Refresh, release & crash safety
- **Refresh = heartbeat DURING the spawn, not only at episode start.** A refresh only at episode
  start is **insufficient**: the spawn watchdog allows an episode to run `ORCH_AGENT_TIMEOUT`
  (default **900 s**) and per-seat overrides go higher still (the SOP itself recommends
  `ORCH_AGENT_TIMEOUT_QAS=1800`). With a 600 s TTL, a healthy long-running seat would age its own
  claim out **mid-episode** — the ticket still sits in its spawn-triggering status (the agent
  transitions only at the end), so the peer would see a stale claim, win, and double-spawn: exactly
  the failure this design exists to prevent, in the most common heavy case. Therefore the holder
  re-stakes from the **watchdog loop** ([`orchestrator.sh:3230`](../../scripts/orchestrator.sh) — it
  already ticks every 1 s around the live child), throttled to once per `ORCH_CLAIM_TTL/3` (~200 s).
  This makes the TTL independent of episode length: it only needs to exceed the heartbeat interval,
  and per-seat timeout overrides can never outrun it.
- **Refresh on handoff too.** The holder also touches the claim when an episode *ends* (handoff
  posted), so the inter-episode idle gap (e.g. Dev-done → Review-pickup while the holder is at its
  concurrency cap) starts with a full TTL. The exposed window for a peer takeover is then pure
  idle-parking beyond the TTL — which is the *intended* takeover case, not an accident.
- **Normal release is implicit at terminal status.** When T reaches Done / Cancelled the orchestrator
  stops dispatching it, so the claim is simply never refreshed again and decays. No explicit release
  call is required. (A terminal claim is also ignored by `first_live_claim`, so a reopened ticket can
  be re-claimed cleanly.)
- **Crash / long-park safety = TTL.** `first_live_claim` ignores any claim whose latest
  server-assigned timestamp (§4.3) is older than `ORCH_CLAIM_TTL` (**default 600 s / 10 min**,
  decoupled from the 1800 s local-lock TTL — safe *only because of* the in-spawn heartbeat above).
  A crashed holder stops heartbeating, so its ticket frees ≤10 min after the crash; the survivor
  re-claims and reconstructs the worktree from the pushed branch (clean-context recovery). A ticket
  parked longer than the TTL between episodes migrates deliberately — see §4.5 for what that costs.

### 4.5 Why ticket affinity, not per-episode  `#PATH_DECISION`
All work on a ticket stays on one machine for the ticket's whole life. This is a requirement, not an
optimization — a spawn runs as a **local child process** ([`orchestrator.sh:3086`](../../scripts/orchestrator.sh))
and its only durable outputs are the pushed git branch and the tracker handoff. If successive roles
of one ticket ran on different machines, three machine-local pieces of state would desynchronize:

| Local state | Split across machines (per-episode) | Coherent (ticket affinity) |
|---|---|---|
| Iteration / bounce guard (§5.5) | each machine counts only the bounces it saw → cap can be exceeded | one machine sees every bounce → cap holds |
| Git worktree / branch | a bounce (Review→Fix) lands on a machine with no local worktree | the worktree that built the branch is still there |
| Per-run budget ledger | one ticket's cost split across two ledgers | attributable to one runner |

The only cost is load distribution: a ticket is pinned to whichever machine claims it first, so an
idle machine cannot take over an in-flight ticket held by a busy one (it *can* pick up any
**unclaimed** ticket). For a small team this is the right trade; TTL-based takeover (§4.4) still
covers the case where the holder crashes or parks.

**Affinity is best-effort, bounded by the TTL — state it honestly.** "One machine owns every
episode" holds only *while the claim stays fresh* (heartbeat during spawns, touch on handoff). A
ticket that idles past `ORCH_CLAIM_TTL` between episodes migrates by design, and the new owner
starts with **reset machine-local counters**: the bounce/iteration guard and the per-run budget
ledger do not travel with the ticket, and the worktree is reconstructed from the pushed branch. A
takeover is therefore a *deliberate degradation* (crash recovery or long-park rebalance), not a
silent correctness path — the iteration cap can, in the worst case, be paid once per owning
machine. Acceptance criteria must be phrased accordingly ("same machine **as long as the claim
stays fresh**"), never as an unconditional same-machine guarantee.

### 4.6 No backlog hogging — claim only what you can spawn now  `#PATH_DECISION`
Affinity raises an obvious risk: the orchestrator that starts first sees the whole Ready backlog in
its first sweep and could **claim every ticket**, starving the others. The rule that prevents this:

> **A machine stakes a claim only at the moment of spawn admission — after the concurrency-cap
> check, never during backlog iteration.** (§7 places the claim after the cap block.)

Consequences:
- A machine holds at most **`ORCH_MAX_CONCURRENT` actively-spawning claims** at any instant. Every
  ticket it *defers for cap* is left **unclaimed** → free for a peer to grab in the same window.
- With two machines each capped at N, the first sweep leaves everything beyond the winner's N slots
  on the table; the second machine fills its own N from that remainder. Work **self-balances by
  capacity**: whichever machine next frees a slot claims the next unclaimed ticket. The head start of
  starting first is at most N tickets, not the whole backlog.
- The settle window (§4.3) only runs on tickets a machine is *admitting to spawn*, so it costs
  latency proportional to throughput, not to backlog size.

**Residual drift** `#PLAN_UNCERTAINTY`: because affinity holds a claim across the idle gap *between*
a ticket's episodes (e.g. Dev-done → Review-pickup), a fast machine can accumulate ownership of more
than N tickets over time (N spawning + a few parked mid-lifecycle). This is bounded by throughput,
not unbounded hogging, and self-corrects via TTL when a parked ticket ages out. If it proves uneven
in practice, add an optional **`ORCH_CLAIM_MAX_OWNED`** cap (total live claims per machine, spawning
*or* parked); above it the machine defers new tickets unclaimed even with a free spawn slot. Left out
of the core design as likely-unnecessary for a two-machine team — decide after the live smoke.
(Kill-switch, outage, budget and iteration gates all run *earlier* in `spawn_dispatch` than the
claim, so a paused or throttled runner never stakes one.)

---

## 5. Adapter change (enabler — required)

The `claim` comment kind must be added to the whitelist in **three** places (purely additive):

| File | Line (today) | Change |
|---|---|---|
| [`scripts/mock-tracker.sh`](../../scripts/mock-tracker.sh) | ~457 | add `claim` to the `case "$kind"` allow-list |
| [`scripts/jira-tracker.sh`](../../scripts/jira-tracker.sh) | ~1058 | add `claim` to the `case "$kind"` allow-list |
| [`profiles/neutral/adapters/task-tracking.md`](../../profiles/neutral/adapters/task-tracking.md) | ~44 | document the `claim` kind in the canonical contract |

No new adapter *operation* is introduced — the claim rides entirely on the existing
`comment` + `get`.

**Plus one adapter verification that is now load-bearing: comment pagination in `cmd_get`.**
Today [`jira-tracker.sh:524`](../../scripts/jira-tracker.sh) fetches comments with a **single**
`GET /rest/api/3/issue/$id/comment` and no pagination loop. If Jira's default page size ever
truncates a long-lived ticket's comment list (handoffs + intake markers + claim stakes/refreshes
all accumulate), the truncation cuts the **newest** end — i.e. exactly the freshest peer claim
becomes invisible, and **both machines adjudicate themselves the winner**. The enabler story must
either verify the endpoint's default page size is safely above any realistic comment count, or add
a pagination loop (`orderBy=created` ascending, follow `startAt`). Note this hazard exists today
for the ABS-62 stall subsystem too (it reads the same `### <at>` headers); fixing it here fixes
both. The claim janitor (§8.4) also stops being merely cosmetic if pagination is not fixed — it
bounds the comment count that keeps adjudication inside one page.

---

## 6. Config surface (all default to a no-op)

| Env var | Default | Meaning |
|---|---|---|
| `ORCH_CLAIM_MODE` | `off` | `off` → Tier 1 only. `on` → enable the remote claim. Default off keeps solo dev runs comment-noise-free; flipped on as one deliberate switch when the 2nd orchestrator is introduced (see §10). |
| `ORCH_INSTANCE_ID` | `<host>-<pid>-<rand>` | per-runner identity; auto-minted, override to pin. |
| `ORCH_CLAIM_SETTLE_MS` | `1500` | base wait between stake and adjudication. |
| `ORCH_CLAIM_JITTER_MS` | `1000` | random 0..N added to settle, to spread concurrent writers. |
| `ORCH_CLAIM_TTL` | `600` (10 min) | age (per the server-assigned comment timestamp, §4.3) past which a claim is ignored as stale. Safe below episode length only because of the in-spawn heartbeat (§4.4); must stay > 3× the heartbeat throttle. |
| `ORCH_CLAIM_ASSIGN` | `0` | cosmetic: also `assign` the ticket to `ORCH_ASSIGNEE` after a win (Candidate A layer). |
| `ORCH_CLAIM_MAX_OWNED` | _(unset)_ | optional (§4.6): cap total live claims per machine (spawning + parked); above it, defer new tickets unclaimed even with a free slot. Off by default. |

New intents / runlog events (parallel to `SKIP-LOCKED`): `CLAIM` (staked), `CLAIM-WON`,
`SKIP-CLAIMED` (lost — release Tier 1 and requeue, rc 3, same path as `SKIP-LOCKED`).

---

## 7. Integration point

The claim goes in **after** the Tier-1 lock **and after the concurrency-cap admission** — never
before (see §4.6: claiming before the cap is what starves the other machines). A machine thus only
ever stakes a claim on a ticket it is about to spawn *right now*, so its live claim count is bounded
by `ORCH_MAX_CONCURRENT` and every deferred ticket stays unclaimed and free for peers.

Concretely, the existing cap block ([`scripts/orchestrator.sh:3048–3062`](../../scripts/orchestrator.sh))
already runs after `acquire_lock` and releases the lock on `DEFER-CAP`. The claim is inserted between
that cap block and the `LIVE_SPAWNS`/budget increment (`:3064`), so a lost claim consumes no slot:

```sh
if ! acquire_lock "$ticket"; then
    intent SKIP-LOCKED "$ticket" "$role" "$to"; return 3
fi
# ... §5.1 concurrency cap (UNCHANGED): if over cap -> release_lock + DEFER-CAP + return 3.
#     A ticket deferred here is NEVER claimed -> it stays free for the other machine.

# NEW — Tier 2 distributed claim, only now that a spawn slot is reserved (default off).
if [ "$ORCH_CLAIM_MODE" != "off" ] && ! acquire_remote_claim "$ticket"; then
    release_lock "$ticket"                       # peer owns it: give the slot straight back
    intent SKIP-CLAIMED "$ticket" "$role" "$to"; return 3
fi

LIVE_SPAWNS=$((LIVE_SPAWNS + 1)); SPAWN_BUDGET=$((SPAWN_BUDGET - 1))   # existing
# ... spawn ...
```

Everything downstream (budget, async spawn, watchdog) is untouched.

---

## 8. Failure modes & edge cases  `#PLAN_UNCERTAINTY`

1. **Both stake within the settle window** — resolved: both read the same dump in step 3 and honor
   the server-first comment. Exactly one winner.
2. **Tracker eventual consistency lags past the settle window** — the residual race collapses to the
   *existing* at-least-once model: worst case two spawns, and the `ticket_still_in` re-read guard +
   `depends_on` gate catch the loser exactly as they do today. The claim only ever *narrows* the
   window; it never makes things worse than the status quo. `#PLAN_UNCERTAINTY`: measure real Jira
   comment-visibility latency in the live smoke to tune `ORCH_CLAIM_SETTLE_MS`.
3. **Claimant crashes / parks mid-ticket** — TTL (§4.4) frees the ticket after `ORCH_CLAIM_TTL` of no
   refresh; the reconcile sweep re-derives it and the survivor re-claims, then reconstructs the
   worktree from the pushed branch (clean-context recovery, ADR-A-0002).
4. **Comment noise** — one claim per ticket plus throttled refreshes (§4.4), not one per episode, and
   idempotent re-reads (§4.3 step 0) suppress duplicate stakes. Optional janitor prunes `kind: claim`
   comments older than the TTL.
5. **Shared service account** — fine: `instance:` distinguishes runners regardless of Jira author.
6. **`ORCH_CLAIM_ASSIGN=1` write fails** — non-fatal (it is cosmetic); the claim of record is the
   comment, never the assignee.
7. **Runner restart** — covered by §4.1: the persisted instance id is reused, so the restarted
   runner recognizes its own claims in step 0 and resumes without yielding to itself.
8. **Epic-integration-branch races (explicitly OUT OF SCOPE, but real)** — the per-ticket claim
   serializes work *per ticket*; it does **not** serialize two machines merging two *different*
   sibling-story PRs into the same epic integration branch (per-epic auto-merge policy). If the
   merge goes through the Bitbucket PR-merge API the server serializes the merges themselves, but
   non-fast-forward push retries / "needs rebase" states can now occur cross-machine.
   `#PLAN_UNCERTAINTY`: observe in the two-machine smoke; if it bites, file a follow-up (retry-on-
   non-FF loop or claim-scoping the epic merge op) — do not widen this epic.
9. **Fleet budget** — `SPAWN_BUDGET` is per runner, so total fleet spend is N × budget. Not a bug;
   the multi-orchestrator SOP (story 7) must state it so operators size budgets per machine.
10. **Duplicate `INTAKE-CLASS` audit comment** — `route_intake` posts it outside the dispatch/claim
   path guarded only by `has_intake_marker`, so two machines can race it. Cosmetic (the marker
   stays at-most-once per machine-read); note it in the SOP, no code change.

---

## 9. Test strategy

- **Unit (mock tracker)**: two runner invocations sharing one mock ticket dir → assert exactly one
  `CLAIM-WON` and one `SKIP-CLAIMED` for the same episode; assert idempotent re-dispatch by the
  winner does not post a second claim comment; assert a claim older than TTL is reclaimed.
- **Heartbeat (mock tracker)**: a simulated spawn running longer than `ORCH_CLAIM_TTL` → assert the
  watchdog-loop refresh keeps the claim fresh (peer's `acquire_remote_claim` returns false for the
  whole spawn); assert the refresh is throttled (≤1 touch per TTL/3).
- **Restart identity**: kill and restart a runner mid-claim → assert the persisted
  `work/.orchestrator/instance-id` is reused and step 0 recognizes the runner's own claim (no
  self-yield, no re-stake storm).
- **Staleness source**: a claim whose body `at:` lies (skewed clock) → assert TTL math follows the
  server-assigned `### <at>` header, not the body.
- **Pagination (jira adapter)**: verify `cmd_get` returns the full comment list on a ticket with
  more comments than one API page, or that the default page size provably exceeds realistic counts
  (§5).
- **Concurrency harness**: N parallel `acquire_remote_claim` calls against one mock ticket → assert a
  single winner (extends the ABS-36 §8 concurrency test from intra-runner to inter-runner).
- **E2E dry-run**: `--dry-run` logs `CLAIM`/`SKIP-CLAIMED` intents without staking real comments.
- **Live smoke**: two checkouts, two `ORCH_INSTANCE_ID`s, one Jira ticket labelled
  `orchestrator-ready` → confirm one spawn, one `SKIP-CLAIMED`, and measure comment-visibility
  latency to tune the settle window.

---

## 10. Rollout

**There is no mixed-fleet phase, so backward compatibility is a non-driver.** The confirmed plan:
a single orchestrator runs today; existing tickets finish under it unaffected; the **second
orchestrator is only introduced once this feature is complete**. The rollout is therefore a single
deliberate switch, not per-machine discipline:

1. Ship stories 1–6 with `ORCH_CLAIM_MODE=off`. The solo runner is untouched (the adapter `claim`
   kind is inert until posted), and dev runs stay comment-noise-free.
2. When ready to add the second machine, set `ORCH_CLAIM_MODE=on` on **both** at once. Because the
   fleet goes from one→two in one step (never a lingering mix of on+off runners), the
   silent-double-spawn hazard of a half-configured fleet **cannot occur** — so no peer-detection
   interlock is built (explicitly rejected below).
3. Tune `ORCH_CLAIM_SETTLE_MS` from the two-machine live smoke before relying on it.

---

## 11. Story breakdown (proposed; sizes are rough)

| # | Story | Enabler? | Notes |
|---|---|---|---|
| 1 | Adapter `claim` comment kind (mock + jira + contract) **+ comment-pagination verification/fix in `cmd_get`** | enabler | §5; unblocks all others |
| 2 | `ORCH_INSTANCE_ID` mint-once-per-checkout + reuse-on-restart | enabler | §4.1 |
| 3 | `acquire_remote_claim` (whole-ticket) + settle/jitter/TTL (server-timestamp based) + **in-spawn watchdog heartbeat + handoff touch** + intents | — | §4.3–4.4, §6 core |
| 4 | Wire Tier 2 into `dispatch` behind `ORCH_CLAIM_MODE` | — | §7 |
| 5 | Optional `ORCH_CLAIM_ASSIGN` cosmetic layer | — | §3 Candidate A |
| 6 | Unit + concurrency + E2E tests | — | §9 |
| 7 | SOP: multi-orchestrator operating mode + one-step on→on switch | — | docs; §10 |
| 8 | (optional) claim-comment janitor | — | §8.4 |

---

## Rejected alternatives (recorded)

- **Assignee-only CAS** (Candidate A as the claim of record) — needs one Jira user per machine and is
  probabilistic; kept only as a cosmetic layer.
- **Transition CAS** (Candidate C) — truly atomic but demands claim-substates across three trackers'
  workflow schemas; too invasive and not tracker-neutral.
- **External lock service** (Redis/etcd/DynamoDB lease) — a truly atomic distributed lock, but adds a
  hard runtime dependency the boilerplate deliberately avoids (zero-dependency bash+adapter ethos,
  ADR-A-0009). Reconsider only if tracker-based claiming proves too latency-bound in practice.
- **Peer-detection interlock** (heartbeat + warn/pause when a peer is active but claiming is off) —
  unnecessary given the confirmed one→two rollout (§10): there is never a mixed on+off fleet to
  protect against. Revisit only if the operating model later allows runners to join with claiming
  disabled.
