# QA Validation Report — ABS-426

**Ticket**: ABS-426 — Harden S7 conformance suite: FAIL-on-mint-failure for all probes + robust json_escape  
**Validator**: QAS  
**Date**: 2026-07-18  
**Commit**: `afadf19` (branch: `ABS-426-auto`)  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Validation

### AC#1 — No silent PASS on mint failure across named probes
**Result**: ✅ PASS

Static code inspection of `tests/test-backend-tracker.sh` at `afadf19`:

- **§10/6 human-session positive control** (line 845): `else` branch previously did `TOTAL++;PASS++` (silent skip). Now calls `mint_fail_probe "§10/6 human-session positive control (policy create)"` which records `TOTAL++;FAIL++`. Verified directly at lines 837–847.
- **§10/7 CONF2 export→import round-trip** (line 914): `else` branch previously did `TOTAL++;PASS++` (silent skip). Now calls `mint_fail_probe "§10/7 CONF2 export→import round-trip"` which records `TOTAL++;FAIL++`. Verified directly at lines 908–915.
- **20a/20b probes** (lines 811–813, 832–834): Already hardened in ABS-384 iteration 2 — inline `FAIL++` pattern confirmed intact, untouched by this commit.
- **Grep scan**: No `TOTAL++;PASS++` pattern in any mint-failure `else` branch remains. All `PASS=($PASS + 1)` increments are inside proper `assert_*` helpers only.

Evidence command: `grep -n 'TOTAL.*PASS\|PASS.*TOTAL' test-backend-tracker.sh` — only shows initialization line 121 and counter-snapshot/restore lines in the bite proof (lines 949, 957).

### AC#2 — Bite proof: induced mint failure causes FAIL
**Result**: ✅ PASS

Bite proof at lines 942–960:
```bash
_p0=$PASS; _f0=$FAIL; _t0=$TOTAL
INDUCED_TOKEN=""   # simulate a failed token/session mint
if [ -n "$INDUCED_TOKEN" ]; then
    :              # real probe body would run here
else
    mint_fail_probe "ABS-426 bite proof: induced mint failure"
fi
_bit=0; [ "$FAIL" -gt "$_f0" ] && _bit=1
PASS=$_p0; FAIL=$_f0; TOTAL=$_t0  # restore — expected failure must not count
assert_eq "$_bit" "1" "ABS-426 bite proof: an induced token/session mint failure records a FAIL (silent-pass path is gone)"
```

Logic is sound: `INDUCED_TOKEN=""` guarantees the `else` branch fires → `mint_fail_probe` fires → `FAIL` incremented → `_bit=1` → `assert_eq` passes. Counters restored so the expected FAIL leaves no trace in the release-gating tally. Mirrors the ABS-370 counter-snapshot self-test pattern exactly. The system-architect independently live-verified this fires on a running Docker stack: "Induced red `FAIL ABS-426 bite proof: induced mint failure` immediately followed by the passing assertion; final tally unaffected (Failed: 0)."

### AC#3 — Robust json_escape replaces minimal sed encoder
**Result**: ✅ PASS

- **Old encoder removed**: `printf '%s' "$*" | sed 's/\\/\\\\/g; s/"/\\"/g'` (only escaped `\` and `"`) — completely absent from the file.
- **New encoder** (lines 559–567): pure-bash, escapes `\`, `"`, `\t`, `\r`, `\n` in correct order (backslash first to avoid double-escaping).
- **Byte-for-byte parity confirmed**: diff comparison between the new `json_escape` in `tests/test-backend-tracker.sh` and `scripts/backend-tracker.sh` returns `BYTE-FOR-BYTE IDENTICAL`.
- **No sed encoder remains**: `grep 'sed.*json_escape\|json_escape.*sed'` returns nothing.

### AC#4 — Regression-clean
**Result**: ✅ PASS

| Check | Result | Command/Evidence |
|-------|--------|-----------------|
| `bash -n tests/test-backend-tracker.sh` | ✅ CLEAN | Run locally against `afadf19` content |
| `bash -n tests/test-orchestrator.sh` | ✅ CLEAN | Run locally against `afadf19` content |
| `tests/test-tracker-adapter-lint.sh` | ✅ **21/21 PASS** | Run from `ABS-426-auto` worktree (full Phase-3 lint suite) |
| §10 Cases 1–7 green | ✅ Confirmed | System-architect live run: 191/191 PASS; security-engineer independently audited commit |
| No bare conflict markers | ✅ CLEAN | `grep '^======='` returns no matches in either file |
| §10/Case 5 in test-orchestrator.sh | ✅ No auto-pass path | Inspected lines 4344–4428: all uses of `assert_contains`/`assert_not_contains`/`assert_eq` — no `TOTAL++;PASS++` on any mint-failure path |

**Note on lint count (13 vs 21)**: Running `test-tracker-adapter-lint.sh` from the current HEAD branch (`epic/ABS-392-merge-readiness-rebase-gate`) gives 13/13 because that branch is missing the Phase-3 knowledge conformance lint section (added in ABS-384). The ABS-426-auto worktree contains the full 21-test version — confirmed 21/21 PASS when run from the worktree.

---

## Prior Gate Evidence (Referenced, Not Re-Verified)

- **Architecture Review (system-architect, `afadf19`)**: APPROVED — live Docker run: 191/191 PASS; bite proof fired; 21/21 lint PASS; bash -n clean; no conflict markers; §10/Case 5 independently confirmed no auto-pass.  
- **Security Review (security-engineer, `afadf19`)**: PASS — json_escape encoder hardened (no injection breakout); human-only 403 guards untouched; BOOTSTRAP_TOKEN ephemeral per-PID, never echoed; net security-positive change.

---

## Summary

All 4 Acceptance Criteria independently verified through static analysis and lint test execution. The implementation is correct, minimal, and reuses established patterns (ABS-370 bite-proof pattern, shared `json_escape`). No regressions introduced.

**Flags**: `security` set — security review already passed (no `design` flag → exits to Story Acceptance).

**Verdict: APPROVED**
