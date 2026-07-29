# Design Workflow Standard Operating Procedure (SOP)

**Purpose**: Define the design request flow for the UI/UX Design Agent, its handoff to the QAS-Design Agent, and the independent design testing stage

**Version**: 1.1 (ABS-3, ABS-10)
**Last Updated**: 2026-07-02

---

## Overview

This SOP covers design work end-to-end:

```text
Request -> Read design system -> Design + Design ACs
        -> Attach to ticket via adapter -> Handoff to QAS-Design
        -> Design Testing (pre-check + per-DAC verification)
        -> Verdict: Design Approved | back to designer (iteration loop)
```

**Agents involved:**

- **UI/UX Design Agent** (`.claude/agents/ui-ux-design.md`) - creates the design and design ACs
- **QAS-Design Agent** (`.claude/agents/qas-design.md`) - independently verifies the design against the ACs (see "Design Testing Stage" below)

---

## The Independence Rule (NON-NEGOTIABLE)

**The UI/UX Design Agent NEVER tests its own designs.**

Design verification belongs exclusively to the QAS-Design Agent. This mirrors
the QAS and Security Engineer independence gates in
`docs/sop/AGENT_WORKFLOW_SOP.md` § "Role Collapsing Guidelines": self-review
bias makes designer-run verification worthless as a quality gate. The
designer's obligation is to make every AC *testable*; executing the tests is
QAS-Design's job, even in collapsed workflows.

---

## Design Request Flow

### Step 1: Request

A design need arrives via a ticket (created through the Issue Enrichment
Agent / task-tracking adapter). The request should state the component/page,
the user goal, and any constraints.

### Step 2: Read the Design System

The UI/UX Design Agent reads the design-system file at
`{{DESIGN_SYSTEM_PATH}}` (default: `docs/design/DESIGN_SYSTEM.md`;
`.html` also supported).

**If the file is missing**: STOP. Request one from the requester; offer to
bootstrap a minimal starter from documented defaults. Never design against
invented styles.

### Step 3: Design + Design ACs

Produce the design artifact
(`docs/agent-outputs/designs/AITBC-{number}-design.md`), citing
design-system tokens/components for every choice. Report any needed deviation
to the requester instead of improvising.

Write a Design Acceptance Criteria block covering, at minimum:
schema conformance, accessibility basics, responsive breakpoints, key user flows.

### Step 4: Attach to Ticket via Adapter

```bash
# Local (mock adapter):
scripts/mock-tracker.sh comment AITBC-XXX \
  --kind handoff --actor ui-ux-design --body "<Design AC block>"

# Production: same block via the tracker MCP
# (e.g. mcp__linear-mcp__create_comment)
```

### Step 5: Handoff to QAS-Design

Hand off three items to the QAS-Design Agent:

1. Design artifact path
2. Design ACs (on the ticket)
3. Design-system file reference (`{{DESIGN_SYSTEM_PATH}}` + version/date)

Exit state: `"Ready for QAS-Design"`. QAS-Design verifies each DAC and
approves or bounces the design back (iteration authority, as with QAS).

---

## Worked Example

**Request** (AITBC-142): "Design a login form for the marketing
site."

**Step 2**: Agent reads `docs/design/DESIGN_SYSTEM.md` - finds
`color.primary`, `spacing.md`, `font.size.md`, `Input` and `Button/primary`
components ({{UI_LIBRARY}}), breakpoints `mobile`/`tablet`/`desktop`.

**Step 3**: Agent writes
`docs/agent-outputs/designs/AITBC-142-design.md`: a single-column
card (`color.surface`, padding `spacing.md`) with email + password `Input`
fields and a full-width `Button/primary` submit, stacked with `spacing.sm`.

**Step 4**: Agent posts this Design AC block to the ticket:

```markdown
## Design Acceptance Criteria [AITBC-142]

**Design artifact**: docs/agent-outputs/designs/AITBC-142-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md (2026-07-02)

### Schema Conformance
- [ ] DAC-1: Submit button uses `Button/primary` with `color.primary` per design system § Components
- [ ] DAC-2: Card padding is `spacing.md`; field gap is `spacing.sm`

### Accessibility
- [ ] DAC-3: Label/background contrast >= 4.5:1 for both field labels
- [ ] DAC-4: Focus order is email -> password -> submit; both inputs have programmatic labels

### Responsive
- [ ] DAC-5: At `mobile` breakpoint, card spans full width minus `spacing.md` margins; no horizontal scroll

### User Flows
- [ ] DAC-6: User can complete login in 3 steps (enter email, enter password, activate submit) using keyboard only
```

