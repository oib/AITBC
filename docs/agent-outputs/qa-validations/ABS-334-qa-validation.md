# QA Validation Report — ABS-334

**Ticket**: ABS-334 — Adapter priority-field conformance: wire priority into backend-tracker.sh  
**Date**: 2026-07-17  
**QAS Actor**: qas (In Test gate)  
**Branch**: ABS-334-auto  
**Commit**: 7160a45  
**Authoritative ACs**: BSA re-scope comment (2026-07-17T14:32:58Z) — body ACs superseded

---

## Summary

Independent QAS verification of commit `7160a45` on branch `ABS-334-auto` against the BSA re-scope ACs. The only remaining gap on `main` was `backend-tracker.sh` priority passthrough (mock and jira already implemented on main).

---

## Acceptance Criteria Verification (BSA Re-scope)

| # | AC | Result |
|---|----|----|
| 1 | `backend-tracker.sh get` emits `priority: <v>` as first-class line; default `normal` (only-when-set, mock parity) | ✅ PASS |
| 2 | `create --priority <v>` + `update ... priority <v>` persist to DB column; invalid value dies with mock-identical message | ✅ PASS |
| 3 | Search column form: `id⇥type⇥status⇥priority⇥title` (ABS-331/334 parity with mock) | ✅ PASS |
| 4 | `tests/test-backend-tracker.sh` priority round-trip (create→get→update→get) + search-column + ENUM-guard assertions; suite green | ✅ PASS |
| 5 | `profiles/neutral/adapters/task-tracking.md` jira-mapping line corrected to ABS-261 label persistence | ✅ PASS |
| 6 | `grep -ic priority` > 0 on all three adapter scripts | ✅ PASS (backend=4, jira=29, mock=23) |

---

## Independent Verification Evidence

### Static Checks

| Check | Result |
|-------|--------|
| `shellcheck scripts/backend-tracker.sh` | PASS — exit 0; only pre-existing SC2155 style warnings, none introduced by this diff |
| `pnpm typecheck` (3 projects) | PASS — all exit 0 |
| `pnpm lint` | PASS — exit 0 |

### Unit Tests (backend)

```
packages/core: 107 PASS, 0 FAIL, 53 SKIP (DB-gated)
apps/server:     0 PASS, 0 FAIL, 52 SKIP (DB-gated)
```

No failures. DB-gated suites skip cleanly without Postgres — expected behaviour.

### Conformance Suite (live docker-provisioned backend)

```
bash tests/test-backend-tracker.sh

=== Test 15: create/update --priority — canonical priority field (ABS-334) ===

  PASS  create --priority high surfaces via get
  PASS  create without --priority emits no priority line (default normal, mock only-when-set parity)
  PASS  update <id> priority low round-trips via get
  PASS  search row carries priority as its own column
  PASS  search defaults an unset priority to 'normal' in its column
  PASS  create --priority bogus rejected non-zero
  PASS  invalid create priority rejected with mock-identical message
  PASS  update priority nonsense rejected non-zero
  PASS  invalid update priority rejected with mock-identical message

=== Test Results ===

  Total:  131
  Passed: 131
  Failed: 0

  ALL CONFORMANCE ASSERTIONS PASSED
```

**131/131 PASS** — includes all 9 new priority round-trip/column/ENUM-guard assertions.

### Priority grep counts

```
grep -ic priority scripts/backend-tracker.sh → 4  ✅
grep -ic priority scripts/jira-tracker.sh    → 29 ✅
grep -ic priority scripts/mock-tracker.sh    → 23 ✅
```

### Docs verification

`profiles/neutral/adapters/task-tracking.md` diff confirmed:
- **Before**: "…mapping onto Jira's NATIVE priority field is a documented follow-up."
- **After**: "This label persistence IS the canonical mapping (ABS-261); it deliberately does NOT touch Jira's native priority field."

Corrects the doc-vs-code gap that was the original motivation for this story.

---

## Scope Compliance

- ✅ Only `backend-tracker.sh` modified (the single gap; mock + jira already on main)
- ✅ No schema changes (DB column from migration 002 already existed)
- ✅ Minimal diff: 7 adapter lines + 1 core line + 2 forced unit-test updates + 1 doc line + 1 test section
- ✅ Out-of-scope: native Jira priority field mapping NOT implemented (would break ABS-261 design)
- ✅ Non-blocking system-architect observation noted (pre-existing mock-vs-backend search ordering divergence, ABS-313 vs ABS-331 — out of scope, correctly untouched)

---

## Ticket Flags

`flags: none` — no `design` flag present → exit target: **Story Acceptance**

---

## Final Verdict

**APPROVED**

All BSA re-scope ACs verified independently. Conformance suite 131/131 PASS on a live docker-provisioned backend. Static checks (typecheck/lint/shellcheck) clean. Docs correction confirmed. Scope minimal and correct.
