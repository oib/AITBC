# ABS-229 — Agentic Delivery Backend, Phase 1: Tracker Core (Spec)

**Epic:** ABS-229 · **Stories:** ABS-233…ABS-242 · **ADR:** ADR-A-0021 (proposed) ·
**Vision:** `specs/DRAFT-agentic-backend-vision.md`
**Date:** 2026-07-12 · **Amended:** 2026-07-15 (ABS-313 design constraints — see change markers `[A-313]`)
**Status:** groomed; S1/S2 delivered, S3/S4 restarted against this amended spec (Operator decision 2026-07-15)

> **[A-313] Amendment summary.** Comment kinds are the MIGRATION format, not the target data
> model (ABS-313 design constraint). Concretely: (a) transitions no longer write a
> `transition-reason` comment row — the reason lives on the transition event only, and the
> rendered comment block is a projection (§3, §5); (b) `orchestration_state` is a first-class
> column; the `orchestrator-ready` label is a rendered projection of it (§2, §4, §11);
> (c) search results are complete by contract — no silent truncation, pagination is
> encapsulated server-side (§4); (d) packet slot selection is encapsulated per slot (§6).

Phase-1 goal: a drop-in replacement for the Jira binding. Acceptance =
`scripts/backend-tracker.sh` passes the mock conformance assertions against a live backend
and an orchestrator run works with `TRACKER_CMD=scripts/backend-tracker.sh` unchanged.

Section numbers below are load-bearing: story ACs reference them (`Spec §N`).

---

## §1 Overview & workspace layout

One backend process (Node ≥ 22, TypeScript, Fastify) + Postgres 16, shipped via docker
compose. pnpm workspace:

```
backend/
├── packages/core/        # entities, type registry, workflow engine, event log, auth
├── packages/realtime/    # SSE fan-out, in-process event bus
├── apps/server/          # composes modules, serves /agent/v1, /api/v1, static SPA
├── apps/web/             # React SPA (kanban board), built to static assets
├── docker-compose.yml
└── Dockerfile
```

Dependency budget: no framework pulling > 5 transitive deps beyond Fastify/pg/zod/react.
Modules register routes, migrations, and event subscribers against `core`; they never import
each other directly (ADR-A-0021 §g). Phase-2+ modules (`forge`, `webhooks`, `telemetry`,
`policies`) plug into the same seams.

## §2 Data model (DDL)

All timestamps `timestamptz`, UTC. All tables carry `org_id`/`project_id` where applicable
(Phase-1 foundation 3).

