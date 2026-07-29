# QA Validation Report — ABS-467

**Ticket**: ABS-467 — Accessibility wave: named controls, legend, non-color signifiers  
**Branch**: `ABS-467-auto`  
**HEAD**: `77f05e6c` (QA report) | Implementation: `de37fc26`  
**Epic tip (ancestor)**: `21fdb44f` (ABS-466 merge into epic/ABS-460)  
**QAS Actor**: qas  
**Date**: 2026-07-19  
**Iteration**: 2 (first run approved; branch later cleaned of ABS-451 contamination via `--onto` rebase; system-architect re-approved; second QAS run here)  
**Verdict**: ✅ APPROVED

---

## Context

This is the second QAS In Test run for ABS-467. The first run (commit `c671d0f9` QA report, commit `523e8f32` impl) approved the ticket, but:
1. RTE bounced at Merging due to a 3-file rebase conflict with ABS-466 (HomeView.tsx, Inbox.tsx, styles.css).
2. be-developer resolved the conflict (commits `2ef4cdcb` + `416824d6`).
3. An accidental ABS-451 contamination was introduced during the rebase fix.
4. System-architect prescribed a `git rebase --onto 21fdb44f 8c28a625` peel-off to remove the ABS-451 commits.
5. Branch was cleaned — now carries exactly 2 ABS-467 commits (`de37fc26` impl + `77f05e6c` prior QA report) on epic tip `21fdb44f`.
6. System-architect re-approved on the cleaned branch and transitioned to In Test.
7. This second QAS run independently re-validates the cleaned branch.

The system-architect confirmed: "the ABS-467 a11y code is byte-identical to what I already approved twice."

---

## Files Verified (10 changed vs epic tip `21fdb44f`)

| File | Change |
|------|--------|
| `backend/apps/web/e2e/a11y.spec.ts` | NEW — 5 a11y e2e tests covering AC1/AC2/AC3 |
| `backend/apps/web/package.json` | Added `@axe-core/playwright@^4.10.1` devDependency |
| `backend/apps/web/src/attentionTypes.ts` | NEW — shared TYPE_ICON/TYPE_LABEL/ATTENTION_TYPES |
| `backend/apps/web/src/components/BoardView.tsx` | Accessible names on card buttons |
| `backend/apps/web/src/components/HomeView.tsx` | `home-attention-legend` Legend rendered (with epic attn.total empty-check) |
| `backend/apps/web/src/components/Inbox.tsx` | `inbox-legend` Legend rendered; imports from attentionTypes; removed ABS-466-obsoleted `canControlOrchestrator` import |
| `backend/apps/web/src/components/Legend.tsx` | NEW — reusable legend component |
| `backend/apps/web/src/styles.css` | focus-visible, legend styles (contrast fixes deferred to ABS-475 theme.css tokens) |
| `backend/pnpm-lock.yaml` | @axe-core/playwright locked |
| `docs/agent-outputs/qa-validations/ABS-467-qa-validation.md` | Prior QA report (Iteration 1) |

---

## Acceptance Criteria Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Axe-core e2e green on Home, Board, drawer (zero serious/critical violations) | ✅ PASS | a11y.spec.ts tests 1, 2, 3 all pass |
| AC2 | Tab-only walkthrough opens card drawer + triggers transition confirm | ✅ PASS | a11y.spec.ts test 5 passes |
| AC3 | Legend visible/discoverable on Board and Home attention list | ✅ PASS | a11y.spec.ts tests 2, 4 pass; `inbox-legend` + `home-attention-legend` both verified |

---

## Validation Suite Results — Iteration 2 (commit `de37fc26` / HEAD `77f05e6c`)

### Typecheck
```
Command: pnpm --filter @agentic-backend/web typecheck (tsc --noEmit)
CWD: backend/
Result: CLEAN (exit 0)
```

### Lint
```
Command: pnpm lint (eslint .)
CWD: backend/
Result: CLEAN (exit 0)
```

### Unit Tests
```
Command: pnpm --filter @agentic-backend/web test
CWD: backend/
Result: 48 passed, 0 failed (includes ABS-475 no-raw-hex gate confirming styles.css resolution)
Duration: ~1333ms
```

### E2E a11y Spec — Green-Run Proof (ABS-453)
```
Command: npx playwright test e2e/a11y.spec.ts --project=desktop
CWD: backend/apps/web
Server: fresh (Playwright auto-started)
Database: isolated agentic_e2e (reset-db.ts recreated empty; migrations applied clean)
HEAD: 77f05e6c1acaf7ae463ae8ae0c8fe890d313496d

  ✓  1 [desktop] › e2e/a11y.spec.ts:65:1 › AC1: Home has zero serious/critical a11y violations (1.3s)
  ✓  2 [desktop] › e2e/a11y.spec.ts:73:1 › AC1: Board has zero serious/critical a11y violations; AC3 legend present (1.0s)
  ✓  3 [desktop] › e2e/a11y.spec.ts:87:1 › AC1: open ticket drawer has zero serious/critical a11y violations (1.1s)
  ✓  4 [desktop] › e2e/a11y.spec.ts:99:1 › AC3: status-color legend is discoverable on the Home attention list (751ms)
  ✓  5 [desktop] › e2e/a11y.spec.ts:106:1 › AC2: keyboard-only path board → card → drawer → transition confirm (869ms)

  5 passed, 0 failed (6.9s)
```

### E2E Full Suite (regression check)
```
Command: npx playwright test --project=desktop --project=mobile
CWD: backend/apps/web
Result: 85 passed, 1 skipped, 0 failed (desktop+mobile)
Duration: ~50.0s

No regressions. The 1 skipped is a known knowledge.spec.ts test.
```

---

## Architecture Review Confirmation

System architect approved in Stage 1 gate (re-approved on cleaned branch, `77f05e6c`):
- Pattern compliance: PASS (shared `attentionTypes.ts` + `Legend` component, reuse-first, dedups existing code)
- `@axe-core/playwright@^4.10.1` devDependency: APPROVED (MIT, dev-only, AC-prescribed; not a cost gate; no credential/secret)
- TypeScript + lint: re-verified clean by architect on cleaned branch
- RLS/auth/DB migrations: N/A (frontend-only change, ADR-A-0011 OK)
- Branch integrity: only 10 ABS-467 files in `git diff 21fdb44f ABS-467-auto --name-only`; zero ABS-451 files
- AC1/AC2/AC3: all met

---

## Notes

- Cosmetic nit (non-blocking): double blank line after Legend block in `Inbox.tsx` was **fixed** in the forward-fix commit `de37fc26`.
- Non-blocking follow-up for BSA: add a dedicated `ui/accessibility.md` pattern (gap surfaced by pattern-discovery). Does not gate acceptance.
- `ux-review-2026-07` label is a tracking label — not a `design` flag. No Design Test gate required.
- styles.css contrast fix: the `--muted`/`--accent`/`--live` darkening was correctly deferred to ABS-475 `theme.css` tokens (same values, already applied by ABS-475). styles.css has 0 raw hex; the ABS-475 no-raw-hex gate in unit tests confirmed this.

---

## Final Verdict

**APPROVED** — All 3 ACs met. Full validation suite clean (typecheck, lint, unit 48/48, e2e a11y 5/5, full e2e 85/85 + 1 skip, 0 fail). Cleaned branch carries only ABS-467 commits on epic tip. No regressions.  
Transitioning → `Story Acceptance`.
