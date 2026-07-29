# QA Validation — ABS-296

**Ticket**: ABS-296 — Blocked auto-release: sweep re-derives dependency-Blocked tickets  
**Branch**: `ABS-296-auto`  
**HEAD commit**: `55bd609` (fix(orch): whole-token dep-id match in blocked_reason_names_dep)  
**Date**: 2026-07-15  
**Actor**: qas  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | `tests/orchestrator.d/ABS-296-blocked-auto-release.sh` asserts: Blocked ticket with dependency-caused `BLOCKED-FROM=<status>` + all `depends_on` Done → one sweep returns to `<status>` | ✅ PASS | 2/2 assertions pass: "sweep emits BLOCKED-AUTO-RELEASE intent when all depends_on Done" + "ticket returns to its BLOCKED-FROM origin (In Progress)" |
| AC2 | No release while any dependency is not `Done` | ✅ PASS | 4 assertions: single-dep pre-Done check + multi-dep partial-Done guard + multi-dep full-Done release |
| AC3 | No release for non-dependency Blocked entry (TDM/escalation/human park stays Blocked) | ✅ PASS | 5 sub-cases: AC3a (no depends_on), AC3b (escalation_note_stall ADR-A-0018 §d), AC3c (crossvisit_autopark ADR-A-0018 §c/§e), AC3d (human/TDM reason with no dep id), AC3e (prefix-collision whole-token match) — all 10 assertions PASS |
| AC4 | `ORCH_BLOCKED_AUTO_RELEASE=0` reproduces today's behaviour (no release) | ✅ PASS | 2/2 assertions: knob-off suppresses intent + ticket stays Blocked |
| AC5 | Release posts audit comment (dep ids + resolved status) + runlog line; idempotent across sweeps (marker-keyed) | ✅ PASS | 4 assertions: marker posted, no double-release on same entry, re-fires on new Blocked entry, re-released to origin on new entry |
| AC6 | `profiles/neutral/adapters/statuses.yaml` carries `Blocked → <origin>` back-edge; strict-YAML parse passes | ✅ PASS | Python `yaml.safe_load()`: 26 statuses parsed, `Blocked.next` = 23 entries (all valid origin statuses), zero parse errors |

**All 6 ACs: PASS**

---

## Test Suite Results

```
Test file: tests/orchestrator.d/ABS-296-blocked-auto-release.sh
Included via: tests/test-orchestrator.sh (ABS-215 pattern, sourced from orchestrator.d/)

ABS-296 test assertions (21 total):
  PASS  ABS-296 AC2: no release while dependency is not Done
  PASS  ABS-296 AC2: ticket stays Blocked while dep not Done
  PASS  ABS-296 AC1: sweep emits BLOCKED-AUTO-RELEASE intent when all depends_on Done
  PASS  ABS-296 AC1: ticket returns to its BLOCKED-FROM origin (In Progress)
  PASS  ABS-296 AC5: BLOCKED-AUTO-RELEASED marker posted on the ticket
  PASS  ABS-296 AC5: no double-release — T left Blocked so sweep skips it
  PASS  ABS-296 AC5: new Blocked entry (fresh transition) triggers release again
  PASS  ABS-296 AC5: re-released to origin on new Blocked entry
  PASS  ABS-296 AC3a: non-dependency Blocked entry (no depends_on) stays Blocked
  PASS  ABS-296 AC3a: non-dep-blocked ticket still in Blocked after sweep
  PASS  ABS-296 AC3b: escalation-budget loop-breaker park stays Blocked even when deps Done
  PASS  ABS-296 AC3b: escalation-parked ticket still in Blocked (ADR-A-0018 §d integrity)
  PASS  ABS-296 AC3c: cross-visit loop-breaker park stays Blocked even when deps Done
  PASS  ABS-296 AC3c: crossvisit-parked ticket still in Blocked (ADR-A-0018 §c/§e integrity)
  PASS  ABS-296 AC3d: human/TDM park (reason names no dep id) stays Blocked even when deps Done
  PASS  ABS-296 AC3d: human-parked ticket still in Blocked after sweep
  PASS  ABS-296 AC4: ORCH_BLOCKED_AUTO_RELEASE=0 suppresses auto-release (today's behaviour)
  PASS  ABS-296 AC4: ticket stays Blocked when ORCH_BLOCKED_AUTO_RELEASE=0
  PASS  ABS-296 AC2: no release when only some depends_on are Done (DB still pending)
  PASS  ABS-296 AC2: release fires once ALL depends_on are Done
  PASS  ABS-296: multi-dep ticket released to BLOCKED-FROM origin (In Progress) after all deps Done
  PASS  ABS-296 AC3e: prefix-collision dep id in reason does not satisfy whole-token match
  PASS  ABS-296 AC3e: ticket stays Blocked when reason names a prefix-colliding id not the actual dep

Full suite: Total 794 / Passed 794 / Failed 0 — ALL TESTS PASSED
```

