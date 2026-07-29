# QA Validation Report — PILOT-49

**Ticket**: PILOT-49 — Infrastruktur-Abbrueche treiben den Iterations-Cap hoch und machen approved Stories unmergebar (Deadlock, live reproduziert)  
**Jira-Zwilling**: ABS-555  
**Branch**: `PILOT-49-auto`  
**Commit under test**: `3281b490`  
**QAS run date**: 2026-07-26  
**Verdict**: ✅ **APPROVED**

---

## Files Changed (commit 3281b490)

| File | Change |
|------|--------|
| `scripts/hooks/iteration-guard.sh` | Infra-abort classification via `INFRA_ABORT_RE`; `abort_count` tracked separately; block message names breakdown |
| `scripts/orchestrator.sh` | `block_for_iteration_cap` captures `ITERATION_GUARD_DETAIL` and surfaces it on the park comment |
| `profiles/neutral/adapters/statuses.yaml` | `Needs PO Decision → Merging` forward edge added |
| `backend/packages/core/src/workflows/statuses.yaml` | Mirror updated identically |
| `tests/test-iteration-guard.sh` | 6 new regression fixtures for AC1/AC2/AC4/AC5 |

---

## Test Results (ABS-285: baseline + branch, same shell, scrubbed env)

| Suite | Baseline (2c564f20) | Branch (3281b490) | Δ New Tests | Result |
|-------|---------------------|-------------------|-------------|--------|
| `tests/test-iteration-guard.sh` | 54/54 | 60/60 | +6 (PILOT-49) | ✅ PASS |
| `tests/test-orchestrator.sh` | (architect verified) | 1327/1327 | 0 | ✅ PASS |
| `tests/test-status-source-drift.sh` | — | 12/12 | 0 | ✅ PASS |
| `tests/test-backend-status-literal-drift.sh` | — | 5/5 | 0 | ✅ PASS |

**No regressions**: all 54 baseline tests pass on the branch.  
**6 new tests** cover the 4 PILOT-49-specific ACs directly.

---

## Acceptance Criteria Verification

### AC1 — Iteration counter distinguishes functional from infra aborts; infra aborts do NOT count

**Status**: ✅ PASS

**Evidence**:
- `INFRA_ABORT_RE` defined in `iteration-guard.sh:100` covers all documented infra causes: `crash-repair`, `inprogress-heal`, `spawn crashed`, `wait-state repair`, `handoff mis-report`, `handoff marker-missing`, `error_max_turns`, `max_turns`, `turn ceiling`, `session-poison`, `session poisoned`, `salvage`, `rate limit`, `ratelimit`, `429`, `timeout`, `connection`, `non-zero exit`
- Specifically covers the live incident cause (`error_max_turns`, `CRASH-REPAIR`) from PILOT-32
- Test: `"2 infra aborts at gate -> counter unchanged, proceed (AC1/AC2)"` — PASS
- Test: `"infra aborts do not consume the cumulative budget (AC1) — no spurious deadlock"` — PASS

### AC2 — Seat abort WITHOUT verdict does NOT consume an iteration

**Status**: ✅ PASS

**Evidence**:
- Criterion implemented as: `infra = (tolower(reason) ~ infra_re)` — checks the transition REASON, not the spawn count
- Infra aborts increment `abort_count` only; never `gate_count` or `total_count`
- Test: same as AC1 — "2 infra aborts at gate -> counter unchanged, proceed (AC1/AC2)" — PASS

### AC3 — Legal path Needs PO Decision → Merging for proven-approved work

**Status**: ✅ PASS

**Evidence**:
- `profiles/neutral/adapters/statuses.yaml`: `- Merging` added under Needs PO Decision transitions with guardrail comment
- `backend/packages/core/src/workflows/statuses.yaml`: mirror updated identically (diff between sections: empty, byte-identical)
- `test-status-source-drift.sh`: 12/12 PASS (statuses.yaml consistency verified)
- `test-backend-status-literal-drift.sh`: 5/5 PASS (backend mirror consistency verified)
- Block comment on the park message: `"If the work is already approved (gate verdicts on the ticket, merge_readiness clean) the PO may route it forward to Merging"` — makes the escape path discoverable

### AC4 — Regression fixtures: infra abort → counter unchanged; real QAS reject → +1

**Status**: ✅ PASS

**Evidence**:
- Test: `"2 real QAS rejects -> +1 each -> block at cap 3 (AC4 control)"` — PASS
- Test: `"1 abort + 2 functional bounces -> cap hit on the functional 2 (AC4)"` — PASS
- These two tests directly encode the AC4 invariant: different reasons → different classification

### AC5 — Observability: block reason names functional vs infra breakdown

**Status**: ✅ PASS

**Evidence**:
- `iteration-guard.sh:380-383`: block message now includes `$abort_count infrastructure abort(s) excluded` and `FUNCTIONAL bounce(s)` count
- `orchestrator.sh` (block_for_iteration_cap): captures guard stderr via `ITERATION_GUARD_DETAIL` and appends it to the park comment body
- Test: `"block reason names the excluded infra aborts (AC5)"` — PASS (asserts `"infrastructure abort"` present in stderr)
- Test: `"block reason names the functional bounce count (AC5)"` — PASS (asserts `"FUNCTIONAL"` present in stderr)

---

## Fail-Safe Bias Verification (architect note, carried forward)

The `INFRA_ABORT_RE` is deliberately broad (covers generic terms like "timeout", "connection"):
- **False positive** (functional reason contains infra term): cap is more lenient — ADR-A-0009 cumulative brake still fires on the real rejects eventually → **safe direction**
- **False negative** (infra reason not matched): re-creates the deadlock → **dangerous direction**

Implementation correctly chooses the safe fail-safe bias. ✅

---

## Escape-Edge Guardrail (AC3)

The NPD → Merging edge in `statuses.yaml` includes an explicit GUARDRAIL comment:
> "use ONLY when the gate approvals are documented on the ticket; a story still genuinely under review takes one of the backward targets above"

This is documentation-level enforcement (PO-judgment gate). The architect's note about this being a deliberate widening of the canonical status machine (ADR-A-0009 brake unchanged) is acknowledged and accepted. ✅

---

## Harness/Mirror Parity

No `harness/claude/agents/*.md` or `harness/claude/skills/*` files were touched → Rule 10 (ABS-317) mirror-parity guard does not apply. ✅

---

## Final Verdict

**✅ APPROVED for Story Acceptance**

All 5 ACs met. Regression fixtures present and passing. Both yaml sources in sync. Full orchestrator suite green (1327/1327). No regressions from baseline. The deterministic deadlock (infra abort → cap trip → parked approved story → unmergeable) is closed.
