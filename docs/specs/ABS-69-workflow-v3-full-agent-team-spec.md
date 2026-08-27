# Design Spec — Workflow v3: Full Agent Team, Two Human Touchpoints

**Ticket**: ABS-69 (epic) · **Status**: accepted · **Date**: 2026-07-05 (accepted 2026-07-06)
**Author role**: BSA / System Architect (drafted with POPM) · **Diagram**: [assets/workflow-v2.drawio](assets/workflow-v2.drawio) (v3 pipeline diagram; filename retained from the draft)

> **History.** Drafted as `DRAFT-workflow-v2-full-agent-team-spec.md` (proposal, 2026-07-05);
> promoted to this accepted spec under epic **ABS-69** (which starts Boilerplate v3) on 2026-07-06.
> Section numbering (§1–§6), scenario ids (S1–S16), and the design decisions §3.1–§3.10 are
> unchanged from the draft so the child stories (ABS-70..ABS-90) and the executable definition
> (`tests/e2e-workflow-v3.sh`, ABS-80) keep referencing them verbatim. The historical "v2" naming
> survives only in the diagram filename and the simulation reference.

Extends the ABS-36 orchestrator so that **every agent role has an automated seat** in the
workflow (all 16 roles except `boilerplate-migration`), and the human's involvement collapses to:

1. **Create an epic** (the only manual start step)
2. **Get notified when the epic is deployed to staging and ready to test** (accept / reject)
3. Genuinely human-only escalations only (credentials, cost, new features, merges-by-exception — ADR-A-0004)

Grounded in the reachability audit of 2026-07-04/05: today only 7 of 17 roles have a live automated
path; 5 have documented handoffs no automation can execute (BSA, issue-enrichment, self-improvement,
TDM, RTE); ui-ux-design/qas-design are human-triggered; security-engineer and data-provisioning-eng
are orphaned. This spec seats them all via the existing mechanism: **status → fresh single-ticket
spawn** (ADR-A-0002, ADR-A-0006, ADR-A-0009 — unchanged).

---

## 1. Pipelines

### 1.1 Epic pipeline (one ticket per epic)

| Status | Spawn | Duty |
|---|---|---|
| `PO Triage` | po-agent | scope, WSJF priority, guardrails; human-only asks → escalation inbox |
| `Grooming` | bsa | decompose into story drafts with specs + testable ACs; set `design` / `security` / `data` flags |
| `Enrichment` | issue-enrichment | dedup gate, agent-ready formatting, guardrail annotation, creates child tickets with `role:` hints |
| `Ticket Review` | qas | **Definition-of-Ready gate** over all children as a batch: testable ACs, flag consistency, dependency + coverage check, blind-spot catalog; verdicts `ready` / `rework` / `open question` (§3.10) |
| `Architecture Review` | system-architect | epic-level pattern selection, `#PATH_DECISION` check; releases stories |
| *(stories in flight — epic rests; JOIN rule §3.1 advances it)* | — | — |
| `Epic Integration` | rte | sync-rebase epic branch onto `main`; staging deploy + smoke run; on fail: `git bisect` the ticket-tagged commits → reopen offending story (§3.5) |
| `Ready for Epic Acceptance` | — (NOTIFY human) | **the** notification: "epic ready to test" |
| `Epic Done` | self-improvement | retro + skill mining + improvement proposals → escalation inbox (fixes the dead trigger) |

### 1.2 Story pipeline (per child story)

