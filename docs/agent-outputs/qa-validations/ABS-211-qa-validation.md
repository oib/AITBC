# QA Validation — ABS-211

**Ticket**: ABS-211 Done-Gate: PR-merged-auf-Zielbranch als DoD-Vorbedingung vor Docs->Done  
**Date**: 2026-07-12  
**QAS seat**: independent verification from `In Test`  
**Branch**: ABS-211-auto  
**Commit**: 551f915 `feat(orch): gate Done on merged PR before epic JOIN [ABS-211]`  
**Working tree**: clean (git status --short: empty)

---

## Acceptance Criteria — Verdict per Item

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Story mit offenem PR kann Docs nicht Richtung Done verlassen; benennender Kommentar (welcher PR fehlt) | **PASS** | done-gate test: "gate INTERVENES (rc 0) on a Done whose PR is still open"; "AC1: the comment NAMES which PR is missing (#133)"; "audit comment cites ABS-211"; tech-writer.md seat precondition added |
| AC2 | Story mit gemergtem PR passiert unveraendert | **PASS** | done-gate test: "merged PR -> no-op (rc 1), Done passes"; "no-forge / no-PR pass (fail-open placeholder)"; no tracker writes on merged path |
| AC3 | Guard-/Repair-Kette erzeugt keinen Merging-Skip mehr ohne PR | **PASS** | done-gate test: "repair-chain Done with open PR #129 is bounced to Merging (rc 0)"; "AC3: routes back through Merging (no Merging-skip without a merged PR)"; `done_pr_gate` at line 3679, `join_check_epic` at line 3685 — gate fires before JOIN |
| AC4 | Tests; Suite gruen | **PASS** | See test results below |

---

## Test Results

| Suite | Result | Count |
|-------|--------|-------|
| `tests/test-done-gate.sh` | **29/29 PASS** | Primary AC evidence |
| `tests/test-station-guard.sh` | **50/50 PASS** | Regression: no station-guard breakage |
| `tests/test-harness-parity.sh` | **6/6 PASS** | Provider mirror in sync |
| `tests/test-orchestrator.sh` | 589/596 (7 pre-existing) | See note below |

### test-orchestrator residual failures (7) — pre-existing, environmental, orthogonal

The 7 failures fall into two families, neither touched by the ABS-211 diff:

**Provenance-path (2 tests):**
- `startup provenance line reports harness=<stable repo>` — expects this tmp worktree path; fails because the test was authored for the stable checkout
- `no seam: provenance harness == script repo` — same cause

**Model-label/max-turns config (5 tests):**
- `explicit operator-wide cap overrides the qas built-in (expected '15', got '80')`
- `downsize label on a system-architect review -> MODEL-LABEL-SKIP`
- `review/judgment seat keeps its role default (no downsized model reaches the seat)`
- `upsize label logs MODEL-LABEL (applied) for the architect`
- `dry-run: review seat -> MODEL-LABEL-SKIP (never MODEL-LABEL)`

**Why orthogonal**: `done_pr_gate()` returns 1 (no-op) immediately unless `to=Done` AND `$FORGE_CMD` is set. In this boilerplate repo `FORGE_CMD` is empty by default. The ABS-211 diff is 0 deletions and touches only `done_pr_gate`/`$FORGE_CMD` seam / tech-writer / tests — none of which interact with provenance-path or model-label logic. The system-architect baseline-verified this independently; the same 7 failures are confirmed stable across runs.

---

## Implementation Correctness

**Diff scope** (git show --stat HEAD): `scripts/orchestrator.sh` +100 (0 deletions), `harness/claude/agents/tech-writer.md` +6, `agent_providers/claude_code/prompts/tech-writer.md` +6 (mirror), `tests/test-done-gate.sh` +180.

**Wiring** (verified by grep): `done_pr_gate "$ticket" "$to"` at line 3679, `join_check_epic` at line 3685 — gate fires first in dispatch's Done branch.

**Pattern compliance**: mirrors `station_guard` shape (post-landing, idempotent, MODE-aware, `ticket_still_in` guard). `forge()` resolves `$FORGE_CMD` the same way `tracker()` resolves `$TRACKER_CMD`. Fail-OPEN in placeholder case (no forge platform / no PR → Done passes unchanged); ADR-A-0004/0005 untouched (gate never merges).

**ABS-66 data-flow**: tech-writer precondition consumes the Merging seat's `Result: merged` gate-results comment, which `rte.md` produces. Defense-in-depth: seat precondition + deterministic runner backstop.

---

## Verdict

**APPROVED** — all four acceptance criteria met. Proceed to Story Acceptance.

