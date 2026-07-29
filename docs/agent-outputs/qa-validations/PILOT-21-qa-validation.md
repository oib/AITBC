# QA Validation — PILOT-21

**Ticket**: Stacked-MR-Verlustklasse: Base-Rebase verwarf gemergte Stacked-Commits still — Guard + Recovery  
**Commit**: `b82c4404` on `PILOT-21-auto`  
**Diff**: `scripts/merge-target-guard.sh` (+44/-5), `tests/test-stacked-mr-guard.sh` (+209 new)  
**QAS run date**: 2026-07-24  
**Verdict**: ✅ APPROVED

---

## AC Verification

### AC1 — Stacked-target refusal (mechanical, unskippable)

The guard's `check` subcommand now refuses any bare story-branch target (`*-auto`, no slash) with exit 1, emitting:

```
MERGE-GUARD-REFUSE target=PILOT-9-auto reason=stacked-story-branch action=hitl-handoff
```

Verified by direct invocation — independently run, not just test harness:

| Input | Expected | Got |
|---|---|---|
| `PILOT-9-auto` | REFUSE (exit 1) | REFUSE (exit 1) ✓ |
| `origin/PILOT-9-auto` | REFUSE (exit 1) | REFUSE (exit 1) ✓ |
| `refs/heads/PILOT-13-auto` | REFUSE (exit 1) | REFUSE (exit 1) ✓ |
| `epic/PILOT-5-backend-jira-parity` | ALLOW (exit 0) | ALLOW (exit 0) ✓ |
| `epic/PILOT-7-auto-pilot` (slug ends `-auto`) | ALLOW (exit 0) | ALLOW (exit 0) ✓ |
| `main` | REFUSE (exit 1, ABS-531 protected, unchanged) | REFUSE (exit 1) ✓ |

Hook enforcement confirmed at `.claude/hooks/pre-bash-merge-guard.sh:152`:
```bash
if ! guard_out=$(bash "$guard" check "$target" 2>/dev/null); then
    _block "merge-target-guard REFUSED: target '$target' is protected." "$intent"
    exit 2
fi
```
The hook branches on exit code, not on string parsing. A REFUSE causes a PreToolUse exit 2 — the merge tool call never executes. No seat can bypass this path.

**AC1: PASS**

### AC2 — Arrival-not-status: stacked-merged story stays parked

`merge_wait_release` resolves the story's real target via `story_merge_target_branch` (ABS-537: epic child → epic integration branch), then calls `story_git_merge_state` which runs `git merge-base --is-ancestor <story-head> <target>`. A branch merged onto a sibling story branch is not an ancestor of the epic integration branch → state `OPEN` → parked, zero adapter writes.

Verified by conformance test constructing real git repos:
- `PILOT-13-auto` stacked-merged onto sibling `PILOT-9-auto` → `story_git_merge_state` = `OPEN`
- `merge_wait_release PILOT-13 "Ready for Merge"` → exit 1, zero tracker writes

No orchestrator code change for AC2; the arrival mechanism pre-existed (ABS-537). The conformance test pins it rather than rebuilding it.

**AC2: PASS**

### AC3 — Happy path: correct epic target releases cleanly

Same `PILOT-13-auto`, after being merged into `epic/PILOT-5-backend-jira-parity`:
- `story_git_merge_state` = `MERGED`
- `merge_wait_release` → exit 0, emits `INTENT MERGE-WAIT-RELEASE ticket=PILOT-13 role=- to=Docs`, adapter writes `TRANSITION PILOT-13 Docs`

No false park. ABS-537 release path intact.

**AC3: PASS**

### AC4 — Determinism

- Repeat `guard.check(PILOT-9-auto)` → `1-1` (same REFUSE verdict, no double-emit)
- Repeat `merge_wait_release` on a not-arrived story → still exit 1, zero adapter writes on both calls

**AC4: PASS**

### AC5 — Full regression suite green

All suites run independently with a scrubbed env (`env -i`), back-to-back on the same branch:

| Suite | Result |
|---|---|
| `test-stacked-mr-guard.sh` (new) | **21/21 PASS** |
| `test-merge-target-guard.sh` | 15/15 PASS |
| `test-merge-wait-target.sh` | 16/16 PASS |
| `test-merge-wait.sh` | 51/51 PASS |
| `test-done-gate.sh` | 32/32 PASS |
| `test-merge-guard-chokepoint.sh` | 16/16 PASS |
| `test-ready-for-merge-gate.sh` | 40/40 PASS |
| `test-adr-reference-lint.sh` | 6/6 PASS |

**Total: 197 tests, 0 failures.** ABS-531 main-protection chokepoint intact. ADR lint (the only prior `run-all.sh` failure, outside this diff) now passes 6/6.

**AC5: PASS**

---

## Code Quality Notes

- Diff is minimal: 2 files. The guard change adds one `case` block (20 lines) with a clear `*/*` exemption for slashed epic branches and a `*-auto` catch for bare story branches.
- No new module, no hook change — reuses the ABS-513/531 guard seam per the BSA `#PATH_DECISION`.
- Error messages are specific: include the loss scenario reference (`PILOT-21, v3-pilot #3 !163`), the retarget instruction, and machine-readable tokens (`reason=stacked-story-branch action=hitl-handoff`).
- ABS-285 env scrub present in the test file (`unset "${!ORCH_@}"`).

---

## Verdict

**✅ APPROVED — all AC1–AC5 met and independently verified.**

Both defences for the v3-pilot #3 stacked-MR silent-loss class are in place:
1. The guard now refuses stacked story-branch targets at the PreToolUse boundary — no seat can form the stack.
2. The arrival gate already rejects a "merged" MR whose head is absent from the integration branch — a stack that forms despite AC1 never reaches Done.

No regression to ABS-531 main-protection or ABS-537 arrival release path. Transitioning to Story Acceptance.
