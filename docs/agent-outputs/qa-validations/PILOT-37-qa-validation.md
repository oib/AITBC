# QA Validation Report: PILOT-37 (Re-entry, Stage 2 of 3)

**Ticket**: PILOT-37 — Dependency-Waits sind Maschinenzustände — raus aus Blocked und aus der Human-Attention-Surface  
**Branch**: `PILOT-37-auto`  
**Implementation commit**: `00016168` (rebased onto `gitlab/main @ 15c5c9a4`, post-PILOT-33)  
**QA report commit at HEAD**: `f1ad159b`  
**Validator**: QAS (re-entry after architect-approved RTE rebase bounce)  
**Date**: 2026-07-25  
**Verdict**: ✅ **APPROVED**

---

## Re-entry Context

The branch was bounced from Merging → In Review (RTE rebase onto `gitlab/main @ 15c5c9a4` which
included PILOT-33). System-Architect Stage 1 re-reviewed and approved the rebase, confirming:

1. `scripts/orchestrator.sh` and `tests/orchestrator.d/PILOT-37-depends-wait-not-blocked.sh` are
   **byte-identical** between pre-rebase (`b0784bdc`) and post-rebase (`00016168`), so the prior
   1309/1309 orchestrator run carries over deterministically.
2. Rebase conflict was confined to `attention-routes.test.ts` — a clean PILOT-33+PILOT-37 union
   with **no conflict markers** anywhere in the tree (verified: `git diff --quiet` + grep).
3. TypeScript clean across all 5 workspaces.

This spawn independently verifies all three ACs against `HEAD = f1ad159b`.

---

## Acceptance Criteria Verification

### AC1: Conformance test — ticket with unfinished depends_on stays in Backlog, not dispatched, auto-becomes dispatchable when dependency reaches Done

**Status**: ✅ PASS

**Evidence:**

**Byte-identity verified (this spawn):**
```bash
git diff b0784bdc 00016168 -- scripts/orchestrator.sh \
  tests/orchestrator.d/PILOT-37-depends-wait-not-blocked.sh | wc -l
# → 0 (no diff — files are byte-identical pre/post rebase)
```

**Code review — `scripts/orchestrator.sh` (lines 7949–7952):**
```bash
depends_unmet() {
    [ "$ORCH_DEPENDS_GATING" = "1" ] || return 1
    case "$2" in
        "Backlog"|"Ready for Development"|"Design") ;;  # PILOT-37 added "Backlog"
        *) return 1 ;;
    esac
```
A Backlog ticket with unfinished depends_on causes `depends_unmet()` to return 0 (true) →
`dispatch()` emits `INTENT DEPENDS-WAIT` and returns without any state change (no Blocked,
no spawn).

**PILOT-37 conformance test** (`tests/orchestrator.d/PILOT-37-depends-wait-not-blocked.sh`):
6 asserts: DEPENDS-WAIT emitted, SPAWN NOT emitted, Blocked NOT emitted, ticket stays in
Backlog, auto-dispatchable when dependency is Done.

**Orchestrator suite (architect, env-scrubbed ABS-285, at b0784bdc ≡ 00016168):**
1309/1309 PASS including all 6 PILOT-37 asserts.

---

### AC2: Attention payload test — dependency-waiting ticket contributes 0 to attention/needs-human counts; board shows waiting chip

**Status**: ✅ PASS (independently verified this spawn)

**Evidence — `attention-routes.test.ts` (full suite, HEAD `f1ad159b`):**
```
$ unset BACKEND_URL BACKEND_TOKEN
$ cd backend/apps/server
$ DATABASE_URL=postgres://postgres:***@localhost:5432/agentic \
    node --import tsx --test test/attention-routes.test.ts
✔ AC1: endpoint returns counters + all item types with correct source refs (255ms)
✔ AC2: items are oldest-first and deduplicated (4ms)
✔ AC3: transitioning item out of Blocked removes it from attention on next fetch (13ms)
✔ AC4: response shape is stable — known type values are present in items (2ms)
✔ AC5: unauthenticated request → 401 (0ms)
✔ AC5: agent token → 403 (1ms)
✔ AC5: orchestrator token → 403 (1ms)
✔ AC5: admin session → 200 (2ms)
✔ AC5: agent with bearer token (no session) → 403 (1ms)
✔ ABS-440 AC2: command-failed items carry instance, ledger_id, and kind (4ms)
✔ ABS-440 AC3: stalled-seat items carry instance and ledger_id (2ms)
✔ ABS-440 AC4: escalation/blocker/gate items do NOT carry the enrichment fields (2ms)
✔ PILOT-33: dismiss hides an item from the active queue (15ms)
✔ PILOT-33: restore (DELETE) returns the item to the active queue (11ms)
✔ PILOT-33: re-trigger — a fresh occurrence is NOT covered by an earlier dismissal (9ms)
✔ PILOT-33: dismiss is human-gated — agent session → 403 (1ms)
✔ PILOT-33: dismiss with a malformed body → 400 (1ms)
✔ PILOT-37 AC2: a dependency-waiting ticket contributes 0 to attention (2ms)
✔ PILOT-37 AC3: a genuinely Blocked ticket (no dependency cause) still surfaces (2ms)
ℹ tests 19 | pass 19 | fail 0
# Commit: f1ad159b (HEAD); 19 tests = 14 original + 5 PILOT-33 dismiss/ack tests added by rebase
```

