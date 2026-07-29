# System Architect — Reference Material

On-demand reference for the `system-architect` seat. The seat prompt
(`.claude/agents/system-architect.md`) carries the decision rules, gate criteria,
handoff contracts, output formats, and escalation triggers. This file holds the
**verbose supporting material** — search-command examples, long output templates,
evidence patterns, and background rationale — so it is only paid for in the turns
that actually produce those artifacts.

**Read this file when** you are: producing a spec-review verdict, authoring an ADR,
writing a PR-review comment, extracting/approving a pattern, or attaching evidence.

---

## 1. Pattern & Session Discovery — Search Commands

Used during pattern validation and conflict prevention.

```bash
# Existing architectural patterns / implementations
grep -r "pattern_name" app/ lib/ components/
grep -r "withUserContext|withAdminContext|withSystemContext" app/
grep -r "authentication|authorization" lib/

# Existing ADRs
ls adrs/ 2>/dev/null || echo "No ADRs yet"

# Architectural decisions / conflicts from other agents' session history
grep -r "architectural|pattern|decision" ~/.claude/todos/ 2>/dev/null
grep -r "TODO|FIXME|hack" ~/.claude/todos/

# Similar architecture in specs
ls specs/AITBC-*-spec.md | grep "architecture|enabler"
grep -r "Technical Enabler" specs/*planning.md
grep -r "Architecture|Technical Implementation" specs/
```

### Reference documentation for validation

- `CONTRIBUTING.md` — project standards
- `docs/database/DATA_DICTIONARY.md` — database architecture (single source of truth)
- `docs/database/RLS_IMPLEMENTATION_GUIDE.md` — security patterns (CRITICAL)
- `docs/guides/SECURITY_FIRST_ARCHITECTURE.md` — security-first principles
- `specs_templates/planning_template.md`, `specs_templates/spec_template.md`
- `patterns_library/README.md` + all `docs/architecture/` ADRs

---

## 2. Spec Review Protocol (full workflow)

### When to review

BSA creates a new implementation spec · technical enablers proposed in planning ·
architectural changes documented · new patterns introduced.

### Steps

1. **Access spec**: `cat specs/AITBC-XXX-{feature}-spec.md`
2. **Architectural analysis** — review sections:
   - High-Level Objective — aligns with business goals?
   - Technical Implementation — architecture complete? fits existing AITBC
     architecture? components affected identified? tech-stack considerations documented?
   - Dependencies — all identified?
   - Security — RLS, auth, data protection?
   - Performance — realistic and measurable?
3. **Pattern validation** — search for similar implementations; validate against SOLID
   (Single Responsibility, Open/Closed, Liskov, Interface Segregation, Dependency Inversion).
4. **Technical Enabler review** (if present): Type (Architecture/Infrastructure/Tech
   Debt/Research) · Justification sound? · Acceptance criteria testable? · Allocated to
   20–30% capacity? · Dependencies clear?
5. **Provide feedback** (templates below).
6. **Update spec** with the review section.
7. **Create ADR** if a significant decision (Guided ADR Authoring, §3).

### Verdict — APPROVED

```markdown
## Architectural Review - AITBC-XXX

### Review Date
[Date]

### Architecture Assessment
✅ **APPROVED**

### Pattern Validation
- Existing pattern: [Pattern name from codebase]
- Alignment: Follows established patterns
- No conflicts identified

### Recommendations
[Any suggestions for improvement]

### ADR Required
[Yes/No - if significant architectural decision]
```

### Verdict — REJECTED

```markdown
## Architectural Review - AITBC-XXX

### Review Date
[Date]

### Architecture Assessment
❌ **REJECTED - Requires Revision**

### Issues Identified
1. [Issue]: [Description]
   - **Risk**: [What could go wrong]
   - **Recommendation**: [How to fix]

### Required Changes
- [ ] [Change 1]
- [ ] [Change 2]

### Re-review Required
Yes - after changes implemented
```

### Spec review section (added to the spec)

```markdown
## Architectural Review
- **Reviewer**: System Architect
- **Date**: [Date]
- **Status**: Approved/Rejected
- **ADR**: [If created, link to adrs/<level>/ADR-XXX.md]
- **Recommendations**: [Any suggestions]
```

---

## 3. Guided ADR Authoring — templates & rationale

Decision rules (hierarchy, scan-first, conflict stop-the-line, bidirectional links,
invocation contract) live in the seat prompt. Use the ADR template from the
`confluence-docs` skill — do NOT invent a new structure.

### ADR file creation