```sql
CREATE TABLE org     (id uuid PRIMARY KEY, key text UNIQUE NOT NULL, name text NOT NULL);
CREATE TABLE project (id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES org,
                      key text NOT NULL, name text NOT NULL, config jsonb NOT NULL DEFAULT '{}',
                      UNIQUE (org_id, key));

-- Types are rows, not DDL (Phase-1 foundation 2).
CREATE TABLE entity_type (
  id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES org,
  key text NOT NULL,                 -- 'epic' | 'ticket' | 'subtask' (phase 1)
  field_schema jsonb NOT NULL,       -- JSON Schema validating work_item.fields
  workflow jsonb NOT NULL,           -- parsed statuses.yaml-format workflow (see §3)
  render jsonb NOT NULL,             -- canonical projection config (frontmatter order, sections)
  UNIQUE (org_id, key));

CREATE TABLE work_item (
  id uuid PRIMARY KEY,
  org_id uuid NOT NULL REFERENCES org, project_id uuid NOT NULL REFERENCES project,
  key text NOT NULL,                 -- 'ABS-123'; see key_sequence
  type_key text NOT NULL,
  title text NOT NULL, status text NOT NULL,
  parent_id uuid REFERENCES work_item,      -- denormalized fast path: parent/children/child-count
  role text, assignee text,
  flags text[] NOT NULL DEFAULT '{}',       -- validated closed set: design|security|data|skip-review|skip-test
  labels text[] NOT NULL DEFAULT '{}',      -- free-form exact-match tokens
  ac_blocking boolean,
  -- [A-313] first-class orchestration opt-in (ABS-313 (8)); the 'orchestrator-ready' label
  -- is a rendered projection of eligible, never a stored label (see §4, §11):
  orchestration_state text NOT NULL DEFAULT 'excluded'
    CHECK (orchestration_state IN ('eligible','paused','manual-only','excluded')),
  body text NOT NULL DEFAULT '',            -- canonical markdown sections, stored VERBATIM
  fields jsonb NOT NULL DEFAULT '{}',       -- type-specific, schema-validated
  revision int NOT NULL DEFAULT 1,
  created timestamptz NOT NULL, updated timestamptz NOT NULL,
  search tsvector GENERATED ALWAYS AS
    (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,''))) STORED,
  UNIQUE (project_id, key));
CREATE INDEX ON work_item USING gin (search);
CREATE INDEX ON work_item USING gin (fields);
CREATE INDEX ON work_item (project_id, status);
CREATE INDEX ON work_item (parent_id);
-- + pg_trgm index on title for phase-1 dedup similarity:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX ON work_item USING gin (title gin_trgm_ops);

CREATE TABLE work_item_link (
  from_id uuid NOT NULL REFERENCES work_item, to_id uuid NOT NULL REFERENCES work_item,
  kind text NOT NULL CHECK (kind IN ('depends-on','origin-review','pr','supersedes')),
  created timestamptz NOT NULL,
  PRIMARY KEY (from_id, to_id, kind));      -- parent-child lives on work_item.parent_id

CREATE TABLE comment (
  id bigserial PRIMARY KEY, item_id uuid NOT NULL REFERENCES work_item,
  -- [A-313] kind vocabulary = v2 COMPAT/MIGRATION format, not the target model. New rows of
  -- kind 'transition-reason' are never written by the backend itself (§3); the kind is kept
  -- in the CHECK only so the importer can ingest v2 tickets verbatim. Typed records for
  -- handoff/gate-results/follow-up/claim arrive with the ABS-313 schema amendment.
  kind text NOT NULL CHECK (kind IN ('understanding','transition-reason','gate-results',
    'handoff','decision','notification','follow-up','bsa-decision','skip','claim')),
  actor text NOT NULL, body text NOT NULL, at timestamptz NOT NULL);
CREATE INDEX ON comment (item_id, id);
-- append-only: no UPDATE/DELETE grants for the app role.

CREATE TABLE work_item_revision (
  item_id uuid NOT NULL REFERENCES work_item, revision int NOT NULL,
  body text NOT NULL, fields jsonb NOT NULL, actor text NOT NULL, at timestamptz NOT NULL,
  PRIMARY KEY (item_id, revision));         -- snapshot on every body/fields write (foundation 5)

CREATE TABLE event (
  seq bigserial PRIMARY KEY,                -- THE global cursor (foundation 1)
  org_id uuid NOT NULL, project_id uuid NOT NULL, item_id uuid,
  kind text NOT NULL,                       -- transition|comment|create|update|link|assign
  actor text NOT NULL, payload jsonb NOT NULL, at timestamptz NOT NULL);
CREATE INDEX ON event (project_id, seq);

CREATE TABLE consumer_cursor (
  consumer_id text NOT NULL,                -- "<token-id>:<instance-id>"
  project_id uuid NOT NULL, last_seq bigint NOT NULL DEFAULT 0,
  updated timestamptz NOT NULL, PRIMARY KEY (consumer_id, project_id));

CREATE TABLE key_sequence (project_id uuid NOT NULL, prefix text NOT NULL,
  next int NOT NULL, PRIMARY KEY (project_id, prefix));

CREATE TABLE auth_token (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid,   -- NULL = org-wide (human/admin)
  hash text NOT NULL,                       -- sha256; constant-time compare
  role text NOT NULL CHECK (role IN ('orchestrator','agent','admin','viewer','maintainer')),
  label text, last_seen timestamptz, created timestamptz NOT NULL);
```

