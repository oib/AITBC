# QA Validation Report — ABS-399

**Ticket**: ABS-399 — Epic acceptance test: 3-story shared-file sequential-merge end scenario passes Merging with zero conflict-bounce
**Parent epic**: ABS-392
**Branch**: ABS-399-auto
**Commit reviewed**: 5424c1d
**Date**: 2026-07-17
**QAS**: qas (In Test gate)
**Verdict**: ✅ APPROVED

---

## Files Reviewed

| File | Status |
|------|--------|
| `tests/test-epic-end-scenario.sh` (new, 262 lines) | Integration test only — no production code |
| `tests/test-scope-map.txt` | Added `orchestrator.sh`→`test-epic-end-scenario.sh` mapping + new `scripts/rebase-gate-check.sh` row |

---

## Static Checks

| Check | Result |
|-------|--------|
| `bash -n tests/test-epic-end-scenario.sh` | ✅ CLEAN |
| `shellcheck -S warning tests/test-epic-end-scenario.sh` | ✅ CLEAN |

---

## Independent Test Run Results

### Primary suite: `tests/test-epic-end-scenario.sh`

```
=== epic-end 3-story shared-file sequential-merge scenario (ABS-399) ===

Part 1. Topological merge-token grant — 3-story depends_on chain (lever 1, ABS-396)
  PASS  S1 walked to Merging
  PASS  S2 walked to Merging
  PASS  S3 walked to Merging
  PASS  the ROOT predecessor S1 takes the token first, despite being created LAST
  PASS  S2 defers to its predecessor S1
  PASS  S3 defers to its predecessor S2
  PASS  the deferral is topological (depends_on), not FIFO
  PASS  single-holder invariant — exactly ONE rte merge seat (human merge-to-main untouched, ADR-A-0005)

Part 2. Pre-acceptance rebase-gate — shared file, sequential merges, ZERO bounce (levers 1+2)
  PASS  DEMO-2: epic-branch merge is CONFLICT-FREE (resolved pre-acceptance)
  PASS  DEMO-2: merged shared.txt has no conflict markers
  PASS  DEMO-3: WITHOUT the gate, the pre-rebase merge WOULD conflict (the bounce the gate prevents)
  PASS  DEMO-3: gate ACCEPTs after the documented rebase
  PASS  DEMO-3: epic-branch merge is CONFLICT-FREE (resolved pre-acceptance)
  PASS  DEMO-3: merged shared.txt has no conflict markers
  PASS  DEMO-4: WITHOUT the gate, the pre-rebase merge WOULD conflict (the bounce the gate prevents)
  PASS  DEMO-4: gate ACCEPTs after the documented rebase
  PASS  DEMO-4: epic-branch merge is CONFLICT-FREE (resolved pre-acceptance)
  PASS  DEMO-4: merged shared.txt has no conflict markers
  -- gate outcomes --
  PASS  S1 was already clean (forked at the current tip) — no rebase, straight ACCEPT
  PASS  S2 rebase-needed was caught AT Story Acceptance (pre-Merging)
  PASS  S3 rebase-needed was caught AT Story Acceptance (pre-Merging)
  -- ZERO conflict-bounce (the epic's headline AC) --
  PASS  no Merging -> Ready for Development in the driven transition ledger
  PASS  no Merging -> Ready for Development recorded on ANY ticket (real tracker state)
  PASS  S1 finished at Docs (merged, never bounced)
  PASS  S2 finished at Docs (merged, never bounced)
  PASS  S3 finished at Docs (merged, never bounced)
  -- the shared file carries every story's change --
  PASS  epic shared.txt is the clean union of all three stories

Part 3. Companion equivalence — degraded readiness <-> native merge_readiness (AC3)
  PASS  degraded readiness=0 (clean) === native merge_readiness 'clean' (story contains the epic tip)
  PASS  degraded readiness=1 (rebase-needed) === native merge_readiness 'rebase-needed' (epic advanced past the story)

=== Results ===
  Total:  29
  Passed: 29
  Failed: 0

All epic-end scenario tests passed.
```

**Primary suite: 29/29 PASS** ✅

### Sibling regression suites

| Suite | Result |
|-------|--------|
| `tests/test-merge-token.sh` | 51/51 PASS ✅ |
| `tests/test-rebase-gate-check.sh` | 7/7 PASS ✅ |

---

## Acceptance Criteria Verification

### AC1: 3-story shared-file sequential-merge scenario completes through Merging with ZERO conflict-bounce

**PASS** ✅

Part 2 drives a real git repo (3 branches all rewriting the same line in `shared.txt`) with a mock-tracker status ledger. The pre-acceptance rebase-gate (`scripts/rebase-gate-check.sh`, ABS-398) catches S2 and S3 _at Story Acceptance_ (before entering Merging). The seat rebases to resolve the conflict, then the gate re-ACCEPTs. Only after a clean gate does the story enter Merging. Result:
- 0 `Merging → Ready for Development` transitions in the driven ledger ✅
- 0 `Merging → Ready for Development` recorded in real tracker state ✅
- All three stories finish at `Docs` ✅
- `shared.txt` = `"shared s1 s2 s3"` (clean union, no conflict markers) ✅
- A control trial-merge proves the conflict the gate prevents is genuine ✅

### AC2: Exercises topological token ordering + pre-acceptance rebase-gate + merge_readiness together

**PASS** ✅

- **Part 1**: A 3-story `depends_on` chain created in reverse age order is driven through the real runner sweep (`--dry-run --once`). The ROOT predecessor S1 takes the merge token first despite being created last (`topo=depends_on`). S2 and S3 each emit `MERGE-QUEUE-WAIT`. Exactly ONE `rte` seat is spawned — ADR-A-0005 human merge-to-main boundary intact.
- **Part 2**: Pre-acceptance rebase-gate exercised over a real git repo.
- **Part 3**: `merge_readiness` equivalence documented.

### AC3: Degraded jira/mock variant covered (or companion equivalence documented)

**PASS** ✅

Part 2 _is_ the degraded git-only path (runs `scripts/rebase-gate-check.sh`). Part 3 adds an explicit companion assertion: `degraded readiness=0 (exit 0)` ≡ native `merge_readiness 'clean'` and `degraded readiness=1 (exit 1)` ≡ native `merge_readiness 'rebase-needed'` — both reduce to `git merge-base --is-ancestor <epic-tip> <story>`. Equivalence is documented and asserted.

---

## Scope & Guardrails Check

| Guardrail | Status |
|-----------|--------|
| Integration test only (no new production code) | ✅ Confirmed — only `tests/` files |
| No new feature / cost / credential | ✅ Confirmed |
| Human merge-to-main boundary intact | ✅ Asserted (exactly 1 rte seat, ADR-A-0005) |
| Depends on ABS-395/396/397/398 consumed | ✅ All consumed in the three-part proof |

---

## Non-Blocking Note (carried from Arch Review, no bounce)

`STUB` points at `tests/fixtures/stub-claude.sh` (which ships as `stub-spawn.sh`). This is a pre-existing dangling reference copied verbatim from the passing sibling `test-merge-token.sh`; it is harmless under `--dry-run` (the variable is never invoked). No regression introduced. Future cleanup candidate — not a QAS blocker.

---

## Verdict

**✅ APPROVED — transition to Story Acceptance**

- All 3 ACs independently verified PASS
- 29/29 assertions pass in my independent run
- Sibling regressions 51/51 and 7/7 clean
- `bash -n` + `shellcheck -S warning` clean
- No production code, no RLS/migration surface, no cost/credential
- Scope honoured; guardrails intact
- No `design` flag → exit to Story Acceptance (not Design Test)
