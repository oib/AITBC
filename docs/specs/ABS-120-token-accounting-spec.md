# ABS-120 Design Spec — Token/Cost Accounting in run.log + Cost Report + Right-Sizing Defaults

**Ticket**: ABS-120 (epic ABS-114) · **Status**: draft (pending architect review) · **Date**: 2026-07-07

## 1. Field extraction (attempt_spawn)

The spawn's `--output-format json` result already carries `total_cost_usd` and
`usage.input_tokens`/`usage.output_tokens` — the runner captures the stdout and throws the fields
away. `attempt_spawn` now extracts them (same sed-over-JSON idiom as `extract_session_id`, no jq
dependency) and appends ONE run.log line per completed spawn attempt:

```
<ts>  SPAWN-USAGE  <ticket>  <role>  <status>  tokens_in=<n> tokens_out=<n> cost_usd=<x>
```

This APPENDS a new event KIND to the existing 6-column TSV — no existing column changes, so the
ABS-111 timing-analysis consumers keep working (ticket constraint). Missing fields (crash before
a result, foreign provider) degrade gracefully to empty values (`tokens_in= tokens_out=
cost_usd=`) — the line still appears, the pipeline never breaks.

## 2. Report script — scripts/orchestrator-report.sh

Zero-dependency bash+awk (like every other script). `orchestrator-report.sh [run.log path]`
(default `work/.orchestrator/run.log`; `ORCH_STATE_DIR` honored). Aggregates SPAWN-USAGE lines:

- **per seat (role)**: spawns, tokens in/out, cost
- **per story (ticket)**: same
- **per epic**: ticket→parent resolved through `TRACKER_CMD get` when a tracker is configured
  (one `get` per distinct ticket, cached); without a tracker the epic section prints a notice and
  is skipped — the report never fails.

Extensible: ABS-125's telemetry columns land in the same script later (per ticket).

## 3. Right-sizing defaults (operator-decided: SET, not recommended)

`model: sonnet` in the role frontmatter of the mechanical seats — `qas`, `tech-writer`, `rte` —
in BOTH namespaces (`.claude/agents/` and `harness/.claude/agents/`, ABS-96).
`system-architect` and `po-agent` stay on opus (established quality rule). Precedence unchanged:
`ORCH_MODEL`/`ORCH_MODEL_<ROLE>` (already implemented in the seam) overrides the frontmatter;
the ABS-121 ticket label will slot between them. NOTE: the operator's Sonnet-4.6 pin in
`orchestrator-spawn-claude.sh` (Sonnet 5 token regression) governs what `sonnet` resolves to —
the pin is included in this epic branch, single chokepoint after `$MODEL` resolution.

Dry-run evidence limitation: the model is resolved inside the SPAWN SEAM (frontmatter read), so a
dry-run intent line cannot show it without duplicating seam logic in the runner; evidence for the
default change = the frontmatter diff + a test asserting the seam resolves `sonnet` for qas and
that `ORCH_MODEL_<ROLE>` still wins (seam invoked directly with a stub claude binary).

## 4. Test plan

- fixture spawn JSON with usage fields (extend stub-spawn to emit them) → run.log SPAWN-USAGE
  line with the exact values
- crash spawn → SPAWN-USAGE line with empty values, no pipeline break
- report: fixture run.log → expected per-seat/per-ticket table (golden assertion); epic section
  with mock tracker; missing tracker → notice, exit 0
- frontmatter: qas/tech-writer/rte = sonnet, system-architect/po-agent = opus (diff-pinning test)
- seam: role frontmatter `sonnet` → `--model` arg contains the pinned sonnet resolution;
  `ORCH_MODEL_<ROLE>` env overrides it (existing B6 mechanism, regression)
