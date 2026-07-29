# QA Validation Report — ABS-355

**Ticket**: ABS-355 — Seat-Provisionierung: Base-Freshness-Guard + Env-Isolation (zweifacher Live-State-Wipe 16.07.)
**Branch**: `ABS-355-auto`
**HEAD commit**: `232909f` (on `7d42d4a` base fix)
**Validator**: QAS
**Date**: 2026-07-17T00:20:00Z
**Iteration**: In Test (after System-Architect Stage-1 In Review APPROVED)

---

## Summary

Independent QAS validation of all three ACs at `In Test`. The implementation is **bash tooling only** (`scripts/orchestrator.sh` +91/−15 across commits `7d42d4a` + `232909f`, plus `tests/orchestrator.d/ABS-355-seat-provisioning.sh`). No DB/RLS/frontend/auth surface.

---

## Validation Method

**Primary**: Ran the ABS-355 seam test file (`tests/orchestrator.d/ABS-355-seat-provisioning.sh`) via a standalone QAS driver that replicates the full `tests/test-orchestrator.sh` harness context (assert helpers, `new_env`/`cleanup_env`, all env pins) — identical to the technique the System-Architect used to independently verify. The driver sources the real orchestrator and test file; the env was scrubbed of all `ORCH_STATE_DIR/ORCH_STOP_FILE/ORCH_RUN_LOG/ORCH_INSTANCE_ID_FILE/JIRA_TRACKER_STATE` before invocation.

**Workaround for pre-existing suite death**: The full `tests/test-orchestrator.sh` run hard-dies at the `ABS-295→296` boundary before reaching `ABS-355`'s position in `orchestrator.d/`. This is a **pre-existing** defect (ABS-295 crash-repair `set -e` death, proven identical with the ABS-355 file removed). The standalone driver approach gives identical coverage to running at an early `orchestrator.d` slot — the same technique that both the developer and system-architect used to independently verify.

---

## Bash Syntax Check

```
bash -n scripts/orchestrator.sh      → PASS (syntax clean)
bash -n tests/orchestrator.d/ABS-355-seat-provisioning.sh → PASS
```

---

## AC Validation Results

### AC1 — Base-Freshness-Guard (provisionierung wählt frischen Remote)

**Requirement**: Provisionierung schlägt hart fehl oder wählt den frischen Remote, wenn origin nicht fetchbar/eingefroren ist (Seam-Test mit totem origin)

**Implementation**: `resolve_fresh_base()` + integration into `ensure_worktree()`. Uses `_bounded_git` (portable hard wall-clock ceiling, SSH `ConnectTimeout=8` + `http.lowSpeedLimit/Time`) to probe all remotes via `ls-remote`; dead/unreachable remotes are skipped; freshest reachable SHA (newest commit timestamp) wins. Never falls back to checkout HEAD.

| Assertion | Result |
|-----------|--------|
| `ABS-355 AC1a: worktree bases on the reachable fresh remote main (not the dead origin, not foreign HEAD)` | ✅ PASS |
| `ABS-355 AC1a: foreign HEAD commit is NOT dragged into the new branch` | ✅ PASS |
| `ABS-355 AC1b: freshest remote (gitlab) wins over the frozen origin tip` | ✅ PASS |
| `ABS-355 AC1b: the frozen origin tip is NOT chosen as the base` | ✅ PASS |

**AC1 verdict**: ✅ PASS — dead-origin seam test and frozen-origin incident replay both green.

---

### AC2 — Env-Isolation (Seat-Env enthält keine Live-State-Variablen)

**Requirement**: Seat-Env enthält keine Live-State-Variablen (Assertion im Spawn-Seam-Test)

**Implementation**: `local _scrub=(env -u ORCH_STATE_DIR -u ORCH_STOP_FILE -u ORCH_RUN_LOG -u ORCH_INSTANCE_ID_FILE -u JIRA_TRACKER_STATE)` prepended before the child exec in `run_spawn_cmd()`. Surgical — runner's own env is untouched; `ORCH_ROLE/TICKET/...` are set on assignment prefix and survive.

| Assertion | Result |
|-----------|--------|
| `ABS-355 AC2: seat env does NOT contain live-state var ORCH_STATE_DIR` | ✅ PASS |
| `ABS-355 AC2: seat env does NOT contain live-state var ORCH_STOP_FILE` | ✅ PASS |
| `ABS-355 AC2: seat env does NOT contain live-state var ORCH_RUN_LOG` | ✅ PASS |
| `ABS-355 AC2: seat env does NOT contain live-state var ORCH_INSTANCE_ID_FILE` | ✅ PASS |
| `ABS-355 AC2: seat env does NOT contain live-state var JIRA_TRACKER_STATE` | ✅ PASS |
| `ABS-355 AC2: seat still receives its own ORCH_ROLE (scrub is surgical, not total)` | ✅ PASS |

**AC2 verdict**: ✅ PASS — all 5 hostile vars scrubbed, ORCH_ROLE preserved.

---

### AC3 — State-Dir-Selbstheilung (Runner überlebt State-Dir-Verlust)

**Requirement**: Runner überlebt einen State-Dir-Verlust ohne Operator (Selbstheilung + WARN-Event)

**Implementation**: `heal_state_dir()` called at every `one_cycle` sweep — idempotent no-op on the normal path; on wipe: recreates `ORCH_STATE_DIR/LOCKS_DIR/PACKETS_DIR/SESSIONS_DIR`, re-stamps own instance-id marker, emits `runlog WARN` event. `acquire_lock()` also guards `[ -d "$LOCKS_DIR" ] || mkdir -p` to prevent ENOENT fail-close.

| Assertion | Result |
|-----------|--------|
| `ABS-355 AC3: heal_state_dir recreates the wiped state dir` | ✅ PASS |
| `ABS-355 AC3: self-heal re-stamps OUR instance-id marker (we own it — it was wiped, not taken)` | ✅ PASS |
| `ABS-355 AC3: self-heal emits a WARN event` | ✅ PASS |
| `ABS-355 AC3: acquire_lock recovers after the lock parent is wiped (no ENOENT fail-close)` | ✅ PASS |

**AC3 verdict**: ✅ PASS — self-heal + WARN + acquire_lock ENOENT recovery all green.

---

## Test Tally

```
Total:   14
Passed:  14
Failed:  0

ALL ABS-355 TESTS PASSED
```

---

## DoD Checklist

- [x] All 3 ACs covered by seam tests
- [x] All 14 assertions PASS in the real harness context
- [x] `bash -n` clean on both orchestrator.sh and test file
- [x] No regression introduced (System-Architect isolation proof: `457 passed / 0 failed` identical with/without ABS-355 file)
- [x] Code review APPROVED by System-Architect (commit `232909f`)
- [x] Working tree clean at HEAD `232909f`

---

## Non-blocking Carry-forward Items (from System-Architect review, out of scope for this ticket)

1. **`_bounded_git` watcher fires `kill` unconditionally** — can SIGTERM a plain-statement caller against a hanging remote (safe today as the sole hang-prone call `ls-remote` is subshell-wrapped; ABS-355 does not regress this). File follow-up hardening ticket.
2. **Pre-existing suite death at ABS-295→296 boundary** — aborts `tests/test-orchestrator.sh` (exit 1), drops ~19 late `orchestrator.d` files incl. ABS-355 from CI tally. File separate ticket for `set -e` boundary fix.

---

## Verdict

**✅ APPROVED — All 3 ACs PASS. 14/14 seam assertions green. Evidence validated independently by QAS.**
