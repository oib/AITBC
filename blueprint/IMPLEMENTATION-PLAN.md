# Implementation Plan

> **Superseding context (SAW rebase).** The boilerplate is now built on the
> [SAW](../README.md) harness as its execution base, with this blueprint as the
> technology-neutral overlay (see [`../INTEGRATION.md`](../INTEGRATION.md)). SAW already provides
> a working harness (roles, skills, commands, hooks, sync/upgrade via `.harness-manifest.yml`,
> bootstrap via `setup-template.sh`), so **Phases 0–7 below are largely satisfied by SAW** and
> should be read as the *conceptual spec* the SAW base is checked against — not as
> green-field build work. The remaining, still-open work is consolidated here as **Phase S**.

## Phase S — SAW integration & genericization (open follow-on)

**Level:** Sonnet (mechanical mapping) with Opus review for the capability abstractions.

1. **Path-reference cleanup.** `blueprint/**` and `adrs/**` still cite the retired `.agentic/…`
   layout. Rewrite each reference to its SAW anchor (or a `profiles/` capability) using the
   concept-mapping table in `INTEGRATION.md`.
2. **Complete the neutral profile bindings.** For each capability in
   [`../profiles/neutral/profile.yaml`](../profiles/neutral/profile.yaml), fill `implemented_by`
   with the SAW skills/commands/agents (mirror `saw-stack` where equivalent).
3. **Second reference profile.** Add a non-SAW profile (e.g. `jira-github-postgres`) to prove
   the profile abstraction genericizes SAW's Linear/Confluence/Supabase opinions without editing
   harness files — the true test of "technology-neutral core."
4. **Reconcile role vocabulary.** Produce one canonical roster mapping the blueprint's 15 roles
   to SAW's 17 SAFe roles (partly done in `INTEGRATION.md`); decide which blueprint-only roles
   (e.g. Duplicate Detection, Task Extraction) become SAW skills/commands vs. new agents.
5. **ADR hierarchy wiring.** Connect the three-level `adrs/` hierarchy to SAW's ADR templates and
   `System Architect` flow so proposed→accepted transitions run through SAW's gates.

**Audience:** implementing agents (Haiku, Sonnet, Opus, Cursor Composer 2.5, Codex) and the humans supervising them.
**Prerequisite reading per task:** only the Blueprint sections named in the phase — do not load the whole repository. Practice the context discipline this boilerplate preaches while building it.

Each phase lists: deliverables, acceptance criteria, recommended model level, and dependencies. Phases 0–2 are strictly ordered; 3–7 can partially parallelize; 8–10 are strictly ordered at the end.

**Model-level guidance (general):**
- **Haiku** — mechanical file generation, schema drafts from a spec, repetitive documentation stubs, template instantiation.
- **Sonnet** — workflow definitions, adapter interfaces, manifests, role documentation, scripts with clear specs.
- **Opus** — architecture, orchestration model, ADR model, governance design, conflict resolution, anything where two Blueprint sections must be reconciled.
- **Cursor Composer 2.5 / Codex** — repository-wide edits, validation, consistency checks, implementation follow-through across many files.

---

## Phase 0 — Scaffold & Schemas

**Level:** Haiku (generation) with a Sonnet review pass. **Depends on:** nothing. **Blueprint:** §4, §5, §12, §14.

Deliverables:
1. Full directory tree per Blueprint §4 (every directory has a README or a real file — no empty dirs).
2. JSON Schemas in `.agentic/schemas/`: `config.schema.json`, `ticket.schema.json`, `context-packet.schema.json`, `handoff-record.schema.json`, `agent-manifest.schema.json`, `workflow.schema.json`, `quality-gate-result.schema.json`, `adr-frontmatter.schema.json`.
3. Templates in `.agentic/templates/`: `epic.md`, `ticket.md`, `adr.md`, `pr-description.md`, `handoff-record.md`, `migration-plan.md`, `feature-request.md`.
4. `VERSION` file and semver conventions note.

Acceptance: every schema parses; every template's frontmatter validates against its schema; `config.yaml` example validates against `config.schema.json`.

## Phase 1 — Governance Core

**Level:** Opus. **Depends on:** Phase 0. **Blueprint:** §7, §9, §20, §21.

Deliverables:
1. Seed agentic ADRs in `adrs/agentic/` (hierarchy, fresh subagents, context minimization, human boundaries, mandatory PRs, active tracking, adapter model, ownership/upgrade, cost gates, minimal change).
2. `.agentic/governance/`: `approval-boundaries.md`, `cost-control.md`, `security.md`.
3. `.agentic/upgrade/`: `README.md` (upgrade flow incl. drift detection), `ownership.yaml` (machine-readable ownership map).
4. ADR authority-order resolution rules, including the project-overrides-company-overrides-agentic mechanics and the "override must name the overridden ADR" rule.

