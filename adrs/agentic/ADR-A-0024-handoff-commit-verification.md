---
id: ADR-A-0024
title: Handoff commit verification — the runner verifies claimed hashes before it accepts a handoff
status: proposed           # human-only acceptance (ADR-A-0004)
scope: agentic
date: "2026-07-13"
---

> **Renumber note (ABS-255, 2026-07-13).** Authored as `ADR-A-0022`; renumbered to
> `ADR-A-0024` to resolve a four-way parallel-branch collision on `0022`
> (ABS-254, ABS-255, ABS-256, ABS-258 each grabbed it independently while `main`
> topped out at `0021`). `ADR-A-0022-agent-def-overlays` (ABS-258) is already on
> `origin` **and** the epic integration branch, so it retains `0022`; the remaining
> colliders renumber in ticket-id order (ABS-254 → 0023, ABS-255 → 0024, ABS-256 → 0025).
>
> **Plan completed (ABS-283, 2026-07-14).** Only ABS-255 (this ADR → `0024`) had executed its
> half; ABS-254 and ABS-256 had never moved, leaving `0022` pointing at three decisions.
> ABS-283 finished the renumber (ABS-254 → `ADR-A-0023`, ABS-256 → `ADR-A-0025`) and added
> `tests/test-adr-id-uniqueness.sh`, which now makes this collision class fail mechanically
> instead of silently.

## Context

Seats have repeatedly reported edits as **committed** that never reached the repository.
Consumer-feedback item 14 (Epic ABS-245) records the reference case: the `ui-ux-design` seat
claimed a template reconciliation **twice**; `git log -S` proved that **no ref ever contained
it**, and the downstream `fe-developer` seat **echoed the claim** into its own handoff. Only
the System Architect caught it, by hand, with git.

Two properties of the current design make this failure class both possible and invisible:

1. **Handoff truthfulness is an honor-system rule.** `_common-rules.md` §1 (ABS-137, Evidence-
   Disziplin) already *requires* the seat to run `git status --short` / `git log --oneline -1`
   and to report only the verified end state. Nothing checks it. A rule an LLM seat can
   simply not follow, with no mechanical consequence, is a rule that eventually is not
   followed — and its violation is silent.
2. **A false claim propagates.** The runner posts the handoff as a `kind:handoff` comment and
   applies the declared transition; the next seat reads that comment as ground truth. One
   unverified sentence therefore becomes the shared context of every downstream seat (the
   `fe-developer` echo). The pipeline is *load-bearing on prose*.

The runner already owns everything needed to check the claim: it provisions the worktree and
its branch (`ensure_worktree`), it runs git plumbing directly against `$ORCH_STATE_ROOT`
(10 call sites today, incl. the `done_pr_gate` merge-base gate), and it has a single choke
point through which every accepted handoff passes (`handoff_followthrough`).

This is an `agentic` decision (ADR-A-0001): it governs the orchestrator/handoff contract across
projects, not one project's architecture. Per ADR-A-0004 it ships `status: proposed`; a human
accepts it. ABS-255 carries the code and tests.

## Decision

### (a) Verify in the RUNNER, at the handoff choke point — not in a reviewer-seat template

Commit verification is a **deterministic runner-side gate** in `handoff_followthrough`
(`scripts/orchestrator.sh`), executed **before** `apply_handoff_transition` — i.e. **before the
handoff is accepted**, not after the ticket has already moved.

**Rejected: verification in the reviewer-seat template.** The reference Befund *is* a
reviewer-side failure: `fe-developer` had the claim in front of it and echoed it. A check
expressed as prose in a seat prompt is (i) non-deterministic — an LLM can skip it, be talked out
of it, or hallucinate the verification itself; (ii) duplicated across every reviewing seat, so it
drifts N ways; (iii) billed per seat, per spawn, in tokens and turns. The runner check is
deterministic, lives in exactly one place, runs in two git plumbing calls, costs no tokens, and
cannot be argued with. Reviewer seats keep their existing evidence duties as the *second* line of
defence; they are not the gate.

