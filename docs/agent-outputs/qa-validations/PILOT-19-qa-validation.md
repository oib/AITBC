# QA Validation: PILOT-19
## Depends-Release on Merge-Fact (not label)

**Verdict: APPROVED**
**Branch:** PILOT-19-auto  
**Commit:** a09bc022  
**Tested:** 2026-07-24  
**Run:** `tests/test-orchestrator.sh` with ORCH env scrubbed (ABS-285)  
**Result:** 1291 passed / 0 failed  

---

## AC1 — Dependent dispatches when blocker's head is merged; no operator action needed

**PASS**

Test: `PILOT-19 AC1: dep head merged -> dependent spawns; worktree bases on the epic branch (merged file visible)` (`tests/test-orchestrator.sh:4173`)

The test drives the blocker to Merging (head unmerged), confirms the dependent waits, then executes a real git merge onto the epic integration branch and pushes. The next reconcile dispatches the dependent and its provisioned worktree contains the dep-file.txt that was only on the epic branch — proving the merge fact triggered release AND that the worktree bases on the updated branch tip.

---

## AC2 — Ancestor-check is the sole release criterion; Docs without merge keeps gate closed

**PASS**

Tests (both must hold):
- `PILOT-19 AC2: dep head not yet an ancestor of the epic branch -> dependent waits` (line 4156)
- `PILOT-19 AC2: dep in 'Docs' with an UNMERGED head keeps the gate closed` (line 4162)

Code inspection (`scripts/orchestrator.sh:7680-7700`): `depends_unmet()` contains no status-string match. The old ABS-119 case block (`"Docs"|"Done") continue`) is removed. Release path:

```bash
ms="$(story_merge_state "$dep" 2>/dev/null)"
[ "${ms%%$'\t'*}" = "MERGED" ] && continue
```

`Done` is the only terminal string check; `story_merge_state` (git merge-base --is-ancestor) is the merge criterion. A dep sitting in `Docs` with an unmerged head returns OPEN/NONE from the probe and the gate stays closed.

---

## AC3 — `depends-strict` label forces Done-only release; documented

**PASS**

Tests:
- `PILOT-19 AC3: 'depends-strict' dependent ignores the merge fact and waits for Done` (line 4251)
- `PILOT-19 AC3: 'depends-strict' releases once the dep is Done` (line 4254)

Test setup merges the blocker's head into the epic branch BEFORE driving the dependent — a normal dependent would release. The `depends-strict` label on the dependent blocks that release; only the subsequent `Done` transition triggers dispatch.

SOP documentation: `docs/sop/ORCHESTRATOR_SOP.md:633-636` — the `depends-strict` exception is described, with scope limited to one label, no new semantics, default remains merge-fact release.

---

## AC4 — Epic-completion (JOIN) gate unchanged

**PASS**

Tests:
- `PILOT-19 AC4: a child in Docs (not Done) does NOT complete the epic` (line 4273)
- `PILOT-19 AC4: epic still rests in Stories In Flight while a child is in Docs` (line 4275)

`join_check_epic()` (`orchestrator.sh:5480+`) checks `[ "$status" = "[Done]" ] && continue` — no merge-fact probe. A child resting in Docs with a merged head does not count as Done for JOIN purposes. The epic stays at `Stories In Flight`. The `depends_unmet` and `join_check_epic` functions are intentionally separate: one governs dispatch (blocker artifact), the other governs pipeline completion (all work finished).

---

## Test Suite Summary

Command:
```bash
bash -c '
unset ORCH_AGENTS_ARG_MAX ORCH_AGENT_TIMEOUT ... [all 37 ORCH_* vars]
bash tests/test-orchestrator.sh 2>&1
'
```

Output (tail):
```
Total:  1291
Passed: 1291
Failed: 0

ALL TESTS PASSED
```

Commit: a09bc022 (`git rev-parse HEAD`)

---

## Scope checks

- No `design` flag in ticket labels (`labels: [orchestrator-ready]`) → exit to Story Acceptance.
- No harness/skills files touched → mirror parity check N/A (ABS-317 not applicable).
- No RLS/security surface (shell orchestrator).
- `blocked_auto_release_sweep` updated to use `depends_unmet` (which now carries merge-fact semantics) — Watcher/sweep path also covered by the existing `depends_unmet` call path.
