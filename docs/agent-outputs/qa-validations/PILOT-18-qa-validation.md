# QA Validation — PILOT-18

**Ticket**: PILOT-18 — Sweep-basierte MR-Conflict-Detection  
**QAS Spawn**: resumed (prior QA at 42/42; forward-fix `83052255` added 1 regression assert → 43/43)  
**Branch**: `PILOT-18-auto`  
**HEAD validated**: `83052255`  
**Date**: 2026-07-25  
**Verdict**: ✅ APPROVED FOR RTE

---

## Test Results (this spawn, against HEAD `83052255`)

| Suite | Count | Result |
|---|---|---|
| `bash -n scripts/orchestrator.sh` | — | SYNTAX CLEAN |
| `tests/test-merge-conflict-redirect.sh` | 43/43 | PASS |
| `tests/test-merge-wait.sh` | 51/51 | PASS |
| `tests/test-merge-wait-target.sh` | 16/16 | PASS |
| `tests/test-ready-for-merge-gate.sh` | 40/40 | PASS |
| `tests/test-orchestrator.sh` (full suite) | 1286/1286 | PASS |

**Total sibling+conformance: 150/150 PASS. Full suite: 1286/1286 PASS. Zero failures.**

---

## AC-by-AC Verification

**AC1** — Conflicted MR at Merge-Gate → Transition to Merging with recipe reason + INTENT line within one sweep; dependents unaffected.  
`merge_conflict_redirect` fires on `story_mergeability == CONFLICT`. Posts a `gate-results` comment with the PILOT-9 resolution recipe (`scripts/next-migration-number.sh`, `--force-with-lease`), calls `intent MERGE-CONFLICT-REDIRECT`, transitions `Ready for Merge → Merging` with `--expect-from`. `notify` fires after the transition lands. 11 assertions in the conformance suite. **MET.**

**AC2** — Clean or undecidable MR → no action, no log spam.  
`CLEAN` and `UNKNOWN` return before any write (`[ "$mstate" = "CONFLICT" ] || return 1`). Forge lane fails open (UNKNOWN) when the backend endpoint lacks `mergeable`. 5 assertions cover CLEAN and UNKNOWN paths. **MET.**

**AC3** — Same (MR-head, target-head) → redirect fires once only.  
Per-fingerprint marker under `$ORCH_STATE_DIR`; a matching `last` marker skips the redirect. A moved target HEAD or a rebased MR HEAD resets the fingerprint and fires again. 4 assertions. **MET.**

**AC4** — Ancestor/merged-ness release authority stays with `merge_wait_release`.  
`merge_conflict_redirect` runs independently and returns early on a MERGED MR (MERGED → `story_mergeability` returns CLEAN → no-op). `merge_wait_release` code untouched; 4 new + 107 sibling regression asserts confirm no regression. **MET.**

---

## Forward-Fix (83052255) Verification

`story_mergeability` originally probed any remote `<id>-auto` branch as authoritative. A real `DEMO-1-auto` (ABS-225 work) conflicted with `main`, causing a false `CONFLICT` on test ticket `DEMO-1` and breaking 3 `test-orchestrator.sh` assertions at the PILOT-17 epic gate.

Fix: before treating a branch tip as authoritative, verify its commits ahead of the target carry a `[<ticket>]` SAFe tag (`git log --grep="[$ticket]" --fixed-strings`). A foreign name-collision carries no such tag → `UNKNOWN` (fail-open). 12 lines added to `scripts/orchestrator.sh`; 1 regression assertion added to the conformance suite (43 total). Fix is minimal and pilot-lane scoped. **Verified correct.**

---

## Scope Check

Commits on `PILOT-18-auto` beyond `main`:
- `e7a704fb` — feat: sweep conflict detection (+140 lines orchestrator.sh, new test suite)
- `2dbd5380` — chore: prior QA evidence
- `ba8447b3` — docs: MERGE-CONFLICT-REDIRECT-GUIDE
- `83052255` — fix: ABS-225 collision guard (+12 lines orchestrator.sh, +1 test assert)

No unrequested scope. Forge lane, ancestor/merged-ness release path, and auto-resolution doctrine all untouched. Outbound-only poll preserved (ADR-A-0010, ADR-A-0026 P11).

---

## Verdict

All four ACs met. Forward-fix eliminates the false-CONFLICT regression cleanly. Full 1286/1286 orchestrator suite green (3 prior epic-gate failures now resolved). No design flag → releasing to **Story Acceptance**.
