# Self-Improvement Agent Standard Operating Procedure (SOP)

**Purpose**: Define how the Self-Improvement Agent is triggered, how it analyzes completed work (retro skill → skill mining → improvement proposals), and how its outputs reach humans and the upstream boilerplate

**Version**: 1.1 (ABS-260)
**Last Updated**: 2026-07-13

---

## Overview

The Self-Improvement Agent ([`.claude/agents/self-improvement.md`](../../.claude/agents/self-improvement.md)) mines recurring agent tasks into concrete skill proposals and files boilerplate improvement proposals into [`work/improvement-proposals/`](../../work/improvement-proposals/README.md) for human review and upstream forwarding.

It has **no self-scheduling and no epic-close detection of its own** — epic-completion detection belongs to the PO-Agent
([`docs/sop/PO_AGENT_SOP.md`](PO_AGENT_SOP.md) section 2). The feedback loop stays inside the guardrails of
[`ADR-A-0004`](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md) and
[`ADR-A-0008`](../../adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md): agents propose, humans forward.

---

## 1. Trigger Paths

### 1.1 PO-Agent Handoff

The PO-Agent triggers the agent **mandatorily on every determined epic completion** and **optionally mid-epic** (repeated story rejections, recurring blocker patterns, clustered follow-up tickets). Handoff format (from [`PO_AGENT_SOP.md`](PO_AGENT_SOP.md) section 5):

```markdown
## Self-Improvement Trigger

- **From**: PO-Agent
- **Trigger**: epic-completion | mid-epic
- **Context**: [epic/ticket references]
- **Observations**: [what motivated the trigger — rejection patterns, gate friction, recurring findings]
```

### 1.2 Human Invocation

Any team member may start the agent directly. Minimum input: a context reference (epic/ticket IDs or a session scope). Without one, the agent asks — it never guesses a scope.

---

## 2. Analysis Flow

```text
Trigger (PO-Agent | human)
  → Step 1: retro skill (.claude/commands/retro.md) — retrospective analysis, REUSED not duplicated
  → Step 2: skill mining — retro output + epic git history + ticket comments (adapter)
  → Step 3: boilerplate improvement proposals → work/improvement-proposals/YYYY-MM-DD-<slug>.md
  → Step 4: self-improvement report → back to the invoker
  → Human: reviews proposals, forwards upstream (gh issue create)
```

**Recurrence heuristic** for skill mining: the same task performed on 3+ tickets or by 2+ agents. Below that, the pattern is noted in the report only.

---

## 3. Worked Example: Mined Skill Proposal

During the AITBC-400 epic, three tickets (AITBC-402, -405, -408) each show a `handoff` comment where the implementing agent manually assembled the same QAS evidence bundle (test output + session ID + lint result) in slightly different shapes, and QAS bounced two of them for missing fields.

````markdown
## Skill Proposal: qas-evidence-bundle

- **Recurring task**: Manual assembly of the QAS evidence bundle before the QAS gate
  (evidence: AITBC-402/-405/-408 handoff comments; -405 and -408 bounced once each
  for missing session IDs)
- **Occurrences**: 3 tickets, 2 different implementing agents
- **Belongs at**: `.claude/skills/qas-evidence-bundle/SKILL.md`
- **Draft SKILL.md**:

  ```markdown
  ---
  name: qas-evidence-bundle
  description: Assemble the standard QAS evidence bundle before requesting the QAS gate. Use when implementation is complete and the ticket moves toward QAS.
  ---

  Collect, in one comment via the task-tracking adapter (kind: gate-results):
  1. Test output (unit + integration commands and results)
  2. Session ID(s) of the implementing run
  3. Lint/type-check results
  4. Per-AC mapping: acceptance criterion → evidence line

  Post with: scripts/mock-tracker.sh comment <ID> --kind gate-results --actor <agent> --body "..."
  ```
````

The proposal ships in the report; the skill itself is created via a follow-up ticket routed through the BSA → Issue Enrichment Agent flow.

---

## 4. Worked Example: Improvement Proposal File

