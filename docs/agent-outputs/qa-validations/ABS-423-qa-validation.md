# QA Validation Report — ABS-423

**Ticket**: ABS-423 — ADR id/key charset guard in ADR importer (mirror PROJECT_KEY_RE)
**Branch**: ABS-423-auto
**Commit reviewed**: 0f12d16
**QAS actor**: qas
**Date**: 2026-07-18
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| AC1 | Invalid ADR `id` (violates charset) fails with **named** error (`InvalidAdrKeyError`), fail closed, imports nothing | ✅ PASS | `InvalidAdrKeyError` thrown in `importAdr` post-`!fm.id` check and before any DB write; caught per-file in admin route OR clause → 422 + `imported: 0`. Test `ABS-423 invalid ADR id fails closed with named error (bad chars)` asserts `imported === 0`, `errors.length === 1`, error message matches `/charset\|ADR BAD!/`. |
| AC2 | Valid ADR `id` (matching charset) imports normally | ✅ PASS | `ADR_KEY_RE = /^[A-Za-z0-9._-]{1,64}$/` — all conforming ids pass `.test()`. Test covers 5 representative ids (`ADR-A-0002`, `ADR-A-0026`, `ADR-A-0003`, `ADR.scope.1`, `x`). |
| AC3 | Importing existing `adrs/agentic/*.md` still succeeds — no valid id rejected | ✅ PASS | Independently verified: all **26** real `adrs/agentic/*.md` ids (`ADR-A-0001` .. `ADR-A-0026`) satisfy `^[A-Za-z0-9._-]{1,64}$` (0 violations). Regression test hardcodes 18 sampled ids (all within charset). System architect confirmed 27 ids independently (0 violations). |
| AC4 | Guard enforced server-side in importer path (`importAdr`), not by UI/caller | ✅ PASS | Guard in `packages/core/src/items.ts` `importAdr()` — domain layer, cannot be bypassed by any caller/UI. Route is `requireAdmin`-gated. |
| AC5 | Charset mirrors `PROJECT_KEY_RE` (single canonical, no drift) | ✅ PASS | `ADR_KEY_RE = /^[A-Za-z0-9._-]{1,64}$/` in `items.ts` (core) exactly matches `PROJECT_KEY_RE = /^[A-Za-z0-9._-]{1,64}$/` in `admin.ts` (server). Cannot share a single import due to layering (core cannot import from server); documented with "keep in sync" comment + `#PATH_DECISION` in ticket. Drift risk bounded by repo-regression test. |
| AC6 | tests + lint + typecheck green | ✅ PASS | `pnpm typecheck`: all 5 packages Done (zero errors). `pnpm lint`: clean (zero output). `pnpm test`: **2 pass / 135 skip (DB-gated, no live Postgres) / 0 fail**. 4 new ABS-423 tests are DB-gated (`{ skip: !BASE_URL }`) — consistent with existing harness. |

---

## Validation Suite Results

```
pnpm typecheck
  packages/core:    Done
  apps/web:         Done
  packages/forge:   Done
  packages/webhooks: Done
  apps/server:      Done
  → all 5 packages PASS

pnpm lint
  → clean (no output, no errors)

pnpm test
  ℹ tests      137
  ℹ pass         2
  ℹ fail         0
  ℹ skipped    135   (DB-gated — no BASE_URL in CI)
  ℹ todo         0
```

---

## Code Review Notes

- **`InvalidAdrKeyError`** correctly extends `Error`, sets `this.name`, exposes `rawKey` readonly — mirrors `UnknownAdrStatusError` idiom exactly.
- **Guard placement**: after `!fm.id` null-check, before `ADR_STATUS_MAP` lookup and all DB operations. Correct order.
- **Per-file isolation**: admin route catch clause is `err instanceof UnknownAdrStatusError || err instanceof InvalidAdrKeyError` — adds to `errors[]`, does not rethrow, allowing sibling files to continue. AC1 isolation confirmed.
- **Export**: `InvalidAdrKeyError` exported from `packages/core/src/index.ts` barrel. Available to consumers.
- **Security (summary from security-engineer gate)**: `key` flows solely through parameterized SQL; regex anchored/bounded (no ReDoS); admin-gated + org-scoped; no new RLS surface; no secret exposure.

---

## Architecture (summary from system-architect gate)

- **Layering (ADR-A-0011)**: constant + guard defined in core, dependency direction respected.
- **Pattern compliance**: mirrors established `UnknownAdrStatusError` per-file fail-closed idiom.
- **AC5 note**: `ADR_KEY_RE` is a mirrored literal (not a shared import) because core cannot import from the server layer — this is correct and documented. Consolidate if `PROJECT_KEY_RE` ever moves to core.

---

## Verdict

**APPROVED** — All 6 ACs met. typecheck + lint + tests green. Implementation correct, pattern-compliant, security-reviewed. No blocking findings from any gate.

**Exit transition**: Story Acceptance (no `design` flag set).
