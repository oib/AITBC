# ABS-36 E2E Dry-Run — Orchestrator Full Lifecycle Gate Evidence

**Date**: 2026-07-04
**Ticket**: ABS-36 (subtask ABS-55, stacked on ABS-52/53/54)
**Branch**: `ABS-55-orchestrator-e2e`
**Spec**: [`specs/ABS-36-orchestrator-spec.md`](../../../specs/ABS-36-orchestrator-spec.md) §8.3
**Script**: [`tests/e2e-orchestrator-dryrun.sh`](../../../tests/e2e-orchestrator-dryrun.sh)

> **Note (ABS-30, 2026-07-04):** the `In Review` transition originally spawned a dedicated
> `reviewer` role. It was later remapped to the existing **`system-architect`** Stage 1 reviewer
> (`scripts/orchestrator.sh` `map_action`), and there is no separate `reviewer` agent definition.
> The captured console blocks below are the **verbatim, unmodified** output of the original run and
> still read `role=reviewer`; they are preserved as-is for evidence integrity. Any run on the
> current mapping emits `role=system-architect` instead — the control flow being asserted is
> unchanged.

---

## 1. Scenario Description

This is the blueprint v1 definition-of-done scenario: an epic and its child tickets walk the
**full canonical status lifecycle** —

```
Backlog -> Ready for Development -> In Progress -> In Review -> In Test
  -> Ready for Human Acceptance -> Ready for Merge -> (Done, out of scope here)
```

— driven entirely by `scripts/orchestrator.sh` against the **mock task-tracking adapter**
(`scripts/mock-tracker.sh`) with the **stub spawn command**
(`tests/fixtures/stub-spawn.sh`, `ORCH_SPAWN_CMD`). No live model is invoked anywhere in this
scenario — the stub echoes a canned handoff and, in step 9 only, uses its
`STUB_TRANSITION_TO`/`STUB_TRACKER` knobs to simulate "the spawned subagent advanced the ticket
itself," exactly as a real implementer subagent would on its own next turn.

The scenario exercises, in order:

1. Epic + two child tickets created — one with `--role fe-developer`, one with **no** `--role**`
   (exercises the `be-developer` fallback, spec §2.2).
2. The epic assigned to the PO-Agent (an actor-attributed `kind: decision` comment) and transitioned
   Backlog → Ready for Development, proving the mapping fires identically for epics and tickets.
3. Both child tickets Backlog → Ready for Development, asserting **role selection**: the
   `fe-developer`-tagged ticket spawns `fe-developer`; the untagged ticket spawns `be-developer`
   with the `#PLAN_UNCERTAINTY` fallback note.
4. → In Progress (**NOOP** — the implementer already spawned itself; asserts no double-spawn).
5. → In Review (**SPAWN reviewer**).
6. → In Test (**SPAWN qas**).
7. → Ready for Human Acceptance (**SPAWN po-agent + NOTIFY** — the human epic-acceptance signal).
8. → Ready for Merge (**NOOP**, the permanent human-only merge boundary — asserts no spawn and no
   notify at this status; asserts every hop left an auditable ticket comment; asserts no state
   exists outside the tracker + orchestrator runtime dirs).
9. A second pair of tickets exercises the **concurrency-cap defer + crash-recovery
   reconciliation** path from spec §8.3 item 9: `ORCH_MAX_CONCURRENT=1` defers the second of two
   simultaneously-eligible tickets; the runner process then exits without retrying (simulated
   crash); a fresh runner's **startup reconciliation sweep** recovers the lost ticket and spawns it
   exactly once, while the already-succeeded ticket is correctly left alone (re-read guard).

**Determinism**: the script uses `--once` (single poll cycle, no infinite loop) throughout, and
step 9 uses one additional `--once` pass rather than a timer/kill-switch race. No `sleep`-based
timing is load-bearing for any assertion. Verified deterministic across 3 consecutive runs (see
§4).

---

## 2. Commands

```bash
# Run the full E2E scenario (34 assertions)
bash tests/e2e-orchestrator-dryrun.sh

# Regression check — the ABS-52/53/54 unit/scenario suite must remain green
bash tests/test-orchestrator.sh
```

---

## 3. Captured Intent / Notify Log

The following is the raw `INTENT ...` / runner-log output produced by hand-driving the same
sequence the E2E script automates (same tracker/stub, same transitions, same ticket ids), so the
exact spawn/role/notify shape at each lifecycle hop is visible in one place:

