# Agentic Backend API Reference

Phase-1 backend (ABS-229): Fastify + Postgres, replacing the Jira binding.
Routes live on two prefixes — `/agent/v1` for the orchestrator adapter, `/api/v1`
for the dashboard/SSE feed.

Stories shipped as of v1 (S1–S9 — ABS-233/234/235/236/237/238/239/240/241):

|Story|Deliverable|
|---|---|
|S1 — ABS-233|`/healthz`, auth middleware|
|S2 — ABS-234|CAS transition engine (internal)|
|S3 — ABS-235|`GET/POST /items`, `GET/PATCH /items/:key`, links, children, parent, child-count, assign|
|S4 — ABS-236|`POST /comments`, `POST /transition`, `GET /events`, SSE stream|
|S5 — ABS-237|`scripts/backend-tracker.sh` — CLI adapter (curl shim, `$TRACKER_CMD` drop-in)|
|S6 — ABS-238|`GET /capabilities`, `GET /items/:key/packet`, `GET /items/:key?view=brief`; `build_packet()` probe|
|S7 — ABS-239|Docker packaging, admin/import, export, orchestrator registration + heartbeat|
|S8 — ABS-240|Board-Monitor SPA: login, Kanban board, ticket detail drawer, SSE live feed|
|S9 — ABS-241|Escalation inbox + human write actions (transition, comment, label/release toggle)|

Phase-3 knowledge surface (ABS-231 epic — `epic/ABS-231-phase3-knowledge`):

|Story|Deliverable|
|---|---|
|S1 — ABS-378|DB migration 008; `adr` type + `adr-lifecycle` workflow; `policy`/`policy_revision` tables|
|S2 — ABS-379|`POST /api/admin/import/adrs`; tar importer; `supersedes:` wiring; human-only `Accepted` guard|
|S3 — ABS-380|`resolveEffectivePolicy`; human policy CRUD (`/api/v1/projects/:p/policies`)|
|S4 — ABS-381|`GET /agent/v1/projects/:p/policies[?audience]`; `policy_rev` line; `policies` capability; adapter op|
|S5 — ABS-382|`build_packet` policy-block injection; `policy_rev` in packet cache; `ORCH_POLICY_INJECT` audit|

Command Queue (ABS-348 / ABS-354 / ABS-444):

|Story|Deliverable|
|---|---|
|ABS-348|`orch_command` table + enqueue/poll/receipt core; two-surface auth split (human session / orchestrator token)|
|ABS-354|Board status-read path (`GET /api/v1/…/commands`)|
|ABS-439|nullable `reason` column + enqueue persistence — stores WHY each destructive command was issued (ABS-417 AC3 follow-up)|

Dashboard read-surface hardening (ABS-410 epic):

|Story|Deliverable|
|---|---|
|ABS-435|`requireDashboardRead` guard; session-only human-role read allowlist on four `/api/v1` dashboard routes|
|ABS-442|`GET /api/v1/projects` gated (posture A); sole SPA caller confirmed; dashboard read surface now fully uniform|

> **Human-only boundaries (ADR-A-0004):** ADR acceptance (`Proposed → Accepted`) and all
> policy writes (create / update / status) are Human acts. No agent or orchestrator token
> may perform them — those routes return `403`. No Phase-3 entity is ever
> `orchestrator-ready`; the DB-level ADR guardrail fails closed on any attempt to set
> `orchestration_state = 'eligible'` on an `adr` work item.

This document covers the **S3 entity-op routes** (ABS-235), the **S4 routes** (ABS-236),
the **S5 CLI adapter** (ABS-237), the **S6 context packet routes** (ABS-238), the
**S7 admin/lifecycle routes** (ABS-239), the **S8 board-monitor SPA and its API
routes** (ABS-240), the **S9 human write surface** (ABS-241), and the
**Phase-3 knowledge surface** (ABS-231).

---

## Authentication

The backend has two auth paths. Each stamps a `via` mechanism marker on the resolved
`Principal` (ABS-413).

**Bearer token** — `Authorization: Bearer <token>` header, handled by `auth.ts`. Sets
`Principal.via = 'bearer'`. Used by agent, orchestrator, and human tokens on `/agent/*`
and API read routes.

