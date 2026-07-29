# QAS Validation Report — ABS-254

**Ticket**: ABS-254 — Session-Invalidierung bei Workspace-Trust-Änderung  
**Branch**: `ABS-254-auto` @ `802bed0`  
**QAS seat**: resume, 2026-07-13  
**Verdict**: ✅ APPROVED

---

## Verification Evidence

### Pre-flight (branch state)
- Branch: `ABS-254-auto`, tip `802bed0`
- Local == origin (tree clean, pushed)
- Three ABS-254 commits: `77fb11f` (ADR), `beac832` (poison guard), `802bed0` (salvage fix)
- Syntax: `bash -n` clean on `scripts/orchestrator.sh`, `tests/fixtures/stub-spawn.sh`, `tests/test-orchestrator.sh`

### AC1 — session-baked vs spawn-fresh design note
**PASS.** `adrs/agentic/ADR-A-0022-session-invalidation-inputs.md` exists with a decision table that classifies every input as session-baked or spawn-fresh, backed by empirical test results (deny/flip/resume proof). ADR-A-0002 carries a bidirectional link to ADR-A-0022. Status: `proposed` per ADR-A-0004 (human-only acceptance).

### AC2 — trust fingerprint rejected, allowlist stays out
**PASS.** `compute_config_generation` was not modified. The function hashes only `orchestrator.sh`, `orchestrator-spawn-claude.sh`, and agent definitions. Comments inside the function explicitly cite ADR-A-0022 and the retro 2026-07-10 decision, ruling out `settings.local.json` and `~/.claude.json`. Trust fingerprint is not present — correct per the conditional "falls Design bestätigt", and the design does not confirm.

### AC3 — test cases
**16/16 PASS** — independently run against `ABS-254-auto @ 802bed0`.

Assertions verified:
| # | Assertion | Result |
|---|-----------|--------|
| 1 | Clean spawn stores its session (guard inert on healthy path) | PASS |
| 2 | Denial-hit spawn resumes the stored clean session (pre-condition) | PASS |
| 3 | Denial-hit spawn stores no session AND drops the one it resumed | PASS |
| 4 | SESSION-POISONED event in run.log | PASS |
| 5 | A denial-hit session is never resumed | PASS |
| 6 | Next spawn after denial starts fresh (INTENT SPAWN, not RESUME) | PASS |
| 7 | Kill-switch ORCH_SESSION_POISON_GUARD=0 stores denial-hit session | PASS |
| 8 | Kill-switch off → no SESSION-POISONED event | PASS |
| 9 | Denial+cap co-occurrence: birth spawn still salvage-resumes | PASS |
| 10 | Salvage produces a clean handoff | PASS |
| 11 | Salvaged session NOT stored (birth denials poison the transcript) | PASS |
| 12 | Salvage-store drop is a SESSION-POISONED run.log event | PASS |
| 13 | Control: clean cap birth spawn salvage-resumes | PASS |
| 14 | Control: clean salvage DOES store its session (drop is birth-denial-driven) | PASS |
| 15 | AC3: allowlist edit does NOT invalidate stored sessions (retro upheld) | PASS |
| 16 | AC3: permission-surface edit causes no SESSION-INVALIDATED churn | PASS |

### Regex independent verification
`result_has_permission_denials()` tested against all 6 cases inline:
- Empty array `[]` → CLEAN ✓
- Whitespace-only `[  ]` → CLEAN ✓  
- Absent field → CLEAN ✓
- Single denial → DENIALS ✓
- Multiline non-empty → DENIALS ✓
- `error_max_turns` + denials co-occurrence → DENIALS ✓

### Code-path verification
- `store_session()` poison guard: `force_poison` 6th arg, deletes pre-existing file before returning, logs SESSION-POISONED ✓
- Salvage block: `birth_denials` captured BEFORE `out="$out_s"` reassignment ✓
- Kill-switch `ORCH_SESSION_POISON_GUARD=0` present and tested ✓
- `compute_config_generation` untouched (no hash change) ✓

### Full suite (first run, same commit)
**708 total / 690 pass / 18 fail**  
The 18 failures are pre-existing self-hosting clusters (label-propagation, MODEL-LABEL/downsize/upsize, `harness=<stable repo>` provenance, reconcile-dispatch, qas cap-override) — none touch session, resume, salvage, poison, or config-generation code. Zero new failures from the ABS-254 diff (confirmed by architecture review: failing-NAME diff empty both directions vs baseline).

---

## AC/DoD Checklist

- [x] AC1: ADR-A-0022 session-baked vs spawn-fresh table — DONE
- [x] AC2: Trust fingerprint rejected per design; allowlist stays out — DONE  
- [x] AC3: Test cases — allowlist change does NOT invalidate; denial-hit session not resumed; salvage re-admission closed; kill-switch covered — DONE
- [x] `bash -n` clean on all changed files
- [x] 16/16 ABS-254 test assertions PASS (independently verified)
- [x] Zero new failures vs baseline
- [x] `compute_config_generation` untouched
- [x] ADR ships `proposed`, ADR-A-0002 bidirectional link present

---

**Verdict: APPROVED for Story Acceptance.**