Discipline: `body` is never parsed into columns. Only fields that agents filter on earn
columns or `fields` entries.

## §3 Workflow engine & resolution

- **Format**: the existing `profiles/neutral/adapters/statuses.yaml` shape (`- name:` /
  `next:` list + metadata) is the workflow definition language, unchanged.
- **Split**: the shipped file is imported as two named workflows, `epic-pipeline` and
  `story-pipeline`, sharing one status namespace per project. `Blocked` and
  `Needs PO Decision` cross-cutting semantics are preserved exactly.
- **Resolution**: `resolve(project, type_key) → workflow`, order **project override → org
  default → built-in**. Phase 1 ships only the built-in pair (foundation 6 = the resolution
  seam exists even if unused).
- **Boot**: parse failure of any configured workflow → fail fast with a log line naming the
  source (mounted file vs built-in). The repo file stays the single source of truth; the
  built-in copy is stamped at build time.
- **Transition service** (single transaction) **[A-313 amended]**:
  1. verify `to ∈ next[from]` for the item's resolved workflow — else `400` with the allowed
     list in the body;
  2. `UPDATE work_item SET status=$to, revision=revision+1, updated=now()
     WHERE id=$id AND status=$expect_from` — rowcount 0 → rollback, `409` (adapter renders
     the ABS-198 NOOP, §7);
  3. `INSERT event (kind='transition', payload={from,to,reason,actor})` — the reason lives
     HERE and only here; **no `transition-reason` comment row is written** (ABS-313 (10):
     the comment existed only because Jira has no visible transition metadata);
  4. post-commit: publish to the in-process bus (→ SSE).

  The mock-parity comment block (`### <at> | kind: transition-reason | actor: <actor>` +
  `Transition: <from> -> <to>. Reason: <reason>`) is synthesized at render time from the
  transition event (§5) — the timeline is a projection over comment rows and events, byte-
  identical to the mock output. Imported v2 `transition-reason` comment rows render as-is.

## §4 Agent API routes & error mapping

All under `/agent/v1/projects/:project`, bearer auth, responses `text/plain; charset=utf-8`
in the exact mock formats. `X-Orch-Instance` header carries `ORCH_INSTANCE_ID` when set.

| CLI op | Route | Notes |
|---|---|---|
| get | `GET /items/:key` | canonical markdown (§5); `?view=brief` see §6 |
| search | `GET /items?status=&type=&parent=&text=&label=` | terse `id⇥type⇥status⇥title` lines; **[A-313] complete by contract** — the response contains ALL matches (server pages internally) or fails with an explicit error; never a silent prefix (ABS-313 (9)); scale test ≥ 1000 items in the conformance suite |
| create | `POST /items` (type, title, prefix?, parent?, role?, flags?, labels?, ac_blocking?, body) | returns new key; status = `Backlog` |
| update | `PATCH /items/:key` | fields: title,type,parent,depends_on,links,flags,labels,ac_blocking; `status` present → `400`; **[A-313]** a label write adding/removing `orchestrator-ready` is mapped onto `orchestration_state` (eligible ↔ excluded) + audit event — the label is never stored (§11) |
| comment | `POST /items/:key/comments` (kind, actor, body) | kind outside vocab → `400` |
| transition | `POST /items/:key/transition` (to, actor, reason, expect_from?) | §3 semantics |
| link | `POST /items/:key/links` (other, kind) | idempotent — replay → `200` "already linked" |
| children | `GET /items/:key/children` | mock line format w/ status summary |
| parent | `GET /items/:key/parent` | parent key or empty line |
| child-count | `GET /items/:key/child-count` | integer line |
| events | `GET /events?since=<seq>` | §8 |
| assign | `POST /items/:key/assign` (accountId) | empty accountId = graceful no-op |
| packet | `GET /items/:key/packet` | §6 |
| capability probe | `GET /capabilities` | plain list of supported ops (`packet`, `brief`, …) |

**Error mapping** (HTTP → adapter, full table mirrored in §7):