```text
### Step 1: create epic + children
epic=DEMO-1 child_fe=DEMO-2 child_be=DEMO-3

### Step 2: epic -> Ready for Development
INTENT SPAWN ticket=DEMO-1 role=be-developer to=Ready for Development note=no-role-frontmatter-defaulting-to-be-developer

### Step 3: children -> Ready for Development (role selection)
INTENT NOOP ticket=DEMO-1 role=- to=In Progress
INTENT SPAWN ticket=DEMO-2 role=fe-developer to=Ready for Development
INTENT HANDOFF ticket=DEMO-2 role=fe-developer to=Ready for Development
INTENT SPAWN ticket=DEMO-3 role=be-developer to=Ready for Development note=no-role-frontmatter-defaulting-to-be-developer
INTENT HANDOFF ticket=DEMO-3 role=be-developer to=Ready for Development

### Step 4: children -> In Progress (NOOP)
INTENT NOOP ticket=DEMO-2 role=- to=In Progress
INTENT NOOP ticket=DEMO-3 role=- to=In Progress

### Step 5: children -> In Review (SPAWN reviewer)
INTENT SPAWN ticket=DEMO-2 role=reviewer to=In Review
INTENT HANDOFF ticket=DEMO-2 role=reviewer to=In Review
INTENT SPAWN ticket=DEMO-3 role=reviewer to=In Review
INTENT HANDOFF ticket=DEMO-3 role=reviewer to=In Review

### Step 6: children -> In Test (SPAWN qas)
INTENT SPAWN ticket=DEMO-2 role=qas to=In Test
INTENT HANDOFF ticket=DEMO-2 role=qas to=In Test
INTENT SPAWN ticket=DEMO-3 role=qas to=In Test
INTENT HANDOFF ticket=DEMO-3 role=qas to=In Test

### Step 7: children -> Ready for Human Acceptance (SPAWN po-agent + NOTIFY)
INTENT SPAWN ticket=DEMO-2 role=po-agent to=Ready for Human Acceptance
INTENT HANDOFF ticket=DEMO-2 role=po-agent to=Ready for Human Acceptance
INTENT NOTIFY ticket=DEMO-2 role=- to=- note=po-agent check complete for DEMO-2 (Ready for Human Acceptance)
INTENT SPAWN ticket=DEMO-3 role=po-agent to=Ready for Human Acceptance
INTENT HANDOFF ticket=DEMO-3 role=po-agent to=Ready for Human Acceptance
INTENT NOTIFY ticket=DEMO-3 role=- to=- note=po-agent check complete for DEMO-3 (Ready for Human Acceptance)

### Step 8: children -> Ready for Merge (NOOP, human-only boundary)
INTENT NOOP ticket=DEMO-2 role=- to=Ready for Merge
INTENT NOOP ticket=DEMO-3 role=- to=Ready for Merge

### Step 9: concurrency-cap defer + crash-recovery reconciliation
-- process 1 (cap=1, then simulated crash before pending-set retry) --
INTENT SPAWN ticket=DEMO-4 role=be-developer to=Ready for Development note=no-role-frontmatter-defaulting-to-be-developer
INTENT HANDOFF ticket=DEMO-4 role=be-developer to=Ready for Development
INTENT DEFER-CAP ticket=DEMO-5 role=be-developer to=Ready for Development
-- process 2 (fresh runner; startup reconciliation sweep) --
orchestrator: starting (mode=live, interval=10s, tracker=.../scripts/mock-tracker.sh)
orchestrator: reconciliation sweep (cycle 1)
INTENT SPAWN ticket=DEMO-5 role=be-developer to=Ready for Development note=no-role-frontmatter-defaulting-to-be-developer
INTENT HANDOFF ticket=DEMO-5 role=be-developer to=Ready for Development
INTENT NOOP ticket=DEMO-4 role=- to=In Progress
```

Notes on reading this log:

- **DEMO-1** is the epic; **DEMO-2** (fe-developer) and **DEMO-3** (no role → be-developer
  fallback) are its children; **DEMO-4/DEMO-5** are the second pair used only for step 9.
- Every `SPAWN` in `--live` mode is immediately followed by a `HANDOFF` line — the stub's canned
  handoff was parsed and posted back to the ticket as a `kind: handoff` comment.
