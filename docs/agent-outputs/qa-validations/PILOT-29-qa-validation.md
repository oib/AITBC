# QA Validation Report — PILOT-29

**Ticket:** PILOT-29 — S3: Command-Queue auf den Push-Kanal — Long-Poll-Delivery für stop-run/abort-spawn-Commands  
**QAS Seat:** qas (ABS-174 spawn seam)  
**Commit under review:** `078509d2` — sole delta on `PILOT-29-auto` over `epic/PILOT-28-poll-to-push`  
**Branch:** PILOT-29-auto  
**Date:** 2026-07-25  
**Verdict:** ✅ APPROVED — Iteration 1 of 3

---

## Environment

- Postgres 16 (Docker `postgres:16-alpine`), fresh container `qas-pilot29-pg`, port 25433
- `DATABASE_URL=postgresql://postgres:qas_pilot29@localhost:25433/pilot29_test`
- All runs back-to-back in the same shell / same env (Rule 9, ABS-285)
- Container destroyed after validation

---

## Static Gates

| Gate | Result | Detail |
|------|--------|--------|
| `pnpm -r typecheck` | ✅ PASS | 5/5 workspaces clean (`core`, `forge`, `webhooks`, `web`, `server`) |
| `pnpm exec eslint .` | ✅ PASS | Exit 0, no warnings |

---

## Acceptance Criteria Validation

All AC tests run from `apps/server/test/command-routes.test.ts` against a live Postgres + LISTEN/NOTIFY bus.

### command-routes.test.ts — 32/32 PASS

| AC | Test name | Result | Time |
|----|-----------|--------|------|
| AC1 | PILOT-29 AC1: enqueue during a wait poll → answers < 1s with the command; pending→delivered | ✅ PASS | 235 ms |
| AC2 | PILOT-29 AC2: two instances — waiter on B, enqueue on A → answers < 1s (S1 bus) | ✅ PASS | 381 ms |
| AC3 | PILOT-29 AC3: a command for instance X does not satisfy instance Y's poll — no busy-loop | ✅ PASS | 2050 ms |
| AC4 | PILOT-29 AC4: an unacked command redelivers on the next waiting poll | ✅ PASS | 51 ms |
| AC5 | PILOT-29 AC5: a wait poll with no command → empty answer at ~timeout; no state flip | ✅ PASS | 2016 ms |
| — | PILOT-29: wait=0 / absent is byte-identical to today's single read | ✅ PASS | 17 ms |

All 32 tests in the suite (including prior AC#1–AC#4 auth, delivery semantics, ABS-386, ABS-413, ABS-439, ABS-444, ABS-447 tests) passed.

---

## Regression Check (S2 / S1)

| Suite | Result | Count |
|-------|--------|-------|
| `events-routes.test.ts` (S2 waiter-mechanics regression) | ✅ 22/22 PASS | 0 failures |
| `packages/core/test/events.test.ts` (S1 bus regression) | ✅ 11/11 PASS | 0 failures |

---

## Baseline Comparison (Rule 9, ABS-285)

Pre-existing failures measured on parent commit `4fe4fea9` (epic tip before PILOT-29) and branch `078509d2` back-to-back, same Postgres container:

| Suite | Baseline (4fe4fea9) | Branch (078509d2) | Delta |
|-------|--------------------|--------------------|-------|
| `report-routes.test.ts` | 0/5 pass (5 pre-existing failures: AC1/AC2/AC3 + DAC-19/DAC-20) | 0/5 pass (identical set) | 0 new failures |
| `telemetry-signals.test.ts` | 1/2 pass (AC1/AC3 ABS-505 pre-existing) | 1/2 pass (identical) | 0 new failures |

**PILOT-29 introduces zero new test failures.**

---

## Implementation Review Notes

- **No second mechanism:** Cross-instance wake reuses S1 bus (`notifyBusEvent`, `pg_notify` inside enqueue transaction — atomic with insert, no post-COMMIT strand window) and existing `kind='command'` event row.
- **Long-poll reuses S2 mechanics:** Same `waiters` set → `preClose` shutdown-drain; same `eventWaitCap`; subscribe-before-read ordering; disconnect cleanup — all passed from `server.ts`, not re-implemented.
- **AC3 no-busy-loop:** Project-scoped wake channel (`cmd\0<projectId>` key via `EventBus.commandKey`) vs instance-scoped queue read. A sibling wake causes a leer-read + re-park (the `while` loop), never a spin.
- **Auth/human-boundary unchanged:** Enqueue: human-session + `requireHuman`. Poll: orchestrator-token + `requireOwnInstance`. Receipts: unchanged. ADR-A-0010 (outbound-only) respected.
- **Delivery semantics unchanged:** `pollCommands` runs once per park, own transaction — at-least-once, pending→delivered flip, redelivery of unacked commands byte-unchanged. `wait=0`/absent is byte-identical to the pre-S3 single read (test-proven).
- **`/capabilities` updated:** `commands-wait` advertised alongside `events-wait` for S4 shipper detection.
- **Non-blocking nit (from architect review, does not block):** `EventBus.commandKey` docstring says `cmd\0<project>` (null byte) but implementation returns `` `cmd ${projectId}` `` (space). Functionally sound (UUID PKs, no collision possible). Correct the comment in a follow-up.

---

## DoD Checklist

- [x] AC1: enqueue during wait poll → <1 s delivery, pending→delivered flip ✅
- [x] AC2: cross-instance via S1 bus, waiter B, enqueue A → <1 s ✅
- [x] AC3: instance-scoped delivery, no busy-loop for sibling instance ✅
- [x] AC4: unacked command redelivers on next waiting poll ✅
- [x] AC5: timeout with no command → empty response, no state flip ✅
- [x] All pre-existing command tests remain green ✅
- [x] No S2 regression ✅
- [x] TypeScript clean ✅
- [x] ESLint clean ✅
- [x] No migration (no schema change) ✅
- [x] `/capabilities` advertises `commands-wait` ✅

---

## Verdict

**✅ APPROVED for Story Acceptance (Iteration 1 of 3 — no bounce)**

Evidence: 32/32 command-routes AC tests pass, 22/22 events-routes pass, 11/11 core events pass, zero new failures vs baseline, tsc + eslint clean. All five AC criteria independently verified against a live Postgres + LISTEN/NOTIFY bus.