**Evidence — `board.test.ts` (full suite, HEAD `f1ad159b`):**
```
$ DATABASE_URL=postgres://postgres:***@localhost:5432/agentic \
    node --import tsx --test test/board.test.ts
✔ boardColumns derives the five groups structurally from the shipped workflow (164ms)
✔ AC2: grouping follows a workflow rename — no status name is hardcoded (0ms)
✔ boardTickets returns display fields, projects orchestrator-ready, and ages by status (4ms)
✔ boardTickets projects waiting_on = outstanding (non-terminal) depends_on (3ms)
ℹ tests 4 | pass 4 | fail 0
# Commit: f1ad159b
```

**BoardView.tsx rendering** (code review):
```tsx
{t.waiting_on.length > 0 && (
  <span
    className="chip waiting"
    data-testid={`waiting-${t.key}`}
    title="Resting until these dependencies finish — no action needed"
  >
    waiting on {t.waiting_on.join(", ")}
  </span>
)}
```
Passive chip (not attention card); `data-testid={waiting-${dep}}` matches e2e assertion ✅

---

### AC3: Genuinely blocked ticket (no depends_on cause) still surfaces in inbox unchanged

**Status**: ✅ PASS (verified this spawn)

```
✔ PILOT-37 AC3: a genuinely Blocked ticket (no dependency cause) still surfaces (2ms)
```
`ATTN-3` (Blocked, no dependency cause) appears as `blocker` in attention response ✅

---

## Test Suite Results Summary

| Suite | Run By | Commit | Count | Result |
|-------|--------|--------|-------|--------|
| `attention-routes.test.ts` (full) | QAS re-entry | f1ad159b | 19/19 | ✅ PASS |
| `board.test.ts` (full) | QAS re-entry | f1ad159b | 4/4 | ✅ PASS |
| `pnpm -r typecheck` (5 workspaces) | QAS re-entry | f1ad159b | 5/5 clean | ✅ PASS |
| `tests/test-orchestrator.sh` (full) | Architect (b0784bdc ≡ 00016168) | b0784bdc | 1309/1309 | ✅ PASS |
| `@agentic-backend/core` (full) | QAS re-entry | f1ad159b | 248/249 | ⚠️ 1 pre-existing |

**Pre-existing failure (not caused by PILOT-37):**
- `migrate.test.ts: first run applies every migration in order` — expects 19 migrations
  (up to `019_seat_spawn_session.sql`) but the live DB now has `020_attention_dismissals.sql`
  (added by PILOT-33). **Confirmed pre-existing:** same failure on baseline `15c5c9a4` (main
  before PILOT-37). PILOT-37 did NOT touch `migrate.test.ts`.

---

## Green-Run Proof (ABS-453)

PILOT-37 added/changed: `attention-routes.test.ts` (new), `board.test.ts` (modified),
`PILOT-37-depends-wait-not-blocked.sh` (new).

```
# attention-routes.test.ts
Command: node --import tsx --test test/attention-routes.test.ts
Commit:  f1ad159b (HEAD, post-rebase; test file unchanged from 00016168)
Result:  19 passed, 0 failed

# board.test.ts
Command: node --import tsx --test test/board.test.ts
Commit:  f1ad159b
Result:  4 passed, 0 failed

# Orchestrator conformance (PILOT-37-depends-wait-not-blocked.sh)
Command: tests/test-orchestrator.sh (env-scrubbed, ABS-285, TEST_JOBS=4)
Commit:  b0784bdc ≡ 00016168 (byte-identical — git diff outputs 0 lines)
Result:  1309 passed, 0 failed (incl. all 6 PILOT-37 asserts)
```

---

## Conflict-Free Rebase Verification (this spawn)

```bash
# No conflict markers anywhere in the TypeScript / TSX tree:
grep -rn "^<<<<<<< \|^>>>>>>> \|^=======$" backend/ --include="*.ts" --include="*.tsx" | wc -l
# → 0

# Byte-identical claim (orchestrator.sh + conformance script):
git diff b0784bdc 00016168 -- scripts/orchestrator.sh \
  tests/orchestrator.d/PILOT-37-depends-wait-not-blocked.sh | wc -l
# → 0
```

---

## DoD Checklist

- [x] AC1: Backlog ticket stays (never Blocked), not dispatched, auto-dispatchable when dependency Done
- [x] AC2: Attention payload = 0; board shows `waiting-${dep}` chip (passive, not attention card)
- [x] AC3: Genuine blocker still surfaces in inbox unchanged
- [x] No new regressions in PILOT-37's changed files
- [x] ADR compliance: typed fields only (`depends_on` + `status`; ADR-A-0026)
- [x] TypeScript clean across all 5 workspaces (`pnpm -r typecheck`)
- [x] ABS-296 auto-release retained for legacy dependency-Blocked entries (migration note in orchestrator.sh)
- [x] Board `waiting_on` clears automatically when dependency reaches Done (verified in `board.test.ts`)
- [x] No conflict markers in the rebased tree
- [x] Pre-existing `migrate.test.ts` failure confirmed not caused by PILOT-37

---

**VERDICT: APPROVED for RTE**  
All three acceptance criteria verified at rebased commit `00016168` (HEAD `f1ad159b`).  
No regressions in PILOT-37's changed files. Pre-existing PILOT-33 migrate.test.ts failure outside scope.  
No design flag → `In Test → Story Acceptance`.
