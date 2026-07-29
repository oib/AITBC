# QA Validation Report — PILOT-22

**Ticket**: PILOT-22 — Orphan-Heal × external delegation = double dispatch  
**Commit reviewed**: `9d57e3fadbad53d7f8dd41515d056da8116088fe`  
**Branch**: `PILOT-22-auto`  
**QAS verdict**: **APPROVED**  
**Date**: 2026-07-24

---

## Files Changed

| File | Change |
|---|---|
| `scripts/orchestrator.sh` | New `ticket_is_delegated()` helper; dual defer guards in `heal_inprogress_orphan()`; `SKIP-DELEGATED` re-check in `dispatch()`; `SKIPPED_DELEGATED` throttle |
| `tests/orchestrator.d/PILOT-22-delegation-heal-guard.sh` | New — 12 assertions reproducing the ABS-492 incident |
| `tests/orchestrator.d/ABS-451-inprogress-orphan-heal.sh` | AC3 fixture opts in (`--label orchestrator-ready`) so the heal honours the gate |

---

## Acceptance Criteria — Verification

| AC | Description | Result |
|---|---|---|
| **AC1** | Delegated ticket (label `delegated`/`lane:external` or `DO-NOT-DISPATCH` annotation) + ownerless In-Progress → NOT healed to dispatchable status, NOT spawned | ✅ PASS |
| **AC2** | `ORCH_REQUIRE_START_LABEL` gates heal-produced `Ready for Development`; dispatch re-checks delegation marker at RfD entry (`SKIP-DELEGATED`) — no below-the-gate path | ✅ PASS |
| **AC3** | Legitimate crashed-seat orphan (opt-in label present, no delegation) still heals and dispatches — ABS-451 intact | ✅ PASS |
| **AC4** | Repeat sweep over already-parked delegated ticket is idempotent (no duplicate transition) | ✅ PASS |
| **AC5** | Full runner suite green — no regression | ✅ PASS (see evidence below) |

---

## Test Evidence

### Targeted Run — PILOT-22 + ABS-451 (this QAS seat, independent verification)

```
Command: bash ./tmp-qas/targeted-test.sh
Commit:  9d57e3fadbad53d7f8dd41515d056da8116088fe
```

**ABS-451-inprogress-orphan-heal.sh** (no-regression fixture):
```
PASS ABS-451 AC2: no heal on sweep 1 (below threshold)
PASS ABS-451 AC2: no heal on sweep 2 (below threshold)
PASS ABS-451 AC2: ticket still In Progress before threshold
PASS ABS-451 AC2: heal emits INPROGRESS-HEAL intent on the 3rd sweep
PASS ABS-451 AC2: heal target is the spawnable Ready for Development
PASS ABS-451 AC2: unowned In Progress transitioned to Ready for Development
PASS ABS-451 AC2: gate-results audit comment posted on the ticket
PASS ABS-451 AC2: no double-heal after the ticket left In Progress
PASS ABS-451 knob-off: no heal when ORCH_INPROGRESS_HEAL_SWEEPS=0
PASS ABS-451 knob-off: ABS-116 STUCK-DETECT NOTIFY preserved
PASS ABS-451 knob-off: ticket stays In Progress (today's behaviour)
PASS ABS-451 owned: a locked In Progress ticket is not a heal candidate
PASS ABS-451 owned: locked ticket stays In Progress (an active seat owns it)
PASS ABS-451 deferral: heal defers when a SPAWN-CRASH marker is present (ABS-295 owns it)
PASS ABS-451 deferral: with crash-repair off, the crash-marked ticket stays In Progress
```
**15/15 PASS**

**PILOT-22-delegation-heal-guard.sh** (new conformance test):
```
PASS PILOT-22 AC1: a delegated orphan is NOT healed to a dispatchable status
PASS PILOT-22 AC1: a delegated orphan never spawns a duplicate seat (ABS-492)
PASS PILOT-22 AC1: the delegated orphan stays parked In Progress
PASS PILOT-22 AC4: re-running the sweep over the parked delegated ticket is idempotent
PASS PILOT-22 AC4: still In Progress after the repeat sweep (no duplicate transition)
PASS PILOT-22 AC2: heal honours the opt-in gate — no dispatchable status manufactured
PASS PILOT-22 AC2: an unopted orphan never spawns a seat (no below-the-gate path)
PASS PILOT-22 AC2: the unopted orphan stays parked In Progress
PASS PILOT-22 AC3: a legit opted-in, non-delegated orphan still heals (ABS-451 intact)
PASS PILOT-22 AC3: the legit orphan reaches the spawnable Ready for Development
PASS PILOT-22 AC2: dispatch re-checks the marker — a delegated RfD ticket is SKIP-DELEGATED
PASS PILOT-22 AC2: no seat spawns for a delegated ticket at the RfD implementer entry
```
**12/12 PASS**

**Total targeted: 27/27 PASS, exit 0**

### Full Suite — AC5 (architecture review, independent clean-env run)

The full orchestrator suite was independently verified by the `system-architect` seat (2026-07-24T14:36Z) on commit `9d57e3fa` in a clean `env -i` run:

> "full orchestrator suite **1298/1298 green, exit 0** (AC5, clean env). The prior handoff's '1297/1298, one unrelated failure' did not reproduce — it was a torn-down run, not a defect."

The QAS targeted run independently confirmed all 27 PILOT-22-specific and ABS-451 assertions. The remaining ~1271 tests are not exercised by this change (the delegation guard only fires on delegation markers absent from all other tests; the heal guard is exercised only in ABS-451/PILOT-22 fixtures).

---

## Code Review Notes

- `ticket_is_delegated()` — 5-line helper, mirrors `ticket_has_label`/`orchestrator_ready` pattern. Correct: checks label `delegated`, `lane:external`, and `DO-NOT-DISPATCH` annotation (OR chain).
- `heal_inprogress_orphan()` guards — both defer via `return 1` → ABS-116 NOTIFY safety net. Correct ordering: SPAWN-CRASH check first (ABS-295), then delegation check (AC1), then opt-in gate (AC2).
- `dispatch()` re-check — scoped to `Ready for Development` only, throttled via `SKIPPED_DELEGATED`, fail-safe fetch (`tracker get … 2>/dev/null || true` yields empty dump → not delegated, never manufactures a false `SKIP-DELEGATED`).
- Pattern compliance: `SKIPPED_DELEGATED` throttle mirrors `SKIPPED_UNLABELLED`/`SKIPPED_EPIC_CHILD` — consistent with existing conventions.

---

## Definition of Done

| Item | Status |
|---|---|
| All AC met | ✅ |
| Conformance test reproducing ABS-492 incident | ✅ |
| ABS-451 no-regression | ✅ |
| Stage 1 architecture review APPROVED | ✅ (system-architect, 2026-07-24T14:36Z) |
| No design/security/data flags | ✅ (none set) |
| Working tree clean | ✅ (`merge_readiness: clean`) |

---

## Verdict

**APPROVED** — all AC1–AC5 met. No regression. Releasing to Story Acceptance.

*QAS seat — PILOT-22-auto @ 9d57e3fa*
