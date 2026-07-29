# QA Validation — ABS-255
**Date**: 2026-07-13  
**Branch**: ABS-255-auto  
**Commits under review**: `216fa75`, `b9de5d7`  
**Verdict**: ✅ APPROVED

---

## Commit verification (pre-flight)

Both handoff-claimed commits checked before any other review:

| Hash | git cat-file -e | git for-each-ref --contains | Result |
|------|-----------------|----------------------------|--------|
| `216fa75` | exists | `refs/heads/ABS-255-auto` | ✅ PASS |
| `b9de5d7` | exists | `refs/heads/ABS-255-auto` | ✅ PASS |

The runner is shipping a gate that verifies commit claims; the handoff itself passes that gate.

---

## Files changed

`git diff 84a8816..b9de5d7 --name-only` → 7 files, +669/-6:

| File | Purpose |
|------|---------|
| `adrs/agentic/ADR-A-0024-handoff-commit-verification.md` | Design doc (renamed from 0022; collision resolved) |
| `profiles/neutral/adapters/statuses.yaml` | New `In Progress → Ready for Development` edge |
| `harness/claude/agents/_common-rules.md` | `commits:` field contract in §1 |
| `scripts/orchestrator.sh` | Gate implementation (`commit_verify_failures`, `record_misreport`, `record_claim_nohash`, `handoff_followthrough` wiring, repair prompt) |
| `scripts/skill-mining.sh` | `HANDOFF-MISREPORT` counted into existing `nomove` signal |
| `tests/fixtures/stub-spawn.sh` | `STUB_HANDOFF_COMMITS` + `STUB_HANDOFF_PROSE` env vars |
| `tests/test-orchestrator.sh` | 22 ABS-255 assertions |

---

## AC1 — Design decision: runner-side gate + failure semantics

**Verdict**: ✅ PASS

ADR-A-0024 documents all design choices:

- **(a) Where**: `handoff_followthrough()` in the runner, before `apply_handoff_transition()`. Reviewer-template verification rejected (the reference Befund was a reviewer-side failure — `fe-developer` echoed the false claim).
- **(b) Machine-readable claim**: `commits: <sha> [<sha> ...]` field in the handoff record. Prose hex-scraping rejected (false positives on PR ids, UUIDs).
- **(c) Two checks**: existence (`git cat-file -e <sha>^{commit}`) then reachability (`git for-each-ref --contains`). "No ref contains it" matches the Befund's actual ground truth.
- **(d) Failure semantics**: refuse transition → undo self-transition (to `Ready for Development`, now legal) → post `HANDOFF-MISREPORT` gate-results comment naming each failing hash → rest ticket for fresh spawn.
- **(f) Hash-less prose**: advisory `HANDOFF-CLAIM-NOHASH`, non-blocking (known false-positive class in review seats).
- **(g) Kill-switch**: `ORCH_VERIFY_COMMITS=1` default-on; `=0` restores pre-ABS-255 behaviour.

ADR number collision resolved: 0022 retained by ABS-258 (already on origin); this ADR renumbered to 0024 (ticket-id order). `status: proposed` per ADR-A-0004 (human acceptance).

---

## AC2 — Implementation with tests

**Verdict**: ✅ PASS

### Functions verified in `orchestrator.sh`

- **`handoff_commits()`**: parses `commits:` field only; drops non-hex tokens (`none`, `n/a`).
- **`handoff_claims_commit()`**: prose regex for advisory path; never blocking.
- **`commit_verify_failures()`**: runs both checks against `$ORCH_STATE_ROOT`; fail-open when git unavailable or no claim.
- **`misreport_marker()` / `misreport_count()`**: mirror `nomove_marker` / `nomove_count` shape.
- **`record_misreport()`**: posts `HANDOFF-MISREPORT` comment; undoes self-transition to `$to` (actor = seat role, so `rework_count()` counts it); falls through to escalation budget if ticket rests.
- **`record_claim_nohash()`**: posts `HANDOFF-CLAIM-NOHASH` advisory; does not count.
- **`handoff_followthrough()`**: calls `commit_verify_failures()` before `apply_handoff_transition()`.
- **Repair prompt** (line 5134): includes `commits:` field description and ABS-255 enforcement note.

### `statuses.yaml`

`In Progress → Ready for Development` edge added with rationale comment (ADR-A-0024 d.2; operator precedent; the only active impl stage missing the ADR-A-0002 bounce edge).

### `_common-rules.md` §1

`commits:` field contract added: REQUIRED when commits created, verified by the runner, with the two check descriptions. Seats already run `git log --oneline -1`; this makes the output machine-readable.

### `skill-mining.sh`

`INTENT-HANDOFF-MISREPORT` added to the `nomove` signal condition (one-line change).

### Test results

Ran a focused script (`tests/test-orchestrator.sh` ABS-255 section, lines 3806–3958):

```
22/22 PASS — exit 0
```

Scenarios covered:

| Scenario | Assertions | Result |
|----------|------------|--------|
| Verified commit claim accepted | 2 | ✅ |
| Fabricated hash refused | 5 | ✅ |
| Orphaned commit (no ref) refused | 2 | ✅ |
| Self-transition UNDONE on mis-report (d.2) | 3 | ✅ |
| Repeated mis-reports → Needs PO Decision | 2 | ✅ |
| No claim → gate inert (fail-open) | 2 | ✅ |
| Hash-less prose → ADVISORY, not blocking | 3 | ✅ |
| Kill-switch ORCH_VERIFY_COMMITS=0 | 2 | ✅ |

The 2 assertions that previously required the `In Progress → Ready for Development` edge now pass (that edge is in the commit preceding the gate implementation). The SA's claim of "22/22 PASS" is confirmed independently.

---

## AC3 — Mis-report feeds existing counters, no new machinery

**Verdict**: ✅ PASS

- **Back-transition path** (d.2): `record_misreport()` calls `tracker transition "$ticket" "$to" --actor "$role"`. A backward, non-human transition is counted natively by `rework_count()` → `ORCH_REWORK_LIMIT` → `escalate_rework` → `Needs PO Decision`. No new code.
- **Rest path** (d.4): `misreport_count()` mirrors `nomove_count()`; `escalation_note_stall()` (ADR-A-0018 escalation budget) is called. `ORCH_RESPAWN_LIMIT` bounds it.
- No new status, no new counter, no new loop-breaker. `skill-mining.sh` adds `HANDOFF-MISREPORT` to the existing `nomove` signal.
- Test assertion "k consecutive mis-reports escalate to Needs PO Decision (existing counter, no new machinery)": ✅ PASS.

---

## Minor observation (non-blocking)

`new_env()` does not include `STUB_HANDOFF_COMMITS` or `STUB_HANDOFF_PROSE` in its `unset` block. Each ABS-255 test scenario explicitly unsets them after use, so there is no functional leak between tests. The fix (adding two vars to `new_env`'s unset list) would be defensive only.

---

## Summary

| Criterion | Status |
|-----------|--------|
| AC1: Design decision documented | ✅ PASS |
| AC2: Implementation + 22/22 tests | ✅ PASS |
| AC3: Existing counters reused | ✅ PASS |
| Commits exist and ref-reachable | ✅ PASS |
| No new counter / status / loop-breaker | ✅ PASS |
| ADR number collision resolved | ✅ PASS |
| Kill-switch default-on | ✅ PASS |

**Final verdict: APPROVED**. Branch `ABS-255-auto` ready for Story Acceptance.
