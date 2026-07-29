# QAS Validation Report — ABS-187

**Ticket:** ABS-187 — Tests: claim mutual-exclusion (unit + concurrency + E2E + smoke)
**Branch:** `ABS-187-auto` · **QAS commit:** `ddcbd73` (jitter recap fix applied)
**Validated:** 2026-07-11 · **Verdict:** APPROVED

---

## Validation Method

Session-resume: re-verified all repo state before acting (ADR-A-0001, Common Seat Rule §3).
Created a separate QAS worktree (`/tmp/abs187-qa-check`) at `origin/ABS-187-auto@09b0e5c` and
ran all test suites independently — not relying on the BE/Architect handoff claims.

---

## Test Runs (independent QAS execution)

| Suite | Command | Result |
|-------|---------|--------|
| New: `tests/test-claim-mutex.sh` | `bash tests/test-claim-mutex.sh` | **22/22 PASSED** |
| Regression: `tests/test-claim.sh` | `bash tests/test-claim.sh` | **20/20 PASSED** |
| Regression: `tests/test-claim-dispatch.sh` | `bash tests/test-claim-dispatch.sh` | **25/25 PASSED** |
| Shellcheck | `shellcheck -S warning tests/test-claim-mutex.sh scripts/smoke-claim-two-machine.sh` | **0 warnings** |

All three existing suites exit 0 — no regression introduced.

---

## AC/DoD Trace

| # | Acceptance Criterion | Verdict | Evidence |
|---|---------------------|---------|----------|
| AC-1 | Unit + concurrency tests green in CI | **PASS** | 22/22 checks; CI auto-discovers `tests/test-*.sh` (.github/workflows/tests.yml:60) |
| AC-2 | Live smoke = runnable script + documented procedure (grooming re-word) | **PASS** | `scripts/smoke-claim-two-machine.sh` — `probe`/`tally`/`measure`; shellcheck clean; dry-validated; live run is operator step |
| AC-3 | Three measurements recorded with tuned settle/TTL recommendation | **PASS** | `docs/agent-outputs/qa-validations/ABS-187-claim-mutex-evidence.md` §3: settle 1500+1000 ms, TTL 600 s, MAX_OWNED unset |

### DoD items
- [x] ADR-A-0009 (zero-dep bash): pure bash 3.2 + BSD tools + adapter; shellcheck clean
- [x] ADR-A-0010 (minimal-change): 3 new files only; no existing test or source modified
- [x] ABS-66 (procedure data-flow): every command named in smoke script exists in orchestrator.sh:2510-2617

---

## Doc Nit Fixed (MEDIUM, system-architect flagged)

Evidence doc line 112 recap said `settle 1500+750 ms`. Code default (`orchestrator.sh:241`)
and §3.1 recommendation (line 65) both say `ORCH_CLAIM_JITTER_MS=1000` (worst-case 2500 ms).
Fixed and committed as `ddcbd73`, pushed to `origin/ABS-187-auto`.

---

## Integration Note (for RTE, not a QAS finding)

Branch `ABS-187-auto` is rebased onto `origin/ABS-185-auto` (ABS-185 claim implementation).
ABS-185 is Done but not yet merged to `main`. **Sequence the ABS-187 PR after ABS-185 merges**
to keep CI on `main` green.

---

## Verdict

**APPROVED for RTE.**
