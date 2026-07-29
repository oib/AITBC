# QA Validation Report — ABS-151

**Ticket**: ABS-151 — Harness: fix recurring be-developer SPAWN-CRASH (non-zero exit / no parseable handoff) at Ready for Development
**QAS Actor**: qas
**Date**: 2026-07-09
**Commit under review**: `c1da40c` (branch `ABS-151-auto`)
**Verdict**: ✅ **APPROVED — Approved for RTE**

---

## Validation Approach

Bash-only harness fix (spawn/handoff-parse path, `scripts/orchestrator.sh`). QAS independently re-ran the full test suite from scratch, confirmed the baseline test count at parent `e59dcfa`, verified all 5 ACs by tracing implementation to test assertions, and applied stop-slop before writing this report.

---

## Test Suite Results

### HEAD (c1da40c)

```
bash tests/test-orchestrator.sh

Total:  457
Passed: 450
Failed: 7
```

### Baseline (e59dcfa — parent)

```
# Checked out parent files; ran suite; restored HEAD
bash tests/test-orchestrator.sh

Total:  444
Passed: 437
Failed: 7
```

### Delta

| Metric | Baseline | HEAD | Delta |
|--------|----------|------|-------|
| Total tests | 444 | 457 | +13 (matches commit) |
| Passed | 437 | 450 | +13 |
| Failed | 7 | 7 | 0 (no regressions) |

**Pre-existing failures (7) — identical in both runs:**
- 2 × self-hosting provenance seam (`startup provenance line reports harness=<stable repo>`, `no seam: provenance harness == script repo`)
- 5 × model-label env (`non-implementer seat keeps the lean global default`, `downsize label on a system-architect review -> MODEL-LABEL-SKIP`, `review/judgment seat keeps its role default`, `upsize label logs MODEL-LABEL (applied) for the architect`, `dry-run: review seat -> MODEL-LABEL-SKIP`)

None of these touch the spawn/handoff-parse path. All are pre-existing environment failures unrelated to ABS-151.

---

## AC Verification

### AC1 — Root cause named; commit message references exact code path/line ✅

Commit message (`c1da40c`) names four precise code locations:

| Code path | Location cited in commit |
|-----------|-------------------------|
| `run_spawn_cmd` subshell — exit code/stderr discarded | `orchestrator.sh:3263-3274` |
| `attempt_spawn` clean-exit-no-handoff path | `orchestrator.sh:3406-3421` |
| `hit_turn_ceiling` / `error_max_turns` detection | `orchestrator.sh:3337` |
| `record_spawn_crash` (live_spawn call site) | `orchestrator.sh:3553` |

The root cause is stated directly: `run_spawn_cmd` executes inside the caller's command-substitution subshell, so its exit code and captured stderr never reached `record_spawn_crash`; the dominant failure mode is the CLI hitting `--max-turns` and aborting with `error_max_turns`, which the old code treated identically to a genuine empty handoff.

**PASS.**

---

### AC2 — Reproduction documented; includes concurrent-epic-seat scenario ✅

Two reproduction paths documented and exercised in `tests/test-orchestrator.sh`:

1. **Turn-ceiling abort**: `STUB_MAX_TURNS_EXIT=1` makes `stub-spawn.sh` emit `{"subtype":"error_max_turns",...}` and exit 0 with no handoff — matching the operator's observed signature (transcript stops, `tokens_out` truncated). Fresh session only (resumed repair sessions still produce the handoff, per the existing contract).

2. **Concurrent-epic-seat isolation**: Two tickets (`T` and `T2`) both set `STUB_FAIL=1`, dispatched in the same `--once` cycle. The diag file is keyed to `$pf` — a per-attempt packet path unique to each spawn — so neither seat's diagnostic contaminates the other.

Tests confirm:
- `INTENT SPAWN-CRASH ticket=$T` and `INTENT SPAWN-CRASH ticket=$T2` both land
- Each ticket carries its own `Diagnostic:` field (no cross-contamination)

**PASS.**

---

### AC3 — Diagnostic (stderr + exit code) emitted on handoff-parse failure — EXECUTED test ✅

All six diagnostic assertions pass:

| Test | Result |
|------|--------|
| `ABS-151: crash marker carries a diagnostic (not opaque)` | PASS |
| `ABS-151: non-zero-exit diagnostic surfaces the spawn exit code` | PASS |
| `ABS-151: non-zero-exit diagnostic surfaces the captured stderr tail` | PASS |
| `ABS-151: empty-handoff crash marker names the failure mode` | PASS |
| `ABS-151: crash marker names the turn-ceiling root cause` | PASS |
| `ABS-151: crash marker cites the CLI signal (error_max_turns)` | PASS |

The implementation writes `exit=<rc>\nstderr=<tail>` to `$pf.diag` inside `run_spawn_cmd` before the subshell exits. `attempt_spawn` reads it back after the command substitution completes. The three classification branches are:
- Non-zero exit: `non-zero exit (exit=N); stderr: <tail>`
- Turn-ceiling: `clean exit (exit=0) but NO parseable handoff — TURN CEILING reached (CLI error_max_turns at --max-turns; transient, raise ORCH_MAX_TURNS_<ROLE>...)`
- Genuine empty/unparseable: `clean exit (exit=0) but no parseable handoff (repair/synthesis produced none); stderr: <tail>`

**PASS.**

---

### AC4 — Regression test: empty/unparseable handoff handled deterministically (retry then escalate) — EXECUTED and green ✅

| Test | Result |
|------|--------|
| `ABS-151: missing handoff is retried per §6 before escalation` | PASS |
| `ABS-151: turn-ceiling abort is retried per §6 before escalation` | PASS |
| `INTENT SPAWN-CRASH ticket=$T` (deterministic escalation after retry) — no-handoff path | PASS |
| `INTENT SPAWN-CRASH ticket=$T` (deterministic escalation after retry) — turn-ceiling path | PASS |

Both new failure modes (empty handoff and turn-ceiling abort) follow the §6 policy: one retry, then escalate to a SPAWN-CRASH marker carrying the diagnostic. Deterministic: the sequence `INTENT RETRY → INTENT SPAWN-CRASH` is asserted for each path.

**PASS.**

---

### AC5 — Existing orchestrator/spawn tests remain green ✅

Pre-existing failure count: 7 at baseline `e59dcfa`, 7 at HEAD `c1da40c`. Same 7 tests in both runs. Zero tests changed from PASS to FAIL. The 13 new assertions are the entire delta.

**PASS.**

---

## Scope / Guardrail Check

- ABS-74 crash-limit policy: not touched (record_spawn_crash escalation logic unchanged — only the `diag` argument added to the marker body).
- ABS-135 `from_status` packet correctness: not touched.
- Packet-schema changes: none.
- Scope is bash spawn/handoff-parse path only, matching the PO guardrail note (2026-07-09).

---

## Summary

| AC | Result |
|----|--------|
| AC1: Root cause + exact code path/line in commit | ✅ PASS |
| AC2: Reproduction documented (turn-ceiling + concurrent-seat) | ✅ PASS |
| AC3: Diagnostic emitted on handoff-parse failure — executed test | ✅ PASS |
| AC4: Deterministic retry-then-escalate — executed and green | ✅ PASS |
| AC5: Existing tests remain green | ✅ PASS |

**Verdict: APPROVED — Approved for RTE**

All 5 acceptance criteria met. 13 new tests added, all green. Zero regressions. Pre-existing failures identical before and after (7, environment-only).
