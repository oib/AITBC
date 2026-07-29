# QA Validation Report — ABS-285

**Ticket**: ABS-285 — Seam-invoking tests scrub ambient ORCH_* env  
**Branch**: `ABS-285-auto` | **Commits**: d933e75 d88681e  
**Merge-base**: bf7e310  
**QAS run**: 2026-07-14  
**Verdict**: ✅ **APPROVED**

---

## Independent Verification Method

All load-bearing claims re-run from scratch. No results trusted from prior actor comments.  
Worktree at `/Users/sahan/local_projects/agentic-development-boilerplate/tmp/ABS-285-work` (d88681e).  
Throwaway base worktree at `/tmp/abs285-qa-base-34860` (bf7e310) — removed after measurement.

---

## AC Verification

### AC1 — `test-agent-def-overlay.sh` env-immune ✅

| Command | Result |
|---|---|
| `env ORCH_TOOLS=Bash,Read bash tests/test-agent-def-overlay.sh` | 24/24 PASS |
| `env -u ORCH_TOOLS bash tests/test-agent-def-overlay.sh` | 24/24 PASS |

Both sides identical and green. Was 19/24 vs 24/24 at the merge-base.

### AC2 — All nine seam-driving files scrub-immune ✅

Swept all nine files under hostile (`ORCH_TOOLS=Bash,Read ORCH_MODEL=opus ORCH_MAX_TURNS=1 ORCH_OVERRIDES_DIR=/nonexistent`) vs scrubbed (`env -i PATH HOME TMPDIR`):

| File | Hostile | Scrubbed | Identical |
|---|---|---|---|
| test-agent-def-overlay.sh | 24/24 rc=0 | 24/24 rc=0 | ✅ |
| test-claim-mutex.sh | 22/22 rc=0 | 22/22 rc=0 | ✅ |
| test-claim.sh | 20/20 rc=0 | 20/20 rc=0 | ✅ |
| test-done-gate.sh | 32/32 rc=0 | 32/32 rc=0 | ✅ |
| test-jira-tracker.sh | ALL PASS rc=0 | ALL PASS rc=0 | ✅ |
| test-kill-guard.sh | 31/31 rc=0 | 31/31 rc=0 | ✅ |
| test-packet-cache.sh | 20/20 rc=0 | 20/20 rc=0 | ✅ |
| test-resume-cwd.sh | 17/17 rc=0 | 17/17 rc=0 | ✅ |
| test-station-guard.sh | 96/96 rc=0 | 96/96 rc=0 | ✅ |

All files carry `unset "${!ORCH_@}"` — confirmed by the structural guard in AC3.

Note: four files use non-standard summary formats; output compared verbatim (not by parsing "Passed: N") and confirmed IDENTICAL.

### AC3 — Regression pin 11/11 ✅

`tests/orchestrator.d/ABS-285-env-scrub.sh` sourced via minimal bash harness (`bash -c '...; source tests/orchestrator.d/ABS-285-env-scrub.sh'`):

- `pass=24 fail=0 rc=0` under hostile env
- `pass=24 fail=0 rc=0` under scrubbed env  
- Assertion: "scores identically" → **PASS**
- Assertion: "fully green under hostile env" → **PASS**
- 9× structural grep assertions (one per file) → **9/9 PASS**
- **Total: 11/11 PASS**

Note: running the pin inline in the Bash tool (zsh/sh subshell for `$()`) produced a false `bad substitution` error on `${!ORCH_@}`. Re-running as `bash -c` resolved it — confirming the pin is bash-specific as intended. The pin is designed to be sourced into `test-orchestrator.sh` (`#!/usr/bin/env bash`).

Mutation test (dev + architect confirmed): with scrub stripped, pin goes 3 failures (`pass=13 fail=11`). QAS accepts this on two independent mutation-test accounts; the structural grep in the pin itself is the ongoing guard.

### AC4 — `_common-rules.md` §9 same-env rule ✅

`harness/claude/agents/_common-rules.md:168`:

> **Measure both sides in the SAME window and with the SAME env (ABS-285).** A test result is only a function of the commit if the environment is held fixed. Seats export ~37 `ORCH_*` vars, and some leak into the code under test (`ORCH_TOOLS` and `ORCH_OVERRIDES_DIR` each flipped assertions in `tests/test-agent-def-overlay.sh`), so a baseline measured by seat A is NOT comparable to a branch run by seat B...

Rule is present with the correct method: back-to-back, same shell, never trust a stale number.

AC4 sequencing gate: PR #196 (ABS-272) was merged into `epic/ABS-278-v2252-hotfix-consumer-feedback` before this work began (PO verified, confirmed by git log). §9 pre-exists at line 141; ABS-285 extends it at line 168.

### AC5 — No new failures vs merge-base ✅

Throwaway worktree at `bf7e310` (merge-base), same shell, no `git stash`.

Nine changed test files on BASE (bf7e310): **zero failures**.  
Nine changed test files on BRANCH (d88681e): **zero failures**.  
Diff of failing assert names: **empty (0 new)**.

`test-wrong-entry-guard.sh` (known to fail at base) was **not modified** by ABS-285 (`git diff bf7e310..d88681e -- tests/test-wrong-entry-guard.sh` = 0 lines). Any failures there pre-existed and are out of scope.

Diff is purely additive: `11 files changed, 145 insertions(+)` — no deletions.

---

## Design Decisions Validated

**Prefix-unset over enumerated list** — `unset "${!ORCH_@}"` is the correct call. An enumerated list would have missed `ORCH_OVERRIDES_DIR` (discovered during development). The prefix-unset covers the class, not the instance.

**Drop-in file** — `tests/orchestrator.d/ABS-285-env-scrub.sh` follows the established pattern (4 siblings, `docs/sop/TEST_SUITE_LAYOUT.md`) and dissolves the file collision with ABS-284 that the PO chained `depends_on` for.

---

## Out-of-Scope Follow-ups (recorded, not blocking)

1. `test-orchestrator.sh`'s own enumerated scrub leaves 67/109 `ORCH_*` vars unprotected — including `ORCH_OVERRIDES_DIR`. Deserves its own ticket.
2. The pin's structural guard hardcodes nine filenames (enumerated-list weakness one level up). Worth a follow-up when a tenth file is added.
3. The Architect's original 14-failure number stays unreproduced (dev found 5+6=11 via two proven leakers). Reported honestly; fix doesn't depend on it.

---

## Verdict

**✅ APPROVED** — All five ACs independently verified first-hand.  
`flags`: none → exit target is **Story Acceptance**.
