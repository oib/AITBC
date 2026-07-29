---
id: ADR-A-0025
title: Per-epic merge token — runner-enforced merge serialization, held across a merge-bounce
status: proposed
scope: agentic
date: "2026-07-13"
---

## Status

**Proposed.** Acceptance is a human decision (ADR-A-0004 / ADR-A-0001 — agents cannot accept ADRs).

## Context

ADR-A-0014 (part 2) already decided that story PRs are merged onto the epic's integration branch
**"sequentially per epic, in acceptance order"** — each story rebases onto the latest epic-branch
tip, re-runs CI, merges on green, and the next story then rebases onto the new tip. That policy is
correct and is not in question here. **It was never mechanically enforced**, and the missing
enforcement produced a livelock in a live consumer run.

**Observed failure (ABS-245 consumer feedback, item 15).** A consumer's SPA epic had several stories
touching the same three files (`app.js`, `index.html`, `styles.css`). One story was **rebase-bounced
five times**; every bounce cost a fresh implementer spawn plus a full re-gate walk.

**Root cause — two independent defects that compound:**

1. **No per-epic serialization exists.** `scripts/orchestrator.sh` takes a **per-ticket**
   single-flight lock only (`acquire_lock <ticket>`, `lock_dir_for()` → `$LOCKS_DIR/<ticket>`), and
   `ORCH_MAX_CONCURRENT` (default `3`) permits several seats in flight. Nothing keys a lock by epic,
   so **two sibling stories of the same epic can hold `Merging` and spawn `rte` concurrently**,
   racing to rebase onto and move the same epic-branch tip. ADR-A-0014's "sequentially per epic" is
   a policy with no mechanism behind it — and the `rte` seat, which is a fresh stateless subagent per
   spawn (ADR-A-0002), structurally *cannot* enforce an ordering it cannot observe.

2. **A mechanical rebase conflict bounces to a full re-gate.** `.claude/agents/rte.md` step 5 sends
   **rebase** failures and **CI** failures down the identical path: transition the story to
   `Ready for Development`. The story then re-walks the pipeline (implementer → architect review →
   QAS → PO acceptance → `Merging`). A rebase conflict is not an implementation defect, but it is
   priced like one.

**The cascade is the product of the two.** While bounced story *B* spends the long re-gate walk,
sibling *C* merges and moves the epic tip. *B* returns to `Merging` against a tip that has moved
*again*, conflicts on the same shared file, and bounces *again*. Because the re-gate walk is slower
than the sibling merge rate, *B* can never catch the tip — a livelock, not a race, which is why it
recurred five times rather than resolving itself.

**This is why serialization alone does not fix it.** Serializing merges still lets *C* take its turn
while *B* re-gates, so the tip still moves under *B*. The bounce, not the concurrency, is what makes
the tip a moving target.

## Decision

We introduce a **per-epic merge token**, enforced by the runner, and **held across a merge-bounce**.

**1. Option (a) and option (b) are not alternatives — they are policy and mechanism.** The ticket
framed a choice between (a) a merge queue where the oldest accepted PR holds a token while siblings
wait, and (b) the runner serializing `Merging` spawns per epic. **(a) is the semantics we adopt;
(b) is the only layer that can implement it.** The runner is the sole component with cross-ticket
visibility and a durable lock store; a per-spawn stateless `rte` seat cannot serialize itself. We
adopt (a)'s semantics *via* (b)'s mechanism. No new status and no new queue store is introduced: the
existing `Merging` status **is** the queue, and the existing lock-dir idiom **is** the token.

**2. One merge token per epic.** At most one story of a given epic may occupy the `rte` `Merging`
seat at a time. When a story's dispatch resolves to `Merging`, the runner resolves its epic
(`tracker parent <ticket>`, already available) and attempts to take the epic's merge token. Siblings
that cannot take it are **not spawned** and simply rest in `Merging` — the ticket status is the wait
state, and dispatch retries them on a later sweep. **Ordering is acceptance order**: among waiting
siblings the token goes to the story with the oldest `Story Acceptance -> Merging` transition.

**3. The token is held across a merge-bounce (the load-bearing rule).** When the token holder is
bounced from `Merging` for a rebase or CI failure, it **keeps the token** through
`Ready for Development` and its re-gate walk, and releases it only when it leaves the merge path for
good — reaching `Docs` (merged) or coming to rest at a human/PO gate (`Ready for Merge`,
`Needs PO Decision`). **Consequently the epic tip cannot move while a story is fixing its rebase
against that tip.** When the bounced story returns to `Merging`, it rebases onto the *same* tip it
already resolved against — a clean rebase — merges, and releases the token to the next sibling. This
is what breaks the livelock, and it is the single rule that distinguishes this decision from
restating ADR-A-0014.

