# Agent Workflow Standard Operating Procedure (SOP)

<!-- docs-identifier-check: skip-file — this document cites consumer-project/template example paths that intentionally do not exist in this repo (ABS-517) -->

**Purpose**: Define standard workflows for agent invocation and coordination

**Version**: 1.5 (v3 orchestrator alignment — ABS-69/ABS-79: Method 2 TDM-orchestration retired)
**Last Updated**: 2026-07-06

---

## Overview

This SOP defines the standard methods for agent workflow coordination:

1. **Method 1**: Direct Specialist Invocation (simple tasks)
2. ~~**Method 2**: TDM Orchestration~~ — **RETIRED** (see the tombstone below; standard features run
   through the v3 orchestrator, not a TDM that nest-spawns specialists)
3. **Method 3**: ARCHitect-in-CLI Orchestration (complex investigations)
4. **Method 4**: System Architect Review for Complex Code (v1.1)

---

## Method 1: Direct Specialist Invocation

**When to Use**: Simple, focused tasks requiring single specialist

**Examples**:

- Documentation updates
- Simple bug fixes
- Configuration changes
- Single-file modifications

### Workflow

```
ARCHitect-in-CLI
└─ Specialist (Complete work)
```

### Steps

1. **Identify Specialist**: Determine correct specialist for task
2. **Invoke Specialist**: Provide clear requirements and context
3. **Validate Deliverable**: Ensure work meets requirements
4. **Create PR**: If all quality gates pass

### Quality Gates

- [ ] Specialist completed all requested work
- [ ] Output matches requirements
- [ ] Tests passing (if applicable)
- [ ] Documentation updated (if applicable)

---

## Method 2: TDM Orchestration — RETIRED

**Retired (ABS-69 / ABS-76).** The original Method 2 had a **TDM subagent orchestrating other
specialist subagents** (BSA → implementer → QAS → RTE). This is **structurally impossible** under
the harness: **subagents cannot nest-spawn subagents.** A spawned agent gets a fresh, single-ticket
context and hands off through the tracker (ADR-A-0002); it has no authority to spawn a team beneath
itself. Every attempt to run "standard features" this way was paper — no automation could execute it.

