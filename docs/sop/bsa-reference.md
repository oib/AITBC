# BSA Reference (examples, templates, evidence patterns)

Companion to `.claude/agents/bsa.md`. The agent definition keeps the decision
rules, gates, and output formats; this file holds the worked examples and
long-form templates the BSA pulls in **only when actually authoring** the
artifact named below. Spec-authoring templates (spec structure, AC patterns,
demo scripts, evidence blocks) live in the **`spec-creation` skill** — this doc
does not duplicate them.

---

## Planning Mode — SAFe Work Breakdown template

Trigger: authoring an Epic → Features → Stories breakdown in
`specs/{feature-name}-planning.md` (copied from `specs_templates/planning_template.md`).
Read `docs/team/PLANNING-AGENT-META-PROMPT.md` first — it carries current CI/CD
standards and SAFe methodology.

```markdown
## SAFe Work Breakdown

### Epic
- **Title**: [Business initiative name]
- **Description**: [Business objective]
- **Business Outcomes**: [Expected results]
- **KPIs/Metrics**: [Success measurement]

### Features
1. **Feature 1**: [Functional component]
   - Description / Acceptance Criteria / Dependencies / Estimated Effort (T-shirt)

### User Stories
1. **Story 1** (→ Feature 1):
   - **User Story**: As a [user], I want to [action], so that [benefit]
   - **Acceptance Criteria**: [ ] measurable outcome; [ ] measurable outcome
   - **Technical Notes** / **Estimated Story Points** (Fibonacci)

### Technical Enablers (20–30% capacity)
1. **Enabler 1**: type (Architecture/Infrastructure/Tech Debt/Research) / justification / AC

### Spikes
1. **Spike 1**: question to answer / time-box / expected outcomes
```

Testing strategy to define per breakdown: Unit, Integration, E2E, Performance,
Security (auth/RLS/data protection), Accessibility (WCAG 2.1 AA).

---

## Spec Creation Mode — section scaffolds

Trigger: authoring `specs/AITBC-XXX-{description}-spec.md` (copied from
`specs_templates/spec_template.md`). The authoritative spec structure, AC
patterns, AC-coverage rules, demo script, and quality checklist are in the
**`spec-creation` skill** — follow it. These scaffolds are the low-level task
shape the skill does not spell out:

```markdown
## Low-Level Tasks
1. [Task]
   - File(s) to create/modify: [paths]
   - Function(s) to create/modify: [names]
   - Implementation details: [code changes / data structures / edge cases]
   - Testing approach: [test cases]

## Technical Implementation Details
- **Architecture**: fit into existing architecture; components affected; decisions needed
- **Dependencies**: external (libraries/services/APIs) + internal + version requirements
- **Security**: RLS requirements / auth / data protection
- **Performance**: response time / resource constraints / benchmarks
```

---

## Evidence Attachment template

```markdown
## BSA Evidence — [Ticket Number]

### Pattern Discovery
- Similar features found / Reusable patterns identified / New patterns needed

### User Story Quality
- ✅ User story format validated
- ✅ Acceptance criteria testable
- ✅ Testing strategy comprehensive

### Validation Results
`yarn lint:md` → [output]

### Architectural Review
- System Architect approval: [Yes/No] / Approved patterns: [list]
```

---

## Common user-story patterns

**Feature implementation**

```markdown
As an authenticated user
I want to [perform action]
So that I can [achieve business value]

Acceptance Criteria:
- [ ] UI component renders correctly
- [ ] API endpoint processes request
- [ ] Database operation enforces RLS
- [ ] Error handling covers edge cases
- [ ] Success/failure feedback to user
```

**Bug fix**

```markdown
As a user experiencing [bug]
I want the system to [correct behavior]
So that I can [complete workflow]

Acceptance Criteria:
- [ ] Root cause identified
- [ ] Fix implemented with test coverage
- [ ] Regression test prevents recurrence
- [ ] Related edge cases validated
```

---

## Follow-Up Ticket — worked examples

See `docs/sop/FOLLOW_UP_TICKET_SOP.md` for the full worked examples of the
create / in-scope / discard decision.
