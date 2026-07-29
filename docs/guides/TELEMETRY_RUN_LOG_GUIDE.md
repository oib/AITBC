# Run-Log Telemetry: SPAWN-USAGE and RUN-USAGE Fields

**Relates to:** ABS-165 (cache-token parser fix + RUN-USAGE rollup + transcript lookup fix)
**Parent epic:** ABS-164 (harness token reduction)
**Last updated:** 2026-07-11

---

## Overview

Every orchestrator run writes a TSV `run.log`. Since ABS-165, each spawn's
real token and cost data is captured in a `SPAWN-USAGE` line, and a
`RUN-USAGE` summary is appended at run end. Before this fix the parser only
read `usage.input_tokens`, so every line showed `tokens_in=1-2` — the bulk of
input lives in the cache fields that were silently dropped.

---

## Quick Reference

```
# Per-spawn line (one per agent seat):
<ts>  SPAWN-USAGE  <ticket>  <role>  <status>  tokens_in=2 cache_read=250000 cache_create=18000 tokens_out=1234 cost_usd=0.7123

# Per-run summary lines (one per ticket + one per role, emitted at run end):
<ts>  RUN-USAGE  <ticket>  -  -  spawns=9 tokens_in=18 cache_read=2250000 cache_create=162000 tokens_out=11106 cost_usd=6.3600
<ts>  RUN-USAGE  -  <role>  -  spawns=3 tokens_in=6 cache_read=750000 cache_create=54000 tokens_out=3702 cost_usd=2.1200
```

---

## SPAWN-USAGE Fields

Each spawn writes one `SPAWN-USAGE` line to `run.log`. The `note` column
(column 6) contains five space-separated `key=value` pairs:

| Field | Source in CLI JSON | Meaning |
|---|---|---|
| `tokens_in` | `usage.input_tokens` | Non-cached input tokens (usually small) |
| `cache_read` | `usage.cache_read_input_tokens` | Tokens served from prompt cache (the real input volume) |
| `cache_create` | `usage.cache_creation_input_tokens` | Tokens written to prompt cache this turn |
| `tokens_out` | `usage.output_tokens` | Output (generated) tokens |
| `cost_usd` | `total_cost_usd` | Cost as reported by the CLI for this spawn |

**Why `tokens_in` is small:** Claude's prompt-cache means the full system
prompt + context is served from cache on all but the first turn. The true
input cost is `cache_read + cache_create`, not `tokens_in` alone.

**On crashed spawns:** all fields are empty (`tokens_in= cache_read= …`).
The rollup treats empty as 0, so the count is still accurate.

---

## RUN-USAGE Rollup

`emit_run_usage_rollup` runs at every clean and error exit of `main()`. It
reads every `SPAWN-USAGE` line in `$ORCH_RUN_LOG` and emits two groups:

- **Per-ticket** — `RUN-USAGE <ticket> - -` — summed across every role that
  touched that ticket in this run.
- **Per-role** — `RUN-USAGE - <role> -` — summed across every ticket the role
  worked on.

Each line's note carries: `spawns= tokens_in= cache_read= cache_create= tokens_out= cost_usd=`

The aggregation ignores `RUN-USAGE` lines (column 2 filter: `$2 == "SPAWN-USAGE"`),
so re-running the orchestrator after a restart never double-counts.

---

## Reading run.log for Cost Analysis

```bash
# All per-spawn and summary lines for a run:
grep -E 'SPAWN-USAGE|RUN-USAGE' /path/to/state-dir/run.log

# Per-ticket summary only:
grep 'RUN-USAGE' /path/to/state-dir/run.log | grep -v 'RUN-USAGE.*-.*-.*-'

# Total cost across all tickets for this run:
grep 'RUN-USAGE' /path/to/state-dir/run.log \
  | awk -F'\t' '$3 != "-" { match($6, /cost_usd=([0-9.]+)/, a); sum += a[1] } END { printf "Total: $%.4f\n", sum }'
```

---

## Transcript Lookup

`record_spawn_telemetry` locates the session transcript for each spawn to
attach token and cost evidence to the ticket comment.

**Search path:** `$ORCH_TRANSCRIPT_DIR` (default `~/.claude/projects`) with
`-maxdepth 4`. The depth was widened from 2 to 4 (ABS-165) because worktree
cwds add extra slug segments (`/path/to/worktree` → `~/.claude/projects/-path-to-worktree-<repo>/`).

**On failure**, the log now shows the specific path attempted:

```
TELEMETRY ... unavailable (no transcript: searched /Users/x/.claude/projects for <uuid>.jsonl)
```

This replaces the old bare `TELEMETRY unavailable`, which gave no diagnostic
trail. If lookup keeps failing, check:

1. `ORCH_TRANSCRIPT_DIR` points to the right Claude projects directory.
2. The session UUID in the spawn result matches a `.jsonl` file in that tree.
3. `-maxdepth 4` is deep enough for your worktree layout (increase if slugs
   nest deeper than 4 directory levels under `ORCH_TRANSCRIPT_DIR`).

---

## Packet-Cache Hits (ABS-176, hardened ABS-202)

When `build_packet` reuses a cached packet (same-role re-spawn, rework bounce, salvage, or crash
retry on an unchanged ticket), the provider receives an identical byte sequence and serves the
packet from its prompt cache. This shows up in `run.log` as a high `cache_read` with a near-zero
`tokens_in` on the second spawn of the same seat:

```
# First spawn of a seat — packet written fresh, then cached by the provider:
<ts>  SPAWN-USAGE  ABS-176  be-developer  In Progress  tokens_in=45 cache_read=0 cache_creation=28000 …

# Rework bounce (same seat, ticket unchanged) — packet served from cache:
<ts>  SPAWN-USAGE  ABS-176  be-developer  In Progress  tokens_in=2  cache_read=28000 cache_creation=0 …
```

The key signal: `cache_read` on bounce ≈ `cache_creation` on the first spawn. This confirms the
packet is byte-identical and the provider hit its cache.

This effect is **same-role only** — cross-role spawns have a different role-definition
systemprompt before the packet, so no shared cache prefix exists across seat boundaries.

The packet cache itself (the disk file at `$ORCH_STATE_DIR/packets/<ticket>.md`) is separate
from the provider prompt cache: the disk cache guarantees byte stability; the provider then
decides whether to cache and serve from its own token cache.

### Cache signature

The disk cache is keyed on a `|`-delimited signature stored in `$ORCH_STATE_DIR/packets/<ticket>.meta`:

```
updated=<tracker updated field>|from=<from_status>|to=<to_status>|role=<role>|resume=<true|false>|tracker_cmd=<TRACKER_CMD>|max_bytes=<ORCH_PACKET_MAX_BYTES>
```

A cache hit requires **all seven fields** to match the stored signature. Any mismatch rebuilds the
packet from scratch:

| Field | Why it's in the signature |
|---|---|
| `updated` | Ticket body changed — any tracker edit bumps this |
| `from`, `to`, `role` | Spawn coordinates written verbatim into the packet header |
| `resume` | Derived from whether a `kind: handoff` comment is present |
| `tracker_cmd` | Written verbatim into the packet header (`tracker_cmd:` line) |
| `max_bytes` | Drives the body-truncation budget — a different cap produces a different body |

**Cross-run invalidation (ABS-202).** `TRACKER_CMD` and `ORCH_PACKET_MAX_BYTES` are constant
within a single orchestrator run, so within a run there is no stale-cache risk. Across runs —
a restarted orchestrator with a different adapter path or a changed packet cap — a ticket whose
`updated` field has not changed would otherwise reuse a packet built under the old values.
ABS-202 closed this by folding both into the signature, so a cross-run change to either
invalidates the cache exactly as a ticket edit does.

---

## Cost Baseline — ABS-129 Shape

The reference baseline for the ABS-164 epic is **$6.36 across 9 spawns**
(≈ $0.71/spawn averaged) from the ABS-129 feature run. A change in a sibling
story is a *saving* only if, on a comparable feature, the summed
`RUN-USAGE cost_usd` drops below this reference without a quality regression
at the gates.

See [`docs/agent-outputs/ABS-165-telemetry-baseline.md`](../agent-outputs/ABS-165-telemetry-baseline.md)
for the full baseline methodology, including how to separate productive spawn
spend from orchestration overhead using the session `/cost` readout.

---

## See Also

- `scripts/orchestrator.sh` — `extract_usage_note`, `record_spawn_telemetry`,
  `emit_run_usage_rollup` (tagged `# ABS-165`)
- `tests/test-station-guard.sh` — unit tests: cache-heavy parser, rollup
  summation, no-double-count assertion
- [`docs/agent-outputs/ABS-165-telemetry-baseline.md`](../agent-outputs/ABS-165-telemetry-baseline.md)
- ABS-120 (token accounting), ABS-125 (spawn telemetry), ABS-164 (epic)