| Case | HTTP | Body |
|---|---|---|
| unknown item | 404 | `no such ticket: <key>` |
| status via update | 400 | mock-identical message |
| illegal transition | 400 | `illegal transition <from> -> <to>; allowed: <list>` |
| CAS mismatch (`expect_from`) | 409 | current status in body |
| bad comment kind / bad flag | 400 | vocab list |
| auth | 401 / 403 | — |

## §5 Canonical rendering golden rules

`GET /items/:key` reproduces the mock format byte-for-byte:

1. YAML frontmatter, field order exactly as `mock-tracker.sh` writes it (`id, type, title,
   status, parent, role*, flags*, labels*, ac_blocking*, assignee*, depends_on, links,
   created, updated` — `*` = only-when-set).
2. Body sections verbatim as stored (Goal / Scope / Acceptance Criteria / Definition of
   Done / Test Plan / ADR Context).
3. `## Comments` with blocks `### <at> | kind: <kind> | actor: <actor>` + blank line + body.
   **[A-313]** This section is a PROJECTION: comment rows and transition events are merged
   chronologically; each transition event renders as a `kind: transition-reason` block with
   body `Transition: <from> -> <to>. Reason: <reason>` — byte-identical to the block the
   mock writes. Golden-file tests cover mixed timelines (imported v2 comment rows +
   backend-native transition events).
4. `depends_on`/`links` frontmatter arrays are rendered from `work_item_link` +
   `parent_id`. **[A-313]** `labels` renders `orchestrator-ready` iff
   `orchestration_state = 'eligible'` (projection, §2/§4).
5. Timestamps ISO-8601 Z, second precision — identical to mock.

**Golden-file tests**: shared fixtures with the mock suite (start: `work/tickets/DEMO-1.md`
plus fixtures covering every optional field and comment kind). `diff <(mock get)
<(curl …/items/X)` must be empty. Mock format changes now require updating fixtures for both
consumers (ADR risk 3).

## §6 Context packet & `get --brief`

`GET /items/:key/packet` returns, in order:

1. full frontmatter;
2. all body sections;
3. latest `handoff` comment (full block);
4. latest transition reason — **[A-313]** rendered from the latest transition EVENT (the
   backend writes no `transition-reason` comment rows, §3); an imported v2
   `transition-reason` comment row counts if it is the newest transition record;
5. latest `gate-results` comment **iff newer than the latest handoff**;
6. **all** `decision` and `bsa-decision` comments (oldest first);
7. breadcrumb: `(N ältere Kommentare weggelassen — vollständige Historie: tracker get <key>)`
   — only when N > 0.

Deterministic for a given item state: byte-stable per `updated` value, so the orchestrator's
packet cache keeps hitting. No byte cap needed — composition replaces truncation.
**[A-313]** Each packet slot (handoff / transition-reason / gate-results / decisions) is
selected by its own encapsulated selector function; today the selectors read comment kinds
(+ the transition event for the reason slot), later they switch to typed records without
changing the packet output format or the adapter (ABS-238 design constraint).

`?view=brief` (adapter: `get --brief`): frontmatter + Goal + Acceptance Criteria + latest
handoff. Intended consumers: dedup gate, intake classifier.

Orchestrator integration (ABS-238): `build_packet()` probes `tracker packet <id>` once per
run (via `GET /capabilities` in the adapter); on support, the packet body replaces the
`=== TICKET ===` dump; `ORCH_PACKET_MODE=full` (env, default `packet`) forces the legacy
path byte-identically. Adapters without the op (mock, jira) → automatic fallback.

## §7 CLI adapter `scripts/backend-tracker.sh`

Bash + curl, target < 300 lines. Env: `BACKEND_URL` (default `http://localhost:8420`),
`BACKEND_TOKEN`, `TRACKER_PROJECT` (project key), optional `ORCH_INSTANCE_ID` (sent as
`X-Orch-Instance`).

- Subcommand parsing identical to `mock-tracker.sh` (flags, `--body-file`, `--reason-file`,
  `--expect-from`, …).