| Status | Spawn | Notes |
|---|---|---|
| `Design` | ui-ux-design | **conditional** (`design` flag): design + design ACs — implementer input AND later test contract |
| `Implement` | be- / fe- / data-engineer | selected by `role:` frontmatter (default `be-developer`) |
| `Code Review` | system-architect | read-only (ABS-57 toolset narrowing, unchanged) |
| `Security Review` | security-engineer | **conditional** (`security` flag): RLS, authz, injection surface; independence gate, not collapsible |
| `Test Prep` | data-provisioning-eng | **conditional** (`data` flag): fixtures, seeded data, RLS test contexts |
| `In Test` | qas | functional ACs + evidence |
| `Design Test` | qas-design | **conditional** (`design` flag): implemented UI vs design ACs; classifies impl-fix vs design-fix bounce |
| `Story Acceptance` | po-agent | accept/reject vs ACs (replaces per-story human gate) |
| `Merging` | rte | **sequential per epic**: rebase onto latest epic branch, CI, auto-merge onto the epic branch on green (§3.5) — never merges to `main` |
| `Docs` → `Done` | tech-writer | story documentation |

`#PATH_DECISION` — **QAS and QAS-Design run serially, not in parallel.** The orchestrator's
state machine holds one status per ticket and one in-flight lock per ticket; a parallel gate needs
per-(ticket, role) locks plus a second-finisher join rule. Serial costs one extra hop on
design-flagged stories only and needs zero new orchestrator concepts. Parallelism is a v2.2
optimization, not part of this spec.

### 1.3 Cross-cutting

| Trigger | Spawn | Duty |
|---|---|---|
| `Blocked` (any stage) | tdm | classify environment / external / scope; resolve or reroute; escalate only human-only calls. Spawn once per Blocked entry (comment-keyed guard, same pattern as ABS-62 re-raise guard) |
| `Needs PO Decision` | po-agent | unchanged (ABS-61) + rework raises (§3.2) |
| Follow-up recommendation (comment) | bsa (via sweep, §3.4) | decide create / in-scope / discard; `create` → issue-enrichment → **Backlog outside the epic** unless marked AC-blocking |

---

## 2. Agent seat descriptions

- **PO-Agent** — product authority at three seats: epic triage, story acceptance, on-demand decisions (incl. stall + rework raises).
- **BSA** — grooming owner: specs, testable ACs, conditional-stage flags; decides all follow-up recommendations.
- **Issue Enrichment** — the single ticket creator, now actually spawned (no more inline-skills exception for the batch case).
- **System Architect** — epic-level architecture review + story-level read-only code review.
- **UI/UX Design** — pre-implementation: design + measurable design ACs.
- **QAS-Design** — post-implementation: verifies the *running* UI against the design ACs; bounces classified impl-fix vs design-fix.
- **be-/fe-/data-engineer** — implementers by `role:` hint.
- **Security Engineer** — independent security gate on security-flagged stories; files follow-ups.
- **Data Provisioning Engineer** — test prep on data-flagged stories so QAS never bounces on missing setup.
- **QAS** — functional AC validation + evidence; additionally the epic-level Definition-of-Ready
  gate at `Ticket Review` (independent of the ticket authors BSA / issue-enrichment; the core
  question — "can I test against these ACs later?" — is QAS's home turf, §3.10).
- **RTE** — story merge automation onto the epic's integration branch (sequential rebase + CI + auto-merge on green; never merges to `main`) and epic staging integration; fires the ready-to-test NOTIFY.
- **Tech Writer** — per-story docs (unchanged).
- **TDM** — blocker triage from any stage; binding classification on fixer ping-pong.
- **Self-Improvement** — auto-spawned on `Epic Done`: retro, skill mining, proposals.

---

## 3. Design decisions (from theoretical scenario testing, 2026-07-05)

Eight scenarios were traced against the runner mechanics (single-status machine, per-ticket
in-flight lock, spawn budget, iteration guard, reconciliation sweep). Six produced defects; the
fixes below are part of this spec. Scenario traces are the acceptance test cases (§5).

### 3.1 JOIN rule — fan-in for "all stories done"  `#EXPORT_CRITICAL`

The sweep gains a mechanical rule: on any child story reaching `Done`, count siblings via the
adapter; when **all original children + AC-blocking additions** are `Done`, transition the epic to
`Epic Integration`. Bash-only, no LLM (ADR-A-0009). Without this rule the ready-to-test
notification never fires — it is the core promise of v2.

### 3.2 Per-ticket rework counter

Any bounce (orange edge) increments a single per-ticket counter, independent of which stage pair
bounced. At 3 → `Needs PO Decision` instead of a re-spawn. Closes the blind spot where a
design-fix loop (5 stages, ~6 spawns per traversal) cycles under the pairwise iteration guard.

### 3.3 SKIP-FORWARD action class — conditional stages are the orchestrator's job

On a transition into `Design` / `Security Review` / `Test Prep` / `Design Test`, the runner reads
the ticket's flags via the adapter; when unflagged it re-transitions to the next status itself
(audit comment, no spawn). Agents never carry routing logic in their prompts.

### 3.4 Follow-up watcher + containment

The sweep scans for `kind: follow-up` comments without a `bsa-decision` reply → spawns BSA on that
ticket. Created follow-up stories default to **Backlog outside the epic**; BSA may attach one to
the current epic only by marking it **AC-blocking** (counted by the JOIN rule). Per-epic follow-up
budget: 5; overflow → `Needs PO Decision`. Prevents quality gates from starving epic completion.

### 3.5 Merge and integration policy  `#EXPORT_CRITICAL`

- Each epic gets a **per-epic integration branch** (`epic/AITBC-XX-{description}`).
  **The RTE `Merging` seat owns its creation**, lazily — as step 0 of merging the epic's first
  accepted story: if `origin/epic/…` does not yet exist, RTE creates it off `origin/main` and pushes
  it, then merges the story; every later story finds it present. **Story PRs target the epic branch,
  never `main`.** Agents never merge to `main` — no environment knob changes that (ADR-A-0014).
- RTE merges an epic's stories **sequentially in acceptance order onto the epic branch**,
  re-rebasing onto the epic branch's latest tip and re-running CI after each merge (rebase-first,
  unchanged from CONTRIBUTING.md).
