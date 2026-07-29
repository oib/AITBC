# QA Validation Report — ABS-299

**Ticket**: ABS-299 — Two-runner worktree trap: ensure_worktree bases new story branches on origin/main not foreign HEAD  
**Date**: 2026-07-14  
**Actor**: qas  
**Commit under review**: `cb84ec7`  
**Branch**: `ABS-299-auto`  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| AC | Description | Result |
|----|-------------|--------|
| AC1 | With foreign HEAD + NO `epic/<parent>-*` branch, new worktree's merge-base is `origin/main`; foreign commit NOT in history | **PASS** |
| AC2 | When `epic/<parent>-*` branch EXISTS, worktree still bases on it (no regression) | **PASS** |
| AC3 | When `origin/main` does not resolve, provisioning succeeds on HEAD and emits a log line | **PASS** (both C1+C2) |

---

## Test Evidence

**Test file**: `tests/orchestrator.d/ABS-299-worktree-base.sh` (176 lines, ABS-215 pattern)  
**Runner**: `tests/test-orchestrator.sh` (auto-sources `orchestrator.d/*.sh`)

### ABS-299-specific assertions (5/5 PASS)

```
=== Story tests: ABS-299-worktree-base.sh ===

ABS-299 — ensure_worktree bases new story branches on origin/main not foreign HEAD

  Part A — no epic branch, foreign HEAD: new worktree must base on origin/main
    PASS  ABS-299 A1: new worktree branch tip == origin/main SHA (not foreign HEAD)
    PASS  ABS-299 A2: foreign HEAD commit is NOT in the new branch's history

  Part B — epic branch present: worktree still bases on it (regression guard)
    PASS  ABS-299 B1: epic branch present → worktree bases on epic branch tip (no regression)

  Part C — no origin/main: provisioning falls back to HEAD with a log line
    PASS  ABS-299 C1: provisioning succeeds when origin/main absent (HEAD fallback)
    PASS  ABS-299 C2: fallback log line emitted when origin/main does not resolve
```

### Full suite summary (QAS independent run)

```
Total:  761
Passed: 728
Failed: 33  ← all pre-existing (provenance/self-hosting, model-label, follow-up-budget)
```

**Pre-existing failure provenance**: System architect's Stage 1 run (same branch) showed 37 pre-existing failures. My run shows 33 — a net improvement, indicating some prior failures were resolved by other concurrent fixes. Zero failures are attributable to ABS-299.

---

## Code Review Verification

**Diff scope** (`git show --stat cb84ec7`):
- `scripts/orchestrator.sh` — +20 lines (net)
- `tests/orchestrator.d/ABS-299-worktree-base.sh` — +176 lines (new)

**Implementation logic** (lines 4189–4213):
- Resolves `origin/$ORCH_LOCAL_MAIN_BRANCH` via `git rev-parse --verify` (with `2>/dev/null` guard)
- Passes SHA explicitly to `git worktree add -b <ticket>-auto <sha>`
- Falls back to bare `git worktree add -b <ticket>-auto` (HEAD) only when resolve returns empty
- Fallback logs via `log()` (writes stderr + runlog `LOG` event — ABS-66 observable)
- Epic-branch base path (lexicographic pick, lines 4179–4188) is completely untouched

**ADR-A-0010 (minimal change)**: ✅ — only the else-branch was modified; epic selection and HEAD last-resort are explicitly preserved  
**Pattern compliance**: ✅ — reuses `origin/$br` idiom already at `orchestrator.sh:4101`; `ensure_worktree()` remains the single provisioning site; test uses ABS-215 per-story include pattern  
**bash syntax**: ✅ — `bash -n` clean  
**shellcheck**: ✅ — 7 pre-existing errors at lines 4325/4541/4582/4612/4627/4646/5732, all outside the 4189–4213 hunk, all pre-existing (confirmed by system architect's Stage 1 review)

---

## System Architect Stage 1 Findings (ABS-299 ticket, 18:08:11Z)

The system architect independently mutation-verified:
- A1 fails on `cb84ec7^` (unfixed): branch tip = foreign HEAD `742cb5f`, not `origin/main` `783cf32`
- A2 fails on `cb84ec7^`: foreign commit IS in history
- C2 fails on `cb84ec7^`: fallback log line absent
- B1 and C1 pass on both sides (correct — regression guards for unchanged behaviour)
- Zero new failures in the suite (baseline 37 fail vs branch 37 fail, +5 passed/+5 total)

Architect verdict: **APPROVED — In Review → In Test**.

---

## G3 Sequencing Dependency

- ABS-289: **Done** ✅ (dep satisfied)
- ABS-271: **In Test** at time of implementation. Architect confirmed commits `e6fd074`/`fca602c` touch lines 1671–1798 and 3441–3574 — no region overlap with `ensure_worktree()` at 4146–4215. **Rebase at PR time expected to be clean.**

---

## QAS Verdict

**APPROVED**. All 3 ACs met, all 5 test assertions pass (independently run). Pre-existing failures unchanged, no regressions. Mutation test confirmed tests pin the defect. Implementation is minimal, pattern-compliant, and ADR-A-0010-conformant.

**Next**: Transition to `Story Acceptance`. No `design` flag on ticket; SKIP-FORWARD past Design Test applies.
