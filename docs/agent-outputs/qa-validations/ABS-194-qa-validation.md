# QA Validation — ABS-194

**Ticket:** ABS-194 — Orchestrator: Resume-Spawns re-derive SPAWN_CWD identically to first spawn + SEAT-CWD diagnostic log  
**Branch:** `ABS-194-auto`  
**Commit:** `09bf75f`  
**QAS run:** 2026-07-11  
**Verdict:** APPROVED

---

## Validation Method

Independent verification — not from handoff claims. All tests run by this QAS seat.

---

## AC Results

| AC | Criterion | Result |
|----|-----------|--------|
| AC1 | Resume-spawn re-derives `ORCH_SPAWN_CWD` == `worktree_for <ticket>` (no main-checkout divergence) | PASS |
| AC2 | Per-spawn diagnostic log line with ticket-id + effective cwd emitted (Erst- AND Resume-Spawn) | PASS |
| AC3 | Regression: simulated resume does NOT fall back to main-checkout | PASS |
| AC4 | No regress for first/parallel spawns; set `SPAWN_CWD` passes through verbatim | PASS |
| AC5 | `ORCHESTRATOR_SOP.md` run.log schema updated with `SEAT-CWD` field | PASS |

---

## Evidence

### test-resume-cwd.sh (new unit suite, 17 assertions)

```
bash tests/test-resume-cwd.sh
  PASS  Ready for Development is worktree-eligible
  PASS  In Review is worktree-eligible
  PASS  In Test is worktree-eligible
  PASS  In Progress is NOT worktree-eligible
  PASS  Done is NOT worktree-eligible
  PASS  Backlog is NOT worktree-eligible
  PASS  resume with empty SPAWN_CWD re-derives the existing worktree (NOT the main checkout)
  PASS  resume derivation == first-spawn derivation (worktree_for), no divergence
  PASS  In Review resume re-derives the worktree
  PASS  In Test resume re-derives the worktree
  PASS  first spawn: an already-set SPAWN_CWD passes through unchanged
  PASS  first spawn: sibling ticket keeps its own SPAWN_CWD (parallel spawns unaffected)
  PASS  no worktree on disk -> empty (never invents one; provisioning stays fail-closed)
  PASS  non-eligible status (In Progress) -> empty, no re-derivation
  PASS  ORCH_WORKTREE_SPAWNS=0 -> empty (operator opt-out honored)
  PASS  SEAT-CWD diagnostic row is emitted to run.log
  PASS  SEAT-CWD row carries the ticket-id AND the resolved worktree cwd

Total: 17 | Passed: 17 | Failed: 0
```

### test-station-guard.sh (regression, 50 assertions)

```
Total: 50 | Passed: 50 | Failed: 0
```

Confirms shared `worktree_eligible_status` helper refactor introduced no regression.

### test-orchestrator.sh — ABS-194 SEAT-CWD block (4 assertions)

```
PASS  ABS-194: live spawn emits a SEAT-CWD run.log event
PASS  ABS-194: SEAT-CWD row carries the ticket-id
PASS  ABS-194: SEAT-CWD shows the provisioned worktree path (not the main checkout)
PASS  ABS-194: a worktree-eligible spawn does NOT fall back to the main checkout
```

Pre-existing failures (2): startup provenance tests expecting `harness=<worktree-path>` but getting `harness=/Users/sahan/boilerplate-stable` (self-hosting mode per CLAUDE.md governance-provenance). `git diff main...ABS-194-auto -- scripts/orchestrator.sh | grep -iE "provenance|harness="` → 0 added lines. Unrelated.

### Syntax check

```
bash -n scripts/orchestrator.sh → OK
```

### Scope boundary

`git diff main...ABS-194-auto -- scripts/orchestrator.sh | grep "^+" | grep -iE "turn_cap|ABS-175|ensure_worktree|provision_worktree"` → one comment-only line (ABS-175 salvage-resume named in a comment). No turn-cap salvage (ABS-175) or grant provisioning (ABS-131/154) code changes.

---

## Implementation Review Notes

- `resolve_seat_cwd` is a pure function called at `run_spawn_cmd` — the single choke point every spawn (first, salvage-resume, handoff-repair) passes through. When `SPAWN_CWD` is empty it re-derives via `worktree_for` if the worktree exists on disk; it never provisions a missing one (fail-closed preserved in `live_spawn`).
- `worktree_eligible_status` extracts the duplicated `case` from `live_spawn`, making both paths agree by construction (DRY).
- `SEAT-CWD` run.log event mirrors the existing `SESSION-INVALIDATED` pattern — `runlog` 5-arg call with `cwd=<path>` or `cwd=<main-checkout>` in the note column.
- Async spawns run in `( live_spawn … ) &` subshells; each carries its own `SPAWN_CWD`, so `resolve_seat_cwd` can never clobber a sibling's cwd.

---

## Verdict

**APPROVED for RTE.**  
All 5 ACs pass. Scope held. No regression. Implementation is minimal, fail-closed, and pattern-compliant.
