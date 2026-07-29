# QA Validation Report — ABS-301

**Ticket**: ABS-301 — Escalation budget must not park tickets in terminal status or mid-work legitimate-progress states  
**Branch**: `ABS-301-auto`  
**Commit reviewed**: `4b51b45`  
**Files changed**: 4 (`adrs/agentic/ADR-A-0018-cross-visit-blocker-classification.md`, `profiles/neutral/adapters/statuses.yaml`, `scripts/orchestrator.sh`, `tests/orchestrator.d/ABS-301-escalation-exemption.sh`)  
**QAS run date**: 2026-07-14  
**Iteration**: 1 of 3  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

| # | Criterion | Verified | Result |
|---|-----------|----------|--------|
| AC1 | `ABS-301-escalation-exemption.sh` Part 1: terminal status accumulates no stall rounds, never parked | Independent test run | ✅ PASS |
| AC2 | Same test Part 3: epic-pipeline forward transition resets counter — hw≥27 (Epic Integration), count→0, ABS-245 3\t0 cannot recur | Independent test run | ✅ PASS |
| AC3 | Same test Part 4: genuine stall on non-terminal status still parks at `ORCH_ESCALATION_BUDGET` rounds — no real-stall masking | Independent test run | ✅ PASS |
| AC4 | `statuses.yaml` carries `terminal: true` on every status with `next: []`; test asserts flag read from file (not hardcoded); strict-YAML parse passes | Strict python3 yaml.safe_load + test run | ✅ PASS |
| AC5 | `ADR-A-0018.md` §d notes the terminal-status exemption and ratchet fix (both with evidence ABS-217/ABS-245) | Direct source read | ✅ PASS |

---

## Independent Verification Details

### AC1 — Terminal status exemption (Part 1)

Ran `tests/test-orchestrator.sh` capturing ABS-301 lines:

```
PASS ABS-301 AC1: escalation_note_stall returns no-park (1) on terminal status for BOTH calls
PASS ABS-301 AC1: stall counter stays 0 — terminal status is not counted
```

Test directly exercises `escalation_note_stall("T-TERM", "Epic Done")` called twice (= `ORCH_ESCALATION_BUDGET=2`). Both calls return 1 (no-park). Stall counter reads 0 after both calls. The terminal guard in `escalation_note_stall()` (line 2925: `status_is_terminal "$status" && return 1`) correctly gates out before writing to state.

### AC2 — Ratchet fix (Part 3)

Pre-loaded the ABS-245 `3\t0` escalation state (count=3, hw=0). Ran one reconcile cycle in `--live --once` mode.

```
PASS ABS-301 AC2 setup: pre-loaded escalation count=3 (the ABS-245 3\t0 ratchet)
PASS ABS-301 AC2: JOIN fires (all children Done)
PASS ABS-301 AC2: escalation_note_progress logged ESCALATION-RESET after JOIN (ratchet fix)
PASS ABS-301 AC2: high-water mark >= 27 (Epic Integration chain_index) — counter tracked epic progress
PASS ABS-301 AC2: epic NOT falsely parked to Blocked — the 3-round pre-JOIN stall count was reset
```

Both ratchet call sites verified in source:
- `join_check_epic` (:3511–3514): inside live-mode + successful-transition branch only
- `epic_join_rest_complete` (:2751): inside the successful-transition block only
Neither fires on a failed or dry-run transition.

### AC3 — Real stalls still park (Part 4)

```
PASS ABS-301 AC3: first stall round does NOT park (below budget)
PASS ABS-301 AC3: genuine stall reaches budget and returns park=0 — real stalls still caught
```

Non-terminal status (`Ready for Development`) at budget=2: first call returns NOPE-1 (no park), second returns PARKED-2 (parks). Real stall detection unchanged.

### AC4 — Declarative terminal flag (YAML + Part 2)

Independent Python3 strict parse:
```
Parsed OK: 26 statuses
terminal: true statuses: ['Epic Done']
no outbound edge statuses (next:[]): ['Epic Done']
PASS: terminal set == no-outbound-edge set (exact match)
```

Key subtlety verified: `Done` is correctly **NOT** flagged `terminal: true` — it retains a legal bisect-reopen edge to `Ready for Development`. The prose comment in statuses.yaml calls it "terminal" but the flag is absent, which is correct.

No hardcoded status-name list found in the diff (AD-2 satisfied). `status_is_terminal()` reads via awk:
```bash
awk -v name="$1" '
    /^  - name: / { cur = substr($0, 11); next }
    cur == name && /^    terminal: true/ { found=1; exit }
    END { exit (found ? 0 : 1) }
' "$sf"
```
Fallback path `${MOCK_TRACKER_STATUSES:-$ORCH_HARNESS_HOME/profiles/neutral/adapters/statuses.yaml}` mirrors the established convention. Returns 1 (not terminal) when file is absent — safe fallback.

```
PASS ABS-301 AC4: status_is_terminal reads terminal:true from statuses.yaml — Epic Done is terminal
PASS ABS-301 AC4: status_is_terminal reads from file — In Progress is NOT terminal (not hardcoded)
```

### AC5 — ADR-A-0018 §d amendment

§d was verified to contain:
- Terminal-status exemption paragraph (ABS-301 reference, ABS-217/ABS-245 evidence citations)
- Ratchet fix paragraph with `join_check_epic` and `epic_join_rest_complete` references and ABS-245 evidence
- `status: accepted` on the ADR was **not flipped** (ADR-A-0004 boundary respected ✅)

---

## Test Suite Results

```
Total:  782
Passed: 782
Failed: 0

ALL TESTS PASSED
```

---

## Architecture Review Notes (from system-architect Stage 1)

Confirmed independently:
- AD-2 (station class from statuses.yaml, never hardcoded): **satisfied** — no added name list or status `case` in diff
- `terminal:true` set == no-outbound-edge set: **exact match** (Epic Done only)  
- Both ratchet calls inside live + successful-transition branch: **confirmed**
- ADR `status: accepted` unchanged: **confirmed**

**Residual noted (not a blocker)**: Fresh no-move rounds accumulated *while the RTE legitimately works at Epic Integration* (bisect running) will still park the epic at budget — from a clean baseline instead of `3\t0`. ABS-245's exact recurrence is closed; the broader "long legitimate work looks like a stall" class is narrowed, not eliminated. Correctly out of scope per ticket. Follow-up recommended in ABS-279.

---

## Flags Check

Ticket `flags` line: none — no `design` flag present.  
Exit transition: **Story Acceptance** (design flag absent; SKIP-FORWARD past Design Test applies per spec §3.3).

---

## Verdict

**✅ APPROVED — All 5 ACs met and independently verified. 782/782 tests pass. Transitioning ABS-301 to Story Acceptance.**
