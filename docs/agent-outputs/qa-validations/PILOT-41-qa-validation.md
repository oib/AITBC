# QA Validation — PILOT-41
## Status-Kollektor + run-status-Skill

**Verdict: APPROVED**
**Date:** 2026-07-25
**QAS seat:** qas
**Branch under review:** PILOT-41-auto
**Commit under review:** badbd8a4

---

## Summary

Three deliverables in commit `badbd8a4`:
- `scripts/run-status-collector.sh` — mechanical, read-only one-call status collector
- `harness/claude/skills/run-status/SKILL.md` — isolated-fork skill (`context: fork`)
- `tests/test-run-status-collector.sh` — 24 assertions

---

## Acceptance Criteria

### AC1: Answer < 1 KB in calling context (manual baseline ≥ 5 KB)

**PASS.**

Mechanism: The `run-status` skill is defined with `context: fork` and `agent: Explore`
(pattern-discovery isolation pattern). Only the 5–10 line prose summary returns to the
caller; the raw collector output stays in the fork. The raw collector output itself is
compact (~270–290 bytes on an idle run), well under any reasonable threshold. End-to-end
drive confirmed:

```
# run-status 2026-07-25T21:47:51Z
board.Backlog: 2
board.Grooming: 1
board.total: 3
spawns.status: unavailable
mr.status: unavailable (set RUN_STATUS_MR_CMD)
inflight.status: unavailable
run.health: unavailable
sensors.status: unavailable
humangate.count: 0
next: dispatch of a ready ticket
```

Output: 290 bytes. With fork isolation, caller receives only 5–10 prose sentences.

### AC2: Every waiting Human Gate is named (silence must never mean "all OK")

**PASS.**

- Every facet header is **always** emitted — even when zero gates exist, the output
  states `humangate.count: 0` positively (never silent).
- Human gates raised from: board human-gate statuses (`Needs PO Decision`,
  `Ready for Human Acceptance`, `Story Acceptance`, etc.), open MRs into protected
  branches, and paused-run markers (`fastfail`/`halt`/`outage`).
- Unavailable sources (no MR cmd, no state dir) are labelled `*.status: unavailable`,
  never rendered as "none" — absence of data is not reported as absence of the thing.
- Test Cases 1 (board + MR gates), 2 (positive "none"), 3 (unavailable labelled), and
  4 (paused-run gate) all verified this property.

### AC3: Two queries produce a real progress diff (ABS-547 budget auto-extend signal)

**PASS.**

- Collector output is deterministic and sorted by construction (sorted `awk` per-status
  counts; sorted facet order).
- Test Case 5 demonstrates:
  - A real board change (ticket promoted to Done) → non-empty diff showing the changed
    board lines.
  - An unchanged board → empty diff (no ordering noise).
- Minor observation (not blocking): the `# run-status <timestamp>` header line changes
  every second. For full-output diffs, consumers would filter `^#` lines to avoid
  spurious single-line deltas; the test correctly scopes to `board.*` lines for the
  ABS-547 signal. The system architect reviewed and approved this design.

---

## Gate Results

| Check | Result |
|---|---|
| tests/test-run-status-collector.sh | **24/24 PASS** |
| shellcheck -S warning (collector) | **CLEAN** |
| shellcheck -S warning (test) | **CLEAN** |
| test-agent-def-lint | **7/7 PASS** |
| test-harness-parity | **6/6 PASS** |
| generate-governor.sh --providers --check | **OK** |

### Test run

```
=== Run-Status Collector (PILOT-41) ===

Case 1: board + MR human gates
  PASS header present
  PASS board counts by status
  PASS multi-word status counted
  PASS board total
  PASS spawn count from ledger
  PASS in-flight seat w/ role
  PASS in-flight count
  PASS MR into main flagged as gate
  PASS MR into feature branch not a gate
  PASS PO-decision ticket named as gate
  PASS MR-into-main named as gate
  PASS both human gates counted
  PASS next event derived from in-flight

Case 2: healthy board, no gates (positive 'none')
  PASS zero gates stated positively
  PASS run health ok

Case 3: unavailable sources labelled (not silent, not 'none')
  PASS no state dir -> spawns unavailable
  PASS no MR cmd -> MRs unavailable
  PASS no sensor script -> sensors unavailable
  PASS no state dir -> health unavailable (not silent)

Case 4: paused run is a human gate
  PASS fastfail marker -> paused
  PASS paused run raised as human gate

Case 5: two runs -> real progress diff
  PASS diff shows the newly-done ticket
  PASS diff is non-empty on real progress
  PASS identical board -> empty diff (no ordering noise)

=== 24/24 passed ===
ALL PASS
```

Commit verified: `badbd8a4` exists and is reachable via `refs/heads/PILOT-41-auto`.

---

## Design Quality

- `set -euo pipefail` + `|| true` per optional source — graceful degradation
- Read-only shell; no DB/auth/migration surface; no LLM
- Isolated-fork pattern reused verbatim from pattern-discovery (`context: fork`,
  `agent: Explore`, `allowed-tools: Bash, Read`)
- PILOT-40's `ops-sweep-sensors.sh` treated as optional (graceful degradation)
- Wiring into Ops-Sweep dispatch seat correctly deferred to PILOT-42

---

## Verdict

**APPROVED — transitioning to Story Acceptance.**

All three acceptance criteria met, all harness gates green, end-to-end drive
confirmed. No blocking or medium findings.
