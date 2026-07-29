# QA Validation — ABS-350

**Ticket**: ABS-350 — `backend-forge.sh` Adapter (`pr-state` for Done-Gate)
**QAS Run Date**: 2026-07-17
**Commit Under Review**: 7dd3a71 (`feat(forge): backend-forge.sh adapter + pr-state query route [ABS-350]`)
**Branch**: ABS-350-auto (rebased onto `epic/ABS-230-phase2-ops-flaeche`)
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | `pr-state <key>` returns documented canonical output (`STATE #REF ci=CI_STATUS mergeable=BOOL`); stdout contract parseable by `orchestrator.sh:story_pr_state` | ✅ PASS | test-backend-forge.sh tests 0+1: 9 assertions PASS covering MERGED/OPEN/DECLINED/NONE states; `story_pr_state()` in orchestrator.sh confirmed to consume `$1` (STATE) and `$2` (REF) via `awk` — contract aligned |
| AC2 | `pr-state <missing-key>` exits non-zero and writes key name to stderr | ✅ PASS | test-backend-forge.sh test 2: 2 assertions PASS — 404 → exit 1, stderr contains key `MISSING-1` |
| AC3 | Adapter reads env vars per `backend-tracker.sh` §7 convention; dies with stderr on unset `BACKEND_TOKEN`/`TRACKER_PROJECT` | ✅ PASS | test-backend-forge.sh test 3: 4 assertions PASS — both env vars tested individually; `require_env()` implementation confirmed in script |
| AC4 | `backend-forge.sh` wired into adapter-lint suite; lint run passes | ✅ PASS | test-tracker-adapter-lint.sh §6 (lines added in commit): 5 forge-specific assertions PASS — presence, bash syntax, pr-state dispatch, executable bit, conformance suite registration; 13/13 total PASS |
| AC5 | `scripts/backend-forge.sh` exists, is executable, named in ≥1 test assertion | ✅ PASS | `-rwxr-xr-x` confirmed; test 0's `assert_contains "$ADAPTER" "backend-forge.sh"` is the naming assertion |

---

## Test Suite Results

```
bash tests/test-backend-forge.sh
→ 21/21 PASS (Test 0: AC5 ×4, Test 1: AC1 ×9, Test 2: AC2 ×2, Test 3: AC3 ×4, Test 4: auth ×2)

bash tests/test-tracker-adapter-lint.sh
→ 13/13 PASS (§1–§5: existing adapter checks ×8, §6: forge adapter ×5)

pnpm -C backend typecheck
→ 4/4 workspaces Done (packages/core, packages/forge, apps/server, apps/web)

pnpm lint (backend/)
→ ESLint exit 0 (no issues)
```

---

## Security / Architecture Cross-Check

- **Token handling**: `BACKEND_TOKEN` rides in a `--config` file (not argv) — identical to `backend-tracker.sh` pattern; no credential exposure risk ✅
- **Read-only**: no merge/write capability; `GET /agent/v1/projects/:p/items/:k/pr-state` only ✅
- **Tenant isolation**: route parameterized SQL scoped to `principal.targetProjectId` (bearer-guarded); no cross-tenant leak ✅
- **ADR-A-0007**: adapter mirrors `backend-tracker.sh` surface exactly ✅
- **ADR-A-0010**: new scripts only; no edits to existing adapters or orchestrator ✅
- **ABS-66 data-flow**: `backend-forge.sh pr-state → forge pr-state → story_pr_state → done_pr_gate` confirmed ✅

---

## Flags Check

- `design` flag: **not set** → exit target is **Story Acceptance**
- `security` flag: not set (read-only adapter; architecture review confirmed clean)

---

## Final Verdict

All 5 ACs **PASS**. Test evidence independently re-run (not taken from BE gate claim):
- `test-backend-forge.sh`: 21/21 PASS
- `test-tracker-adapter-lint.sh`: 13/13 PASS
- TypeCheck: 4/4 workspaces Done
- Lint: clean

**APPROVED** — transitioning to `Story Acceptance`.