**What replaces it.** Standard multi-specialist feature development is now driven by the **v3
orchestrator**, not by an agent orchestrating agents. The Coordinator (`scripts/orchestrator.sh`)
turns each ticket **status transition** into a fresh single-ticket spawn of the mapped seat, and the
mechanical JOIN / SKIP-FORWARD / rework / crash guards sequence the work — no nesting. See
[`docs/sop/ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "Epic Lifecycle (v3)" and the spec
[`specs/ABS-69-workflow-v3-full-agent-team-spec.md`](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md).

**What the TDM actually is now.** The TDM is a **blocker-triage seat**, not an orchestrator. When a
ticket enters `Blocked` (any stage, either pipeline) the Coordinator spawns the TDM **once per
Blocked entry** to classify the blocker (environment / external-dependency / scope), resolve or
reroute what agents can fix, and escalate only genuinely human-only calls. It never coordinates a
feature build. Seat details land with **ABS-76** (`Blocked → tdm` map row + `harness/claude/agents/tdm.md`
triage section); until it merges, `Blocked` still maps to `SPAWN-NOTIFY po-agent` — see the
ORCHESTRATOR_SOP "Blocked → TDM triage — target behavior" note.

The executable definition of the v3 workflow is `tests/e2e-workflow-v3.sh` (ABS-80).

---

## Method 3: ARCHitect-in-CLI Orchestration

**When to Use**: Complex investigations requiring multiple specialists with dependencies

**Examples**:

- Root cause analysis
- Complex automation creation
- Multi-specialist coordination
- Investigation-driven work

### Workflow

```
ARCHitect-in-CLI (Orchestrator)
├─ Specialist 1 (Parallel if independent)
├─ Specialist 2 (Parallel if independent)
├─ Specialist 3 (Sequential if dependent)
└─ System Architect (Review if complex code) ← See Method 4
```

### Steps

1. **Define Investigation Scope**: Clear objectives and success criteria
2. **Identify Specialists**: Determine all required specialists
3. **Coordinate Invocations**: Parallel for independent work, sequential for dependencies
4. **Validate Deliverables**: Ensure all outputs meet requirements
5. **System Architect Review**: MANDATORY if complex code created (see Method 4)
6. **Create PR**: Only after all validations and reviews

### Quality Gates

- [ ] All specialists invoked correctly
- [ ] Parallel/sequential coordination optimal
- [ ] All deliverables validated
- [ ] **System Architect review (if complex code)** ← CRITICAL
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Evidence attached to Linear

---

## Method 4: System Architect Review for Complex Code

**When to Use**: Complex automation/infrastructure code created during investigation

**MANDATORY Triggers**:

- Bash scripts >100 lines
- CI/CD workflow changes
- Infrastructure automation
- Database migration scripts
- Security-critical code
- TypeScript/JavaScript >200 lines

### Step 1: Complete Specialist Work

Invoke specialist (Data Engineer, RTE, etc.) to create deliverable:

```typescript
Task({
  subagent_type: "data-engineer",
  description: "Create production deployment script",
  prompt: `Create automated deployment script for production migrations.

Requirements:
- SSH to production server via Tailscale
- Execute migration via Docker
- Comprehensive error handling
- Rollback capability
- Validation checks

Context: [Investigation findings, requirements, constraints]`,
});
```

### Step 2: System Architect Review (MANDATORY)

After specialist delivers complex code, invoke System Architect:

```typescript
Task({
  subagent_type: "system-architect",
  description: "Review deployment automation",
  prompt: `Architectural review required for AITBC-XXX deliverables.

Files to Review:
- scripts/deploy-migration-prod.sh (710 lines bash)
- scripts/pre-migration-audit.ts (TypeScript with Prisma)
- scripts/validate-migration-rls.ts (TypeScript pre-commit hook)
- .github/workflows/migration-validation.yml (641 lines CI/CD)

Review Criteria:
1. Architectural patterns and consistency
2. Security best practices (SSH, Docker, credentials)
3. Error handling and edge cases
4. Code quality and maintainability
5. Documentation completeness

Decision Required:
- [ ] APPROVED: Ready for PR with recommendations
- [ ] REQUIRES FIXES: Detailed issues list

Context:
[What automation does, why needed, production impact]

Reference: AITBC-XXX investigation findings`,
});
```

### Step 3: Address Review Feedback

If System Architect requires fixes:

1. **Invoke specialist again** with System Architect feedback
2. **Implement fixes** addressing all issues
3. **Re-submit to System Architect** for re-review
4. **Repeat until approved**

Example:

```typescript
Task({
  subagent_type: "data-engineer",
  description: "Address System Architect feedback on deployment script",
  prompt: `System Architect review identified the following issues:

1. Missing error handling for SSH connection failures
2. Hardcoded credentials (should use environment variables)
3. No rollback mechanism for failed migrations
4. Insufficient logging for debugging

Please update scripts/deploy-migration-prod.sh to address all issues.

Original script: [Attach current version]
System Architect feedback: [Full review comments]`,
});
```

### Step 4: Create PR (Only After Approval)

Once System Architect approves:

1. **Document architectural decisions** (ADR if needed)
2. **Update Linear ticket** with review approval
3. **Create PR** with System Architect approval noted in description
4. **Attach evidence** (review approval, test results)

### Example: AITBC-321 Gap

**Missing Steps**: System Architect review NOT invoked

**What Should Have Happened**:

1. Data Engineer delivered scripts ✅
2. **System Architect reviewed scripts** ❌ (MISSING)
3. **Fixes applied based on review** ❌ (MISSING)
4. **System Architect approved** ❌ (MISSING)
5. RTE created CI/CD workflow ✅
6. **System Architect reviewed workflow** ❌ (MISSING)
7. **System Architect final approval** ❌ (MISSING)
8. PR created ❌ (Created without approval)

**Lesson**: **Never skip architectural review for complex code**

---

## Workflow Selection Guide

### Decision Tree

```
What type of work?
├─ Simple task, single specialist → Method 1
├─ Standard feature, multiple specialists → v3 orchestrator (ORCHESTRATOR_SOP; Method 2 retired)
├─ Complex investigation, multiple specialists → Method 3
└─ Complex code created? → Method 4 (MANDATORY)
```

### Complexity Assessment

**Simple** (Method 1):

- Single file changes
- Documentation updates
- Configuration tweaks
- Bug fixes <50 lines

**Standard** (v3 orchestrator — Method 2 retired):

- Feature implementation
- Multi-component changes
- Standard user stories
- Clear requirements

  Driven by ticket-status transitions through the Coordinator, not by an agent orchestrating agents.
  See [`docs/sop/ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md).

  **Intake variants (v3.1 flexible intake — ABS-102).** Standard work no longer has to start as an
  empty epic the pipeline decomposes. The orchestrator classifies each top-level ticket three ways
  (see ORCHESTRATOR_SOP "Intake classification"):

  - **Parentless ticket → Path-A** — a standalone story/bug with no parent epic runs a **solo story
    pipeline** on its own branch and ends at an **RTE PR-to-main (no auto-merge)**; it never touches
    the epic machinery (no JOIN, no epic-integration branch).
  - **Pre-populated epic → Path-B** — an epic authored **with its child tickets already attached**
    skips Grooming decomposition and enters at the **Ticket-Review Definition-of-Ready gate** over the
    existing children (auto-fix rework loop; substance-only escalation).
  - **Empty epic** — the unchanged v3.0 flow (`Grooming → Enrichment` generate the stories).

