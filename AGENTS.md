# SAFe Agent Team Quick Reference

> **Philosophy**: "Search First, Reuse Always, Create Only When Necessary"
>
> Pattern discovery is MANDATORY before implementation.
>
> **Team Culture**: "We work as a round table team that has 4 pillars of SAFe inscribed on that round table. It means something."
>
> **Note**: This file is auto-loaded as system instructions by tools that follow the `AGENTS.md` convention, including Codex CLI and Google Antigravity (see [.agents/README.md](./.agents/README.md)).

## Documentation

**Workflow SOPs:**
5
- [Agent Workflow SOP v1.4](./docs/sop/AGENT_WORKFLOW_SOP.md) - vNext contract, Exit States, Role Collapsing (AITBC-497/499)
- [Agent Configuration SOP](./docs/sop/AGENT_CONFIGURATION_SOP.md) - Tool restrictions, model selection
- [ARCHitect-in-CLI Role](./docs/workflow/ARCHITECT_IN_CLI_ROLE.md) - Primary orchestrator definition

**CI/CD Documentation:**

- [CI/CD Pipeline Guide](./docs/ci-cd/CI-CD-Pipeline-Guide.md) - Pipeline implementation guide

**Database SOPs:**

- [RLS Migration SOP](./docs/database/RLS_DATABASE_MIGRATION_SOP.md) - MANDATORY for Data Engineer

**Project Standards:**

