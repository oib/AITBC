---
id: ADR-A-0026
title: First-class orchestration state — typed schema fields and records instead of comment-parsed control state
status: accepted
scope: agentic
date: "2026-07-16"
accepted_by: Raphael Sahann (POPM)
accepted_date: "2026-07-16"
---

## Context

[ADR-A-0021](ADR-A-0021-agentic-delivery-backend.md) (proposed) decides to build the agentic
delivery backend and keeps the `statuses.yaml` workflow format, the frozen 13-op adapter
contract, and the mock output shapes as the compatibility surface. That ADR settles *what the
backend is*; it does not settle *where the orchestrator's control state lives*.

Under Jira (v2.22.0–v2.25.x) that state has nowhere native to live, so the runner
**reconstructs it by parsing prose comments and filesystem markers**: iteration caps read from
`of N` comment text, follow-up budget computed as `count(kind:follow-up) − count(kind:bsa-decision)`,
escalation counters kept as files in the state dir, handoff truth parsed from a `commits:` line,
seat ownership held by filesystem locks. Forty-eight hours of v2.25.x operation (2026-07-14…16)
produced a class of failures that look unrelated but share this single root cause. The Operator
(ABS-313, 2026-07-15) directs that v3 model these states as **first-class fields and typed
records**, with comments reduced to human-readable explanation carrying **no control state**.

The Phase-1 spec has already begun landing this direction (commit `ac27bbf`, spec
`ABS-229-agentic-backend-phase1-spec.md`, change markers `[A-313]`): `orchestration_state` is a
first-class column, transitions no longer write a `transition-reason` comment row (the reason
lives on the transition event; the comment block is a render-time projection), search is complete
by contract, and packet slots are selected by encapsulated per-slot selectors. **This ADR is the
normative decision those spec changes implement** — it must underpin them, not contradict them.

The unifying constraint (ABS-313): **comment kinds are the MIGRATION format, not the target data
model.** The `kind` vocabulary survives only so the importer can ingest v2 tickets verbatim and so
the mock-parity renderer can synthesize byte-identical timeline blocks; the backend itself writes
control state to typed columns, relations, and events.

## Decision

Anchor the orchestrator's control state as **first-class schema elements** in the v3 backend data
model, and forbid the backend from encoding control semantics in comment text or in filesystem
markers. Every state the runner reads to make a dispatch, gate, budget, ownership, or routing
decision has a named column, relation, typed record, or event — never a parsed comment or a state-
dir file.

This is a follow-up to ADR-A-0021 (its data-model foundations 1–6 stand); it names the concrete
schema elements and the migration mapping, and adds three doctrines that fell out of the 48-hour
operation.

### (a) Pathology catalogue — one named schema element per failure mode

Each row is a v2 control-state pathology and the v3 schema element that removes it structurally.
The first ten are enumerated in the ABS-313 body; P11–P13 are the 2026-07-15/16 operational
findings. Where later rows overlap earlier ones the overlap is stated, not duplicated.

