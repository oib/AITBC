# QA Validation Report — ABS-338

**Ticket**: ABS-338 — Shadow-Befund (divergence-status): ABS-127: Backend='Backlog' vs Jira='Canceled'
**Branch**: `ABS-338-auto` | **Commit**: `ddde860`
**QAS Run**: 2026-07-17
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC-1 | Ursache analysiert (Backend-Bug vs Mirror-Bug vs erwartete Modell-Lücke) | ✅ PASS | Genuine canonical model gap confirmed: `grep -in cancel profiles/neutral/adapters/statuses.yaml` → 0 matches before change. Not a mirror bug, not an API bug. Two consumers broke: shadow mirror emitted `unbekannter Jira-Status 'Canceled' — skip` and runner STUCK-DETECT fired on ABS-127 (sweeps=3). |
| AC-2 | Fix umgesetzt ODER als bewusste Modell-Entscheidung dokumentiert | ✅ PASS | Option A implemented per operator decision-of-record (2026-07-17): `Canceled` added as canonical terminal status (`terminal: true`, `next: []`) to `profiles/neutral/adapters/statuses.yaml` + `backend/packages/core/src/workflows/statuses.yaml`. Decision rationale documented in YAML comments. |
| AC-3 | Befund tritt im nächsten Audit-Zyklus nicht mehr auf | ✅ PASS | All consumers now handle `Canceled` correctly: `is_known_status("Canceled")=true`, `is_legit_rest_status("Canceled")=true` (STUCK-DETECT exemption), `status_is_terminal("Canceled")=true` (ABS-132/ABS-339 limiter exemption — no code edit needed; data-driven). Shadow mirror will recognize `Canceled` as a known canonical status → `unbekannter Jira-Status 'Canceled'` skip/divergence cleared. |

---

## Validation Runs (Independent QAS Execution)

### Orchestrator Test Suite (`tests/test-orchestrator.sh`)
```
Run 1: Total: 1157, Passed: 1157, Failed: 0 (exit code 0)
Run 2: Total: 1157, Passed: 1157, Failed: 0 (exit code 0)
```
- ABS-338 test contributes 14 assertions (Part 1–4) to the 1157 total
- Part 1: status_is_terminal/is_legit_rest_status/is_known_status = true for `Canceled`, false for `In Progress` (no masking)
- Part 2: ABS-132 respawn limiter EXEMPTS Canceled (nomove_count=0, escalation-budget=0)
- Part 3: STUCK-DETECT skips `Canceled` as legit rest; still fires on genuine non-terminal stall (no masking)
- Part 4: YAML shape verified (`terminal: true`, `next: []`); mirror parity `profiles/` == `backend/` (byte-identical)

### Backend TypeScript Tests (`node --import tsx --test`)
```
workflow.test.ts + board.test.ts: 32 pass, 0 fail, 1 skip (Postgres-gated)
```
- AC#1: `all.statuses.length === 27` ✅ (was 26 before ABS-338)
- Terminal statuses: `["Epic Done", "Canceled"]` ✅ (only two statuses with `next: []`)
- board.test.ts: Done column now `["Done", "Canceled"]` — derived structurally ✅

### Tracker Divergence Suite (`tests/test-tracker-divergence.sh`)
```
24/24 assertions passed
```

### Mirror Drift Guard (`tests/test-mirror-drift-guard.sh`)
```
5/5 passed
```

### Tracker Adapter Lint (`tests/test-tracker-adapter-lint.sh`)
```
8/8 passed — ALL TESTS PASSED
```

---

## Functional Verification

```
status_is_terminal("Canceled")   → 0 (TERMINAL=true)  ✅
is_legit_rest_status("Canceled") → 0 (LEGIT REST)     ✅ — STUCK-DETECT exempted
is_known_status("Canceled")      → 0 (KNOWN)          ✅ — no longer triggers unknown-status divergence
status_is_terminal("In Progress") → 1 (NOT TERMINAL)  ✅ — no masking
```

---

## Change Surface Verified

| File | Change | Verified |
|------|--------|---------|
| `profiles/neutral/adapters/statuses.yaml` | Added `Canceled` terminal status (19 lines) | ✅ |
| `backend/packages/core/src/workflows/statuses.yaml` | Byte-identical copy (mirror parity) | ✅ |
| `scripts/orchestrator.sh` | `Canceled` enumerated in `is_legit_rest_status`, `is_known_status`, `first_live_claim`, `propagate_start_label` (4 hunks) | ✅ |
| `tests/orchestrator.d/ABS-338-canceled-terminal-status.sh` | 14 assertions, 4 parts | ✅ |
| `backend/packages/core/test/workflow.test.ts` | 26→27 statuses; terminal list assert | ✅ |
| `backend/packages/core/test/board.test.ts` | Done group → `[Done, Canceled]` | ✅ |

**ABS-132 limiter**: no code edit needed — already data-driven via `status_is_terminal` reading `terminal: true` from file. ✅

---

## AC-3 Divergence Clearance Assessment

The root divergence (`unbekannter Jira-Status 'Canceled' — skip` in shadow mirror) is caused by `Canceled` not being a known canonical status. With this change:
- `is_known_status("Canceled")` = true → shadow mirror/audit will recognize it in the next cycle
- `is_legit_rest_status("Canceled")` = true → runner STUCK-DETECT no longer fires on ABS-127
- `status_is_terminal("Canceled")` = true → ABS-132 respawn limiter exempts it

**AC-3 is structurally satisfied.** Live confirmation awaits the next shadow-audit cycle run by the operator (the operator-local shadow scripts under `work/scratch/` are gitignored and not in-scope for this validation).

---

## Architecture Notes (System Architect, non-blocking)

The system architect noted two non-blocking items:
1. Recommend memorializing the canonical-model decision against ADR-A-0026 (operator made it a decision-of-record; not a gate condition).
2. `release_merge_token`/`clear_sessions` don't key on `Canceled` (unreachable under normal flow; not a defect).

Neither item blocks approval.

---

## Verdict

**✅ APPROVED** — All three acceptance criteria verified. Tests pass across all suites. Implementation is minimal, correct, and consistent with the operator decision-of-record (Option A). No flags (`design`, `security`, `data`) in ticket labels.

**Exit**: `In Test → Story Acceptance` (no `design` flag).
