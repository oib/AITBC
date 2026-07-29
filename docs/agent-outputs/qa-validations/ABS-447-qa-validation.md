# QA Validation Report — ABS-447

**Ticket**: ABS-447 — Cap `orch_command.reason` length (ABS-439 security follow-up)
**Branch**: ABS-447-auto
**Commit**: a6f2776
**QAS date**: 2026-07-18
**Verdict**: ✅ APPROVED

---

## Test Execution

### Integration Suite — Command Routes

```
cd backend && \
  DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" \
  node --import tsx --test --test-concurrency=1 apps/server/test/command-routes.test.ts
```

**Result**: 26/26 PASS · 0 fail · 0 skipped · 0 cancelled

`skipped 0` confirmed — `DATABASE_URL` was set; no silent-skip occurred.

### Typecheck

```
pnpm -r typecheck
```

**Result**: PASS — all 5 packages (packages/core, packages/forge, packages/webhooks, apps/web, apps/server)

### Lint

```
pnpm lint
```

**Result**: PASS — clean (no ESLint errors or warnings)

---

## Acceptance Criteria Verification

| # | Criterion | Evidence | Verdict |
|---|-----------|----------|---------|
| AC1 | Migration adds `CHECK (reason IS NULL OR char_length(reason) <= 2000)` on `orch_command`; applies cleanly; documented in `DATA_DICTIONARY.md` | `011_command_reason_length.sql` confirmed (migration number 011, next-free; 010 was taken). `DATA_DICTIONARY.md` §ABS-447 entry verified. Test "ABS-447: the DB CHECK constraint backstops an over-length reason at the column" PASS. | ✅ PASS |
| AC2 | Enqueue route rejects over-length reason with HTTP 400 before any write | Test "ABS-447: an over-length reason is rejected 400 reason_too_long and no row is written" PASS — asserts `res.statusCode===400`, `error==="reason_too_long"`, `count(*)=0` for the idempotency key. Route diff confirms check runs BEFORE the `try { enqueueCommand(...) }` block. | ✅ PASS |
| AC3 | Reason at/below cap persists verbatim (no ABS-439 regression) | Test "ABS-447: a reason exactly at the cap persists verbatim (no ABS-439 regression)" PASS — `"y".repeat(2000)` → 201, persisted value equals submitted value. ABS-439 verbatim-persist tests also still pass. | ✅ PASS |
| AC4 | Command without `reason` still succeeds — nullable/backward compatible | Test "ABS-444: the reason column is nullable — a core enqueue with no reason stores null" PASS (201 + NULL). No regression. | ✅ PASS |
| AC5 | Human-gating unchanged — agent/bearer/viewer/anon rejected before length check | All gating tests pass: "AC#2: enqueue rejects an agent token (403)", "ABS-413: enqueue rejects a bearer admin/maintainer token (403, mechanism gate)", "AC#2: enqueue rejects a read-only viewer session (403)", "AC#2: enqueue rejects an unauthenticated request (401)". Length check runs inside already-gated handler (AFTER `requireHuman`). | ✅ PASS |

---

## Implementation Verification

### Single Source of Truth
`MAX_REASON_LENGTH = 2000` exported from `@agentic-backend/core` (`packages/core/src/commands.ts`):
- Route imports and enforces it (`routes/commands.ts`)
- DB CHECK mirrors it (`011_command_reason_length.sql`: `char_length(reason) <= 2000`)
- Frontend confirm dialog mirrors it (`Orchestrators.tsx`: `REASON_MAX_LENGTH = 2000`, `maxLength={REASON_MAX_LENGTH}`)

### Reject-Before-Write (AC2)
Route code confirmed: `reason_too_long` 400 is returned before the `try { enqueueCommand(...) }` block. Test asserts `count(*)=0` for the idempotency key — no partial write.

### Consistency (trimmed-length alignment)
`enqueueCommand` normalises `args.reason?.trim() || null`, and the route checks `reason.trim().length > MAX_REASON_LENGTH` — both measure the trimmed value. Route JS `.length` ≥ pg `char_length` for astral chars, so no route-accept/DB-reject unhandled-500 path.

### Duplicate-key artifact fix
Latent duplicate `reason?: string | null` key in `EnqueueArgs` (from ABS-439/ABS-444 near-dup merge) removed — in-region, correct cleanup.

### be/fe split
Confirmed correct per system-architect gate-results: only `ConfirmDialog` in `Orchestrators.tsx` persists `orch_command.reason` (via `api.enqueueCommand`). `TicketDrawer`'s reason feeds `api.humanTransition` (transition-reason column, different field, out of scope). No missed confirm dialog.

### Cap value
2000 chars per authoritative operator DEDUP-MERGE note (supersedes body's 4096 default). Confirmed applied consistently across all three enforcement points.

---

## Pre-existing Failure (Non-Blocking)

`report-routes.test.ts` — 5 tests fail with `TypeError: Cannot read properties of undefined`. **Confirmed pre-existing**:
- `report-routes.test.ts` is NOT in commit `a6f2776`'s diff (`git show --stat a6f2776` confirms)
- be-developer and system-architect independently stash-verified this fails on pristine HEAD
- Error is entirely unrelated to reason-length logic
- **Classification**: `code` / pre-existing — not caused by ABS-447, not a bounce trigger

---

## Gates Summary

| Check | Result |
|-------|--------|
| `pnpm -r typecheck` | ✅ PASS (5 packages) |
| `pnpm lint` (ESLint) | ✅ PASS |
| command-routes integration (26 tests, incl. 3 ABS-447) | ✅ 26/26 PASS, 0 skipped |
| AC1 migration + docs | ✅ PASS |
| AC2 route 400 before write | ✅ PASS |
| AC3 verbatim persist | ✅ PASS |
| AC4 nullable backward-compat | ✅ PASS |
| AC5 human-gating unchanged | ✅ PASS |

---

## Verdict

**APPROVED** — All 5 acceptance criteria met. TypeCheck, lint, and 26/26 integration tests (0 skipped) pass on commit `a6f2776`. `orch_command.reason` cap of 2000 chars is enforced at route level (400 `reason_too_long` before write), backed by DB `CHECK` constraint (migration 011), with the confirm-dialog `maxLength` as a UX guard. Human-gating (AC5) verified unchanged. No regression to ABS-439/ABS-444 audit-landing behaviour.

**Flags**: `[data, security]` — no `design` flag. Transitioning to **Story Acceptance**.
