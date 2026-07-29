# QA Validation — ABS-345: Bitbucket ForgeProvider + PR Mirror

- **Ticket**: ABS-345 (ABS-230 S1) — parent epic ABS-230 Phase 2
- **Branch / commit under test**: `ABS-345-auto` @ `266263c`
- **Gate**: In Test (QAS) — **Verdict: APPROVED**
- **Flags**: `security` (no `design` flag) → exit target `Story Acceptance`
- **Date**: 2026-07-17

## Environment

- node v26.3.1, pnpm 11.12.0
- Postgres 16 (docker `backend-db-1`, `postgres://postgres:postgres@localhost:5432/agentic`)
- Integration tests run against real Postgres in isolated schemas (none skipped)

## Static validation

| Check | Command | Result |
|-------|---------|--------|
| Typecheck (4 projects) | `pnpm -r typecheck` | **PASS** |
| Lint | `pnpm lint` (eslint .) | **PASS** (clean) |

## Test evidence

| Suite | Result |
|-------|--------|
| `@agentic-backend/forge` (provider/mirror/webhook) | **20/20 PASS** (real DB, 0 skipped) |
| `apps/server` `forge-routes.test.ts` | **5/5 PASS** |

## Acceptance-criteria verification (independently re-run, not just handoff claim)

| AC | Requirement | Evidence | Verdict |
|----|-------------|----------|---------|
| AC1 | `ForgeProvider` interface (`getPullRequest`/`listPullRequestsForBranch`/`getMergeStatus`/`merge`); Bitbucket conformance | `provider.test.ts` "conforms to ForgeProvider (all methods present)" + full method behavior tests | **PASS** |
| AC2 | Bitbucket webhook (created/updated/merged/declined) updates matching `pr_mirror` row; captured payload over HTTP asserts state transition | `forge-routes.test.ts` (OPEN→DECLINED over HTTP, 200) + `mirror.test.ts` (OPEN→MERGED); no-match → clean no-op | **PASS** |
| AC3 | Lazy-poll: stale row refreshed from REST (mocked), `updated_at` bumps; fresh row not polled | `mirror.test.ts` stale→refreshed (calls=1, updated_at bump) + fresh→not polled (calls=0) + absent | **PASS** |
| AC4 | Forge creds server-side/env only; none appear in `/agent/*`, `/api/*` responses or SPA bundle | `forge-routes.test.ts` sentinel scan (`SENTINEL-BB-TOKEN`/`WS`/`SECRET`) across capabilities/healthz/whoami/events/webhook responses | **PASS** |
| AC5 | Webhook verifies HMAC shared secret; 401/403 on unsigned/bad-sig; valid accepted | `webhook.test.ts` (valid/wrong-secret/tampered/missing/no-secret) + `forge-routes.test.ts` (unsigned→401 no write, bad-sig→401, no-secret→503) | **PASS** |
| AC6 | `backend/packages/forge/index.ts` entry present + imported in `apps/server/src` | `package.json exports "." → ./src/index.ts`; `routes/forge.ts` imports `@agentic-backend/forge`; `server.ts:22` import + `server.ts:345` `registerForgeRoutes(app, pool)` | **PASS** |

## Security posture (security-flagged)

- HMAC fail-closed: no secret → 503, missing/bad sig → 401; `timingSafeEqual` constant-time; signature verified over byte-exact raw body **before** `JSON.parse`.
- Webhook lives outside `/api` and `/agent` (bearer guard cannot apply) and self-authenticates via HMAC.
- Parameterized SQL throughout; ticket key regex-extracted then bound; REST paths `encodeURIComponent`'d.
- Credentials env-only, never returned/logged; sentinel non-exposure test confirms no leak.
- Independent Security Review seat already PASSED (2 non-blocking follow-ups filed).

## Pre-existing failures — NOT attributable to ABS-345 (verified)

1. **`bootstrap-promotion` ×3** — *environment*. Whoami returns 403≠200 because the live
   `backend-backend-1` dev container has seeded the shared `public` schema of the `agentic`
   DB; the test's `search_path=<schema>,public` fallback reads that residue. Test file is
   byte-identical to the parent commit (`git diff 266263c~1 266263c` empty); no ABS-345 file
   touches auth/token/dev-boot. Escalated as environment (does not block ABS-345, not routed to
   implementer).
2. **core `workflow.test.ts`** — *profile/parser drift*. `profiles/neutral/adapters/statuses.yaml`
   line 487 carries a `terminal:` field the core `workflow.ts` parser rejects
   ("unknown status field"). File is entirely outside the ABS-345 diff. Pre-existing defect in a
   different subsystem; recommend a follow-up to teach the parser the `terminal:` field (or
   revert the profile field).

Both were flagged by the implementer, architect and security seats and confirmed here to be
independent of this change. Neither affects any ABS-345 acceptance criterion.

## Follow-ups (carried forward, non-blocking)

- MEDIUM (security-validated): `applyBitbucketWebhook` resolves work item by `key` alone but
  `work_item` is `UNIQUE(project_id, key)` — latent cross-tenant resolution in a multi-project DB;
  safe in the current single-org/single-repo deployment. Filed for BSA (Story 2/3 / Phase 4).
- LOW: Bitbucket Cloud does not natively HMAC-sign webhooks; live delivery needs a signing proxy.
  Ops runbook note.
- NEW (this gate): core `workflow.ts` parser vs neutral-profile `terminal:` drift (see above).

## Verdict

**APPROVED.** All 6 acceptance criteria PASS with genuine tests against a real Postgres;
typecheck + lint green; security ACs verified; two failing suites confirmed pre-existing and
outside the ABS-345 diff. Releasing In Test → Story Acceptance (no `design` flag).
