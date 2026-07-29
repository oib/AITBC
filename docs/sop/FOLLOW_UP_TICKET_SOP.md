# Follow-Up Ticket Standard Operating Procedure (SOP)

**Purpose**: Define how review feedback becomes a follow-up ticket — the **watcher-driven** chain
that turns a `kind: follow-up` comment into a BSA decision, the outside-epic default, the AC-blocking
attachment rule, and the per-epic budget

**Version**: 2.0 (v3 watcher chain — ABS-69 / ABS-75, spec §3.4)
**Last Updated**: 2026-07-06

---

## Overview

During review, agents frequently surface findings that are out of scope for the current ticket.
In **v1/v2 this was a paper chain** — a reviewing agent was supposed to "hand off to the BSA", but
no automation could execute that hand-off, so recommendations sat in comments and starved.

**v3 replaces the paper chain with a sweep-driven watcher (spec §3.4, ABS-75).** A reviewing agent
does not "invoke" anyone — it simply posts a `kind: follow-up` comment on the ticket. The
orchestrator's reconciliation sweep does the routing:

1. **Reviewing agent** posts a **Follow-Up Recommendation** as a `kind: follow-up` comment (any
   reviewing seat — QAS, System Architect code review, SecEng audit, DoR gate, etc.).
2. **The sweep watcher** scans for `kind: follow-up` comments that have **no `kind: bsa-decision`
   reply** and spawns the **BSA** on that ticket (one spawn per unanswered follow-up; the answered
   ones are skipped by the same comment-keyed re-raise guard the JOIN/stall rules use).
3. **BSA** decides `create` / `in-scope` / `discard` and records a `kind: bsa-decision` comment
   (which disarms the watcher for that follow-up).
4. **On `create`**: the created follow-up story defaults to **Backlog *outside* the current epic**;
   the BSA attaches it to the current epic only by marking it **AC-blocking** (then it becomes a
   child counted by the JOIN rule). Creation itself follows the enrichment protocol.

**Key principles**:

- There is NO dedicated "Review Agent" and NO agent-to-agent spawn — the watcher is a **mechanical,
  bash-only sweep scan** (ADR-A-0009), and BSA arrives as a fresh single-ticket spawn (ADR-A-0002).
- **Outside-epic default**: a follow-up does **not** silently expand the current epic's scope. It
  lands in the Backlog for independent prioritization.
- **AC-blocking is the only way in**: the BSA may attach a follow-up to the *current* epic only by
  marking it AC-blocking; the JOIN rule then blocks epic completion until that child is `Done`.
- **Per-epic budget: 5.** The 6th follow-up on one epic raises **`Needs PO Decision`** instead of
  creating — this prevents quality gates from starving epic completion (spec S7). Budgets are
  **isolated per epic** (S9): one epic's overflow never affects another's.
- The `bsa-decision` reply is what closes the loop — the watcher keys off its **absence**, so an
  unanswered follow-up re-spawns the BSA and an answered one never does.

> **Runner enforcement (ABS-297)**: A bsa handoff that claims the follow-up pile is empty
> ("all follow-ups answered", "pile is empty", etc.) while a `kind: follow-up` without a
> `kind: bsa-decision` reply still exists on the ticket is **refused** — no transition is
> applied, a `MARKER-MISSING` gate-results comment is posted, and the seat is re-spawned.
> Post the `kind: bsa-decision` reply *before* handing off. See
> `ORCHESTRATOR_SOP.md §Handoff Marker Duty Verification` (ABS-297).