```bash
scripts/mock-tracker.sh comment AITBC-142 \
  --kind handoff --actor ui-ux-design --body "$(cat design-ac-block.md)"
```

**Step 5**: Agent hands off:

> "Design complete for AITBC-142. Artifact at
> docs/agent-outputs/designs/AITBC-142-design.md. Design ACs
> posted to ticket. Design system: docs/design/DESIGN_SYSTEM.md. Ready for
> QAS-Design verification."

The QAS-Design Agent then verifies DAC-1 through DAC-6 independently
and posts the verdict. The designer does not participate in verification.

---

## Design Testing Stage (QAS-Design)

The QAS-Design Agent (`.claude/agents/qas-design.md`) picks up the
`"Ready for QAS-Design"` handoff and runs the design gate. The designer
never participates in this stage.

### Stage 1: Pre-Check

Before executing any test, QAS-Design verifies:

- DAC block exists on the ticket and the design artifact exists at the stated path
- Every criterion is testable without asking the designer (concrete tokens, values, steps)
- The design-system file exists at `{{DESIGN_SYSTEM_PATH}}`

If the DAC block is missing or any criterion is untestable, QAS-Design
**rejects back to the UI/UX Design Agent with reasoning** - it never invents
or repairs criteria itself:

> "QAS-Design pre-check FAILED for AITBC-142. Rejecting to
> @ui-ux-design: DAC-5 names no breakpoint behaviour ('should look fine on
> phones' is untestable). Resubmit with testable criteria."

### Stage 2: Per-DAC Verification

QAS-Design verifies each DAC individually against the design artifact and
`{{DESIGN_SYSTEM_PATH}}`, recording PASS/FAIL with evidence. Minimum
coverage regardless of DAC wording: design-schema conformance,
accessibility basics (contrast, focus order, labels), responsive
breakpoints, key user-flow sanity.

### Stage 3: Evidence + Verdict via Adapter

Test results are attached to the design ticket using the `gate-results`
comment kind (the adapter's kind for test/gate outcomes):

```bash
scripts/mock-tracker.sh comment AITBC-142 \
  --kind gate-results --actor qas-design --body "$(cat design-test-report.md)"

# Production: same report via the tracker MCP
# (e.g. mcp__linear-mcp__create_comment)
```

**Pass verdict example** (report body, continuing the worked example):

```markdown
## Design Test Report [AITBC-142]

**Artifact**: docs/agent-outputs/designs/AITBC-142-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md (2026-07-02)

- DAC-1: PASS - submit uses `Button/primary` with `color.primary` (design system § Components)
- DAC-2: PASS - card padding `spacing.md`, field gap `spacing.sm`
- DAC-3: PASS - label contrast 7.2:1 (>= 4.5:1)
- DAC-4: PASS - focus order email -> password -> submit; programmatic labels present
- DAC-5: PASS - `mobile`: full width minus `spacing.md` margins, no horizontal scroll
- DAC-6: PASS - keyboard-only login in 3 steps

**Verdict: DESIGN APPROVED** - ready for implementation (functional gate remains with QAS)
```

**Fail verdict example** (iteration loop back to the designer):

```markdown
## Design Test Report [AITBC-142]

- DAC-1: PASS
- DAC-2: FAIL - artifact specifies card padding `spacing.lg`; DAC-2 and
  design system § Layout require `spacing.md`
- DAC-3: FAIL - `color.text.muted` on `color.surface` computes to 3.9:1,
  below the 4.5:1 body-text minimum
- DAC-4 .. DAC-6: PASS

**Verdict: DESIGN BLOCKED** - returning to @ui-ux-design for iteration
```

The fail path loops: QAS-Design returns findings per DAC to the UI/UX
Design Agent, the designer revises the artifact (never QAS-Design), hands
off again with exit state `"Ready for QAS-Design"`, and QAS-Design re-runs
the pre-check and full per-DAC verification. The loop repeats until all
DACs pass (iteration authority, as with the general QAS) or QAS-Design
escalates to a human (TDM/POPM) after repeated unresolved loops.

**Gate boundary**: QAS-Design approves the design only (the DACs). The
general QAS remains the gate owner for functional ACs and test suites on
the implementation - no double gate for the same criteria.

---

## Related Documentation

- `.claude/agents/ui-ux-design.md` - UI/UX Design Agent definition
- `.claude/agents/qas-design.md` - QAS-Design Agent (testing counterpart)
- `docs/design/DESIGN_SYSTEM.md` - design-system starter template
- `docs/sop/AGENT_WORKFLOW_SOP.md` - Role Collapsing Guidelines (independence gates)
