# QA Validation Report — ABS-322
**Ticket**: ABS-322 — v3 Fastlane: kollabierte Kette — Solo-Seat + kombiniertes Gate + Merge-Queue
**QAS Actor**: qas
**Date**: 2026-07-16
**Commits**: dd99ec5 (initial impl) + cce2cbb (iter-2 fix: thread seat_note into packet)
**Verdict**: ✅ APPROVED — all AC1–AC5 PASS, no regressions, guardrails intact

---

## Test Suite Results

| Suite | Count | Result |
|---|---|---|
| `bash tests/test-orchestrator.sh` (4 shards) | 1004/1004 | **PASS** |
| `bash -n scripts/orchestrator.sh` | — | **CLEAN** |
| `shellcheck -S error scripts/orchestrator.sh` | 7 findings | **ZERO NEW** (identical to baseline dd99ec5) |
| Working tree | — | **CLEAN** (HEAD at cce2cbb) |

All 23 ABS-322-specific assertions in `tests/orchestrator.d/ABS-322-fastlane-collapse.sh` passed (10 intent-log assertions + 6 packet-seam assertions via STUB_PACKET_COPY on live spawns + 7 control/kill-switch assertions).

---

## Acceptance Criteria Validation

### AC1 — Single Solo-Seat (no separate QAS/Design/Review spawns)
**PASS**

Evidence from test suite:
- `ABS-322 AC1: fastlane implementer spawns exactly one Solo-Seat` → PASS
- `ABS-322 AC1: fastlane In Test is folded forward, not spawned as a separate QAS seat` → PASS (FASTLANE-COLLAPSE with `target=Design Test`)
- `ABS-322 AC1: no separate QAS spawn for a fastlane ticket` → PASS

Implementation: `fastlane_skip()` folds `In Test → Design Test` over a legal edge (statuses.yaml line 219 confirms `Design Test` is in `In Test.next`). Mirrors ABS-84/ABS-124 skip machinery.

### AC2 — Solo-Seat produces impl + scoped test evidence + self-review record
**PASS**

Evidence from packet-seam assertions (STUB_PACKET_COPY on a live `--live --once` spawn):
- `ABS-322 AC2: the Solo-Seat directive REACHES the seat packet (not just the run.log)` → PASS
  - Packet contains `seat_note: fastlane-solo-seat:dev+scoped-tests+self-review`
- `ABS-322 AC2/B2: the packet instructs the Solo-Seat to actually run scoped tests + self-review` → PASS
  - Packet contains `seat_note_directive:` with explicit instruction to run ticket-scoped tests and post a self-review record

