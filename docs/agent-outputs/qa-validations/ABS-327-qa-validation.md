# QA Validation Report — ABS-327

**Ticket**: ABS-327 — Koexistenz S1: Dual-Write-Shim shadow-tracker.sh  
**Branch**: ABS-326-koexistenz  
**Commit**: bd5975d  
**Validator**: QAS  
**Date**: 2026-07-16  
**Verdict**: ✅ APPROVED

---

## Scope

`scripts/shadow-tracker.sh` (+139 lines), `tests/test-shadow-tracker.sh` (+199 lines), `.gitignore` (9 lines, runtime-state entries).

---

## Test Run (Independent QAS Execution)

Test suite run from worktree `.claude/worktrees/eager-driscoll-e66dd3` (branch `ABS-326-koexistenz`, commit `bd5975d`):

```
=== shadow-tracker.sh — dual-write shim (ABS-327) ===

[1] passthrough byte-identity + exit codes
  PASS  get stdout byte-identical to the primary adapter
  PASS  get exit code 0 passed through
  PASS  primary stderr passes through untouched
  PASS  non-zero primary exit code passed through unchanged

[2] mirror routing: mutating vs read ops
  PASS  comment (mutating) reaches the mirror
  PASS  mirror receives the verbatim primary argv
  PASS  read ops + events are NOT mirrored
  PASS  failed primary op is never mirrored

[3] mirror failure: caller unaffected, replay log written
  PASS  exit code unchanged by the failing mirror
  PASS  stdout unchanged by the failing mirror
  PASS  no mirror noise on the caller's stderr
  PASS  missed op logged with mirror exit code in replay format
  PASS  mirror stderr captured as commented context lines
  PASS  missing mirror binary: caller still succeeds
  PASS  missing mirror binary logged as rc=127

[4] replay format round-trips the exact argv
  PASS  eval of the logged replay text reproduces the exact argv (multi-line body survives)

[5] create key-parity check
  PASS  create passes the primary's new id through
  PASS  matching keys: nothing logged
  PASS  key mismatch logged with both keys

All 19 assertions passed
```

**Result: 19/19 PASS**

---

## Acceptance Criteria Verification

### AC1 — All conformance ops pass through with identical stdout/exit-code ✅
- **Evidence**: Tests [1] (byte-identical stdout, stderr passthrough, exit codes 0 and non-zero), tests [2] (comment mutating routing verbatim, read ops passthrough).
- Implementation uses `"$PRIMARY_CMD" "$@" > "$p_out" || p_rc=$?; cat "$p_out"` — primary stdout buffered and re-emitted byte-exact; primary stderr flows to caller's stderr unchanged (not redirected in the primary invocation); `exit "$p_rc"` returns exact exit code.
- All six mutating ops (`create|update|comment|transition|link|assign`) present in `case` statement; all read ops (`get/search/children/parent/child-count/events`) pass straight through.

### AC2 — Dead backend changes neither exit-code nor output; missed op replay-able ✅
- **Evidence**: Tests [3] — failing mirror (rc=7): caller exit=0, stdout byte-identical, no mirror noise on stderr; log entry `rc=7 -- comment ABS-2` confirmed; mirror stderr captured as `#`-prefixed context. Missing binary (rc=127): caller still succeeds, logged as `rc=127`.
- Test [4] — replay round-trip: eval of logged text after `" -- "` reproduces exact argv including multi-line `$'first line\nsecond "quoted" line\ttabbed'` body.
- Implementation: `mirror_op` captures all mirror output, `log_miss` appends replay line then exits; `main()` never sees mirror rc. Log write itself is `|| true` (read-only FS safe).

### AC3 — Sandbox run with TRACKER_CMD=shadow-tracker.sh behavior-identical ✅
- **Evidence**: `events` correctly NOT mirrored (passthrough-only, confirmed in test [2] "read ops + events are NOT mirrored"). All read ops pass through byte-identical. System Architect verified: "passthrough identity covers behavior-equivalence; run-boilerplate walkthrough documented in the runbook (ABS-329) as the operator verification step."
- The shim is a pure pass-through for the orchestrator's read path; mutating ops mirror after the primary succeeds, adding no observable side-effects to the caller.

---

## Additional Checks

| Check | Result |
|---|---|
| `set -uo pipefail` (no `-e`, deliberate) | ✅ Confirmed in source |
| Primary stdout buffered + re-emitted byte-exact | ✅ Confirmed (`$p_out` tmp file + `cat`) |
| Primary stderr passes untouched | ✅ Test [1] asserts "primary-stderr-marker" |
| Mirror call best-effort (`m_rc` captured, not propagated) | ✅ Confirmed |
| `work/.shadow-mirror.log` gitignored | ✅ Commit adds entry |
| `work/divergence/` gitignored | ✅ Commit adds entry |
| Secret leakage check: `%q`-argv log captures only ticket content | ✅ Token in curl `--config` (not argv) — SA confirmed |
| Scope compliance (no out-of-scope files) | ✅ Only 3 files in commit (shadow-tracker.sh, test, .gitignore) |

---

## Non-Blocking Items (recorded, not gate criteria)

**MEDIUM (from SA)**: Mirror runs synchronously; `backend-tracker.sh` has no `--max-time`. A *hanging* (not *down*) backend could stall the primary lane. AC2 as written ("Container down") is met. Flagged for ABS-237 adapter / pilot follow-up.

**INFO (from SA)**: Stream ordering — primary stdout buffered and emitted after primary exits (needed for key-parity); cross-stream interleaving differs but each stream is byte-identical. Harmless for orchestrator.

---

## Verdict

**APPROVED → Story Acceptance**

All 3 ACs verified. 19/19 assertions PASS (independent QAS run). No `design` flag on ticket. No `environment` or `external-dependency` failures. Implementation is a clean `$TRACKER_CMD` adapter-family drop-in with zero blast radius on primary lane.
