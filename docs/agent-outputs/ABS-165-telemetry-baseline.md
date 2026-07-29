# ABS-165 — Token/Cost Telemetry Baseline

**Ticket:** ABS-165 (parent ABS-164) — *Telemetrie-Fix: Cache-Token-Felder + RUN-USAGE-Rollup in run.log, Transcript-Lookup reparieren*
**Purpose:** freeze the reference numbers against which every later saving of the ABS-164 epic is proven. Without a trustworthy per-spawn/per-run token+cost record, no "we saved X" claim in a sibling story is auditable — this doc is that anchor.

## Why the fix was needed

Before ABS-165 the `SPAWN-USAGE` run.log line parsed only `usage.input_tokens`, so it read `tokens_in=1-2` on every spawn: the real input volume lives in the **cache fields** (`cache_read_input_tokens` / `cache_creation_input_tokens`) which the parser ignored (ABS-120 left incomplete). The spawn-telemetry transcript lookup (ABS-125) also failed to locate the session transcript for worktree cwds and logged a bare `TELEMETRY unavailable`, giving no diagnostic trail.

## What the fixed telemetry now records

- **Per spawn** (`SPAWN-USAGE` run.log note): `tokens_in= cache_read= cache_create= tokens_out= cost_usd=` — all five fields, with real values (> 1) on real spawns; empty (degrading to 0 in the rollup) on crashed spawns.
- **Per run** (`RUN-USAGE` run.log lines, emitted at run end, purely mechanical awk over the log): one summed line per ticket and one per role, carrying `spawns= tokens_in= cache_read= cache_create= tokens_out= cost_usd=`.
- **Transcript lookup**: found via find-by-UUID under `~/.claude/projects` (`-maxdepth 4`, reaching worktree-nested slugs); on a miss the attempted transcript filename + search dir is logged instead of a bare `unavailable`.

## Reference baseline — ABS-129 shape

The canonical reference feature run is **ABS-129**: **$6.36 across 9 spawns** (≈ $0.71/spawn averaged; the shape, not a per-seat guarantee — review seats on opus cost more than mechanical seats on sonnet). Any epic-ABS-164 optimisation is measured against this shape: a change is a *saving* only if, on a comparable feature, the summed `RUN-USAGE cost_usd` (and the token totals behind it) drop below this reference without a quality regression at the gates.

## Session baseline (overhead calibration)

The session-level baseline is captured with the **canonical feature prompt** and the CLI's own `/cost` readout for the wrapping session, so the orchestration **overhead** (packet construction, resume/rework turns, repair-handoff turns) is separable from the productive spawn spend. Method:

1. Run the canonical feature prompt through the standard station pipeline.
2. Record the summed `RUN-USAGE` totals from run.log (productive spawn spend).
3. Record the session `/cost` total (productive + overhead).
4. Overhead = session `/cost` − Σ `RUN-USAGE cost_usd`.

Re-capture this pair whenever the model mix or the packet/seam construction changes; a rising overhead ratio is itself a regression signal for the epic.

## How to reproduce the numbers

```bash
# Per-spawn + rollup lines for a run:
grep -E 'SPAWN-USAGE|RUN-USAGE' <state-dir>/run.log

# Aggregated per-seat / per-story / per-epic view (ABS-120 report):
scripts/orchestrator-report.sh <state-dir>/run.log
```
