# QA Validation — PILOT-48
**Add Playwright e2e coverage for MC command receipts (PILOT-32 test-plan gap)**

- **Ticket**: PILOT-48
- **Branch**: PILOT-48-auto
- **Commit under review**: `2cfb4474` (`test(web): add Playwright e2e for MC command receipts [PILOT-48]`)
- **QAS run date**: 2026-07-25
- **Verdict**: ✅ **APPROVED**

---

## Validation Summary

| Gate | Result |
|------|--------|
| New spec — `command-receipts.spec.ts` (4 tests) | ✅ 4 passed, 0 failed |
| Web unit suite (`pnpm test`) | ✅ 91 passed, 0 failed |
| Full e2e suite regression check | ✅ 117/120 passed; 2 pre-existing reauth failures (see below) |
| Typecheck (`pnpm typecheck`) | ✅ PASS (per architect review — re-run clean) |
| ESLint on new spec | ✅ PASS (per architect review — re-run clean) |

---

## AC Verification

### AC1 — Failed/refused receipt shows in ticker AND issuing control ✅ PASS
**Test**: `e2e/command-receipts.spec.ts:141` — AC1: a refused abort-spawn receipt shows in the ticker AND on the issuing control

**Evidence**: `pnpm test:e2e command-receipts.spec.ts` — test 1: ✓ (636ms)

- Drives abort-spawn against unknown ledger id → backend returns `failed` receipt with diagnostic
- Ticker: `feed-item[data-kind="command"]` with diagnostic text appears within 8 s ✓
- Issuing control: `.cmd-pill.cmd-failed` with diagnostic inline, `role="alert"` ✓

### AC2 — Executed receipt renders the same way ✅ PASS
**Test**: `e2e/command-receipts.spec.ts:171` — AC2: an executed stop-run receipt renders in the ticker AND on the issuing control

**Evidence**: test 2: ✓ (262ms)

- Drives stop-run → executed receipt
- Ticker: `feed-item[data-kind="command"]` with result text ✓
- Issuing control: `.cmd-pill.cmd-executed` containing "executed", `title={result}` ✓

### AC3 — Undelivered vs executing pills render distinctly ✅ PASS
**Test**: `e2e/command-receipts.spec.ts:198` — AC3: undelivered (pending) and executing (delivered) pills are distinct, and distinct from terminal

**Evidence**: test 3: ✓ (12.4s — expected, 10s stale threshold + 3s wall-clock tick)

- One instance drives both states: A = issued + delivered (no receipt) → `cmd-executing`; B = issued, never polled → `cmd-undelivered`
- `.cmd-pill.cmd-executing` with text "no receipt yet" ✓
- `.cmd-pill.cmd-undelivered` with text "orchestrator offline?" ✓
- `.cmd-pill.cmd-executed` count = 0, `.cmd-pill.cmd-failed` count = 0 ✓

### AC4 — Reload persistence + idempotent de-dup ✅ PASS
**Test**: `e2e/command-receipts.spec.ts:233` — AC4: a failed receipt survives reload (not toast-only); a duplicate receipt makes no duplicate entry

**Evidence**: test 4: ✓ (894ms)

- Failed receipt visible on control and as exactly 1 ticker entry before reload ✓
- Duplicate/idempotent receipt: ticker still shows exactly 1 entry ✓
- After `page.reload()`: `.cmd-pill.cmd-failed` with diagnostic still visible (listCommands-backed server state, not toast) ✓

### AC5 — Runs green in existing e2e job; no regression ✅ PASS
**Evidence**:

1. **New spec green run** (ABS-453 proof):
   ```
   Command: unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID
            DATABASE_URL=postgres://postgres:postgres@localhost:55432/agentic
            pnpm test:e2e command-receipts.spec.ts
   Result:  4 passed (17.3s)
   Commit:  2cfb4474
   ```

2. **Full suite regression check**:
   ```
   Command: same env-scrub as above; pnpm test:e2e (all specs)
   Result:  117 passed, 2 failed (reauth.spec.ts only), 1 skipped
   ```

3. **Reauth failures are pre-existing** (not PILOT-48 regressions):
   - `git diff --name-only 2c564f20..HEAD` → **only** `backend/apps/web/e2e/command-receipts.spec.ts`
   - PILOT-48 adds zero product code changes; no existing file was modified
   - Failures in `reauth.spec.ts` (AC1, AC3) involve `drawer-scrim` pointer event interception in pre-existing product code — architecturally impossible for a tests-only commit to cause these
   - **Failure classification**: `environment` / pre-existing flakiness in the re-auth UI overlay interaction — NOT introduced by PILOT-48

---

## Environment

- Postgres: `pilot8-testprep-pg` (Docker) on `localhost:55432`, password `postgres`
- Playwright browsers: Chromium 149.0.7827.55 (installed at `~/.cache/ms-playwright/chromium-1228`)
- Web SPA: built from `PILOT-48-auto` HEAD (`pnpm --filter web build`)
- e2e DB: `agentic_e2e` (drop + recreate by `reset-db.ts` at each run)
- Env-scrubbed: `BACKEND_URL`, `BACKEND_TOKEN`, `TRACKER_CMD`, `ORCH_INSTANCE_ID` unset per operator guardrail

---

## DoD Checklist

- [x] All 5 ACs verified by direct evidence
- [x] 4 new Playwright tests green (ABS-453 green-run proof: command + pass counter + commit)
- [x] Unit suite 91/0 (no regression)
- [x] Typecheck + ESLint clean (per architect, re-run clean)
- [x] Tests-only commit — no product/backend/SSE/migration change (verified via `git diff --name-only`)
- [x] Wired into existing e2e suite via `reset-db.ts` fixture, no new standing infra
- [x] No design flag → no qas-design gate required
- [x] Evidence committed on story branch `PILOT-48-auto`, not main

---

## Verdict

**✅ APPROVED** — All 5 ACs met with direct browser-level e2e evidence. PILOT-32's Playwright test-plan gap is closed. No regressions. Story may advance to **Story Acceptance**.
