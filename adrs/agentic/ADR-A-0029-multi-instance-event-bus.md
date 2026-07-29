---
id: ADR-A-0029
title: Multi-instance event bus — Postgres LISTEN/NOTIFY backing (amends ADR-A-0021 §e)
status: proposed
scope: agentic
date: "2026-07-20"
---

# ADR-A-0029: Multi-instance event bus — Postgres LISTEN/NOTIFY backing (amends ADR-A-0021 §e)

- **Renumber note (governance correction, 2026-07-25):** authored as `ADR-A-0028` on
  2026-07-20 and collided with `ADR-A-0028` (rule-ledger executable enforcement, ABS-515),
  which reached `origin/main` first. Per `docs/sop/ADR_AUTHORING_GUIDE.md` the ADR already on
  `origin` retains its number, so this file moved to `ADR-A-0029`. The collision went
  undetected because this file shipped without a frontmatter block: the duplicate check in
  `tests/test-adr-id-uniqueness.sh` keys on the frontmatter `id:` and skips files that have
  none, so it reported only "missing frontmatter id" and never the double allocation. The
  frontmatter above was added by the same correction. Renumbering is NOT an acceptance
  (ADR-A-0004): `status:` and all decision content are unchanged.

- **Status:** proposed
- **Date:** 2026-07-20
- **Origin:** ABS-501 (S1 foundation of epic ABS-500, Poll→Push). Design specified
  in-ticket; review 2026-07-20 raised the transactional-NOTIFY, payload-`kind`, and
  wait-Cap points resolved here.