**Complex** (Method 3):

- Root cause analysis
- Multi-specialist coordination
- Investigation-driven work
- Unclear requirements

**Complex Code** (Method 4 - MANDATORY):

- Bash scripts >100 lines
- CI/CD workflows
- Infrastructure automation
- Security-critical code
- TypeScript/JavaScript >200 lines

---

## Quality Gates by Method

### Method 1 Quality Gates

- [ ] Specialist completed work
- [ ] Output matches requirements
- [ ] Tests passing (if applicable)

### Standard-Feature Quality Gates (v3 orchestrator — Method 2 retired)

- [ ] Each seat's transition-driven spawn completed and handed off via the tracker
- [ ] Handoffs recorded as `kind: handoff` comments (the runner posts them)
- [ ] Tests passing (QAS gate at `In Test`)
- [ ] Evidence attached to the ticket via the adapter

### Method 3 Quality Gates

- [ ] All specialists invoked correctly
- [ ] Deliverables validated
- [ ] **System Architect review (if complex code)**
- [ ] Tests passing
- [ ] Documentation updated

### Method 4 Quality Gates (CRITICAL)

- [ ] Specialist delivered complex code
- [ ] **System Architect reviewed code**
- [ ] **Fixes applied (if required)**
- [ ] **System Architect approved**
- [ ] Architectural decisions documented
- [ ] Linear ticket updated with approval
- [ ] PR created with approval noted

**If ANY Method 4 trigger matched: BLOCK PR until System Architect approval**

---

## Escalation Paths

The v3 escalation model is **status-driven**: an agent escalates by transitioning the ticket, and
the Coordinator spawns the right seat. `Blocked` → TDM blocker triage (ABS-76 target; see the
retired-Method-2 tombstone), `Needs PO Decision` → po-agent product decision (ABS-61). The seats
below are the destinations those transitions resolve to.

### Technical Blockers → `Blocked` (TDM triage) or `Needs PO Decision`

1. **TDM (blocker triage seat)**: classifies environment / external-dependency / scope; resolves or
   reroutes what agents can fix; escalates human-only calls. `environment` and `external-dependency`
   failures are NEVER routed back to implementers (see Loop Termination rule 1). Spawned once per
   `Blocked` entry — **not** an orchestrator (ABS-76).
2. **System Architect**: architectural guidance (also the `In Review` and `Architecture Review` seat).
3. **PO-Agent / Product Owner**: business/scope decision via `Needs PO Decision`.

### Process Issues

1. **PO-Agent** (`Needs PO Decision`): scope/priority/direction calls within delegated authority.
2. **RTE**: CI/CD and merge/integration issues (`Merging` / `Epic Integration` seats).
3. **Self-Improvement** (`Epic Done` auto-spawn): recurring process gaps → improvement proposals.

