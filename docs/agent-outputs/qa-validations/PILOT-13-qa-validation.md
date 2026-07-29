# QA Validation Report — PILOT-13

**Ticket**: PILOT-13 — Attachment download hardening: nosniff header + RFC 5987 filename encoding
**Branch**: `PILOT-13-auto`
**Commit under test**: `59912363781f74ff489529237cc9151dc4b2b66a`
**QAS run date**: 2026-07-22
**Verdict**: APPROVED

---

## Green-run Proof (ABS-453)

New/changed test files in PILOT-13 diff:
- `backend/apps/server/test/attachment-routes.test.ts` (modified — 3 new PILOT-13 test cases added)

### Test Run: `attachment-routes.test.ts`

**Command**:
```
DATABASE_URL="postgres://postgres:qas_pilot13_pass@localhost:55413/agentic"
  node --import tsx --test --test-concurrency=1 apps/server/test/attachment-routes.test.ts
```

**Sandbox**: Docker Compose project `pilot13-qas-37980`, Postgres on port `55413` (non-8420, ABS-374 compliant).
**Commit**: `59912363781f74ff489529237cc9151dc4b2b66a`

```
tests 8
pass 8
fail 0
skipped 0
duration_ms 517.390833
```

**Result: 8 passed, 0 failed**

---

## Acceptance Criteria Verification

### AC#1 — X-Content-Type-Options: nosniff on download response
**Status**: PASS

- Implementation: download handler emits .header("x-content-type-options", "nosniff") on every GET /attachments/:id/content response.
- Test: "download hardening: nosniff header + RFC 5987 non-ASCII filename, byte-identical (PILOT-13 AC#1,#2)" asserts dl.headers["x-content-type-options"] === "nosniff".
- Test result: PASS (11.07ms)

### AC#2 — Non-ASCII filename with RFC 5987 filename*=UTF-8'' + byte-identity (sha256)
**Status**: PASS

- Implementation: contentDisposition() helper emits both filename="..." (ASCII fallback) and filename*=UTF-8''<pct> (RFC 5987 percent-encoded).
- Test: asserts match(cd, /filename*=UTF-8''sp%C3%A9c-%CE%B4.md/) for spec-delta.md upload + sha256 byte-identity check.
- Test result: PASS (11.07ms)

### AC#3 — Control chars stripped, quote-stripping preserved
**Status**: PASS

- Implementation: contentDisposition() strips C0+DEL (unicode 0000-001f, 007f) first, then strips double-quote from ASCII fallback.
- Test: uploads filename with C0 bytes and double-quote; asserts no control byte in Content-Disposition AND filename="abcd.md" in ASCII fallback.
- Test result: PASS (9.54ms)

### AC#4 — No regression in existing attachment-routes.test.ts
**Status**: PASS

All 8 tests pass including pre-PILOT-13 cases:
- round-trip byte-identity: PASS
- event-in-txn (kind=attachment): PASS
- capabilities token: PASS
- 413 (oversized upload): PASS
- 404 (unknown ticket): PASS
- foreign-project 403: PASS

Note: bootstrap-promotion.test.ts and report-routes.test.ts have pre-existing failures (last touched by ABS-282 and ABS-353 commits; PILOT-13 diff does NOT touch those files). Not PILOT-13 regressions.

### AC#5 — docs/guides/AGENTIC-BACKEND-API.md notes nosniff + RFC 5987 behaviour
**Status**: PASS

grep -n "nosniff|RFC 5987|content-type-options" docs/guides/AGENTIC-BACKEND-API.md:
  line 598: carries X-Content-Type-Options: nosniff so legacy
  line 600: Content-Disposition filename is emitted per RFC 5987
  line 601: filename="..." fallback plus a UTF-8 percent-encoded filename*=UTF-8''<pct>

---

## Type-check + Lint

| Check | Result |
|-------|--------|
| pnpm -r typecheck | PASS — all 5 packages clean (core, server, forge, webhooks, web) |
| pnpm lint | PASS — no ESLint errors |

---

## Scope Verification

PILOT-13 diff touches exactly 3 files:
1. backend/apps/server/src/routes/attachments.ts — download handler + contentDisposition() helper
2. backend/apps/server/test/attachment-routes.test.ts — 3 new PILOT-13 test cases
3. docs/guides/AGENTIC-BACKEND-API.md — download-route docs update

Out-of-scope items confirmed untouched: upload path, storage model (bytea, ADR-A-0010), list route, mock-tracker.sh, jira-tracker.sh.

---

## Security Flag Review

Ticket carries `security` flag. PILOT-9 security-engineer review (2026-07-22T14:25:40Z) verdict: pass — nosniff closes MIME-sniffing, control-char strip (incl. CR/LF) kills header-injection/response-splitting (double-covered by Node CRLF rejection), RFC 5987 encoding correct with byte-identity preserved, project-scoping/authz unchanged. Security review gate cleared before In Test.

---

## Final Verdict

APPROVED — all 5 AC criteria met, 8/8 tests green, typecheck clean, lint clean, docs updated, security gate cleared.

Sandbox: non-8420 port 55413 (ABS-374 compliant); container cleaned up post-run.
Exit transition: In Test -> Story Acceptance (no design flag set).
