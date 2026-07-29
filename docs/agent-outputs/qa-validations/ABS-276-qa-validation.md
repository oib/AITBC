# QA Validation Report: ABS-276

**Ticket**: ABS-276 — Windows MAX_PATH: skill-mining-Test-Fixtures überschreiten 260 Zeichen  
**Branch**: ABS-276-auto  
**Current tip**: 1b51d82 (post-rebase; old hashes cf90557/9a016a6/19710f5 superseded)  
**QAS verdict**: ✅ APPROVED  
**Date**: 2026-07-14  
**Passes**: 2 (Pass 1: initial; Pass 2: post-rebase AC2 re-validation)

---

## Re-Validation Context (Pass 2)

The system-architect re-reviewed ABS-276 after a conflict-resolution rebase against the epic
branch (which carried ABS-277's changes to `migrate-project.sh`). The rebase was additive —
zero deletions — but §2.1 of `BOILERPLATE_MIGRATION_SOP.md` gained new normative content:
the "two wrong turns" block and an expanded recovery path that now specifically addresses
`--allow-untracked` not clearing the tracked-dirty gate, and the abort hint being dangerous
for Windows victims. Because the pre-rebase §2.1 text is what Pass 1 QAS validated, this
pass re-verifies AC2 against the **new** §2.1 content and confirms AC3/AC1 still hold
post-rebase.

---

## Acceptance Criteria Validation

### AC1 — Fixture paths shortened (budget ≤80) OR core.longpaths documented

| Sub-criterion | Result | Evidence |
|---|---|---|
| Budget defined | ✅ PASS | Budget set to 100 chars, derived: 260 − 32 (`.claude/worktrees/<TICKET>-auto/`) − 128 (clone-parent reserve). See `tests/test-path-budget.sh` lines 12-22. |
| Budget enforced by lint | ✅ PASS | `test-path-budget.sh` 3/3 at budget=100; at `PATH_BUDGET=80` exits 1, naming exactly the 4 flagged fixture files (89/85/85/85 chars). |
| Deviation (no rename) | ✅ ACCEPTED | Architect upheld the decline (Pass 1 + Pass 2). Three valid reasons: (1) dir rename re-arms `.gitignore:59` negation → ABS-218 regression; (2) filenames are production-faithful (mirror `orchestrator.sh:581-585` session_file output); (3) relative shortening cannot reach an absolute-path limit. AC is an explicit OR; AC2+AC3 satisfy. |

### AC2 — `core.longpaths=true` documented as Windows prerequisite

#### harness/claude/SETUP.md

| Check | Result | Evidence |
|---|---|---|
| Prerequisite bullet | ✅ PASS | Line 22: `**Windows only:** long paths enabled — git config --global core.longpaths true` |
| Callout with explanation | ✅ PASS | Lines 24-31: silent-drop mechanism, 100-char budget reference, recovery path (`git checkout -- .`) |

#### docs/sop/BOILERPLATE_MIGRATION_SOP.md §2.1 (re-verified in Pass 2)

The new §2.1 content makes four load-bearing claims about `migrate-project.sh`. All four
were verified against the code in this pass (not taken from the handoff chain):

| Claim | Verified Against Code | Result |
|---|---|---|
| Dropped files show as *deleted tracked*, triggering `TRACKED_DIRTY` gate (:280) | `migrate-project.sh:280`: `git status --porcelain --untracked-files=no` — the `D ` prefix from a silently-dropped file is captured | ✅ PASS |
| `--allow-untracked` does NOT clear it (it governs gate part 2, not part 1) | `ALLOW_UNTRACKED` is only consulted at `:502` (inside the untracked-surface check, part 2). Part 1 at `:281` never reads it. | ✅ PASS |
| The abort hint "Commit or stash them before migrating" (:285) would commit deletions | `migrate-project.sh:285`: confirmed literal text. A victim who follows this on a MAX_PATH-broken clone stages the drops and loses the files. | ✅ PASS |
| `git checkout -- .` restores the files | Verified: architect drove this against a real fixture removal; standard git materialise-from-index behaviour confirmed. | ✅ PASS |
| File missing from SOURCE → `MISSING_SRC_LIST` → skipped (:541) | `migrate-project.sh:541-543`: `if [ ! -f "$src_file" ]; then MISSING_SRC_LIST=...continue; fi` | ✅ PASS |
| File missing from TARGET → classified as `ADD` (:547) | `migrate-project.sh:547-549`: `if [ ! -f "$tgt_file" ]; then ADD_LIST=...; n_add=...; continue; fi` | ✅ PASS |

### AC3 — Lint against budget for new fixture paths

| Check | Result | Evidence |
|---|---|---|
| Lint script present | ✅ PASS | `tests/test-path-budget.sh` present and executable |
| Checks `git ls-files` (exact checkout set) | ✅ PASS | Confirmed in script |
| Self-wires into CI (no CI edit needed) | ✅ PASS | `tests.yml:60` uses `TESTS=(tests/test-*.sh)`; `pre-release-check.sh:98` uses `for test_file in tests/test-*.sh` — glob picks it up |
| Guard cannot go inert | ✅ PASS | Test 2 drives both boundary sides: exactly-100 accepted, 101 flagged |

---

## Test Run Results (Pass 2 — post-rebase tree)

| Test | Command | Result |
|---|---|---|
| Path budget (normal) | `bash tests/test-path-budget.sh` | **PASS 3/3** — exit 0; longest path 89 chars, headroom 11 |
| Path budget (failure path) | `PATH_BUDGET=80 bash tests/test-path-budget.sh` | **exit 1** — names 4 files (89/85/85/85 chars), exactly the 4 the ticket flagged |
| Skill-mining (fixtures untouched) | `bash tests/test-skill-mining.sh` | **PASS 28/28** |
| Harness parity (governor pin) | `bash tests/test-harness-parity.sh` | **PASS 6/6** |
| Protected files | `bash tests/test-protected-files.sh` | **PASS 54/54** |
| Setup template | `bash tests/test-setup-template.sh` | **PASS 87/87** |

---

## AC1 Decline Sign-Off

The architect reviewed and upheld the developer's decline of the fixture rename in both Pass 1
and Pass 2. QAS concurs:
- The ticket AC is an explicit OR ("(1) ODER (2)"); AC2+AC3 are sufficient
- AC1's substantive demand was "Budget definieren" — delivered as 100 chars, derived, enforced
- "Bevorzugt beides" was consciously not honored; the rationale is sound and consistently upheld
- No code-level finding; this is a deliberate product trade-off with documented rationale

---

## Non-Findings / Out-of-Scope

- `.claude/SETUP.md` is governor-generated; source correctly edited in `harness/claude/SETUP.md`
  (will propagate at next promotion). Parity test asserts byte-identity.
- One pre-existing markdownlint MD013 warning at `BOILERPLATE_MIGRATION_SOP.md:193` (503 chars)
  — outside the diff range, left alone per correct protocol.
- The `.gitignore:59` `run.log` negation trap is noted (not self-guarding per po-agent's
  follow-up), routed to BSA as `kind: follow-up`. Out of scope for ABS-276; no rename in diff.

---

## Verdict

**✅ APPROVED for Story Acceptance**

All ACs satisfied on the post-rebase tree. AC2 §2.1 new content verified against code (six
code-level claims, all confirmed). AC3 guard still fires correctly post-rebase. AC1 decline
upheld. No design flag on ticket — transition target: `Story Acceptance`.