Acceptance: an Opus reviewer can answer any "who may decide X?" question from these files alone, with no contradictions against the Blueprint.

## Phase 2 — Orchestration Contract

**Level:** Opus. **Depends on:** Phase 1. **Blueprint:** §11, §12, §13, §22.

Deliverables:
1. `.agentic/orchestrator/README.md`: spawn rules (one fresh subagent per task type — enumerate all nine task types), context-packet assembly algorithm, result contract, retry/reassign/escalate ladder, parallelism rules, resume flow.
2. `.agentic/handoff/README.md`: handoff record model + the resumability invariant and how it is tested.
3. `.agentic/workflows/statuses.yaml`: the nine-status machine with transitions, triggering events, and triggered workflows.
4. Context-minimization policy doc (`.agentic/orchestrator/context-policy.md`): stop conditions, graph-before-grep rule, overrun declaration, budgets.

Acceptance: a Sonnet agent given only a sample ticket + these files can describe, step by step, exactly which subagents get spawned with which packet fields — with no ambiguity about who spawns what.

## Phase 3 — Agent Roles

**Level:** Sonnet (role content), Haiku (manifest stubs from the role table). **Depends on:** Phase 2. **Blueprint:** §10, §19.

Deliverables — for each of the 15 roles plus `_template/`:
1. `agent.md` — mission, responsibilities, boundaries, escalation rules, default context-loading rules, forbidden actions, handoff expectations.
2. `prompt.md` — operational system prompt (assembled from agent.md content; keep them consistent).
3. `tools.yaml`, `skills.yaml`, `mcps.yaml` — required/default/optional grants, forbidden actions, unavailable-tool escalation.

Acceptance: manifests validate against `agent-manifest.schema.json`; every tool/skill/MCP referenced exists in the registries (Phase 7 cross-check); no role grants merge/deploy/ADR-accept capability; PO vs. Coordinator boundary is unambiguous.

## Phase 4 — Workflows

**Level:** Sonnet. **Depends on:** Phases 2–3. **Blueprint:** §3, §14, §15.

Deliverables in `.agentic/workflows/`:
1. `epic-intake.workflow.yaml` — epic → PO understanding comment → decomposition → ticket-quality gate → cost gate → backlog.
2. `ticket-implementation.workflow.yaml` — Ready for Development → In Progress → In Review → In Test → Ready for Human Acceptance.
3. `review-followup.workflow.yaml` — Review → Task Extraction → Duplicate Detection (not-done tickets only) → Ticket Creation → PO prioritization.
4. `epic-acceptance.workflow.yaml` — completion check, human notification, Ready for Merge, Done, documentation sweep.
5. `blocked-escalation.workflow.yaml` — Blocked triage ladder up to human notification.
6. `upgrade.workflow.yaml` and `migration.workflow.yaml` — boilerplate upgrade and existing-project adoption.
7. `README.md` — workflow syntax reference.

Acceptance: all workflows validate against `workflow.schema.json`; every step names an existing role; every human gate maps to a governance boundary from Phase 1; every status transition in workflows exists in `statuses.yaml`.

## Phase 5 — Adapters

**Level:** Sonnet. **Depends on:** Phase 0 (schemas); informs Phase 4. **Blueprint:** §17, §18, §21.

Deliverables:
1. `task-tracking/INTERFACE.md` — canonical operations, canonical model, event contract. Plus `jira-cloud.adapter.yaml` and `gitlab-ce.adapter.yaml` (operation + status mappings, webhook event mapping — **reference manifests, no productive code**) and `mock.adapter.yaml` + mock behavior spec (markdown tickets in `work/tickets/`, polling events).
2. `git/INTERFACE.md` — branch/diff/commit/PR operations; the structural no-merge-to-protected-branches constraint.
3. `notifications/INTERFACE.md` — notify-human events routed through the tracker.
4. `design-system/INTERFACE.md` — tokens, component rules, UX constraints; Figma-MCP-backed and file-backed variants.
5. `secrets/INTERFACE.md` — mediated-access model, approval flow for raw access, audit events.
6. `adapters/README.md` — adapter philosophy, conformance (mock = reference), how to add a provider.

Acceptance: a Sonnet agent can walk the full epic dry-run using only the mock adapter spec; Jira/GitLab manifests cover every canonical operation or explicitly mark gaps.

## Phase 6 — Bootstrap, Upgrade, Migration