### Security Concerns → `Security Review`

1. **Security Engineer** (`Security Review` seat): independent review on security-flagged stories;
   files follow-ups. Not collapsible into any implementer.
2. **System Architect**: architectural impact.
3. **Security team**: human escalation.

---

## Success Metrics

### Method 1 Success

- Fast turnaround (<1 hour)
- Single specialist sufficient
- Quality standards met

### Standard-Feature Success (v3 orchestrator — Method 2 retired)

- Clean status-transition handoffs (no nesting, no agent-orchestrating-agents)
- Every seat's spawn completed and advanced the ticket
- Evidence consistently attached via the adapter

### Method 3 Success

- Efficient parallel/sequential coordination
- All deliverables validated
- ARCHitect-in-CLI maintained context

### Method 4 Success (CRITICAL)

- **100% of complex automation reviewed**
- **0% unreviewed scripts >100 lines**
- **System Architect approval before all PRs with complex code**
- **Architectural governance enforced**

---

## vNext Workflow Contract (AITBC-497)

### Exit States

Each agent role has an explicit exit that defines its handoff point. Two different things are
named here — do not confuse them (ABS-253):

- **Exit status** — the CANONICAL tracker status the seat transitions the ticket to. Only the
  statuses in `profiles/neutral/adapters/statuses.yaml` exist; a transition to anything else
  fails (`ERROR: transition: unknown status '<x>'`, exit=1) and the ticket stays put with no
  owning seat. The seat executes this transition itself — the runner does not do it for it.
- **Handoff label** — prose in the handoff statement, naming who picks the work up next. It is
  NOT a status and must never be passed to `transition`.

| Role             | Exit status (transition target)                                                   | Handoff label                            |
| ---------------- | --------------------------------------------------------------------------------- | ---------------------------------------- |
| BE-Developer     | `In Review`                                                                       | "Ready for QAS"                          |
| FE-Developer     | `In Review`                                                                       | "Ready for QAS"                          |
| Data-Engineer    | `In Review`                                                                       | "Ready for QAS"                          |
| System Architect | `Security Review` (`In Test` when unflagged); `Ready for Development` on findings | "Stage 1 Approved - Ready for ARCHitect" |
| QAS              | `Design Test` on a design-flagged story, else `Story Acceptance`                  | "Approved for RTE"                       |
| RTE              | `Docs` with auto-merge on, else `Ready for Merge` (human gate)                    | "Ready for HITL Review"                  |
| HITL             | `Done`                                                                            | MERGED                                   |

### Stop-the-Line Gate

**MANDATORY**: Before any implementation work begins:

1. **Check for AC/DoD**: Does the Linear ticket have acceptance criteria?
2. **If NO AC/DoD**: STOP immediately - do not proceed
3. **Escalate to BSA**: Request acceptance criteria definition
4. **Wait for AC/DoD**: Only proceed after criteria are defined

```
┌─────────────────────────────────────────────────────────────┐
│                  STOP-THE-LINE GATE                         │
│                                                             │
│  AC/DoD exists?  ──YES──▶  Proceed to implementation        │
│        │                                                    │
│        NO                                                   │
│        │                                                    │
│        ▼                                                    │
│  STOP - Escalate to BSA for acceptance criteria             │
└─────────────────────────────────────────────────────────────┘
```

### QAS Gate Owner Role

QAS is a **GATE**, not just a report producer. Work does not proceed without QAS approval.

**QAS Ownership**:

- Independent verification of ALL implementation work
- Iteration authority (can bounce back repeatedly until satisfied)
- Final evidence posted to Linear (system of record)
- Exit State: `"Approved for RTE"`

**Linear MCP Tools (MANDATORY for QAS)**:

- `mcp__linear-mcp__create_comment` - Post evidence/verdict
- `mcp__linear-mcp__update_issue` - Update ticket status
- `mcp__linear-mcp__list_comments` - Review prior evidence

### RTE PR Shepherd Role

RTE is the **PR shepherd**, not the gatekeeper. RTE does NOT merge.

