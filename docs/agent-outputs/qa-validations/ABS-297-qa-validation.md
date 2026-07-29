# QA Validation Report — ABS-297

**Ticket**: ABS-297 — Marker duty validation: runner refuses handoff claims with no corresponding machine-readable marker  
**Branch**: `ABS-297-auto`  
**Commit verified**: `9a5f660`  
**QAS actor**: qas  
**Date**: 2026-07-15  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | `tests/orchestrator.d/ABS-297-marker-duty.sh`: po-agent JOIN-exempt claim without `JOIN-EXEMPT (triage)` marker → refused (no transition, `MARKER-MISSING` runlog, gate-results comment) | ✅ PASS | 5/5 assertions in AC1/AC4 section pass — INTENT MARKER-MISSING emitted, gate-results comment posted naming child, ticket status holds at pre-transition status, `INTENT-MARKER-MISSING` in run.log |
| AC2 | Same test: bsa handoff claiming pile empty with pending follow-up → refused likewise | ✅ PASS | 3/3 assertions in AC2/AC4 section pass — MARKER-MISSING intent emitted, gate-results comment posted, no transition applied |
| AC3 | Happy path: with markers present, handoff accepted, declared transition applies | ✅ PASS | 2/2 assertions — no MARKER-MISSING in output, parent transitioned to `In Progress` |
| AC4 | Refusal comment names exact missing marker and target ticket (grep-asserted) | ✅ PASS | AC1 path: child ticket ID named in comment; AC2 path: `kind: bsa-decision` named in comment |
| AC5 | `po-agent.md` and `bsa.md` state marker duty explicitly | ✅ PASS | `po-agent.md` lines 120–133: "Marker Duty: JOIN Exemption (ABS-297)" section, "refused — no transition applied, `MARKER-MISSING` comment posted"; `bsa.md` lines 119–123: "Marker Duty: Follow-Up Decision (ABS-297)" section, "decision + marker, or the handoff is refused" |

**Test run (independent re-run by QAS)**:

```
TOTAL=11 PASS=11 FAIL=0
```

Run command:
```bash
# Minimal harness sourcing ABS-297-marker-duty.sh directly
source tests/orchestrator.d/ABS-297-marker-duty.sh
# Confirmed in isolation with full assert_contains/assert_not_contains/assert_eq harness
```

---

## Additional Validation

| Check | Result | Detail |
|-------|--------|--------|
| `bash -n scripts/orchestrator.sh` | ✅ PASS | "SYNTAX OK" |
| Kill-switch `ORCH_VERIFY_MARKERS` | ✅ Present | Line 1565 default-on; line 2628 and 2648 guard both checks |
| ABS-255 precedent (ADR-A-0024) | ✅ Honoured | `record_marker_missing()` mirrors `record_misreport()` exactly: refuses transition, posts gate-results comment, emits intent line, back-transitions with `actor=role` so rework_count increments natively |
| Table-driven off existing printers | ✅ Confirmed | `handoff_claims_join_exempt()` calls `join_exempt_marker()` (line 2547); `child_join_exempt()` also uses it (line 3370); `epic_has_unprocessed_followups()` uses existing follow-up/bsa-decision counting |
| Commit exists on branch | ✅ Confirmed | `9a5f660 feat(orchestrator): refuse handoffs claiming marker effects without the marker [ABS-297]` |
| Files changed (4): | ✅ All present | `scripts/orchestrator.sh`, `.claude/agents/po-agent.md`, `.claude/agents/bsa.md`, `tests/orchestrator.d/ABS-297-marker-duty.sh` |

---

## Ticket Flags Check (exit routing)

Ticket labels: `[model:sonnet, orchestrator-ready]` — no `design` flag.  
→ Exit to **Story Acceptance** (not Design Test).

---

## Final Verdict

**APPROVED** — all 5 acceptance criteria met, 11/11 tests pass, `bash -n` clean, ADR-A-0024 precedent honoured, kill-switch present, SOP language explicit in both agent definitions.

Handoff to: **Story Acceptance**
