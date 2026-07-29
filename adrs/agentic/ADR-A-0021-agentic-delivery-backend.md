---
id: ADR-A-0021
title: Agentic delivery backend — agent-first tracker platform replacing the Jira binding
status: proposed
scope: agentic
date: "2026-07-12"
---

## Context

The boilerplate's ticket access is tracker-agnostic by design: every read/write goes through
the neutral capability contract (`profiles/neutral/adapters/task-tracking.md`, 13 CLI ops
behind `$TRACKER_CMD`, ADR-A-0007), with `scripts/mock-tracker.sh` as the conformance
reference and `scripts/jira-tracker.sh` (1387 lines) as the live binding. The Jira binding
works (v2.22.0+ live runs), but carries structural overhead that no adapter can remove,
because Jira is built for humans:

- **Impedance mismatch**: `role`, `depends_on`, `links`, `flags`, `ac_blocking` have no
  native Jira home and are label-encoded (`role:<name>`, `depends-on:<id>`, `flag:<name>`),
  reconstructed on every `get`.
- **Cost**: one JQL sweep per poll as a deliberate budget; ADF/JSON payloads; the interactive
  lane needs the Atlassian MCP server (~40 tool schemas) plus the `jira-sop` skill in context
  (~10–20k tokens per session that touches tickets).
- **Context quality**: the orchestrator's context packet embeds the full comment history and
  truncates body-tail-first at `ORCH_PACKET_MAX_BYTES` (32 KB) — on bounced tickets this can
  silently cut acceptance criteria.
- **No product story**: the boilerplate cannot be sold as a self-contained product while its
  tracker is a customer-provided Jira.

The Operator's direction (2026-07-12) widens the goal beyond a tracker swap: the backend
becomes the boilerplate's central platform — orchestrator logs and telemetry, ADRs, and
org-wide policies live in it; one backend manages multiple projects with multiple
orchestrator instances; the entity model must extend to future ops/support work (incidents,
support cases, runbooks); a kanban dashboard with realtime push lets the human monitor and
intervene (including triggering merges, which requires a git/Bitbucket integration); and
external systems (deploy pipelines, CI) call inbound webhooks that flow into the workflow.

## Decision

Build the **agentic delivery backend**: a modular monolith in Node/TypeScript (one container,
plus Postgres 16 in docker compose) whose spine is an **append-only event log** over a
**generic work-item store with an entity-type registry**, and whose contract with the
boilerplate is a new `$TRACKER_CMD` adapter (`scripts/backend-tracker.sh`) that is
CLI-identical to `scripts/mock-tracker.sh`. The orchestrator does not change (one
opt-in exception, (f) below).

### (a) Storage — Postgres 16 with JSONB entities, not NoSQL, not full event sourcing

The "SQL vs NoSQL" question is a false dichotomy for this workload: **Postgres JSONB is a
document store inside a transactional engine.** Entities are objects (`fields jsonb`; new
entity types are registry rows, not DDL migrations), while we keep the three properties this
workload leans on hardest and a document DB gives up:

1. **Atomic transitions** — the `--expect-from` compare-and-set (ABS-198) becomes
   `UPDATE … WHERE status = $expect` + comment insert + event insert **in one transaction**;
   state and history can never diverge.
2. **A globally ordered event cursor** (`bigserial seq`) — simultaneously the `events` op,
   the SSE feed, the audit trail, and the webhook-output channel.
3. **Referential integrity and joins** — links/hierarchy edges, JOIN-rule/child-count
   queries, and `tsvector` + `pg_trgm` similarity for the dedup gate.

Full event sourcing (state derived by replay) is rejected: the audit needs the *log* and the
orchestrator needs the *feed*, but nothing needs replay — we take the append-only event log
written transactionally with each state change ("event-logged CRUD") and skip projections,
rebuild tooling, and upcasters.

### (b) Entity-type registry — types and workflows are data, not code

`entity_type` rows carry a field schema (JSON Schema over `fields`), a workflow, and a
canonical-render config. Epic/story/subtask ship in Phase 1; `adr`, `policy`, and later
`incident`/`support-case`/`runbook` are inserts plus workflow YAML — no core change. The
`statuses.yaml` **format is retained** as the workflow definition language (the current file
splits mechanically into `epic-pipeline` and `story-pipeline`); resolution order is
**project override → org default → built-in**, with today's statuses.yaml shipped as the
built-in. Types/workflows are validated YAML config; there is no runtime type-creation UI
before Phase 4 (scope fence).

### (c) API layering — three surfaces, one server