- Auto-merge on green CI applies **only to story merges onto the epic branch** — it replaces the
  per-story human merge *onto the epic branch* with a CI gate; it does **not** touch the human gate
  at `main`. Branch protection on the epic branch leans entirely on CI once active; branch
  protection on `main` is unchanged (human merge required, ADR-A-0004/0005, both respected). Letting
  agents integrate each other's accepted stories on the epic branch without per-story human review
  is a real but **contained** trust decision (a human still tests and merges every epic PR to
  `main`) and needs explicit human sign-off — ADR-A-0014, a standalone decision *within* the
  ADR-A-0004/0005 `main` boundaries, not an amendment to them.
- The epic branch is kept current with `main` by the **single sanctioned rewrite**: RTE rebases it
  onto `origin/main` and pushes `--force-with-lease` (never a forward-merge — that would break the
  linear, ticket-tagged history). It runs at least immediately before RTE releases the epic to
  `Ready for Epic Acceptance` (i.e. before the human opens the epic PR), and may run periodically
  during `Stories In Flight`; it is safe because in-flight story branches re-rebase onto the epic tip
  at merge time regardless.
- **Sync-rebase conflict** (main drift / a second epic touched the same files) → RTE runs
  `git rebase --abort` (epic branch untouched, no partial rewrite) and transitions the epic to
  `Blocked` with the conflicting paths in the blocker comment. The v3 Blocked flow (§3.7) takes
  over: TDM triages, and resolution resumes the epic to its pre-blocked status (`Epic Integration`)
  to retry. An agent never hand-resolves the conflict (that would push unreviewed integration into
  what the human tests).
- The **only** path from an epic branch to `main` is a human-merged PR at `Ready for Epic
  Acceptance`, after the human tests the integrated epic on staging.