Consistency note: git is **not** the tracker, so ADR-A-0007 (adapter model) is not in play —
the runner shells git directly here exactly as it already does for worktrees and the PR
merge-base gate.

### (b) The claim must be machine-readable — a `commits:` field in the handoff record

The handoff record (spec §6) gains **one optional field**:

```markdown
## Handoff

- role: <role>
- ticket: <ticket-id>
- commits: <sha> [<sha> ...]      # REQUIRED when this spawn created commits; omit when it created none
- summary: ...
- status: ...
- next: ...
```

`_common-rules.md` §1 is upgraded from "report the verified end state" to: **a seat that
committed MUST name its hashes on the `commits:` line** (it already runs `git log --oneline -1`;
this only makes the output machine-readable). The field is the *only* input the gate parses.

**Rejected: scraping hex tokens out of the handoff prose.** Any `[0-9a-f]{7,40}` heuristic also
matches PR ids, UUID fragments, and colour codes; a false positive on a *blocking* gate costs a
wasted respawn cycle and operator trust. An explicit field yields **zero false positives** by
construction, and it is precisely what the ticket asks for ("Handoffs, die Commits behaupten,
MÜSSEN den Hash nennen").

### (c) The two checks — existence, then reachability

For every hash on the `commits:` line, against `$ORCH_STATE_ROOT`:

1. **Existence** — `git cat-file -e <sha>^{commit}` — the object exists and is a commit.
   Failure ⇒ the hash is **fiction**.
2. **Reachability (branch containment)** — the commit is contained in at least one ref:
   `git for-each-ref --contains <sha> --count=1 refs/heads/ refs/remotes/` is non-empty.
   Failure ⇒ the commit exists as a dangling object but **no ref contains it** (committed on a
   detached HEAD, or on a branch since reset/discarded) — exactly the ground truth `git log -S`
   established in the Befund ("kein Ref enthielt sie je").

Both checks pass ⇒ the handoff is accepted; the flow proceeds unchanged. Any check fails ⇒
**mis-report** (d).

Reachability is deliberately checked against **any** ref, not against the ticket's work branch.
The work-branch name is not fixed — `ensure_worktree` prefers any existing `refs/heads/<ticket>-*`
branch (a seat may name it freely) and only falls back to `<ticket>-auto` — so a branch-scoped
check would mis-fire on legitimate work committed to, say, the epic integration branch. "No ref
contains it" is the unambiguous, zero-false-positive failure the Befund actually describes.

**Fail-open on *cannot check*, fail-closed on *check says no*.** If git is unavailable, the repo
is missing, or the handoff carries no `commits:` field, the gate does nothing (no claim, no
verdict). Only a hash that *demonstrably* fails a check blocks. Live mode only.

### (d) Failure semantics — refuse the handoff, put the work back on the seat that lied

On a mis-report the runner:

1. **Does not apply the declared transition.** The handoff is rejected, not accepted.
2. **Undoes a self-transition — back to the spawn status, which for the dominant implementer
   case is `Ready for Development`.** An implementer is spawned while the ticket rests in
   `Ready for Development` and, per `_common-rules` §7 (claim protocol), self-transitions
   `Ready for Development → In Progress` at the *start* of work. So at handoff time the ticket
   sits in `In Progress` and the undo the runner must perform is **`In Progress → Ready for
   Development`**. This ADR therefore **adds that edge to
   `profiles/neutral/adapters/statuses.yaml`** (`In Progress.next += Ready for Development`).

   **Why this edge, and why `Ready for Development` rather than a rest in place.** `In Progress`
   is `class: resting`: the reconcile sweep never re-derives a spawn from it
   (`orchestrator.sh` maps `In Progress → NOOP`), and STUCK-DETECT on it is NOTIFY-only
   (ABS-195) — so a ticket rested at `In Progress` **orphans**, which is the exact failure this
   ADR exists to prevent. `Ready for Development` is `class: transient`: the sweep re-derives it
   and spawns a fresh implementer to actually commit. The edge is also the one gap in the
   status machine: ADR-A-0002 already routes **every** impl-fix bounce to `Ready for
   Development` (a fresh implementer) — `In Review`, `Security Review`, `Test Prep` all carry
   that edge; `In Progress` was the only active implementation/review stage missing it. The
   live Jira workflow already permits the transition (real operators performed exactly
   `In Progress → Ready for Development` twice on ABS-255's own crash-reroutes); only the
   neutral-profile canonical machine lacked it. Adding it closes an inconsistency rather than
   widening the machine. The backward, non-human transition is counted natively by
   `rework_count()` (AC3, (e)) and bounded by `ORCH_REWORK_LIMIT`, so the bounce cannot loop.
3. **Posts a `gate-results` comment** with the marker line
   `HANDOFF-MISREPORT status=<status> (orchestrator)`, naming **each** failing hash and **which**
   check it failed — so the record is auditable and the next spawn (session-resume) sees exactly
   what was disbelieved.
4. **Rests the ticket.** The sweep re-derives and re-spawns the same seat, which must now really
   commit.

The seat is not "punished" beyond being made to do the work it claimed to have done. The escape
from an endless bounce is the counting in (e), not a special case here.

### (e) Counting — reuse the existing counters, add none (AC3)

A mis-report feeds the **existing** escalation machinery; no third counter is introduced:

| mis-report branch | existing counter it feeds | bound |
| --- | --- | --- |
| Runner transitions the ticket **back** (d.2) | `rework_count()` — a backward transition by a non-human actor is counted natively, with no new code | `ORCH_REWORK_LIMIT` → `escalate_rework` → `Needs PO Decision` |
| Ticket **rested** in place (d.4) | consecutive-marker counting + `escalation_note_stall` (ADR-A-0018 escalation budget), mirroring `record_nomove` / `nomove_count` | `ORCH_RESPAWN_LIMIT` → `Needs PO Decision` |

`record_misreport()` mirrors the proven `record_nomove()` shape (marker → consecutive count since
the last transition → escalate at the limit → note the stall), the same way `epic_join_rest_complete`
mirrors `writelight_enrichment_complete` (ABS-214). A distinct marker (`HANDOFF-MISREPORT` vs.
`HANDOFF-NOMOVE`) keeps the two diagnosable apart while both land in the same budget.

`scripts/skill-mining.sh` counts the new marker into its existing `nomove` signal (one line), so a
seat that mis-reports repeatedly surfaces in the mining report as a prompt-quality defect — which
is what it is.

### (f) Claim without a hash — advisory in v1, explicitly not blocking

A handoff whose prose claims a commit (`committed` / `pushed`) while carrying **no** `commits:`
field violates the (b) contract, but is **not** blocked in v1. It gets a non-counting advisory
comment (`HANDOFF-CLAIM-NOHASH`).

Reason: the only available detector is a prose regex, and it has a real false-positive class —
review and PO seats routinely and correctly write "no code committed; review only". Blocking on
that would bounce honest handoffs. The advisory is free, and it produces exactly the evidence
needed to decide the promotion.

**Promotion criterion (made measurable — PILOT-69 AC2).** The v1 criterion ("false-positive rate
low enough to be tolerable") was never evaluated across the six releases after this ADR, because
nothing counted the advisory — the rate was unmeasured, so the promotion could neither fire nor be
struck. It is now instrumented and bounded:

- **Measure.** `scripts/skill-mining.sh` counts `INTENT-HANDOFF-CLAIM-NOHASH` per role and as a
  run total (a `HANDOFF-CLAIM-NOHASH advisories` line per role + the run-level total in the report
  header). The false-positive class is *structural*, not statistical: an advisory on a
  **committing** seat (`be-developer` / `fe-developer` / any seat whose spawn produced commits) is a
  true signal (it committed and named no hash); an advisory on a **review/PO/QAS** seat is the
  expected false positive ("review only, no commit"). The per-role split makes the two directly
  readable.
- **Criterion.** Promote (f) to the (d) mis-report path **only if**, over one full release, the
  skill-mining report shows the advisory concentrated on **committing** seats — i.e. committing-seat
  advisories are a **non-trivial majority** of the run total AND recur across seats. As long as the
  volume stays dominated by review/PO/QAS seats (the false-positive class), promotion stays parked
  and the gap stays advisory.
- **Deadline / cadence.** Evaluated **at each release retrospective** against that release's
  skill-mining report (the report already runs per orchestrator run). The evaluation is a named
  retro step, not an open-ended "someday"; a release whose report is missing records
  "not-evaluated: no telemetry", never a silent skip.

Until that criterion is met this stays a deliberately **acknowledged residual gap**: a seat that
lies *and* names no hash is only warned about in v1. It is accepted because the primary Befund — a
claim that is *asserted with evidence which does not hold* — is fully closed by (c), and because a
blocking gate with a known false-positive class is worse than an honest advisory (ADR-A-0010).

### (g) Kill-switch — `ORCH_VERIFY_COMMITS`, default-on

Per the ABS-111 convention (every new seam is default-on with an `ORCH_*=0` escape):
`ORCH_VERIFY_COMMITS=1` (default) enables the gate; `=0` restores the pre-ABS-255 behaviour
(handoffs accepted unverified). Fail-open to the legacy path.

## Consequences

- **Handoff truthfulness stops being an honor system.** ABS-137 / `_common-rules` §1 gains a
  mechanical backstop at the one point every handoff passes through.
- **A false claim can no longer propagate.** It is caught at the seat that made it, before the
  transition and before the `kind:handoff` comment becomes downstream context — so no future seat
  can echo it (the `fe-developer` failure is structurally prevented).
- **Cost: two git plumbing calls per handoff that claims a commit.** No network, no tokens, no
  LLM. Handoffs that claim nothing are untouched.
- **New handoff-record field** `commits:`. Optional by parse (absent = no claim), mandatory by
  contract when the spawn committed. Seat definitions and the §6 handoff template are updated
  once; a seat that omits it after committing is (f)-advised, not blocked.
- **No new counter, no new status, no new loop-breaker** — mis-reports resolve through
  `rework_count` / the ADR-A-0018 escalation budget, and terminate at `Needs PO Decision` like
  every other stuck-ticket class.
- **One new status-machine edge**: `In Progress → Ready for Development` in
  `profiles/neutral/adapters/statuses.yaml`, so the (d.2) undo of an implementer self-transition
  is legal. It closes a pre-existing gap (the only active impl/review status lacking the
  ADR-A-0002 impl-fix bounce edge) and matches the live Jira workflow, which already allows it.
- **A new failure mode is now visible in the runlog and in skill-mining**: a seat that repeatedly
  mis-reports is surfaced as a prompt-quality defect rather than silently corrupting the record.
- **Residual gap (f):** commit claims that name no hash are advised, not blocked, in v1.
- Latency on a mis-report: one extra sweep (the seat is re-spawned to actually commit) — the same
  cost shape as an existing no-move round.

## Alternatives considered

1. **Verify in the reviewer-seat template** (the ticket's other option). Rejected — see (a): the
   Befund is a reviewer-side failure; prose checks are non-deterministic, duplicated per seat, and
   token-billed. The runner is deterministic, single-point, and free.
2. **Scrape hex tokens from the handoff prose** instead of a `commits:` field. Rejected — see (b):
   false positives on a blocking gate (PR ids, UUIDs, colour codes) are more expensive than the
   contract change.
3. **Treat a mis-report as a SPAWN-CRASH.** Rejected: a crash is a *transient infrastructure*
   fault with backoff semantics (ABS-118). A mis-report is a *content* fault by a seat that ran
   fine — it needs a bounce back to the seat, not an exponential retry delay. Miscategorising it
   would also pollute the crash diagnostics that ABS-151 deliberately sharpened.
4. **Post-hoc audit** (verify claims in a nightly sweep / at the epic JOIN). Rejected: by then the
   false claim is already downstream context and the story may be `Done`. The Befund's whole cost
   was that detection came late and by hand.
5. **A pre-commit / post-spawn hook in `.claude/hooks/`.** Rejected: `.claude/` is
   governor-generated from the pinned `.governor-tag` (ABS-94), so it is not the durable home for
   this logic (same reasoning as ADR-A-0020 (d)); and a hook cannot refuse a *handoff* — only the
   runner can.
6. **Verify branch containment against the ticket's work branch only.** Rejected — see (c): the
   work-branch name is not fixed (`ensure_worktree` accepts any `refs/heads/<ticket>-*`), so this
   would mis-fire on legitimate commits made on the epic integration branch.
7. **Land the (d.2) undo without a new edge** — either rest the ticket at `In Progress`, or
   two-hop it out through `In Review`, or fire a BOUNCE-REROUTE re-spawn. All rejected (ABS-255
   AC2 blocker): resting at `In Progress` orphans (that status re-derives to NOOP, STUCK is
   NOTIFY-only) — the very failure this ADR prevents; a two-hop puts the ticket transiently in a
   review status it never earned and would spawn a reviewer; a bespoke BOUNCE-REROUTE duplicates
   the re-spawn machinery `Ready for Development` already provides. The single `In Progress →
   Ready for Development` edge is the minimal change, and it is the ADR-A-0002 canonical
   impl-fix bounce target the machine was already missing for this one status.

## Related Decisions

- [ADR-A-0006](ADR-A-0006-active-task-tracking.md) — status changes trigger agents; this ADR
  guards the *evidence* attached to the transitions that drive them.
- [ADR-A-0018](ADR-A-0018-cross-visit-blocker-classification.md) — the escalation budget /
  auto-park that bounds a repeating mis-report; no new loop-breaker is added.
- [ADR-A-0010](ADR-A-0010-minimal-change-default.md) — minimal-change default: one field, one
  gate, reused counters, and the deliberate non-blocking (f).
- [ADR-A-0007](ADR-A-0007-adapter-model.md) — the adapter model covers the *tracker*; git is not
  the tracker, so the runner's direct git usage here is in bounds.
- [ADR-A-0020](ADR-A-0020-design-first-story-routing.md) — same shape of decision (runner-side
  mechanical guard over an agent-honored rule) and the `.claude/`-is-generated reasoning.
- [ADR-A-0001](ADR-A-0001-three-level-adr-hierarchy.md) — `agentic` level: a cross-project
  orchestration decision.

## References

- ABS-255 (this decision's ticket; carries the code + tests). Epic ABS-245 (consumer feedback);
  consumer-feedback CSV item 14 (the `ui-ux-design` double claim, `git log -S` disproof, the
  `fe-developer` echo).
- `_common-rules.md` §1 Evidence-Disziplin (ABS-137/ABS-174/ABS-195) — the honor-system rule this
  ADR makes mechanical.
- `scripts/orchestrator.sh`: `handoff_followthrough()` (the choke point),
  `apply_handoff_transition()`, `record_nomove()` / `nomove_count()` (the mirrored shape),
  `rework_count()` / `escalate_rework()`, `escalation_note_stall()` (ADR-A-0018),
  `ensure_worktree()` (branch selection), `done_pr_gate` (precedent: runner-side git gate),
  ABS-111 default-on-with-`ORCH_*=0` convention.
- `scripts/skill-mining.sh`: the `nomove` signal the new marker feeds.
- ABS-214 / ABS-203 — the precedent for a new runner-side follow-through step mirroring an
  existing proven one.