| Surface | Prefix | Auth | Format / contract |
|---|---|---|---|
| Agents/orchestrators | `/agent/v1/*` | bearer token per orchestrator, project-scoped | `text/plain`, exactly the mock-CLI output shapes; **frozen, additive-only** |
| Dashboard | `/api/v1/*` + SSE | session cookie | JSON, evolves freely |
| Machines | `/webhooks/:hookId` | HMAC-SHA256 | provider JSON; deliveries persisted and replayable |

The canonical text (frontmatter + markdown, TSV search lines, event lines) is rendered at
the API edge. Token efficiency is a product feature: a server-composed context packet
(`GET …/packet`: body sections + latest handoff + latest transition-reason + gate-results if
newer + all decisions + an omitted-count breadcrumb) replaces today's full-history dump and
its silent 32 KB truncation; `get --brief` serves the dedup gate; no MCP lane is needed at
all — interactive sessions use the same CLI adapter.

### (d) Boilerplate seams — backward compatibility is the acceptance test

- `scripts/backend-tracker.sh`: curl shim (< 300 lines target), byte-identical CLI to
  mock/jira; env `BACKEND_URL`, `BACKEND_TOKEN`, `TRACKER_PROJECT`. Switching =
  `TRACKER_CMD=scripts/backend-tracker.sh`. **It must pass the mock conformance assertions
  (`tests/test-mock-tracker.sh` semantics) against a live backend; any diff is a release
  blocker.**
- `events`: server-side cursor per (token, `ORCH_INSTANCE_ID`) replaces the local
  snapshot-diff; same line format, at-least-once; the existing claim protocol
  (ABS-182/185) continues to arbitrate double-dispatch.
- `$FORGE_CMD`: `scripts/backend-forge.sh` implements `pr-state <ticket>` →
  `MERGED|OPEN|NONE` from the backend's PR mirror; the Done gate (ABS-211) works unchanged.
- Logs/telemetry: a tail-and-POST shipper posts `run.log`/telemetry lines as events — the
  orchestrator itself stays untouched.

### (e) Integrations — forge outbound, webhooks inbound, SSE to the browser

A backend-side `ForgeProvider` interface (Bitbucket Cloud REST first, GitHub later) keeps a
PR-mirror row per work item fresh via Bitbucket webhooks with a lazy-poll fallback.
**Merge from the board** requires: human role ≥ maintainer on the project **and** the item in
a human-merge-gate status (Ready for Merge / Ready for Epic Acceptance) — then
`forge.merge`, an audited event, and an optional configured auto-transition. This does not
move merge authority: the human still merges (ADR-A-0005, ADR-A-0014); the board is a new
front door for the same Stage-3 HITL act. Forge credentials live server-side only.

Inbound webhooks are per-hook HMAC endpoints whose **mapping rules are configuration**
(match on payload path → target entity selector → transition/comment with
`actor=webhook:<hook>`); actions run through the same transition engine and event log, so the
orchestrator sees webhook-driven changes in its normal poll with zero special plumbing.

Realtime to the browser is **SSE** (heartbeats, `Last-Event-ID` resume mapping to the event
`seq`). The orchestrator keeps polling in v1; the blessed later path is long-poll on the same
events endpoint, a change confined to the adapter script.

### (f) The single orchestrator touch — packet composition (opt-in)

`build_packet()` uses the adapter's `packet` op via a capability probe, with kill switch
`ORCH_PACKET_MODE=full` restoring the current full-`get` path (ABS-111 convention:
default-on with an `ORCH_*` escape). Everything else in `scripts/orchestrator.sh` is
untouched.

### (g) Product shape

pnpm workspace: `packages/core` (entities, registry, workflow engine, event log, auth),
`packages/forge|webhooks|policies|telemetry|realtime`, `apps/server` (composes modules),
`apps/web` (React SPA served statically). Modules communicate only via core services and the
event bus. Install = `docker compose up` (backend + `postgres:16-alpine` + volume);
migrations auto-apply at startup; backup = `pg_dump`; export = canonical-markdown tarball
(vendor-lock escape hatch). License: offline-verifiable signed key (Ed25519) with feature
flags gating module registration; white-label via theming config. `org_id` columns exist
from day one; v1 ships single-org per install.

### (h) Phasing

- **Phase 1 — tracker core**: drop-in Jira replacement (13 ops + packet/brief), adapter +
  conformance, kanban board with SSE, minimal human interventions, importer, Docker packaging.