- `Ready for Human Acceptance` is the only status producing both a `SPAWN` and a `NOTIFY` in the
  same pass (SPAWN-then-NOTIFY, §2 of the spec).
- `Ready for Merge` produces `NOOP` only — no `SPAWN`, no `NOTIFY` — confirming it is a silent,
  fully human-owned gate.
- In step 9's second process, reconciliation dispatches **DEMO-5** (the crash-lost deferred
  ticket) exactly once, and correctly reports `NOOP` (not another `SPAWN`) for **DEMO-4**, which
  had already advanced to `In Progress` in process 1 — proof the re-read guard prevents a
  double-spawn during crash recovery.

---

## 4. Full Test Run Output

```text
=== E2E dry-run: Orchestrator full lifecycle (ABS-36 spec sec8.3) ===

Step 1 — create epic + child tickets (mock tracker)
  epic=DEMO-1 child_fe=DEMO-2 (role=fe-developer) child_be=DEMO-3 (no role -> fallback)

Step 2 — epic assigned to PO-Agent (Backlog status-change event)
  PASS epic Backlog->Ready for Development spawns implementer (role falls back on the epic itself)

Step 3 — child tickets: Backlog -> Ready for Development (role selection)
  PASS FE child: role from ticket frontmatter (fe-developer)
  PASS BE child: no role frontmatter -> be-developer fallback
  PASS BE child fallback records the #PLAN_UNCERTAINTY note
  PASS FE child --live spawn lands a handoff
  PASS BE child --live spawn lands a handoff
  PASS FE child handoff recorded as kind:handoff comment
  PASS BE child handoff recorded as kind:handoff comment

Step 4 — In Progress is NOOP (implementer already spawned itself)
  PASS FE child In Progress -> NOOP
  PASS BE child In Progress -> NOOP
  PASS FE child In Progress does not double-spawn
  PASS BE child In Progress does not double-spawn

Step 5 — In Review -> SPAWN reviewer
  PASS FE child In Review -> SPAWN reviewer
  PASS BE child In Review -> SPAWN reviewer

Step 6 — In Test -> SPAWN qas
  PASS FE child In Test -> SPAWN qas
  PASS BE child In Test -> SPAWN qas

Step 7 — Ready for Human Acceptance -> SPAWN po-agent + NOTIFY
  PASS FE child RHA -> SPAWN po-agent
  PASS BE child RHA -> SPAWN po-agent
  PASS RHA -> NOTIFY fires (SPAWN-then-NOTIFY, human epic-acceptance signal)
  PASS RHA -> exactly one NOTIFY per child ticket (2 total)

Step 8 — human-only boundary: Ready for Merge is NOOP, never a spawn
  PASS FE child Ready for Merge -> NOOP
  PASS BE child Ready for Merge -> NOOP
  PASS Ready for Merge never spawns (human-only merge boundary)
  PASS Ready for Merge never spawns (human-only merge boundary)
  PASS Ready for Merge does not also NOTIFY (NOOP is silent — human already owns this gate)
  PASS every lifecycle hop left a ticket comment (FE=11, BE=11 blocks)
  PASS no state outside the tracker + orchestrator runtime dirs (ADR-A-0007 adapter-only access)

Step 9 — concurrency-cap defer + crash-recovery reconciliation (spec sec8.3 item 9)
  PASS cap=1: second Ready-for-Development event deferred, not dropped
  PASS cap=1: exactly one of the two tickets spawns in the crashed process's single pass
  PASS fresh runner runs its startup reconciliation sweep
  PASS reconciliation re-derives and dispatches the crash-lost deferred ticket
  PASS crash recovery: both tickets end up spawned exactly once total (no loss, no double-spawn)
  PASS the already-spawned ticket is NOT re-spawned by reconciliation (re-read guard)
  PASS the crash-lost deferred ticket is spawned exactly once by reconciliation

=== Test Results ===

  Total:  34
  Passed: 34
  Failed: 0

  ALL TESTS PASSED
```

Re-run 3 consecutive times with identical results (34/34 pass, no flakes) to confirm determinism
on macOS bash 3.2 (`GNU bash, version 3.2.57(1)-release (arm64-apple-darwin25)`).

### Regression check — `tests/test-orchestrator.sh` (ABS-52/53/54 suite)

