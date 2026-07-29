# QA Validation — ABS-605

**Title:** Stationsabhaengiger Salvage-Cap + RTE-Turn-Cap-Rekalibrierung  
**Verdict:** APPROVED  
**Date:** 2026-07-27  
**QAS commit under test:** `0dddee27` on `ABS-605-auto` (`refs/remotes/gitlab/ABS-605-auto`)

---

## Syntax check

```
bash -n scripts/orchestrator.sh   → clean
bash -n tests/test-orchestrator.sh → clean
```

## Function exercise (independent source, QAS seat)

Sourced `scripts/orchestrator.sh` directly and exercised all new functions:

| Call | Result | Expected | Status |
|---|---|---|---|
| `builtin_role_max_turns rte` | `100` | `100` | ✅ PASS |
| `builtin_role_salvage_max_turns rte` | `30` | `30` | ✅ PASS |
| `builtin_role_salvage_max_turns be-developer` | `''` | `''` | ✅ PASS |
| `salvage_max_turns rte` (default=5) | `30` | `30` | ✅ PASS |
| `salvage_max_turns be-developer` | `5` | `5` | ✅ PASS |
| `salvage_max_turns qas` | `5` | `5` | ✅ PASS |
| `ORCH_SALVAGE_MAX_TURNS_RTE=42 salvage_max_turns rte` | `42` | `42` | ✅ PASS |
| `ORCH_SALVAGE_MAX_TURNS_BE_DEVELOPER=9 salvage_max_turns be-developer` | `9` | `9` | ✅ PASS |

Previously unchanged built-ins (regression):

| Call | Result | Status |
|---|---|---|
| `builtin_role_max_turns qas` | `180` | ✅ unchanged |
| `builtin_role_max_turns po-agent` | `40` | ✅ unchanged |
| `builtin_role_max_turns issue-enrichment` | `60` | ✅ unchanged |

## Suite shard — `_SHARD_RANGE=4993:5358` (run twice independently)

```
Run 1: ##SHARDRESULT PASS=811 FAIL=0 TOTAL=811  (exit 0)
Run 2: ##SHARDRESULT PASS=811 FAIL=0 TOTAL=811  (exit 0)
```

Commit under test: `0dddee27` (`git rev-parse HEAD`)

ABS-605 labelled assertions in the shard (all PASS):

```
PASS  ABS-605: rte built-in cap raised 60->100 (ceil_to_10 of observed peak 61 x1.5)
PASS  ABS-605: rte has a station-specific salvage budget (30, full-suite exit)
PASS  ABS-605: an ordinary seat has no station-specific salvage budget
PASS  ABS-605: rte salvage resolves to the station-aware 30, not the default 5
PASS  ABS-605: an ordinary seat salvage resolves to the default 5
PASS  ABS-605: a non-rte measured seat still uses the default salvage 5
PASS  ABS-605: ORCH_SALVAGE_MAX_TURNS_<ROLE> env beats the built-in per-role value
PASS  ABS-605: ORCH_SALVAGE_MAX_TURNS_BE_DEVELOPER=9 beats the default for an ordinary seat
```

## AC checklist

### AC1 — `ORCH_SALVAGE_MAX_TURNS` per-role resolvable

- ✅ `salvage_max_turns()` resolves in order: per-seat env `ORCH_SALVAGE_MAX_TURNS_<ROLE>` → `builtin_role_salvage_max_turns()` → default `ORCH_SALVAGE_MAX_TURNS`
- ✅ Pattern mirrors ABS-156/ABS-565 via the same `role_env` helper
- ✅ RTE station: built-in = 30 (its ABS-453 full-suite exit cannot run in 5 turns)
- ✅ All other seats fall to the default 5 (no station-specific budget)
- ✅ Both consumers in `attempt_spawn` use `$salvage_cap`: the `SALVAGE-RESUME` intent log line and `SPAWN_MAX_TURNS_OVERRIDE`
- ✅ Regression tests cover rte=30, be-developer=5, qas=5, and per-seat env overrides for both rte and ordinary seats

### AC2 — RTE built-in cap recalibration

- ✅ `builtin_role_max_turns rte` raised from 60 to 100
- ✅ Derivation documented: `ceil_to_10(61×1.5) = 100` — rte hit `subtype=error_max_turns` at `num_turns=61` against the old cap 60; same formula applied in ABS-565
- ✅ Derivation present in both the orchestrator.sh header comment and the inline `builtin_role_max_turns` comment

## Scope check

Two files changed: `scripts/orchestrator.sh` (+60 net), `tests/test-orchestrator.sh` (+20 net).  
Shell orchestrator infra only. No product source, no DB ops, no RLS, no auth. YAGNI: resolver is 3 lines; no speculative abstraction.

---

**VERDICT: APPROVED — transition to Story Acceptance**
