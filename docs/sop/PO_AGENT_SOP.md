# PO-Agent Standard Operating Procedure (SOP)

**Purpose**: Define how the PO-Agent exercises product ownership — story acceptance after the QAS gate, epic-completion determination, WSJF backlog prioritization, the three human-only escalation paths, and the Self-Improvement Agent trigger

**Version**: 1.1 (ABS-173)
**Last Updated**: 2026-07-09

---

## Overview

The PO-Agent ([`.claude/agents/po-agent.md`](../../.claude/agents/po-agent.md)) holds delegated product ownership: full story-acceptance authority, epic-completion determination, and autonomous backlog prioritization — codified in the Amendment 2026-07-02 (ABS-9) of [`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md).

Three decisions are **human-only** and are never made by the PO-Agent: creating new features, merging to main ([ADR-A-0005](../../adrs/agentic/ADR-A-0005-mandatory-prs.md)), and approving additional costs ([ADR-A-0009](../../adrs/agentic/ADR-A-0009-cost-approval-gate.md)).

All decisions are recorded on tickets via the task-tracking adapter — mock adapter `scripts/mock-tracker.sh` locally, the configured tracker MCP in production.

---

## 1. Story Acceptance Flow (Post-QAS)

Acceptance runs ONLY after the QAS gate. QAS independence is untouched — the PO-Agent consumes the QAS verdict, never produces or overrides it.

```text
Implementation → QAS gate ("Approved for RTE") → PO-Agent acceptance → RTE PR → HITL merge
```

### Procedure

1. **Verify the QAS gate**: the ticket carries QAS evidence and the QAS exit state. Missing → return the ticket, do not accept.
2. **Evidence check**: read the acceptance criteria and the attached evidence (test output, session IDs, validation results). Every AC must be demonstrably met by evidence, not asserted.
3. **Issue the decision** and record it on the ticket via the adapter.

### Example: Accept

```markdown
## PO-Agent Acceptance Decision

- **Ticket**: AITBC-231
- **Decision**: accept
- **QAS Gate**: QAS evidence comment 2026-07-01, exit state "Approved for RTE"
- **AC Verification**:
  - AC1 (retry on failure): met — integration test output attached, 3/3 retries observed
  - AC2 (idempotent side effects): met — duplicate-run test shows single write
  - AC3 (docs updated): met — docs/guides/jobs.md diff in PR
- **Reasoning**: All acceptance criteria demonstrably met by attached evidence. Hand to RTE for PR.
```

```bash
# Record locally via the mock adapter
scripts/mock-tracker.sh comment AITBC-231 --kind acceptance --actor po-agent \
  --body "Decision: accept — all ACs met by evidence (see acceptance decision block)"
```

### Example: Reject

```markdown
## PO-Agent Acceptance Decision

- **Ticket**: AITBC-232
- **Decision**: reject
- **QAS Gate**: QAS evidence comment 2026-07-01, exit state "Approved for RTE"
- **AC Verification**:
  - AC1 (export includes archived rows): NOT met — evidence covers active rows only
  - AC2 (CSV encoding): met
- **Reasoning**: AC1 has no supporting evidence for archived rows. Returned to implementing
  agent via TDM with the specific gap. Re-acceptance after new QAS evidence.
```

Out-of-scope findings surfaced during acceptance go to the BSA as a Follow-Up Recommendation ([`docs/sop/FOLLOW_UP_TICKET_SOP.md`](FOLLOW_UP_TICKET_SOP.md)) — never absorbed silently, never filed directly.

---

## 2. Epic-Completion Check Procedure

An epic is complete when **all child stories are accepted AND the epic Definition of Done is met**. The PO-Agent determines and records this.

1. **Query the epic's children via the adapter**:

   ```bash
   scripts/mock-tracker.sh search --parent AITBC-200
   # Production: tracker MCP equivalent (list issues by parent/epic)
   ```

2. **Verify each child is accepted**: every child carries a recorded PO-Agent `accept` decision. Any child missing one → epic NOT complete; list the gaps on the epic ticket.
3. **Verify the epic Definition of Done**: check each DoD item on the epic ticket/spec against evidence (docs updated, migrations deployed, all PRs human-merged, etc.).
4. **Record the determination** on the epic ticket via the adapter — children verified, DoD items checked, verdict.
5. **Trigger the Self-Improvement Agent** (mandatory on completion — see section 5).

---

## 3. WSJF Prioritization Example

```text
WSJF = Cost of Delay / Job Size
Cost of Delay = Business Value + Time Criticality + Risk Reduction / Opportunity Enablement
```

Each component scored on the relative scale 1, 2, 3, 5, 8, 13, 20. Three sample backlog tickets:

| Ticket                                          | Business Value | Time Criticality | Risk Reduction | Job Size | WSJF (CoD / Size)    |
| ----------------------------------------------- | -------------- | ---------------- | -------------- | -------- | -------------------- |
| AITBC-310 Fix checkout tax rounding | 13             | 20               | 8              | 3        | 41 / 3 = **13.7**    |
| AITBC-311 Add invoice PDF export    | 8              | 3                | 2              | 5        | 13 / 5 = **2.6**     |
| AITBC-312 Migrate session store     | 3              | 5                | 13             | 8        | 21 / 8 = **2.6**     |

**Resulting order**: AITBC-310 → AITBC-311 → AITBC-312. The 311/312 tie breaks toward the smaller job (311, size 5).

**Record the decision** on each affected ticket via the adapter (scores, rank, reasoning), e.g.:

```bash
scripts/mock-tracker.sh comment AITBC-310 --kind prioritization --actor po-agent \
  --body "WSJF 13.7 (BV 13 + TC 20 + RR 8 / size 3) — ranked #1: revenue-impacting defect with deadline decay"
```

Re-score when new tickets arrive, an epic completes, or facts change. Prioritization covers existing scope only — new-feature gaps escalate (section 4.1).

---

## 4. The Three Human-Only Escalation Paths

The PO-Agent prepares; the human decides. No exceptions.

### 4.1 Creating New Features → Feature Proposal to Human POPM

Feature initiation is human. When acceptance or backlog work reveals a genuine new-feature need, the PO-Agent prepares a **feature proposal document** — problem, evidence, expected value, rough WSJF estimate, no implementation detail — and hands it to the human POPM (oib). The feature exists only if the human says so.

### 4.2 Merging to Main → RTE → HITL

Per ADR-A-0005, the merge button is the human gate. After acceptance, the PO-Agent hands the ticket to the **RTE**, which shepherds the PR to **HITL** for the human merge decision. The PO-Agent never merges and never treats its acceptance as merge authority.

### 4.3 Approving Additional Costs → Cost Summary to Human

Per ADR-A-0009, license and LLM API costs pause at the `additional-costs` human gate. The PO-Agent prepares a **cost summary** (option, cost source, no-cost alternative, trade-off) and escalates; the human approves or rejects each cost flag in the tracker.

---

## 5. Self-Improvement Trigger Handoff

The PO-Agent starts the Self-Improvement Agent ([`.claude/agents/self-improvement.md`](../../.claude/agents/self-improvement.md), arrives with ABS-4) whenever it deems the time right:

- **Mandatory**: on every determined epic completion (step 5 of the epic-completion check)
- **Optional (mid-epic)**: after repeated story rejections, recurring blocker patterns, or a cluster of follow-up tickets pointing at the same process gap

**Handoff format**:

```markdown
## Self-Improvement Trigger

- **From**: PO-Agent
- **Trigger**: epic-completion | mid-epic
- **Context**: [epic/ticket references]
- **Observations**: [what motivated the trigger — rejection patterns, gate friction, recurring findings]
```

---

## 6. `Needs PO Decision` Spawn

`Needs PO Decision` is the tenth canonical lifecycle status ([`profiles/neutral/adapters/statuses.yaml`](../../profiles/neutral/adapters/statuses.yaml), ABS-61). It exists so an agent, a human, or a sweep can request a **product decision on demand** — a scope, priority, or direction call that is not a blocker — **or submit a bare epic for decomposition**, without overloading `Blocked`. Any active (non-`Done`) status may transition into it; the Coordinator maps entry to a plain **SPAWN po-agent** (no human NOTIFY — the PO-Agent decides autonomously within its delegated authority, [ADR-A-0004](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md) ABS-9 amendment).

When spawned on this status, first **read the packet ticket via the adapter** (`scripts/mock-tracker.sh get <id>`) and branch on its `type`: a non-epic ticket is an on-demand **product decision** (section 6.1); a `type: epic` with no children is a bare epic submitted for **decomposition** (section 6.2). This mirrors the branch in [`.claude/agents/po-agent.md`](../../.claude/agents/po-agent.md) ("`Needs PO Decision` Spawn").

### 6.1 On-demand product decision (non-epic ticket)

1. **Read the request.** The trigger is the latest request on the ticket — the most recent `kind: handoff` comment (the runner's packet resume signal) or the latest human/agent comment. Identify precisely what decision is being asked for and the options on the table.
2. **Decide within delegated authority.** Prioritization, scope clarification, and accept/defer-existing-scope calls are yours to make (sections 1–3). If the request actually needs a **human-only** call — a new feature, a merge, or additional cost (section 4) — do NOT invent it: prepare the appropriate proposal/summary and record that the decision is escalated.
3. **Record a `decision` comment** on the ticket via the adapter, naming the request, the decision, and the reasoning (evidence over assertion).
4. **Transition the ticket onward.** For an on-demand product decision the exits are `Backlog` (deprioritized / needs regrooming), `Ready for Development` (decided, proceed), or `Blocked` (needs a human-only call or is genuinely obstructed). The status has other outgoing transitions too: when the orchestrator raised the ticket here as a **v3 escalation** (rework / crash-limit, follow-up budget, empty-epic, or ambiguous-bisect), resume it onto the pipeline instead — **epics** to `PO Triage`, `Grooming`, or `Stories In Flight`; **stories** to `Design`. Those seven targets are the status's full outgoing set (`profiles/neutral/adapters/statuses.yaml`, `Needs PO Decision` → `next`); unlike `Blocked` this status does **not** resume to the exact stage the ticket left — an escalation is a fresh product call, not a resume-to-origin.

```bash
# Record the decision, then route the ticket onward (mock adapter locally).
scripts/mock-tracker.sh comment AITBC-231 --kind decision --actor po-agent \
  --body "Needs PO Decision request: ship v1 without archived-row export? Decision: proceed with active rows only for v1; archived export is a new-feature follow-up. Reasoning: unblocks the release; no accepted AC covers archived rows."
scripts/mock-tracker.sh transition AITBC-231 "Ready for Development" --actor po-agent \
  --reason "Needs PO Decision resolved: proceed with v1 scope"
```

### 6.2 Epic decomposition (bare `type: epic` with no children)

A bare epic reaches this status when a human or agent **submits it for decomposition** (the epic-submission step in "Submitting a bare epic" below). If the packet ticket is `type: epic` and `children <epic-id>` returns empty, decompose it into implementable child tickets.

1. **Confirm the epic is bare** — query its children; empty output means decompose (non-empty → treat as a section 6.1 decision):

   ```bash
   scripts/mock-tracker.sh children <epic-id>   # empty → decompose
   ```

2. **Decompose the epic body** into child tickets — one child per coherent, independently implementable unit of scope, each with its own **goal**, **scope**, and **acceptance criteria** derived from the epic.
3. **For EACH child, before creating it, run the two inline gates.** Because the orchestration loop cannot spawn the Issue Enrichment Agent as a nested subagent, the PO-Agent runs the enrichment protocol **inline via the skills** (scoped exception to the creation-routing rule — see [`.claude/agents/po-agent.md`](../../.claude/agents/po-agent.md)):
   - **Dedup gate** (`duplicate-detection` skill): `scripts/mock-tracker.sh search --text "<child title / keywords>"` — if a real match exists, link/annotate rather than create a duplicate.
   - **Enrichment protocol** (`issue-enrichment` skill): structure the child as goal / scope / acceptance criteria / references and add the guardrail annotation. Write this enriched body to a scratch file so it can be passed to `create --body-file`.
4. **Create each child via the adapter**, parented to the epic, with the implementer-role hint the orchestrator reads (ABS-36 §2.2) and the enriched body via `--body-file` — the goal/scope/AC must persist onto the child (not the `_TBD_` template) because the implementer reads the child body downstream, and the adapter is the only sanctioned writer (agents never touch `work/tickets/*.md` directly — ORCHESTRATOR_SOP Overview):

   ```bash
   scripts/mock-tracker.sh create --type ticket --parent <epic-id> \
     --role <be-developer|fe-developer|data-engineer> --title "<enriched child title>" \
     --body-file <path-to-enriched-body>
   ```

5. **Transition each created child to `Ready for Development`** so the Coordinator can dispatch it:

   ```bash
   scripts/mock-tracker.sh transition <child-id> "Ready for Development" --actor po-agent \
     --reason "Decomposed from epic <epic-id>; enriched + dedup-checked"
   ```

6. **Post a `decision` comment on the epic** listing every child id + title and the **total child count** — so a human can size `ORCH_MAX_SPAWNS_PER_RUN` before the fan-out runs ([ADR-A-0009](../../adrs/agentic/ADR-A-0009-cost-approval-gate.md): decomposition fan-out must be budget-visible):

   ```bash
   scripts/mock-tracker.sh comment <epic-id> --kind decision --actor po-agent \
     --body "Epic decomposition: created N children — <child-1-id> <title>; …; Total: N. Human: size ORCH_MAX_SPAWNS_PER_RUN accordingly before the run."
   ```

7. **Transition the epic back to `Backlog`** — the epic itself is not implementable; it rests in `Backlog` until the epic-completion check (section 2) fires when its children are done:

   ```bash
   scripts/mock-tracker.sh transition <epic-id> "Backlog" --actor po-agent \
     --reason "Decomposition complete: N children created and set Ready for Development; epic rests until the completion check"
   ```

**Submitting a bare epic for decomposition.** To hand an epic to the PO-Agent for decomposition, **submit it by transitioning the bare epic to `Needs PO Decision`** — the epic needs a goal/scope body but no children yet:

```bash
scripts/mock-tracker.sh transition <epic-id> "Needs PO Decision" --actor <human|agent> \
  --reason "Bare epic submitted for PO-Agent decomposition"
```

The Coordinator spawns the PO-Agent, which decomposes it per section 6.2 and returns the epic to `Backlog`.

Out-of-scope needs surfaced while deciding or decomposing follow the usual routes — new features to the human POPM (section 4.1), follow-up recommendations to the BSA.

---

## Related Documents

- [`harness/.claude/agents/po-agent.md`](../../harness/.claude/agents/po-agent.md) - PO-Agent role definition (source of truth; slimmed to 13.4 KB in ABS-173)
- [`docs/sop/po-agent-reference.md`](po-agent-reference.md) - Machine-oriented companion: worked examples, templates, and long bash sequences the agent pulls in on each named Trigger (extracted in ABS-173)
- [`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md) - Approval boundaries + ABS-9 amendment
- [`docs/sop/ADR_AUTHORING_GUIDE.md`](ADR_AUTHORING_GUIDE.md) - ADR Authoring Request handoff (PO-Agent → System Architect)
- [`docs/sop/FOLLOW_UP_TICKET_SOP.md`](FOLLOW_UP_TICKET_SOP.md) - Follow-up routing (PO-Agent → BSA)
- [`.claude/agents/issue-enrichment.md`](../../.claude/agents/issue-enrichment.md) - Ticket creation (PO-Agent → Issue Enrichment Agent)
