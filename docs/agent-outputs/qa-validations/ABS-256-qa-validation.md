# QA Validation — ABS-256

**Branch:** `ABS-256-auto` | **Commit:** `429b77a` | **Date:** 2026-07-13 | **Actor:** qas  
**Verdict:** APPROVED

## Files under review

| File | Change |
|------|--------|
| `adrs/agentic/ADR-A-0022-per-epic-merge-token.md` | +213 lines (new) |
| `scripts/orchestrator.sh` | +186 lines (merge_token_gate in dispatch()) |
| `tests/test-merge-token.sh` | +300 lines (36 assertions, 6 scenarios) |
| `adrs/agentic/ADR-A-0014-workflow-v3-per-epic-merge-gate.md` | +6 lines (bidirectional link) |

## AC1 — Design ADR

`adrs/agentic/ADR-A-0022-per-epic-merge-token.md` exists on branch, status `proposed`.
Status is correct: ADR-A-0004 requires human acceptance; agents cannot accept ADRs.

The ADR frames the design decision: (a) merge-queue token and (b) runner serializes Merging
spawns are not alternatives. (a) is the semantics adopted; (b) is the only layer that can
implement it (the `rte` seat is a stateless subagent per spawn, ADR-A-0002, and cannot
serialize itself).

The ADR documents the root cause (two compounding defects: no per-epic serialization in
`dispatch()` plus mechanical rebase conflicts priced as code defects), the load-bearing rule
(token held across a merge-bounce, freezing the epic tip while the holder fixes its rebase),
the narrowing of ADR-A-0014 §3's periodic sync-rebase to `Epic Integration` only, and the
deliberate separation from the conflict-magnet proposal (different surface: epic-to-main vs
story-to-epic-tip).

Rejected alternatives are listed and reasoned: `ORCH_MAX_CONCURRENT=1`, plain merge queue
without the cross-bounce hold, `rte` hand-resolving conflicts, merge commits, file-overlap
detection.

**AC1: PASS**

## AC2 — Two stories, same file → no double bounce

`tests/test-merge-token.sh` drives the real runner (`--dry-run --once`) against the mock
tracker in isolated `mktemp` environments per scenario.

QAS independent run result: **36/36 PASS (exit 0)**.

**Scenario A — serialization.** Two sibling stories of one epic walk to `Merging`. One sweep:
exactly one `rte` seat spawns (`MERGE-TOKEN-ACQUIRE`); the other emits `MERGE-QUEUE-WAIT`
and rests in `Merging`. Token is keyed by epic, not ticket.

**Scenario B — the load-bearing rule.** S1 acquires the token. S2 waits.
`rte` bounces S1 to `Ready for Development`. On the next sweep: S1 re-gates (implementer
spawns), the token is NOT released (`bounce does NOT release the token — ADR-A-0022 §3`
assertion green), and S2 STILL waits (`MERGE-QUEUE-WAIT` asserted again, `INTENT SPAWN
ticket=S2 role=rte to=Merging` absent). S1 re-walks to `Merging`, re-enters its own token
(`MERGE-TOKEN-HOLD`), spawns `rte`. `bounces=1` reported. `bounces=2` absent. S1 reaches
`Docs`; token releases. S2 acquires token and spawns `rte`. S2 no longer waits.

**AC2: PASS**

## AC3 — Bounce telemetry

**Scenario C.** Solo story: `bounces=0` on first dispatch. After two `rte: Merging → Ready
for Development` transitions: `bounces=2`.

**Section F (unit, sourced).** `merge_bounce_count` counts `rte`-actor comments with
`Merging -> Ready for Development` transition text. Forward exits (`Merging -> Docs`,
`Merging -> Done`) count 0. Non-`rte` actors count 0. Empty dump yields 0. Two rte bounces
accumulate (unrelated `Story Acceptance -> Merging` transition ignored).

**AC3: PASS**

## Additional checks

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | CLEAN |
| `ORCH_MERGE_QUEUE=0` (kill-switch) | Both siblings spawn; no MERGE-QUEUE-WAIT (Scenario D) |
| Parentless story | Spawns `rte` ungated; never queues (Scenario D) |
| Stale-token reclaim | Holder parked off merge path (human → Blocked) → token reclaimed → sibling proceeds (Scenario E) |

## Regression — tests/test-orchestrator.sh

QAS run (isolated, no concurrent runs): **633/651 pass, 18 fail**.

Failing tests:

```
SKIP-UNLABELLED, po-agent spawn, STALL-RAISE on DEMO-1   (4 — namespace collision)
harness provenance path (expects ABS-256-work, got stable repo)  (2)
operator model-cap (expected 15, got 80 — no-cap default)        (1)
MODEL-LABEL-SKIP / downsize on DEMO-1/3/7                        (5)
LABEL-PROPAGATE / orchestrator-ready on DEMO-2/3                 (6)
```

Zero of the 18 failures involve `Merging`, `merge_token_gate`, `MERGE-TOKEN-ACQUIRE/HOLD/RELEASE`,
`MERGE-QUEUE-WAIT`, or `bounces=`. `merge_token_gate` returns early on any non-`Merging`
dispatch edge; it structurally cannot touch those tests.

Failure categories match the documented environmental causes: DEMO-* ticket namespace reuse
across concurrent runs, harness-provenance resolving to the stable repo path (not the tmp
worktree), and the no-cap model default (`80` vs configured `15`).

System architect ran a byte-identical A/B: HEAD `429b77a` and parent `1b561d9` produced
identical failure sets (32 each under higher concurrent load). QAS run confirms the same
pattern in isolation with fewer contamination effects.

**Zero regressions introduced.**

## Design deviation accepted

The implementation derives token staleness from holder liveness (holder gone or off the
story merge path) rather than the ADR sketch's `ORCH_LOCK_TTL` wall-clock reclaim.
The ADR marks Implementation Notes non-binding. The deviation is code-documented and sound:
a legitimate hold spans a full re-gate walk, and a TTL reclaim would steal the token mid-fix
and reopen the cascade the fix closes.

## Verdict

**APPROVED.** AC1, AC2, AC3 pass. Zero regressions. Syntax clean.

**Note for human/PO:** ADR-A-0022 ships `proposed`. Human acceptance is required before it
governs (ADR-A-0004). Until then, ADR-A-0014's original text stands.