The iter-1 architecture bounce (B1) is cleared: `build_packet` now accepts `$6 (seat_note)` and renders it as a `seat_note:` header + `seat_note_directive:` in `$pf` (the seat's stdin). The note is also in the packet cache signature (invalidates cache on note change).

### AC3 — Combined gate runs review AND scoped tests as one gate before merge-queue
**PASS**

Evidence from intent-log assertions + packet-seam assertions:
- `ABS-322 AC3: fastlane In Review spawns the single combined gate` → PASS
- `ABS-322 AC3: the gate is marked review+scoped-tests (one gate)` → PASS
- `ABS-322 AC3: the combined-gate directive REACHES the reviewer packet` → PASS
  - Packet contains `seat_note: fastlane-combined-gate:review+scoped-tests`
- `ABS-322 AC3/B2: the combined gate is instructed to run scoped tests (one gate replaces QAS+review)` → PASS
  - Packet directive: "the tests must actually execute here before the ticket enters the merge-queue"
- `ABS-322 AC3: no synchronous PO seat in the collapsed chain (deferred to ABS-323)` → PASS (Story Acceptance folds to Merging)

B2 and B3 from the architecture bounce are cleared: the combined-gate directive now reaches the reviewer's stdin packet (not just run.log), and is asserted at the correct packet seam.

### AC4 — `lane=normal` ticket walks full v3 pipeline unchanged
**PASS**

Evidence — all control assertions pass:
- `ABS-322 AC4: normal-lane implementer is unchanged` → PASS
- `ABS-322 AC4: normal-lane spawn carries no fastlane Solo-Seat mark` → PASS
- `ABS-322 AC4: normal-lane In Review unchanged` → PASS
- `ABS-322 AC4: normal-lane gate carries no fastlane mark` → PASS
- `ABS-322 AC4: normal-lane In Test still spawns QAS` → PASS
- `ABS-322 AC4: normal-lane ticket is never fastlane-collapsed` → PASS
- `ABS-322 AC4: normal-lane packet carries no seat_note (byte-unchanged header)` → PASS (packet-seam)
- `ABS-322 AC4: normal-lane In Review packet carries no seat_note` → PASS (packet-seam)

Every fastlane branch is gated on `lane=fastlane AND ORCH_FASTLANE_COLLAPSE=1`. Normal-lane spawns pass an empty `seat_note` → byte-identical header.

### AC5 — Chain ends at merge-queue; no merge token, no merge to main
**PASS**

Evidence:
- `ABS-322 AC5: passing fastlane work is enqueued onto the merge-queue (Merging)` → PASS
  - `Story Acceptance → Merging` is a legal edge (statuses.yaml line 254 confirms)
- `ABS-322 AC5: the collapse issues no merge token` → PASS

Independently verified: `fastlane_collapse_target "Story Acceptance"` returns `Merging`, not a merge-token call. Guardrails (merge-token, full suite at epic integration, human merge to main) are untouched — no code changes on those paths.

### Kill-Switch
- `ABS-322: knob=0 restores the full chain (QAS runs for a fastlane ticket)` → PASS
- `ABS-322: knob=0 emits no FASTLANE-COLLAPSE` → PASS

---

## Fold Edge Legality (independent verification)

| Fold | From | To | statuses.yaml line | Legal |
|---|---|---|---|---|
| QAS station folded | In Test | Design Test | 219 | ✅ |
| PO station folded | Story Acceptance | Merging | 254 | ✅ |

Both targets appear in `.next` lists for the respective source statuses.

---

## Diff Analysis

- `dd99ec5`: +99/-0 on `scripts/orchestrator.sh`; +105 on `tests/orchestrator.d/ABS-322-fastlane-collapse.sh`
- `cce2cbb`: +27 on `scripts/orchestrator.sh`; +54 on `tests/orchestrator.d/ABS-322-fastlane-collapse.sh`
- Combined: minimal, mirrors existing `gate_skip`/ABS-84/ABS-124 skip machinery; `build_packet` generalized (not special-cased)
- No changes to: merge-token logic, full suite at epic integration, human merge to main, lane=normal paths

---

## Definition of Done

| Item | Status |
|---|---|
| All AC1–AC5 verified with evidence | ✅ PASS |
| No regressions in full suite (1004/1004) | ✅ PASS |
| bash -n syntax clean | ✅ PASS |
| shellcheck: zero new errors vs baseline | ✅ PASS |
| Working tree clean at HEAD cce2cbb | ✅ PASS |
| Fold edges legal (statuses.yaml) | ✅ PASS |
| Guardrails (merge-token/full-suite/human-merge) untouched | ✅ PASS |
| Kill-switch ORCH_FASTLANE_COLLAPSE=0 restores full chain | ✅ PASS |

---

## Verdict

**APPROVED for Story Acceptance.**

All five acceptance criteria are met. The architect bounce (B1/B2/B3) is fully cleared: the `seat_note` now threads `do_spawn_action → live_spawn → attempt_spawn → build_packet` and is rendered as a `seat_note:` header + `seat_note_directive:` in the seat's stdin packet, with packet-seam assertions proving delivery. The collapsed chain folds over legal edges, normal-lane is byte-identical, and the chain ends at the merge-queue with no merge token.

This ticket has no `design` flag → exit to **Story Acceptance**.
