# Agentic Delivery Backend — Vision & Phased Roadmap

**Status:** draft (design-first; governing decision record: `adrs/agentic/ADR-A-0021-agentic-delivery-backend.md`, proposed)
**Date:** 2026-07-12
**Origin:** Operator direction — replace the Jira binding with an agent-first backend that
becomes the boilerplate's central platform and ships with it as one product.

---

## 1. Problem

Jira works as a tracker binding, but it is built for humans, and every layer of that shows up
as overhead for an agent team:

| Overhead class | Today | Structural? |
|---|---|---|
| Data-model mismatch | `role`/`depends_on`/`links`/`flags`/`ac_blocking` label-encoded (`role:<x>`, `depends-on:<id>`), reconstructed on every `get` | yes |
| API cost | one JQL sweep per 15 s poll (deliberate budget), ADF/JSON payloads | yes |
| Context cost | interactive lane = Atlassian MCP (~40 tool schemas) + `jira-sop` skill ≈ 10–20k tokens/session | yes |
| Context quality | orchestrator packet embeds the full comment history, truncates body-tail-first at 32 KB — can silently cut acceptance criteria on bounced tickets | fixable only at the source |
| Product | the boilerplate cannot be sold self-contained while its tracker is customer-provided Jira | yes |

The foundation to build on already exists: **the boilerplate is tracker-agnostic.** All
ticket access goes through the 13-op CLI contract behind `$TRACKER_CMD`
(`profiles/neutral/adapters/task-tracking.md`); `scripts/mock-tracker.sh` is the reference
implementation and `tests/test-mock-tracker.sh` is a ready-made conformance suite. The
backend is a new binding behind the same seam — the 5000-line orchestrator does not change.

## 2. Vision

One backend, one container image (plus Postgres), sold with the boilerplate:

- **Everything runs through it**: tickets, orchestrator run logs and token/cost telemetry,
  ADRs, org-wide policies that projects inherit.
- **Multi-project, multi-orchestrator**: one backend manages many projects; each orchestrator
  instance registers, gets a project-scoped token, and consumes its own event cursor.
- **Agent-first API**: terse canonical text (the mock-tracker formats) rendered at the API
  edge; a server-composed context packet; no MCP anywhere.
- **Human = monitor + targeted intervention**: a realtime kanban board (SSE), an escalation
  inbox for exactly today's human touchpoints (Blocked, Needs PO Decision, Ready for Epic /
  Human Acceptance), and minimal actions — transition with reason, comment, label toggle,
  and **merge-from-board** via a backend-side Bitbucket integration (same human merge
  authority as today, new front door).
