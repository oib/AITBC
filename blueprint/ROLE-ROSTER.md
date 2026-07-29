# Role roster: blueprint's 15 roles ↔ SAW's 17 SAFe roles

The neutral blueprint ([`BLUEPRINT.md`](BLUEPRINT.md) §10) defined 15 agent roles. The
[SAW](../README.md) base ships **17 SAFe agents** ([`harness/claude/agents/`](../harness/claude/agents)
— the shipped-harness source; a live, byte-identical copy is read at runtime from
[`.claude/agents/`](../.claude/agents)). This
roster is the canonical reconciliation: **11 blueprint roles map directly to a SAW agent; 4
blueprint-only roles are realized as SAW skills/commands/tooling, not new agents** — keeping the
roster lean (SAW's "role collapsing" principle) rather than inflating it to 15.

## Direct mappings (blueprint role → SAW agent)

| Blueprint role | SAW agent | Notes |
|----------------|-----------|-------|
| Ticket Creation Agent | **BSA** — Business Systems Analyst ([`bsa.md`](../harness/claude/agents/bsa.md)) | Requirements decomposition, acceptance criteria, test strategy |
| Architect Agent | **System Architect** ([`system-architect.md`](../harness/claude/agents/system-architect.md)) | ADRs, Stage-1 PR review, migration approval |
| Review Agent | **System Architect** + **QAS** | Architecture/technical review = System Architect; AC verification = QAS (gate owner) |
| Frontend Agent | **FE Developer** ([`fe-developer.md`](../harness/claude/agents/fe-developer.md)) | |
| Backend Agent | **BE Developer** ([`be-developer.md`](../harness/claude/agents/be-developer.md)) | |
| Data Agent | **DE** + **DPE** ([`data-engineer.md`](../harness/claude/agents/data-engineer.md), [`data-provisioning-eng.md`](../harness/claude/agents/data-provisioning-eng.md)) | Schema/migrations = DE; test data/access = DPE |
| QA/Test Agent | **QAS** ([`qas.md`](../harness/claude/agents/qas.md)) | **Gate owner**, iteration authority, Exit: "Approved for RTE" |
| Security Agent | **SecEng** ([`security-engineer.md`](../harness/claude/agents/security-engineer.md)) | Independence Gate, non-collapsible |
| Documentation Agent | **TW** — Technical Writer ([`tech-writer.md`](../harness/claude/agents/tech-writer.md)) | |
| Release Agent | **RTE** — Release Train Engineer ([`rte.md`](../harness/claude/agents/rte.md)) | **PR shepherd, never merges**, Exit: "Ready for HITL" |
| PO Agent | **TDM** ([`tdm.md`](../harness/claude/agents/tdm.md)) + **POPM** (human) | Product-side coordination = TDM; final epic acceptance/prioritization = the human POPM. (The blueprint modeled the PO as an agent; SAW keeps final product judgment human — consistent with the blueprint's own "human performs final epic acceptance" rule.) |

## Blueprint-only roles → realized without a new agent

| Blueprint role | SAW realization | Why not a new agent |
|----------------|-----------------|---------------------|
| Coordinator Agent | **ARCHitect-in-CLI** orchestrator role ([`ARCHITECT_IN_CLI_ROLE.md`](../docs/workflow/ARCHITECT_IN_CLI_ROLE.md)) + **TDM** + [`orchestration-patterns`](../.agents/skills/orchestration-patterns/SKILL.md) skill | Orchestration in SAW is a *hat* worn in-CLI plus the TDM, not a separate agent — avoids a spawn-only role |
| Task Extraction Agent | [`retro`](../harness/claude/commands/retro.md) command + BSA follow-up | Extracting follow-ups is a workflow step (retro → new specs), not a standing role |
| Duplicate Detection Agent | [`pattern-discovery`](../harness/claude/skills/pattern-discovery/SKILL.md) skill + [`search-pattern`](../harness/claude/commands/search-pattern.md) command ("Search First, Reuse Always") | SAW's core "search before create" culture already prevents duplicates; it's a mandatory skill, not a role |
| Boilerplate Migration Agent | [`scripts/sync-claude-harness.sh`](../scripts/sync-claude-harness.sh) + [`.harness-manifest.yml`](../.harness-manifest.yml) + [workspace-adoption guide](../docs/guides/WORKSPACE-ADOPTION-GUIDE.md) | Upgrades/adoption are tooling + human-run scripts, not an agent that takes tickets |

## Net result

- **Agents:** 11 (SAW's roster, unchanged). No new agent files are introduced by the neutral overlay.
- **Coverage:** every blueprint responsibility has a home — as a SAW agent, a SAW skill/command,
  or the harness tooling.
- **Human boundary preserved:** the PO's product-judgment responsibilities land with the human
  POPM and the merge/deploy/ADR-acceptance boundaries stay human (see
  [`governance/approval-boundaries.md`](governance/approval-boundaries.md)).
