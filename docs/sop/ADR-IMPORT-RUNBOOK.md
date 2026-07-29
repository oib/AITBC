# ADR Import Runbook

Import Architecture Decision Records from `adrs/agentic/*.md` into the agentic
backend as `adr` work items. The endpoint is idempotent; re-importing an unchanged
file is a no-op.

**Authentication:** admin (bootstrap) token required. No agent or orchestrator token
is accepted on this route.

---

## Prerequisites

- Backend running at `$BASE` (default `http://localhost:8420`)
- `BACKEND_BOOTSTRAP_TOKEN` set in your shell
- ADR markdown files under `adrs/agentic/` with valid frontmatter (see below)
- Docker + `curl` + `tar`

---

## Step 1 — Verify ADR frontmatter

Each file must have an opening `---` block with at minimum an `id:` field. The
importer aborts that file (not the whole tar) if `id` is missing.

Required fields:

| Field | Example | Notes |
| ----- | ------- | ----- |
| `id` | `ADR-A-0007` | Becomes `work_item.key`; must match `^[A-Za-z0-9._-]{1,64}$` and be unique in the project |
| `title` | `Commit message convention` | — |
| `status` | `accepted` | Case-insensitive; see status map below |

Optional fields:

| Field | Alias | Notes |
| ----- | ----- | ----- |
| `date` | `adr_date` | Stored in `work_item.fields['adr_date']` |
| `scope` | `adr_scope` | Stored in `work_item.fields['adr_scope']` |
| `supersedes` | — | Key of the ADR this one replaces (e.g. `ADR-A-0002`) |

**Id charset:**

The `id` must match `^[A-Za-z0-9._-]{1,64}$` (ASCII letters, digits, dots,
underscores, hyphens; 1–64 characters). A violation is **fail-closed**: the file
is skipped and an error entry appears in the response `errors` array. Sibling files
in the same tar continue unaffected.

**Status map (case-insensitive):**

| Frontmatter value | Backend status |
| --- | --- |
| `draft` | `Draft` |
| `proposed` | `Proposed` |
| `accepted` | `Accepted` |
| `superseded` | `Superseded` |
| anything else | `422` — the file is rejected; other files in the tar continue |

Unknown status is **fail-closed** in the same way — the file is skipped, siblings
continue, and an error entry appears in the `errors` array.

**Example frontmatter:**

```markdown
---
id: ADR-A-0007
title: Commit message convention
status: accepted
date: 2026-05-01
scope: agentic
supersedes: ADR-A-0002
---

## Context

We needed a consistent commit format across the agentic-delivery codebase...
```

---

## Step 2 — Pack and import

```bash
TOKEN=$BACKEND_BOOTSTRAP_TOKEN
BASE=http://localhost:8420
PROJECT=ABS

tar -cf - adrs/agentic/*.md | \
  curl -sf -X POST "$BASE/api/admin/import/adrs?project=$PROJECT" \
    -H "authorization: Bearer $TOKEN" \
    -H 'content-type: application/x-tar' \
    --data-binary @-
```

**Success response (200):**

```json
{ "imported": 22, "keys": ["ADR-A-0001", "ADR-A-0002", "..."] }
```

**Partial failure response (422):**

```json
{
  "imported": 21,
  "keys": ["ADR-A-0001", "..."],
  "errors": [
    {
      "file": "ADR-A-0005-some-decision.md",
      "error": "ADR ADR-A-0005: unknown status 'in-progress' — fail closed (allowed: draft, proposed, accepted, superseded)"
    }
  ]
}
```

A bad `id` charset produces the same 422 shape:

```json
{
  "imported": 0,
  "keys": [],
  "errors": [
    {
      "file": "ADR-BAD.md",
      "error": "ADR id 'My Decision!' violates the allowed charset ^[A-Za-z0-9._-]{1,64}$ — fail closed"
    }
  ]
}
```

Partial failure does **not** roll back successfully imported files. Fix the
frontmatter in the failing file and re-run — the others are idempotent no-ops.

---

## Step 3 — Verify

```bash
# Check one ADR round-trips correctly
TRACKER_CMD=scripts/backend-tracker.sh \
BACKEND_TOKEN=$TOKEN \
TRACKER_PROJECT=$PROJECT \
  scripts/backend-tracker.sh get ADR-A-0007
```

The response should have `type: adr` in frontmatter and the verbatim body from the
markdown file.

---

## The `supersedes:` frontmatter convention

`supersedes:` triggers two side effects when the named ADR exists in the project:

1. A `work_item_link` row of `kind='supersedes'` is written from the importing ADR
   to the superseded one (idempotent — `ON CONFLICT DO NOTHING`).
2. If the superseded ADR is not already in `Superseded` status, the importer updates
   its status and records a `kind='transition'` event
   (`reason: superseded by <id>`). The transition appears on the SSE feed.

Both side effects commit atomically with the importing ADR's own write.

**Only machine-readable `supersedes:` frontmatter triggers a link.** Prose
references (e.g. "This decision supersedes ADR-A-0007") are not parsed.

If `supersedes:` names a key not found in the project, the field is stored in
`work_item.fields` but no link is written and no error is raised.

---

## Re-import idempotency

Re-importing a file whose `title`, `status`, `body`, and frontmatter fields
(`adr_date`, `adr_scope`, `supersedes`) are **unchanged** is a **no-op**:

- The transaction rolls back.
- No `work_item_revision` row is written.
- No event is appended.
- The key still appears in the response `keys` array so callers know the file
  was processed.

When content changes (any field differs), the importer updates `work_item`, writes a
new `work_item_revision` snapshot, and appends one `kind='import'` event.

The `supersedes` link write uses `ON CONFLICT DO NOTHING` — a second import never
creates a duplicate link.

**Safe to run on every deploy.** The importer is designed to be called in CI or a
deploy script after every ADR file change. Files that have not changed cost one
read per file and commit nothing.

---

## Human-only: ADR acceptance

Importing an ADR with `status: accepted` sets its `work_item.status` to `Accepted`
directly (the importer bypasses the transition guard for bulk-load purposes). After
import, any subsequent `→ Accepted` transition via the tracker API (agent or human)
goes through the human-only guard in the transition service.

**No agent or orchestrator token may transition an ADR to `Accepted`.** The guard
returns `403 { "error": "forbidden", "reason": "ADR acceptance is a human-only
action (ADR-A-0004)" }` for any non-human principal. There is no UI path that
bypasses this check (ADR-A-0004).

---

## Related

- API route: `docs/guides/AGENTIC-BACKEND-API.md` — `POST /api/admin/import/adrs`
- Knowledge guide: `docs/guides/AGENTIC-BACKEND-KNOWLEDGE.md`
- Importer source: `backend/packages/core/src/items.ts` (`importAdr`)
- Admin route source: `backend/apps/server/src/routes/admin.ts`
- Human-only guard: `backend/apps/server/src/server.ts` (transition hook)
- Import tests: `backend/apps/server/test/adr-import-routes.test.ts`
- ADR workflow: `backend/packages/core/src/workflows/adr-lifecycle.yaml`
- S2 spec doc: `backend/docs/adr-import-api.md`