**Session cookie** — issued by `POST /api/v1/session` (validates a bearer token, returns
an `HttpOnly` cookie). Handled by `sessions.ts`. Sets `Principal.via = 'session'`.
Required by all human-only write surfaces (see [Session authentication](#session-authentication)).

> **Human-only write gate (ABS-413):** `requireHuman` (`routes/guards.ts`) rejects `403`
> unless `role ∈ {admin, maintainer}` **AND** `via === 'session'`. A bearer token with
> role `admin`/`maintainer` is rejected — the session mechanism is required, not the role
> alone (ADR-A-0004/0005; team decision:
> `docs/agent-outputs/ABS-413-auth-mechanism-gate-decision.md`).
>
> **Dashboard read gate (ABS-435 / ABS-442):** `requireDashboardRead` (`routes/guards.ts`)
> rejects `403` unless `role ∈ {admin, viewer, maintainer}` **AND** `via === 'session'`.
> Applied to every read route on the `/api/v1` dashboard surface — `/attention`, `/board`,
> `/inbox`, `/items/:key`, and `/projects` (the full list; no authenticated read is left
> ungated by omission). Machine roles (`agent`/`orchestrator`) and human-role bearer tokens
> are both rejected; an in-org agent cannot enumerate dashboard data (ADR-A-0004/0005).

Bearer token scope: project-scoped tokens are rejected on any project other than the one
they were issued for (`403 forbidden`). Org-wide tokens authenticate against any project
in the same org; a cross-org attempt returns `403`. Missing or malformed tokens return
`401 unauthorized`.

The project id comes from `Principal.targetProjectId` (resolved by `auth.ts`); routes
never extract it from the URL path, so a mismatched `:project` key returns `404`, not
an auth error.

---

## Entity Ops (S3 — ABS-235)

All entity-op responses are `text/plain; charset=utf-8`, byte-identical to the
`scripts/mock-tracker.sh` output so the S5 CLI adapter can be a pure curl shim. Error
bodies are also `text/plain` (unlike the S4 JSON errors below).

**Common path parameter**

|Parameter|Description|
|---|---|
|`project`|Project key (e.g. `ABS`)|

---

### `GET /agent/v1/projects/:project/items/:key`

Returns the canonical full render of a work item. Add `?view=brief` for the
abbreviated dedup-gate form (frontmatter + Goal + AC + latest handoff) — see the
S6 section below.

**Path parameters**

|Parameter|Description|
|---|---|
|`key`|Work item key (e.g. `ABS-123`)|

**Response**

```
200 text/plain
---
id: ABS-123
type: ticket
title: My ticket
status: In Progress
...
---

## Goal
...

## Comments

### 2026-07-15T12:00:00Z | kind: handoff | actor: be-developer
...
```

The frontmatter reproduces the mock format field-by-field. The `priority:` field appears
only when the value is not `normal` (only-when-set, matching the mock's own rule for
optional fields). The `orchestrator-ready` label appears in `labels:` when
`orchestration_state = 'eligible'`; it is projected at render time and stored in no table.

The `## Comments` section is a chronological projection: comment rows and transition events
merged by timestamp. Each transition event renders as a `kind: transition-reason` block,
byte-identical to the block the mock writes for `transition`.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <key>`|Key not found in the project|

**Example**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-123
```

---

### `GET /agent/v1/projects/:project/items`

Searches work items with optional filters. Returns all matches; no LIMIT, no silent
prefix. An empty result set is an empty body, not an error.

**Query parameters**

|Parameter|Description|
|---|---|
|`status`|Exact status match (e.g. `In Progress`)|
|`type`|Exact type match: `epic`, `ticket`, or `subtask`|
|`parent`|Parent item key (e.g. `ABS-1`)|
|`text`|Case-insensitive substring in title or body|
|`label`|Exact label; `orchestrator-ready` matches items with `orchestration_state = 'eligible'`|

All parameters are optional and combinable. Results order: priority `hotfix` first
(`hotfix > high > normal > low`), then oldest created first.

**Response**

```
200 text/plain
ABS-1    epic    Stories In Flight    My epic
ABS-2    ticket  In Progress          My ticket
```

Each line is tab-separated: `key`, `type`, `status`, `title`, newline.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <parent>`|`parent` filter references an unknown key|

**Example**

```bash
# All in-progress tickets
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3000/agent/v1/projects/ABS/items?status=In+Progress&type=ticket"

# Full-text search
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3000/agent/v1/projects/ABS/items?text=renderer"
```

---

### `POST /agent/v1/projects/:project/items`

Creates a work item. Assigns the next key in the sequence for `prefix` and sets
the initial status to `Backlog`.

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`type`|string|yes|`epic`, `ticket`, or `subtask`|
|`title`|string|yes|Title text|
|`prefix`|string|no|Key prefix (default: `DEMO`)|
|`parent`|string|no|Parent item key|
|`role`|string|no|Assigned role label|
|`flags`|string[]|no|Any of: `design`, `security`, `data`, `skip-review`, `skip-test`|
|`labels`|string[]|no|Labels matching `[A-Za-z0-9._:-]+`; `orchestrator-ready` sets `orchestration_state = 'eligible'`|
|`ac_blocking`|boolean|no|Marks the item as blocking AC sign-off|
|`priority`|string|no|`hotfix`, `high`, `normal` (default), or `low`|
|`body`|string|no|Markdown body; default is the mock's template boilerplate|
|`fields`|object|no|Type-specific structured fields (validated against the type's `field_schema`)|

**Response**

```
200 text/plain
ABS-42
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`create: invalid type '...' (epic\|ticket\|subtask)`|Unknown type|
|`400`|`create: title is required`|`title` absent or empty|
|`400`|`create: invalid flag '...' (design\|security\|data\|skip-review\|skip-test)`|Unknown flag|
|`400`|`create: invalid priority '...' (hotfix\|high\|normal\|low)`|Unknown priority|
|`400`|`create: invalid label '...' (allowed: A-Za-z0-9 . _ - :)`|Label fails pattern|
|`404`|`no such ticket: <parent>`|`parent` key not found|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"ticket","title":"Add auth guard","prefix":"ABS","priority":"high"}' \
  http://localhost:3000/agent/v1/projects/ABS/items
# → 200: ABS-42
```

---

### `PATCH /agent/v1/projects/:project/items/:key`

Updates a single field on a work item. Status changes go through `POST /transition`
(see S4) — sending `field=status` returns `400`.

**Path parameters**

|Parameter|Description|
|---|---|
|`key`|Work item key|

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`field`|string|yes|Field name|
|`value`|string|yes|New value (always a string, even for arrays and booleans)|

**Writable fields**

|Field|Value format|
|---|---|
|`title`|Plain text|
|`type`|`epic`, `ticket`, or `subtask`|
|`parent`|Item key; `[]` to clear|
|`depends_on`|JSON-serialized array of keys, e.g. `["ABS-1","ABS-2"]`|
|`links`|JSON-serialized array of link strings|
|`flags`|JSON-serialized array; allowed values: `design`, `security`, `data`, `skip-review`, `skip-test`|
|`labels`|JSON-serialized array; `orchestrator-ready` maps to `orchestration_state`|
|`ac_blocking`|`"true"` or `"false"`|
|`priority`|`hotfix`, `high`, `normal`, or `low`|

Writing `orchestrator-ready` via `labels` sets `orchestration_state = 'eligible'` and
appends an audit event. The label is never stored in a table.

**Response**

```
200 text/plain
ABS-123: title updated
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`update: status changes must go through 'transition' (validated + reasoned)`|`field=status`|
|`400`|`update: field '<name>' is managed by the tracker`|`id`, `created`, or `updated`|
|`400`|`update: unknown field '...' (title\|type\|parent\|...)`|Field name not in the writable set|
|`400`|Vocab error|Value outside the allowed set (type, flag, priority, label pattern)|
|`404`|`no such ticket: <key>`|Key not found|

**Example**

```bash
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"field":"priority","value":"high"}' \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-123
# → 200: ABS-123: priority updated
```

---

### `POST /agent/v1/projects/:project/items/:key/links`

Adds a link from `key` to another item (or external ref). Idempotent: posting the
same `(key, other, kind)` triple twice inserts one row.

**Path parameters**

|Parameter|Description|
|---|---|
|`key`|Source item key|

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`other`|string|yes|Target key or external URL (e.g. a PR URL)|
|`kind`|string|yes|`parent-child`, `depends-on`, `origin-review`, or `pr`|

**Response**

```
200 text/plain
ABS-123: linked ABS-100 (depends-on)
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`link: invalid kind '...' (parent-child\|depends-on\|origin-review\|pr)`|Unknown kind|
|`400`|`link: 'other' is required`|`other` absent or empty|
|`404`|`no such ticket: <key>`|Source key not found|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"other":"ABS-100","kind":"depends-on"}' \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-123/links
```

---

### `GET /agent/v1/projects/:project/items/:key/children`

Returns direct children of `key`, one TSV line per child (same format as search).

**Response**

```
200 text/plain
ABS-10    ticket  Backlog  Child one
ABS-11    ticket  In Progress  Child two
```

Trailing newline after the last line. Empty body when the item has no children.

**Example**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-1/children
```

---

### `GET /agent/v1/projects/:project/items/:key/parent`

Returns the parent of `key` as a single TSV line (same format as a search row).

**Response**

```
200 text/plain
ABS-1    epic  Stories In Flight  My epic
```

Empty body when the item has no parent.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <key>`|Key not found|

---

### `GET /agent/v1/projects/:project/items/:key/child-count`

Returns the count of direct children as a decimal integer string, followed by a
newline.

**Response**

```
200 text/plain
3
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <key>`|Key not found|

---

### `POST /agent/v1/projects/:project/items/:key/assign`

Assigns a work item to an account.

**Path parameters**

|Parameter|Description|
|---|---|
|`key`|Work item key|

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`accountId`|string|yes|Account identifier to assign|

**Response**

```
200 text/plain
ABS-123: assigned to user@example.com
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`assign: 'accountId' is required`|`accountId` absent or empty|
|`404`|`no such ticket: <key>`|Key not found|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"accountId":"user@example.com"}' \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-123/assign
```

---

## Write transaction guarantee

Every write op (create, update, link, assign) runs one Postgres transaction that:

1. Resolves the item and takes an exclusive lock.
2. Applies the change to `work_item`.
3. Inserts a snapshot row into `work_item_revision`.
4. Inserts an event row into `event`.

All four steps commit or roll back together — no partial writes.

An attachment upload (PILOT-9) shares this guarantee: the `attachment` row and its
`event` row (`kind='attachment'`) commit in one transaction — either both land or
neither does.

---

## Context Packet & Brief View (S6 — ABS-238)

S6 adds three routes that let the orchestrator receive a server-composed,
pre-filtered context packet instead of the full item dump. The packet targets the
~5–8× token reduction on bounced tickets by replacing the `ORCH_PACKET_MAX_BYTES`
byte-cap truncation (which silently dropped Acceptance Criteria from long tickets)
with slot-selector composition on the server.

---

### `GET /capabilities`

Returns a plain-text list of optional adapter ops the server supports. The
orchestrator calls this once per process run (via `backend-tracker.sh capabilities`)
to decide whether to use the packet path or fall back to the legacy full-dump.

**Authentication:** bearer token required

**Route:** root-level (`/capabilities`), project-independent

**Response (200):** `text/plain; charset=utf-8`

```
packet
brief
policies
attachments
```

One capability token per line. The backend returns four tokens: `packet`, `brief`,
`policies` (Phase 3, ABS-381), and `attachments` (PILOT-9). A backend without the
attachment migration/route omits the `attachments` token, so a probe can detect the
capability exactly like `packet`/`brief`/`policies`.

**Errors**

|Status|Cause|
|---|---|
|`401`|Missing or invalid token|

**Example**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8420/capabilities
# -> packet
# -> brief
# -> policies
# -> attachments
```

---

## Attachments (PILOT-9 — twin ABS-489)

File attachments at a work item (parity with the Jira attachment workflow). File
content is stored as `bytea` in Postgres (#PATH_DECISION: minimal, transactional,
rides the existing backup; object storage is out of scope). The size limit is
**10 MB** (`10485760` bytes), enforced at the route (Fastify `bodyLimit` → `413`)
and by a `CHECK` constraint on `attachment.size_bytes`.

An upload writes the `attachment` row **and** an `event` row (`kind='attachment'`)
in one transaction (see *Write transaction guarantee*). The attachment event lands
in the event **log** (audit trail) but is deliberately not surfaced in the
orchestrator `events` dispatch feed, which is `transition`/`create`-only by design.

### `POST /agent/v1/projects/:project/items/:key/attachments`

Uploads a file. Raw request body (`application/octet-stream`); the filename rides
the `X-Attachment-Filename` header, the media type the optional
`X-Attachment-Content-Type` header (default `application/octet-stream`).

**Response (201):** `text/plain` — the new attachment id (uuid).

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`missing X-Attachment-Filename header`|Filename header absent|
|`404`|`no such ticket: <key>`|Key not found in the caller's project|
|`413`|`Payload Too Large`|Body exceeds the 10 MB limit|

### `GET /agent/v1/projects/:project/items/:key/attachments`

Lists an item's attachments, one `{...}` line each (oldest first):

```
{id: <uuid>, filename: <name>, size: <bytes>, sha256: <hex>, created: <iso>, actor: <role>}
```

### `GET /agent/v1/projects/:project/attachments/:id/content`

Downloads the raw bytes with the stored `media_type` as `Content-Type` and a
`Content-Disposition: attachment; filename="..."` header. An id outside the
caller's project is reported `404` (never another project's bytes).

The response is hardened against the stored, uploader-controlled `media_type`/
`filename` (PILOT-13): it carries `X-Content-Type-Options: nosniff` so legacy
browsers cannot MIME-sniff the payload into an inline render, and the
`Content-Disposition` filename is emitted per RFC 5987 — an ASCII
`filename="..."` fallback plus a UTF-8 percent-encoded `filename*=UTF-8''<pct>`
token so non-ASCII filenames round-trip, with control characters (C0 + DEL)
stripped from both tokens. The ASCII fallback additionally drops `"` and `\`
so neither can break out of or mis-terminate its quoted-string for a strict
RFC 6266 parser (PILOT-14).

**Example**

```bash
# upload → list → download (byte-identical)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  -H "X-Attachment-Filename: spec.md" \
  --data-binary @spec.md \
  http://localhost:8420/agent/v1/projects/ABS/items/ABS-231/attachments
# -> <uuid>
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8420/agent/v1/projects/ABS/attachments/<uuid>/content -o out.md
```

---

### `GET /agent/v1/projects/:project/items/:key/packet`

Returns a server-composed context packet for the work item. The packet includes
only the slots relevant to an agent spawn — no byte cap, no tail truncation. The
`## Acceptance Criteria` section is always present.

**Path parameters**

|Parameter|Description|
|---|---|
|`key`|Work item key (e.g. `ABS-238`)|

**Response (200):** `text/plain; charset=utf-8`

The response body follows the exact slot order from Spec §6 (amended 2026-07-15):

```
<full YAML frontmatter>
---

<all body sections verbatim (Goal / Scope / Acceptance Criteria / DoD / Test Plan / ADR Context)>

## Comments

<latest handoff block>

<latest transition-reason block (rendered from transition event, or v2 comment fallback)>

<latest gate-results block — only if newer than the latest handoff>

<all decision + bsa-decision blocks, oldest first>

(N ältere Kommentare weggelassen — vollständige Historie: tracker get <key>)
```

The breadcrumb line appears only when N > 0 omitted comments exist. The
`## Comments` header is always emitted (even with zero comments), because
decisions must always appear (Spec §6 AC).

The transition-reason block is synthesized from the backend transition event
(`event.reason`). For imported v2 tickets with no backend-native event, the latest
`kind: transition-reason` comment row is used instead.

**Byte-stability:** two calls with the same `updated` timestamp return byte-identical
responses.

**No byte cap:** composition replaces truncation. The packet size is bounded by the
selected slots, not the full comment history.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <key>`|Key not found in the project|

**Example**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8420/agent/v1/projects/ABS/items/ABS-238/packet
```

---

### Brief view — `GET /items/:key?view=brief`

Returns an abbreviated render for the orchestrator's dedup gate: frontmatter +
Goal + Acceptance Criteria + latest handoff. All other comments are omitted.

**Query parameter:** `view=brief`

**Response (200):** `text/plain; charset=utf-8`

```
<full YAML frontmatter>
---

## Goal

<goal body>

## Acceptance Criteria

<ac body>

### <at> | kind: handoff | actor: <actor>

<latest handoff body>
```

No `## Comments` wrapper around the handoff block. The handoff is emitted directly
after the AC section.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`404`|`no such ticket: <key>`|Key not found in the project|

**Example**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8420/agent/v1/projects/ABS/items/ABS-238?view=brief"
```

---

### Slot-selector architecture

Each packet slot is composed by a standalone TypeScript selector function in
`backend/packages/core/src/packet/selectors/`. The four selectors are:

|Selector|File|Returns|
|---|---|---|
|`selectHandoff`|`selectors/handoff.ts`|Latest `kind: handoff` comment|
|`selectTransitionReason`|`selectors/transitionReason.ts`|Latest transition event reason (v2 comment fallback)|
|`selectGateResults`|`selectors/gateResults.ts`|Latest `kind: gate-results` comment, only if newer than the handoff|
|`selectDecisions`|`selectors/decisions.ts`|All `kind: decision` + `kind: bsa-decision` comments, oldest first|

Each selector accepts a `PacketDb` interface (defined in
`backend/packages/core/src/packet/PacketDb.ts`) and is individually unit-testable
without a real database. The composition function in
`backend/packages/core/src/packet/compose.ts` calls all four selectors and
assembles the output — it contains no inline `kind` matching.

This encapsulation satisfies the v3 design constraint (ABS-313): when typed event
records replace `comment.kind` rows, only the selectors change — the packet output
format and the adapter subcommand surface stay unchanged.

---

## Comments (S4 — ABS-236)

### `POST /agent/v1/projects/:project/items/:key/comments`

Appends a human-readable comment to a work item. Comments are append-only and
carry no control state — the event log is the source of truth.

**Path parameters**

|Parameter|Description|
|---|---|
|`project`|Project key (e.g. `ABS`)|
|`key`|Work item key (e.g. `ABS-123`)|

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`kind`|string|yes|One of the writable vocabulary kinds|
|`actor`|string|yes|Identity of the commenter|
|`body`|string|yes|Comment text (may be empty string)|

**Writable `kind` values** (9 writable; `transition-reason` is reserved):

`understanding`, `gate-results`, `handoff`, `decision`, `notification`,
`follow-up`, `bsa-decision`, `skip`, `claim`

> `transition-reason` is reserved for import/projection only ([A-313], ABS-313).
> The transition service writes the reason onto the event payload, not as a comment row.
> Posting `kind=transition-reason` via this route returns `400`.

**Response**

```
201 text/plain
ABS-123: comment added
```

**Errors**

|Status|`error` field|Cause|
|---|---|---|
|`400`|`missing_field`|One of `kind`, `actor`, or `body` is absent|
|`400`|`bad_comment_kind`|`kind` outside the writable vocabulary|
|`404`|`not_found`|Item or project not found in the caller's org|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"kind":"handoff","actor":"be-developer","body":"Implementation complete."}' \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-236/comments
# → 201: ABS-236: comment added
```

---

## Transition (S4 — ABS-236)

### `POST /agent/v1/projects/:project/items/:key/transition`

Moves a work item to a new status via a compare-and-set (CAS) transaction.
The transition event records the reason; no comment row is written ([A-313]).

**Path parameters**

|Parameter|Description|
|---|---|
|`project`|Project key|
|`key`|Work item key|

**Request body** (JSON)

|Field|Type|Required|Description|
|---|---|---|---|
|`to`|string|yes|Target status|
|`actor`|string|yes|Identity of the caller|
|`reason`|string|yes|Human-readable rationale (stored on the event payload)|
|`expect_from`|string|no|Expected current status for CAS — omit to skip the check|

**Transaction sequence**

1. CAS check: if `expect_from` is set and the item's live status differs → `409`.
2. Legality check: `to` must be in `next[current_status]` per the item's workflow → `400`.
3. `UPDATE work_item … WHERE status = expect_from` (atomic CAS) → `409` on race loss.
4. `INSERT` transition event with `{ from, to, reason }` on the payload.
5. Publish the event to the in-process bus → SSE fan-out.

Steps 3–4 commit atomically or not at all.

**Response**

```
200 text/plain
ABS-123: Backlog -> In Progress
```

**Errors**

|Status|`error` field|Cause|
|---|---|---|
|`400`|`missing_field`|`to`, `actor`, or `reason` absent|
|`400`|`illegal_transition`|`to` not in `next[from]`; response includes `allowed` list|
|`404`|`not_found`|Item or project not found in the caller's org|
|`409`|`cas_mismatch`|Item already left `expect_from`; adapter renders as ABS-198 NOOP|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to":"In Progress","actor":"be-developer","reason":"claiming","expect_from":"Ready for Development"}' \
  http://localhost:3000/agent/v1/projects/ABS/items/ABS-236/transition
# → 200: ABS-236: Ready for Development -> In Progress
```

---

## Events op (S4 — ABS-236)

### `GET /agent/v1/projects/:project/events`

Returns transition events since a sequence number, one line per event in the
mock-tracker format. The orchestrator adapter calls this with `since=auto`
(the default) so the server tracks its cursor.

**Query parameters**

|Parameter|Default|Description|
|---|---|---|
|`since`|`auto`|Sequence floor: integer seq, or `auto` for server-side cursor|

**Request header**

|Header|Default|Description|
|---|---|---|
|`X-Orch-Instance`|`default`|Distinguishes instances of the same token; forms the cursor key `token:instance`|

**Cursor semantics**

- `since=auto`: the server reads and advances `consumer_cursor` for
  `(token, X-Orch-Instance)` inside a transaction with `SELECT … FOR UPDATE`.
  Two callers with different `X-Orch-Instance` values hold independent cursor
  rows and never contend.
- `since=<integer>`: uses the supplied number as the floor; does **not** update
  the stored cursor.

At-least-once delivery: if the HTTP response is lost after the server commits
the cursor advance, the next `auto` poll starts past those events. Callers dedup
on `(ticket_id, to, at)`.

**Semantic difference vs mock**

`mock-tracker.sh events` emits a snapshot diff: A→B→C on the same ticket collapses
to one line showing the net change. This endpoint emits one line per transition.
A→B→C appears as three lines. The orchestrator re-reads item state before spawning,
so multi-event batches for the same ticket are dispatch-safe.

**Response**

```
200 text/plain
{ticket_id: ABS-123, from: Backlog, to: In Progress, at: 2026-07-15T14:42:47Z}
{ticket_id: ABS-124, from: null, to: Backlog, at: 2026-07-15T14:43:01Z}
```

Empty body when there are no new events.

**Errors**

|Status|`error` field|Cause|
|---|---|---|
|`400`|`bad_since`|`since` is neither `auto` nor a finite integer|
|`404`|`not_found`|Project not found in the caller's org|

**Example**

```bash
# Adapter call — server-managed cursor, two independent instances
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Orch-Instance: orchestrator-1" \
     "http://localhost:3000/agent/v1/projects/ABS/events?since=auto"

# Explicit floor — does not advance the stored cursor
curl -H "Authorization: Bearer $TOKEN" \
     "http://localhost:3000/agent/v1/projects/ABS/events?since=42"
```

---

## SSE stream (S4 — ABS-236)

### `GET /api/v1/projects/:project/events/stream`

Server-Sent Events feed for the Kanban dashboard. Sends every committed
transition event as it lands, with reconnect support via `Last-Event-ID`.

**Request headers**

|Header|Description|
|---|---|
|`Authorization`|`Bearer <token>` — required|
|`Last-Event-ID`|Resume from this sequence number on reconnect|

**Response**

```
200 text/event-stream
```

Event frame:

```
id: 17
data: {"seq":"17","ticket_id":"ABS-236","from":"Merging","to":"Docs","at":"2026-07-15T15:52:59Z"}

```

Keep-alive frame (every 15 seconds):

```
: heartbeat

```

Initial frame on connect:

```
: connected

```

**Reconnect / replay**

On reconnect with `Last-Event-ID: <seq>`, the server replays every event with
`seq > Last-Event-ID` from the log before resuming the live stream. The handler
subscribes to the bus **before** querying the log, buffers live events that arrive
during the replay window, then flushes the buffer deduplicating against the
replayed set. No event is lost or duplicated under concurrent commits.

Events reach the client under 1 second after the transition commits to Postgres.

**Error**

|Status|Cause|
|---|---|
|`404`|Project not found in the caller's org|

**Example**

```bash
# Tail live events
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  http://localhost:3000/api/v1/projects/ABS/events/stream

# Reconnect from seq 16
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  -H "Last-Event-ID: 16" \
  http://localhost:3000/api/v1/projects/ABS/events/stream
```

---

## CLI Adapter (S5 — ABS-237)

`scripts/backend-tracker.sh` is the `$TRACKER_CMD` drop-in for the live backend.
Its CLI is byte-identical to `scripts/mock-tracker.sh`, so the orchestrator,
seats, and skills run unchanged when pointed at the real backend instead of the mock.

### Environment variables

|Variable|Default|Required|Description|
|---|---|---|---|
|`BACKEND_URL`|`http://localhost:8420`|no|Backend base URL|
|`BACKEND_TOKEN`|—|**yes**|Bearer token issued by the backend|
|`TRACKER_PROJECT`|—|**yes**|Project key (e.g. `ABS`)|
|`ORCH_INSTANCE_ID`|—|no|Sent as `X-Orch-Instance` for per-instance event cursors (§8)|
|`BACKEND_CURL`|`curl`|no|Override the curl binary (test seam)|

The token travels in a `curl --config` file, never on the argv, so it does not
appear in `ps` output.

### Subcommands

All 19 subcommands — 12 mock-compatible, 3 new S6 ops, 1 new Phase-3 op, and 3
backend-only attachment ops:

|Subcommand|Signature|
|---|---|
|`get`|`get <id>` — full canonical render|
|`get --brief`|`get --brief <id>` — brief view: frontmatter + Goal + AC + latest handoff [S6]|
|`search`|`search [--status V] [--type V] [--parent V] [--text V] [--label V]`|
|`create`|`create --type T --title T [options]` — see `create --help` for full flag list|
|`update`|`update <id> <field> <value>`|
|`comment`|`comment <id> --kind K --actor A (--body T \| --body-file P)`|
|`transition`|`transition <id> <to> --actor A (--reason T \| --reason-file P) [--expect-from S]`|
|`link`|`link <id> <other> <type>`|
|`children`|`children <id>`|
|`parent`|`parent <id>`|
|`child-count`|`child-count <id>`|
|`events`|`events`|
|`assign`|`assign <id> <accountId>`|
|`packet`|`packet <id>` — server-composed context packet (Spec §6) [S6]|
|`capabilities`|`capabilities` — plain-text list of supported optional ops; used by `build_packet()` probe [S6]|
|`policies`|`policies [--audience <role>]` — effective-policy text + `policy_rev` line [Phase-3 S4]|
|`attach`|`attach <id> <file>` — upload a file to a work item; prints the new attachment id [PILOT-9]|
|`attachments`|`attachments <id>` — list an item's attachments (`{id, filename, size, sha256, created, actor}` lines) [PILOT-9]|
|`attachment-get`|`attachment-get <att-id> <out-path>` — download attachment bytes to `<out-path>` (byte-identical) [PILOT-9]|

### HTTP → exit-code / stderr table (spec §7)

|HTTP code|Exit|stdout|stderr|
|---|---|---|---|
|`2xx`|`0`|response body verbatim|—|
|`409` (CAS mismatch)|`0`|`<id>: NOOP compare-and-set expect-from=<expected> actual=<actual> (skipped <to>)`|—|
|`400` illegal transition|`1`|—|`ERROR: transition: illegal transition '<from>' -> '<to>' for <id>`|
|`400` other|`1`|—|`ERROR: <body or "request failed (400)">`|
|`404`|`1`|—|`ERROR: no such ticket: <id>`|
|`401` / `403`|`1`|—|`ERROR: auth failed (<code>): check BACKEND_TOKEN / TRACKER_PROJECT`|
|Network failure|`1`|—|`ERROR: backend request failed (curl exit <N>): <message>`|

The `409 → exit 0` rule implements ABS-198: a lost CAS race is not an error —
a peer moved the ticket first, which is the intended outcome.

### Behavioral differences from mock (sanctioned, not defects)

These are spec-documented differences (Epic-AC 1, ADR-Risiko 1); the adapter
handles both so callers observe no behavioral change:

|Operation|mock-tracker.sh|backend-tracker.sh|
|---|---|---|
|`events`|Snapshot diff: A→B→C collapses to A→C|One line per transition; dispatch-safe (re-reads state first)|
|`transition` to unknown status|`unknown status` in stderr|`illegal transition` in stderr (both non-zero exit)|
|`attach` / `attachments` / `attachment-get`|Not supported (no attachment store)|Backend-only ops (PILOT-9); the file attachment store lives only in the backend, like `policies`. Evidence primary path stays the repo/comments — attachments are additive.|

### `build_packet()` integration (S6 — ABS-238 / Phase-3 S5 — ABS-382)

When `TRACKER_CMD=scripts/backend-tracker.sh`, the orchestrator's `build_packet()`
function probes the adapter once per process run:

```bash
probe_packet_capability   # calls: tracker capabilities | grep -x "packet"
```

On a backend adapter the probe resolves to `packet` and `build_packet()` calls
`tracker packet <id>` instead of `tracker get <id>`. The resulting packet is
smaller (slot-selected, no byte cap) and always includes the Acceptance Criteria.

The `ORCH_PACKET_MODE` environment variable overrides the probe:

|Value|Behavior|
|---|---|
|unset / `packet`|Probe the adapter; use `packet` op when available (default)|
|`full`|Always use the legacy `tracker get` full-dump path, byte-identically to pre-S6|

`ORCH_PACKET_MODE=full` restores the pre-S6 behavior byte-for-byte (ABS-111
convention). Use it when debugging or when the backend is temporarily unavailable.

**Phase-3 S5 — Policy injection (`ORCH_POLICY_INJECT`, ABS-382)**

After resolving the ticket packet, `build_packet()` calls `tracker policies
--audience "$role"` once per build and prepends the rendered effective-policy text
as a block before `=== TICKET ===`:

```
=== POLICY (policy_rev: 3a1b2c…) ===
<rendered effective-policy text for this seat's role>

=== TICKET ===
<ticket dump>
```

The `policies` op returns the rendered text followed by a `policy_rev: <sha256>`
trailing line; the runner lifts the hash into the block header and strips that line
from the body.

`policy_rev` also folds into the packet-cache signature. A policy change invalidates
the cache exactly like a ticket `updated` change; an unchanged policy set re-hits.

Every spawn writes one `POLICY-INJECT` line to `run.log` recording its `policy_rev`
(`policy_rev=none` when no policy applies or when the adapter lacks the `policies`
op). The line fires before the cache-hit early return, so it is never skipped.

```bash
grep POLICY-INJECT work/.orchestrator/run.log | tail -40
```

`ORCH_POLICY_INJECT` controls this behaviour:

|Value|Effect|
|---|---|
|unset / `on`|Inject policy when the adapter offers the `policies` op (default)|
|`off`|Skip injection; produce a byte-identical legacy packet even on a capable adapter|

Adapters without `policies` (mock/jira) exit non-zero, leaving the policy block
empty — the packet is byte-identical to the pre-Phase-3 format. Injection is context
only: it hands the seat governance text to read and grants no new authority.

**Adapter fallback matrix:**

|Adapter|`capabilities` output|Effective packet mode|Policy injection|
|---|---|---|---|
|`backend-tracker.sh`|`packet`, `brief`, `policies`|`packet`|active (when `ORCH_POLICY_INJECT=on`)|
|`mock-tracker.sh`|command not found → exit non-zero|`full`|none (byte-identical to legacy)|
|`jira-tracker.sh`|command not found → exit non-zero|`full`|none (byte-identical to legacy)|
|Any adapter + `ORCH_PACKET_MODE=full`|probe skipped|`full`|none (legacy path forced)|
|Any adapter + `ORCH_POLICY_INJECT=off`|—|unchanged|forced off|

### Quick start

```bash
export BACKEND_URL=http://localhost:8420
export BACKEND_TOKEN=my-token
export TRACKER_PROJECT=ABS

# Drop-in replacement for mock-tracker.sh
TRACKER_CMD=scripts/backend-tracker.sh bash .claude/skills/run-boilerplate/driver.sh --once
```

### Conformance suite

`tests/test-backend-tracker.sh` is the epic's acceptance gate (Epic-AC 1): it
mirrors every `test-mock-tracker.sh` assertion against a live backend, proving
the adapter is a true drop-in. Any assertion diff is a release blocker (ADR-Risiko 1).
S6 (ABS-238) extended the suite with assertions for `packet`, `get --brief`, and
`capabilities`.

The suite is self-provisioning — it boots a throwaway docker-compose stack
(backend + disposable Postgres) on an ephemeral port, runs all assertions,
then tears the stack down on exit:

```bash
bash tests/test-backend-tracker.sh   # boots backend, runs 122 assertions, tears down
```

Requires `docker` and `docker compose`. Exits `0` (SKIP) cleanly when Docker is
unavailable. The suite is auto-discovered by CI (`tests/test-*.sh` glob) and
registered in `tests/test-tracker-adapter-lint.sh`.

---

## Error body shape

**S3 (entity ops):** errors are `text/plain`. The body is the mock-identical message
string (e.g. `no such ticket: ABS-999`). The S5 CLI adapter prints it straight to stderr.

**S4 (comments, transition, events):** errors are `application/json`:

```json
{ "error": "<error_code>", "...": "...additional fields" }
```

|`error`|Extra fields|
|---|---|
|`missing_field`|`required: [...]` — list of absent fields|
|`bad_comment_kind`|`kind: "<submitted>"`, `allowed: [...]`|
|`illegal_transition`|`from`, `to`, `allowed: [...]`|
|`not_found`|`item` or `project` key|
|`cas_mismatch`|`expected`, `actual`, `to`|

**S7 (admin/lifecycle):** errors are `application/json` with a single `error` string:

```json
{ "error": "forbidden" }
```

|`error` value|Status|Cause|
|---|---|---|
|`forbidden`|`403`|Non-admin token used on an admin-only route|
|`project query parameter is required`|`400`|`?project=` absent|
|`no such project`|`404`|Project key not found in the caller's org|
|`key is required`|`400`|`POST /api/admin/projects` body missing `key`|
|`project already exists: <key>`|`409`|Duplicate project key in the same org|
|`instance is required`|`400`|`POST /agent/v1/orchestrators` body missing `instance`|
|`send a tar body with Content-Type: application/x-tar`|`400`|Import body is not a tar buffer|

---

## Admin & Data-Lifecycle Routes (S7 — ABS-239)

S7 turns the backend into an installable product (spec §9/§10). All five routes
require an **admin (org-wide) token** — the bootstrap token seeded from
`BACKEND_BOOTSTRAP_TOKEN`. Agent and orchestrator tokens return `403`.

For the Docker install path and operator runbook (backup, restore, `pg_dump`) see
`backend/README.md`.

---

### `POST /api/admin/projects`

Create a project inside the bootstrap org. The install path calls this immediately
after `docker compose up` to provision a project for the orchestrator to operate on.

**Authentication:** admin token required

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`key`|`string`|yes|Project key (e.g. `ABS`). Unique per org.|
|`name`|`string`|no|Display name; defaults to `key`.|

**Response (201)**

```json
{ "project": "ABS" }
```

**Errors:** `400` key missing; `409` project already exists; `403` non-admin token.

**Example**

```bash
curl -sf -X POST http://localhost:8420/api/admin/projects \
  -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"key":"ABS","name":"My project"}'
# -> {"project":"ABS"}
```

---

### `POST /api/admin/import?project=KEY`

Import a tar of mock-format markdown files (`work/tickets/*.md`) into the named
project. Each `<KEY>.md` member in the archive becomes a work item plus its comments.
BSD-tar AppleDouble sidecars (`._*.md`) are silently skipped.

**Authentication:** admin token required

**Query parameter:** `project` — project key (required)

**Request body:** `Content-Type: application/x-tar` — ustar tar stream

**Response (200)**

```json
{ "imported": 1, "keys": ["ABS-1"] }
```

A ticket imported through this endpoint round-trips **byte-identically** through
`GET /agent/v1/projects/:project/items/:key` (ABS-239 AC#2).

**Errors:** `400` project missing or body not a tar; `404` no such project; `403` non-admin.

**Example**

```bash
tar -cf - -C work/tickets DEMO-1.md | \
  curl -sf -X POST "http://localhost:8420/api/admin/import?project=ABS" \
    -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
    -H 'content-type: application/x-tar' \
    --data-binary @-
# -> {"imported":1,"keys":["DEMO-1"]}
```

---

### `GET /api/export?project=KEY`

Export all tickets in the project as a tar of canonical `.md` files — one
`<KEY>.md` per ticket, ordered by key. Use this as the vendor-lock escape hatch
or a daily backup.

**Authentication:** admin token required

**Query parameter:** `project` — project key (required)

**Response (200):** `Content-Type: application/x-tar` — binary tar stream.
`Content-Disposition: attachment; filename="<KEY>-export.tar"`.

The export is self-contained: a `POST /api/admin/import` of the export onto a
fresh project reproduces every ticket byte-for-byte (tested in
`tests/compose-lifecycle.sh`).

**Errors:** `404` no such project; `403` non-admin.

**Example**

```bash
# Download
curl -sf "http://localhost:8420/api/export?project=ABS" \
  -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
  -o backup.tar
tar -tf backup.tar   # lists ABS-1.md, ABS-2.md, ...

# Restore into an empty project
curl -sf -X POST "http://localhost:8420/api/admin/import?project=ABS" \
  -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
  -H 'content-type: application/x-tar' \
  --data-binary @backup.tar
```

---

### `POST /agent/v1/orchestrators`

Register an orchestrator instance. The bootstrap admin token mints a
**project-scoped orchestrator token** returned exactly once — store it immediately.
Only its `sha256` hash is persisted; the server cannot recover a lost token.

Any authenticated call from an orchestrator refreshes its `last_seen` timestamp
(heartbeat). The registration call itself counts as the first heartbeat, so the
instance appears `live` immediately after registration.

**Authentication:** admin token required

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`project`|`string`|yes|Project key the orchestrator operates on.|
|`instance`|`string`|yes|Unique instance identifier (`ORCH_INSTANCE_ID`).|

**Response (201)**

```json
{
  "token": "<project-scoped-orchestrator-token>",
  "project": "ABS",
  "instance": "orch-01"
}
```

**Errors:** `400` missing `instance` or `project`; `404` no such project; `403` non-admin.

**Example**

```bash
SEAT_TOKEN=$(
  curl -sf -X POST http://localhost:8420/agent/v1/orchestrators \
    -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN" \
    -H 'content-type: application/json' \
    -d '{"project":"ABS","instance":"orch-01"}' | jq -r .token
)
# export into the consumer's environment:
export BACKEND_TOKEN="$SEAT_TOKEN"
export TRACKER_CMD=scripts/backend-tracker.sh
```

---

### `GET /api/v1/projects/:project/orchestrators`

List all registered orchestrator instances for the project with their live/stale
status. An instance is **live** when its `last_seen` is within
`ORCH_HEARTBEAT_THRESHOLD_SEC` seconds of now (default 90 s = 3× the poll
interval); older instances are **stale**.

**Authentication:** admin token required

**Path parameter:** `:project` — project key

**Response (200)**

```json
{
  "orchestrators": [
    { "instance": "orch-01", "last_seen": "2026-07-16T10:00:00Z", "status": "live" },
    { "instance": "orch-02", "last_seen": "2026-07-15T09:00:00Z", "status": "stale" }
  ]
}
```

`last_seen` is an ISO-8601 UTC string or `null` when no heartbeat has been
recorded (should not occur after a valid registration). `status` is either `"live"`
or `"stale"`.

**Errors:** `404` no such project; `403` non-admin.

**Example**

```bash
curl -sf "http://localhost:8420/api/v1/projects/ABS/orchestrators" \
  -H "authorization: Bearer $BACKEND_BOOTSTRAP_TOKEN"
# -> {"orchestrators":[{"instance":"orch-01","last_seen":"...","status":"live"}]}
```

---

## Board-Monitor SPA (S8 — ABS-240)

S8 ships a React single-page application served statically from the same Docker image as
the backend (spec §11, ADR-A-0021 §(c)). No separate frontend container is needed.
Source: `backend/apps/web/`. All board routes use an `HttpOnly` session cookie — not a
Bearer header.

### Session authentication

The login flow for board routes:

1. The user POSTs their bearer token to `POST /api/v1/session`. The server validates it
   and sets `Set-Cookie: session=<token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800`.
   The token does not appear in the URL or in `localStorage`.
2. The browser sends the session cookie automatically on every subsequent request, including
   the SSE `EventSource` (which uses `withCredentials: true`).
3. `GET /api/v1/session` returns the caller's `role` and `orgId`; the SPA calls it on load
   to decide whether to show the login form or the board.

`Secure` is appended to the cookie when `NODE_ENV=production`.

---

### `POST /api/v1/session`

Validates a bearer token and issues an `HttpOnly` session cookie.

**Authentication:** none (public; the token is validated here)

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`token`|string|yes|Bearer token issued by the backend|

**Response (200)**

```json
{ "ok": true, "role": "orchestrator" }
```

The `Set-Cookie` response header carries the session cookie.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`{"error":"missing_token"}`|`token` absent or empty|
|`401`|`{"error":"invalid_token"}`|Token fails auth|

**Example**

```bash
curl -c cookies.txt -X POST http://localhost:8420/api/v1/session \
  -H 'content-type: application/json' \
  -d '{"token":"my-bearer-token"}'
# -> {"ok":true,"role":"orchestrator"}
```

---

### `POST /api/v1/logout`

Clears the session cookie (`Max-Age=0`).

**Authentication:** cookie session (or none — always succeeds)

**Response (200)**

```json
{ "ok": true }
```

---

### `GET /api/v1/session`

Returns the current session's role and org. The SPA calls this on load.

**Authentication:** cookie session required

**Response (200)**

```json
{ "authenticated": true, "role": "orchestrator", "orgId": "org-uuid" }
```

**Errors:** `401` when no valid session cookie is present.

---

### `GET /api/v1/projects`

Lists every project in the authenticated session's org (selector metadata only:
`key` + `name`).

**Authentication:** human dashboard session required — `requireDashboardRead`
(roles `admin`/`viewer`/`maintainer`, `via === "session"`). Machine roles
(`agent`/`orchestrator`) and human-role bearer tokens are rejected `403`, matching
the rest of the dashboard read surface (ABS-442).

**Response (200)**

```json
{ "projects": [{ "key": "ABS", "name": "My project" }] }
```

**Errors:** `401` no valid session; `403` an authenticated non-human-session principal.

---

### `GET /api/v1/projects/:project/board`

Returns the board projection: workflow-derived column groups and all ticket cards for
the project.

**Authentication:** cookie session required

**Path parameter:** `:project` — project key

**Response (200)**

```json
{
  "project": "ABS",
  "columns": [
    { "group": "Backlog",                     "statuses": ["Backlog"] },
    { "group": "Epic Pipeline",               "statuses": ["Refinement", "Stories In Flight", "..."] },
    { "group": "Story Pipeline",              "statuses": ["Ready for Development", "In Progress", "..."] },
    { "group": "Blocked / Needs PO Decision", "statuses": ["Blocked", "Needs PO Decision"] },
    { "group": "Done",                        "statuses": ["Done"] }
  ],
  "tickets": [
    {
      "key": "ABS-123",
      "type": "ticket",
      "title": "My ticket",
      "status": "In Progress",
      "role": "fe-developer",
      "flags": ["design"],
      "labels": ["orchestrator-ready"],
      "assignee": null,
      "priority": "high",
      "status_age_seconds": 3600
    }
  ]
}
```

**Column derivation (AC2)**

The five column groups come from `boardColumns()` (`backend/packages/core/src/board.ts`),
which reads the registered workflow at call time and derives group membership from
structural properties (each status's `pipeline` marker, fan-in, and fan-out). No status
name is hardcoded in the server or the SPA. Renaming a status in `statuses.yaml` reshapes
the columns automatically on the next board fetch.

**Ticket ordering**

Tickets order priority-descending (`hotfix > high > normal > low`), then oldest-created
first, then by key. The full sorted list is returned; the SPA places each card into the
column whose `statuses` array contains the ticket's current status.

**Priority display (SCOPE-APPEND, operator 2026-07-13)**

|Priority|Card appearance|
|---|---|
|`hotfix`|Colour-coded `hotfix` badge|
|`high`|Colour-coded `high` badge|
|`normal`|No badge|
|`low`|No badge; card dimmed (`.low` CSS class)|

**Errors:** `401` no valid session; `404` project not found in the caller's org.

---

### `GET /api/v1/projects/:project/items/:key` (dashboard)

Returns structured JSON for the ticket detail drawer. This differs from the S3
text/plain route at `/agent/v1/…`; both routes read the same rows but serve different
consumers.

**Authentication:** cookie session required

**Path parameters:** `:project` — project key; `:key` — work-item key

**Response (200)**

```json
{
  "frontmatter": {
    "id": "ABS-123",
    "type": "ticket",
    "title": "My ticket",
    "status": "In Progress",
    "role": "fe-developer",
    "priority": "normal"
  },
  "body": "## Goal\n\nAdd the login flow.\n",
  "comments": [
    {
      "at": "2026-07-16T10:00:00Z",
      "kind": "handoff",
      "actor": "fe-developer",
      "body": "Implementation complete."
    }
  ],
  "allowed_transitions": ["Merging", "Blocked", "Needs PO Decision"]
}
```

`frontmatter` contains every field from the canonical render. `comments` is the full
chronological timeline, including `transition-reason` events projected from the event
log. All 10 comment kinds appear; the SPA renders a `kind` badge on each and applies
extra emphasis (`.emphasized` CSS class) to `handoff` and `decision` comments.

`allowed_transitions` (added S9 — ABS-241) is the list of legal next statuses for
the item's current status, derived from the registered workflow at call time. The
drawer's transition dropdown is pre-populated with this list and never offers an
illegal edge.

**Errors**

|Status|Body|Cause|
|---|---|---|
|`401`|`{"error":"unauthorized"}`|No valid session cookie|
|`404`|`{"error":"not_found"}`|Item or project not found in the caller's org|

---

### SPA — `backend/apps/web/`

The React SPA is built with Vite and served by `@fastify/static` from the same server
process. The SSE feed (`GET /api/v1/projects/:project/events/stream`, see
[SSE stream (S4)](#sse-stream-s4--abs-236)) drives live card updates; the SPA passes
`{ withCredentials: true }` to `EventSource` so the session cookie goes with every
reconnect automatically.

**End-to-end suite**

```bash
# Requires a running server at port 8478
cd backend/apps/web && pnpm e2e
```

`e2e/board.spec.ts` covers: Login → project selection → board render → SSE live-update
(< 5 s) → ticket status change → detail drawer → comment timeline with `.emphasized`
class on decision comments.

**Production build (no external CDN)**

```bash
pnpm --filter @agentic-backend/web build
# dist/assets/index-*.js   ~152 kB  (no CDN reference)
# dist/assets/index-*.css   ~5 kB
```

---

## Human Actions — Board Write Surface (S9 — ABS-241)

S9 adds the operator's write surface: an escalation inbox that surfaces the four
human-touchpoint statuses and four write endpoints that route through the same core
engine and event log as the agent ops. Every write records `actor=human`. All write
endpoints require a writer role (`admin` or `maintainer`) **and** a genuine session
cookie — a bearer token with those roles is rejected `403` (ABS-413 mechanism gate).

### Role matrix (S9 write endpoints)

|Caller|Write endpoints (`POST`/`PATCH` on `/api/v1/…`)|
|---|---|
|`admin` / `maintainer` session (cookie)|Allowed — `actor=human` recorded on every write|
|`admin` / `maintainer` bearer token|`403 forbidden` — mechanism check (ABS-413)|
|`viewer` session|`403 forbidden`|
|`agent` / `orchestrator` bearer token|`403 forbidden`|
|no credentials|`401 unauthorized`|

The allowlist is fail-closed: a new role added later is denied write by default.
`viewer` can reach all S8 read routes (board, detail, inbox, SSE) but none of the
S9 write routes.

---

### `GET /api/v1/projects/:project/inbox`

Returns all items currently in a human-touchpoint status, oldest (longest
time-in-status) first, each with its latest comment.

**Authentication:** cookie session required (any role)

**Path parameter:** `:project` — project key

**Human-touchpoint statuses** (phase 1, status-based; ABS-313 (24) deferred):

|Status|Human action|
|---|---|
|`Blocked`|Unblock or escalate|
|`Needs PO Decision`|Record a product decision|
|`Ready for Epic Acceptance`|Sign off or reject the epic|
|`Ready for Human Acceptance`|Approve the story for release|

**Response (200)**

```json
{
  "items": [
    {
      "key": "ABS-241",
      "type": "ticket",
      "title": "Backend S9: Board-Eingriffe",
      "status": "Blocked",
      "role": "fe-developer",
      "status_age_seconds": 7200,
      "latest_comment": {
        "kind": "decision",
        "actor": "po-agent",
        "at": "2026-07-16T10:00:00Z",
        "body": "Held in Blocked — dependency gate not yet clear."
      }
    }
  ]
}
```

`status_age_seconds` — seconds since the last transition event (fallback: item
creation). Determines the oldest-first ordering. `latest_comment` is `null` when
the item has no comments.

**Errors:** `401` no valid session; `404` project not found.

**Example**

```bash
curl -b cookies.txt \
  http://localhost:8420/api/v1/projects/ABS/inbox
```

---

### `POST /api/v1/projects/:project/items/:key/transition` (human)

Transitions a ticket. Runs through the same CAS engine as the agent endpoint
(`POST /agent/v1/…/transition`) — same legality check, same event log, same SSE
publish. Always records `actor=human`.

**Authentication:** cookie session, writer role required (`admin` / `maintainer`)

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`to`|string|yes|Target status|
|`reason`|string|yes|Rationale (non-empty)|
|`expect_from`|string|no|CAS guard — current status the drawer displayed; a concurrent peer move yields `409`|

`expect_from` maps to `allowed_transitions` from the detail endpoint: the drawer
pre-fills it so a peer that moved the ticket first yields `409 cas_mismatch`
(conflict UI), never a silent overwrite (AC2).

A successful transition is published to the SSE bus; open board tabs see the card
move without a reload (AC1).

**Response (200)**

```json
{ "ok": true, "from": "Blocked", "to": "In Progress" }
```

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`400`|`missing_field`|`to` or `reason` absent or empty|
|`400`|`illegal_transition`|Target not in `allowed_transitions`; response includes `allowed` list|
|`403`|`forbidden`|Non-writer session role|
|`404`|`not_found`|Item or project not found|
|`409`|`cas_mismatch`|Ticket already left `expect_from`; conflict UI, not a silent overwrite|

**Example**

```bash
curl -b cookies.txt -X POST \
  -H 'content-type: application/json' \
  -d '{"to":"In Progress","reason":"Unblocking — ABS-240 is Done","expect_from":"Blocked"}' \
  http://localhost:8420/api/v1/projects/ABS/items/ABS-241/transition
# -> {"ok":true,"from":"Blocked","to":"In Progress"}
```

---

### `POST /api/v1/projects/:project/items/:key/comments` (human)

Posts a comment from the board drawer. Restricted to `decision` and `notification`
kinds. Always records `actor=human`.

**Authentication:** cookie session, writer role required (`admin` / `maintainer`)

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`kind`|string|yes|`decision` or `notification`|
|`body`|string|yes|Comment text (may be empty)|

**Response (201)**

```json
{ "ok": true }
```

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`400`|`missing_field`|`kind` or `body` absent|
|`400`|`bad_comment_kind`|`kind` outside `["decision","notification"]`; response includes `allowed` list|
|`403`|`forbidden`|Non-writer session role|
|`404`|`not_found`|Item or project not found|

**Example**

```bash
curl -b cookies.txt -X POST \
  -H 'content-type: application/json' \
  -d '{"kind":"decision","body":"Approved for release."}' \
  http://localhost:8420/api/v1/projects/ABS/items/ABS-241/comments
# -> 201 {"ok":true}
```

---

### `PATCH /api/v1/projects/:project/items/:key/labels`

Sets the ticket's full label set. The board drawer uses this for both free labels and
the release toggle.

**Release toggle (`orchestrator-ready`):** writing this label maps to
`orchestration_state = 'eligible'` with an audit event; removing it maps to
`excluded`. The label is never stored in a table — it is projected at read time (see
[Entity Ops](#entity-ops-s3--abs-235)). The board does not offer `orchestrator-ready`
as a free label; it is available only via the dedicated release toggle (AC3,
v3-Design-Constraint). The `PATCH /agent/v1/…` `labels` write does the same mapping,
so a direct agent write of `orchestrator-ready` also sets the field correctly.

Routes through the same `updateItem` path as the agent PATCH. Always records
`actor=human`.

**Authentication:** cookie session, writer role required (`admin` / `maintainer`)

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`labels`|string[]|yes|Full desired label set after the toggle|

**Response (200)**

```json
{ "ok": true }
```

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`400`|`missing_field`|`labels` absent or not an array|
|`400`|label vocab error|A label fails the `[A-Za-z0-9._:-]+` pattern|
|`403`|`forbidden`|Non-writer session role|
|`404`|`not_found`|Item or project not found|

**Example — release toggle**

```bash
# Enable orchestration (orchestration_state=eligible, audit event)
curl -b cookies.txt -X PATCH \
  -H 'content-type: application/json' \
  -d '{"labels":["orchestrator-ready"]}' \
  http://localhost:8420/api/v1/projects/ABS/items/ABS-241/labels
# -> {"ok":true}

# Disable (orchestration_state=excluded, audit event)
curl -b cookies.txt -X PATCH \
  -H 'content-type: application/json' \
  -d '{"labels":[]}' \
  http://localhost:8420/api/v1/projects/ABS/items/ABS-241/labels
# -> {"ok":true}
```

---

## Knowledge Surface — Phase 3 (ABS-231)

Phase 3 adds ADR and policy entities to the backend. Every route in this section
carries a human-only boundary callout where it applies.

> **ADR-A-0004 guardrail:** ADR acceptance (`Proposed → Accepted`) and all policy
> writes are Human acts. Agent and orchestrator tokens receive `403` on those paths.
> No Phase-3 entity carries `orchestrator-ready`; the DB-level CHECK prevents it.

---

### `POST /api/admin/import/adrs` (S2 — ABS-379)

Import a tar of ADR markdown files (`adrs/agentic/*.md`) as `adr` work items.
Idempotent on re-import. Fails closed on unknown `status` frontmatter or an
`id` that violates `^[A-Za-z0-9._-]{1,64}$` (ABS-423).

**Authentication:** admin token required

**Query parameter:** `project` — project key (required)

**Request body:** `Content-Type: application/x-tar` — ustar tar stream

BSD-tar AppleDouble sidecars (`._*.md`) are silently skipped. Non-`.md` members
are ignored. Missing `id` frontmatter aborts that file before touching the DB.
A malformed `id` (charset violation) is treated identically: the file is skipped,
an error entry is added to `errors`, and sibling files continue.

**Frontmatter field mapping**

|Frontmatter key|Maps to|Notes|
|---|---|---|
|`id`|`work_item.key`|Must match `^[A-Za-z0-9._-]{1,64}$`; violation → 422 fail-closed|
|`title`|`work_item.title`|—|
|`status`|`work_item.status` (see status map below)|—|
|`date` / `adr_date`|`work_item.fields['adr_date']`|—|
|`scope` / `adr_scope`|`work_item.fields['adr_scope']`|—|
|`supersedes`|`work_item.fields['supersedes']` + `work_item_link` write|—|

**Status mapping (case-insensitive)**

|Frontmatter `status`|`work_item.status`|
|---|---|
|`draft`|`Draft`|
|`proposed`|`Proposed`|
|`accepted`|`Accepted`|
|`superseded`|`Superseded`|
|anything else|`422` — fail-closed|

**Response (200) — all files imported:**

```json
{ "imported": 3, "keys": ["ADR-A-0001", "ADR-A-0002", "ADR-A-0003"] }
```

**Response (422) — partial failure (unknown status or invalid id charset):**

```json
{
  "imported": 2,
  "keys": ["ADR-A-0001", "ADR-A-0003"],
  "errors": [
    {
      "file": "ADR-A-0002-my-decision.md",
      "error": "ADR ADR-A-0002: unknown status 'in-progress' — fail closed (allowed: draft, proposed, accepted, superseded)"
    },
    {
      "file": "ADR-BAD.md",
      "error": "ADR id 'My Decision!' violates the allowed charset ^[A-Za-z0-9._-]{1,64}$ — fail closed"
    }
  ]
}
```

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`{ "error": "project query parameter is required" }`|`?project=` absent|
|`400`|`{ "error": "send a tar body with Content-Type: application/x-tar" }`|wrong Content-Type|
|`403`|`{ "error": "forbidden" }`|non-admin token|
|`404`|`{ "error": "no such project" }`|project key not found in caller's org|

**Example**

```bash
TOKEN=$BACKEND_BOOTSTRAP_TOKEN
BASE=http://localhost:8420

tar -cf - adrs/agentic/*.md | \
  curl -sf -X POST "$BASE/api/admin/import/adrs?project=ABS" \
    -H "authorization: Bearer $TOKEN" \
    -H 'content-type: application/x-tar' \
    --data-binary @-
# -> {"imported":22,"keys":["ADR-A-0001","ADR-A-0002",...]}
```

See `docs/sop/ADR-IMPORT-RUNBOOK.md` for the full operator runbook including
`supersedes:` frontmatter wiring and idempotency details.

---

### ADR `→ Accepted` transition guard (human-only, ADR-A-0004)

The transition service enforces a fail-closed allowlist on any request to move an
`adr` item to `Accepted`. Principals with role `admin` or `maintainer` succeed;
every other caller receives `403`:

```
403 { "error": "forbidden", "reason": "ADR acceptance is a human-only action (ADR-A-0004)" }
```

This applies to both the agent endpoint (`POST /agent/v1/…/transition`) and the
human dashboard endpoint (`POST /api/v1/…/transition`). There is no UI path that
bypasses it — the guard runs in the transition service before the CAS check.

---

### `GET /agent/v1/projects/:project/policies` (S4 — ABS-381)

Read-only effective-policy op on the agent surface. Returns the Org ∪ Project active
policy set rendered as text, followed by a `policy_rev: <sha256>` line. Only `active`
policies participate; `draft` and `retired` are excluded.

**Authentication:** agent or orchestrator token (Bearer)

**Query parameter:** `audience` (optional) — role token (e.g. `be-developer`).
Omit to return the all-audiences union.

**Response (200):** `text/plain; charset=utf-8`

```
# Commit message policy
Use conventional commits: type(scope): description [TICKET-ID].

# Code review policy
All PRs require one reviewer approval before merge.

policy_rev: 3a1b2cd4ef567890abcdef1234567890abcdef12
```

The rendered text block ends with `\n` before the `policy_rev:` line. When no
active policy applies, the body is:

```
(no applicable policy)
policy_rev: <hash of the empty-render constant>
```

**Reserved markers (ABS-425 — trust-boundary hardening).** The `policy_rev:`
header line and any `=== … ===` section-marker line are **reserved** by the op's
output framing and MUST NOT appear in rendered policy **body** text. Those forms
are how a spawn packet carries the revision hash (`policy_rev: <sha256>`) and
delimits sections (`=== POLICY (policy_rev: …) ===`, `=== TICKET ===`); a body
line beginning `policy_rev:` or matching `=== … ===` could forge a revision hash
or a packet section boundary when injected. A policy source whose rendered text
would emit such a line is a **contract violation**: the op MUST fail loudly at
render time (non-zero exit / no forged output) rather than emit corrupting text.
Policy text is trusted today (human-authored; agent writes are `403`), so this
cannot occur now — the reservation locks the boundary before the Phase-3
policy-authorship surface matures.

**Line-terminator-parity invariant (ABS-432 CR-parity, generalized by ABS-441 —
defense-in-depth).** The render-time guard and any marker **consumer** (the
`build_packet` extraction) MUST stay in provable parity on **all line-terminator**
handling, not just LF. Two mechanisms enforce this:

- **Carriage return (`\r`, ABS-432).** The guard tests each line with its `\r`
  characters stripped, so a CRLF-terminated or CR-obfuscated reserved marker
  (`=== TICKET ===\r`, `policy_rev:\r`) is rejected exactly as its bare form is — the
  guard sees what a CR-stripping consumer (`tr -d '\r'`) would see.
- **Non-LF Unicode line terminators (NEL `U+0085`, LS `U+2028`, PS `U+2029`, ABS-441).**
  The guard splits the rendered body on LF only, so it additionally **fails loud when the
  rendered body embeds any of these terminators**. A lenient, Unicode-line-aware consumer
  could split on one of them and resolve a reserved marker that an LF-only guard would
  miss; rejecting their presence at render time keeps guard and consumer in parity. A
  well-formed policy body carries none of them, so clean input renders byte-identically.

This keeps the boundary fail-closed if the policy trust model later loosens **and** a more
lenient (CR-stripping or Unicode-line-aware) marker consumer is introduced; the guard
cannot silently diverge from the consumer on any line-terminator handling.

**No writes.** No events are emitted. Policy changes happen only on the human CRUD
surface (see below); this route is read-only for agents (ADR-A-0004).

**Errors**

|Status|Body|Cause|
|---|---|---|
|`401`|—|Missing or invalid token|
|`404`|`{ "error": "not_found" }`|Project not found in caller's org|

**Example**

```bash
# All-audiences effective policy
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8420/agent/v1/projects/ABS/policies

# Role-specific effective policy
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8420/agent/v1/projects/ABS/policies?audience=be-developer"
```

**Adapter op**

```bash
# backend-tracker.sh wrapper
backend-tracker.sh policies                        # all audiences
backend-tracker.sh policies --audience be-developer
```

---

### Human Policy CRUD (S3 — ABS-380)

> **Human-only (ADR-A-0004 / ABS-413):** every write route below requires a session
> cookie with role `admin` or `maintainer`. A bearer token — even one with role
> `admin`/`maintainer` — is rejected `403` (mechanism check; `routes/guards.ts`
> `requireHuman`). No agent-surface write route for policies exists.

All routes are under `/api/v1/projects/:project/policies`. The `project` id comes
from `principal.targetProjectId` (caller's own org); a foreign-org policy id is
not-found (`404`), never forbidden.

**Session exchange:**

```bash
curl -sS -X POST https://host/api/v1/session \
  -H 'content-type: application/json' \
  -d '{"token":"<human-token>"}' -c cookies.txt
```

**Authorization outcomes on write routes**

|Caller|Result|
|---|---|
|`admin` / `maintainer` human session|`200` / `201`|
|`admin` / `maintainer` bearer token|`403` — mechanism check (ABS-413)|
|`viewer` session|`403`|
|agent token (Bearer)|`403`|
|orchestrator token (Bearer)|`403`|
|no credentials|`401`|

The response `policy` object shape for all routes:

```json
{
  "id": "uuid",
  "orgId": "uuid",
  "projectId": "uuid",
  "key": "commit-style",
  "audience": "be-developer",
  "title": "Commit style",
  "body": "Use conventional commits.",
  "status": "active",
  "revision": 1,
  "created": "2026-07-18T00:00:00Z",
  "updated": "2026-07-18T00:00:00Z"
}
```

Every create, update, and status change writes a `policy_revision` snapshot and
appends one `kind='policy'` event on the global seq (same audit spine as ticket
writes). A create→update→status sequence yields three revisions and three events.

---

#### `GET /api/v1/projects/:project/policies`

List the project's policies, ordered `(audience NULLS FIRST, key)`.

**Authentication:** human writer session

**Response (200):** `{ "policies": [ { … }, … ] }`

---

#### `GET /api/v1/projects/:project/policies/:id`

Read one policy by id, scoped to the caller's org + project.

**Authentication:** human writer session

**Response (200):** `{ "policy": { … } }`
**Response (404):** `{ "error": "not_found" }`

---

#### `POST /api/v1/projects/:project/policies`

Create a project-scoped policy. `key` and `title` are required.

**Authentication:** human writer session required (admin / maintainer)

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`key`|string|yes|Topic slug — the override unit for Org ∪ Project resolution|
|`title`|string|yes|Display title|
|`audience`|string|no|Role token (e.g. `be-developer`) or `null` = all audiences|
|`body`|string|no|Canonical markdown; default `""`|
|`status`|string|no|`draft` (default), `active`, or `retired`|

**Response (201):** `{ "policy": { … } }` (`revision: 1`)

**Errors**

|Status|Body|Cause|
|---|---|---|
|`400`|`{ "error": "missing_field", "required": ["key","title"] }`|`key` or `title` absent|
|`400`|`{ "error": "bad_status", "allowed": ["draft","active","retired"] }`|Unknown status|
|`403`|`{ "error": "forbidden" }`|Non-writer session|

**Example**

```bash
curl -b cookies.txt -X POST \
  -H 'content-type: application/json' \
  -d '{"key":"commit-style","title":"Commit style","audience":"be-developer","body":"Use conventional commits.","status":"active"}' \
  http://localhost:8420/api/v1/projects/ABS/policies
# -> 201 {"policy":{...,"revision":1}}
```

---

#### `PATCH /api/v1/projects/:project/policies/:id`

Update `title` and/or `body`. At least one field is required. Bumps `revision`.

**Authentication:** human writer session required

**Request body (JSON):** `{ "title": "…", "body": "…" }` (one or both)

**Response (200):** `{ "policy": { … } }` (revision incremented)

**Errors:** `400` missing field; `403` non-writer; `404` not found

---

#### `POST /api/v1/projects/:project/policies/:id/status`

Change status only — activate, retire, or return to draft. Bumps `revision`.

**Authentication:** human writer session required

**Request body (JSON):** `{ "status": "active" }` (`draft` | `active` | `retired`)

**Response (200):** `{ "policy": { … } }` (revision incremented)

**Errors:** `400` bad status; `403` non-writer; `404` not found

---

#### `GET /api/v1/projects/:project/policies/effective`

Preview the effective-policy resolution for the editor UI (ABS-383). Returns the
same resolution as the agent op but as JSON.

**Authentication:** human writer session

**Query parameter:** `audience` (optional) — role token

**Response (200):**

```json
{ "rendered": "# Commit style\n…\n", "policy_rev": "3a1b2c…" }
```

---

## Command Queue (ABS-348 / ABS-354 / ABS-439)

The command queue delivers control commands from an authenticated human operator to a
live orchestrator instance. The board's Seat Drawer issues `stop-run` or `abort-spawn`
commands; the shipper polls for them and posts a receipt. Every step appends a
`kind='command'` audit event with `actor='human'`.

### Auth split

Two route prefixes, two auth models:

|Surface|Prefix|Auth|Roles|
|---|---|---|---|
|Enqueue + status read|`/api/v1/…`|HttpOnly cookie session|`admin`, `maintainer`|
|Poll + receipt|`/agent/v1/…`|Bearer token|Orchestrator token, own instance only|

`requireHuman` rejects agent/orchestrator tokens and `viewer` sessions (`403`).
The poll/receipt paths reject any token whose `label` ≠ `:id` (`403` cross-instance
reject).

### Command object

All command routes return objects of this shape:

```json
{
  "id": "uuid",
  "instance": "orch-01",
  "kind": "stop-run",
  "ledgerId": null,
  "state": "pending",
  "execCount": 0,
  "result": null,
  "reason": "Wrong epic branch targeted.",
  "created": "2026-07-18T15:30:00Z"
}
```

|Field|Type|Description|
|---|---|---|
|`id`|`string`|Command UUID|
|`instance`|`string`|Target orchestrator instance|
|`kind`|`"stop-run" \| "abort-spawn"`|Command type|
|`ledgerId`|`string \| null`|Spawn ledger id — set only for `abort-spawn`|
|`state`|`"pending" \| "delivered" \| "executed" \| "failed"`|Lifecycle state|
|`execCount`|`number`|Terminal receipts recorded|
|`result`|`string \| null`|Outcome text from the shipper|
|`reason`|`string \| null`|Operator rationale (ABS-439); `null` when `reason` was blank or absent|
|`created`|ISO-8601 UTC string|Enqueue timestamp|

---

### `POST /api/v1/projects/:project/orchestrators/:instance/commands`

Enqueue a control command. Submitting the same `idempotency_key` a second time returns
the existing command without appending a second audit event. Supply `reason` for
destructive commands — the operator's confirm-dialog rationale is persisted verbatim
to `orch_command.reason` and surfaced on every command read-back (ABS-439).
`reason` is nullable; omitting it or submitting a blank string stores `null`.

**Authentication:** human cookie session, `admin` or `maintainer` required

**Path parameters**

|Parameter|Description|
|---|---|
|`project`|Project key|
|`instance`|Orchestrator instance id|

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`kind`|string|yes|`"stop-run"` or `"abort-spawn"`|
|`reason`|string|no|Operator rationale — persisted verbatim to `orch_command.reason`; blank or absent stores `null`|
|`ledger_id`|string|`abort-spawn` only|Spawn ledger id to abort|
|`idempotency_key`|string|no|Client key for safe retries; absent → server generates a UUID|

**Response (201 — new command)**

```json
{ "command": { "id": "…", "kind": "stop-run", "state": "pending", "reason": "…" }, "created": true }
```

**Response (200 — idempotent hit)**

```json
{ "command": { … }, "created": false }
```

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`400`|`bad_kind`|`kind` outside `["stop-run","abort-spawn"]`|
|`400`|`abort-spawn requires ledger_id`|`kind=abort-spawn` with no `ledger_id`|
|`400`|`stop-run must not carry ledger_id`|`kind=stop-run` with a `ledger_id`|
|`403`|`forbidden`|Non-human or viewer session|
|`404`|`not_found`|Project not found in caller's org|

**Example**

```bash
curl -b cookies.txt -X POST \
  -H 'content-type: application/json' \
  -d '{"kind":"stop-run","reason":"Wrong epic branch targeted — stopping now."}' \
  http://localhost:8420/api/v1/projects/ABS/orchestrators/orch-01/commands
# -> 201 {"command":{"id":"…","kind":"stop-run","state":"pending","reason":"Wrong epic branch targeted — stopping now.","created":"…"},"created":true}
```

---

### `GET /api/v1/projects/:project/orchestrators/:instance/commands`

Returns all commands for the instance, newest first. The board uses this to show
delivery and execution status.

**Authentication:** human cookie session, `admin` or `maintainer` required

**Response (200)**

```json
{ "commands": [ { "id": "…", "kind": "stop-run", "state": "executed", "reason": "…" } ] }
```

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`403`|`forbidden`|Non-human or viewer session|
|`404`|`not_found`|Project not found|

---

### `GET /agent/v1/orchestrators/:id/commands`

Poll pending and delivered commands for the calling instance. Flips every `pending`
command to `delivered` (with an audit event) and returns all non-terminal commands.
A re-poll after a lost response redelivers the same set (at-least-once).

**Authentication:** orchestrator Bearer token; token `label` must match `:id`

**Path parameter:** `:id` — orchestrator instance id

**Response (200)**

```json
{ "commands": [ { "id": "…", "kind": "stop-run", "state": "delivered", "reason": "…" } ] }
```

Empty array when no non-terminal commands exist. The `reason` field lets the shipper
log the operator's rationale.

---

### `POST /agent/v1/orchestrators/:id/commands/:cmdId/receipt`

Record a terminal receipt (`executed` or `failed`). Only the first terminal move
increments `exec_count` and writes an audit event; a duplicate receipt is a silent
no-op returning the settled command.

**Authentication:** orchestrator Bearer token; token `label` must match `:id`

**Path parameters:** `:id` — instance; `:cmdId` — command UUID

**Request body (JSON)**

|Field|Type|Required|Description|
|---|---|---|---|
|`state`|string|yes|`"executed"` or `"failed"`|
|`result`|string|no|Outcome summary|

**Response (200)**

```json
{ "command": { … }, "settled": true }
```

`settled: false` on an already-settled command (idempotent no-op).

**Errors**

|Status|`error`|Cause|
|---|---|---|
|`400`|`bad_state`|`state` outside `["executed","failed"]`|
|`403`|`forbidden`|Token `label` ≠ `:id`|
|`404`|`not_found`|Command id not found in this instance's scope|

**Example**

```bash
curl -X POST \
  -H "Authorization: Bearer $SEAT_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"state":"executed","result":"Orchestrator stopped cleanly."}' \
  http://localhost:8420/agent/v1/orchestrators/orch-01/commands/cmd-uuid/receipt
# -> {"command":{…},"settled":true}
```

---

### Schema — `010_command_reason.sql` (ABS-439)

```sql
ALTER TABLE orch_command ADD COLUMN reason text;
```

Nullable; no backfill. Existing rows and any future non-destructive-kind enqueues are
unaffected. The mandatory-ness for `stop-run` / `abort-spawn` is enforced at two
layers: the Seat Drawer confirm dialog (Confirm button disabled until non-empty) and
the server-side `reason_required` reject (defence-in-depth behind `requireHuman`).
The reason also appears in the enqueue audit event payload so the audit trail records
it in two places: the `orch_command.reason` column and the `event` row.

> **Follow-up ABS-447**: adds a server-side length cap and a DB `CHECK` constraint.
> Until ABS-447 ships, `reason` is bounded only by Fastify's default body limit (~1 MB).

---

## Related

- Spec: `specs/ABS-229-agentic-backend-phase1-spec.md` §2 (schema), §4 (routes + errors),
  §5 (canonical renderer), §6 (context packet + brief view, amended 2026-07-15),
  §7 (CLI adapter exit-code table), §8 (events + SSE), §9 (Docker packaging),
  §10 (import/export), §11 (board-monitor SPA), §12 (test plan)
- ADR: `ADR-A-0021` §(c) API/canonical text, §(a)(2) event cursor, §(d) CLI seam,
  §(e) SSE, §(f) single orchestrator touch for S6 (`build_packet()` only), §(g) product shape
- ADR: `ADR-A-0010` — diff bounded to `build_packet()` + one probe helper
- Migration `003`: `backend/packages/core/src/migrations/003_orchestration_and_link_facets.sql`
- Golden fixtures: `backend/packages/core/test/` (shared with the mock suite)
- CLI adapter: `scripts/backend-tracker.sh` — S6 ops: `packet`, `get --brief`, `capabilities`; Phase-3 S4: `policies`
- Packet selectors: `backend/packages/core/src/packet/selectors/` (four TypeScript modules)
- Packet composer: `backend/packages/core/src/packet/compose.ts`
- Packet DB interface: `backend/packages/core/src/packet/PacketDb.ts`
- Packet cache tests: `tests/test-packet-cache.sh`
- Operator guide: `backend/README.md` (install, import, export, backup, restore)
- Compose lifecycle test: `backend/tests/compose-lifecycle.sh`
  (compose-up → import → export → restore → pg\_dump)
- Conformance suite: `tests/test-backend-tracker.sh` (122 assertions; mirrors `test-mock-tracker.sh` + S6 ops)
- Adapter lint: `tests/test-tracker-adapter-lint.sh`
- Board-monitor SPA: `backend/apps/web/` (source), `backend/apps/web/e2e/board.spec.ts` (Playwright E2E)
- Board column derivation: `backend/packages/core/src/board.ts` (`boardColumns`, `boardTickets`)
- Human write endpoints: `backend/apps/server/src/routes/dashboard.ts` (S9 — `escalationInbox`, transition, comment, labels)
- Escalation inbox query: `backend/packages/core/src/board.ts` (`escalationInbox`, `ESCALATION_INBOX_STATUSES`)
- Human write integration tests: `backend/apps/server/test/dashboard-routes.test.ts`
- Playwright E2E (S9 drawer + orchestrator poll): `backend/apps/web/e2e/board.spec.ts`
- Phase-3 knowledge migration: `backend/packages/core/src/migrations/009_knowledge_adr_policy.sql`
- ADR workflow: `backend/packages/core/src/workflows/adr-lifecycle.yaml`
- Policy service + resolver: `backend/packages/core/src/policies.ts`
- Policy human routes: `backend/apps/server/src/routes/policies.ts`
- ADR importer: `backend/packages/core/src/items.ts` (`importAdr`, `renderAdrItem`)
- ADR import route tests: `backend/apps/server/test/adr-import-routes.test.ts`
- Policy route tests: `backend/apps/server/test/policy-routes.test.ts`
- Knowledge guide: `docs/guides/AGENTIC-BACKEND-KNOWLEDGE.md`
- ADR-import runbook: `docs/sop/ADR-IMPORT-RUNBOOK.md`
- Phase-3 backend docs (`backend/docs/`): `knowledge-data-model.md`, `adr-import-api.md`, `policy-api.md`
- Command queue core: `backend/packages/core/src/commands.ts`
  (`enqueueCommand`, `pollCommands`, `recordReceipt`, `listCommands`)
- Command queue route: `backend/apps/server/src/routes/commands.ts` (`registerCommandRoutes`)
- Command queue migration: `backend/packages/core/src/migrations/010_command_reason.sql` (ABS-439)
- Command queue integration tests: `backend/apps/server/test/command-routes.test.ts` (20 tests; 3 cover ABS-439)
- Seat Drawer (board UI for enqueue + reason): `backend/apps/web/src/components/Orchestrators.tsx`
- Web API client (enqueueCommand): `backend/apps/web/src/api.ts`