| # | v2 pathology (evidence) | v3 schema element | Why the schema prevents it structurally |
|---|---|---|---|
| P1 | Iteration-gate cap as an `of N` marker in a comment; a historical marker poisons a gate permanently and the env override is inert (ABS-305; live ABS-302, 2026-07-15) | `iteration_cap` as a **field** on the ticket/gate, runtime-mutable, changes audited as events | Dispatch reads the live field; a past comment cannot re-raise the cap, so no env override is needed — the authoritative value *is* the current field |
| P2 | Follow-up budget = `count(kind:follow-up) − count(kind:bsa-decision)` over comments → JOIN deadlocks, budget env-only, triage only via an exactly-formatted comment (Retro-Befund 4, ABS-298) | `follow_up` as its **own entity** with `status ∈ {open, decided}` and a `budget` **column** | Budget is a value, not a derived count; a malformed or missing comment cannot change it, and the JOIN reads entity status not comment arithmetic |
| P3 | `kind:` header must be its own ADF paragraph or the marker is not counted (JOIN-EXEMPT / bsa-decision cases, 2026-07-13/14) | Typed **events / decision records** written via API | The record's type is a column; there is no free-text paragraph whose formatting can silently invalidate it |
| P4 | Escalation / stall counters kept as **files** in the state dir → survive restarts invisibly; Operator reset = delete the file (ABS-311, ABS-302) | Counters as **fields** with a reset endpoint + audit event | A field lives in the backend, is visible in the UI, and its reset is an audited event, not a silent unlinked file |
| P5 | Handoff truth (`commits:` line, hash verification ABS-255) parsed from markdown prose | Handoff as a **structured record** (`role`, `commits[]`, `verified_state`) | Verification reads typed fields; a prose line that drifts from the record cannot be the source of truth |
| P6 | Stuck / orphan diagnosis needs log-grep + a process tree (mis-diagnosis trap, 2026-07-14) | **Seat registry** table (`seat_id`, `ticket`, `pid`/`session`, `heartbeat`) | Liveness is a queryable row; diagnosis is a SELECT, and the same table backs the live UI and the ABS-312 watchdog |
| P7 | Blocked origin recorded as a `BLOCKED-FROM` comment | `blocked_from` **field** | Resume-to-origin reads a column; there is no comment to lose or mis-format |
| P8 | Orchestration opt-in as an `orchestrator-ready` **label** + the fence as a JQL env string → two divergent fences (Operator addition, 2026-07-15) | `orchestration_state` **field** (`eligible` / `paused` / `manual-only` / `excluded`); the label is a **rendered projection** | Both runner and UI read one field; partitioning becomes one backend query, not two JQL fences that can diverge; label changes map onto the field with an audit event |
| P9 | Silent API truncation — Jira's unpaged search dropped the oldest rows past ~132 tickets with no error, so tickets vanished from the sweep and the JOIN evaluation (BUSCH operation, 2026-07-15; fixed by `nextPageToken` paging) | **Completeness-by-contract** query API: every query returns ALL matches (paging encapsulated server-side in the client SDK) or an **explicit error** — never a silent prefix; ≥ 1000-item scale test in the API Definition-of-Done | Absence is impossible to represent silently; the contract makes a partial answer a hard error, and the scale test proves it at size |
| P10 | Silent seat death — 5 seats died 2026-07-15 ~07:45 with no handoff, no `SPAWN-CRASH`, no log trace; only their filesystem locks remained and blocked the dispatch loop ~50 min (SKIP-LOCKED loop; lock TTL did not fire) | Seat **LEASES** instead of filesystem locks: a seat holds its claim only via a periodic heartbeat; a lapsed heartbeat expires the lease, the backend marks the seat dead with the last-known state as a **terminal event** and auto-releases the ticket | By construction there is no seat state without a terminal record (`started → (heartbeat)* → ended | lease-expired`); a lock cannot outlive its seat, and "silently died" is not a representable state |
| P11 | External events do not reach the tracker — during the Bitbucket outage a merge happened but no status transition followed; a stopgap watcher was needed (Operator session, 2026-07-15/16) | A declared **`waiting-for-external`** orchestration substate that a **sweep rule actively polls**; doctrine: **never build on provider→tracker automation** | The truth is the poll the backend performs (the ADR-A-0021 (e) lazy-poll fallback is promoted to the authority, not a fallback); a missing webhook cannot strand the item because nothing waits passively on it |
| P12 | Dead status with no dispatch rule — `Ready for Merge` NOOPs; 3 tickets stranded in 2 days | **Status-machine totality check**: at workflow-boot every status must have a dispatch rule, a declared rest-semantics, or a JOIN-semantics — otherwise the backend **refuses to start** (fail-fast, naming the offending status) | A status that no seat and no rule handles cannot exist at runtime; the gap is caught at boot, not discovered as a stranded ticket days later |
| P13 | Marker corpses after a crash — halt-markers, locks and session files survive a restart though their processes are dead; Operator recovery = delete files | Control state lives in the **backend**, not in file markers; **restart-reconcile validates against instance-id / liveness**. Generalises P10 (seat ownership → leases) and P4 (counters → fields): the same doctrine, applied to every marker | A backend row's owner is proven live by heartbeat/instance-id at reconcile; a dead process's state is superseded, not silently honoured — no file can assert ownership its process no longer holds |

