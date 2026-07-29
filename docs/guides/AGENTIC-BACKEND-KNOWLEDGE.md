# Agentic Backend — Knowledge Layer Guide

Phase-3 (ABS-231) adds a **knowledge layer** to the backend: Architecture Decision Records
(ADRs) as first-class work items and org/project-scoped **policies** that the orchestrator
injects into agent spawn packets. This guide covers the data model, the ADR lifecycle,
effective-policy resolution, and the packet-injection audit trail.

For HTTP route details see `docs/guides/AGENTIC-BACKEND-API.md` — "Knowledge Surface (Phase 3)".
For the ADR import operator procedure see `docs/sop/ADR-IMPORT-RUNBOOK.md`.

---

## Human-only boundaries (ADR-A-0004)

**ADR acceptance and all policy writes are Human acts.** No agent or orchestrator
token may perform them.

- `POST /api/admin/import/adrs` — admin token only (no agent token accepted).
- `POST /api/v1/.../policies` (create/update/status) — human writer session only
  (`admin` or `maintainer` role). Agent and orchestrator Bearer tokens receive `403`.
- ADR `→ Accepted` transition — the transition service checks a fail-closed allowlist.
  Any non-human principal attempting to accept an ADR gets `403 forbidden`.

No Phase-3 entity is ever `orchestrator-ready`. Migration `008` adds a DB-level CHECK:

```sql
CHECK (type_key <> 'adr' OR orchestration_state = 'excluded')
```

Any attempt to set `orchestration_state = 'eligible'` on an `adr` row fails at the
database, regardless of which route or principal triggered it.

---

## ADR lifecycle

ADRs live in the `adr-lifecycle` workflow. The four statuses:

```
Draft ──▶ Proposed ──▶ Accepted ──▶ Superseded
  ▲           │
  └───────────┘   (Proposed → Draft on revision request)
```

| Status | Class | Meaning |
| -------- | ------- | --------- |
| `Draft` | transient | Imported as draft, or bounced back from Proposed for revision |
| `Proposed` | transient | Submitted for human acceptance |
| `Accepted` | resting | A human accepted it — **human-only transition target** |
| `Superseded` | resting, terminal | A newer Accepted ADR retired it |

`Accepted` and `Superseded` are human-owned. No agent may transition an ADR into either.

The workflow source is `backend/packages/core/src/workflows/adr-lifecycle.yaml`.
`WORKFLOW_BY_TYPE` in `registry.ts` maps `adr → adr-lifecycle`; `resolveWorkflowFor`
returns this workflow rather than the story-pipeline fallback.

### ADR render format

`GET /agent/v1/projects/:project/items/:key` routes `adr` items through `renderAdrItem`.
Frontmatter fields appear in this order; starred fields appear only when set:

```
---
id: ADR-A-0007
type: adr
title: Commit message convention
status: Accepted
adr_date: 2026-05-01        # only when set
adr_scope: agentic          # only when set
supersedes: ADR-A-0002      # only when set
created: 2026-07-17T20:00:00Z
updated: 2026-07-17T20:00:00Z
---
<verbatim body from importAdr>
```

`adr` items always carry `orchestration_state = 'excluded'` (DB CHECK). They never
appear in the orchestrator dispatch queue and carry no `orchestrator-ready` label.

---

## Policy data model

A policy is **not** a `work_item`. It is org-scopable, audience-filtered, and resolved
by an Org ∪ Project union — none of which the scope-required work-item spine expresses.
Phase 3 gives it a dedicated table.

### `policy` table

| Column | Type | Notes |
| -------- | ------ | ------- |
| `id` | `uuid` PK | `gen_random_uuid()` |
| `org_id` | `uuid` NOT NULL | FK → `org` |
| `project_id` | `uuid` | FK → `project`; NULL = org-wide |
| `key` | `text` NOT NULL | Topic slug — the override unit |
| `audience` | `text` | Role token (e.g. `be-developer`) or NULL = all audiences |
| `title` | `text` NOT NULL | Display title |
| `body` | `text` NOT NULL | Canonical markdown; stored verbatim; default `''` |
| `status` | `text` NOT NULL | `CHECK IN ('draft','active','retired')`; default `draft` |
| `revision` | `int` NOT NULL | Incremented on every body/status write |
| `created` / `updated` | `timestamptz` NOT NULL | |

`UNIQUE (org_id, project_id, key, audience)` — one policy per (scope, key, audience).

### `policy_revision` table

Snapshot written on every body or status change (parity with `work_item_revision`).