- Responses printed verbatim (server already renders canonical text).
- Exit-code/stderr mapping:

| HTTP | Adapter behavior |
|---|---|
| 200/201 | print body, exit 0 |
| 404 | stderr `no such ticket: <key>`, exit ≠ 0 (mock-identical code) |
| 400 (status-via-update / illegal transition / vocab) | stderr mock-identical text, exit ≠ 0 |
| 409 (CAS) | **stdout ABS-198 NOOP line, exit 0** (matches mock `--expect-from` semantics) |
| 401/403 | stderr auth hint, exit ≠ 0 |
| network error | stderr, exit ≠ 0 (orchestrator outage machinery takes over) |

- `events`: calls `GET /events?since=` with the server-side cursor (adapter passes no local
  state; see §8). New optional subcommands: `packet <id>`, `get --brief <id>`; unknown
  subcommands fail exactly like the mock.
- Conformance: `tests/test-backend-tracker.sh` mirrors the `test-mock-tracker.sh` assertion
  set against a disposable compose stack; registered in `test-tracker-adapter-lint.sh`.
  Any diff = release blocker.

## §8 Events, consumer cursors, SSE

- `GET /agent/v1/projects/:p/events?since=<seq|auto>`: with `auto` (adapter default), the
  server reads/advances `consumer_cursor` for `(token, X-Orch-Instance)`. A numeric `since`
  is an explicit floor (`since=0` = the full history from seq 1; a non-numeric `since` is
  rejected `400 bad_since` — never a silent empty). Response: mock format, one line per
  **create OR transition** event `{ticket_id: X, from: A, to: B, at: T}`, followed by cursor
  advance. At-least-once; consumers dedup (`SEEN_EVENTS` in the orchestrator already does).
- **Create events are delivered (ABS-427)**: a freshly-created ticket surfaces as a creation
  line `{ticket_id: X, from: null, to: Backlog, at: T}` — parity with the mock's `events`,
  where a newly-appeared ticket is a creation event. This is what lets the event-driven
  orchestrator (`ORCH_REQUIRE_START_LABEL=0`) see new tickets; the transition-only feed left
  it blind to them and forced the label-sweep mode (`=1`). Decision: deliver create events
  (restores mock parity) rather than ratify transition-only.
- **Documented semantic difference vs mock**: mock `events` is a snapshot diff (A→B→C within
  one poll collapses); the backend emits every transition. The orchestrator dedups on
  `(ticket,to,at)` and re-reads ticket state before spawning (`ticket_still_in`), so
  multiple same-ticket events per batch are safe — a conformance case proves it
  (ABS-236 AC 2). Optional `?coalesce=1` returns exact mock parity (latest event per ticket)
  if the proof fails.
- Two consumers, two cursors: independent positions, no starvation (ADR risk 2).
- SSE `GET /api/v1/projects/:p/events/stream`: JSON events for the dashboard, `id:` = event
  seq, heartbeat comment every 15 s, `Last-Event-ID` resume. Long-poll `wait=` is Phase 4.

## §9 Docker packaging & install

- `Dockerfile`: multi-stage (build → `node:22-alpine` runtime), non-root user, `HEALTHCHECK
  CMD wget -qO- localhost:8420/healthz`, target < 200 MB.
- `docker-compose.yml`: services `backend` + `db` (`postgres:16-alpine`), named volume
  `backend-data` for pgdata, healthcheck-gated startup, single `.env` for
  `POSTGRES_PASSWORD` / `BACKEND_BOOTSTRAP_TOKEN`.
- Migrations embedded, auto-applied at startup, idempotent.
- Install path (verified in ABS-239, documented in ABS-242): `docker compose up` →
  bootstrap-token login on the board → create org/project → register orchestrator → export
  token into the consumer's env → `TRACKER_CMD=scripts/backend-tracker.sh`.
- Image tags follow boilerplate release tags (one-product coupling).

## §10 Data lifecycle & orchestrator registration

