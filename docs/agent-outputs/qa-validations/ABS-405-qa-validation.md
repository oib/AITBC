# QA Validation Report — ABS-405

**Ticket**: ABS-405 — abort-spawn identity binding: add process cmdline as second identity factor (close same-second start-time recycle residual)
**Branch**: `ABS-405-auto`
**Commit**: `5842297` (`feat(shipper): add cmdline as second abort-spawn identity factor [ABS-405]`)
**Date**: 2026-07-17
**QAS Actor**: qas (In Test gate)
**Flags**: `security` (no `design` flag)

---

## Pre-flight Checks

| Check | Result |
|-------|--------|
| `bash -n scripts/backend-shipper.sh` | ✅ PASS |
| `bash -n tests/test-shipper-commands.sh` | ✅ PASS |
| `shellcheck -S warning scripts/backend-shipper.sh` | ✅ PASS |
| Commit diff scope (scripts/backend-shipper.sh + tests/ only) | ✅ PASS |
| `scripts/orchestrator.sh` untouched by ABS-405 commit | ✅ PASS (AC6 diff gate) |

---

## Test Suite Execution (Independent QAS run)

```
bash tests/test-shipper-commands.sh
```

**Result: 42/42 PASS** (run independently by QAS in worktree `tmp/ABS-405-work` @ `5842297`)

Key test sections exercised:
- `I1` — both identity factors present in ledger entry (start-time + cmdline)
- `I3` — same-second recycle: start-time matches, cmdline differs → refuse (no signal)
- `I4` — portability: `ps -o lstart= -o command=` on host OS
- `I5(empty)` — absent token → refuse (no signal)
- `I5(partial)` — one-factor-only token → refuse (no signal)
- `I2` — recycled/mismatched identity PID → refuse (ABS-387 regression)
- `AC2` — full match (both factors) → signal sent (positive case)
- `AC5` — idempotency: already-executed abort does NOT re-signal
- All ABS-387/354/388 regression assertions → unchanged and passing

---

## Acceptance Criteria Verification

### AC1 — `pid_identity()` captures BOTH start-time and cmdline, combined into one token; test asserts ledger entry carries both factors
- **Implementation**: `pid_identity()` calls `ps -o lstart= -o command= -p "$1"` in ONE `ps` invocation, piped through `tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//'` — same normalisation as ABS-387's single-factor token.
- **Test evidence**: I1 PASS — "identity token carries the start-time factor" + "identity token carries the cmdline factor (ABS-405)"
- **Status**: ✅ PASS

### AC2 — `abort-spawn` refuses to signal when EITHER identity factor mismatches; test asserts refusal when cmdline differs but start-time matches (same-second recycle simulation)
- **Implementation**: `exec_abort_spawn` compares `recorded_identity` vs `live_identity` byte-for-byte; `[ -z "$recorded_identity" ] || [ "$recorded_identity" != "$live_identity" ]` routes to `refuse_abort` (no signal, `failed` receipt, stderr log). Since both factors are baked into one token, ANY mismatch triggers refusal.
- **Test evidence**: I3 PASS — "same-second target is alive before abort", "cmdline factor differs → target NOT signalled (survives)", "failed receipt on same-second cmdline mismatch", "failure reason names the identity mismatch", "refusal logged to stderr"
- **Status**: ✅ PASS

### AC3 — `abort-spawn` signals only when BOTH factors match; test asserts signal on full match
- **Implementation**: Signal (`kill -"$SHIPPER_ABORT_SIGNAL" "$pid"`) is only reached after the full byte-for-byte identity comparison passes (and `kill -0` liveness check passes).
- **Test evidence**: AC2 section PASS — "matched identity → target process was signalled (no longer running)" + "abort receipt state=executed"
- **Status**: ✅ PASS

### AC4 — Absent/partial token still refuses (fail-safe, #EXPORT_CRITICAL)
- **Implementation**: `[ -z "$recorded_identity" ]` catches the empty-token case; one-factor-only tokens produce a different byte string than the two-factor live token → caught by `[ "$recorded_identity" != "$live_identity" ]`.
- **Test evidence**: I5(empty) PASS — "absent identity token → live target NOT signalled" + "failed receipt on absent token"; I5(partial) PASS — "one-factor-only token → live target NOT signalled" + "failed receipt on one-factor-only token"
- **Status**: ✅ PASS

### AC5 — Identity capture and comparison remain portable across macOS + Linux
- **Implementation**: `ps -o lstart=` and `ps -o command=` accepted by BSD/macOS `ps` and Linux procps `ps`. Comparison is same-host, so cross-platform format differences are irrelevant.
- **Test evidence**: I4 PASS — "identity token captured on the host OS (ps -o lstart= -o command=)"
- **Status**: ✅ PASS

### AC6 — No regression to ABS-387 / ABS-354 behaviour; `tests/test-shipper-commands.sh` (prior 24/24 → now 42/42) still passes; `orchestrator.sh` untouched
- **Implementation**: `orchestrator.sh` not touched by commit `5842297` (`git show --stat` confirms 2 files: `scripts/backend-shipper.sh` + `tests/test-shipper-commands.sh` only). ABS-387/354/388 regression assertions are in the test suite and all pass.
- **Test evidence**: 42/42 PASS (includes all prior assertions); AC1 diff gate PASS — "scripts/orchestrator.sh unchanged"
- **Status**: ✅ PASS

---

## Security / #EXPORT_CRITICAL Review Notes

The security-engineer (origin of this follow-up from ABS-387) independently validated this story at the Security Review gate. Key findings confirmed by QAS:

- **No injection**: identity tokens are never `eval`'d — only quoted string comparisons.
- **TAB/newline collapse**: `tr -s '[:space:]' ' '` collapses TAB and newline to space, so an adversarial cmdline cannot inject a TAB (field separator) into TAB-separated ledger field 5 — `awk -F'\t' '{print $5}'` stays intact.
- **Fail-safe preserved**: refusal fires on ANY doubt (either factor mismatch OR absent token) via the unchanged `refuse_abort` path. Direction is never "signal on doubt."
- **Recycle window closed**: the ~1s same-second start-time-granularity residual is now closed by the cmdline second factor.

---

## Non-Blocking Carry-Forward (inherited, no new follow-up)

The **producer/consumer token-FORMAT contract** (external ABS-348 ledger producer must emit field 5 with the exact `ps -o lstart= -o command= | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//'` derivation) is already documented in:
- be-developer `gate-results` comment (ABS-348-directed)
- system-architect non-blocking carry-forward
- security-engineer no-new-follow-up note

This is fail-safe-but-inert on divergence (every abort refuses, no wrong-process signal). It is NOT a QAS gate blocker. Must be confirmed with the backend producer team before a live run.

---

## Verdict

**✅ APPROVED — QAS PASS**

All 6 acceptance criteria met. 42/42 tests pass (independent QAS run). `bash -n` clean, `shellcheck -S warning` clean, `orchestrator.sh` untouched. Fail-safe `#EXPORT_CRITICAL` invariant preserved and strengthened. No regression.

**Flags**: `security` set, `design` NOT set → exit transition to `Story Acceptance`.