| Column | Type | Notes |
| -------- | ------ | ------- |
| `policy_id` | `uuid` NOT NULL | FK → `policy` |
| `revision` | `int` NOT NULL | |
| `title` / `body` / `status` | `text` NOT NULL | Snapshot at write time |
| `actor` | `text` NOT NULL | Writer identity |
| `at` | `timestamptz` NOT NULL | |

Primary key `(policy_id, revision)`.

Every policy write appends a `kind='policy'` event on the global seq (same audit
spine as ticket writes). A create→update→status sequence yields three revisions and
three events.

---

## Effective-policy resolution

`resolveEffectivePolicy(pool, orgId, projectId, audience?)` returns
`{ rendered, policyRev }` where `policyRev = sha256(rendered)` hex.

### Algorithm

1. Only `status='active'` policies participate — `draft` and `retired` are excluded.
2. When `audience` is given, keep audience-matching **and** audience-NULL policies.
3. Union Org ∪ Project. A project-scoped row wins the **whole document** over an
   org-wide row with the same `(key, audience)` override unit — project always wins.
4. Order `(audience NULLS FIRST, key)`.
5. Render each block. An empty result renders `(no applicable policy)\n`, which has
   its own stable hash (`EMPTY_POLICY_RENDER`, exported from `@agentic-backend/core`).

### Byte-stability

For a fixed policy set the resolver returns identical `rendered` bytes and an identical
`policyRev` across repeated calls, independent of row insertion order. This stability
lets a spawn be audited against the exact `policyRev` that governed it.

### Org-wide dedup edge case

Postgres treats NULLs as distinct in the UNIQUE constraint, so two org-wide rows with
the same `key` and NULL `audience` can coexist. The resolver closes this: the override
key is `JSON.stringify([audience, key])` and a deterministic tie-break (by `title` then
`body`) picks a single winner, keeping rendered output stable.

---

## Packet-injection audit trail

When `ORCH_POLICY_INJECT=on` (the default) and the adapter offers the `policies` op,
`build_packet()` prepends the effective-policy block to each spawn packet:

```
=== POLICY (policy_rev: 3a1b2c…) ===
# Commit message policy
Use conventional commits: type(scope): description [TICKET-ID].

=== TICKET ===
<ticket dump>
```

`policy_rev` folds into the packet-cache signature. A policy change re-derives the
packet (cache miss). An unchanged policy set re-hits the cache and serves the same
packet without a new backend call.

Every packet build — cache hit or miss — writes one `POLICY-INJECT` line to `run.log`:

```
ts    POLICY-INJECT    ticket    role    to    policy_rev=<hash|none>
```

`policy_rev=none` when no policy applies or when the adapter does not offer the
`policies` op (mock/jira adapters). To reconstruct which policy revision governed a
spawn:

```bash
grep POLICY-INJECT work/.orchestrator/run.log | grep ABS-123
```

### Policy events as audit evidence

Each policy write (create, update, status change) appends a `kind='policy'` event on
the global seq, with payload `{ policy_id, key, audience, scope, from_status,
to_status, revision, actor }`. To answer "what policy governed spawn X?":

1. Read `policy_rev` from the `POLICY-INJECT` run.log line for that spawn.
2. Query `policy_revision` where `sha256(body) = <policy_rev>` — or more practically,
   find the `policy_revision` row whose `revision` was active at the spawn timestamp
   by walking the `policy` events backward from that time.

---

## Related

- Knowledge migration: `backend/packages/core/src/migrations/009_knowledge_adr_policy.sql`
- ADR workflow YAML: `backend/packages/core/src/workflows/adr-lifecycle.yaml`
- Type registry: `backend/packages/core/src/registry.ts` (`WORKFLOW_BY_TYPE`, `builtInWorkflows`)
- Policy service + resolver: `backend/packages/core/src/policies.ts`
- ADR importer + renderer: `backend/packages/core/src/items.ts` (`importAdr`, `renderAdrItem`)
- Policy human routes: `backend/apps/server/src/routes/policies.ts`
- Agent policy route: `backend/apps/server/src/routes/policies.ts` (`registerAgentPolicyRoutes`)
- Resolver tests: `backend/packages/core/test/policy-resolution.test.ts`
- ADR import tests: `backend/apps/server/test/adr-import-routes.test.ts`
- API reference: `docs/guides/AGENTIC-BACKEND-API.md` — "Knowledge Surface (Phase 3)"
- ADR-import runbook: `docs/sop/ADR-IMPORT-RUNBOOK.md`
- Orchestrator SOP (policy injection): `docs/sop/ORCHESTRATOR_SOP.md` — `ORCH_POLICY_INJECT`
- Phase-3 spec: `specs/ABS-231-phase3-spec-draft.md` (attached to epic ABS-231)
