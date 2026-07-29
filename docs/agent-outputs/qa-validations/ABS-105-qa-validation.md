# QA Validation — ABS-105 — Path-A parentless-ticket solo pipeline

- **Ticket**: ABS-105 (parent ABS-102, role be-developer)
- **Gate**: QAS In Test validation
- **Branch / commit**: `ABS-105-parentless-solo-pipeline` @ `f1e58f8`
- **Diff scope (verified)**: purely additive — `docs/sop/ORCHESTRATOR_SOP.md` (+29) and
  `tests/test-path-a-solo-pipeline.sh` (new, 28 assertions). `git diff --name-only d155a86 f1e58f8`
  confirms **zero `scripts/` changes** (`orchestrator.sh` and `test-orchestrator.sh` byte-identical to parent).
- **Verdict**: APPROVED

## Acceptance Criteria — independently re-run against the real orchestrator

| AC | Requirement | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Plain parentless bug spawns solo seats (triage/DoR head, implement, code review, in test, story acceptance) and SKIP-FORWARDs Design/Security Review/Test Prep/Design Test with audit comments and zero spawns each | PASS | Path-A suite lines 148-171 green; SKIP-FORWARD intents + `assert_not_contains` on each conditional seat |
| AC2 | No epic-level status ever entered (PO Triage, Grooming, Enrichment, Ticket Review, Architecture Review, Epic Integration) | PASS | transition-log assertions (lines 174-181) all green; no bsa / issue-enrichment spawn |
| AC3 | JOIN rule never evaluates for a parentless ticket | PASS | no JOIN intent (line 184); code-confirmed parent-gating at orchestrator.sh:1683 (epic-type gate) and :1797 (done_parent non-empty gate) |
| AC4 | Security-flagged parentless ticket DOES spawn Security Review, flags honored | PASS | lines 203-206 green: security-engineer spawns at Security Review, no SKIP-FORWARD |
| AC5 | Triage+DoR head runs the Story-1 seat, yields ready/rework/needs-decision on the single ticket | PASS | SPAWN po-agent to=Backlog (single-ticket mode); ready routes Backlog->Design; code map_action(Backlog)=SPAWN po-agent at orchestrator.sh:313 |

## Validation suites (re-run on QAS box)

| Suite | Result |
|-------|--------|
| tests/test-path-a-solo-pipeline.sh | 28/28 PASS |
| tests/test-intake-classification.sh | 21/21 PASS |
| tests/e2e-workflow-v3.sh | 83 PASS / 1 SKIP (ADR-A-0014 pending) / 0 FAIL |
| tests/test-orchestrator.sh | 241 total / 6 FAIL — ALL pre-existing + environmental (see below) |

## test-orchestrator.sh — 6 failures triaged, none caused by ABS-105

BE/architect reported this suite as "239 PASS / 2 FAIL". Actual state is 241 / 6 FAIL. I triaged all six:

- 2x harness-provenance failures (`harness=<stable repo>` vs worktree) — the self-hosting governance
  seam per CLAUDE.md ABS-92; environmental.
- 4x iteration-cap `DEMO-1` failures (BLOCK-ITERATION-CAP intent / no-qas-spawn / ->Blocked / gate-results comment).

**Proof they are not regressions**: I ran `tests/test-orchestrator.sh` at the **parent commit `d155a86`
(main, before ABS-105 existed)** in a throwaway worktree — the **identical 6 failures** appear, and the
provenance failure there reports the parent worktree's own path. Combined with the byte-identical
`scripts/` (ABS-105 touches only a SOP doc + one new test file), all six failures are conclusively
pre-existing on main and environmental — **outside ABS-105's diff surface**. Classification:
`environment` (not `code`); not routable to the implementer, and not a blocker for this ticket.

Minor note (non-blocking): the BE/architect evidence under-counted this suite (2 vs actual 6). It does
not change the verdict because the failures are proven pre-existing and unrelated.

## ADR / pattern compliance

- ADR-A-0010 minimal-change: honored — solo pipeline is the v3.0 story seat map + SKIP-FORWARD reused
  as-is; no forked pipeline (diff adds no `scripts/` logic).
- ADR-A-0014 carve-out: consistent — story stops at Story Acceptance; epic-less merge seam deferred to Story 4.
- Reuse-existing-role: honored — po-agent Backlog seat in single-ticket mode; no new role.

## Exit

All 5 ACs PASS. All ABS-105-owned suites green. No regressions attributable to this diff.
Transition: In Test -> Design Test (runner SKIP-FORWARDs to Story Acceptance, no design flag).