The follow-up marker is also what the JOIN **quiescence guard** watches: an epic with an unprocessed
follow-up (a `kind: follow-up` without a `bsa-decision` reply, anywhere in its tree) does **not**
JOIN, so an AC-blocking follow-up filed in the same cycle the last story finishes cannot lose the
race (sweep order: watcher → JOIN; see [`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "JOIN rule +
guards").

---

## Follow-Up Recommendation Format (posted as `kind: follow-up`)

Reviewing agents record findings as a `kind: follow-up` comment via the adapter — **no hand-off to
a named agent**; the sweep watcher picks it up. The compact structured block:

```markdown
## Follow-Up Recommendation

- **Source Agent**: [QAS | System Architect | SecEng | other]
- **Context Ticket**: AITBC-XXX
- **Finding**: [What was observed, with file/evidence references]
- **Why Out of Scope**: [Why the current ticket cannot absorb this]
- **Suggested Action**: [What the reviewing agent recommends]
```

```bash
scripts/mock-tracker.sh comment AITBC-XXX --kind follow-up --actor <source-agent> \
  --body "$(cat follow-up-recommendation.md)"
```

The watcher spawns the BSA on the **next sweep** because this comment has no `kind: bsa-decision`
reply yet. The reviewing agent does nothing further.

---

## Decision Outcomes

When the watcher spawns the BSA, it answers every recommendation with one of three explicit
decisions, recorded as a **`kind: bsa-decision`** comment (this is the reply the watcher keys off —
its presence disarms the re-raise for that follow-up):

```markdown
## Follow-Up Decision

- **Recommendation**: [Reference to the Follow-Up Recommendation]
- **Decision**: create | in-scope | discard
- **Reasoning**: [Why this decision was made]
- **Epic attachment** (create only): outside-epic (default) | AC-blocking child of AITBC-<epic>
```

```bash
scripts/mock-tracker.sh comment AITBC-XXX --kind bsa-decision --actor bsa \
  --body "$(cat follow-up-decision.md)"
```

### Outcome 1: `create`

The finding is valid, actionable, and does not belong in the current ticket → new ticket warranted.

**Example**:

```markdown
## Follow-Up Recommendation

- **Source Agent**: SecEng
- **Context Ticket**: AITBC-142
- **Finding**: Webhook endpoint `/api/webhooks/payments` lacks rate limiting; audit evidence in AITBC-142 comments
- **Why Out of Scope**: AITBC-142 covers webhook signature verification only; rate limiting is separate infrastructure work
- **Suggested Action**: Add rate limiting middleware to all webhook endpoints

## Follow-Up Decision

- **Recommendation**: SecEng rate-limiting finding on AITBC-142
- **Decision**: create
- **Reasoning**: Valid security gap affecting multiple endpoints; expanding AITBC-142 would break its testable scope. Warrants its own ticket with dedicated ACs.
```

BSA then drafts the requirement and creates the ticket via the enrichment protocol (see below). By
**default the created story lands in Backlog outside the current epic** — a security or quality gap
is real work, but it does not silently expand the epic that surfaced it. The BSA attaches it to the
current epic **only** by marking it **AC-blocking** (see "Outside-Epic Default and AC-Blocking
Attachment"), which is the deliberate, budgeted exception.

### Outcome 2: `in-scope`

The finding belongs in the current ticket → fold it into the current spec/acceptance criteria.

**Example**:

```markdown
## Follow-Up Recommendation

- **Source Agent**: QAS
- **Context Ticket**: AITBC-156
- **Finding**: Form submits successfully but shows no success feedback to the user
- **Why Out of Scope**: Not listed in the acceptance criteria for AITBC-156
- **Suggested Action**: Create a follow-up ticket for success feedback UX

## Follow-Up Decision

- **Recommendation**: QAS success-feedback finding on AITBC-156
- **Decision**: in-scope
- **Reasoning**: The user story promises "confirmation of submission" — the AC was incomplete, not the scope. Adding AC to AITBC-156; FE Developer addresses in the current iteration.
```

BSA updates the current spec/ACs and notifies the source agent and TDM.

### Outcome 3: `discard`

The finding does not warrant action → document the reasoning and close the loop.

**Example**:

```markdown
## Follow-Up Recommendation

- **Source Agent**: System Architect
- **Context Ticket**: AITBC-163
- **Finding**: Utility function duplicates logic that a planned shared library could provide
- **Why Out of Scope**: Refactoring to a shared library is beyond this PR
- **Suggested Action**: Consider a refactoring enabler ticket

## Follow-Up Decision

- **Recommendation**: System Architect shared-library suggestion on AITBC-163
- **Decision**: discard
- **Reasoning**: The shared library is already covered by existing enabler AITBC-98 (verified via Linear search). Creating a new ticket would duplicate tracked work.
```

BSA documents the reasoning on the current ticket and notifies the source agent.

---

## Outside-Epic Default and AC-Blocking Attachment (spec §3.4, S11)

Every `create` follow-up defaults to **Backlog, parented to nothing / outside the epic** — it is
prioritized independently like any other backlog item.

The BSA attaches a follow-up to the **current epic** only by marking it **AC-blocking**:

- An AC-blocking follow-up is created as a **child of the epic**, and the JOIN rule counts it — the
  epic **cannot** reach `Epic Integration` (and therefore cannot fire the ready-to-test NOTIFY)
  until that child is `Done` (spec §3.1, S11).
- Reserve AC-blocking for findings that genuinely make the epic's stated outcome incomplete or
  unsafe to ship (e.g. a missing authz check on a story the epic delivers). Everything else stays
  outside the epic.
- Because an unprocessed follow-up also holds the JOIN quiescence guard, an AC-blocking follow-up
  filed in the same cycle the last story completes wins the race — JOIN waits for the watcher, the
  BSA attaches the child, and the epic integrates only after it is `Done`.

## Per-Epic Follow-Up Budget (spec §3.4, S7 / S9)

Each epic carries a follow-up budget of **5**. When the 6th follow-up on one epic would be created,
the chain instead raises **`Needs PO Decision`** on the epic — a signal that the quality gates are
outrunning the epic's scope and the product owner should decide (rescope, split, or accept the
backlog of follow-ups). Budgets are **isolated per epic**: a second epic in flight has its own
independent count of 5 and is unaffected by the first epic's overflow.

### Recovery after exhaustion (ABS-293)

Exhaustion is **not** a one-way door. Two sanctioned recovery paths, both declarable at the
tracker without touching the runner's environment mid-run:

1. **PO disposition per follow-up.** A `kind: bsa-decision` comment on the ticket carrying the
   follow-up lowers its pending count (net `follow-up` minus `bsa-decision`). This is how the JOIN
   quiescence gate clears when the watcher can no longer spawn a bsa — the PO answers the
   follow-ups directly. Pinned by `tests/orchestrator.d/ABS-293-budget-recovery.sh`.
2. **Budget re-arm.** A `kind: decision` comment **on the epic** whose body contains
   `FOLLOWUP-BUDGET-RESET (triage)` grants one further full `ORCH_FOLLOWUP_BUDGET`. Anchoring is
   quote-proof (the token only counts in the body of a `kind: decision` comment), and the
   escalation guard is generation-aware: each re-armed budget that exhausts again escalates the
   epic **once more** — never an escalation storm, never a permanent latch.

Follow-ups that arrive while the budget is exhausted no longer strand silently: the watcher marks
each one on its ticket with a `FOLLOWUP-STRANDED n=<ordinal>` comment naming both recovery paths.

## Ticket Creation (`create` only) — enrichment protocol

When the decision is `create`, the BSA drafts the requirement following the `spec-creation` skill
drafting conventions:

```markdown
## Follow-Up Ticket Draft

- **Title**: Add rate limiting to webhook endpoints
- **Problem**: Webhook endpoints accept unlimited requests; SecEng audit on AITBC-142 flagged abuse potential
- **Desired Outcome**: All webhook endpoints reject requests exceeding a configurable rate threshold
- **Scope**: In: webhook routes, middleware, configuration. Out: non-webhook API routes, WAF-level controls
- **Acceptance Hints**: Requests over threshold return 429; limits configurable per endpoint; existing webhook tests still pass
- **Origin**: SecEng audit, AITBC-142
```

Creation runs the enrichment protocol — the same three steps the Issue Enrichment Agent
(`.claude/agents/issue-enrichment.md`) owns:

1. **Deduplication** — mandatory `duplicate-detection` gate (reject/append/create verdict)
2. **Enrichment** — agent-ready formatting, guardrail-feasibility check, guardrail annotation
3. **Creation** — create/append via the task-tracking adapter and link to the context ticket

> **v3 note (no nesting).** Because a spawned BSA **cannot nest-spawn** the Issue Enrichment Agent
> as a subagent (ADR-A-0002; see AGENT_WORKFLOW_SOP "Method 2 retired"), the BSA follow-up seat runs
> the dedup + enrichment gates **inline via the skills** and creates the ticket itself through the
> adapter — the same scoped inline-enrichment exception the PO-Agent uses for epic decomposition
> ([`PO_AGENT_SOP.md`](PO_AGENT_SOP.md) §6.2). The epic-pipeline **`Enrichment`** status (a separate
> issue-enrichment spawn for batch child creation from grooming) is the non-inline path; the two do
> not conflict. Either way the created ticket is deduped, enriched, and linked to the context ticket.

---

## Issue Enrichment Stage

Once the Issue Enrichment Agent receives the draft, it runs its enforced three-step workflow. Continuing the rate-limiting example above, the full chain (local/dev with the mock adapter):

**1. Dedup gate** (`duplicate-detection` skill — mandatory, never skipped):

```bash
scripts/mock-tracker.sh search --text "rate limiting"
scripts/mock-tracker.sh search --text "webhook"
# (no matching ticket found)
```

```markdown
**Verdict**: create
**Matched**: none
**Reasoning**: Rule 5 — no identical or similar ticket found for "rate limiting" / "webhook".
```

(A `reject` verdict stops here — the matched reference goes back to the BSA. An `append` verdict extends the matched ticket instead of creating.)

**2. Enrichment** (`issue-enrichment` skill): the draft is formatted into the agent-ready structure (goal / scope / acceptance criteria / references), checked for guardrail feasibility (ADR-A-0001 hierarchy, ADR-A-0004 approval boundaries, ADR-A-0010 minimal-change), and annotated with the resulting guardrail notes. A `block` outcome returns the draft to the BSA instead of creating.

**3. Adapter create** (system-agnostic per ADR-A-0006/0007 — mock tracker locally, configured tracker MCP in production):

```bash
NEW=$(scripts/mock-tracker.sh create --type ticket --title "Add rate limiting to webhook endpoints")
scripts/mock-tracker.sh comment "$NEW" --kind handoff --actor issue-enrichment \
  --body "Enriched body: goal/scope/AC/references + guardrail annotation. Origin: SecEng audit, AITBC-142."
scripts/mock-tracker.sh link "$NEW" AITBC-142 origin-review
```

See `.claude/agents/issue-enrichment.md` and `.claude/skills/issue-enrichment/SKILL.md` for the full workflow, ticket template, and guardrail checklist.

---

## Related Documentation

- `.claude/agents/bsa.md` - BSA role definition (Follow-Up Ticket Decision section)
- `.claude/agents/issue-enrichment.md` - Issue Enrichment Agent (dedup, enrichment, creation)
- `.claude/skills/duplicate-detection/SKILL.md` - Mandatory dedup gate (reject/append/create)
- `.claude/skills/issue-enrichment/SKILL.md` - Agent-ready template + guardrail checklist
- `.claude/skills/spec-creation/SKILL.md` - Drafting conventions
- [AGENT_WORKFLOW_SOP.md](AGENT_WORKFLOW_SOP.md) - Agent coordination methods (Method 2 retired: no agent-to-agent spawn)
- [ORCHESTRATOR_SOP.md](ORCHESTRATOR_SOP.md) - The sweep watcher, JOIN quiescence guard, per-day budget
- [specs/ABS-69-workflow-v3-full-agent-team-spec.md](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md) §3.4 - the follow-up watcher + containment design
- `tests/e2e-workflow-v3.sh` - S7 (budget overflow → Needs PO Decision), S9 (per-epic isolation), S11 (AC-blocking wins the JOIN race)
