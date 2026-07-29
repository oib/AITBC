# Agentic Development Boilerplate — Product Vision & Technical Blueprint

**Version:** 2.0.0-draft · **Status:** Blueprint (pre-implementation) · **Audience:** Engineering leadership, platform teams, implementing agents
**Format note:** Each numbered H2 below maps to one Confluence child page when imported.

> **Read this first.** This document is the **technology-neutral vision and architecture**. The
> **execution layer is [SAW](../README.md)** (SAFe Agentic Workflow), vendored as the base; this
> blueprint's abstract roles, adapters, and gates map onto SAW's concrete roles/skills/commands
> per the concept table in [`../INTEGRATION.md`](../INTEGRATION.md). Stack neutrality is realized
> through [`../profiles/`](../profiles/README.md): SAW's Linear/Confluence/Supabase stack is the
> `saw-stack` profile, and `neutral` is the default. Some section text below still describes the
> original clean-room `.agentic/…` layout as the **design record**; each such concept has a live
> home in the authoritative crosswalk, [`CROSSWALK.md`](CROSSWALK.md). Imperative "do this"
> instructions (bootstrap, quick-start) have been updated to live SAW paths.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [Target User Journey](#3-target-user-journey)
4. [Repository Structure](#4-repository-structure)
5. [Configuration Model](#5-configuration-model)
6. [Bootstrap Model](#6-bootstrap-model)
7. [Upgrade Model](#7-upgrade-model)
8. [Existing-Project Adoption Model](#8-existing-project-adoption-model)
9. [ADR Hierarchy](#9-adr-hierarchy)
10. [Agent Roles](#10-agent-roles)
11. [Orchestration Model](#11-orchestration-model)
12. [Fresh Subagent Execution Model](#12-fresh-subagent-execution-model)
13. [Context Minimization Strategy](#13-context-minimization-strategy)
14. [Ticket Lifecycle](#14-ticket-lifecycle)
15. [Review and Follow-Up Lifecycle](#15-review-and-follow-up-lifecycle)
16. [Quality Gates](#16-quality-gates)
17. [Design-System Integration](#17-design-system-integration)
18. [Task-Tracking Adapter Model](#18-task-tracking-adapter-model)
19. [MCP, Tool, and Skill Model](#19-mcp-tool-and-skill-model)
20. [Security and Cost-Control Model](#20-security-and-cost-control-model)
21. [PR and Human-Approval Model](#21-pr-and-human-approval-model)
22. [Notification and Resumability Model](#22-notification-and-resumability-model)
23. [Implementation Roadmap](#23-implementation-roadmap)

---

## 1. Executive Summary

The Agentic Development Boilerplate is a **technology-neutral foundation for the full multi-agent software development life cycle**. It is copied into a repository, bootstrapped once, and from then on the repository is operable by a fleet of AI agents under human governance.

The core promise:

> A human product owner writes an epic and hands it to the PO Agent. Days later, the human receives a testable, reviewable implementation — decomposed into tickets, implemented on branches, reviewed, tested, documented, and assembled into pull requests — ready for human acceptance and merge.

The human focuses on what only humans should decide: **planning, architectural approvals, cost approvals, epic acceptance, and merging to main**. Agents handle everything between: decomposition, ticket creation, implementation, review, testing, documentation, PR creation, and workflow coordination.

Three architectural convictions shape the entire design:

1. **Fresh subagents, durable artifacts.** Every task is executed by a disposable, task-scoped subagent with a clean context window. No hidden long-running agent memory is ever required to understand project state. All durable state lives in tickets, ADRs, PRs, and handoff records.
2. **Context is a budget, not a buffet.** Every workflow defines the smallest sufficient context. Agents never load broad repository context by default; excessive context loading is treated as a workflow quality defect.
3. **Humans own irreversibility.** Anything hard to undo — merges to main, accepted ADRs, production deployments, new costs, breaking changes — passes through an explicit human gate. Everything reversible is delegated to agents.

The boilerplate is technology-neutral: it works for web apps, mobile apps, SaaS products, agentic apps, APIs, and internal tools. All tool-specific behavior (Jira, GitLab, Figma, deployment) lives behind adapter interfaces; v1 ships interface definitions and mock/reference flows, not productive integrations.

---

## 2. Goals and Non-Goals

### Goals

| # | Goal |
|---|------|
| G1 | A human can go from *epic written* to *implementation ready for acceptance* with no manual coordination in between. |
| G2 | The boilerplate is technology-neutral: no assumed language, framework, cloud, or tracker. Technology is read from configuration, never assumed. |
| G3 | Every task runs in a fresh, task-scoped subagent fed a minimal context packet; work is always resumable by a new subagent. |
| G4 | Strict context minimization and token efficiency are enforced as first-class architectural requirements. |
| G5 | A three-level ADR hierarchy (company / agentic / project) governs decisions, with explicit human acceptance and a defined authority order. |
| G6 | The boilerplate is versioned, upgradeable across projects, and clearly separates boilerplate-owned from project-owned files. |
| G7 | Task tracking is **active**: status changes trigger agents. Jira Cloud and GitLab CE are prepared as v1 adapters behind a neutral interface. |
| G8 | A mandatory tooling layer declares the MCPs, tools, skills, and adapters required for agentic execution, validated at bootstrap. |
| G9 | Human approval boundaries (architecture, costs, merges, deployments, ADR acceptance, epic acceptance) are structurally enforced, not just documented. |
| G10 | Existing projects can adopt the boilerplate through an analysis-first migration performed by a dedicated Boilerplate Migration Agent. |

### Non-Goals (v1)

- **No productive Jira, GitLab, Figma, or deployment integrations.** v1 ships adapter interfaces, reference manifests, and a mock adapter that enables full local dry-runs.
- **No custom orchestrator runtime.** The boilerplate defines the orchestration contract; it runs on existing subagent-capable runtimes (Claude Code, Agent SDK, Cursor, Codex, or equivalents).
- **No autonomous merges or deployments.** Ever. This is a permanent non-goal, not a v1 gap.
- **No replacement of human product judgment.** The PO Agent assesses whether an epic's requests are implemented; the human performs final acceptance.
- **No company ADR content.** The structure supports company ADRs, but v1 does not ship or copy any by default.
- **No multi-repository orchestration.** v1 targets a single repository per project.

---

## 3. Target User Journey

The canonical journey, end to end:

1. **Adopt.** The human creates a repository from the template and runs `scripts/setup-template.sh` (SAW's bootstrap). It fills project identity, records the choices in `.harness-manifest.yml`, has the team select a stack [profile](../profiles/README.md) (`saw-stack` or `neutral`), and the human accepts the agentic ADR baseline. The repository is now agent-operable.
2. **Describe.** The human writes an epic/spec using `specs_templates/spec_template.md` — intent, outcomes, constraints, explicit exclusions — and creates it in the task tracker (Linear in the `saw-stack` profile; any tracker via the [task-tracking capability](../profiles/neutral/adapters/task-tracking.md)).
3. **Hand off.** The human assigns the epic to the PO Agent (a status change or label; the tracker adapter turns it into a trigger).
4. **Decompose.** The PO Agent comments its understanding on the epic, asks clarifying questions if needed, and spawns a Ticket Creation Agent. Tickets are created with goal, scope, acceptance criteria, definition of done, test plan, and embedded ADR/design-system excerpts. If any planning option introduces license or LLM API costs, the workflow pauses at a **cost approval gate**.
5. **Approve plan.** The human skims the ticket breakdown on the epic. Architecture-relevant tickets carry proposed ADRs awaiting human acceptance.
6. **Execute.** The Coordinator moves tickets through the lifecycle, spawning a fresh subagent per ticket, per review, per test task, per documentation task. Quality gates run; results are written to tickets and PRs. Blockers the agents cannot resolve are escalated to the human via the tracker.
7. **Accept.** When all epic tickets reach *Ready for Human Acceptance* and the PO Agent judges the epic's requests implemented, it notifies the human in the task tracker with a summary: what was built, test evidence, gate results, open exceptions, and the PRs awaiting merge.
8. **Merge.** The human reviews the PRs (each carries ticket summaries, scope, test evidence, gate results, exceptions, ADR references) and merges to main. Agents never merge.

Secondary journeys: **upgrade** (pull a new boilerplate version, Migration Agent applies it), **existing-project adoption** (analysis → migration plan → human approval → staged application), and **feature-request back to the boilerplate** (project files a structured request upstream).

---

## 4. Repository Structure

The live repository combines the **SAW harness** (execution) with a **neutral overlay** (governance). The clean-room `.agentic/` tree from early drafts was retired; resolve every legacy `.agentic/…` path through [`CROSSWALK.md`](CROSSWALK.md).

| Concern | Live home |
|---------|-----------|
| Harness, hooks, skills, agents | `harness/claude/` (shipped-harness source; `.claude/` is a live, byte-identical copy read at runtime), `.agents/`, `agent_providers/` |
| Pattern library | [`patterns_library/`](../patterns_library/) |
| Stack / capabilities | [`profiles/`](../profiles/README.md) |
| ADRs | [`adrs/`](../adrs/) |
| Bootstrap | [`scripts/setup-template.sh`](../scripts/setup-template.sh) |
| Upgrades / drift | [`.harness-manifest.yml`](../.harness-manifest.yml), [`scripts/sync-claude-harness.sh`](../scripts/sync-claude-harness.sh) |

**Ownership:** harness files stay upgrade-clean via the manifest `protected` / `replaced` lists; project-owned files (accepted ADRs, application code) are never overwritten by sync. Upstream feature requests: [`.github/ISSUE_TEMPLATE/feature_request.md`](../.github/ISSUE_TEMPLATE/feature_request.md).

---

## 5. Configuration Model

> **Live home:** [`profiles/<name>/profile.yaml`](../profiles/README.md) binds capabilities to providers; [`.harness-manifest.yml`](../.harness-manifest.yml) holds identity substitutions. See CROSSWALK § “Bootstrap, configuration & upgrade”.

Design intent (unchanged): no secrets in config (names only); stack read from profile, never assumed; human approval boundaries are stack-independent invariants.

---

## 6. Bootstrap Model

> **Live:** [`scripts/setup-template.sh`](../scripts/setup-template.sh) ([`TEMPLATE_SETUP.md`](../TEMPLATE_SETUP.md)). Existing-project adoption: [`docs/guides/WORKSPACE-ADOPTION-GUIDE.md`](../docs/guides/WORKSPACE-ADOPTION-GUIDE.md). Upgrades: [`scripts/sync-claude-harness.sh`](../scripts/sync-claude-harness.sh).

Three modes (`new-project`, `existing-project`, `upgrade`) share one SAW entry point. Bootstrap substitutes placeholders, validates tooling readiness, and emits a gap report. It is idempotent.

---

## 7. Upgrade Model

> **Live:** [`scripts/sync-claude-harness.sh`](../scripts/sync-claude-harness.sh) + [`.harness-manifest.yml`](../.harness-manifest.yml) (`protected`, `replaced`, `renames`). See [`docs/HARNESS_SYNC_GUIDE.md`](../docs/HARNESS_SYNC_GUIDE.md).

Drift detection compares installed harness files to the manifest; project-owned files are untouched; ADR changes require human acceptance. Upgrades land as PRs — humans merge. Rollback = revert the upgrade PR.

---

## 8. Existing-Project Adoption Model

> **Live:** [`docs/guides/WORKSPACE-ADOPTION-GUIDE.md`](../docs/guides/WORKSPACE-ADOPTION-GUIDE.md).

Analysis-first workflow: read-only inventory → migration plan → human approval gate → staged PRs. Mandatory tooling validation runs before agents take real tickets.

---

## 9. ADR Hierarchy

Three levels, one authority order, one template.

| Level | Location | Scope | Examples | Copied to projects? |
|-------|----------|-------|----------|---------------------|
| **Company** | `adrs/company/` | Organization-wide | GDPR handling, company design system, engineering constraints | Not by default (v1); referenced or added manually |
| **Agentic** | `adrs/agentic/` | Boilerplate/agentic-SDLC decisions, apply across projects | Fresh-subagent execution, human merge boundary, context minimization | Yes — copied at bootstrap, updated via upgrades |
| **Project** | `adrs/project/` | This project's architecture | Storage choice, API style, module boundaries | Local only |

**Authority order (conflict resolution):**

> Accepted project ADR > Accepted company ADR > Accepted agentic ADR > governance defaults

A project ADR may override a broader ADR **only when explicitly accepted by a human**, and it must name the ADR it overrides.

**Rules:**
- Agents create ADRs only in `proposed` status. The ADR/Governance Checker tool structurally prevents agents from setting `accepted`.
- Humans approve every accepted ADR.
- Minimal required fields only: `status`, `scope`, `context`, `decision`, `consequences`, plus `supersedes` when needed (see [`adrs/`](../adrs/) templates and [`specs_templates/`](../specs_templates/)).
- The Ticket Creation Agent embeds **relevant ADR excerpts directly in tickets** whenever it improves execution quality — coding agents should rarely need to open ADR files themselves.

The boilerplate ships a seed set of agentic ADRs (see `adrs/agentic/`) covering: the ADR hierarchy itself, fresh-subagent execution, context minimization, human approval boundaries, the mandatory PR model, active task tracking, the adapter model, boilerplate ownership/upgrades, cost gates, minimal-change discipline,
and the three-layer application-architecture default.

---

## 10. Agent Roles

Fifteen blueprint roles map onto SAW's eleven agents — see [`ROLE-ROSTER.md`](ROLE-ROSTER.md). Prompt source lives under [`harness/claude/agents/`](../harness/claude/agents/) (plus mirrored provider copies); the live `.claude/agents/` is a byte-identical runtime copy.

| Role | Mission (one line) |
|------|--------------------|
| **PO Agent** | Product-side steward of epics: intake, clarification, prioritization, progress monitoring, epic-done assessment, human notification. |
| **Coordinator Agent** | Execution mechanics: spawns fresh subagents per task, builds context packets, drives the status machine, enforces gates, retries/reassigns. |
| **Ticket Creation Agent** | Decomposes epics into executable tickets meeting the ticket quality rules; embeds ADR/design-system excerpts; flags cost-incurring options. |
| **Review Agent** | Reviews diffs/PRs for correctness, scope discipline, ADR compliance; produces structured findings. |
| **Task Extraction Agent** | Converts review findings and ticket comments into well-formed candidate follow-up tasks. |
| **Duplicate Detection Agent** | Checks candidate tasks against all **not-done** tickets; merges or drops duplicates. |
| **Architect Agent** | Proposes ADRs, assesses breaking changes and architectural impact; never accepts ADRs. |
| **Frontend Agent** | Implements UI tickets; consumes the design-system adapter and Figma MCP when configured; subject to visual QA. |
| **Backend Agent** | Implements service/API tickets against explicit contracts. |
| **Data Agent** | Schemas, migrations, data pipelines; reversibility and migration safety first. |
| **QA/Test Agent** | Executes ticket test plans, writes/extends tests, produces test evidence; Playwright-based checks for UI projects. |
| **Security Agent** | Security reviews on triggers (auth, secrets, dependencies, security-labeled tickets); secret-scanning oversight. |
| **Documentation Agent** | Updates docs, changelogs, and READMEs affected by merged scope. |
| **Release Agent** | Assembles PRs, writes PR descriptions per template, prepares (never executes) deployments and release notes. |
| **Boilerplate Migration Agent** | Existing-project analysis, migration plans, boilerplate upgrades, drift detection. |

The **PO/Coordinator split** is deliberate: the PO Agent makes product-priority decisions and talks to the human; the Coordinator makes mechanical spawning/sequencing decisions. This keeps the PO prompt small and stable while orchestration logic evolves independently. The PO may stop or reassign poorly performing agents via the Coordinator.

Agents may use additional skills or MCPs beyond their manifests only when the PO Agent approves it or delegates to a better-suited role — recorded as a ticket comment.

---

## 11. Orchestration Model

Orchestration is **event-driven off the task tracker** and **stateless between tasks**:

- **Triggers.** Ticket status changes are the primary events (Section 14 maps status → triggered workflow). The tracker adapter surfaces events via webhook (Jira/GitLab) or polling (mock). Manual triggers (human comment commands) and scheduled sweeps (stale-ticket detection) are secondary.
- **Workflows.** Declarative steps, gates, and failure routes — live in [`docs/sop/AGENT_WORKFLOW_SOP.md`](../docs/sop/AGENT_WORKFLOW_SOP.md) (SAFe Exit States). Workflows reference roles, never runtimes.
- **The Coordinator** is the only component that spawns subagents. For each step it: assembles the context packet (Section 12), spawns a fresh subagent with the role's prompt + packet, waits for the structured result, verifies the handoff record was written, runs/collects gates, and advances the status machine.
- **Failure handling.** Retry once with the failure appended to the packet; then reassign to a better-suited role or escalate to the PO Agent; the PO escalates to the human if unresolvable. Every hop is a ticket comment.
- **Parallelism.** Tickets without declared dependencies run in parallel up to `orchestrator.max_parallel_subagents`. Dependencies are declared on tickets at creation time.
- **Runtime neutrality.** The orchestration contract ([`docs/workflow/ARCHITECT_IN_CLI_ROLE.md`](../docs/workflow/ARCHITECT_IN_CLI_ROLE.md)) assumes only: the runtime can spawn a fresh-context subagent with a given prompt and packet, and return its structured output. Claude Code subagents, Agent SDK, Cursor, Codex, or Antigravity all satisfy this.

---

## 12. Fresh Subagent Execution Model

**Every task is executed by a fresh, task-scoped subagent.** No exceptions. A new subagent is spawned for each: ticket, subtask, code review, test task, documentation task, migration task, follow-up extraction task, duplicate-detection task, and quality-gate investigation.

Subagents are disposable execution units: clean context window in, structured artifacts out.

### The context packet

Context is assembled from the ticket/spec, not a formal packet schema — see CROSSWALK § “Roles, orchestration & handoff”. Typical contents:

- ticket/subtask ID and links
- goal, scope (in/out), acceptance criteria, definition of done, test plan
- relevant ADR excerpts (pre-summarized)
- relevant design-system guidance, if any
- assigned agent role + pointer to role prompt
- allowed/default skills and MCPs for this task
- affected files or capabilities, if known
- required quality gates
- handoff requirements (what must be written back, where)
- prior handoff records, when resuming or retrying

### The handoff record

Before terminating, every subagent writes back — to the ticket, PR, or agent output artifact ([`AGENT_OUTPUT_GUIDE.md`](../harness/claude/AGENT_OUTPUT_GUIDE.md), shipped-harness source; the live runtime copy is `.claude/AGENT_OUTPUT_GUIDE.md`):

- result summary and decisions made (with rationale)
- blockers encountered
- changed files
- test evidence
- gate results
- context loaded beyond the packet, and why (Section 13)
- next-step recommendations

**Invariant:** a brand-new subagent given only the ticket + latest handoff record can resume the work. If it can't, the previous handoff was defective — a workflow quality bug, tracked like any other defect. No long-running hidden agent context is ever required to understand project state; durable state lives in tickets, ADRs, PRs, handoff records, and audit-relevant repository files.

---

## 13. Context Minimization Strategy

Context efficiency is a core architectural requirement, not an optimization. The mandatory strategy:

1. **Start from the ticket or epic, never from the repository.** The packet is the primary context; the repo is a lookup target.
2. **Load only:** the role definition, the applicable workflow step, ADR excerpts in the packet, the files/contracts named in the packet, and the required gate definitions.
3. **Stop loading** the moment the agent can identify: the task goal, the owning capability, applicable ADRs/governance rules, files or contracts likely affected, and required quality gates.
4. **Graph before grep.** When the [knowledge capability](../profiles/neutral/adapters/knowledge.md) is configured — the in-repo OKF bundle ([`knowledge/`](../knowledge/README.md)) or a context-graph MCP (Graphify / codebase-memory) — agents must query its index before any broad grep or full-file exploration, following the mandatory context sequence (index → concept → linked concepts → named source files). Broad exploration without a prior knowledge query is a gate-relevant workflow violation.
5. **Excerpts over rediscovery.** The Ticket Creation Agent front-loads summarized ADR and design-system excerpts into tickets so coding agents don't re-derive context. Cost is paid once at ticket creation, not N times at execution.
6. **Declare overruns.** Any context loaded beyond the packet must be documented in the handoff record with a reason. Repeated overruns on similar tickets indicate defective ticket creation and generate a follow-up task against the workflow itself.
7. **Budgets.** `config.context` sets soft budgets per task class; the Coordinator includes them in packets. Exceeding budget doesn't halt work — it gets flagged and reviewed.

Treating excessive context loading as a quality problem closes the loop: token waste becomes visible, attributable, and fixable at its source (usually under-specified tickets).

---

## 14. Ticket Lifecycle

### Statuses (v1, required)

```
Backlog → Ready for Development → In Progress → In Review → In Test
        → Ready for Human Acceptance → Ready for Merge → Done
                          (any) ↔ Blocked
```

| Status | Entered when | Triggers |
|--------|--------------|----------|
| Backlog | Ticket created | PO prioritization sweep |
| Ready for Development | Prioritized + dependencies clear + ticket-quality gate passed | Coordinator spawns implementation subagent |
| In Progress | Subagent starts | Progress monitoring |
| In Review | Implementation handoff complete, PR/diff exists | Coordinator spawns Review Agent |
| In Test | Review passed (or findings triaged) | Coordinator spawns QA/Test Agent |
| Ready for Human Acceptance | Tests pass, gates green or exceptions documented | PO epic-completion check; human notification when epic-complete |
| Ready for Merge | Human accepted ticket scope | Human merges (Release Agent has PR ready) |
| Done | PR merged | Documentation sweep, epic progress update |
| Blocked | Any agent hits an unresolvable obstacle | PO Agent triage → human escalation if needed |

Statuses are **active**: each transition is an event that triggers the mapped workflow ([`docs/sop/AGENT_WORKFLOW_SOP.md`](../docs/sop/AGENT_WORKFLOW_SOP.md); the tracker adapter maps canonical statuses onto provider-specific boards).

### Ticket content (required fields)

Every ticket carries: **Goal, Scope (in/out), Acceptance Criteria, Definition of Done, Test Plan**, and **relevant ADR context** when useful. Template: [`specs_templates/spec_template.md`](../specs_templates/spec_template.md).

### Ticket quality rules (enforced as a gate)

The Ticket Creation Agent must verify each ticket: is executable by an agent; has clear acceptance criteria; has a definition of done; has a test plan; has enough context to avoid unnecessary repository exploration; includes relevant ADR/design-system/governance excerpts when useful; and introduces **no unapproved architecture changes, breaking changes, or costs** (violations route to the Architect Agent or the cost gate instead of the backlog).

---

## 15. Review and Follow-Up Lifecycle

Review findings never die in comments. The mandatory follow-up chain:

```
Review Agent → Task Extraction Agent → Duplicate Detection Agent → Ticket Creation Agent → PO Agent
```

1. **Review Agent** reviews the diff/PR, writes structured findings (blocking vs. non-blocking) to the PR and ticket. Blocking findings send the ticket back to *In Progress* (new subagent, packet includes the findings).
2. **Task Extraction Agent** (fresh subagent) converts non-blocking findings into candidate follow-up tasks with enough context to stand alone.
3. **Duplicate Detection Agent** checks each candidate against all **not-done** tickets only (Done tickets are history, not duplicates). Merges into existing tickets or drops with a logged rationale.
4. **Ticket Creation Agent** turns surviving candidates into full-quality tickets (same quality gate as epic decomposition).
5. **PO Agent** prioritizes and inserts them into the backlog, linking back to the originating review.

Each step is a separate fresh subagent with a narrow packet. The chain also runs for findings from quality-gate investigations and security reviews.

---

## 16. Quality Gates

Defined in [`docs/sop/PRE_PR_VALIDATION_CHECKLIST.md`](../docs/sop/PRE_PR_VALIDATION_CHECKLIST.md) and [`.github/workflows/`](../.github/workflows/), executed by QAS and CI, results posted to tickets and PR descriptions.

| Gate | Applies to | Conditional? |
|------|-----------|--------------|
| `format` | Every change | No |
| `lint` | Every change | No |
| `tests` | Every change | No |
| `build` | Every change | No |
| `security-scan` | Every change (secrets, dependencies, SAST hook point) | No |
| `adr-check` | Every ticket/PR (does this trigger ADR/approval/cost/breaking-change rules?) | No |
| `ticket-quality` | Every ticket before *Ready for Development* | No |
| `design-system-check` | UI changes | When design system configured |
| `visual-qa` (Playwright) | UI changes | UI projects — then mandatory |
| `cost-approval` | Planning/ticket creation | When a cost-incurring option is selected |

Gate *commands* are project-specific (configured at bootstrap: e.g., `format.command: <project formatter>`); gate *semantics* are boilerplate-owned.

**Exception policy:** Agents may create PRs with failing gates only if the failure and its reason are documented in the PR description and ticket. *Ready for Merge* may be reached with exceptions only if each exception is justified, documented, and visible to the human at merge time. Exceptions are never silent and never granted by the agent that caused the failure.

---

## 17. Design-System Integration

- **The stack works without a design system.** `design_system.enabled: false` is a fully supported configuration; frontend work proceeds on generic accessibility and consistency rules.
- **Bootstrap asks.** The questionnaire covers: design system? source (Figma / token files / docs)? company design-system ADR to reference?
- **If configured, it is mandatory for frontend agents.** The Design System Adapter exposes tokens, component rules, and UX constraints; the `design-system-check` gate verifies conformance; ticket packets carry relevant design excerpts.
- **Figma MCP** is prepared as an optional, conditional integration: mandatory for frontend agents only when Figma is declared in config as the design source.
- **Playwright visual QA is required for UI projects** regardless of design-system presence.
- Design systems may additionally be governed via company ADRs and an optional design-system profile file referenced from config.

---

## 18. Task-Tracking Adapter Model

The boilerplate is task-tracking-tool agnostic; agents speak only the neutral interface defined in [`profiles/neutral/adapters/task-tracking.md`](../profiles/neutral/adapters/task-tracking.md):

- **Operations:** `get_ticket`, `search_tickets`, `create_ticket`, `update_ticket`, `comment`, `transition`, `link`, `get_epic_children`, `subscribe_events`.
- **Canonical model:** the nine v1 statuses, the required ticket fields, epics-with-children. Each adapter maps canonical statuses to provider states (mapping declared in the adapter manifest + config).
- **Active tracking:** adapters surface status-change events (webhooks for Jira Cloud and GitLab CE; polling for mock) that the Coordinator consumes as workflow triggers.

**v1 adapters (`mock` is live; `jira-cloud`/`gitlab-ce` remain interface mappings, prepared but not productive):**

| Adapter | Form in v1 |
|---------|-----------|
| `jira-cloud` | Interface mapping manifest: canonical ops → Jira REST/webhook concepts, status mapping template |
| `gitlab-ce` | Interface mapping manifest: canonical ops → GitLab issues/labels/boards, webhook mapping |
| `mock` | **Implemented — fully functional reference:** tickets as markdown+frontmatter files in [`work/tickets/`](../work/README.md), all nine operations via [`scripts/mock-tracker.sh`](../scripts/mock-tracker.sh), transitions = frontmatter edits validated against [`profiles/neutral/adapters/statuses.yaml`](../profiles/neutral/adapters/statuses.yaml), events = polling. Conformance test: [`tests/test-mock-tracker.sh`](../tests/test-mock-tracker.sh). Enables complete local dry-runs of every workflow. |

Additional providers plug in through the same interface. The mock adapter doubles as the conformance reference: a new adapter is correct when the full epic dry-run behaves identically.

---

## 19. MCP, Tool, and Skill Model

A **mandatory tooling layer** declares what the multi-agent SDLC requires. Registries: [`harness/claude/skills/`](../harness/claude/skills/) (shipped-harness source; live copy at `.claude/skills/`), [`.cursor/mcp.json`](../.cursor/mcp.json), per-role tool grants in agent manifests — see CROSSWALK § “Skills, governance & ADRs”.

### Mandatory for every project

1. **Task Tracking Adapter** — read/create/update/comment/transition tickets (Section 18).
2. **Git Repository Adapter** — branches, diffs, commits, PR/MR creation. Structurally **cannot merge to main**.
3. **Orchestrator / Subagent Runtime** — fresh task-scoped subagents + context packets + persisted handoff state (Sections 11–12).
4. **Knowledge Base / Context Graph** — the [knowledge capability](../profiles/neutral/adapters/knowledge.md): an [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) bundle in-repo (`knowledge/`) by default, Graphify / codebase-memory MCPs as alternative providers; queried before broad exploration whenever available (Section 13).
5. **Ponytail / Minimal-Change Skill** — default for all coding and review agents: minimal, scoped, reversible changes; no unnecessary abstractions, rewrites, or broad refactors.
6. **Quality Gate Runner** — executes configured gates, publishes results to tickets and PRs.
7. **ADR / Governance Checker** — detects ADR/approval/cost/security/breaking-change triggers; **prevents agents from marking ADRs accepted**.
8. **Notification Adapter** — human notification through the task tracker (epic ready, blocker needs input).

### Conditionally mandatory

1. **Playwright MCP** — mandatory for UI projects (browser testing, visual QA, design-system validation).
2. **Figma MCP** — mandatory only when Figma is the declared design source.
3. **Design System Adapter** — mandatory when a design system is configured.
4. **Secrets / Credential Access Adapter** — mandatory when agents need protected systems; mediated access preferred (tool performs the action; agent never sees the credential) and raw secret exposure requires explicit human approval.
5. **Cost Approval Gate** — mandatory whenever a task may introduce license or LLM API costs.

### Bootstrap validation

Bootstrap validates this layer: each mandatory capability must resolve to a configured provider, be explicitly mocked, or the project is marked **not ready for agentic execution** — with the gap list in the readiness report.

**v1 reference tools/MCPs modeled explicitly:** Graphify, codebase-memory, Ponytail, Playwright MCP, Figma MCP (conditional), Jira Cloud adapter, GitLab CE adapter, Git/PR adapter, task-tracking notification adapter, quality gate runner, ADR/governance checker, secrets access adapter.

---

## 20. Security and Cost-Control Model

### Security

- **No secrets in the repository, ever.** The `security-scan` gate enforces it; configuration carries secret *references*, injected per environment.
- **Agents don't see raw secrets** unless a human explicitly approves it for a specific task. The Secrets Adapter prefers **mediated access**: the tool performs the privileged action; the agent gets the outcome, not the credential.
- **Secret access is modeled** in profile config and governance ([`governance/security.md`](governance/security.md), [`../SECURITY.md`](../SECURITY.md)) — who may request access, what requires approval, what is logged.
- **Security triggers:** changes touching auth, secrets handling, dependency manifests, or security-labeled tickets automatically involve the Security Agent or a security-review workflow step, via the ADR/Governance Checker.

### Cost control

- **License costs and LLM API costs are "additional costs."** Any planning or ticket-creation path that selects a cost-incurring option must pause at the **cost approval gate** — a human approves in the tracker before the option is chosen.
- Cost approval is a first-class workflow gate (not a convention), with the decision recorded on the ticket.
- Config may carry pre-approved licenses and budget hints so the gate only fires on genuinely new costs.

---

## 21. PR and Human-Approval Model

**PRs are mandatory.** All agent work reaches main only through a PR. A PR may bundle multiple tickets; an epic may produce multiple PRs. The Release Agent assembles PRs; the Git Adapter structurally cannot merge protected branches.

**Every PR description contains** (template-enforced): ticket summary, implemented scope, test evidence, quality gate results, gate exceptions with justification, ADR references, and outstanding human approval requirements.

**Humans must approve:**

| Decision | Gate mechanism |
|----------|---------------|
| Architecture changes | ADR acceptance (project/company level) |
| Breaking changes | ADR-check gate → Architect review → human sign-off on ticket |
| Merges to main | Git provider protection + adapter cannot merge |
| Additional license costs | Cost approval gate |
| Additional LLM API costs | Cost approval gate |
| Production deployments | Release Agent prepares only; human executes |
| Accepted ADRs | Only humans set `status: accepted` (checker-enforced) |
| Final epic acceptance | PO Agent recommends; human accepts |

Agents may create PRs and prepare production deployments — never merge, never deploy.

---

## 22. Notification and Resumability Model

### Notification

- All human-facing notification flows through the **task-tracking system** (v1): the human's existing inbox, no new channels.
- The PO Agent notifies the human when: an epic is **ready for acceptance** (with summary, evidence, exceptions, PR links) and when a **blocker cannot be resolved autonomously** (with what was tried and what decision is needed).
- The final epic notification happens on the epic itself.

### Resumability

- Decisions are documented in tickets; every subagent writes a handoff record before terminating (Section 12).
- Ticket comments, PR descriptions, and handoff records together contain the full state needed to resume interrupted work with a brand-new subagent.
- The Coordinator's resume flow: read ticket → read latest handoff record → build packet with `resume: true` and prior state → spawn fresh subagent. Nothing depends on any prior agent still existing.
- A scheduled staleness sweep flags tickets that sit in an active status without progress, routing them to PO triage.

---

## 23. Implementation Roadmap

The detailed, phase-by-phase plan with model-level recommendations lives in [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md). Summary:

| Phase | Scope | Recommended level |
|-------|-------|-------------------|
| 0 | Repo scaffold, schemas, templates, file stubs | Haiku (mechanical generation) |
| 1 | Governance core: ADR model, approval boundaries, ownership/upgrade design | Opus |
| 2 | Orchestration contract, context packets, handoff model, status machine | Opus |
| 3 | Agent roles: role docs, prompts, manifests | Sonnet (Haiku for stubs) |
| 4 | Workflow definitions + ticket lifecycle wiring | Sonnet |
| 5 | Adapter interfaces + mock tracker + reference manifests (Jira/GitLab/Figma/Git/secrets) | Sonnet |
| 6 | Bootstrap, upgrade, migration flows + questionnaire + validation | Opus design / Sonnet implementation |
| 7 | Quality gates, tooling registries, cost + security gates | Sonnet |
| 8 | Repo-wide consistency pass, schema validation, cross-reference checks | Cursor Composer 2.5 / Codex |
| 9 | End-to-end dry-run: epic → tickets → mock implementation → PR, with mock adapter | Opus supervising Sonnet |
| 10 | Pilot on a real project; feed findings back as boilerplate feature requests | Human + PO Agent |

Definition of done for v1: a human can bootstrap a fresh repo, write an epic in `work/tickets/`, and drive the full lifecycle to a mergeable PR using only mock adapters — with every gate, handoff, and approval boundary exercised.