**RTE Ownership**:

- PR creation (from spec/template)
- CI/CD monitoring
- Evidence assembly
- PR metadata edits
- Exit State: `"Ready for HITL Review"`

**RTE Must NOT**:

- Merge PRs (HITL is final merge authority)
- Implement product code
- Approve own work (QAS gate required)

### 3-Stage PR Review

```
┌─────────────────────────────────────────────────────────────┐
│                    3-STAGE PR REVIEW                        │
├─────────────────────────────────────────────────────────────┤
│ Stage 1: System Architect                                   │
│          └─ Pattern validation, technical review            │
│          └─ Exit: "Stage 1 Approved - Ready for ARCHitect"  │
├─────────────────────────────────────────────────────────────┤
│ Stage 2: ARCHitect-in-CLI                                   │
│          └─ Architectural alignment                         │
│          └─ Cross-cutting concerns                          │
├─────────────────────────────────────────────────────────────┤
│ Stage 3: HITL (Human-in-the-Loop)                           │
│          └─ Final merge authority                           │
│          └─ Exit: MERGED                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Role Collapsing Guidelines (AITBC-499)

### Collapsible Roles

**RTE (Release Train Engineer)**: COLLAPSIBLE

- PR creation and CI shepherding can be done by implementer
- Use when: Simple PRs, single-agent work, fast iteration needed
- Collapsed into: BE-Developer, FE-Developer, or Data-Engineer

### Non-Collapsible Roles (Independence Gates)

**QAS (Quality Assurance Specialist)**: NOT COLLAPSIBLE

- Independence gate - cannot be collapsed into implementer
- Spawn subagent for verification even in collapsed workflows
- Rationale: Self-review bias, quality enforcement

**Security Engineer**: NOT COLLAPSIBLE

- Security audit requires independence
- Cannot be performed by implementer
- Rationale: Security blindness, conflict of interest

**QAS-Design (Design Quality Assurance)**: NOT COLLAPSIBLE

- Independence gate - cannot be collapsed into UI/UX Design Agent or any implementer
- Spawn subagent for design verification even in collapsed workflows
- Rationale: Self-review bias for design (designer never tests own designs)

### Collapsed Workflow Example

```
Standard Workflow:
BE-Developer → QAS → RTE → HITL

Collapsed Workflow (RTE collapsed):
BE-Developer → QAS → [BE handles PR] → HITL

