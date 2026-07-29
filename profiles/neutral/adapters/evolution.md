# Evolution Adapter — Interface

> Self-evolution signal extraction and auditable evolution assets (Genes, Capsules, Events).
> Evolver is a **prompt generator**, not a code patcher — it never edits source autonomously.

The evolution capability distills recurring agent friction into reusable, protocol-bound assets
that feed the **existing Self-Improvement loop** (`.claude/agents/self-improvement.md` Step 2).
Humans remain the gate for merges, outward writes, and cost-bearing network features.

## Canonical model

- **Memory scan** (`memory/`) — per-session signal logs (errors, capability gaps, perf notes).
  Gitignored at runtime; readable without the Evolver CLI installed.
- **GEP asset store** (`.evolver/gep/`) — `genes.json`, `capsules.json`, `events.jsonl`.
  Each line in `events.jsonl` is an immutable **EvolutionEvent** (id, timestamp, gene_id,
  signals[], outcome, review_mode).
- **Cycle** — Evolver scans memory, selects a Gene/Capsule via GEP, emits a reviewable prompt,
  and appends an EvolutionEvent. Validation commands are whitelisted (`node`/`npm`/`npx` only).

## Operations (all adapters MUST implement)

| Operation | Semantics |
| --------- | --------- |
| `list_events(since?)` | Return parsed lines from `.evolver/gep/events.jsonl` (newest first; optional ISO filter). |
| `get_event(id)` | Return one EvolutionEvent by `id`, or nearest match by timestamp. |
| `scan_signals()` | List signal summaries from `memory/` (file names + mtime; no Evolver CLI required). |
| `run_cycle(review=true)` | From repo root: invoke `evolver --review` when CLI present; returns prompt/event or skipped. |

## Provider bindings

A [profile](../../README.md) binds this capability to a provider:

- **`none`** (neutral default) — capability declared; no Evolver invocation; Self-Improvement and
  lifecycle hooks skip Evolver sources gracefully.
- **`evolver`** — local CLI `@evomap/evolver` (Node >= 18); offline by default; `--review`
  mandatory. Opt in via [`profiles/evolver/profile.yaml`](../../evolver/profile.yaml).

## Governance invariants  `#EXPORT_CRITICAL`

- `EVOLVER_AUTO_ISSUE=false` — no autonomous cross-repo issue filing.
- `EVOLVER_VALIDATOR_ENABLED=0` — no validator network by default.
- No `A2A_HUB_URL` / Hub connection without explicit human approval (`additional-costs` boundary).
- Project hooks register in **`.claude/hooks-config.json` only** — never run `evolver setup-hooks`
  (writes user-level config).

## Lifecycle hooks

Registered additively in `.claude/hooks-config.json` via `scripts/hooks/evolver-lifecycle.sh`.
Skips when provider is `none` or CLI is missing; 300s rate limit after a **successful** run.

| Harness event | Matcher | Command |
| ------------- | ------- | ------- |
| `SessionStart` | `.*` | `bash "${CLAUDE_PROJECT_DIR:-.}/scripts/hooks/evolver-lifecycle.sh"` |
| `PostToolUse` | `Write\|Edit` | same |
| `Stop` | `.*` | same |

## Who uses it

- **Self-Improvement Agent** — Step 2 skill mining reads `memory/` and `.evolver/gep/events.jsonl`.
- **Lifecycle hooks** — table above; always exit 0 (fail-open, same discipline as ABS-12).