**Deduplication note.** P13 is the general doctrine ("no control-state marker survives its
process; the backend + heartbeat/instance-id is the liveness source of truth"); P10 is its
seat-ownership instance (leases) and P4 its counter instance (fields). P13 adds only the
restart-reconcile rule that binds every remaining marker to a liveness check. P6 (registry) and
P10 (leases) are the same table seen twice: P6 is its visibility role, P10 its ownership role.

### (b) The design constraint, stated normatively

**Comment kinds are the migration format, not the target data model.** Concretely, for the v3
backend:

1. The backend **never writes** control state into comment text. New `transition-reason`,
   budget, cap, counter, ownership, or routing state is a column, relation, typed record, or
   event — never a comment the runner later re-parses.
2. The `comment.kind` vocabulary is retained **only** for (i) the importer ingesting v2 tickets
   verbatim and (ii) the mock-parity renderer synthesizing byte-identical timeline blocks from
   events. It carries no runtime control semantics.
3. Comments remain a first-class human channel for `decision` / `notification` prose — read by
   humans, never parsed by the runner for state.

### (c) Migration mapping — v2 markers → v3 fields

The v2 adapter (`scripts/backend-tracker.sh`) and the importer map today's marker conventions
onto the new elements; the mapping is the migration contract:

- `of N` iteration marker → `iteration_cap` field (importer reads the highest historical marker
  as the seed value; thereafter the field is authoritative).
- `kind:follow-up` / `kind:bsa-decision` comment pairs → `follow_up` entities with derived
  `status` and a `budget` column seeded from the last env value.
- escalation / stall state-dir files → counter fields (seeded from the file at import; the file
  is then retired).
- `commits:` handoff prose → `handoff` record (`role`, `commits[]`, `verified_state`).
- `BLOCKED-FROM=<status>` comment → `blocked_from` field.
- `orchestrator-ready` label + fence JQL → `orchestration_state` field; the label renders as a
  projection (`eligible` ↔ label present).
- filesystem seat locks → seat leases (no import; locks are abandoned on cutover, leases take
  over ownership from first heartbeat).

Imported v2 comment rows render as-is in the timeline projection; only **new** state is written
to the typed model.

## Consequences

- **ABS-238 (context packet).** Each packet slot (handoff / transition-reason / gate-results /
  decisions) is selected by an **encapsulated per-slot selector**. Today the selectors read
  comment kinds (plus the transition event for the reason slot); when the typed records of (a)
  land, the selectors switch to reading them **without changing the packet output format or the
  adapter**. The packet contract is the seam that lets the data model migrate underneath it.
- **ABS-241 (board interventions).** The release lever writes the `orchestration_state` field
  (`eligible` / `paused` / `manual-only` / `excluded`) with an audit event; the `orchestrator-ready`
  label is only its rendered projection, and the generic label toggle does not offer it. Board
  interventions act on fields, so a human action and a runner read see one authoritative value.
- **ABS-230 / ABS-231 (Phase-2/3 UI epics).** ABS-313 blocks these: the schema is **locked before
  the UI is built**, so the board renders and mutates first-class fields rather than encoding
  control state back into comments a future runner would have to parse. Building the UI first
  would re-introduce the comment-parsing coupling this ADR removes.
- **Conformance surface grows.** The completeness-by-contract query API (P9) adds a ≥ 1000-item
  scale test to the API Definition-of-Done; the lease model (P10) adds heartbeat-expiry and
  auto-release cases; the totality check (P12) adds a workflow-boot refusal test. These are
  additive to the ADR-A-0021 mock-conformance suite, not a change to it.
- **The `kind` CHECK constraint stays, its meaning narrows.** The vocabulary is now explicitly a
  compat/migration artifact; a mock-format change still requires a coordinated golden-fixture
  update (ADR-A-0021 consequence), and additionally must not reintroduce control semantics into a
  comment kind.
- **Tenant isolation / RLS (POPM decision, 2026-07-16).** v1 runs single-tenant per deployment —
  one backend container per project (ABS-239); **no database-level RLS in v1**. App-layer token
  checks are the only guard. Revisit if a deployment ever serves more than one tenant; recorded as
  an epic-level decision on ABS-229 (replacing the spec section the `[A-313]` amendment removed).
- **`iteration_cap` default and granularity deferred (POPM decision, 2026-07-16).** The field
  ships without a fixed default policy; whether the cap is per ticket, per gate, or per
  ticket×gate — and its sensible default — needs operational data first. The Phase-1 spec models
  the field; the default is set once enough run telemetry exists.
- **No orchestrator behaviour change beyond ADR-A-0021's single touch.** The runner keeps reading
  the same adapter ops; the state it reads is now field-backed on the backend side. The v2 marker
  conventions keep working through the migration mapping, so the cutover is not a big-bang.

## Alternatives considered

1. **Keep comment-parsing (do nothing).** Rejected: this is the confirmed root cause of P1–P13.
   Every fix stays a per-symptom patch (a new marker format, a new env override, a new state-dir
   file), and each new marker is a fresh poisoning/format/liveness bug. The 48-hour evidence is
   that the class does not shrink under patching.
2. **Hybrid — some state in fields, some still in comments.** Rejected: a hybrid keeps a parsing
   path alive, so the runner must know *which* state is field-backed and which is comment-derived,
   and the migration never completes. The failure modes (silent format drift, marker corpses,
   env-only budgets) all live on the parsing path; leaving any of it keeps the whole class open.
   The importer already provides the only legitimate reason to read a comment for state (ingesting
   history once), after which the typed model is authoritative.
3. **Derive control state from the event log by replay.** Rejected here for the same reason
   ADR-A-0021 rejects full event sourcing: the runner needs a *current value* to read cheaply at
   dispatch time, not a fold over the log. First-class fields written transactionally with the
   event (event-logged CRUD) give both the value and the audit trail without a projection layer.

## Related Decisions

- [ADR-A-0021](ADR-A-0021-agentic-delivery-backend.md) — the backend this ADR extends; its
  data-model foundations 1–6, the retained `statuses.yaml` format, and the frozen adapter
  contract are the substrate. This ADR names the concrete control-state fields and the migration
  mapping on top of them.
- [ADR-A-0007](ADR-A-0007-adapter-model.md) — the adapter contract is unchanged; field-backed
  state is rendered into the same mock-format ops, so the seam is preserved.
- [ADR-A-0003](ADR-A-0003-context-minimization.md) — the encapsulated packet-slot selectors (P3,
  ABS-238) let the packet stay minimal while the underlying records become typed.
- [ADR-A-0006](ADR-A-0006-active-task-tracking.md) — canonical statuses; the totality check (P12)
  enforces that every status in a resolved workflow is dispatchable, at-rest, or a JOIN node.
- [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md) — this ADR ships `proposed`; acceptance is
  human-only (POPM).

## References

- ABS-313 — "v3-Design-Input: Erste-Klasse-Zustandsfelder statt Kommentar-Parsing"; body (P1–P10)
  and the PO Authoring Request (`kind: handoff`, po-agent, 2026-07-15). The Operator's Teil-B
  additions (10)–(24) in the 2026-07-15 notification comment are carried by the BSA into the
  Phase-1 spec and the colliding stories; this ADR fixes the schema for the P1–P13 control-state
  class.
- Operator direction 2026-07-15 (orchestration_state as a field, label as projection) and
  2026-07-15/16 operational findings (P11 external-event doctrine, P12 status totality, P13 marker
  corpses / restart-reconcile).
- Spec amendment `ac27bbf` — `specs/ABS-229-agentic-backend-phase1-spec.md` `[A-313]` markers:
  transition without a comment write (§3), timeline as projection (§5), `orchestration_state`
  column (§2/§4/§11), search completeness (§4), packet-slot selectors (§6). This ADR is the
  normative decision that spec implements.
- Evidence tickets: ABS-305/302 (P1), ABS-298 (P2), ABS-311 (P4), ABS-255 (P5), ABS-312 (P6),
  ABS-101/208 (P8 release lever). Colliding Phase-1 stories: ABS-238 (packet slots), ABS-241
  (`orchestration_state`). Blocked Phase-2/3 epics: ABS-230, ABS-231.