- Epic Integration smoke failure → RTE runs a mechanical `git bisect` over the epic branch's
  **linear, ticket-tagged commit range**, with endpoints defined explicitly (the smoke runs after
  the sync-rebase): `git bisect start <epic-tip> <merge-base(epic, origin/main)>` — **bad** = the
  current epic-branch tip, **good** = the post-sync-rebase merge-base with `origin/main` (carries no
  story commits), smoke hook as the predicate. Isolates the culprit commit → maps it to its story via
  the `[AITBC-XXX]` tag → reopen + bounce that story (the epic branch is never reset —
  the reopened story's fresh merge lands on top of the current epic-branch tip); no tag / ambiguous
  mapping → `Needs PO Decision`.
- **No agent ever reverts main, and no agent resets the epic branch (except the sanctioned
  sync-rebase onto `origin/main` above).** Epic rejection is forward-fix: human feedback →
  `Grooming` → new/changed stories that merge onto the still-living epic branch → re-propose the
  epic PR. Reverts of `main` are human-only; by construction `main` carries no epic's unaccepted
  work, so there is nothing on `main` for an agent to revert.

### 3.6 JOIN guards: no vacuous fire, no follow-up race  `#EXPORT_CRITICAL`  *(round-2 findings)*

- **Empty-epic guard**: if grooming/enrichment yields zero children, the JOIN condition is
  vacuously true — without a guard the epic would deploy nothing and notify the human. Zero
  children at JOIN evaluation → `Needs PO Decision` instead.
- **Quiescence guard**: a story can post a follow-up comment and hit `Done` in the same cycle; if
  JOIN evaluates before the watcher processes the comment, an AC-blocking follow-up loses the race
  and the epic integrates without it. JOIN therefore only fires when the epic has **no unprocessed
  follow-up comments**; the sweep runs watcher → JOIN re-check, in that order.

### 3.7 Blocked applies to the epic pipeline too  *(round-2 finding)*

Epic seats (BSA missing domain input, enrichment hitting tracker limits, …) can block just like
implementers. `Blocked` stores the pre-blocked status; TDM spawns once per entry (same guard);
human resolution resumes the ticket **to the status it blocked from**, not to a fixed stage.

### 3.8 Spawn-failure escalation  *(round-2 finding)*

The sweep's crash-recovery re-derive is a retry loop with no exit: a deterministically-crashing
seat (bad prompt, oversized packet) would be re-spawned every cadence forever. Consecutive crash
counter per (ticket, status): resets on success, at 3 → `Needs PO Decision`. Complements the
existing spawn-adapter single retry.

### 3.9 Safety wiring for new statuses

Every new agent-owned status: added to `is_reconcilable_status()` (crash recovery) and covered by
stall detection with the comment-keyed re-raise guard. Human-owned states (`Ready for Epic
Acceptance`, `Blocked`) rest. Spawn budget becomes per-day, sized for ~2 epics
(`#PLAN_UNCERTAINTY`: measure a real epic first — estimate is 80–100 spawns for a 10-story epic).

### 3.10 Ticket Review — Definition-of-Ready gate before story release  *(round-3 addition)*

Bounce loops in the story pipeline (code review, QAS, design test) are mostly *symptoms* of
tickets that were never fully thought through; §3.2 only caps those loops, it does not prevent
them. `Ticket Review` moves the check to the front: after `Enrichment`, before
`Architecture Review`, one **qas** spawn reviews **all child tickets as a batch** against a
Definition-of-Ready checklist (`docs/sop/DEFINITION_OF_READY.md`, new).

- **Seat = qas, not a new role**: the reviewer must be independent of the authors (BSA drafted,
  issue-enrichment formatted — same non-collapsible-gate logic as `Security Review`), and the
  decisive lens is testability (shift-left / three-amigos). Cost: exactly +1 spawn per epic.
- **Checklist (per ticket)**: every AC measurable/testable (no "works correctly");
  `design`/`security`/`data` flags consistent with content; `role:` hint plausible; scope small
  enough for one single-ticket spawn; pattern/spec references present; no unresolved
  `#PLAN_UNCERTAINTY` without a resolution path.
- **Cross-story checks (the batch advantage)**: overlaps/duplicate work between stories,
  dependencies explicit and acyclic, and a mandatory **coverage mapping** — every goal in the
  epic text must map to ≥1 story AC; an unmapped goal is a `rework` verdict naming the gap.
  Without an explicit mapping instruction *any* reviewer only checks tickets in isolation and
  misses what is absent.
- **Blind-spot catalog**: a fixed question list held against every story — error/edge cases,
  authz/RLS, migrations for existing data, idempotency, observability, rollback. Catches the
  recurring categories of "forgotten points"; QAS's what-if lens is the best fit here.
- **Three verdicts**:
  - `ready` (all children) → `Architecture Review`;
  - `rework` → bounce to `Grooming` with the concrete defect list (BSA fixes, enrichment
    updates tickets). The per-ticket rework counter (§3.2) applies to the **epic ticket**:
    3 bounces → `Needs PO Decision` — no new guard mechanics needed;
  - `open question` — anything the reviewer cannot decide is never guessed but escalated to
    `Needs PO Decision`; po-agent triaged the epic and is the product authority. This is the
    structural mitigation for the one class no gate can catch from ticket text alone:
    unwritten domain knowledge.
- **Ordering** `#PATH_DECISION`: DoR *before* `Architecture Review`, so the architect reviews and
  releases only complete tickets (reviews once, not twice). Rejected alternative: folding the
  checklist into `Architecture Review` — cheaper (no new status) but mixes two verdict types
  with different return routes in one spawn and breaks one-seat-one-duty.

---

## 4. Required changes

1. **orchestrator.sh** — extended `map_action` table (§1), JOIN rule, rework counter, SKIP-FORWARD,
   follow-up watcher, per-(status) safety wiring, per-day budget.
2. **Adapters** — new canonical statuses in `profiles/neutral/adapters/statuses.yaml` + mock adapter;
   Jira workflow must add the statuses (ops task — same blocker class as ABS-64 live smoke).
3. **Ticket schema** — `design` / `security` / `data` flags + `ac-blocking` marker (frontmatter/labels,
   mirroring the existing `role:` hint mechanism).
4. **CI / branch protection** — auto-merge policy, staging deploy + smoke entry point for RTE.
5. **Agent definitions** — seat-specific prompt sections (e.g. QAS-Design bounce classification,
   TDM once-per-entry, RTE merge/bisect procedures, QAS Ticket-Review seat: DoR checklist +
   coverage mapping + blind-spot catalog + three-verdict output, §3.10); fix qas/qas-design
   `tools:` frontmatter (single-line flow lists — separate task already flagged).
6. **SOPs** — PO_AGENT_SOP (triage seat, rework raises), FOLLOW_UP_TICKET_SOP (watcher, AC-blocking,
   budget), AGENT_WORKFLOW_SOP (retire Method 2 TDM-orchestration; TDM = blocker triage),
   SELF_IMPROVEMENT_SOP (auto-trigger on `Epic Done`), new EPIC_LIFECYCLE section in ORCHESTRATOR_SOP,
   new **DEFINITION_OF_READY.md** (DoR checklist, coverage-mapping rule, blind-spot catalog —
   referenced by the QAS Ticket-Review seat prompt, §3.10).

---

## 5. Acceptance test cases

Executable as a spec-level simulation: `python3 tests/workflow-v2-sim.py` (all sixteen pass;
mutation checks confirm the suite fails when the JOIN rule, SKIP-FORWARD, or the rework counter
is removed). Evidence: [docs/agent-outputs/qa-validations/DRAFT-workflow-v2-sim-results.md](../agent-outputs/qa-validations/DRAFT-workflow-v2-sim-results.md).
The **executable definition** of the landed workflow is `tests/e2e-workflow-v3.sh` (ABS-80) — the
same S1–S16 scenarios re-run as deterministic bash dry-runs against the real `scripts/orchestrator.sh`
+ mock adapter; it is the epic's exit gate (like ABS-55 for ABS-36). The python sim is retained as
the spec-level reference; the `tests/workflow-v2-sim.py` filename and the sim-results doc path keep
their historical "v2" naming.

- [x] **S1 Happy path** — 3-story epic (1 design-flagged): every stage spawns exactly once per story;
      JOIN fires after last `Done`; human receives exactly one ready-to-test NOTIFY.
- [x] **S2 Design flaw in test** — design-fix bounce re-runs Design→…→Design Test; rework counter
      reaches 3 → `Needs PO Decision`, no budget blow-up.
- [x] **S3 Design-flagged test sequence** — `In Test` pass → `Design Test` spawn; unflagged story
      SKIP-FORWARDs past `Design Test` with an audit comment and no spawn.
- [x] **S4 Plain story** — no flags: `Security Review`, `Test Prep`, `Design Test` all SKIP-FORWARD;
      total spawns for the story = 5 (implement, review, qas, acceptance, merge) + tech-writer.
- [x] **S5 Combination break** — two individually-green stories; sequential merge catches the conflict
      at the second story's rebase (bounce), or the integration bisect reopens the offending story.
- [x] **S6 Blocked on credentials** — TDM spawned once per Blocked entry, classifies human-only,
      escalation NOTIFY sent; human unblocks; sweep re-derives the implementer spawn.
- [x] **S7 Follow-up storm** — 6 follow-ups filed: 5 created outside the epic, 6th → `Needs PO
      Decision`; JOIN unaffected unless BSA marked one AC-blocking.
- [x] **S8 Crash + rejection** — killed spawn mid-`Architecture Review` recovered by reconcile sweep;
      human epic rejection routes feedback to `Grooming` (forward-fix), main untouched.

Round 2 (2026-07-05, added while extending the suite — S10/S11/S14/S15 each exposed a new defect,
fixed by §3.6–3.8):

- [x] **S9 Concurrent epics** — two epics in flight: JOINs, notifies and follow-up budgets fully
      isolated per epic.
- [x] **S10 Empty epic** — zero groomed stories → `Needs PO Decision`, no vacuous ready-to-test
      NOTIFY (§3.6 empty-epic guard).
- [x] **S11 AC-blocking follow-up** — filed in the same cycle the last story finishes: JOIN waits
      (quiescence, §3.6), BSA attaches the child, epic integrates only after it is Done.
- [x] **S12 Cross-stage rework** — three different reviewers bounce once each: the single
      per-ticket counter reaches 3 → `Needs PO Decision` (would be invisible to pairwise guards).
- [x] **S13 Max-flag story** — design+security+data runs all 10 stages: 10 story spawns,
      16 spawns total to NOTIFY incl. the Ticket-Review gate (upper cost pin per story).
- [x] **S14 Epic-level Blocked** — BSA blocks during grooming: TDM once per entry, resume returns
      to `Grooming` (pre-blocked status, §3.7).
- [x] **S15 Deterministic crash** — implementer crashes every spawn: 3 consecutive crashes →
      `Needs PO Decision` instead of an infinite retry loop (§3.8).

Round 3 (2026-07-05, Ticket-Review / Definition-of-Ready gate, §3.10):

- [x] **S16 DoR gate** — epic with un-ready tickets: `Ticket Review` bounces to `Grooming` with
      the defect list; **no story is released before the gate passes**; third bounce →
      `Needs PO Decision` via the epic ticket's rework counter (§3.2). Mutation check: suite
      fails when the gate is removed (`dor_gate` disabled).

---

## 6. Open questions  `#PLAN_UNCERTAINTY`

1. Real spawn-count and cost profile per epic (calibrate per-day budget + `ORCH_MAX_TURNS` per seat).
2. Staging deploy mechanics for RTE (project-specific `{{DEPLOY_COMMAND}}`; boilerplate ships the seam only).
3. Whether `Security Review` should also be mandatory on `data`-flagged stories (RLS overlap).
4. NOTIFY transport (current: notify seam in runner; candidate: PushNotification / tracker mention).
5. Rollout order — suggested: SKIP-FORWARD + new statuses first (inert), then seats one gate at a
   time (BSA/enrichment → design pair → seceng/DPE → TDM), auto-merge last (needs ADR-A-0014
   accepted — the standalone epic-branch auto-merge decision).
