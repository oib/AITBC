# QA Validation — Workflow v2 Spec Simulation (DRAFT, pre-implementation)

**Spec**: [specs/ABS-69-workflow-v3-full-agent-team-spec.md](../../../specs/ABS-69-workflow-v3-full-agent-team-spec.md) (formerly `DRAFT-workflow-v2-full-agent-team-spec.md`, renamed/superseded)
**Test**: `python3 tests/workflow-v2-sim.py` · **Date**: 2026-07-05 (round 3) · **Runner**: local (POPM session)

Validates the PROPOSED v2 state machine logic (spec §1–§3) against the §5 scenario suite
S1–S16, plus mutation checks proving the suite detects the absence of each scenario-derived
guard. Round 2 added S9–S15; designing them exposed four NEW defects, now fixed in the spec:
empty-epic vacuous JOIN (§3.6), JOIN/follow-up race (§3.6 quiescence), epic-level Blocked
unhandled (§3.7), and unbounded crash-retry (§3.8). Round 3 added the **Ticket Review /
Definition-of-Ready gate** (§3.10) with S16: un-ready tickets bounce to `Grooming` before any
story is released; the epic ticket's rework counter (§3.2) caps the loop. This is a spec-level
simulation — the bash E2E dry-run against the real orchestrator is an implementation-phase
gate, not covered here.

## Output

```
— scenario suite (all guards active) —
  PASS  S1: Happy path: 3 stories, one design-flagged; exactly one NOTIFY.
  PASS  S2: Design flaw loop: qas-design always demands design fix -> rework cap.
  PASS  S3: Design-flagged story runs Design Test; unflagged story skips it.
  PASS  S4: Plain story costs exactly 6 spawns.
  PASS  S5: Rebase fail bounces story B; smoke fail bisects to story A; no revert.
  PASS  S6: Blocked on credentials: TDM once per entry, escalation, resume.
  PASS  S7: Follow-up storm: 5 to backlog, 6th -> Needs PO Decision; JOIN unaffected.
  PASS  S8: Crash recovery + human rejection = forward-fix, main untouched.
  PASS  S9: Concurrent epics: JOINs, notifies and follow-up budgets stay isolated.
  PASS  S10: Empty epic: grooming yields zero stories -> Needs PO Decision, no NOTIFY.
  PASS  S11: AC-blocking follow-up joins the epic; JOIN waits for it (no race).
  PASS  S12: Rework counter accumulates ACROSS stages: three different reviewers.
  PASS  S13: Max-flag story (design+security+data) runs all 10 stages: 16 spawns to NOTIFY.
  PASS  S14: Epic-level Blocked (BSA needs domain input): TDM once, resume to Grooming.
  PASS  S15: Repeated spawn crashes escalate (3 consecutive -> Needs PO Decision).
  PASS  S16: DoR gate: un-ready tickets bounce to Grooming; no story released; cap -> PO.
— mutation checks (each disabled guard must break its scenario) —
  CAUGHT  JOIN rule disabled -> S1 fails as expected
  CAUGHT  SKIP-FORWARD disabled -> S3 fails as expected
  CAUGHT  SKIP-FORWARD disabled -> S4 fails as expected
  CAUGHT  rework counter disabled -> S2 fails as expected
  CAUGHT  rework counter disabled -> S12 fails as expected
  CAUGHT  empty-epic guard disabled -> S10 fails as expected
  CAUGHT  JOIN quiescence disabled -> S11 fails as expected
  CAUGHT  crash escalation disabled -> S15 fails as expected
  CAUGHT  DoR gate disabled -> S16 fails as expected
  CAUGHT  DoR gate disabled -> S1 fails as expected
RESULT: OK — workflow v2 behaves as specified
```

## Notes

- Cost pins: 27 spawns for a 3-story epic (S1, incl. the +1 Ticket-Review gate spawn) ·
  6-spawn floor per plain story (S4) · 10 story spawns / 16 total to NOTIFY for a max-flag
  story (S13) — inputs for the per-day budget calibration (spec §6.1).
- The DoR gate costs exactly +1 spawn per epic (batch review of all children in one qas
  spawn); its loop protection reuses §3.2 unchanged.
- Mutation checks are the point: every guard that a review round introduced has at least one
  scenario that fails when the guard is removed (10 mutation runs, all caught). `dor_gate`
  disabled also breaks S1's spawn-count pin — the gate is load-bearing in the happy path,
  not an optional detour.
