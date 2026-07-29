# Test Prep — PILOT-9 (Attachment store at the work item)

Data-Provisioning-Engineer handoff for QAS. Everything below was **verified live** by
this seat against an ephemeral sandbox Postgres (never port 8420 — ABS-374). QAS runs
with zero setup gaps: pick the path per AC.

Twin: ABS-489. Commit under test: `166eedfb`. Branch: `PILOT-9-auto`.

---

## 1. Fixtures (committed)

- `backend/apps/server/test/fixtures/PILOT-9/spec-draft.md` — representative
  evidence/spec payload. 90 bytes, UTF-8 (incl. multibyte), known digest:
  `sha256 = fa026dad4712749d74fd9443f0d7ce0e76c05910fa2ab1a6d6a47d405de99701`.
  Use it for the AC#1 byte-identical round-trip (`attach` → `attachments` → `attachment-get`).
- **Boundary / edge rows are generated at runtime** (do NOT commit a 10 MB blob):
  - Over-limit (AC#2, → 413): `head -c 10485761 /dev/zero > big.bin` (10 MB + 1 byte).
  - At-limit ok-case (optional): `head -c 10485760 /dev/zero > atlimit.bin` (exactly 10 MB).
  - Unknown-ticket (AC#2, → 404 "no such ticket"): just `attach NOPE-999 <any file>`.

## 2. Seeded data + RLS/auth test contexts

The backend uses **bearer-token project isolation** (not the `withUserContext`
PL/pgSQL helpers) — the token IS the RLS context. Two contexts cover every AC:

| Context | How to seed | Purpose |
|---|---|---|
| **org-wide admin** (`withAdminContext` analogue) | the boot `BACKEND_BOOTSTRAP_TOKEN` seeds it on first boot; it is the org-wide admin token | upload/list/download in the target project (AC#1, AC#3); actor recorded as `admin` |
| **foreign project-scoped agent** (cross-tenant negative) | `POST /agent/v1/orchestrators {"project":"OTHER","instance":"foreign-01"}` → project-scoped token bound to OTHER | AC#5: foreign token → **403** on upload AND download of the PROJ path |

The DB-gated integration test (`attachment-routes.test.ts`) **self-provisions** its own
schema, orgs (A/B), projects (PROJ/OTHER), tokens (`tokenAwide`, `tokenBscoped`) and
work items over HTTP, and cleans up in `after`. QAS needs **only a Postgres** for that path.

## 3. Path A — DB-gated integration suite (in-process, no container)

`buildServer(pool)` runs in-process; only a Postgres `DATABASE_URL` is required.

```bash
# throwaway Postgres on an isolated port (never 5432/8420 live)
docker run -d --name pilot9-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=agentic -p 55439:5432 postgres:16-alpine
export DATABASE_URL="postgres://postgres:t@127.0.0.1:55439/agentic"
cd backend
node --import tsx --test --test-concurrency=1 apps/server/test/attachment-routes.test.ts
node --import tsx --test --test-concurrency=1 packages/core/test/migrate.test.ts
docker rm -f pilot9-pg
```

**Verified result (this seat):**
- `attachment-routes.test.ts` — **6/6 pass** (round-trip, event-in-txn AC#3, capabilities
  token, 413, 404 no-such-ticket, foreign-project 403).
- `migrate.test.ts` — **7/7 pass** (015 idempotent AC#1; 001..013 byte-unchanged).
- `pnpm -r typecheck` — clean, all packages.

## 4. Path B — live CLI transcript (AC#1, AC#2 evidence; ABS-374 sandbox)

Run the server directly on a **non-8420** port against the sandbox Postgres:

```bash
cd backend
export DATABASE_URL="postgres://postgres:t@127.0.0.1:55439/agentic_cli" \
       NODE_ENV=development BACKEND_BOOTSTRAP_TOKEN="pilot9-$(openssl rand -hex 24)" PORT=8499
scripts/sandbox-guard.sh "http://127.0.0.1:8499"   # OK: non-8420
node --import tsx apps/server/src/index.ts &        # migrations auto-apply (015 included)
BASE=http://127.0.0.1:8499
curl -sf -X POST $BASE/api/admin/projects -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
  -H 'content-type: application/json' -d '{"key":"ABS","name":"Attach demo"}'
# foreign token for AC#5:
curl -sf -X POST $BASE/agent/v1/orchestrators -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
  -H 'content-type: application/json' -d '{"project":"OTHER","instance":"foreign-01"}'

export BACKEND_URL=$BASE BACKEND_TOKEN="$BACKEND_BOOTSTRAP_TOKEN" TRACKER_PROJECT=ABS
KEY=$(scripts/backend-tracker.sh create --type ticket --title "Attachment target")
scripts/backend-tracker.sh attach "$KEY" apps/server/test/fixtures/PILOT-9/spec-draft.md
scripts/backend-tracker.sh attachments "$KEY"
scripts/backend-tracker.sh attachment-get <att-id> out.md   # sha256 out.md == fixture digest
```

**Verified transcript (this seat, port 8499):**
```
created: ABS-1
attach -> id=d6809556-d91d-42e7-a331-b41cc242cdee (exit 0)
{id: d6809556-…, filename: spec-draft.md, size: 90,
 sha256: fa026dad4712749…de99701, created: 2026-07-22T13:30:44Z, actor: admin}
attachment-get exit=0   → sha_out == sha_in  → AC#1 ✓ byte-identical
```
AC#2 still to capture by QAS: over-limit `attach` → 413 + adapter exit≠0; `attach NOPE-999`
→ "no such ticket: NOPE-999". AC#3 event row: `SELECT kind,payload FROM event WHERE
kind='attachment'` (event LOG, not the `events` dispatch feed — by design, per the
be-developer decision comment).

Cleanup: kill the node server; `docker rm -f` the Postgres container.

## 5. Notes for QAS

- **8 pre-existing suite failures are NOT PILOT-9 regressions.** Back-to-back on the same
  sandbox Postgres: BASE `e872ca73` = 212 tests / 8 fail; BRANCH `166eedfb` = 218 tests
  (+6 attachment, all pass) / **same 8 fail** (identical names: `dev boot seeds…`,
  `non-dev boot…`, and 5 `report-routes` ACs). PILOT-9 touches none of those files.
  They are environmental (need `orchestrator-report.sh` / dev-boot env) and out of scope.
- `attachments` capability token: `GET /capabilities` → `packet\nbrief\npolicies\nattachments`.
- Mock difference is sanctioned (ADR-A-0021): `mock-tracker.sh` has no attachment ops —
  documented in `docs/guides/AGENTIC-BACKEND-API.md §Behavioral differences`.
