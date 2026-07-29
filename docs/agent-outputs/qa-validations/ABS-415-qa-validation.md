# QA Validation Report — ABS-415

**Ticket**: ABS-415 — Harden ABS-205/ABS-393 seat-classification seam: mktemp -d throwaway base + trailing-slash path normalization  
**Branch**: `ABS-415-auto`  
**Commit**: `479ee16`  
**Validator**: qas  
**Date**: 2026-07-18  
**Verdict**: ✅ APPROVED

---

## Files Changed

| File | Nature |
|------|--------|
| `scripts/orchestrator.sh` | Seam hardening (lines ~460–495): mktemp -d + trailing-slash normalization |
| `tests/orchestrator.d/ABS-393-main-checkout-state-isolation.sh` | Regression include extended with ABS-415 block |

Total changed code lines: 16 (3 code + 13 comments). Minimal diff — no drive-by refactors.

---

## Acceptance Criteria Verification

### AC1 — mktemp -d throwaway base (atomic, mode-700) ✅

**Criterion**: The main-checkout seat's throwaway state base is created with `mktemp -d` (atomic, mode-700) instead of the guessable `$$-$RANDOM` interpolation. `ORCH_SEAT_STATE_ROOT` test override still takes precedence.

**Evidence**:
- Code: `_orch_seat_statedir_base="${ORCH_SEAT_STATE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/orch-seat-state-$$-XXXXXX")}"`
- `${VAR:-default}` lazy-eval: mktemp is NOT invoked when `ORCH_SEAT_STATE_ROOT` is set
- Independently verified: `mktemp -d` on this platform creates `drwx------` (mode-700), atomic, unpredictable 6-char suffix
- Command output: `drwx------@ 2 sahan staff 64 Jul 18 13:59 /var/folders/.../orch-seat-state-32682-OCtblz`

**PASS**

---

### AC2 — Trailing-slash normalization on both classification operands ✅

**Criterion**: `REPO_ROOT` and `ORCH_PARENT_STATE_ROOT` normalized (trailing slash stripped) before seat-classification equality compare, so a trailing-slash `ORCH_TARGET_REPO` no longer misclassifies a main-checkout seat.

**Evidence**:
- First compare: `[ "${_orch_computed_state_root%/}" = "${ORCH_PARENT_STATE_ROOT%/}" ]`
- Second compare: `[ "${REPO_ROOT%/}" != "${ORCH_PARENT_STATE_ROOT%/}" ]`
- `ORCH_STATE_ROOT` assignments use raw (un-normalized) values — `git -C "$ORCH_STATE_ROOT"` paths stay correct
- Both operands normalized in both relevant comparisons

**PASS**

---

### AC3 — Explicit `ORCH_STATE_DIR`/`STOP_FILE` precedence preserved; top-level runner untouched ✅

**Criterion**: Explicit `ORCH_STATE_DIR`/`STOP_FILE` still win; top-level runner (no `ORCH_PARENT_STATE_ROOT`) unchanged; full `tests/test-orchestrator.sh` green.

**Evidence**:
- `ORCH_STATE_DIR="${ORCH_STATE_DIR:-$_orch_statedir_base/work/.orchestrator}"` — byte-identical (only line number shifted by +10)
- `ORCH_STOP_FILE="${ORCH_STOP_FILE:-$_orch_statedir_base/work/.orchestrator-stop}"` — byte-identical
- Outer `else` block (no `ORCH_PARENT_STATE_ROOT`): `ORCH_STATE_ROOT="$_orch_computed_state_root"` — untouched
- Full test suite: **1208/1208 PASS** (exit code 0, independently run by this reviewer)

**PASS**

---

### AC4 — Regression test extended ✅

**Criterion**: `tests/orchestrator.d/ABS-393-main-checkout-state-isolation.sh` extended with: (a) trailing-slash `ORCH_TARGET_REPO` still classifies as main-checkout + redirects state off live dir; (b) throwaway base is a real `mktemp -d` directory.

**Evidence** — 3 new assertions confirmed in file:
1. `assert_not_contains "$_ABS415_SD" "$_ABS415_LIVE/work/.orchestrator"` — redirected OFF live dir with trailing slash
2. `assert_eq "$([ -f "$_ABS415_LEDGER" ] && echo yes || echo no)" "yes"` — live ledger survives seat cleanup trap
3. `assert_contains "$_ABS415_OUT" "BASE_IS_DIR=yes"` — throwaway base is a real on-disk `mktemp -d` directory

Test logic verified: without the fix, `"$_ABS415_LIVE/"` ≠ `"$_ABS415_LIVE"` → misclassify as worktree seat → AC4(a) would FAIL, confirming the test is discriminating.

**PASS**

---

### AC5 — `bash -n scripts/orchestrator.sh` clean ✅

**Criterion**: No syntax errors in either changed file.

**Evidence**:
```
$ bash -n scripts/orchestrator.sh && echo "CLEAN"
CLEAN

$ bash -n tests/orchestrator.d/ABS-393-main-checkout-state-isolation.sh && echo "CLEAN"
CLEAN
```

**PASS**

---

## Full Test Suite Results

```
=== Test Results (aggregated over 4 shards) ===

  Total:  1208
  Passed: 1208
  Failed: 0

  ALL TESTS PASSED
```

Exit code: 0. Independently re-run by this reviewer.

---

## Security Flag Verification

- Security Review gate: PASSED (2026-07-18T11:37:54Z, security-engineer)
- Finding: `[positive | TOCTOU/symlink]` — `mktemp -d` closes the pre-create/symlink redirect vector
- `[low | correctness]` double-trailing-slash edge filed as non-blocking follow-up (out of scope for ABS-415)
- RLS/authz/migrations: N/A (pure shell)

---

## Out-of-Scope Verification

Confirmed byte-identical (no regression):
- ABS-393 redirect behaviour
- AC3 forensic self-heal path
- AC4 ledger rebuild path  
- Explicit `ORCH_STATE_DIR`/`STOP_FILE` pinned tests
- Top-level runner (no `ORCH_PARENT_STATE_ROOT`)

---

## Verdict

**✅ APPROVED — All 5 ACs met, 1208/1208 tests pass, security flag cleared.**

No `design` flag on ticket → transition to **Story Acceptance**.