```bash
# Choose the level dir per adrs/README.md: agentic | company | project
touch adrs/project/ADR-P-XXXX-{decision-title}.md
```

### ADR body skeleton (if the skill template is unavailable)

```markdown
# ADR-XXX: [Title] (From AITBC-YYY)

## Status
Proposed        <!-- only a human accepts: status: accepted + accepted_by -->

## Context
[Business and technical context]

## Decision
[What was decided]

## Consequences
### Positive
- [Benefit]
### Negative
- [Trade-off]

## Alternatives Considered
1. [Alternative A]: [Why rejected]
2. [Alternative B]: [Why rejected]

## Related Decisions
- [Related / superseded / superseding ADRs — bidirectional links]

## References
- Spec: specs/AITBC-YYY-{feature}-spec.md
- Ticket: AITBC-YYY
```

### Scan for existing coverage (Step 1 commands)

```bash
grep -ril "topic_keyword" adrs/agentic/ adrs/company/ adrs/project/ 2>/dev/null
grep -ril "topic_keyword" adrs/ docs/architecture/decisions/ 2>/dev/null
cat adrs/agentic/README.md
```

### PO-Agent handoff (Path A) request format

```markdown
## ADR Authoring Request
**From**: PO-Agent
**Ticket**: AITBC-XXX
**Topic**: [Decision topic]
**Context**: [Why a decision is needed now]
**Proposed Level**: [company/agentic/project - System Architect validates]
```

---

## 4. PR Review — verbose material

Gate criteria (the mandatory checklist) live in the seat prompt. Below are the
command examples, the long verdict templates, common-issue reference, and metrics.

### Analysis commands

```bash
# Access PR (Bitbucket: bb, GitHub: gh — gh)
gh pr view [PR_NUMBER]
gh pr diff [PR_NUMBER]
gh pr checks [PR_NUMBER]
# Linear/tracker context: mcp__linear-mcp__get_issue

# Pattern & RLS spot checks
grep -r "withUserContext|withAdminContext|withSystemContext" [changed_files]
grep -r "prisma\." [changed_files] | grep -v "withUserContext|withAdminContext|withSystemContext"
grep -r "await auth()" [changed_files]; grep -r "if (!userId)" [changed_files]
grep -r ": any" [changed_files]
grep -r "try {" [changed_files]; grep -r "NextResponse.json.*error" [changed_files]
```

### Migration safety (if applicable)

`cat prisma/migrations/[name]/migration.sql` — verify: no `DROP TABLE` without backup ·
no data-loss risk · proper indexes · RLS policies added for any new table.

### Verdict — APPROVED

```markdown
## System Architect PR Review - AITBC-XXX (PR #XXX)

### Review Date
[Date and time]

### Technical Validation
✅ **APPROVED**

### Checklist Results
- [x] Pattern compliance verified
- [x] RLS context enforced
- [x] Authentication correct
- [x] Database migrations safe (N/A if none)
- [x] TypeScript types valid
- [x] Error handling comprehensive
- [x] Performance acceptable
- [x] No architectural conflicts

### Code Quality Assessment
**Rating**: Excellent/Good/Acceptable
**Notes**: [Any observations]

### Next Step
**ESCALATE TO ARCHitect-in-CLI** for Stage 2 comprehensive review

---
**Reviewer**: System Architect (Opus)
**Review Duration**: [X minutes]
```

### Verdict — CHANGES REQUESTED

```markdown
## System Architect PR Review - AITBC-XXX (PR #XXX)

### Review Date
[Date and time]

### Technical Validation
⚠️ **CHANGES REQUESTED**

### Issues Identified
#### CRITICAL (Must Fix Before Approval):
1. **RLS Context Missing** (Line XX in [file])
   - **Issue**: Direct Prisma call without RLS context
   - **Fix**: Wrap in `withUserContext(prisma, userId, async (client) => {...})`
   - **Risk**: Cross-user data access vulnerability

#### MEDIUM (Should Fix):
2. **Performance Concern** (Line ZZ in [file])
   - **Issue**: N+1 query pattern detected
   - **Recommendation**: Use Prisma `include`

### Required Actions
- [ ] Fix Critical Issue #1
- [ ] Address Medium Issue #2

### Re-Review Required
**YES** - after changes pushed

### TDM Action Required
Coordinate with [Agent] to address feedback.

---
**Reviewer**: System Architect (Opus)
**Review Duration**: [X minutes]
```

### Post the verdict

```bash
gh pr review [PR_NUMBER] --comment --body "[markdown]"
gh pr review [PR_NUMBER] --approve --body "[approval markdown]"
gh pr review [PR_NUMBER] --request-changes --body "[changes markdown]"
```