- **Open at the edges**: inbound HMAC webhooks with configurable mapping rules ("deploy
  finished → transition epic"), so external pipelines participate in the workflow without
  special orchestrator plumbing.
- **Extensible core**: an entity-type registry (types + workflows are data) so ops/support
  work — incidents, support cases, runbooks — lands as configuration, not a rewrite.

## 3. Architecture (decided in ADR-A-0021)

> Modular monolith (Node/TS, Fastify, one container) + Postgres 16 · JSONB entities with an
> entity-type registry · append-only event log with a global `bigserial` cursor · relational
> edges/comments · SSE push · canonical text rendered at the API edge.

### 3.1 SQL vs NoSQL — resolved

False dichotomy: Postgres JSONB **is** the document store (entities as objects, new types
without DDL migrations) inside a transactional engine. What NoSQL would give up is exactly
what this workload leans on: atomic CAS transitions (state + comment + event in one
transaction), a globally ordered event cursor (feed/audit/SSE/webhook channel in one), and
joins/integrity for hierarchy and the dedup gate (`tsvector` + `pg_trgm`). Full event
sourcing is likewise rejected — we keep the append-only log ("event-logged CRUD") and skip
replay/projections/upcasters. Also rejected: MongoDB (SSPL, loses the above), Kafka/Redis
(the event table + in-process bus is the broker), microservices, GraphQL, SQLite
(single-writer ceiling, no trgm, no managed-DB story), Elasticsearch.

### 3.2 Core data model

`org` → `project` → `work_item` (typed core columns + `fields jsonb` + `body` markdown
verbatim + generated `tsvector`), `work_item_link` (parent-child | depends-on |
origin-review | pr | supersedes), `comment` (append-only, the 10 canonical kinds),
`work_item_revision` (snapshots → ADR/policy versioning), `event` (global seq; audit +
feed), `consumer_cursor` (per orchestrator token/instance), `entity_type` (field schema +
workflow + render config — **types are rows, not DDL**).

### 3.3 Workflows

The `statuses.yaml` format is retained as the workflow language. The current file splits
mechanically into `epic-pipeline` + `story-pipeline`; later types bring their own
(`adr-lifecycle`, `policy-lifecycle`, `incident`, …). Resolution: project override → org
default → built-in (today's statuses.yaml ships as the built-in). Transitions are enforced
server-side with native CAS — stronger than the mock.

### 3.4 API surfaces

| Surface | Prefix | Auth | Format |
|---|---|---|---|
| Agents/orchestrators | `/agent/v1/*` | bearer per orchestrator, project-scoped | text/plain, mock-CLI shapes; frozen, additive-only |
| Dashboard | `/api/v1/*` + SSE | session cookie | JSON |
| Machines | `/webhooks/:hookId` | HMAC-SHA256 | provider JSON, replayable deliveries |

Token-efficiency features: server-composed packet (body + latest handoff + latest
transition-reason + gate-results if newer + all decisions + omitted-count breadcrumb;
~5–8× smaller on bounced tickets, kills the silent AC truncation), `get --brief` for the
dedup gate, zero MCP.

### 3.5 Boilerplate seams (backward compatibility is sacred)

- `scripts/backend-tracker.sh` — curl shim, CLI-identical to mock/jira; env `BACKEND_URL`,
  `BACKEND_TOKEN`, `TRACKER_PROJECT`. Switch = set `TRACKER_CMD`. Must pass the mock
  conformance assertions against a live backend (release blocker).
- `events` — server-side cursor per (token, `ORCH_INSTANCE_ID`), same output lines,
  at-least-once; claim protocol keeps arbitrating double-dispatch.
- `$FORGE_CMD` — `backend-forge.sh pr-state` from the PR mirror; Done gate unchanged.
- Telemetry — tail-and-POST shipper for run.log/telemetry; orchestrator untouched.
- The only orchestrator edit ever: `build_packet()` capability probe for the `packet` op,
  kill switch `ORCH_PACKET_MODE=full`.

## 4. Roadmap (one epic per phase)

| Phase | Scope | Outcome |
|---|---|---|
| **1 — Tracker core** | schema, registry, workflow engine, 13 ops + packet/brief, adapter + conformance, orchestrator registration/heartbeat, kanban + SSE, minimal interventions, importer, Docker packaging | drop-in Jira replacement; a live run can switch `TRACKER_CMD` |
| **2 — Ops surface** | Bitbucket ForgeProvider + PR mirror + merge-from-board, `backend-forge.sh`, inbound webhooks + mapping rules, run.log/telemetry ingest, report views; **absorbs ABS-127**: the telemetry shipper becomes a bidirectional local orchestrator agent — spawn-level observability (live seats per instance), run-ID enabler + agent/run log filters, and a command poll executing `stop-run` (`ORCH_STOP_FILE`) and `abort-spawn` locally (no inbound connection to the operator host) | board shows PR/CI truth; human merges from the board; deploy pipelines drive the workflow; run/spawn control from the board |
| **3 — Knowledge** | `adr`/`policy` types, revision editing, effective-policy resolution (org ∪ project), `policies` adapter op + revision-pinned packet injection, ADR importer | ADRs/policies live in the backend; every spawn auditable against the exact policy text it saw |
| **4 — Ops/support + productization** | incident/support-case/runbook types (registry config), SLA/timer fields, license enforcement (Ed25519 offline keys, feature-flag-gated modules), white-label, GitHub provider, long-poll events | sellable, extensible platform beyond dev delivery |

**Phase-1 foundations** (must exist in phase 1 to avoid rework later): event log with global
seq · entity-type registry + JSONB fields · org/project scoping on every table · scoped
tokens + roles · revision snapshots on body updates · named per-type/org/project-resolvable
workflows.

## 5. Product & sellability

- **Install**: `docker compose up` — backend + `postgres:16-alpine` + volume; migrations
  auto-apply; backup = `pg_dump`; export = canonical-markdown tarball (no lock-in).
- **Packaging**: pnpm workspace — `packages/core|forge|webhooks|policies|telemetry|realtime`,
  `apps/server`, `apps/web` (React SPA served statically). Modules talk only via core
  services + event bus.
- **Licensing**: offline-verifiable signed license key (Ed25519) carrying expiry and feature
  flags that gate module registration; optional telemetry ping behind a flag; white-label =
  theming config. `org_id` everywhere keeps a managed SaaS tier open without a data-model
  migration (v1 = single-org per install).
- **Coexistence**: mock adapter stays the sandbox default and conformance reference;
  `jira-tracker.sh` + `jira-sop` remain as the legacy Jira-profile binding for Jira-bound
  customers.

## 6. Top risks (tracked in ADR-A-0021)

1. Adapter-parity trap — exact exit codes/output shapes; mock conformance suite in CI, diff = release blocker.
2. Event-cursor semantics with multiple consumers — per (token, instance-id), at-least-once.
3. Packet-trimming quality — decisions always included, breadcrumb + kill switch.
4. Type-registry scope creep — YAML config only, no runtime type UI before Phase 4.
5. Merge authz / forge credentials — role + gate-status + audit event; secrets never in the SPA.
6. SSE through customer proxies — heartbeats, `Last-Event-ID` resume, proxy docs.