- **Phase 2 — ops surface**: forge/PR mirror/merge-from-board, inbound webhooks,
  run.log/telemetry ingest, report views. Absorbs the ABS-127 dashboard epic (Operator
  decision 2026-07-12): the telemetry shipper doubles as a bidirectional local orchestrator
  agent — it pushes spawn-level status (plus a minimal run-ID enabler in the orchestrator)
  and polls a command endpoint to execute `stop-run` (existing `ORCH_STOP_FILE` kill switch)
  and `abort-spawn` locally, so the backend never needs an inbound connection to the
  operator host.
- **Phase 3 — knowledge**: `adr`/`policy` entity types (revision snapshots, `supersedes`
  links; effective policy = org ∪ project, project wins), a `policies` adapter op rendering
  effective policy text into packets, revision-pinned (`policy_rev` hash) for auditability.
- **Phase 4 — ops/support + productization**: incident/support-case/runbook types (registry
  config), SLA/timer fields, license enforcement, white-label, GitHub provider, long-poll
  events.

**Phase-1 foundations that must exist to avoid rework** (consequences of this decision):
(1) the append-only event log with global seq; (2) the entity-type registry + JSONB fields
even while only epic/story/subtask ship; (3) org/project scoping on every table; (4) auth as
scoped tokens + roles; (5) revision snapshots on body updates; (6) the workflow engine
resolving named, per-type, org/project-overridable workflows.

### (i) Tenant isolation — app-layer scoping ratified for Phase 1; Postgres RLS is a triggered backstop

The backend is multi-tenant by `org_id`/`project_id` from day one, but **there is no
database-level RLS**, and none is added in Phase 1. The boilerplate's RLS-always principle
is expressed through the Prisma context helpers (`withUserContext` / `withAdminContext` /
`withSystemContext`), which do not map onto this plain `node-postgres` service. Per §(c),
the token-authenticated route is the tenant boundary: the bearer token resolves to a fixed
`(org_id, project_id)`, and every core data function takes that scope as a **required,
non-optional parameter** and carries an `org_id`/`project_id` predicate on every statement;
an item outside the caller's scope is reported as **not found (404), never forbidden (403)**,
so scope is never even confirmed to exist to a foreign caller. This is enforced by
compile-time signatures (the scope params cannot be omitted) plus the golden-file/conformance
suite, and is the *only* tenant isolation in the system.

This app-layer-only model is **ratified as the deliberate Phase-1 decision**, not left as a
silence, for three reasons: (1) the helpers that the RLS-always principle names do not exist
in a plain `pg` service; (2) Phase 1 ships **single-org per install** (§g), so cross-tenant
leakage has no live surface until multi-org-per-install exists; (3) the scope predicate is
threaded mechanically through required parameters rather than by convention, and the
conformance suite walks the foreign-scope → 404 path.

**Hard trigger for RLS as defence-in-depth.** Before **multi-org-per-install** ships
(explicitly out of Phase-1 scope, and a later-phase concern), Postgres RLS **becomes
mandatory** as a backstop beneath the app-layer scoping: a per-transaction session GUC
(`SET LOCAL app.current_org = $org` / `app.current_project`) plus `CREATE POLICY … USING
(org_id = current_setting('app.current_org')::uuid)` on every tenant-scoped table. Until then
the app-layer model stands, but the moment a second org shares one database the "one service
forgets its predicate → silent cross-tenant leak" risk goes live with nothing beneath it to
catch the mistake, so the backstop is owed at that boundary — recorded here so it is not
rediscovered a fourth time by an implementer.

## Consequences

- The Jira overhead classes disappear structurally: no label-encoding, no JQL sweeps, no ADF,
  no MCP schemas; packet size on bounced tickets drops ~5–8× and the silent AC-truncation bug
  is replaced by explicit, recoverable comment elision.
- The boilerplate + backend become one sellable product with a `docker compose up` install.
- `scripts/jira-tracker.sh` and the `jira-sop` skill are **not deleted**: they remain the
  Jira-profile binding for customers bound to Jira. The lane doctrine in `task-tracking.md`
  is updated: with the backend, both lanes (autonomous and interactive) use the same CLI
  adapter; the MCP lane exists only in the Jira profile.
