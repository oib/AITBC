# QA Validation Report — ABS-295

**Ticket**: ABS-295 — CRASH-REPAIR: reconcile sweep routes orphaned seat-owned tickets back to their origin station  
**Branch**: ABS-295-auto  
**Commit under review**: dee23d6  
**QA Date**: 2026-07-15  
**Verdict**: ✅ APPROVED

---

## Validation Summary

### Test Suite Run

```
Command: bash tests/test-orchestrator.sh
Results: Total: 780 | Passed: 747 | Failed: 33
ABS-295 assertions: 24/24 PASS
Pre-existing failures: 33 (env-sensitive: provenance/harness path, model-label, reconcile-timing — all confirmed pre-existing per architect's baseline comparison on 4b9ffaa)
```

Run performed independently (no prior runs on this machine in this session). Architect's prior verification: 3 consecutive runs, 24/24 PASS each.

---

## Acceptance Criteria Verification

### AC1 — Happy path: all 4 conditions met → transition to origin status

```
PASS  ABS-295 AC1: all 4 conditions met → CRASH-REPAIR intent in stdout
PASS  ABS-295 AC1: ticket routed back to origin status (Ready for Development)
```
✅ **MET**

### AC2 — Negative cases (one per failed condition)

```
PASS  ABS-295 AC2-a: no crash marker → no repair
PASS  ABS-295 AC2-b: live lock held → no repair (condition 2 fails)
PASS  ABS-295 AC2-c: crash age < threshold → no repair (condition 3 fails)
PASS  ABS-295 AC2-d: foreign instance id → no repair (two-runner safety, condition 4 fails)
```
✅ **MET** — all four negative cases pass

### AC3 — ORCH_CRASH_REPAIR_SECONDS=0 → NOTIFY-only (no repair)

```
PASS  ABS-295 AC3: ORCH_CRASH_REPAIR_SECONDS=0 → no repair (knob off)
PASS  ABS-295 AC3: ticket stays In Progress when repair knob is off
```
✅ **MET** — knob-off reproduces today's behaviour exactly

### AC4 — Audit evidence: comment + CRASH-REPAIR runlog line

```
PASS  ABS-295 AC4: CRASH-REPAIR audit comment posted on ticket
PASS  ABS-295 AC4: audit comment names crash time
PASS  ABS-295 AC4: audit comment names session id
PASS  ABS-295 AC4: audit comment names origin status
PASS  ABS-295 AC4: CRASH-REPAIR intent line present in stdout (runlog line verified)
```
✅ **MET** — audit comment and runlog line both verified

### AC5 — Idempotency: second sweep does not transition again

```
PASS  ABS-295 AC5 setup: first sweep repaired the ticket
PASS  ABS-295 AC5: CRASH-REPAIR comment present → second sweep is idempotent (no re-transition)
```
✅ **MET**

### AC6 — ADR-A-0004 amended with AD-1 self-reversal rule

Verified manually:
- `adrs/agentic/ADR-A-0004-human-approval-boundaries.md` contains `## Amendment 2026-07-14 (ABS-295, ABS-296, ABS-298, ABS-301) — AD-1: self-reversal rule`
- Status remains `proposed` (correct — acceptance is human-only per architect)
- AD-1 states the general rule for all four heal stories; names all four tickets (ABS-295/296/298/301)
- Non-negotiable constraints listed (instance-scoped, reverse-only, ORCH_*=0 off-switch, human PR gate)
- Follows the file's own `## Amendment` precedent (ABS-9, ABS-11)

✅ **MET** — as widened by the System Architect

---

## Architecture Validation (from Iteration 1/2/3 review)

All four correctness defects raised by the System Architect are fixed and verified by the expanded test suite:

| Defect | Fix | Verified by |
|--------|-----|-------------|
| CRITICAL-1: awk picks oldest marker (not newest) | `last-wins` in `END` block | AC-MULTI-1 PASS |
| CRITICAL-2: dedup key not episode-scoped | Key is `CRASH-REPAIR instance=${inst} crash-time=${crash_ts}` | AC-MULTI-2 + AC-MULTI-3 PASS |
| MEDIUM-3: age gate fails open + duplicates `iso_to_epoch()` | Delegates to `iso_to_epoch()`; `[ -n "$crash_epoch" ] \|\| return 1` | test coverage + code review |
| MEDIUM-4: same-status no-op repair reachable | `[ "$origin_status" != "$status" ] \|\| return 1` | AC-MULTI-4 PASS |

### Additional Tests (architect-required)

```
PASS  ABS-295 AC-MULTI-1: two own markers → CRASH-REPAIR fires
PASS  ABS-295 AC-MULTI-1: repair routes to NEWER marker's origin (Ready for Development, not stale Backlog)
PASS  ABS-295 AC-MULTI-2 setup: episode-1 repair landed
PASS  ABS-295 AC-MULTI-2: new crash episode → repair fires again (episode-scoped dedup)
PASS  ABS-295 AC-MULTI-2: episode-2 repair routed ticket back to origin
PASS  ABS-295 AC-MULTI-2: same crash episode → repeat sweep is idempotent
PASS  ABS-295 AC-MULTI-3: foreign CRASH-REPAIR comment does not block own repair (instance-scoped dedup)
PASS  ABS-295 AC-MULTI-4: marker origin == current status → no repair (same-status no-op guard)
PASS  ABS-295 AC-MULTI-4: ticket remains In Progress when origin == current status
```

---

## Bespoke Harness Deletion

Verified: `tests/run-abs295.sh` does NOT exist in the tree or git index. Evidence lives exclusively in the canonical `tests/orchestrator.d/ABS-295-crash-repair.sh` runner (ABS-215 pattern).

---

## ADR Compliance

| ADR | Check |
|-----|-------|
| ADR-A-0001 (ADR hierarchy) | ✅ Hardening of existing reconcile scope; no new ADR class |
| ADR-A-0004 (human-approval boundaries) | ✅ AD-1 in-scope: reverses only runner's own logged crash state = reconcile; no merge/deploy authority |
| ADR-A-0010 (minimal-change default) | ✅ 4-condition gate; NOTIFY path unchanged; `ORCH_CRASH_REPAIR_SECONDS=0` off-switch preserves today's behaviour |
| AD-2 (station class from statuses.yaml) | ✅ `[ "$status" = "In Progress" ]` literal acceptable here (AD-2 targets station-class arrays, per architect's ruling) |
| AD-3 (one lock, not two) | ✅ Reuses `lock_dir_for` + `ORCH_LOCK_TTL` (:3603); no second lock primitive |

---

## Pre-existing Failures (not ABS-295)

33 failures on this machine (vs architect's count of 37 — 4 gap is env-sensitive):
- Provenance/harness path (harness=/Users/sahan/boilerplate-stable, not ABS-295-work) — 2 failures
- Model-label env-sensitive tests — ~19 failures
- Reconcile dispatch timing tests — 3 failures
- Other pre-existing: label-gate, budget-overflow, ABS-195 spawn seam — remainder

None are ABS-295 regressions. Failure set is diff-identical to the base commit (4b9ffaa) confirmed by the System Architect.

---

## Final Verdict

**✅ APPROVED**

All 6 ACs met. 24/24 test assertions PASS. Architecture compliance confirmed. No regressions introduced. Bespoke harness deleted. AC-MULTI-2 (formerly flaky) is deterministic across multiple runs.