Note: QAS gate is ALWAYS present, never collapsed
```

---

## Loop Termination Rules (ABS-11)

These rules prevent infinite iteration cycles and mandate human escalation at critical points. They apply to both QAS (functional gates) and QAS-Design (design gates). All agents and humans reference this single authoritative section.

### 1. Failure Classification (Mandatory Before Any Bounce)

Before returning work to any implementer or designer, classify the failure as exactly one of:

- **`code`** - Bug in implementation (wrong logic, missing feature, test failure, design defect)
- **`spec`** - Spec/DAC incomplete or unclear (acceptance criteria missing, requirements ambiguous, DACs untestable)
- **`environment`** - Missing/invalid secrets, env vars, services, permissions, or credentials in the runtime
- **`external-dependency`** - Third-party service/account/API key no agent can provision

**Critical Rule**: `environment` and `external-dependency` failures are NEVER routed to implementers or designers. Escalate to TDM/human on the FIRST occurrence — the fix is outside their scope.

### 2. Iteration Cap

Every bounce comment posted to the ticket MUST include the literal marker `Iteration N of 3`, where N = (number of prior bounce comments on the ticket) + 1. Read N from actual tracker comments — never trust agent memory.

At N = 3, bouncing is FORBIDDEN:

1. Collect all three failed iterations
2. Quote the full failure chain in escalation
3. Route to TDM/POPM with: "Three iterations exhausted."

### 3. Same-Error-Twice Rule

If the same failure signature (identical error message or failing assertion) appears in two consecutive validation runs after a fix attempt, escalate to TDM/human immediately, regardless of N. The fixes are not reaching the root cause — this needs human triage.

### 4. DAC Change Freeze

Design Acceptance Criteria (DACs) are immutable during an open iteration cycle. If the designer believes a DAC is wrong or scope changed:

1. The ticket goes back to the BSA/spec level (re-opened)
2. The current iteration cycle ends
3. The counter resets only after revised DACs are re-accepted on the ticket

QAS-Design MUST reject any revision that arrives with silently changed DACs.

### 5. Arbiter Rule

If two fixers each claim a failure belongs to the other (e.g., implementer vs. tech-writer, or implementer vs. QAS on classification), TDM issues a binding classification after ONE round trip — no second ping-pong.

### 6. Environment Preflight

Implementers MUST validate the spec's Environment Prerequisites section BEFORE implementing. Gaps in environment readiness (missing credentials, unavailable services, unprovisioned accounts) escalate to a human for resolution (per ADR-A-0004 Amendment 2026-07-03). Credentials provisioning is human-only; agents cannot fix environment prerequisites.

### 7. Mechanical Enforcement (ABS-12)

The iteration cap (rule 2) is enforced by the harness, not by prompt language alone. A `PreToolUse` hook (`scripts/hooks/iteration-guard.sh`) fires whenever a gate agent posts a bounce marker. It counts the ticket's prior REAL bounces — a marker-bearing gate comment followed by a backward transition (counting model v2, ABS-115) — **through the task-tracking adapter** and **blocks the bounce (exit 2)** once the next bounce would reach the cap — the agent physically cannot bounce again and must escalate. This removes the dependency on a mid-loop model self-diagnosing that it is on attempt N. APPROVE results that mention the marker informationally MUST carry the literal `(no bounce)` suffix (as rule 2's convention already shows) — it is what lets the hook distinguish an approval from a bounce at cap; quoted markers in operator/decision comments never count.

> **Wiring lives in `.claude/settings.template.json` (ABS-32).** The live hook wiring is the `"hooks"` block of `.claude/settings.template.json` — the file Claude Code auto-loads once it is copied to `.claude/settings.json`. `.claude/hooks-config.json` is an annotated source-of-record mirror only and is **not** loaded at runtime. This closes the ABS-23 regression, where the old wiring in `hooks-config.json` (never loaded, with command-in-matcher patterns like `Bash.*git push` that can never match the tool name `Bash`, and `exit 1` blockers that do not block) meant the iteration guard, push blocker, and commit reminder were all dead code. Matchers are now tool names only; command conditions read the tool-call JSON on stdin via `jq`; genuine policy blocks exit 2. Behavior is verified by `tests/test-hooks-behavioral.sh`.

- **Cap source**: `M` in the most recent `Iteration N of M` marker; default 3. Per-gate: forward progress over a gate resets only that gate's counter (ABS-115).
- **Cumulative budget**: a second, never-resetting per-ticket counter caps total real bounces at `ITERATION_GUARD_TICKET_CAP` (default 9, `0` = off) — the general cost/time brake per ticket.
- **Fail-open**: if the tracker is unreachable or no ticket id is derivable, the guard allows the handoff (exit 0) with a stderr warning — a broken tracker never deadlocks all agent work, and rules 1–6 above remain the fallback layer.
- **Human override**: after a block, a human triages the root cause and either closes the ticket or raises the per-ticket cap by posting a corrected marker directly in a terminal outside Claude Code (hooks only run inside the harness). Design records: `specs/ABS-12-iteration-guard-spec.md`, `specs/ABS-115-iteration-guard-v2-spec.md`.

---

## Direct Implementation Status Discipline (ABS-126)

When a seat implements a ticket directly (not via orchestrator-managed spawn) the
agent must keep the tracker in sync manually. #PATH_DECISION: single-operator
account vs per-role accounts vs unset (graceful no-op) — configure via
`ORCH_ASSIGNEE` / `ORCH_ASSIGNEE_<ROLE>`; **never hardcode accountIds** (ADR-A-0010).

| Work phase | Tracker action | Command |
|---|---|---|
| Implementation begins | Transition to **In Progress** + set assignee | `tracker transition <id> "In Progress" --actor <role> --reason "starting implementation"` then `tracker assign <id> "$ORCH_ASSIGNEE"` |
| Commit + evidence attached | Transition to **In Review** + post handoff comment | `tracker transition <id> "In Review" --actor <role> --reason "implementation complete"` then `tracker comment <id> --kind handoff --actor <role> --body "…"` |
| Review accepted | Follow pipeline (QAS → Done) | Handled by reviewer seat or orchestrator |

**Rules:**

1. Use `tracker assign` (the adapter command) — never raw REST calls (ADR-A-0006/0007).
2. Assignee at start: read from `ORCH_ASSIGNEE_<ROLE>` (beats) or `ORCH_ASSIGNEE`. Empty = graceful skip, no error.
3. Post the handoff comment **before** transitioning to In Review so reviewers see the evidence immediately.
4. If the seat is orchestrator-managed (spawned via `live_spawn`), the orchestrator already calls `tracker assign` at spawn time — do not call it again.

---

## Related Documentation

- [`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) - v3 Epic Lifecycle: the status-driven workflow that replaces Method 2
- [`specs/ABS-69-workflow-v3-full-agent-team-spec.md`](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md) - full-agent-team v3 spec
- `TDM_AGENT_ASSIGNMENT_MATRIX.md` - Specialist assignment guide
- `ARCHITECT_IN_CLI_ROLE.md` - ARCHitect-in-CLI responsibilities
- `AGENT_CONFIGURATION_SOP.md` - Tool restrictions, model selection
- `WORKFLOW_COMPARISON.md` - TDM role clarification
- `WORKFLOW_MIGRATION_GUIDE.md` - vNext transition guide
- `PRE_PR_VALIDATION_CHECKLIST.md` - Quality gates before PR
- `WORKFLOW_QUALITY_CHECKLIST.md` - Self-validation checklist

