# Definition of Ready Standard Operating Procedure (SOP)

**Purpose**: Define the Definition-of-Ready (DoR) gate the QAS **Ticket Review** seat runs over an
epic's child tickets before any story is released — the checklist, the mandatory coverage-mapping
rule, the blind-spot catalog, and the three verdicts with their exit transitions

**Version**: 1.0 (ABS-69 / ABS-79, spec §3.10)
**Last Updated**: 2026-07-06

---

## Overview

`Ticket Review` is a v3 epic-pipeline status (`Enrichment → Ticket Review → Architecture Review`).
The Coordinator maps entry to **SPAWN qas** ([`docs/sop/ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md)
"Epic Lifecycle"). A fresh QAS is spawned **once per epic**, after Enrichment has created the child
tickets, and **batch-reviews ALL of the epic's children** against the Definition of Ready **before
any story is released** into the story pipeline.

This is a **shift-left / three-amigos** gate, not a test run. Bounce loops later in the story
pipeline (code review, QAS, design test) are mostly *symptoms* of tickets that were never fully
thought through; the rework counter (spec §3.2) only caps those loops, it does not prevent them.
`Ticket Review` moves the check to the front so the architect downstream reviews and releases only
complete tickets (reviews once, not twice).

**Why QAS, not a new role** — the reviewer must be **independent of the authors** (BSA drafted,
issue-enrichment formatted; same non-collapsible-gate logic as `Security Review`), and the decisive
lens is testability: "can I test against these ACs later?" is QAS's home turf. Cost: exactly **+1
spawn per epic**.

The QAS Ticket-Review seat charter (`harness/claude/agents/qas.md`) cross-links to this SOP; this
SOP links back to it and to the orchestrator runbook.

---

## The DoR Checklist (per child ticket)

Every child ticket must satisfy **every** item. A ticket that fails any item makes the epic a
`rework` verdict (see Verdicts).

- **Every AC is measurable / testable.** No "works correctly", "handles errors gracefully", "looks
  good" — each acceptance criterion names an observable condition a later gate can pass or fail
  against (a value, a status code, a concrete user step, an artifact).
- **Flags are consistent with content.** The `design` / `security` / `data` flags match what the
  ticket actually describes: a ticket touching auth/RLS/injection surface carries `security`; one
  needing fixtures or seeded data carries `data`; a UI ticket carries `design`. A missing or spurious
  flag is a defect (it changes which conditional seats the runner spawns or SKIP-FORWARDs).
- **The `role:` hint is plausible.** The implementer-role hint the orchestrator reads
  (`be-developer` / `fe-developer` / `data-engineer`) fits the ticket's work.
- **Scope is small enough for one single-ticket spawn.** The ticket is completable by a single
  fresh subagent in one pass (ADR-A-0002). A ticket that clearly needs to be several tickets is a
  defect naming the split.
- **Pattern / spec references are present.** The ticket points at the relevant
  `patterns_library/` pattern(s) and/or spec section(s) rather than leaving discovery to the
  implementer from scratch.
- **No unresolved `#PLAN_UNCERTAINTY` without a resolution path.** A metacognitive uncertainty tag
  is fine only when the ticket also states how it gets resolved (a spike, a named decision owner, a
  fallback). An open uncertainty with no path is an `open question` verdict, not a silent pass.

---

## Cross-Story Checks (the batch advantage)

Reviewing all children together — not one at a time — is the whole point of the batch gate. Beyond
the per-ticket checklist:

- **Overlap / duplication** — no two stories quietly implement the same work.
- **Dependencies explicit and acyclic** — cross-story dependencies are stated on the tickets and do
  not form a cycle.
- **Mandatory coverage mapping** (see below).

### The Mandatory Coverage-Mapping Rule

**Every goal in the epic text must map to at least one story AC.** The reviewer builds an explicit
mapping — epic goal → the story AC(s) that satisfy it — and checks that no goal is left unmapped.

> An **unmapped epic goal is a `rework` verdict that names the gap** (the missing story or the
> missing AC), not a pass.

This rule is mandatory because without an explicit mapping instruction *any* reviewer only checks
tickets **in isolation** and misses what is **absent** — the class of defect where the tickets are
each individually fine but, taken together, do not deliver the epic. Absence is invisible to a
per-ticket read; only the mapping surfaces it.

---

## The Blind-Spot Catalog

A **fixed question list** held against every story — the recurring categories of "forgotten points"
that ticket authors under-specify. QAS's what-if lens is the best fit here. For each story, ask
whether the ticket has addressed:

- **Error / edge cases** — empty input, failure of a downstream call, boundary values, concurrent
  access, partial completion.
- **Authz / RLS** — who is allowed to do this; row-level security context; tenant/user isolation.
- **Migrations for existing data** — a schema/behavior change that must handle rows that already
  exist, not just new writes (backfill, defaults, nullability).
- **Idempotency** — safe to retry; no duplicate side effects on a re-run (payments, webhooks, jobs).
- **Observability** — is the new behavior visible (logs, metrics, evidence) when it succeeds and
  when it fails.
- **Rollback** — how the change is undone or disabled if it misbehaves (forward-fix / flag / revert
  ownership — reverts of main are human-only, spec §3.5).

A story that silently ignores a category that clearly applies to it is a defect for the `rework`
list — or an `open question` if the reviewer cannot tell from the ticket text whether it applies.

---

## The Three Verdicts

The gate produces exactly one verdict for the epic, recorded on the epic ticket via the adapter. The
exit transitions are the runner's; the seat issues the transition it names.

### `ready` — all children pass → `Architecture Review`

Every child satisfies the checklist, the cross-story checks hold, coverage mapping is complete, and
no blind-spot category is silently ignored. Transition the epic to `Architecture Review`; the
system-architect then reviews and releases only complete tickets.

### `rework` — one or more defects → `Grooming`

Bounce the epic to `Grooming` with a **concrete defect list** — each entry names the ticket and the
exact failing item (untestable AC, inconsistent flag, unmapped epic goal, missing blind-spot
handling, oversized scope). BSA fixes the specs/ACs and issue-enrichment updates the tickets, then
the epic re-enters `Ticket Review`.

The `rework` bounce (`Ticket Review → Grooming`) is a **backward transition counted by the epic
ticket's rework counter** (spec §3.2, [`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "Rework counter").
**No new guard mechanics** — the same cross-stage counter that governs story bounces governs DoR
bounces: at 3 the runner escalates the epic to `Needs PO Decision`, and **no story is ever released**
before the gate passes.

### `open question` — cannot decide → `Needs PO Decision`

Anything the reviewer **cannot decide from the ticket text** — the class no gate can catch: unwritten
domain knowledge — is **never guessed**. Transition the epic to `Needs PO Decision`; the po-agent
that triaged the epic is the product authority and answers. This is the structural mitigation for
missing domain knowledge; guessing it is exactly the failure the gate exists to prevent.

---

## Path-B entry-gate reuse (v3.1 flexible intake — ABS-102 / ABS-107)

Under **v3.1 flexible intake**, this same Definition-of-Ready gate is **reused as the entry gate for a
pre-populated epic** — an epic authored with its child tickets already attached (Path-B). Instead of
`Grooming` decomposing an empty epic and then `Ticket Review` checking the generated children, the
runner routes a pre-populated epic **straight into this gate over its pre-existing children**, with no
Grooming decomposition step (ABS-107). The checklist, the mandatory coverage-mapping rule, the
blind-spot catalog, and the three verdicts are **unchanged and applied verbatim** — only the point at
which the gate runs moves earlier in the pipeline. A `ready` epic exits to `Architecture Review` with
no story generation; a `rework` epic drives the auto-fix loop (ABS-108) where substance-only gaps
escalate to `Needs PO Decision`, capped at 3 bounces by the same rework counter (spec §3.2). The
three-way route that selects this path is in [`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "Intake
classification".

### The epic-prerequisite check (Path-B only)

Because a pre-populated epic **skips `Grooming`**, the goal/scope framing that Grooming would otherwise
produce is **assumed already present on the epic ticket**. Before (and in addition to) the per-child DoR
checklist, the Path-B gate therefore verifies **four epic-level prerequisites on the epic ticket
itself**:

- **Goal present** — the epic states, in testable terms, what it delivers (not a title alone). Without a
  goal the coverage-mapping rule has nothing to map the children against.
- **Scope present** — an explicit in-scope / out-of-scope boundary. Without it, "overlap / duplication"
  and absent-work cannot be judged across the children.
- **Acceptance criteria / Definition of Done present** — epic-level ACs or a DoD the children must
  collectively satisfy; these are the mapping *targets* for the coverage rule.
- **ADR context present** — the applicable ADRs / guardrail annotation are named (or an explicit "none
  beyond defaults"), so the architect and the children inherit the right constraints.

**A missing prerequisite is not a silent pass.** Route it by the same three-verdict logic:

- A prerequisite that is **absent but reconstructable from the epic text** (e.g. the scope is implied by
  the children but never written down) is a **`rework`** finding — the auto-fix loop (ABS-108) adds the
  missing framing; the `gate-results` defect list names the exact missing prerequisite.
- A prerequisite whose absence is a **genuine product/domain gap** — no goal at all, or ACs that would
  require inventing unwritten requirements — is an **`open question`** → `Needs PO Decision`; the
  po-agent that triaged the epic decides. It is **never guessed** (same rule as the per-child checklist).

The epic-prerequisite check is recorded in the same `gate-results` comment as the per-child results, as
an explicit four-item pass/fail block, so the verdict is auditable.

### Path-B auto-fix rework loop (v3.1 flexible intake — ABS-108)

When the Path-B entry gate returns **`rework`**, the epic bounces `Ticket Review → Grooming` exactly
as it does under v3.0 — **the same transition, the same rework counter, no new status**. What differs
for Path-B is *what the Grooming bounce does*: because the children **already exist**, BSA/issue-enrichment
do **not** re-decompose from scratch — they **auto-normalize the existing children at child granularity**
against the `gate-results` defect list, then the epic **re-enters `Ticket Review`** for a fresh check.
This repeats until the gate returns `ready` (→ `Architecture Review`) or the counter caps out.

**The auto-fix set is enumerated and closed.** Auto-fix authority covers *formatting / normalization*
only — nothing that changes what a story delivers. Each item below names the **canonical tracker
operation** that applies it (ADR-A-0007 — the loop uses only the canonical operations, so the SOP
never prescribes a step the tooling cannot perform; ABS-66). The complete, closed set the loop may apply
to an existing child:

1. **Tighten a vague AC** — rewrite an untestable AC ("handles errors gracefully") into a measurable one
   over the **same** delivered behavior; never add or remove what the story does.
   *Mechanism:* `update <id> body-file <path>` — a true **in-place** body edit (ABS-252). It REPLACES the
   body and preserves the frontmatter and every comment, so the file must carry the ticket's full
   goal/scope/AC, not just the delta.
2. **Set / repair a `design` / `security` / `data` flag** to match the content the ticket already describes.
   *Mechanism:* `update <id> flags [...]` — a true **in-place** field edit.
3. **Repair the `role:` hint** (`be-developer` / `fe-developer` / `data-engineer` / …) to fit the work.
   *Mechanism:* **close-and-replace** — the hint is a `role:<name>` label set only at `create` time via
   `--role`; `update labels` cannot carry it (the `:` fails the label charset), so this item uses
   close-and-replace rather than the in-place body edit that items 1 and 4 use.
4. **Add a missing pattern / spec reference** that already applies to the ticket's stated work.
   *Mechanism:* `update <id> body-file <path>` — a reference lives in the ticket body (same in-place
   mechanism as item 1).
5. **Create a coverage-gap story** for an epic goal the existing children leave unmapped — a *missing*
   story that the epic text already calls for, not a new requirement.
   *Mechanism:* `create --body-file` (+ `update <id> depends_on` to wire it into the tree) — a purely
   **additive** create, no replacement.
6. **Split an oversized story** into single-spawn units that, together, deliver exactly the original scope.
   *Mechanism:* `create` the split units + re-link, then **close-and-replace** retires the original.

**Body rewrites are in-place (ABS-252); close-and-replace is the narrow fallback.** The canonical adapter
DOES have an in-place description edit: `update <id> body-file <path>` (and the inline `update <id> body
<text>`) rewrites a child's body — its ACs and References — preserving the frontmatter and every comment,
in both the mock and the Jira binding. Body normalizations (items 1 and 4) are therefore applied **in
place, on the same issue key**; the body no longer goes stale against the agreed ACs.

**Close-and-replace** survives only where the adapter still cannot edit in place: the **`role:` hint**
(item 3 — a `role:<name>` label set only at `create` time via `--role`; `update labels` cannot carry it,
the `:` fails the label charset) and the **retire step of item 6**. There, `create` a corrected successor
child (body via `--body-file`, role via `--role`, flags via `--flag`), carry over its `parent` and
`depends_on`, then close the superseded original. **"In place / do not re-decompose" means at child
granularity**: the loop corrects the epic's children **one ticket at a time** and never regenerates the
whole child set from the epic text.

**The authority boundary (ADR-A-0004).** Anything beyond normalization is a **product decision reserved
to the PO-Agent** (human-delegated authority, ABS-9 amendment) and is **never auto-applied**. A genuine
scope/domain gap in a child — **rewriting what a story delivers**, or **adding an unwritten requirement**
the epic text does not already call for — is not on the auto-fix list. When the gate finds such a gap, it
issues the **`open question`** verdict → `Needs PO Decision` (not `rework`), so it is escalated, never
silently resolved by the loop. If BSA/issue-enrichment discover *during* an auto-fix pass that a listed
`rework` defect actually requires a scope change, they **stop and raise it as an open question** to
`Needs PO Decision` rather than auto-applying it. This boundary — normalization is delegated, substance is
the PO-Agent's — is the central design constraint of the loop.

**The 3-bounce cap (spec §3.2 — reused verbatim).** Each `Ticket Review → Grooming` rework bounce
increments the **epic ticket's** existing per-ticket rework counter (spec §3.2,
[`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "Rework counter"). At `ORCH_REWORK_LIMIT` (default 3) the
runner transitions the epic to `Needs PO Decision` instead of re-spawning. **No new counter or threshold
mechanics are introduced** — the same cross-stage counter that caps story bounces caps the auto-fix loop,
which is itself the escalation-to-human safety valve against an unbounded auto-fix loop (ADR-A-0004). The
auto-fix set above stays enumerated and closed (ADR-A-0010 minimal-change): the loop is a bounded
normalizer, not a general-purpose ticket-rewriter.

## Related Documents

- [`docs/sop/ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) — the `Ticket Review` seat in the epic
  lifecycle; the rework counter that counts DoR bounces; the empty-epic / quiescence guards
- [`specs/ABS-69-workflow-v3-full-agent-team-spec.md`](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md) §3.10 — the design decision this SOP implements
- `harness/claude/agents/qas.md` — the QAS Ticket-Review seat charter (references this SOP)
- [`docs/sop/PO_AGENT_SOP.md`](PO_AGENT_SOP.md) — where `open question` → `Needs PO Decision` lands
- [`docs/sop/FOLLOW_UP_TICKET_SOP.md`](FOLLOW_UP_TICKET_SOP.md) — the watcher-driven follow-up chain a DoR finding can spawn
- `tests/e2e-workflow-v3.sh` — S16 exercises the DoR gate end-to-end (un-ready tickets bounce to
  `Grooming`, no story released before the gate passes, third bounce → `Needs PO Decision`)
