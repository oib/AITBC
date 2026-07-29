# Crosswalk: neutral-core concepts → SAW home

The clean-room blueprint was organized under a `.agentic/` tree that has been **retired** in
favor of the [SAW](../README.md) harness (see [`../INTEGRATION.md`](../INTEGRATION.md)). This
table is the authoritative reconciliation: for every concept the blueprint and ADRs still name
with a `.agentic/…` path, it gives the **live SAW home** (or the neutral overlay location, or
marks it a retired concept realized differently).

Read it as: *"when a blueprint section says `.agentic/X`, the working system provides it at Y."*

## Bootstrap, configuration & upgrade

| Blueprint concept (`.agentic/…`) | Live home | Notes |
|----------------------------------|-----------|-------|
| `bootstrap/bootstrap.sh`, `bootstrap/questionnaire.yaml` | [`scripts/setup-template.sh`](../scripts/setup-template.sh) + [`TEMPLATE_SETUP.md`](../TEMPLATE_SETUP.md) | SAW bootstrap = `{{PLACEHOLDER}}` substitution wizard |
| `config.yaml` | [`.harness-manifest.yml`](../.harness-manifest.yml) + selected [`profiles/`](../profiles/README.md) profile | Identity/substitutions live in the manifest; stack choice in the profile |
| `VERSION` | [`HARNESS_CHANGELOG.yml`](../HARNESS_CHANGELOG.yml) + `manifest_version` in `.harness-manifest.yml` | SAW versions the harness here |
| `upgrade/ownership.yaml` | `.harness-manifest.yml` → `protected` / `replaced` / `renames` | Same ownership idea, SAW's mechanism |
| `upgrade/README.md` | [`scripts/sync-claude-harness.sh`](../scripts/sync-claude-harness.sh) + [`docs/HARNESS_SYNC_GUIDE.md`](../docs/HARNESS_SYNC_GUIDE.md) | The upgrade/drift flow |
| `overrides/` | `.harness-manifest.yml` → `protected` / `replaced` | Project-owned files stay upgrade-clean |
| `migration/analysis-checklist.md` | [`docs/guides/WORKSPACE-ADOPTION-GUIDE.md`](../docs/guides/WORKSPACE-ADOPTION-GUIDE.md) | Existing-project adoption |

## Roles, orchestration & handoff

| Blueprint concept | Live home | Notes |
|-------------------|-----------|-------|
| `agents/<role>/` | [`harness/claude/agents/`](../harness/claude/agents) — shipped source; `.claude/agents/` is the live runtime copy (+ `.gemini/`, `.codex/`, `agent_providers/`) | See [`ROLE-ROSTER.md`](ROLE-ROSTER.md) for the 15↔11 mapping |
| `orchestrator/README.md` | [`docs/workflow/ARCHITECT_IN_CLI_ROLE.md`](../docs/workflow/ARCHITECT_IN_CLI_ROLE.md) + [`.agents/skills/orchestration-patterns/SKILL.md`](../.agents/skills/orchestration-patterns/SKILL.md) | ARCHitect-in-CLI + TDM orchestrate |
| `orchestrator/context-policy.md` | [`profiles/neutral/adapters/knowledge.md`](../profiles/neutral/adapters/knowledge.md) (mandatory context sequence, OKF bundle) + [`.agents/skills/pattern-discovery/SKILL.md`](../harness/claude/skills/pattern-discovery/SKILL.md) | Knowledge capability defines the load order; "Search First, Reuse Always" covers pattern reuse |
| `handoff/README.md`, `templates/handoff-record.md` | [`AGENT_OUTPUT_GUIDE.md`](../harness/claude/AGENT_OUTPUT_GUIDE.md) + `docs/agent-outputs/` | Evidence-based delivery + agent output artifacts (shipped-harness source; live copy at `.claude/AGENT_OUTPUT_GUIDE.md`) |
| `schemas/context-packet.schema.json` | *retired concept* | SAW passes task context via role prompts + Linear ticket + AGENT_OUTPUT_GUIDE, not a formal packet schema |

## Workflow, tickets & quality gates

| Blueprint concept | Live home | Notes |
|-------------------|-----------|-------|
| `workflows/statuses.yaml`, `workflows/` | [`profiles/neutral/adapters/statuses.yaml`](../profiles/neutral/adapters/statuses.yaml) + [`docs/sop/AGENT_WORKFLOW_SOP.md`](../docs/sop/AGENT_WORKFLOW_SOP.md) + Linear board states | Canonical status machine is live; SAFe Exit States; tracker = Linear in `saw-stack` |
| `templates/epic.md`, `templates/ticket.md` | [`specs_templates/`](../specs_templates) (`spec_template.md`, `planning_template.md`, `pi_planning_template.md`) | Requirements decomposition = BSA |
| `templates/pr-description.md` | [`.github/pull_request_template.md`](../.github/pull_request_template.md) | PR content contract |
| `templates/feature-request.md` | [`.github/ISSUE_TEMPLATE/feature_request.md`](../.github/ISSUE_TEMPLATE/feature_request.md) | Upstream feature requests |
| `quality-gates/gates.yaml` | [`docs/sop/PRE_PR_VALIDATION_CHECKLIST.md`](../docs/sop/PRE_PR_VALIDATION_CHECKLIST.md) + `.github/workflows/` CI + QAS gate | Gate ownership = QAS role |
| `tools/registry.yaml`, `mcps/registry.yaml` | per-provider config: [`.cursor/mcp.json`](../.cursor/mcp.json), `.gemini/settings.json`, agent `tools:` frontmatter | MCP/tool grants declared per provider |

## Skills, governance & ADRs

| Blueprint concept | Live home | Notes |
|-------------------|-----------|-------|
| `skills/`, `skills/ponytail.md` | [`harness/claude/skills/`](../harness/claude/skills) (shipped source; live copy at `.claude/skills/`) / [`.agents/skills/`](../.agents/skills) (canonical) | `pattern-discovery` ≈ ponytail/minimal-change |
| `governance/approval-boundaries.md` | [`governance/approval-boundaries.md`](governance/approval-boundaries.md) | Kept in the neutral overlay |
| `governance/cost-control.md` | [`governance/cost-control.md`](governance/cost-control.md) | Kept in the neutral overlay |
| `governance/security.md` | [`governance/security.md`](governance/security.md) + [`../SECURITY.md`](../SECURITY.md) + `security-audit` skill | |
| `adapters/…/INTERFACE.md` | [`../profiles/neutral/adapters/`](../profiles/neutral/adapters) | Neutral capability contracts; bound by profile |
| `templates/adr.md`, ADR model | [`adrs/`](../adrs) hierarchy + System Architect flow | Three-level hierarchy is an overlay addition; see [ADR wiring](../adrs/agentic/README.md) |

## How to use this table

- **Actionable references** (a command to run, a file to edit) in the blueprint/ADRs have been
  updated in place to the "Live home" path.
- **Conceptual references** (naming a design artifact) are intentionally left as the design
  record; resolve them through this table rather than expecting a `.agentic/` file to exist.
