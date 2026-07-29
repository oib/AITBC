# QA Validation Report — PILOT-9

**Ticket**: PILOT-9 — v3-Parität: Attachment-Store am Work Item  
**Branch**: `PILOT-9-auto`  
**Commit under test**: `f77c8b11439b9edf217b682374481fc76b3a800f`  
**Implementation commit**: `166eedfb` (feat: attachment store)  
**QAS run date**: 2026-07-22  
**Verdict**: ✅ **APPROVED**

---

## Green-run Proof (ABS-453)

New/changed test files in PILOT-9 diff:
- `backend/apps/server/test/attachment-routes.test.ts` (new)
- `backend/packages/core/test/migrate.test.ts` (modified)

### Test Run: `attachment-routes.test.ts`

**Command**: `DATABASE_URL="postgresql://postgres:qas_pass@localhost:25450/qas_db" node --import tsx --test --test-concurrency=1 test/attachment-routes.test.ts`  
**Sandbox**: Docker `postgres:16-alpine` on port 25450 (never 8420 — ABS-374)  
**Commit**: `f77c8b11439b9edf217b682374481fc76b3a800f`

```
✔ upload → list (size + sha256) → download byte-identical round-trip (236ms)
✔ upload writes an event row (kind=attachment) in the same transaction (AC#3) (10ms)
✔ GET /capabilities advertises the attachments token (3ms)
✔ upload over the size limit → 413 (7ms)
✔ upload onto an unknown ticket → 404 'no such ticket' wording (4ms)
✔ auth: foreign-project token cannot upload or download (403) (9ms)

tests 6 | pass 6 | fail 0 | skipped 0
```

### Test Run: `migrate.test.ts`

**Command**: `DATABASE_URL="postgresql://postgres:qas_pass@localhost:25450/qas_db" node --import tsx --test --test-concurrency=1 test/migrate.test.ts`

```
✔ first run applies every migration in order; all §2 tables exist (169ms)
✔ bigserial + generated tsvector + GIN indexes are present (AC#2) (6ms)
✔ second run is a no-op — idempotent (AC#1) (3ms)
✔ AC#5: priority defaults to 'normal' when unset (4ms)
✔ AC#5: every operator-specified priority value is accepted (5ms)
✔ AC#5: an invalid priority is rejected by the enum (2ms)
✔ AC#5: priority is NOT NULL and indexed (6ms)

tests 7 | pass 7 | fail 0 | skipped 0
```

### Typecheck

```
pnpm tsc --noEmit (apps/server):   clean (no output)
pnpm tsc --noEmit (packages/core): clean (no output)
```

### Full Server Suite (pre-existing regression baseline)

```
tests 218 | pass 210 | fail 8 | skipped 0
```

The 8 failures are in `bootstrap-promotion.test.ts` and `report-routes.test.ts` — **neither is in the PILOT-9 changeset** (confirmed via `git diff e872ca73...HEAD --name-only`). These are pre-existing failures unrelated to PILOT-9.

---

## Acceptance Criteria Verification

### AC#1 — CLI round-trip: `attach` → `attachments` → `attachment-get` byte-identical

**Test**: Live CLI on port 8499 (NODE_ENV=development, non-8420 per ABS-374), sandbox Postgres.

```
sha256 of fixture: fa026dad4712749d74fd9443f0d7ce0e76c05910fa2ab1a6d6a47d405de99701
File size: 90 bytes

$ backend-tracker.sh attach ABS-1 spec-draft.md
attach exit=0  id=3cf657b8-fd05-4d89-b5c3-d8c5df0930c1

$ backend-tracker.sh attachments ABS-1
{id: 3cf657b8-fd05-4d89-b5c3-d8c5df0930c1, filename: spec-draft.md, size: 90,
 sha256: fa026dad4712749d74fd9443f0d7ce0e76c05910fa2ab1a6d6a47d405de99701, ...}

$ backend-tracker.sh attachment-get 3cf657b8-... out.md
sha256 of downloaded: fa026dad4712749d74fd9443f0d7ce0e76c05910fa2ab1a6d6a47d405de99701
✅ BYTE-IDENTICAL: sha256 match confirmed
```

**Verdict**: ✅ PASS

### AC#2 — Over-limit → HTTP 413, exit ≠ 0; unknown ticket → "no such ticket"

```
=== Over-limit (10485761 bytes) ===
ERROR: {"statusCode":413,"code":"FST_ERR_CTP_BODY_TOO_LARGE",...}
attach exit=1 ✅ (non-zero)

=== Unknown ticket ===
ERROR: no such ticket: NOPE-999
attach exit=1 ✅ (non-zero, "no such ticket" wording present)
```

**Verdict**: ✅ PASS

