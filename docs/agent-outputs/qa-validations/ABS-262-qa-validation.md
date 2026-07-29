# QA Validation — ABS-262

**Ticket**: ABS-262 — Backend hardening: fail-fast on unset/default BACKEND_BOOTSTRAP_TOKEN outside dev  
**Branch**: ABS-262-auto  
**Commit validated**: f30c389  
**Validated by**: QAS  
**Date**: 2026-07-14  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | Non-dev + `BACKEND_BOOTSTRAP_TOKEN` unset → server refuses to start with explicit error naming the var | ✅ PASS | Tests: 8 cases (production, staging, unset, empty `NODE_ENV`). Live probe: `loadConfig({ NODE_ENV: 'production' })` → throws `"BACKEND_BOOTSTRAP_TOKEN is required outside dev (NODE_ENV=production)"`. Critically: `NODE_ENV=""` (what compose renders for `${NODE_ENV:-}`) also throws. |
| AC2 | Non-dev + `BACKEND_BOOTSTRAP_TOKEN` equals dev default → server refuses to start | ✅ PASS | Tests: 4 cases (same non-dev NODE_ENV loop). Live probe: throws `"BACKEND_BOOTSTRAP_TOKEN is the well-known dev default outside dev"`. Whitespace-padding bypass also closed (trim-before-compare). |
| AC3 | In dev/development, current behaviour preserved | ✅ PASS | Tests: 9 cases covering `dev`, `development`, `Development` (case-insensitive). `loadConfig({ NODE_ENV: 'development' })` → boots with convenience default `dev-bootstrap-token-change-me`. |
| AC4 | `docker-compose.yml` no longer supplies `:-dev-bootstrap-token-change-me` fallback; `.env.example` documents strong token required outside dev | ✅ PASS | Compose: `NODE_ENV: ${NODE_ENV:-}` and `BACKEND_BOOTSTRAP_TOKEN: ${BACKEND_BOOTSTRAP_TOKEN:-}` — no non-empty fallback. Mechanically guarded by `compose-env.test.ts`. `.env.example` carries explicit comment: "OUTSIDE DEV a strong, unguessable token is REQUIRED: the server refuses to boot if it is unset or still set to that dev default (ABS-262)." |
| AC5 | Unit test covering fail-fast branch (non-dev + unset/default → throws/exits non-zero) | ✅ PASS | `backend/packages/core/test/config.test.ts`: full `{dev, non-dev} × {unset, empty, dev-default, strong}` matrix. 21 new cases + 4 added in iteration 2 for `NODE_ENV=""`. Plus `compose-env.test.ts` guards the YAML layer. |

---

## Test Suite Results

```
pnpm -r test:
  packages/core: 32 pass / 0 fail / 3 skip (pre-existing DB-gated migrate tests)
  apps/server:    0 pass / 0 fail / 7 skip (pre-existing DB-gated integration tests)

pnpm typecheck: PASS (both packages/core and apps/server)
pnpm lint:      PASS (no ESLint violations)
```

---

## Validation Matrix (independently probed)

| NODE_ENV | Token | Expected | Result |
|----------|-------|----------|--------|
| `production` | unset | refuse | ✅ exit 1, error names var |
| `staging` | unset | refuse | ✅ exit 1 |
| `<unset>` | unset | refuse | ✅ exit 1 (fail-closed) |
| `""` (compose render) | unset | refuse | ✅ exit 1 (critical path) |
| `production` | `dev-bootstrap-token-change-me` | refuse | ✅ exit 1, "well-known dev default" |
| `production` | `  dev-bootstrap-token-change-me  ` (padded) | refuse | ✅ rejected (trim-before-compare) |
| `development` | unset | allow | ✅ boots with convenience default |
| `dev` | unset | allow | ✅ boots |
| `Development` | unset | allow | ✅ boots (case-insensitive) |
| `production` | strong token | allow | ✅ boots with that token |

---

## Architecture & Security Review Outcomes

**Architecture Review (Iteration 1)**: Bounced on CRITICAL — compose `NODE_ENV: ${NODE_ENV:-development}` re-introduced the vulnerability (manufactured dev env for any operator who set nothing). Fixed in commit f30c389.

**Architecture Review (Iteration 2)**: PASS — composition-level fix verified; all code-level decisions endorsed (fail-closed `NODE_ENV`, `loadConfig` placement, trim handling, test matrix).

**Security Review**: PASS — Production path (image + operator env) independently verified fail-closed. Dockerfile sets no `NODE_ENV`, so a deployed image with nothing set → unset → non-dev → refuses to boot.

---

## Non-Blocking Findings (Security Engineer — filed for follow-up, not blocking this ticket)

1. **`.env.example` ships both `NODE_ENV=development` and the dev-default token** — `cp .env.example .env` on a prod host collapses both gates. Not blocking: compose also ships `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}` on a published 5432, confirming this is a dev/demo artifact; the production code path (image + operator-supplied env) is proven fail-closed. AC4 as written is met (the file clearly documents the strong-token requirement).
2. **`compose-env.test.ts` only guards `docker-compose.yml`, not `.env.example`** — a gap in mechanical defence-in-depth. Accepted given the file's context.
3. **Non-revoked dev-default token in DB** (DB seeded in dev → token survives promotion) — correctly deferred to ABS-235/S3 (token model changes out of scope here). QAS confirms this is pre-existing and correctly scoped out.
4. **Compose `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}`** — default postgres password on published 5432. Not in scope for this ticket (no AC about it). Follow-up for BSA/PO.

---

## Definition of Done

| Item | Status |
|------|--------|
| Fail-fast unit test green | ✅ 32 pass / 0 fail |
| lint/typecheck green | ✅ both PASS |
| Aligns with ADR-A-0004 #4 (human-provisioned scoped credentials) | ✅ token is operator-provisioned; no auto-generation |

---

## QAS Independent Verification

- Verified the `loadConfig` seam is the **only** place `BACKEND_BOOTSTRAP_TOKEN` is consumed (no bypass path).
- Verified `isDevEnv()` normalizes to lowercase and tests only `"dev"` / `"development"`.
- Verified `NODE_ENV` is normalized once in `loadConfig` and passed to `isDevEnv()` (no drift risk between gate and error message).
- Verified compose supplies `${NODE_ENV:-}` (empty fallback), which renders as `""` — the test matrix covers this exact value.
- Verified Dockerfile carries no baked-in `NODE_ENV`, so the production image leaves the gate decision entirely to operator-supplied env.

---

## Verdict

**✅ APPROVED — All 5 ACs met. Gates green. Transitioning to Story Acceptance.**

No `design` flag on ticket → exit target is **Story Acceptance** (not Design Test).