**4. The sanctioned epic-branch sync-rebase may not run while a merge token is held.** ADR-A-0014
part 3 permits the epic-branch sync-rebase onto `origin/main` to run *"periodically while the epic
rests in `Stories In Flight`"*. That force-push rewrites the epic tip and would re-invalidate a
token holder mid-fix — reopening the exact cascade this ADR closes. We therefore **narrow that
permission**: the sync-rebase runs **only at `Epic Integration`**, where the JOIN rule (all children
`Done`) guarantees no token is held. The periodic-sync option is dropped, not made conditional —
nothing depended on it, and the mandatory pre-`Ready for Epic Acceptance` sync-rebase (which A-0014
requires and which runs at `Epic Integration`) is unaffected.

**5. Agents gain no conflict-resolution authority.** The token makes the post-bounce rebase clean, so
no agent needs the ability to hand-resolve a conflict. The `#EXPORT_CRITICAL` no-hand-resolve
invariant (ADR-A-0014 part 3) stands untouched, and no `main` boundary (ADR-A-0004 / ADR-A-0005)
moves.

**6. Conflict-magnet reduction stays a separate enabler — deliberately not bundled here.** The local
proposal `work/improvement-proposals/2026-07-11-reduce-shared-file-conflict-magnets-at-epic-integration.md`
addresses a **different surface**: conflicts between the *epic branch and `main`* at the
`Epic Integration` sync-rebase (monolithic `tests/test-orchestrator.sh`, the single-line
`ORCHESTRATOR_SOP` version header). This ADR addresses conflicts between a *story branch and the
epic tip* at `Merging`. They share a symptom, not a mechanism: the merge token cannot help the
epic↔`main` rebase (nothing serializes `main`), and splitting conflict magnets cannot help the
story↔epic-tip cascade (shared files are the consumer's own SPA files, which the boilerplate cannot
restructure). The proposal remains valid on its own merits and should be filed as its own enabler;
merging the two would couple a correctness fix to a toil fix and delay both.

## Implementation Notes

Non-binding sketch for the implementing seat — the decision is above; these are the anchors that
already exist, so that the smallest diff is the obvious one.

- **Token store** — reuse the existing atomic `mkdir` lock idiom of `acquire_lock()`, keyed by epic:
  `$LOCKS_DIR/merge/<epic-id>`, recording the holding story id. Reuse `ORCH_LOCK_TTL` stale-reclaim
  so a crashed `rte` seat cannot wedge an epic forever.
- **Acquire** — in `dispatch()`, on `to_status == Merging`: resolve the epic via
  `tracker parent <ticket>` (already used at `scripts/orchestrator.sh` ~line 3105 / `fm_field <dump>
  parent`). Token free, or already held by *this* story (re-entry after a bounce) → spawn `rte`.
  Held by a sibling → **do not spawn**, log a `MERGE-QUEUE-WAIT` intent line, leave the ticket resting
  in `Merging`.
- **Release** — on the holder reaching `Docs`, `Ready for Merge`, or `Needs PO Decision`. **Not** on
  the bounce to `Ready for Development` (that is decision 3's hold).
- **Head-of-line safety** — a genuinely broken holder stalls its epic's merging. This is bounded by
  the existing ABS-74 rework counter, which routes a story at the rework limit to `Needs PO Decision`
  (a human gate) — which also releases the token.
- **Kill-switch** — `ORCH_MERGE_QUEUE=1` (default on); `=0` restores today's unserialized behavior in
  one env edit, per the boilerplate's kill-switch convention (cf. `ORCH_AUTOMERGE`,
  `ORCH_DESIGN_FIRST_ROUTING`).
- **Telemetry (ticket AC3)** — reuse the existing rework-count derivation over transition reasons,
  filtered to `actor=rte`, to report merge-bounces per story/epic. No new metrics store.
- **Test (ticket AC2)** — in the mock-tracker harness: two stories of one epic touching the same
  file, both accepted → assert the second is **not** spawned while the first holds the token, and
  that it incurs **at most one** bounce (never a second) because the tip is frozen during its fix.

## Consequences

### Positive

- The five-bounce livelock is structurally impossible: the tip cannot move under a story that is
  fixing its rebase against that tip.
- ADR-A-0014's "sequentially per epic, in acceptance order" finally has a mechanism; the policy stops
  depending on a stateless seat's good behavior.
- Cost falls where it hurt most — each avoided bounce removes a fresh implementer spawn plus a full
  re-gate walk (architect, QAS, PO).