- **Import**: `POST /api/admin/import` (admin token) accepts mock-format markdown files
  (multipart or tar) → work_items + comments; `work/tickets/*.md` round-trips byte-identically
  (ABS-239 AC 2). Jira import: out of scope; documented unsupported one-liner
  (`jira-tracker.sh get` loop → import).
- **Export**: `GET /api/export` → tar of canonical `.md` per ticket — backup story and
  vendor-lock escape hatch. Restore = import of the export (tested).
- **Backup**: `pg_dump -Fc` documented; export-tar as the belt-and-braces.
- **Registration**: `POST /agent/v1/orchestrators` with the bootstrap token → project-scoped
  orchestrator token (stored hashed). Any authenticated call updates `last_seen`; the board
  shows live/stale per instance (threshold: 3× poll interval).

## §11 Dashboard views & human actions

Views (React SPA, served by the backend, session-cookie auth after token login — HttpOnly,
token never in URL/localStorage):

1. **Kanban** — column groups derived from the resolved workflow definitions (Backlog /
   epic pipeline / story pipeline / Blocked + Needs PO Decision / Done); cards: key, title,
   role, flags, assignee, time-in-status. No hardcoded status lists.
2. **Ticket detail drawer** — frontmatter, body, full comment timeline (kind badges;
   handoff/decision highlighted).
3. **Event feed** — live SSE tail, filterable by ticket/kind.
4. **Escalation inbox** — items in Blocked, Needs PO Decision, Ready for Epic Acceptance,
   Ready for Human Acceptance; oldest first; shows the latest escalation comment.
5. **Orchestrators** — registered instances, live/stale.

Human actions (all via `/api/v1`, `actor=human`, same transition engine/event log as agent
ops — one write path):

- transition: dropdown limited to legal next statuses, reason mandatory, `expect_from`
  prefilled from the rendered status (CAS conflict → conflict UI, never silent overwrite);
- comment (kinds `decision` / `notification`);
- **[A-313]** release toggle: writes `orchestration_state` (eligible/paused/manual-only/
  excluded) with an audit event — the Operator's release lever (ABS-101/208) is field-based;
  the `orchestrator-ready` label is only its rendered projection (§2/§4/§5). The generic
  label toggle covers free-form labels and does not offer `orchestrator-ready`;
- shortcuts: Unblock, Epic acceptance (preconfigured transitions).

Write endpoints require a human session; agent tokens are rejected (ABS-241 AC 4).
Merge-from-board is Phase 2 (ABS-230).

## §12 Conformance test plan

1. **Adapter parity**: `tests/test-backend-tracker.sh` = the `test-mock-tracker.sh`
   assertion set (CLI in/out, exit codes, stderr texts) against a disposable compose stack;
   wired into CI and `test-tracker-adapter-lint.sh`.
2. **Golden rendering**: byte-diff per op against mock output for shared fixtures (§5).
3. **Workflow walk**: every legal edge accepted, every illegal edge rejected, for the
   imported statuses.yaml (§3).
4. **Events**: multi-consumer cursors; same-ticket multi-event batch dispatch safety (§8).
5. **Packet**: composition matrix per comment constellation; `ORCH_PACKET_MODE=full`
   byte-parity with legacy `build_packet()` (§6).
6. **E2E smoke**: run-boilerplate driver `--once` cycle with
   `TRACKER_CMD=scripts/backend-tracker.sh` (dispatch → stub seat → transition observed).
7. **Lifecycle**: compose-up → import → export → restore round-trip (§10).

## §13 Out of scope (Phase 1)

Forge/PR mirror/merge-from-board and inbound webhooks (Phase 2, ABS-230); telemetry ingest
and report views (Phase 2); ADR/policy entity types and packet policy injection (Phase 3,
ABS-231); incident/support/runbook types, license enforcement, white-label, GitHub provider,
long-poll events (Phase 4, ABS-232). Also: sprints, estimates, worklogs, custom-field UI,
attachments, multi-org per install, webhook outbound, runtime type-creation UI, Jira
bidirectional sync, deleting `jira-tracker.sh`/`jira-sop` (they remain the Jira-profile
binding).