### Loop Termination Rules Implementation

- `.claude/agents/qas.md` - QAS iteration authority and failure classification details
- `.claude/agents/qas-design.md` - QAS-Design iteration authority, DAC change freeze, and failure classification
- `adrs/agentic/ADR-A-0004-human-approval-boundaries.md` - Human-only decision boundaries (including credentials provisioning amendment 2026-07-03)
- `scripts/hooks/iteration-guard.sh` + `specs/ABS-12-iteration-guard-spec.md` - Mechanical enforcement of the iteration cap (ABS-12)

---

## Version History

### v1.5 (2026-07-06)

- **Retired**: Method 2 (TDM Orchestration) — structurally impossible (subagents cannot nest-spawn);
  standard features run through the v3 orchestrator (ABS-69). TDM is a blocker-triage seat (ABS-76).
- **Updated**: decision tree, complexity assessment, quality gates, success metrics, and the
  escalation matrix to the status-driven v3 model.
- **Added**: cross-links to [`ORCHESTRATOR_SOP.md`](ORCHESTRATOR_SOP.md) "Epic Lifecycle (v3)" and
  the ABS-69 spec; noted `tests/e2e-workflow-v3.sh` as the workflow's executable definition.

### v1.4 (2025-12-23)

- **Added**: vNext Workflow Contract (AITBC-497)
- **Added**: Role Collapsing Guidelines (AITBC-499)
- **Added**: Exit States for all agent roles
- **Added**: Stop-the-Line Gate (mandatory AC/DoD check)
- **Added**: QAS Gate Owner role with iteration authority
- **Added**: RTE PR Shepherd role (no code, no merge)
- **Added**: 3-Stage PR Review process
- **Updated**: Related Documentation links
- **Rationale**: Major upgrade establishing clear ownership boundaries and mandatory gates

### v1.3 (2025-12-15)

- **Changed**: TDM role from orchestrator to reactive blocker resolution
- **Added**: ARCHitect-in-CLI as primary orchestrator
- **Impact**: Clearer role boundaries

### v1.1 (2025-10-06)

- **Added**: Method 4 (System Architect Review for Complex Code)
- **Rationale**: AITBC-321 gap discovery (unreviewed complex automation)
- **Impact**: Prevents future governance gaps

### v1.0 (2025-10-05)

- Initial SOP with Methods 1-3
- Basic workflow patterns
- Quality gates defined

---

**Reference**: AITBC-497/499 vNext Workflow Contract