- [Harness Whitepaper](./docs/whitepapers/CLAUDE-CODE-HARNESS-MODERNIZATION-AITBC-444.md) - Complete harness architecture
- [Agent Perspective](./docs/whitepapers/CLAUDE-CODE-HARNESS-AGENT-PERSPECTIVE.md) - Why the harness works
- [SAFe Methodology](https://github.com/oib/AITBC) - This repository

## When to Use Which Agent

| Agent Role                           | Use Case                                                                                          | Success Criteria                                            | Primary Tools                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ----------------------------------- |
| **TDM** (Technical Delivery Manager) | Blocker triage seat (`Blocked` → classify env/external/scope, resume to origin, ABS-76); evidence tracking (NOT orchestration - see v1.3 SOP) | Blocker classified + resolved/escalated, ticket resumed     | Linear, Confluence                  |
| **BSA** (Business Systems Analyst)   | Requirements decomposition, acceptance criteria, testing strategy, follow-up ticket decisions     | Clear user stories, testable ACs, QA plan defined           | Linear, Confluence, Markdown        |
| **Issue Enrichment Agent**           | Owns ticket creation: dedup gate, agent-ready formatting, guardrail annotation, tracker operation | Verdict recorded, no duplicates, ticket created via adapter | Read, Grep, Bash, tracker adapter   |
| **PO-Agent** (Product Owner Agent)   | Story acceptance (post-QAS), epic-completion determination, WSJF prioritization, orchestration    | Accept/reject + reasoning recorded, epic DoD verified       | Read, Grep, Bash, tracker adapter   |
| **Self-Improvement Agent**           | Epic Retro seat (auto-spawned on `Epic Done`, ABS-69): runs `scripts/skill-mining.sh` FIRST (mandatory input, ABS-219), then retro; skill mining + boilerplate improvement proposals | Miner report read; per `SKILL-KANDIDAT` verdict a filed proposal or reasoned rejection; report | Read, Write, Grep, Glob, Bash       |
| **Boilerplate Migration**            | Migrating a consuming project to the current boilerplate version (runs FROM the current checkout) | Reviewable diff on migration branch, migration report filed | Read, Write, Edit, Bash, Grep, Glob |
| **System Architect**                 | Pattern validation, Stage 1 PR review, migration approval, arch decisions, guided ADR authoring   | ADR created/updated at correct level, PR review complete    | Read, Grep, ADR templates           |
| **UI/UX Design Agent**               | Schema-conformant design creation, design ACs, handoff to QAS-Design (never tests own designs)    | Design cites design system, testable design ACs on ticket   | Read, Write, Edit, Grep, Glob       |
| **FE Developer**                     | UI components, client-side logic, user interactions                                               | Lint and build passes                                       | Read, Write, Edit, Bash             |
| **BE Developer**                     | API routes, server logic, RLS enforcement                                                         | Integration tests pass                                      | Read, Write, Edit, Bash             |
| **DE** (Data Engineer)               | Schema changes, migrations, database architecture                                                 | Migration applied, RLS maintained                           | Prisma, SQL, migration tools        |
| **TW** (Technical Writer)            | Documentation, guides, technical content                                                          | Markdown lint passes                                        | Read, Write, Edit, Grep, Glob, Bash |
| **DPE** (Data Provisioning Engineer) | Test data, database access, data validation                                                       | Test data available, DB accessible                          | SQL, Prisma Studio, scripts         |
| **QAS** (Quality Assurance)          | **GATE OWNER**: Execute testing, validate ACs, iteration authority, evidence to Linear            | All ACs verified, evidence posted, Exit: "Approved for RTE" | Playwright, Jest, Linear MCP        |
| **QAS-Design** (Design QA)           | **DESIGN GATE**: Verify design ACs (DACs) independently, iteration loop back to UI/UX Design      | All DACs verified, evidence posted, Exit: "Design Approved" | Read, Bash, Grep, tracker adapter   |
| **SecEng** (Security Engineer)       | Security validation, RLS checks, vulnerability assessment (Independence Gate - not collapsible)   | Security audit passed, RLS enforced                         | RLS scripts, security tools         |
| **RTE** (Release Train Engineer)     | **PR SHEPHERD**: PR creation, CI/CD monitoring (NO code, NO merge) - Exit: "Ready for HITL"       | PR created, CI green, Exit: "Ready for HITL Review"         | Git, host PR CLI (`gh`: `bb`/`gh`), CI tools |

## Agent Handoff Map

Canonical inter-agent handoffs introduced with the team extension (ADR-A-0012):

```text
Follow-up work (ticket creation chain):
  Any reviewing agent (QAS, System Architect, SecEng, ...)
    └─ Follow-Up Recommendation ─→ BSA (decide: create / in-scope / discard)
         └─ Follow-Up Ticket Draft ─→ Issue Enrichment Agent
              ├─ 1. duplicate-detection skill (reject / append / create)
              ├─ 2. issue-enrichment skill (agent-ready format + guardrail notes)
              └─ 3. create/append via task-tracking adapter

Product ownership (PO-Agent):
  PO-Agent ─ ADR Authoring Request ─→ System Architect (guided ADR authoring)
  PO-Agent ─ Follow-Up Recommendation ─→ BSA (see chain above)
  PO-Agent ─ Self-Improvement Trigger ─→ Self-Improvement Agent
             (mandatory at epic completion, optional mid-epic)
  Human-only, never PO-Agent: new features, merge to main, additional costs

Design workflow:
  Requester ─→ UI/UX Design Agent (design + Design Acceptance Criteria)
    └─ "Ready for QAS-Design" ─→ QAS-Design Agent (independent DAC testing)
         └─ fail: findings ─→ back to UI/UX Design Agent (iteration loop)

Standalone:
  Boilerplate Migration Agent — human-invoked, runs from the current boilerplate
  against a target project; merge of the migration branch stays human-only.
```

## v3 Automated Seat Coverage (ABS-69)

Every agent role below has a **live automated seat** in the v3 orchestrator workflow — the coordinator spawns a fresh agent on the trigger status (ADR-A-0002), the agent does its seat duty and transitions the ticket via the adapter. No role is paper-only or orphaned. The spawn-facing seat section lives in each role's `harness/claude/agents/<role>.md`. Full status→role map: `docs/sop/ORCHESTRATOR_SOP.md`; charters per spec §2, §3.10.

| Role                        | v3 Seat                     | Trigger status → exit                                                                 |
| --------------------------- | --------------------------- | ------------------------------------------------------------------------------------- |
| **PO-Agent**                | PO Triage                   | `PO Triage` → Grooming / Backlog / Needs PO Decision                                   |
| **PO-Agent**                | Story Acceptance            | `Story Acceptance` → Merging (accept) / Ready for Development (reject)                 |
| **PO-Agent**                | Needs PO Decision (ABS-61)  | `Needs PO Decision` → Backlog / Ready for Development / Blocked; epic decomposition    |
| **BSA**                     | Grooming                    | `Grooming` → Enrichment (story drafts + flags)                                         |
| **BSA**                     | Follow-up Decision (ABS-75) | sweep on unanswered `kind: follow-up` → `kind: bsa-decision` reply; create/in-scope/discard |
| **Issue Enrichment Agent**  | Enrichment                  | `Enrichment` → Ticket Review (batch child creation)                                   |
| **QAS**                     | Ticket Review (DoR gate)    | `Ticket Review` → Architecture Review / Grooming (rework) / Needs PO Decision          |
| **System Architect**        | Architecture Review         | `Architecture Review` → Stories In Flight + releases each child to Design              |
| **UI/UX Design Agent**      | Design                      | `Design` (design flag) → Ready for Development (design + measurable design ACs)        |
| **Security Engineer**       | Security Review             | `Security Review` (security flag) → Test Prep / Ready for Development (blocking)       |
| **Data Provisioning Eng**   | Test Prep                   | `Test Prep` (data flag) → In Test (fixtures + RLS test contexts)                       |
| **QAS-Design**              | Design Test                 | `Design Test` (design flag) → Story Acceptance / Design (design-fix) / Ready for Development (impl-fix) |
| **Technical Writer**        | Docs                        | `Docs` → Done (story documentation)                                                   |
| **RTE**                     | Merging (ABS-89)            | `Merging` → Docs (merged) / Ready for Development (rebase|CI failure); no revert       |
| **RTE**                     | Epic Integration (ABS-90)   | `Epic Integration` → Ready for Epic Acceptance (NOTIFY) / bisect reopen / Needs PO Decision |
| **TDM**                     | Blocker Triage (ABS-76)     | `Blocked` (any stage) → resume to pre-blocked status / hold + human escalation         |
| **Self-Improvement Agent**  | Epic Retro                  | `Epic Done` (terminal) → `skill-mining.sh` first (ABS-219), then retro + skill mining, no exit transition |
| **Boilerplate Migration**   | (human-invoked, standalone) | not part of the automated loop — runs from the current checkout against a target       |

Conditional stages (`Design`, `Design Test`, `Security Review`, `Test Prep`) are SKIP-FORWARDed by the runner when the story lacks the matching flag — agents carry zero routing logic. `Ready for Epic Acceptance` and `Stories In Flight` are resting states (NOTIFY / JOIN); `Backlog` seeds the pipelines.

## Auto-Loaded Skills

Skills are loaded progressively—metadata at startup, full content when context triggers.

| Skill                    | Trigger                    | Purpose                                     |
| ------------------------ | -------------------------- | ------------------------------------------- |
| `safe-workflow`          | Commits, branches, PRs     | SAFe format, rebase-first workflow          |
| `pattern-discovery`      | Before writing code        | Pattern-first development (MANDATORY)       |
| `duplicate-detection`    | Before creating any ticket | Mandatory dedup gate: reject/append/create  |
| `issue-enrichment`       | After dedup verdict        | Agent-ready format + guardrail annotation   |
| `rls-patterns`           | Database operations        | RLS context helpers (withUserContext, etc.) |
| `frontend-patterns`      | UI work                    | Clerk, shadcn, Next.js patterns             |
| `api-patterns`           | API route creation         | Route structure, error handling             |
| `testing-patterns`       | Writing tests              | Jest, Playwright patterns                   |
| `orchestration-patterns` | Multi-step work            | Agent loop, evidence-based delivery         |
| `agent-coordination`     | Multi-agent work           | Assignment matrix, escalation patterns      |
| `team-coordination`      | Agent Teams spawn          | Multi-agent orchestration (experimental)    |
| `stop-slop`              | Before emitting deliverable| Anti-slop output-quality gate               |

**Note**: `/skills` command has display bug (v2.0.73, GitHub #14733). Skills work but won't show in list. Ask Claude directly: "What skills are available?"

## Success Validation Commands

### Frontend Development

```bash
npm run type-check && npm run lint && npm run build && echo "FE SUCCESS" || echo "FE FAILED"
```

### Backend Development

```bash
npm run test:integration && echo "BE SUCCESS" || echo "BE FAILED"
```

### Documentation

```bash
npm run lint:md && echo "DOCS SUCCESS" || echo "DOCS FAILED"
```

### Pre-Push Validation

```bash
npm run ci:validate && echo "CI SUCCESS" || echo "CI FAILED"
```

### Database Migration

```bash
npx prisma migrate dev --name migration_name && echo "MIGRATION SUCCESS" || echo "MIGRATION FAILED"
```

## SAFe Specs-Driven Workflow

### Planning Phase (BSA)

```bash
# Large initiative → Use planning template
cp specs_templates/planning_template.md specs/{feature}-planning.md
# Fill with Epic → Features → Stories → Enablers

# User story → Use spec template
cp specs_templates/spec_template.md specs/AITBC-XXX-{feature}-spec.md
# Fill with implementation details
```

### Execution Phase (All Agents)

```bash
# 1. Read spec for clear goal
cat specs/AITBC-XXX-{feature}-spec.md

# 2. Extract:
# - User story (goal)
# - Acceptance criteria (success)
# - Low-level tasks (steps)
# - Demo script (validation)

# 3. Implement using Simon's loop:
# - Clear goal from spec
# - Pattern discovery (codebase + specs)
# - Iterate until demo script passes
# - Escalate if blocked
```

## Pattern Discovery Protocol (MANDATORY)

### 0. Search Specs Directory (FIRST)

```bash
# Find similar implementations in specs
ls specs/*-spec.md | grep "similar_feature"

# Review SAFe user stories
grep -r "As a.*I want to" specs/

# Check patterns from past specs
cat specs/XXX-similar-spec.md
```

### 1. Search Codebase

```bash
# Search for similar functionality
grep -r "feature_name|functionality" app/

# Find existing helpers
ls lib/ && grep -r "helper_pattern" lib/

# Check components
grep -r "component_pattern" components/
```

### 2. Search Session History

```bash
# Search agent session todos
grep -r "similar_feature|pattern" ~/.claude/todos/ 2>/dev/null

# Find recent implementation patterns
ls -lt ~/.claude/todos/ | head -20
```

### 3. Consult Documentation

- `CONTRIBUTING.md` - Workflow and git process
- `docs/database/DATA_DICTIONARY.md` - Database schema (SINGLE SOURCE OF TRUTH)
- `docs/database/RLS_IMPLEMENTATION_GUIDE.md` - Row Level Security (MANDATORY for DB ops)
- `docs/security/SECURITY_FIRST_ARCHITECTURE.md` - Security patterns

### 4. Architectural Validation

- Propose pattern to System Architect
- Get approval before implementation
- Document decision in session notes

## Agent Workflow

### Standard Agent Loop (Per Simon Willison)

1. **Clear Goal** - BSA defines with acceptance criteria
2. **Pattern Discovery** - Search codebase and sessions
3. **Iterative Problem Solving**:
   - Implement approach
   - Run validation command
   - If fails → analyze error, adjust, repeat
   - If blocked → escalate to TDM with context
4. **Evidence Attachment** - Session ID + validation results in Linear

### No Over-Engineering

- ❌ No file locks
- ❌ No circuit breakers
- ❌ No arbitrary retry limits
- ✅ Let agents iterate until success or blocked
- ✅ Agent decides when to escalate

## Session Archaeology

### Monitor Concurrent Sessions

```bash
# See active sessions
ls -lt ~/.claude/todos/*.json | head -10

# Check for concurrent work on same files
grep -l "file_path" ~/.claude/todos/*.json
```

### Cross-Agent Coordination

```bash
# Find related work by another agent
grep -r "linear_ticket_number" ~/.claude/todos/

# Discover implementation patterns
grep -r "withUserContext|withAdminContext" ~/.claude/todos/
```

## Exit States (vNext Contract)

Each agent has explicit exit states that define handoff points:

```
┌─────────────────┬───────────────────────────────────────────┐
│ Role            │ Exit State                                │
├─────────────────┼───────────────────────────────────────────┤
│ BE-Developer    │ "Ready for QAS"                           │
│ FE-Developer    │ "Ready for QAS"                           │
│ Data-Engineer   │ "Ready for QAS"                           │
│ QAS             │ "Approved for RTE"                        │
│ RTE             │ "Ready for HITL Review"                   │
│ System Architect│ "Stage 1 Approved - Ready for ARCHitect"  │
│ HITL            │ MERGED                                    │
└─────────────────┴───────────────────────────────────────────┘
```

### Gate Quick Reference

```
┌─────────────────┬─────────────────┬─────────────────────────┐
│ Gate            │ Owner           │ Blocking?               │
├─────────────────┼─────────────────┼─────────────────────────┤
│ Stop-the-Line   │ Implementer     │ YES - no AC = no work   │
│ QAS Gate        │ QAS             │ YES - no approval = stop│
│ Stage 1 Review  │ System Architect│ YES - pattern check     │
│ Stage 2 Review  │ ARCHitect-CLI   │ YES - architecture check│
│ HITL Merge      │ oib            │ YES - final authority   │
└─────────────────┴─────────────────┴─────────────────────────┘
```

**Iteration cap is mechanically enforced (ABS-12)**: the QAS / QAS-Design gate loops are capped by prompt-level rules (ABS-11) **and** by a `PreToolUse` hook — `scripts/hooks/iteration-guard.sh`, wired in `.claude/hooks-config.json`. It counts a ticket's `Iteration N of M` bounce markers via the task-tracking adapter and blocks the bounce once the cap (default 3) is reached, forcing human escalation. It fails open if the tracker is unreachable. See the [Loop Termination Rules](./docs/sop/AGENT_WORKFLOW_SOP.md) and `specs/ABS-12-iteration-guard-spec.md`.

### Role Collapsing (AITBC-499)

- **RTE**: Collapsible (PR creation, CI shepherding can be done by implementer)
- **QAS**: NOT collapsible (independence gate - spawn subagent for verification)
- **SecEng**: NOT collapsible (security audit requires independence)

See [Agent Workflow SOP v1.4](./docs/sop/AGENT_WORKFLOW_SOP.md) for details.

### Agent Teams (Experimental)

Agent Teams enable real-time multi-agent orchestration using Claude Code's experimental Agent Teams feature. When enabled, agents are spawned as teammates with shared task lists and SAFe quality gates enforced via task dependencies.

- **Enable**: Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`
- **Skill**: `/team-coordination` — patterns for TeamCreate, SendMessage, shared TaskList
- **Guide**: See [Agent Teams Guide](docs/onboarding/AGENT-TEAMS-GUIDE.md) and [Optional Features](docs/guides/OPTIONAL-FEATURES.md)

---

## Quick Reference

### Key Documentation

- Branch/commit/PR conventions: invoke the `safe-workflow` skill (loads on demand). `CONTRIBUTING.md` is the reference, not a mandatory read.
- `docs/database/DATA_DICTIONARY.md` - Database schema (SINGLE SOURCE OF TRUTH)
- `docs/database/RLS_DATABASE_MIGRATION_SOP.md` - Schema changes (ARCHitect approval required)
- `docs/security/SECURITY_FIRST_ARCHITECTURE.md` - Security patterns

### Agent Files

- `.claude/agents/bsa.md` - Business Systems Analyst
- `.claude/agents/system-architect.md` - System Architect
- `.claude/agents/tdm.md` - Technical Delivery Manager
- `.claude/agents/fe-developer.md` - Frontend Developer
- `.claude/agents/be-developer.md` - Backend Developer
- `.claude/agents/data-engineer.md` - Data Engineer
- `.claude/agents/data-provisioning-eng.md` - Data Provisioning Engineer
- `.claude/agents/tech-writer.md` - Technical Writer
- `.claude/agents/qas.md` - Quality Assurance Specialist
- `.claude/agents/security-engineer.md` - Security Engineer
- `.claude/agents/rte.md` - Release Train Engineer
- `.claude/agents/po-agent.md` - PO-Agent (Product Owner)
- `.claude/agents/issue-enrichment.md` - Issue Enrichment Agent
- `.claude/agents/ui-ux-design.md` - UI/UX Design Agent
- `.claude/agents/qas-design.md` - QAS-Design Agent
- `.claude/agents/self-improvement.md` - Self-Improvement Agent
- `.claude/agents/boilerplate-migration.md` - Boilerplate Migration Agent

## Human-in-the-Loop (HITL) Model

**Product Owner / Product Manager**: oib

Day-to-day product ownership is delegated to the **PO-Agent** (`.claude/agents/po-agent.md`): story acceptance (post-QAS), epic-completion determination, and autonomous WSJF backlog prioritization (per the ADR-A-0004 amendment, ABS-9). The human POPM's role:

- **Feature initiation**: Creating new features is human-only — the PO-Agent manages and prioritizes existing scope, and escalates feature proposals
- **Merge approval**: Merges to main remain human (ADR-A-0005); accepted work reaches HITL via RTE-shepherded PRs
- **Cost approval**: Additional license/LLM costs remain human (ADR-A-0009); the PO-Agent escalates with a cost summary
- **Guardrail-setting**: Defines and adjusts the boundaries the PO-Agent operates within
- **Escalation target & oversight**: Receives PO-Agent escalations and retains oversight of all agent work
- All work requires evidence in Linear before acceptance review
- Swimlane workflow: Backlog → Ready → In Progress → Testing → Ready for Review → Done
- Final approval on deliverables sits with the PO-Agent — EXCEPT feature initiation, merges to main, and cost approval, which stay with the human POPM

---

## 🎯 Agent Invocation Examples

### Simple Invocation (Direct Mention)

Use `@agent-name` for simple, single-step tasks:

```bash
# Planning
@bsa Create a spec for user profile API endpoint
@system-architect Review the RLS policy for user_profiles table

# Implementation
@be-developer Implement the GET /api/user/profile endpoint
@fe-developer Create a UserProfile component with form validation
@data-engineer Add email_verified column to users table

# Quality & Documentation
@qas Write integration tests for user profile feature
@security-engineer Audit RLS policies for user_profiles table
@tech-writer Document the user profile API in README

# Coordination
@tdm Coordinate implementation of AITBC-123 user profile feature
@rte Create PR for AITBC-123 and run CI validation
```

### Task Tool Invocation (Complex Tasks)

Use `Task()` for complex, multi-step tasks with detailed instructions:

```typescript
// BSA: Create comprehensive spec
Task({
  subagent_type: "bsa",
  description: "Create spec for AITBC-123",
  prompt: `Create comprehensive spec for AITBC-123 user profile feature.

Requirements:
- User can view and edit their profile
- Profile includes: name, email, bio, avatar
- Email verification required
- Admin can view all profiles

Please:
1. Search for existing user/profile patterns in patterns_library/
2. Create user story with acceptance criteria
3. Define testing strategy (unit, integration, E2E)
4. Add #EXPORT_CRITICAL tags for security requirements
5. Reference relevant patterns from pattern library`,
});

// Backend Developer: Implement with pattern discovery
Task({
  subagent_type: "be-developer",
  description: "Implement AITBC-123 API",
  prompt: `Read spec at specs/AITBC-123-user-profile-spec.md

Implement the user profile API endpoints:
1. GET /api/user/profile - Get current user's profile
2. PUT /api/user/profile - Update current user's profile
3. GET /api/admin/users/:id/profile - Admin view any profile

Requirements:
- Use withUserContext for user endpoints
- Use withAdminContext for admin endpoints
- Follow RLS patterns from patterns_library/database/
- Validate input with Zod schemas
- Write unit tests for each endpoint

Pattern discovery is MANDATORY before implementation.`,
});

// QAS: Execute comprehensive testing
Task({
  subagent_type: "qas",
  description: "Test AITBC-123 feature",
  prompt: `Read spec at specs/AITBC-123-user-profile-spec.md

Execute the testing strategy defined by BSA:

1. Unit Tests:
   - Test Zod validation schemas
   - Test RLS context helpers
   - Test error handling

2. Integration Tests:
   - Test GET /api/user/profile with user context
   - Test PUT /api/user/profile with valid/invalid data
   - Test admin endpoints with admin context
   - Test RLS isolation (user A cannot see user B's data)

3. E2E Tests:
   - User can view their profile
   - User can edit their profile
   - Admin can view any profile
   - Unauthorized access is blocked

Validate all acceptance criteria from the spec.`,
});

// TDM: Reactive blocker resolution (NOT orchestration)
Task({
  subagent_type: "tdm",
  description: "Resolve blocker for AITBC-123",
  prompt: `A blocker has been reported for AITBC-123.

TDM Responsibilities (per v1.3 SOP):
1. Monitor progress - read session archaeology, Linear, PR comments
2. Identify blocker details - search for "FAILED|error|blocked"
3. Escalate to appropriate specialist to resolve
4. Track evidence - attach session IDs, test results to Linear
5. Update Linear ticket with resolution

NOTE: TDM is REACTIVE, not an orchestrator.
ARCHitect-in-CLI is the primary orchestrator.`,
});
```

### When to Use Which Invocation Method

| Scenario                  | Method         | Example                                             |
| ------------------------- | -------------- | --------------------------------------------------- |
| **Simple question**       | Direct mention | `@bsa What patterns exist for user authentication?` |
| **Single-step task**      | Direct mention | `@be-developer Add logging to the login endpoint`   |
| **Multi-step task**       | Task tool      | BSA creating spec with pattern discovery            |
| **Complex coordination**  | Task tool      | Multiple agents working on related features         |
| **Detailed requirements** | Task tool      | QAS executing comprehensive test strategy           |
| **Blocker resolution**    | Task tool      | TDM investigating and escalating blockers           |

### Pro Tips

1. **Always reference specs**: `Read spec at specs/AITBC-XXX-spec.md`
2. **Mandate pattern discovery**: `Pattern discovery is MANDATORY before implementation`
3. **Check #EXPORT_CRITICAL tags**: `Review #EXPORT_CRITICAL tags in spec first`
4. **Validate with commands**: Use success validation commands from agent prompts
5. **Update Linear**: TDM can update Linear with `mcp__linear-mcp__create_comment`
6. **TDM is reactive**: Don't use TDM for orchestration—use ARCHitect-in-CLI

---

**Quick Start**: invoke the `safe-workflow` skill for branch/commit/PR conventions (`CONTRIBUTING.md` is the reference, not a mandatory read), search codebase, propose to System Architect, validate with test command, attach evidence to Linear.

---
