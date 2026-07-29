# QA Validation Report — PILOT-31

**Ticket**: PILOT-31 — S6: Shipper-Telemetrie-Tail per tail -F statt 5-s-Sleep-Schleife  
**QAS**: qas  
**Date**: 2026-07-25  
**Commit under review**: 94c24ee75f6052fdc34d4d4679a56817f6958b13  
**Branch**: PILOT-31-auto  
**Verdict**: ✅ APPROVED

---

## Validation Environment

- Worktree: `/tmp/PILOT-31-work` (branch `PILOT-31-auto`, commit `94c24ee7`)
- shellcheck 0.11.0 (Homebrew)
- bash syntax check via `bash -n`
- All test suites run with `unset BACKEND_URL BACKEND_TOKEN` (no live backend needed)

---

## Static Analysis

| Check | Command | Result |
|-------|---------|--------|
| Bash syntax | `bash -n scripts/backend-shipper.sh` | ✅ PASS — SYNTAX OK |
| shellcheck | `shellcheck -S warning scripts/backend-shipper.sh` | ✅ PASS — no output (clean) |

---

## Test Suite Results

### test-shipper-tail.sh (AC1–AC5 new coverage)

Command: `unset BACKEND_URL BACKEND_TOKEN && bash tests/test-shipper-tail.sh`  
Commit: `94c24ee75f6052fdc34d4d4679a56817f6958b13`  
**Result: 14/14 PASSED**

```
=== AC1: new line → ingest POST < 2s (wake, not poll) ===
  PASS AC1: initial drain shipped the RUN-START event (1 >= 1)
  PASS AC1: appended line was shipped
  PASS AC1: latency under 2s (1 <= 2)
=== AC5: mid-run new ledger file discovered within poll interval ===
  PASS AC5: mid-run ledger line was discovered and shipped (no loss)
  PASS AC5: discovery latency within poll interval (2s) + slack (2 <= 4)
  PASS AC5: ledger line shipped exactly once (no duplicate)
=== AC3: 500-line burst → batched POSTs, no line-by-line ===
  PASS AC3: all 500 burst lines shipped exactly once (+RUN-START)
  PASS AC3: shipped as batches, not 500 single POSTs (6 <= 20)
  PASS AC3: more than one POST (batching, initial drain + burst) (6 >= 2)
=== AC2: truncate → no lost, no duplicated events ===
  PASS AC2: first drain shipped 3 events
  PASS AC2: post-truncate line shipped (no loss)
  PASS AC2: pre-truncate line not re-shipped (no duplicate)
  PASS AC2: total events = 3 (pre) + 2 (post-truncate), none lost/dup
=== AC4: SHIPPER_TAIL=0 legacy sleep loop still ships ===
  PASS AC4: SHIPPER_TAIL=0 sleep loop shipped the new line
=== Test summary ===
PASS 14/14 tests passed
```

### test-shipper-commands.sh (existing regression suite)

Command: `unset BACKEND_URL BACKEND_TOKEN && bash tests/test-shipper-commands.sh`  
Commit: `94c24ee75f6052fdc34d4d4679a56817f6958b13`  
**Result: 42/42 PASSED**

```
=== Test summary ===
PASS 42/42 tests passed
```
(Full output: all individual test lines green)

### test-backend-shipper.sh (existing baseline)

Command: `unset BACKEND_URL BACKEND_TOKEN && bash tests/test-backend-shipper.sh`  
Commit: `94c24ee75f6052fdc34d4d4679a56817f6958b13`  
**Result: 8/8 PASSED**

```
=== Test summary ===
PASS 8/8 tests passed
```

---

## Acceptance Criteria Verification

| AC | Criterion | Evidence | Result |
|----|-----------|----------|--------|
| AC1 | New run.log line → Ingest-POST <2s | `latency under 2s (1 <= 2)` — test-shipper-tail.sh | ✅ PASS |
| AC2 | Log-Rotation/Truncate → no lost, no duplicated events (cursor proof) | AC2 block: 3 pre-truncate events exact, 2 post-truncate shipped, no re-ship | ✅ PASS |
| AC3 | 500-line burst → batched POSTs (≤ Batch-Size), not 500 single-POSTs | `6 <= 20` posts for 500 lines | ✅ PASS |
| AC4 | SHIPPER_TAIL=0 restores exact legacy sleep-loop behavior; existing tests green | AC4 test pass + 42/42 test-shipper-commands + 8/8 test-backend-shipper | ✅ PASS |
| AC5 | Mid-run new ledger file discovered within poll interval (≤5s); no loss of pre-discovery lines (cursor) | `2 <= 4` latency; shipped once | ✅ PASS |

---

## Design-Vorgaben Compliance

| Requirement | Verified |
|-------------|----------|
| zero-dep (tail -F only, no fswatch/inotify) | ✅ — `grep` confirms only `tail` used |
| Cursor stays authoritative | ✅ — rotation/restart cursor behavior covered by AC2 + AC4 |
| Coalescing batch window retained | ✅ — AC3 burst test: 500 lines → 6 batches |
| SHIPPER_FOLLOW=0 (drain+exit) unchanged | ✅ — existing 42/42 + 8/8 tests green |
| SHIPPER_TAIL=0 fallback | ✅ — AC4 explicit test |
| Discovery for mid-run ledger files | ✅ — AC5 with ≤4s (≤5s poll bound) |
| ADR-A-0009 (zero-dep) / ADR-A-0010 (outbound-only) | ✅ — commit message confirms; static analysis clean |

---

## Flags Check

Ticket flags: `labels: [orchestrator-ready]` — no `design` flag.  
Exit transition: **Story Acceptance** (not Design Test).

---

## Verdict

**✅ APPROVED for Story Acceptance**

All 5 ACs verified. All three test suites (14/14 + 42/42 + 8/8) green. Static analysis clean.  
Commit `94c24ee7` on branch `PILOT-31-auto` meets the spec.
