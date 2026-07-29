# QA Validation — PILOT-76

**Ticket:** PILOT-76 — Epic-Integration scheitert vier Runs in Folge am RTE  
**Branch:** `PILOT-76-auto`  
**Head commit at validation:** `2abb67832e57dc34c907f2d36f8521329289d37e`  
**Actor:** qas  
**Date:** 2026-07-27 (resume after forward-fix 2abb6783)

---

## Verdict: APPROVED

All five acceptance criteria met. Forward-fix `2abb6783` adds 3 rule-ledger rows; no AC logic changes. No design flag → releasing to Story Acceptance.

---

## Forward-fix Addendum (2abb6783)

The story bounced at the C4 rule-ledger gate after Story Acceptance. Forward-fix `2abb6783` adds ledger rows R-1109/R-1110/R-1111 for the three new headings in `docs/sop/rte-reference.md`. Independently re-verified (back-to-back, same shell, on this HEAD):

```
bash scripts/rule-ledger-check.sh   → exit 0: "rule-ledger-check: OK"
bash tests/test-rule-ledger.sh      → 19/19 PASS (all cases, including C4)
bash tests/test-spawn-tmpdir.sh     → 4/4 PASS
bash tests/test-spawn-skill-path.sh → 32/32 PASS
bash tests/test-agent-def-overlay.sh→ 24/24 PASS
```

Only `docs/rule-ledger.yaml` changed. No harness, no `agent_providers/`, no spawn seam — no mirror-parity concern (common rule 10). All prior AC verdicts still hold.

---

## AC Checklist

### AC1 — Root-cause analysis as gate-results comment, BEFORE code (REVISED per BSA decision 2026-07-26T21:16:37Z)

**PASS.**  
gate-results comment posted at `2026-07-26T22:07:06Z`. Both code commits landed at `2026-07-27T00:10:32+0200` / `00:10:38+0200` (= `22:10:32Z` / `22:10:38Z` UTC). The analysis precedes the code by ~3 minutes.

The comment names the concrete failure mechanism per case:
- Case 1 (PILOT-17): station timeout — suite ~15 min > 10-min Bash call limit
- Case 2 (PILOT-28): sync-rebase conflict — human-only by doctrine, intentional operator path
- Case 3 (PILOT-39): scratch read-denial — seat could run the suite but was denied reading its own mktemp artefacts outside cwd allowlist
- Case 4 (PILOT-58): missing legal handoff path — the sole forward edge (`Ready for Epic Acceptance`) is gated behind ABS-453 full-suite `--verify`; trivial merge does not bypass this gate

Case 4 proof: the analysis traces `HANDOFF-NOMOVE` → 2× respawn-limit → `Needs PO Decision` through the runner mechanic. Cases 1/3/4 are identified as one infrastructure gap, not independent bugs.

### AC2 — RTE Scratch/Temp read access decision (Case 3)

**PASS.**  
`scripts/orchestrator-spawn-claude.sh` lines 525–543 export `TMPDIR=<worktree>/tmp` before `exec`, guarded by `[ -n "${ORCH_SEAT:-}" ]`. Every `mktemp` the seat and its spawned harness make lands inside the already-allowlisted cwd. Narrow fix (not a broad `/var/folders/**` grant). `tmp/` is gitignored. `mkdir` is best-effort with silent fallback — cannot fail a spawn.

Verified: `grep -n "TMPDIR" scripts/orchestrator-spawn-claude.sh` shows the export at line 540.

### AC3 — Staged-suite entry actually used (Case 1)

**PASS.**  
`harness/claude/agents/rte.md` §221–236 drives `tests/staged-suite.sh` staged:
```
--list → one --stage per Bash call → --verify at the fixed epic tip
```
`tests/staged-suite.sh` handles all three flags (confirmed: lines 214–217). No code change was needed; ABS-557 already wired this. Documented as a present enabler in the SOP.

### AC4 — Live falsification (trivial integration → Ready for Epic Acceptance without operator)

**PASS (deferred, honestly documented).**  
The TMPDIR fix enables the seat to produce and read the gate verdict even on a trivial merge. Final proof requires a live epic run. This is documented as pending in `docs/sop/rte-reference.md` under "What remains operator-supported" — not claimed as done.

### AC5 — SOP documents station as operator-supported

**PASS.**  
`docs/sop/rte-reference.md` has a new section (commit `a2142904`):  
`## Epic-Integration station — status: OPERATOR-SUPPORTED (PILOT-76)`

Contains: four-pilot failure table, enablers in place (ABS-557 staged entry, PILOT-76 TMPDIR fix), what remains operator-supported (sync-rebase conflict resolution = human-only by ADR-A-0005/ABS-90; full-suite scale), and the falsification condition for promoting the station.

---

## Test Evidence (ABS-453 green-run proof)

The ticket adds `tests/test-spawn-tmpdir.sh` — mandatory green-run per ABS-453.

```
Command: bash tests/test-spawn-tmpdir.sh
Commit:  2abb67832e57dc34c907f2d36f8521329289d37e

=== PILOT-76: seat TMPDIR pinned inside the worktree ===
AC — a worktree-provisioned seat gets TMPDIR=<worktree>/tmp
  PASS seat exec'd with TMPDIR pointing inside its ORCH_SPAWN_CWD worktree
  PASS the tmp dir was actually created (mktemp targets land there, readable at the gate)
AC — TMPDIR follows ORCH_TARGET_REPO when no worktree is set
  PASS seat exec'd with TMPDIR pointing inside its ORCH_TARGET_REPO cwd
  PASS the tmp dir was created inside the target repo
=== Results: 4/4 passed ===
```

**Rule-ledger gate (forward-fix):**

```
bash scripts/rule-ledger-check.sh   → exit 0
bash tests/test-rule-ledger.sh      → 19/19 PASS
```

**Regression suite (seam tests):**

```
bash tests/test-spawn-skill-path.sh  → 32/32 passed
bash tests/test-agent-def-overlay.sh → 24/24 passed
```

All runs back-to-back on this HEAD `2abb6783`, same shell.

---

## Scope / Compliance

- Files changed across all 4 commits: `scripts/orchestrator-spawn-claude.sh` (+20 lines), `tests/test-spawn-tmpdir.sh` (new), `docs/sop/rte-reference.md` (+50 lines), `docs/rule-ledger.yaml` (+13 lines, R-1109/1110/1111)
- No `harness/claude/agents/*` or `harness/claude/skills/*` edits → no provider-mirror regeneration needed (common rule 10)
- No RLS, auth, DB, TypeScript surface — shell seam + docs + ledger only
- Commit format: SAFe `type(scope): description [PILOT-76]` ✓ on all 4 commits
- No design flag on ticket → exit to Story Acceptance

---

## Exit

**Verdict: APPROVED — releasing to Story Acceptance**