- No new status, no new queue store, no new seat, no new agent authority. The change is confined to
  `dispatch()` plus one lock helper.
- Reversible in one env edit (`ORCH_MERGE_QUEUE=0`).

### Negative

- **Head-of-line blocking**: a slow or repeatedly-failing token holder stalls its epic's remaining
  merges. This trade-off is **not new** — ADR-A-0014 already accepted it explicitly ("a stuck
  rebase/CI on one story stalls the remainder of that epic's integration, bounded by the story's
  rework counter"). This ADR makes it real rather than introducing it, and the rework counter →
  `Needs PO Decision` remains the bound.
- Merge throughput within a single epic is capped at one story at a time (across epics, unchanged).
  For epics whose stories touch disjoint files this serialization is pure overhead — accepted as the
  price of not having to detect file overlap.
- The **first** bounce of a conflicting story still costs a full re-gate walk; only the *repeat*
  bounces are eliminated. Cheapening the first bounce (a shallow re-entry that skips gates for a
  rebase-only fix) would move a quality-gate boundary and is **explicitly out of scope** — the
  ticket's AC is "no double bounce", and YAGNI applies until the single bounce is shown to be the
  dominant cost.
- One more lock class to reason about and to reclaim on crash (mitigated by reusing the existing TTL
  reclaim rather than writing a new one).

### Neutral

- Dropping ADR-A-0014's optional periodic sync-rebase (decision 4) removes an unused permission, not
  a used capability; drift against `main` is still resolved by the mandatory sync-rebase at
  `Epic Integration`.

## Alternatives Considered

- **`ORCH_MAX_CONCURRENT=1`** (global serialization). Rejected: it serializes *every* seat across
  *all* epics — a global throughput collapse to fix a per-epic problem — and it still does not freeze
  the tip across a bounce, so the livelock survives.
- **Serialization without the cross-bounce hold** (a plain merge queue). Rejected: this is the
  intuitive reading of ticket option (a)/(b), and it does **not** fix the reported failure. Siblings
  still take their turn while the bounced story re-gates, the tip still moves under it, and the story
  still bounces repeatedly. Decision 3 exists precisely because this weaker option was tempting.
- **Let `rte` hand-resolve trivial story-level rebase conflicts.** Rejected: it moves a trust
  boundary (agents resolving conflicts unreviewed) to buy something the token already gives us for
  free.
- **Merge story PRs with a merge commit instead of rebasing.** Rejected: it destroys the linear,
  ticket-tagged history that ADR-A-0014 part 4's `git bisect` mechanic depends on.
- **Detect file overlap between sibling PRs and serialize only the overlapping ones.** Rejected as
  over-engineering: it adds diff-intersection machinery to save a serialization that costs little,
  and it fails open (a missed overlap silently restores the cascade).

## Related Decisions

- **ADR-A-0014** (Workflow v3 — per-epic integration branch; gated auto-merge) — **refined, not
  superseded.** This ADR supplies the missing enforcement for its part-2 "sequentially per epic"
  policy, and **narrows its part-3 permission** for the epic-branch sync-rebase to `Epic Integration`
  only (decision 4). A-0014's decisions otherwise stand unchanged; its `main` boundaries are
  untouched.
- **ADR-A-0004** (Human approval boundaries) — untouched: no agent gains any merge-to-`main` or
  conflict-resolution authority.
- **ADR-A-0005** (Mandatory PRs) — untouched: every story still reaches the epic branch via a PR.
- **ADR-A-0002** (Fresh task-scoped subagents) — the reason enforcement must live in the runner: the
  `rte` seat is stateless per spawn and cannot serialize itself.
- **ADR-A-0010** (Minimal-change default) — the basis for rejecting file-overlap detection and the
  bundling of the conflict-magnet proposal.

## References

- Ticket **ABS-256** (this decision); epic **ABS-245** (consumer feedback); consumer-feedback CSV
  item 15 (the five-bounce episode).
- `work/improvement-proposals/2026-07-11-reduce-shared-file-conflict-magnets-at-epic-integration.md`
  — the adjacent (epic↔`main`) conflict-magnet problem, deliberately kept separate (decision 6).
- `scripts/orchestrator.sh` — `lock_dir_for()` / `acquire_lock()` (per-ticket lock, ~line 3195),
  `ORCH_MAX_CONCURRENT` (~line 238), epic resolution via `tracker parent` (~line 3105).
- `.claude/agents/rte.md` — `Merging` seat duty; step 5 (the rebase/CI bounce to
  `Ready for Development`).
- `specs/ABS-69-workflow-v3-full-agent-team-spec.md` §3.5 — merge and integration policy.