Then notify TDM (Linear comment: approved → ready for Stage 2; changes → issues summary,
coordinate fixes, wait for updated PR).

### Common PR issues (from pattern analysis)

1. RLS context missing (~40%) — always use `withUserContext/withAdminContext/withSystemContext`
2. Authentication bypass (~25%) — add `const { userId } = await auth();`
3. Type-safety violations (~20%) — remove `any`, add interfaces
4. Performance (~10%) — optimize queries, add indexes, paginate
5. Error-handling gaps (~5%) — try/catch, proper error responses

### Review metrics to report to TDM

Review duration (target <15 min) · issues per category · first-review approval rate ·
re-review cycles (target <2).

---

## 5. Pattern Library Maintenance (when BSA proposes a new pattern)

1. **Validate need** — confirm it doesn't already exist:
   `ls patterns_library/**/*.md | grep -i "similar_pattern"`; `grep -r "proposed_pattern" app/ lib/ components/`
2. **Extract from a proven implementation** — find the best existing implementation and
   review it for quality, security, RLS compliance.
3. **Document** — `touch patterns_library/{category}/{pattern-name}.md`, using the template
   from `patterns_library/README.md`.
4. **Validate quality**: RLS enforced (if DB) · auth required (if protected) · Zod input
   validation · comprehensive error handling · TS strict · copy-paste ready with
   placeholders · security checklist included.
5. **Add to index** — update `patterns_library/README.md` category table.
6. **Approve** with an approval note (extracted-from path, RLS status, security validated).

### Pattern template

```markdown
# Pattern Name
## What It Does
[Purpose and use case]
## When to Use
- Use case 1
## Code Pattern
[Complete, copy-paste ready code]
## Customization Guide
1. Replace `{placeholder}` with your value
## Security Checklist
- [ ] RLS context enforced
- [ ] Auth required
- [ ] Input validated
## Validation
[Commands to verify]
```

---

## 6. Evidence Attachment Template

```markdown
## Architectural Decision - [Ticket Number]

### Session ID
[Claude session ID]

### Pattern Discovery
- Existing patterns found: [list]
- Conflicts identified: [list]
- New patterns approved: [list]

### Decision Rationale
[Why this approach was chosen]

### Validation Results
\`\`\`bash
yarn lint && yarn type-check && yarn build
# [Output]
\`\`\`

### ADR Created
- ADR-XXX: [Title]
- Location: adrs/<level>/ADR-XXX-title.md
```

---

## 7. Common Architectural Patterns (code)

### RLS context (MANDATORY for DB operations)

```typescript
// User operation
const result = await withUserContext(prisma, userId, async (client) => {
  return client.tableName.findMany({ where: { user_id: userId } });
});
// Admin operation (requires admin role)
const adminResult = await withAdminContext(prisma, userId, async (client) => {
  return client.tableName.findMany();
});
// System operation (background tasks)
const systemResult = await withSystemContext(prisma, "operation", async (client) => {
  return client.tableName.create({ data: systemData });
});
```

### API route

```typescript
// app/api/[route]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { withUserContext } from "@/lib/db/rls-helpers";
import prisma from "@/lib/prisma";

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const data = await withUserContext(prisma, userId, async (client) => {
    return client.tableName.findMany({ where: { user_id: userId } });
  });
  return NextResponse.json({ data });
}
```

### UI component

```typescript
// components/feature/ComponentName.tsx
import { useAuth } from "@clerk/nextjs";
export function ComponentName() {
  const { userId } = useAuth();
  // UI logic
}
```

---

## 8. Background rationale

- **Stage-1 review context**: You are Stage 1 of the 3-stage PR review (Stage 2 =
  ARCHitect-in-CLI comprehensive review; Stage 3 = HITL oib final merge).
  Target ~5–15 minutes per PR. Review trigger: after RTE creates the PR (automatic
  escalation from TDM). Automated re-review: on PR update after changes requested, re-run
  the full checklist.
- **Architecture & Governance Owner (AITBC-314)** — supporting docs:
  `SYSTEM_INTEGRATION_MAP.md`, `DATA_GOVERNANCE_POLICY.md`, `DATA_OWNERSHIP_MATRIX.md`,
  `DISASTER_RECOVERY_PLAYBOOK.md`.
- **Conflict-prevention checklist**: no duplicate implementations · follows existing
  patterns · no conflicting RLS context · TS types defined · consistent error handling ·
  no new security vulnerabilities · build passes · no regression risk.
