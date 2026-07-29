---
type: concept
resource: profiles/neutral/adapters/evolution.md
tags: [evolution, self-improvement, evolver]
timestamp: 2026-07-03
---

# Evolution loop

[EvoMap Evolver](https://github.com/EvoMap/evolver) is wired in as an **evolution capability
adapter feeding the existing Self-Improvement loop** — not a parallel self-improvement
mechanism. It is a prompt generator, never a code patcher, and never auto-merges.

## What Evolver does

1. Scans `memory/` (per-session signal logs — errors, capability gaps, friction).
2. Selects Genes/Capsules via the GEP protocol.
3. Emits a reviewable GEP prompt (`evolver --review`, stderr only).
4. Appends an auditable `EvolutionEvent` line to `.evolver/gep/events.jsonl`.

Both `memory/` and `.evolver/` are created at runtime and gitignored.

## Opt-in profile

The neutral profile declares `evolution` with `provider: none` by default (no invocation; the
Self-Improvement Agent skips Evolver sources gracefully). To enable: select the
[`profiles/evolver/profile.yaml`](../profiles/evolver/profile.yaml) binding (`based_on: neutral`),
or set `ACTIVE_PROFILE=evolver` / `EVOLUTION_PROVIDER=evolver`. Requires Node >= 18 and a global
`npm i -g @evomap/evolver` install (not bundled by this repo).

## Lifecycle hook

`scripts/hooks/evolver-lifecycle.sh`, registered additively on **`Stop`** in
`.claude/hooks-config.json` (never `SessionEnd`): if the evolution provider is `none` or the
`evolver` CLI isn't installed, it exits 0 with a stderr `SKIP` notice; otherwise it runs
`evolver --review` and touches `.evolver/.last-hook-run` only after a successful run. A 300-second
rate limit against that marker prevents evolver spam on every edit. This mirrors the fail-open
discipline of the [iteration-guard hook](loop-termination.md).

## Governance defaults

Offline by default: `EVOLVER_AUTO_ISSUE=false`, `EVOLVER_VALIDATOR_ENABLED=0`. Hub/network
features (`A2A_HUB_URL`, `A2A_NODE_ID`) require explicit human approval via a follow-up ticket —
never set by the lifecycle hook itself. Running `evolver setup-hooks` (which targets user-level
config) is prohibited in implementation, docs, or CI; this repo keeps hooks project-level in
`.claude/hooks-config.json` only.

## Self-Improvement handoff

The Self-Improvement Agent (`.claude/agents/self-improvement.md`, Step 2 evidence) reads two
sources: `memory/` (session signal scan) and `.evolver/gep/events.jsonl` (parse each line's
`signals[]`, `gene_id`, `outcome`). **Recurrence heuristic with Evolver**: the same signal or
gene appears on 2+ events, OR retro friction plus 1 EvolutionEvent. Fixture example:
`work/fixtures/evolver/sample-events.jsonl` → `work/fixtures/evolver/sample-skill-proposal.md`.
Humans remain the gate for merges, outward writes, and any cost-bearing network feature.

## Related

- [capabilities-and-profiles.md](capabilities-and-profiles.md) — `evolution` as the 10th
  neutral capability
- [loop-termination.md](loop-termination.md) — the sibling hook (iteration-guard) sharing the
  fail-open pattern
- [approval-boundaries.md](approval-boundaries.md) — why Hub/network features need a human gate
- Source: `docs/onboarding/EVOLVER-INTEGRATION.md`, `specs/ABS-25-evolver-integration-spec.md`,
  `docs/sop/SELF_IMPROVEMENT_SOP.md`