Retro analysis across two epics shows every project team re-writing the same evidence-comment shape because the boilerplate ships no template for it — a boilerplate gap, not a project gap. The agent writes `work/improvement-proposals/2026-07-02-add-evidence-comment-template.md`:

```markdown
# Add a gate-results evidence comment template to the boilerplate

- **Filed**: 2026-07-02
- **Filed by**: self-improvement (trigger: epic-completion)
- **Context**: AITBC-400 epic; retro findings from AITBC-300 epic

## Rationale

Across two epics, 5 tickets show hand-rolled, inconsistent gate-results comments; 3 QAS
bounces trace back to missing evidence fields. Every project inherits this gap because the
boilerplate defines the comment KINDS but ships no body template.

## Suggested Boilerplate Change

- `specs_templates/`: add `evidence-comment-template.md` (per-AC evidence mapping structure)
- `.claude/agents/qas.md`: reference the template in the gate-entry checklist
- `work/README.md`: link the template from the Comments section

## Impact

All downstream projects; removes a recurring QAS bounce class. Small, additive, no
migration needed.

## Invariants Preserved

Retro archive stays append-only; no permission or merge-gate change.

## Falsifying Eval

`bash tests/test-skill-mining.sh` — a regression here refutes the mined-skill claim.

## Rollback

Delete the harvested skill file; the miner re-proposes only on fresh evidence.

## Issue Body (copy-paste-ready)

Gate-results comments are hand-rolled per project and QAS bounces trace back to missing
fields. Proposal: ship an evidence-comment template in specs_templates/, reference it from
the QAS agent definition and work/README.md. Evidence: 5 tickets across 2 epics in a
downstream project, 3 QAS bounces. Additive change, no migration.
```

---

## 5. Human Forwarding Step

**Export duty first (ABS-260)**: every proposal about a **boilerplate-owned** file also gets one row in the
consumer-feedback CSV `work/consumer-feedback/YYYY-MM-DD-<project-slug>.csv`, format
[`.agentic/templates/consumer-feedback-item.md`](../../.agentic/templates/consumer-feedback-item.md). The prose proposal
is what the human reads; the CSV row is what the upstream intake consumes
([`BOILERPLATE_MIGRATION_SOP.md`](BOILERPLATE_MIGRATION_SOP.md) section 6.2: dedup gate → verification against HEAD → a
verdict per item back to the project). A boilerplate-level finding without an exported item never reaches upstream.

1. Human reviews the proposal file in `work/improvement-proposals/` and the exported CSV batch.
2. If worthwhile, forwards it upstream against the **boilerplate** repository (the CSV batch goes with it):

   ```bash
   gh issue create --repo <boilerplate-org>/<boilerplate-repo> \
     --title "Add a gate-results evidence comment template to the boilerplate" \
     --body-file work/improvement-proposals/2026-07-02-add-evidence-comment-template.md
   ```

3. If declined, a short note in the file (or its deletion) closes the loop.

**Hard rule**: the agent never performs step 2 — direct cross-repo writes are forbidden (ADR-A-0004); the task-tracking
adapter points at the project's tracker only, and the boilerplate evolves through upstream feature requests as its single
channel (ADR-A-0008). An **optional future enabler** may automate step 2 behind an explicit HITL approval; until then,
forwarding is fully manual.

---

## Related Documents

- [`.claude/agents/self-improvement.md`](../../.claude/agents/self-improvement.md) - Full agent role definition
- [`docs/sop/PO_AGENT_SOP.md`](PO_AGENT_SOP.md) - Trigger owner (section 5: Self-Improvement Trigger Handoff)
- [`work/improvement-proposals/README.md`](../../work/improvement-proposals/README.md) - Proposal store, naming, template
- [`.agentic/templates/consumer-feedback-item.md`](../../.agentic/templates/consumer-feedback-item.md) - Consumer-feedback CSV item format (export duty, ABS-260)
- [`docs/sop/BOILERPLATE_MIGRATION_SOP.md`](BOILERPLATE_MIGRATION_SOP.md) - Section 6: the consumer-feedback channel (export duty + upstream intake)
- [`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md) - Human-only boundaries
- [`adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md`](../../adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md) - Boilerplate ownership + upstream channel
