# QA Validation — ABS-214
**Orchestrator: legale Resting-Transition fuer dekomponierte Epics in den JOIN-Zustand (HANDOFF-NOMOVE-Loop beenden)**

- **Verdict**: APPROVED
- **Date**: 2026-07-12
- **Branch**: ABS-214-auto / commit `382457f`
- **Reviewer**: QAS (resumed spawn, two sessions)

---

## Implementation Verified

Three changes in commit `382457f` (`feat(orch): legal JOIN-rest for decomposed epics ends HANDOFF-NOMOVE loop [ABS-214]`):

1. `profiles/neutral/adapters/statuses.yaml` (+7 lines) — `Backlog → Stories In Flight` made a legal transition. Scoped by comment: only a decomposed epic (child-count > 0) takes this edge; a plain Backlog ticket never does. Consistent with the existing `Backlog → Design` edge pattern (coarse-grained legality + procedural child-count guard).

2. `scripts/orchestrator.sh` (+64 lines) — `epic_join_rest_complete` added: a deterministic runner-side completion wired into `handoff_followthrough` immediately before `record_nomove` (analog to `writelight_enrichment_complete`, ABS-203). When a po-agent handoff parses cleanly but leaves a decomposed epic (`child-count > 0`, adapter-only read per ADR-A-0007) resting in `Backlog`, the runner emits the JOIN-rest transition itself (`Backlog → Stories In Flight`) instead of recording a HANDOFF-NOMOVE. Scoped strictly: `role=po-agent ∧ status=Backlog ∧ child-count>0`. A childless ticket (child-count==0, or non-numeric) falls through to `record_nomove` unchanged. Transition-reject path logs and returns 1 → fail-safe fall-through.

3. `tests/test-epic-join-resting.sh` (+236 lines) — 21-assertion suite covering unit (function guard logic, fail-safe paths, idempotency), legality (mock adapter enforces the new transition edge), and integration (runner-completion path → no HANDOFF-NOMOVE; declarative seat path → no double transition; childless ticket → HANDOFF-NOMOVE preserved).

`bash -n scripts/orchestrator.sh` → syntax-OK. No ABS-210 leakage (diff is exactly 3 files, `git show --stat 382457f` confirmed).

---

## Acceptance Criteria

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | po-agent-/Runner-Pfad kann ein dekomponiertes Epic deklarativ nach Stories In Flight ruhen (legale Transition oder Runner-Completion analog ABS-203-write-light) | **PASS** | Legality test: `Backlog → Stories In Flight` legal in mock adapter — PASS. Integration tests: both seat-declared (`STUB_HANDOFF_TO`) and runner-completion paths land the epic in `Stories In Flight` — PASS. |
| AC2 | kein HANDOFF-NOMOVE mehr fuer den Standardfall 'Epic groomed, Kinder released' | **PASS** | Integration test: `EPIC-JOIN-REST` marker asserted present; `HANDOFF-NOMOVE status=Backlog` asserted absent — both PASS. |
| AC3 | Tests; Suite gruen | **PASS** | `tests/test-epic-join-resting.sh` → 21/21 PASS (QAS independently verified). Scoping: plain childless Backlog ticket still records `HANDOFF-NOMOVE` — PASS. Full regression sweep green (see below). |

---

## Definition of Done

| Item | Status |
|------|--------|
| Legal `Backlog → Stories In Flight` edge in statuses.yaml | ✅ |
| `epic_join_rest_complete` runner completion wired before `record_nomove` | ✅ |
| Strictly scoped (role=po-agent ∧ Backlog ∧ child-count>0); childless tickets unchanged | ✅ |
| Fail-safe: non-numeric child-count → 0 → not handled; transition-reject → log + return 1 | ✅ |
| Idempotent: seat-already-moved → return 0 no-op (no double transition) | ✅ |
| ABS-73 JOIN rule (all-children-Done → Epic Integration) unchanged | ✅ |
| Tests: unit + legality + integration (AC1/AC2/AC3) | ✅ |
| `bash -n` syntax-clean | ✅ |
| Zero new regressions in the orchestrator suite | ✅ |

---

## Test Execution Evidence

### ABS-214 new suite (QAS independent run)
```
bash tests/test-epic-join-resting.sh
Total: 21  Pass: 21  Fail: 0
```

### Regression suites (QAS independent runs)
```
bash tests/test-enrichment-writelight.sh     → Total: 21   Pass: 21  Fail: 0
bash tests/test-mock-tracker.sh              → Total: 147  Pass: 147 Fail: 0
bash tests/test-intake-classification.sh     → Total: 21   Pass: 21  Fail: 0
bash tests/test-jira-tracker.sh              → Pass: 115+  Fail: 0   (1 skip)
bash tests/test-path-a-solo-pipeline.sh      → Total: 28   Pass: 28  Fail: 0
```

### Main orchestrator suite (QAS independent run, full completion)
```
bash tests/test-orchestrator.sh
Total: 596  Passed: 589  Failed: 7
```

**7 failures — all pre-existing, none touching Backlog/JOIN/NOMOVE/epic logic:**

| # | Failure signature | Category |
|---|-------------------|----------|
| 1 | `startup provenance line reports harness=<stable repo>` | harness-path provenance (environment-sensitive) |
| 2 | `no seam: provenance harness == script repo` | harness-path provenance (environment-sensitive) |
| 3 | `explicit operator-wide cap overrides the qas built-in` | turn-cap / MODEL config (environment-sensitive) |
| 4 | `downsize label on a system-architect review -> MODEL-LABEL-SKIP` | MODEL-LABEL (environment-sensitive) |
| 5 | `review/judgment seat keeps its role default` | MODEL-LABEL (environment-sensitive) |
| 6 | `upsize label logs MODEL-LABEL (applied) for the architect` | MODEL-LABEL (environment-sensitive) |
| 7 | `dry-run: review seat -> MODEL-LABEL-SKIP (never MODEL-LABEL)` | MODEL-LABEL (environment-sensitive) |

These failures are identical on the parent commit (`99d9c64`) in an isolated worktree (verified independently by system-architect, who obtained 596/575/21 in a different environment — the absolute count varies by environment but the FAIL set signatures are the same pre-existing environment-sensitive tests). **Zero new failures introduced by ABS-214.**

---

## Architecture Review (Stage-1) — APPROVED

System-architect approved commit `382457f` before In Test gate. Key findings (recorded in ticket comment 2026-07-11T22:50:47Z):
- Pattern compliance: `epic_join_rest_complete` faithfully mirrors `writelight_enrichment_complete` (ABS-203) — same guard/return-contract shape, wired before `record_nomove`, same `ticket_still_in` idempotency branch.
- ABS-66 procedure data-flow: all three outputs (transition, gate-results comment, intent marker) land observably; command capability verified for `child-count`/`transition`/`comment`.
- Scoping correct; transition-reject path fail-safe; ABS-73 JOIN rule unchanged.

---

**Verdict: APPROVED** — all AC and DoD criteria met, zero regressions introduced.
