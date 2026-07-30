---
name: run-status
description: "Answer the operator's recurring \"Status?\" question in one compact\
  \ reply. Use when the operator (or the Ops-Sweep seat before it acts) asks \"status?\"\
  , \"where are we?\", \"what's running / stuck / waiting on me?\", or wants a run\
  \ situation report. Runs as an isolated fork \u2014 only the short answer returns,\
  \ the raw dumps stay in the fork."
triggers:
- user
- model
context: fork
subagent: true
allowed-tools:
- exec
- read
---

# Run-Status Skill

## Purpose

Answer "Status?" without dragging the raw material into the caller's context.
The operator asks this several times a session; answered by hand it costs 4–6
tool calls whose multi-kilobyte dumps (board listings, runlog tails, MR lists)
then sit permanently in the calling window. This skill runs the mechanical
collector inside an **isolated fork**, reads its output there, and returns ONLY
a 5–10 line prose summary — the same isolation pattern `pattern-discovery` uses
(raw material stays in the fork; only the distilled result comes back).

## When to Use

- The operator asks "status?", "where are we?", "what's stuck?", "what do you
  need from me?".
- The Ops-Sweep (TDM) seat wants a situation report BEFORE taking any action.
- Any time you need the run's state but must NOT grow the caller's context by
  the kilobytes of raw tracker/runlog/MR output.

## How It Works

Run the collector once and read its (line-oriented, deterministic) output:

```bash
scripts/run-status-collector.sh
```

Pass the run-state through the environment when available, so the spawn/in-flight/
health facets are populated rather than "unavailable":

```bash
ORCH_STATE_DIR="$ORCH_STATE_DIR" \
RUN_STATUS_MR_CMD='glab mr list -R <repo> 2>/dev/null | awk "NR>2{print \$1, \$4}"' \
scripts/run-status-collector.sh
```

The collector emits one statement per line, grouped by facet:
`board.<Status>: <n>`, `board.total`, `spawns.total`, `mr.<id>: target=… gate=…`,
`inflight.<ticket>: role=… age=…s`, `run.health`, `sensors.<i>`,
`humangate.<i>` + `humangate.count`, and a derived `next:` line.

## Output Contract (STRICT — this is the whole point)

The fork's reply back to the caller MUST be ONLY the prose summary, **under
1 KB**, structured as (5–10 lines):

1. **Done / progress** — what finished or advanced (from the board counts).
2. **Running** — in-flight seats and how long they have been going.
3. **Stuck / attention** — sensor findings, paused run-health, long-running seats.
4. **Needs YOU (human gates)** — name EVERY `humangate.*` line. If
   `humangate.count: 0`, say so explicitly ("no human action pending").
5. **Next** — the derived `next:` line.

Hard rules:

- **NEVER echo the raw collector output**, board listings, runlog lines, or MR
  dumps back to the caller. Those stay in the fork. The caller gets sentences.
- **Silence is forbidden for human gates.** Every waiting human gate MUST be
  named; an omitted gate is a correctness failure (a run can look "fine" while
  it is actually blocked on the human). If `humangate.count` is 0, state that
  positively — do not just leave it out.
- **Report only what the collector saw.** A facet printed as `unavailable`
  (e.g. `mr.status: unavailable`, `sensors.status: unavailable`) is reported as
  "unknown", never as "none" — absence of data is not absence of the thing.

## Progress Diff

The collector output is stable and diffable by construction. To report progress
between two points in time, capture and diff:

```bash
mkdir -p work/scratch
scripts/run-status-collector.sh > work/scratch/status.a    # earlier
scripts/run-status-collector.sh > work/scratch/status.b    # later
diff work/scratch/status.a work/scratch/status.b           # the real progress delta
```

A non-empty diff is genuine forward motion — the signal the ABS-547 budget
auto-extend reads to decide whether a run is still making progress.

## Reference

- Collector: `scripts/run-status-collector.sh` (mechanical, read-only, no LLM).
- Plan + Change-Contract: the Ops-Sweep proposal, §5 (Status skill: same
  collection, two consumers — the operator session and the Ops-Sweep seat).
