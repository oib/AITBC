# QA Validation: PILOT-81 — Harness-release preflight guard

- **Ticket**: PILOT-81
- **Branch**: PILOT-81-auto
- **Commit**: 79056b00 (`feat(orchestrator): refuse a live start on a non-release harness checkout [PILOT-81]`)
- **Validator**: qas
- **Date**: 2026-07-27
- **Re-validation**: after architect rebase onto epic tip 51e7a2db (2026-07-27T02:10Z)
- **Verdict**: ✅ APPROVED

---

## Test run — 10/10 PASS

Command:
```
SUITE_INCLUDE_ONLY=PILOT-81-harness-release-guard.sh bash tests/test-orchestrator.sh
```

Run against commit: 79056b00 (HEAD of PILOT-81-auto post-rebase)

```
=== Story include (isolated, PILOT-50): PILOT-81-harness-release-guard.sh ===

=== PILOT-81 harness-release preflight guard ===

  PASS  PILOT-81 AC5: story-branch harness => start refused (exit 1)
  PASS  PILOT-81 AC1: refusal names the exact-tag failure
  PASS  PILOT-81 AC6: HARNESS-VERSION stamped to run.log even on refusal
  PASS  PILOT-81 AC5: dirty harness on tag => start refused (exit 1)
  PASS  PILOT-81 AC2: refusal names the dirty tree
  PASS  PILOT-81 AC5: clean harness on tag => start allowed (exit 0)
  PASS  PILOT-81 AC5: allowed start logs OK
  PASS  PILOT-81 AC6: HARNESS-VERSION line written to run.log
  PASS  PILOT-81 AC6: run.log records the resolved release tag
  PASS  PILOT-81 kill switch: ORCH_HARNESS_RELEASE_GUARD=0 => legacy start allowed

  Total: 10  Passed: 10  Failed: 0
EXIT: 0
```

Commit reachability:
```
git cat-file -e 79056b00^{commit}  → exists
git for-each-ref --contains 79056b00 → refs/remotes/gitlab/PILOT-81-auto (via descendant 4052b0cd)
```

---

## AC-by-AC verdict

### AC1 — `--exact-match` only; prefix match documented as insufficient ✅

`check_harness_release()` (`scripts/orchestrator.sh:7347`) calls:
```bash
tag="$(git -C "$h" describe --exact-match --tags HEAD 2>/dev/null || true)"
```
An empty `$tag` triggers `die` with a message explicitly naming the prefix-match failure:
```
"A prefix match (git describe --tags -> 'vX-N-g...') is INSUFFICIENT and is exactly what let unpublished code run on 2026-07-26."
```
The comment block in the code documents why `--exact-match` is mandatory. SOP section "Harness-release preflight (PILOT-81)" repeats this for operators.

Test coverage: assertion "PILOT-81 AC1: refusal names the exact-tag failure" **PASS**.

### AC2 — Dirty-tree refusal ✅

`git status --porcelain` output captured into `$dirty`. Any non-empty value triggers `die` naming "working tree is DIRTY". Covers both uncommitted and untracked changes.

Test coverage: assertion "PILOT-81 AC2: refusal names the dirty tree" **PASS**.

### AC3 — Guard in runner, not launcher ✅

`check_harness_release` is defined and called only in `scripts/orchestrator.sh` (verified: `grep -n check_harness_release scripts/orchestrator.sh` returns only `scripts/orchestrator.sh`). Called in `main()` at line 10904, after `init_run_id`. No launcher script contains the function.

### AC4 — Belegter Weg identified and closed ✅

SOP section "Which seat parked the checkout, and how it is closed (AC4)" documents:
- Identified seat type: single-repo self-hosting implementers whose work target is the main checkout.
- Evidence: two commits in the stable checkout reflog on two different days (PILOT-64, PILOT-50).
- Three-layer closure: ABS-224 pre-commit guard (blocks `git commit` on main), PILOT-66 post-checkout guard (warns when main HEAD moves to a work branch), PILOT-81 run-start refusal (turns a silently parked state into a loud gate the operator must clear).

### AC5 — Three regression scenarios: all pass ✅

`tests/orchestrator.d/PILOT-81-harness-release-guard.sh` exercises all three required cases against purpose-built temporary git repositories:

| Scenario | Expected | Actual |
|---|---|---|
| Harness on story branch (past tag) | exit 1, names exact-tag failure | PASS |
| Harness on tag, dirty tree | exit 1, names dirty tree | PASS |
| Harness on tag, clean tree | exit 0, logs "harness-release guard: OK" | PASS |

Kill switch also covered: `ORCH_HARNESS_RELEASE_GUARD=0` allows a story-branch harness start (legacy behavior preserved).

Note: `tests/sandbox-guard.sh` exports `ORCH_HARNESS_RELEASE_GUARD=0` for the broader suite (dev checkout is not on a release tag by definition), while PILOT-81's test file sets it back to `1` against isolated temp repos. This design is correct and keeps the rest of the suite unaffected.

### AC6 — HARNESS-VERSION in run.log, pass and fail ✅

`runlog HARNESS-VERSION - - - "tag=${tag:-none} sha=${sha} dirty=..."` executes before any `die` or `return` in `check_harness_release()`, so the line lands in `run.log` regardless of outcome.

Tests confirm:
- "PILOT-81 AC6: HARNESS-VERSION stamped to run.log even on refusal" **PASS**
- "PILOT-81 AC6: HARNESS-VERSION line written to run.log" **PASS**
- "PILOT-81 AC6: run.log records the resolved release tag" **PASS** (checks for `tag=v9.9.9`)

---

## Additional checks

- `--dry-run` bypass: `[ "$MODE" = "live" ] || return 0` on line 7334; dry-run mode sets `MODE="dry-run"`, so the guard is never reached.
- `ORCH_HARNESS_HOME` defaults to `$REPO_ROOT` (line 332) — the harness checkout root — and is exported; the guard operates on the correct path.
- No `harness/claude/**` edits in this commit → no provider-mirror regen required.
- Post-rebase: architect verified zero conflict markers, both PILOT-79 and PILOT-81 guards survive, `bash -n` clean (2026-07-27T02:10Z handoff). Re-run confirms tests still green.

---

## Verdict

All six acceptance criteria are met. Implementation confined to `scripts/orchestrator.sh` and the SOP; no product data surface or auth layer touched. Tests isolated (purpose-built temp git repos). Sandbox guard correctly scopes the guard off for the broader suite.

**APPROVED — transitioning to Story Acceptance.**