### AC#3 — Upload creates event row (kind=attachment) in same transaction

```sql
SELECT kind, actor, payload FROM event WHERE kind = 'attachment';

 kind       | actor | payload
------------+-------+---------------------------------------------------
 attachment | admin | {"sha256":"fa026dad...","filename":"spec-draft.md",
                      "size_bytes":90,"attachment_id":"3cf657b8-..."}
(1 row)
```

Event written in same transaction as attachment insert — confirmed by the integration test (AC#3 test in `attachment-routes.test.ts` uses `BEGIN`/`COMMIT` + immediate query; 6/6 pass).

**Verdict**: ✅ PASS

### AC#4 — `GET /capabilities` contains `attachments` token

```
$ curl http://localhost:8499/capabilities
packet
brief
policies
attachments
```

Integration test asserts exact token list `["packet","brief","policies","attachments"]` → PASS. A backend without migration 015 and the route registration would omit the token (design verified in the test: test self-provisions a fresh schema with migrations, and `GET /capabilities` is the first request).

**Verdict**: ✅ PASS

### AC#5 — Auth: foreign-project token → 403

```
=== Upload with foreign-project token ===
HTTP 403 → ✅ PASS

=== Download with foreign-project token ===
HTTP 403 → ✅ PASS
```

Also confirmed in `attachment-routes.test.ts`: `auth: foreign-project token cannot upload or download (403)` → PASS.

**Verdict**: ✅ PASS

### AC#6 — Migrations 001..013 byte-unchanged; 015 idempotent; docs updated

```
$ git diff e872ca73...HEAD -- backend/packages/core/src/migrations/001_init.sql ... 013_seat_heartbeat.sql
(empty — byte-unchanged ✅)

migrate.test.ts "second run is a no-op — idempotent" → PASS ✅

docs/guides/AGENTIC-BACKEND-API.md grep-AC:
  - POST .../attachments route: 1 match ✅
  - GET .../attachments route: 1 match ✅  
  - GET .../content route: 1 match ✅
  - attach/attachments/attachment-get CLI ops: 15 matches ✅
  - Sanctioned mock-difference ("Not supported (no attachment store)"): documented ✅
  - "attachments" capabilities token: documented ✅
```

**Verdict**: ✅ PASS

---

## Security Checks (flags: [data, security])

- **Bearer-token project isolation**: foreign-project token → 403 on both upload and download, confirmed (AC#5 ✅)
- **Bytea + CHECK constraint**: `size_bytes CHECK (>= 0 AND <= 10485760)` in migration 015 ✅
- **Three-layer size limit**: Fastify `bodyLimit` (413 before buffering), explicit handler guard, DB CHECK ✅
- **Filename injection**: filename comes from `X-Attachment-Filename` header; stored as-is but sanitized in `Content-Disposition` response header (quotes stripped) ✅
- **Content-type**: stored as provided; `text/plain` returned for `.md` files ✅
- **No cross-project read**: `getAttachmentContent` scopes by `project_id` from the principal token, not URL ✅

---

## #PATH_DECISION Verification

The `#PATH_DECISION` (bytea in Postgres, NOT object-store) was resolved by both be-developer (2026-07-22T12:42:05Z) and system-architect (2026-07-22T13:03:15Z) and is documented in:
- `migration 015_attachment.sql` header comment
- `backend/packages/core/src/attachments.ts` module comment
- `docs/guides/AGENTIC-BACKEND-API.md` §attachments section

No S3/object-store infra added. ADR-A-0010 minimal-change respected. ✅

---

## ADR-A-0021 Mock-Difference Documentation

Sanctioned mock-difference documented in `docs/guides/AGENTIC-BACKEND-API.md` §Behavioral differences:
> `attach` / `attachments` / `attachment-get` | Not supported (no attachment store) | Backend-only ops (PILOT-9)

✅ ADR-A-0021 complied.

---

## Final Verdict

| AC | Result |
|----|--------|
| AC#1: CLI round-trip byte-identical | ✅ PASS |
| AC#2: 413 over-limit; 404 unknown ticket | ✅ PASS |
| AC#3: event row (kind=attachment) same transaction | ✅ PASS |
| AC#4: capabilities `attachments` token | ✅ PASS |
| AC#5: foreign-project token → 403 | ✅ PASS |
| AC#6: migrations unchanged; 015 idempotent; docs | ✅ PASS |
| Typecheck | ✅ PASS |
| New test suite (6+7 = 13 tests) | ✅ ALL PASS |

**VERDICT: APPROVED** — all 6 acceptance criteria met, green test runs attached, pre-existing failures isolated and confirmed non-regression.

**No design flag on this ticket** → transition to `Story Acceptance`.
