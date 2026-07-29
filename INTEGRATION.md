# Integration: SAW base + technology-neutral core

This boilerplate is **built on [SAFe Agentic Workflow (SAW)](https://github.com/bybren-llc/safe-agentic-workflow)**
as its execution foundation, with a **technology-neutral core** layered on top so the same
harness works for any stack — SAW's opinionated Linear/Confluence/Supabase stack ships as one
ready-to-use *profile*, not as a hard dependency.

## Attribution

The files that make up the harness (`.claude/`, `.gemini/`, `.codex/`, `.cursor/`, `.agents/`,
`dark-factory/`, `docs/`, `scripts/`, `patterns_library/`, `.harness-manifest.yml`, and the
associated top-level docs) are vendored from **SAW**:

- **Source:** https://github.com/bybren-llc/safe-agentic-workflow
- **Version:** v2.10.0 · **Commit:** `a10f722aef5d0f794871801140c691d2cbec2d38`
- **License:** MIT — © 2026 J. Scott Graham (@cheddarfox) / ByBren, LLC (see [`LICENSE`](LICENSE), [`NOTICE`](NOTICE))

SAW's `LICENSE`, `NOTICE`, and `CITATION.*` are preserved unchanged. This integration adds a
neutral overlay; it does not relicense SAW.

## The two layers

| Layer | Owns | Where |
|-------|------|-------|
| **SAW harness (execution)** | *How* agents actually run: per-provider configs (Claude Code, Gemini CLI, Codex CLI, Cursor, Antigravity), SAFe roles, model-invoked skills, slash commands, hooks, dark-factory, and the harness-manifest sync/upgrade mechanism | SAW's original directories (`.claude/`, `.agents/`, `dark-factory/`, `scripts/`, `.harness-manifest.yml`, …) |
| **Neutral core (governance & vision)** | *What* the system guarantees regardless of stack: the product vision, the profile abstraction, the three-level ADR hierarchy, neutral capability/adapter definitions, and the human-approval boundaries | [`blueprint/`](blueprint), [`profiles/`](profiles), [`adrs/`](adrs), this file |

The neutral core never forks SAW's logic. It **wraps** it: a *profile* binds neutral
capabilities (task-tracking, docs, database, deploy, …) to concrete providers. SAW's stack is
the [`saw-stack`](profiles/saw-stack/profile.yaml) profile; [`neutral`](profiles/neutral/profile.yaml)
is the stack-agnostic default.

## Concept mapping (neutral core ↔ SAW)

Most of the neutral core's principles already exist in SAW under different names — the overlay
makes the mapping explicit rather than inventing a parallel system.

| Neutral-core concept ([`blueprint/`](blueprint)) | SAW realization |
|--------------------------------------------------|-----------------|
| Human-owns-irreversibility / no autonomous merge | **RTE** role: "PR SHEPHERD — NO code, NO merge, Exit: Ready for HITL" |
| PO/Coordinator orchestration | **TDM** + ARCHitect-in-CLI orchestrator role |
| Ticket Creation / requirements decomposition | **BSA** (Business Systems Analyst) |
| QA/Test gate owner | **QAS** (gate owner, iteration authority) |
| Security review trigger | **SecEng** (Independence Gate, non-collapsible) |
| Architecture changes need ADRs | **System Architect** + ADR templates |
| Context minimization / "graph before grep" | **pattern-discovery** skill ("Search First, Reuse Always") |
| Minimal-change (Ponytail) discipline | pattern-first + `patterns_library/` reuse culture |
| Boilerplate ownership + version-tracked upgrades | **`.harness-manifest.yml`** + `scripts/sync-claude-harness.sh` (identity/renames/protected/replaced/conflict-strategy) |
| Bootstrap (new-project) | `scripts/setup-template.sh` (`{{PLACEHOLDER}}` substitution) |
| Task-tracking adapter (neutral) | **Linear** in `saw-stack`; neutral interface in [`profiles/neutral/adapters/task-tracking.md`](profiles/neutral/adapters/task-tracking.md) |
| Docs adapter (neutral) | **Confluence** in `saw-stack` |
| Three-level ADR hierarchy (company/agentic/project) | *Added by this overlay* — SAW has ADR templates but no cross-project hierarchy ([`adrs/`](adrs)) |

## What changed vs. the original clean-room blueprint

The first version of this repo (`.agentic/` clean-room design) has been **retired in favor of
SAW's proven machinery**. Its genuinely additive ideas were kept and relocated:

- Vision & implementation plan → [`blueprint/`](blueprint)
- Neutral adapter interfaces → [`profiles/neutral/adapters/`](profiles/neutral/adapters)
- Governance principles → [`blueprint/governance/`](blueprint/governance)
- Three-level ADR hierarchy → [`adrs/`](adrs)

> **Note on internal links in `blueprint/` and `adrs/`:** those documents describe the neutral
> architecture and some still reference the original `.agentic/…` layout. Read them as the
> *design record*; the live execution layer is SAW, mapped via the table above. Rewriting those
> path references to SAW anchors is tracked as follow-on work (see
> [`blueprint/IMPLEMENTATION-PLAN.md`](blueprint/IMPLEMENTATION-PLAN.md)).

## Where to start

- **Use the harness:** SAW's [`README.md`](README.md) and [`TEMPLATE_SETUP.md`](TEMPLATE_SETUP.md).
- **Understand the vision & governance:** [`blueprint/BLUEPRINT.md`](blueprint/BLUEPRINT.md).
- **Pick/define a stack:** [`profiles/README.md`](profiles/README.md).
