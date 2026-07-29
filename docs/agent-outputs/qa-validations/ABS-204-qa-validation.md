# QA Validation — ABS-204

**Ticket**: ABS-204 — Escalation-Resume-to-Origin: legit PO-Deprioritize (→Backlog) vs. Fehl-Dump (ABS-198 M2)
**QAS run**: 2026-07-11
**Branch**: `ABS-204-auto`
**Commits reviewed**: `cf95e96` (ADR-A-0019), `7a73c20` (BE build)
**Verdict**: APPROVED

---

## State Re-verification (Resume Etiquette)

- `git status --short`: clean tree
- `git log --oneline -1`: `7a73c20 feat(orchestrator): escalation resume-to-origin vs. mis-dump signal [ABS-204]`
- Tracker: ABS-204 at `In Test`, updated 2026-07-11T00:04:17Z
- ADR file: `adrs/agentic/ADR-A-0019-po-deprioritize-vs-misdump-signal.md` present, `status: proposed`

---

## Acceptance Criteria

### AC#1 — Design decision documented; new-ADR call explicit

**PASS**

`adrs/agentic/ADR-A-0019-po-deprioritize-vs-misdump-signal.md` (commit `cf95e96`, System Architect):

- **Signal**: an explicit declared target (`verdict: deprioritize` + `target: Backlog`) in the escalation handoff, not the transition path. A target-less resume is a mis-dump by definition.
- **ADR call**: YES — new ADR authored. M2 changes sanctioned routing semantics a shipped guard depends on; the architect explicitly overrode the ABS-198 "no new ADR" annotation.
- **Status**: `proposed` — human accepts per ADR-A-0004 (correct; no agent self-accepts).

### AC#2 — Target-less escalation handoff → resume-to-origin or halt in Blocked, never Backlog (mock tracker)

**PASS**

`escalation_resume_target()` at `scripts/orchestrator.sh` L1783. Wired into `apply_handoff_transition` at L1815 as the third fallback (after declared-target and `handoff_default_target`). Only fires when `to = "Blocked"` (tdm seat). Reads `last_transition_into_blocked_from` for the recorded origin; excludes Backlog / Blocked / Needs PO Decision as resume candidates; prints the origin or `Blocked` (idempotent halt).

Two executed tests confirmed in QAS run (`/tmp/abs204-test-full.txt` lines 355–364):

| Test | Result |
|------|--------|
| tdm at Blocked, no declared target, real origin (In Progress) → resume-to-origin | PASS |
| `Transition: Blocked -> Backlog` count = 0 | PASS |
| tdm at Blocked, no declared target, only escalation-status origin (Needs PO Decision) → halt in Blocked | PASS |
| `RUNNER-TRANSITION to Needs PO Decision` absent (no ping-pong) | PASS |
| `RUNNER-TRANSITION to Backlog` absent (never Backlog by discretion) | PASS |

### AC#3 — Legit `Needs PO Decision → Backlog` PO-park stays functional; guard unchanged

**PASS**

Ordering in `apply_handoff_transition`: `handoff_target_status` (declared target) fires BEFORE `escalation_resume_target`. A declared `target: Backlog` is captured at the first call and `escalation_resume_target` is never reached. `last_po_park_epoch` (L1116) and `stall_raise_suppressed` (L1172) are untouched — confirmed by diff inspection.

Executed regression test (line 365–366, `/tmp/abs204-test-full.txt`):

| Test | Result |
|------|--------|
| Declared deprioritise target honoured (not diverted to Blocked/origin) | PASS |
| Legit PO-deprioritize lands in Backlog | PASS |
| `Needs PO Decision → Backlog` transition `last_po_park_epoch` keys off — intact | PASS |

---

## Test Suite Results (QAS Independent Run)

| Suite | QAS count | Notes |
|-------|-----------|-------|
| `bash tests/test-orchestrator.sh` | 502 PASS / 7 FAIL | 7 pre-existing, orthogonal |
| `bash tests/test-tracker-adapter-lint.sh` | 2/2 PASS | ADR-A-0007 |
| `bash tests/e2e-orchestrator-dryrun.sh` | 38/38 PASS | |

**Pre-existing failures (7)** — confirmed orthogonal to ABS-204 diff:
- 2 × harness-provenance/worktree-path: `startup provenance line reports harness=<stable repo>`, `no seam: provenance harness == script repo` — these assert `harness=<stable repo>` but run from the `tmp/ABS-204-work` worktree copy
- 5 × model-label sizing: `explicit operator-wide cap overrides the qas built-in`, `downsize label on a system-architect review → MODEL-LABEL-SKIP`, `review/judgment seat keeps its role default`, `upsize label logs MODEL-LABEL`, `dry-run: review seat → MODEL-LABEL-SKIP`

None of these 7 test descriptions appear in the ABS-204 diff (confirmed by `git diff f21eb9f HEAD -- tests/test-orchestrator.sh | grep -E ...` returning empty for all 7 patterns).

System Architect (Stage-1) independently confirmed zero regressions via base-vs-HEAD diff: `f21eb9f` → 475P/21F; HEAD → 488P/21F (21 failures byte-identical at both commits). QAS count difference (502 vs 488) reflects environmental delta between review sessions; the zero-regression conclusion holds in both environments.

---

## Scope Verification

**In scope, delivered:**
- ADR-A-0019 (mechanical signal, new-ADR call) — done by System Architect
- `escalation_resume_target()` wired into `apply_handoff_transition` — minimal, additive
- 13 new tests covering AC#2 and AC#3

**Out of scope (correctly absent):**
- Human-Gate-Rest-Whitelist (ABS-197): no changes
- Escalation budget/auto-park-to-Blocked (ABS-199): no changes
- Worktree-State-Isolation: no changes

**No product code modified.** Diff is bash orchestration only (`scripts/orchestrator.sh`, `tests/test-orchestrator.sh`, `adrs/agentic/`). No DB, Prisma, TypeScript, or frontend surface.

---

## Verdict

**APPROVED** — all three ACs satisfied, PO-park guard un-regressed, zero new failures introduced. ADR-A-0019 remains `proposed` pending human acceptance (ADR-A-0004; no agent self-accepts).
