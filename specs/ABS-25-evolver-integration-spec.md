# ABS-25 Design Spec — Evolver Integration

**Ticket**: ABS-25 · **Status**: ready for implementation · **Date**: 2026-07-03

Execution contract for wiring [EvoMap Evolver](https://github.com/EvoMap/evolver) into the
SAFe boilerplate as an `evolution` capability adapter feeding the existing Self-Improvement loop.
Jira holds the story; **this file is authoritative for paths, hooks, and validation**.

## 1. Goal

Evolver is a prompt generator (GEP protocol), not a code patcher. It scans `memory/`, selects
Genes/Capsules, emits a reviewable GEP prompt, and records auditable `EvolutionEvent` lines in
`.evolver/gep/events.jsonl`. The Self-Improvement Agent consumes those events as Step 2 evidence;
humans remain the gate for merges, outward writes, and cost-bearing network features.

**Integration thesis:** Evolver is bound as a **capability adapter feeding the existing
Self-Improvement loop**, not as a parallel self-improvement mechanism.

## 2. File manifest

| Action | Path | Notes |
| ------ | ---- | ----- |
| **Add** | `profiles/neutral/adapters/evolution.md` | Capability interface |
| **Edit** | `profiles/neutral/profile.yaml` | Add `evolution` capability block |
| **Add** | `profiles/evolver/profile.yaml` | Opt-in binding (`based_on: neutral`) |
| **Edit** | `profiles/neutral/adapters/README.md` | Add `evolution` row |
| **Edit** | `profiles/README.md` | Add capability + shipped profile rows |
| **Edit** | `.claude/agents/self-improvement.md` | Step 2 evidence sources |
| **Edit** | `agent_providers/claude_code/prompts/self-improvement.md` | Mirror Step 2 |
| **Add** | `scripts/hooks/evolver-lifecycle.sh` | Thin Evolver wrapper |
| **Edit** | `.claude/hooks-config.json` | Additive lifecycle hooks (§5) |
| **Add** | `tests/test-hooks-config.sh` | JSON + required-key regression |
| **Add** | `tests/test-evolver-lifecycle.sh` | Hook skip paths + rate limit |
| **Edit** | `.gitignore` | `.evolver/`, `memory/` |
| **Edit** | `.env.template` | Governance defaults (§4) |
| **Add** | `docs/onboarding/EVOLVER-INTEGRATION.md` | Operator guide |
| **Add** | `work/fixtures/evolver/sample-events.jsonl` | Fixture EvolutionEvent |
| **Add** | `work/fixtures/evolver/sample-skill-proposal.md` | Expected mapping example |

**Out of manifest:** do not edit `.agents/`, `.cursor/`, `.gemini/`, `.codex/` in this ticket
unless a follow-up explicitly scopes multi-provider sync.

## 3. Evolution adapter operations

`profiles/neutral/adapters/evolution.md` MUST define:

| Operation | Semantics |
| --------- | --------- |
| `list_events(since?)` | Return parsed lines from `.evolver/gep/events.jsonl` (newest first; optional ISO timestamp filter). |
| `get_event(id)` | Return one EvolutionEvent by id field, or nearest match by timestamp. |
| `scan_signals()` | List signal summaries from `memory/` (file names + mtime; do not require Evolver installed). |
| `run_cycle(review=true)` | From repo root: invoke `evolver --review` when CLI present; return `{ prompt, event_id }` or `{ skipped: true, reason }`. |

**Providers:**

- **`none`** (neutral default) — capability declared; no Evolver invocation; Self-Improvement skips Evolver sources gracefully.
- **`evolver`** — local CLI `@evomap/evolver` (Node >= 18); offline by default; `--review` mandatory.

## 4. Governance defaults

Document in `profiles/evolver/profile.yaml` `notes` and `.env.template`. Canonical list:
[`profiles/neutral/adapters/evolution.md`](../profiles/neutral/adapters/evolution.md) § Governance invariants.

Prerequisite (documented, not installed by the repo): `npm i -g @evomap/evolver` (Node >= 18).

## 5. Hook wiring sketch  `#PATH_DECISION`

Evolver's `setup-hooks --platform=*` targets **user-level** config. This repo uses
**project-level** `.claude/hooks-config.json` (see ABS-12 §5). Implementation:

### 5.1 Wrapper script

`scripts/hooks/evolver-lifecycle.sh`:

- `cd` to `${CLAUDE_PROJECT_DIR:-.}` (git repo root).
- If evolution provider is `none` → exit 0, stderr: `evolver-lifecycle: SKIP evolution provider none`.
- If `command -v evolver` fails → exit 0, stderr: `evolver-lifecycle: SKIP evolver not installed`.
- Else run `evolver --review` (stderr-only; do not auto-apply GEP prompt to source).
- **Always exit 0** on skip or evolver failure (fail-open — same discipline as ABS-12 iteration-guard).
- Touch `.evolver/.last-hook-run` only after a **successful** `evolver --review`.

### 5.2 Additive registration in `.claude/hooks-config.json`

Append entries per the hook table in
[`profiles/neutral/adapters/evolution.md`](../profiles/neutral/adapters/evolution.md) § Lifecycle hooks.
**Do not** register on `SessionEnd` — `Stop` only. Do not remove or rewrite existing hooks.

### 5.3 Rate limit

Skip if last **successful** run was less than 300s ago (`.evolver/.last-hook-run` — gitignored).
Prevents evolver spam on every file edit.

### 5.4 Prohibited

- Running `evolver setup-hooks` in implementation, docs, or CI.
- Writing to `~/.cursor/hooks.json` or user-level `~/.claude/` hook config.

## 6. Success validation command

```bash
npx markdownlint-cli specs/ABS-25-evolver-integration-spec.md docs/onboarding/EVOLVER-INTEGRATION.md profiles/neutral/adapters/evolution.md && bash tests/test-hooks-config.sh && bash tests/test-evolver-lifecycle.sh && echo "ABS-25 SUCCESS" || echo "ABS-25 FAILED"
```

## 7. Demo script (QAS / fixture — no live Evolver required)

1. Read `work/fixtures/evolver/sample-events.jsonl` — confirm one JSON line with EvolutionEvent fields.
2. Read `.claude/agents/self-improvement.md` Step 2 — confirm `memory/` and `.evolver/gep/events.jsonl` listed.
3. Apply Step 2 procedure to the fixture — output must match structure of `sample-skill-proposal.md`.
4. Run success validation command — expect `ABS-25 SUCCESS`.
5. Open `.claude/hooks-config.json` — confirm iteration-guard entry still present alongside evolver entries.

## 8. Self-Improvement handoff mapping

Add to Step 2 evidence table:

| Source | How |
| ------ | --- |
| Evolver memory scan | Read `memory/` for repeated error/signal filenames referenced across sessions |
| Evolution events | Read `.evolver/gep/events.jsonl`; each line is an EvolutionEvent. Map `signals[]` / `gene_id` / `outcome` fields to recurring friction. Cite event id or timestamp in skill proposals. |

**Recurrence with Evolver:** same signal or gene activation on 2+ events, OR same friction in retro + 1 EvolutionEvent.

## 9. Pattern references

- `profiles/neutral/adapters/task-tracking.md` — adapter contract shape
- `profiles/jira-github-postgres/profile.yaml` — profile binding example
- `specs/ABS-12-iteration-guard-spec.md` §5 — additive hook registration
- `adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md`
- `adrs/agentic/ADR-A-0010-minimal-change-default.md`

## 10. Logical commits

1. `feat(profiles): add evolution capability and evolver profile [ABS-25]`
2. `feat(hooks): additive evolver lifecycle registration [ABS-25]`
3. `docs(self-improvement): wire Evolver evidence sources [ABS-25]`
4. `test(hooks): add hooks-config regression test [ABS-25]`

## 11. Subtasks

| Key | Title | Owner |
| --- | ----- | ----- |
| ABS-25a | Profile + adapter + gitignore + env template | Composer 2.5 |
| ABS-25b | Hook script + additive hooks-config + test | Composer 2.5 |
| ABS-25c | Self-Improvement wiring + fixtures + onboarding doc | Composer 2.5 |
| ABS-25d | Smoke + Self-Improvement E2E + Architect review | Human / Opus |