- The mock adapter stays the default for sandbox runs and remains the conformance reference;
  its format now has a second consumer (the backend's renderer), so mock format changes
  require a coordinated golden-fixture update.
- The app layer, not the DB, enforces workflow transitions (the DB cannot read JSONB
  workflows in a constraint) — the conformance suite must walk every legal and illegal edge
  of the imported statuses.yaml.
- A new operational dependency (Postgres) enters the product; accepted for the single-writer
  ceiling, ordered cursor, trgm similarity, and the enterprise "point it at our RDS" ask.
- Tenant isolation is app-layer-only in Phase 1 (§i): a documented, mechanically-scoped
  exception to the Prisma RLS-always principle, valid while the product is single-org per
  install. Postgres RLS is deferred but pre-specified (session-GUC + policies) and becomes a
  release blocker the moment multi-org-per-install is in scope. Every future story that adds a
  tenant-scoped route inherits the required-scope-parameter + foreign-scope-→-404 rule.

## Alternatives considered

1. **Keep Jira, optimize the adapter.** Rejected: the overhead is structural (human-first
   data model, ADF, per-poll JQL, MCP interactive lane); no adapter work removes it, and it
   blocks the one-product sale.
2. **SQLite single-container minimal tracker** (the pre-widening plan). Rejected for the
   platform scope: single-writer ceiling forces re-architecture the moment a second process
   (webhook receiver, reporting job) exists; no `pg_trgm`; unbounded event/telemetry growth
   wants real indexes/partitioning; enterprises ask for managed Postgres.
3. **MongoDB / dedicated document DB.** Rejected: loses one-transaction CAS+comment+event,
   the ordered global cursor, and cheap joins; SSPL licensing is hostile to a resold product;
   a second heavyweight container.
4. **Full event sourcing / CQRS.** Rejected: replay-derived state, projection rebuilds, and
   event upcasters are recurring costs with no requirement behind them; restore must be
   "load a pg_dump", not "replay 2M events through the right code version".
5. **Kafka/Redis/NATS event broker.** Rejected: one process and one Postgres suffice; the
   event table + in-process bus is the broker; `LISTEN/NOTIFY` is the pre-built seam if a
   second process ever appears.
6. **Microservices.** Rejected: the product installs on customer machines; every extra
   service multiplies failure modes; module boundaries live in code (pnpm packages), not the
   network.
7. **GraphQL / tRPC public API.** Rejected: agents must stay curl-simple and token-terse;
   REST + plain-text + SSE mirrors the frozen 13-op discipline. (Internal type-sharing via a
   contracts package is fine.)
8. **GitHub/GitLab Issues or Linear as backend.** Rejected: same human-first mismatch, no
   one-product packaging, and the entity model (policies, incidents, ADRs) doesn't fit.

## Related Decisions

- [ADR-A-0007](ADR-A-0007-adapter-model.md) — adapter-only tracker access; unchanged and
  reinforced: the backend is a new binding behind the same seam.
- [ADR-A-0003](ADR-A-0003-context-minimization.md) — the server-composed packet is this
  principle applied at the source.
- [ADR-A-0005](ADR-A-0005-mandatory-prs.md) / [ADR-A-0014](ADR-A-0014-workflow-v3-per-epic-merge-gate.md)
  — merge authority stays human; merge-from-board is a new front door to the same gate.
- [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md) — this ADR ships `proposed`;
  acceptance is human-only.
- [ADR-A-0010](ADR-A-0010-minimal-change-default.md) — the orchestrator is touched in exactly
  one function, behind a kill switch.
- [ADR-A-0026](ADR-A-0026-first-class-orchestration-state.md) — follow-up that names the
  concrete first-class control-state fields/records for this data model (iteration caps,
  follow-up budget, counters, handoff, seat leases, `orchestration_state`, …) and the v2→v3
  migration mapping; establishes "comment kinds = migration format, not the target data model".

## References

- Operator direction (2026-07-12): backend as central platform; multi-project; ops/support
  extensibility; merge-from-board; realtime push; inbound webhooks; SQL-vs-NoSQL exploration.
- `profiles/neutral/adapters/task-tracking.md` (capability contract, lane doctrine),
  `profiles/neutral/adapters/statuses.yaml` (workflow format retained).
- `scripts/mock-tracker.sh` (CLI/format reference), `scripts/jira-tracker.sh`
  (label-encoding overhead evidence), `scripts/orchestrator.sh` (`$TRACKER_CMD` L205,
  `$FORGE_CMD` L215, `build_packet()` ~L4244, `ORCH_INSTANCE_ID` ~L4881).
- `tests/test-mock-tracker.sh`, `tests/test-tracker-adapter-lint.sh` (conformance suite =
  Phase-1 acceptance test).
- ABS-168 (token-overhead verification: main-context bytes are the cost), ABS-152 (two-lane
  doctrine), ABS-198 (CAS NOOP semantics), ABS-211 (Done PR gate), ABS-182/185 (claims).
- Vision & phased roadmap: `specs/DRAFT-agentic-backend-vision.md`. Phase-1 spec:
  `specs/ABS-<epic>-agentic-backend-phase1-spec.md` (filed with the epic).