- **Amends:** ADR-A-0021 §(e) ("Realtime to the browser is SSE … the blessed later path is
  long-poll on the same events endpoint"). This ADR fills in the multi-instance broker that
  §(e) named but did not specify.
- **Relates to:** ADR-A-0004 (ADR acceptance + wait-state evidence are human-only), ABS-500
  (epic), ABS-502..507 (downstream stories that consume the wait-Cap and payload format).
- **Human boundary:** acceptance of this ADR is a human act (ADR-A-0004); the implementer
  and architect leave it `proposed`.

## Context

Phase-1 realtime is an in-process `EventBus` (`backend/packages/core/src/events.ts`): a
transition commit calls `bus.publish()`, an `EventEmitter` fans the event out to that
process's SSE subscribers, and reconnect resume replays from the event log via
`Last-Event-ID` (`readTransitionEventsSince`). This is correct for **one** process and wrong
for two: a `publish()` on instance A never wakes a subscriber on instance B, because the
`EventEmitter` is process-local. The epic (ABS-500) moves the orchestrator and the browser
off polling onto push (long-poll + SSE), which is only sound if a write on any instance
wakes waiters on every instance. That is the gap this ADR closes; §(e) already pre-blessed
`LISTEN/NOTIFY` as the seam.

## Decision

Back the bus with Postgres `LISTEN/NOTIFY`. The event **log stays the single source of
truth**; NOTIFY carries only a **pointer** that wakes subscribers, which then read the event
bodies from the log themselves.

1. **NOTIFY is a pointer, never the payload.** Publish emits
   `pg_notify('bus_events', '<projectId>:<seq>[:<kind>]')`. `pg_notify` caps at 8000 bytes,
   and duplicating the event body onto the wire would give the log a rival source of truth.
   A woken subscriber reads the actual events with `readBusEventsSince`
   (`readTransitionEventsSince`'s sibling) — the same log-read the SSE `Last-Event-ID` resume
   already uses.

2. **NOTIFY runs inside the event-insert transaction — not after commit.** `pg_notify` is
   transactional: issued on the **same** connection that inserted the event and **before**
   `COMMIT`, the wake is delivered atomically with the commit and only if the commit lands.
   App-side notify *after* the commit is explicitly rejected: it opens a crash window (event
   durable in the log, wake lost → subscribers hang until their timeout/fallback). Cost is
   one extra statement in the transition transaction.
   *(#PATH_DECISION, review 2026-07-20 — resolved: transactional.)*

3. **One global channel, filtered in-process** — not a channel per project. A listener
   issues a single `LISTEN bus_events` regardless of how many projects it serves; the
   process filters on the `projectId` in the payload. Rejected alternative — a channel per
   project — needs dynamic `LISTEN`/`UNLISTEN` bookkeeping tied to project lifecycle for no
   throughput win at this scale (single install, tens of projects).
   *(#PATH_DECISION — resolved: single channel.)*

4. **Payload format `<projectId>:<seq>:<kind>`** — carry `kind`. It lets S2's events-waiter
   wake-filter transition/create events against S5 signal events (`usage-updated`,
   `seat-log-appended`) **without a log read**, so telemetry publishes do not generate empty
   wakes at the agent `events` op. A `kind`-less pointer is still parsed (defaults to
   `transition`) for forward tolerance. In S1 only transitions NOTIFY, so `kind` is always
   `transition`; later stories widen the emitters.
   *(#PATH_DECISION, review 2026-07-20 — resolved: include `kind`.)*

5. **Dedicated LISTEN connection, not drawn from the request pool.** A long-held `LISTEN`
   client that never returns would permanently shrink the pool; the bus opens its own
   `pg.Client` from the connection string. On connection loss it reconnects with backoff
   (100 ms → doubling → 5 s cap) and closes the seq gap by replaying, per active project,
   from the last delivered `seq` (`readBusEventsSince`) — the same subscribe-before-replay
   discipline as `server.ts` SSE resume.

6. **In-process fast path stays; one dedup gate.** Local subscribers are still served
   synchronously by the `EventEmitter` (unchanged latency). Every delivery — local fast
   path, remote NOTIFY drain, reconnect gap-replay — funnels through a single `deliver()`
   that dedups by `seq`, so an instance's own echoed NOTIFY and any replay overlap collapse
   to exactly one emission (order-independent, so the fast path and the NOTIFY echo may race
   freely).

7. **wait-Cap — one value, one source.** The server-side long-poll/SSE wait is capped at
   **`EVENT_WAIT_CAP_SECONDS`, default 55** (one env var, one default). S2/S3 use it as the
   hold cap for the long-poll and SSE waits; S4's adapter derives its `curl --max-time` and
   heartbeat threshold from it (below the cap, so a heartbeat always precedes the cap). 55 s
   sits under the common 60 s proxy/LB idle timeout so a held request returns before an
   intermediary cuts it. This ADR owns the number; downstream stories read it, never
   re-pick it.

## Consequences

- Multi-instance publish/subscribe becomes correct: a transition on any instance reaches
  every instance's SSE and (S2+) long-poll waiters in < 1 s (ABS-501 AC1).
- The log remains the one source of truth; NOTIFY adds no durable state and no payload
  duplication (AC2). A crash between insert and wake is impossible — they share a
  transaction (AC6).
- Single-instance behavior and every existing events/SSE test are unchanged: the bus is
  in-process-only unless a `databaseUrl`/connection string is supplied (AC4). Production
  wires it (`apps/server/src/index.ts`); tests opt in explicitly.
- Not solved here (accepted, matches the existing SSE layer): the theoretical `seq`-ordering
  gap when two cross-item transactions commit out of `seq` order. Per-item CAS serializes
  same-item transitions; cross-item tailing inherits the log-tailing bound the SSE resume
  already lives with. A stronger low-water-mark cursor is out of scope for S1.
- Out of scope (later stories): the long-poll endpoint (S2), web event kinds / signal events
  (S5), and deployment/scaling questions.

## Alternatives considered

- **App-level pub/sub after commit (notify post-COMMIT, or Redis).** Rejected: the
  post-commit window strands events on a crash (see §2); Redis adds a dependency and a
  second source of truth for a need Postgres already serves (§(e) pre-blessed NOTIFY).
- **Channel per project.** Rejected (§3): dynamic LISTEN bookkeeping, no benefit at this
  scale.
- **Payload carries the event body.** Rejected (§1): 8000-byte cap and a rival source of
  truth; the log read is cheap and already exists.
- **LISTEN connection from the pool.** Rejected (§5): permanently shrinks the request pool.
