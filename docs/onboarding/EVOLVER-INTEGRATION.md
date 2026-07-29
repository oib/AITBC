# Evolver Integration Guide

This guide explains how [EvoMap Evolver](https://github.com/EvoMap/evolver) is wired into the
SAFe agentic boilerplate as an **evolution capability adapter** feeding the existing
Self-Improvement loop — not as a parallel self-improvement mechanism.

## Prerequisites

- **Node.js** >= 18
- **Evolver CLI** (global install; not bundled by this repo):

  ```bash
  npm i -g @evomap/evolver
  ```

- **Git repository** — Evolver uses git for blast-radius calculation; run from the project root.

## Opt-in profile

The neutral profile declares `evolution` with `provider: none` (default). To enable Evolver:

1. Use the [`profiles/evolver/profile.yaml`](../../profiles/evolver/profile.yaml) binding, or
2. Set `ACTIVE_PROFILE=evolver` and ensure `capabilities.evolution.provider: evolver`, or
3. Set `EVOLUTION_PROVIDER=evolver` in `.env` for a quick override.

Governance defaults and lifecycle hook wiring are defined in
[`profiles/neutral/adapters/evolution.md`](../../profiles/neutral/adapters/evolution.md)
(§ Governance invariants, § Lifecycle hooks).

## What Evolver does here

Evolver is a **prompt generator**, not a code patcher:

1. Scans `memory/` for session signals (errors, capability gaps, friction).
2. Selects Genes/Capsules via the GEP protocol.
3. Emits a reviewable GEP prompt (`evolver --review`).
4. Appends auditable `EvolutionEvent` lines to `.evolver/gep/events.jsonl`.

It never edits source autonomously and never auto-merges. Humans decide what crosses boundaries.

## Evolution → Self-Improvement handoff

The Self-Improvement Agent (`.claude/agents/self-improvement.md` Step 2) reads:

| Source | Path |
| ------ | ---- |
| Memory scan | `memory/` |
| Evolution events | `.evolver/gep/events.jsonl` |

Map `signals[]`, `gene_id`, and `outcome` to recurring friction. Cite event `id` in skill
proposals. Fixture example: `work/fixtures/evolver/sample-events.jsonl` →
`work/fixtures/evolver/sample-skill-proposal.md`.

**Recurrence with Evolver:** same signal or gene on 2+ events, OR retro friction + 1
EvolutionEvent.

## Gitignored runtime dirs

These are created at runtime and excluded from version control:

- `.evolver/` — GEP asset store and hook rate-limit marker
- `memory/` — per-session signal logs

## Validation

```bash
npx markdownlint-cli specs/ABS-25-evolver-integration-spec.md docs/onboarding/EVOLVER-INTEGRATION.md profiles/neutral/adapters/evolution.md
bash tests/test-hooks-config.sh
bash tests/test-evolver-lifecycle.sh
echo "ABS-25 SUCCESS"
```

Optional smoke (when Evolver CLI is installed):

```bash
ACTIVE_PROFILE=evolver evolver --review
# Expect GEP prompt on stderr; new line in .evolver/gep/events.jsonl
```

## Further reading

- `specs/ABS-25-evolver-integration-spec.md` — execution contract
- `profiles/neutral/adapters/evolution.md` — capability interface (canonical hook + governance table)
- `docs/sop/SELF_IMPROVEMENT_SOP.md` — Self-Improvement trigger model
