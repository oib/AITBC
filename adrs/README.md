# ADRs — three-level hierarchy wired to SAW

This `adrs/` tree is the **authoritative ADR home** for the repository. It adds a three-level
hierarchy and an explicit human-accepted lifecycle on top of the [SAW](../README.md) base
(SAW ships an ADR-authoring role but only a flat `docs/adr/` location and no acceptance gate).

## The three levels

| Level | Directory | Scope | Copied to projects? |
|-------|-----------|-------|---------------------|
| Company | [`company/`](company/README.md) | Organization-wide (GDPR, company design system, engineering constraints) | No (referenced/added manually) |
| Agentic | [`agentic/`](agentic/README.md) | Boilerplate/agentic-SDLC decisions, apply across projects | Yes — shipped, updated via harness sync |
| Project | [`project/`](project/README.md) | This project's architecture | Local only |

**Authority order (conflict resolution):**
`accepted project ADR > accepted company ADR > accepted agentic ADR > governance defaults`.
A narrower ADR overrides a broader one only with an explicit `overrides:` reference and human
acceptance.

## Wiring to the SAW execution layer

| Concern | SAW mechanism | Wiring |
|---------|---------------|--------|
| **Who authors ADRs** | **System Architect** agent ([`.claude/agents/system-architect.md`](../.claude/agents/system-architect.md)) — "ADR creation for significant decisions" | Unchanged. The System Architect is the ADR author for all three levels. |
| **Where ADRs live** | SAW default: flat `docs/adr/ADR-{n}-{title}.md` | **Superseded by this tree.** New ADRs go to `adrs/<level>/` with ids `ADR-A/C/P-nnnn`. Treat `adrs/` as the single source; migrate any `docs/adr/` entries here. |
| **Proposed → accepted lifecycle** | SAW review = human PR review (RTE shepherds, HITL merges) | An ADR is **`proposed`** when authored on a branch; it becomes **`accepted`** when a **human merges its PR** — the same merge-to-main boundary that governs all agent work. Agents may only ever write `status: proposed`; a human sets `accepted` + `accepted_by`. |
| **Significant-decision trigger** | System Architect gate + [`PRE_PR_VALIDATION_CHECKLIST.md`](../docs/sop/PRE_PR_VALIDATION_CHECKLIST.md) ("ADRs created for significant decisions") | Architecture-changing work stops for an ADR before proceeding — the neutral `architecture-change` / `adr-acceptance` approval boundaries. |

So the neutral rule *"agents propose ADRs, humans accept them"* is realized by SAW's existing
human-merge gate: **ADR acceptance == a human merging the ADR's PR.** No new enforcement tool is
required; the invariant rides on the boundary SAW already enforces (agents never merge).

## Templates & format

Use the format described in [`agentic/README.md`](agentic/README.md) (minimal fields: `status`,
`scope`, `context`, `decision`, `consequences`, `supersedes`/`overrides` when needed). The
System Architect embeds relevant accepted-ADR excerpts into specs so downstream agents don't
re-discover them (mirrors SAW's pattern-first, context-efficient culture).