**Level:** Opus (flow design review), Sonnet (script + docs). **Depends on:** Phases 1, 5. **Blueprint:** §6, §7, §8.

Deliverables:
1. `bootstrap/README.md` — three modes, step order, idempotency, readiness report format.
2. `bootstrap/questionnaire.yaml` — declarative questions → config keys, with conditionals (UI? → Playwright required; Figma? → Figma MCP).
3. `bootstrap/bootstrap.sh` — runnable skeleton: `new-project` fully functional against mock adapters (questionnaire → config.yaml → ADR copy → tooling validation → readiness report); `existing-project` installs `.agentic/` and emits the Migration Agent's first task; `upgrade` delegates to the upgrade flow. Clearly marked TODO seams where real adapters plug in.
4. `migration/analysis-checklist.md` and migration-plan flow docs.
5. Mandatory-tooling validation logic spec: capability → configured provider | mock | not-ready.

Acceptance: `bootstrap.sh new-project` runs end-to-end on a fresh git repo and produces a valid `config.yaml` + readiness report; re-running is a no-op validation pass.

## Phase 7 — Tooling Layer & Quality Gates

**Level:** Sonnet. **Depends on:** Phase 3. **Blueprint:** §16, §19, §20.

Deliverables:
1. `.agentic/tools/registry.yaml` — quality-gate runner, ADR/governance checker, git adapter, task-tracking adapter, notification adapter, secrets adapter, design-system adapter, cost-approval gate: capability, mandatory/conditional status, interface pointer, unavailable-escalation.
2. `.agentic/mcps/registry.yaml` — Graphify, codebase-memory, Playwright MCP, Figma MCP (conditional): when mandatory, capabilities, configuration keys.
3. `.agentic/skills/` — `ponytail.md` (minimal-change discipline), `context-minimization.md`, `ticket-quality.md`, `handoff-discipline.md` + registry.
4. `.agentic/quality-gates/gates.yaml` + `README.md` (exception policy: documented failure → PR allowed; justified + documented exception → Ready for Merge allowed).

Acceptance: every entry in every role's manifests resolves to a registry entry; every gate in `gates.yaml` is referenced by at least one workflow; the ADR checker spec provably blocks agent-side ADR acceptance.

## Phase 8 — Consistency & Validation Pass

**Level:** Cursor Composer 2.5 or Codex. **Depends on:** Phases 0–7.

Deliverables:
1. Repo-wide cross-reference check: every relative link resolves; every role/tool/skill/MCP/gate/status/workflow mentioned anywhere exists exactly once in its registry; terminology is uniform (e.g., "context packet", "handoff record", canonical status names).
2. Schema validation run over all YAML/JSON/frontmatter; fix violations.
3. A `validate.sh` (or equivalent) that re-runs these checks — this becomes the boilerplate's own CI gate.

Acceptance: `validate.sh` exits 0; a grep for orphaned references returns nothing.

## Phase 9 — End-to-End Dry-Run

**Level:** Opus supervising Sonnet workers. **Depends on:** Phase 8.

Script and execute the canonical journey against the mock adapter: write a sample epic → PO intake → decomposition into ≥3 tickets (one triggering the cost gate, one triggering an ADR proposal) → implementation → review with one blocking + one non-blocking finding → follow-up chain → tests → Ready for Human Acceptance → human notification artifact → PR description artifact. Every subagent boundary produces a real handoff record.

Acceptance: a fresh agent given only `work/tickets/` and the handoff records can reconstruct the entire history; every human gate fired exactly where the governance docs say it must; context overruns were declared or absent.

## Phase 10 — Pilot & Feedback

**Level:** Human-led, PO Agent assisted. **Depends on:** Phase 9.

Adopt the boilerplate on one real project (new-project mode). Run one real epic with a real tracker adapter built against `INTERFACE.md` (first productive adapter — this is deliberately *after* v1). File every friction point as a feature request against the boilerplate repo using the shipped template. Triage into v2.1.

---

## Cross-phase rules for implementing agents

1. **Stay in your phase's file set.** Loading Blueprint sections outside your phase is a context overrun — declare it.
2. **Propose, don't decide.** Anything resembling an architecture decision goes into a proposed ADR, not into prose.
3. **The Blueprint wins.** On conflict between this plan and `BLUEPRINT.md`, the Blueprint is authoritative; flag the conflict rather than silently reconciling.
4. **No productive integrations.** If you find yourself writing a Jira API call, stop — v1 ships interfaces and mocks only.
5. **Every file you create must be referenced** from at least one other file (registry, README, or index). Orphan files fail Phase 8.