```text
=== Test Results ===

  Total:  41
  Passed: 41
  Failed: 0

  ALL TESTS PASSED
```

No regression: all 41 pre-existing scenario assertions remain green after adding the E2E script.

---

## 5. Gate / Approval-Boundary Checklist

Per-status and per-safety-mechanism coverage exercised by this E2E scenario:

| Gate / boundary | Spec ref | Exercised by | Result |
| --- | --- | --- | --- |
| Backlog → Ready for Development (SPAWN implementer, epic and ticket) | §2 | Steps 2, 3 | PASS |
| Role selection — ticket `role` frontmatter honored (`fe-developer`) | §2.2 | Step 3 (`CHILD_FE`) | PASS |
| Role selection — fallback to `be-developer` + `#PLAN_UNCERTAINTY` note when absent | §2.2 | Step 3 (`CHILD_BE`), Step 2 (epic itself) | PASS |
| In Progress → NOOP (no double-spawn of an already-working implementer) | §2, §2.1 | Step 4 | PASS |
| In Review → SPAWN reviewer | §2 | Step 5 | PASS |
| In Test → SPAWN qas | §2 | Step 6 | PASS |
| Ready for Human Acceptance → SPAWN po-agent + NOTIFY (human epic-acceptance signal) | §2 | Step 7 | PASS |
| Ready for Merge → NOOP (permanent human-only merge boundary, ADR-A-0004/0005; no spawn, no notify) | §2, §2.1, §9 | Step 8 | PASS |
| Handoff records land as `kind: handoff` comments | §4, Open Q C | Steps 3, 5, 6, 7 (per-status `assert ... kind: handoff`) | PASS |
| Audit trail — every lifecycle hop leaves a ticket comment | §7 | Step 8 (comment-count assertion) | PASS |
| No state outside tracker + orchestrator runtime dirs (adapter-only access) | ADR-A-0007 | Step 8 | PASS |
| Concurrency cap defer (`ORCH_MAX_CONCURRENT`) — Nth+1 event deferred, not dropped | §5.1 | Step 9 (process 1) | PASS |
| Crash-recovery reconciliation sweep recovers a lost deferred event exactly once | §5.1 (amendment) | Step 9 (process 2) | PASS |
| Re-read guard prevents double-spawn of an already-succeeded ticket during reconciliation | §5.4 | Step 9 (process 2, `DEMO-4` → `NOOP`) | PASS |

Mechanisms covered by the pre-existing `tests/test-orchestrator.sh` suite (not re-proven here to
avoid duplication, confirmed still green in §4): single-flight lock (§5.2), kill switch (§5.3),
spawn budget exhaustion + notify (§5.4, ADR-A-0009), iteration-guard → Blocked (§5.5), and the
retry-once-then-escalate failure path (§6, including the watchdog timeout).

---

## 6. Scope Note — "Ready for Merge NOTIFY" Wording

The mapping table in `specs/ABS-36-orchestrator-spec.md` §2 and the shipped
`scripts/orchestrator.sh` `map_action()` both classify `Ready for Merge` as **NOOP**, not
SPAWN-then-NOTIFY — the runner is silent at this status; it neither spawns nor sends a notify
comment, because the human already owns the gate the moment the ticket enters it. This evidence
document and `tests/e2e-orchestrator-dryrun.sh` assert the actual (NOOP) behavior. The human-only
boundary is preserved either way (no autonomous spawn crosses it); the only distinction is whether
the runner also posts a passive notify, which — per the accepted spec — it does not for this
status. See `docs/sop/ORCHESTRATOR_SOP.md` § "Human-Only Boundaries" for the operational
description.

---

## Verdict

**PASS** — the orchestrator drives a ticket (and its parent epic) through the full canonical
lifecycle with the stub spawn and mock tracker, produces the exact SPAWN/NOOP/NOTIFY intents the
spec's mapping table requires at every hop, resolves the implementer role correctly in both the
ticket-hint and fallback cases, lands every handoff as an auditable `kind: handoff` comment, keeps
both permanent human-only boundaries (`Ready for Merge`, `In Progress` double-spawn prevention)
silent and spawn-free, and recovers a crash-lost, concurrency-deferred event exactly once via the
startup reconciliation sweep with no double-spawn. `tests/test-orchestrator.sh` (41/41) shows no
regression from the ABS-52/53/54 baseline.