---

## Architecture Review Findings Resolved

The system-architect Stage 1 bounce (Iteration 1 of 3, commit `f9b2c6c`) raised two blocking issues. Both are resolved in commits `d2bcf62` and `55bd609`:

### CRITICAL-1 — Release predicate (resolved ✅)

**Root cause**: Original code discriminated on "has `depends_on`" rather than "blocked BECAUSE of dependency". Loop-breaker parks (`crossvisit_autopark`, `escalation_note_stall`) with satisfied deps would have been auto-released, nullifying ADR-A-0018 guarantees.

**Fix**: `blocked_reason_names_dep()` function added. Requires the most recent `-> Blocked` transition reason to name at least one of the ticket's dep ids as a **whole token** (normalises non-alphanumeric chars, uses `case *" $dep "*` match). Fail-closed when no dep id appears.

**Verification**: AC3b (escalation_note_stall), AC3c (crossvisit_autopark), AC3d (TDM/human no-dep reason), AC3e (prefix-collision) — all 8 assertions PASS.

### MEDIUM-1 — Marker ordering (resolved ✅)

**Root cause**: `BLOCKED-AUTO-RELEASED` marker was posted before `tracker transition`. A transient adapter error would have permanently stranded the ticket (marker anchored, but ticket never left Blocked).

**Fix**: Marker is now posted in the `&&` success branch of `if tracker transition ...`. A failed transition logs an error and retries next sweep — self-healing.

**Verification**: Implementation at `orchestrator.sh:3130-3140` — marker comment inside the `if tracker transition ...` success block.

---

## Pattern Compliance

| Check | Result |
|-------|--------|
| Marker as idempotency key (`blocked_auto_release_marker()`) — mirrors `crash_marker_body()`, `blocked_from_marker()` idiom | ✅ |
| `ORCH_BLOCKED_AUTO_RELEASE` knob, `0` = off = today's behaviour | ✅ |
| `runlog`/`intent` audit trail emitted before transition | ✅ |
| One per-story test include `tests/orchestrator.d/ABS-296-blocked-auto-release.sh` (ABS-215 pattern) | ✅ |
| `depends_unmet()` reused — no duplicate dependency evaluation logic | ✅ |
| Origin denylist commented (Backlog excluded deliberately; matches statuses.yaml allowance) | ✅ |
| Marker posted AFTER successful transition (MEDIUM-1 fix; fail-open → fail-closed) | ✅ |
| `is_known_status()` used for origin sanity (AD-2: no hardcoded status class array) | ✅ |

---

## ADR / AD Checks

| Rule | Outcome |
|------|---------|
| ADR-A-0004 (human-approval boundaries) | PASS — only dep-named reason triggers release; loop-breaker and human parks untouched |
| ADR-A-0010 (minimal change) | PASS — scoped to dep-caused Blocked only; `ORCH_BLOCKED_AUTO_RELEASE=0` off switch; depends-gate unchanged |
| AD-1 self-reversal (ABS-279 Architecture Review) | PASS — release keyed on dep-named transition reason (machine-readable evidence the runner caused it) |
| ADR-A-0018 loop-breaker integrity | PASS — verified empirically: escalation-budget and cross-visit loop-breaker parks stay Blocked even when deps Done |

---

## Ticket Flags

`labels: [model:sonnet, orchestrator-ready]` — **no `design` flag**. Exit target: **Story Acceptance**.

---

## Verdict

**APPROVED** — All 6 AC assertions PASS. Full suite 794/794. CRITICAL-1 and MEDIUM-1 from architect Stage 1 review both resolved and verified. ADR-A-0018 loop-breaker integrity confirmed by test. Pattern compliance confirmed. No `design` flag — releasing to Story Acceptance.
