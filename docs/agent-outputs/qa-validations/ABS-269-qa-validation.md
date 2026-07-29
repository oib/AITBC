# QA Validation Report — ABS-269

**Ticket**: ABS-269 — Stack-Applicability-Guard: unresolvable profile fails CLOSED (generic-only)
**Branch**: `ABS-269-auto`
**Commit**: `750d2ae`
**QAS Run**: 2026-07-14
**Validator**: qas (independent)

---

## Test Suite Results

| Suite | Result | Count |
|---|---|---|
| `tests/test-pattern-applicability.sh` | ✅ PASS | 37/37 |
| `tests/test-profile-activation.sh` | ✅ PASS | 17/17 |
| `tests/test-evolver-lifecycle.sh` | ✅ PASS | PASS |
| `tests/test-harness-parity.sh` | ✅ PASS | 6/6 |

**shellcheck**: Clean on changed files. Only SC1091 (info-level) on pre-existing `source` line in `pattern-applicability.sh` — untouched by this PR, pre-existing finding noted by developer and confirmed by system architect.

---

## AC-by-AC Verification (Independent)

### AC1 — Unresolvable profile → generic-only, not the full library

**Command run**:
```bash
ACTIVE_PROFILE=does-not-exist bash scripts/pattern-applicability.sh 2>/dev/null | wc -l
# → 10 (generic patterns only)
ACTIVE_PROFILE=does-not-exist bash scripts/pattern-applicability.sh 2>/dev/null | grep -E "^(api|ui|database)/"
# → (empty — no stack-specific patterns)
ACTIVE_PROFILE=fastapi bash scripts/pattern-applicability.sh 2>/dev/null | wc -l
# → 10 (same result for PO's original repro profile name)
```
**Result**: ✅ PASS — 10 generic patterns returned, 0 stack-specific (`api/`, `ui/`, `database/`) patterns.

---

### AC2 — Deliberate asymmetry intact

**Commands run**:
```bash
# absent key (neutral) → still unfiltered
ACTIVE_PROFILE=neutral bash scripts/pattern-applicability.sh 2>/dev/null | wc -l
# → 24 ✅

# stack: [] → generic-only
PROFILES_DIR=<tmpdir/profiles> ACTIVE_PROFILE=empty-stack bash scripts/pattern-applicability.sh 2>/dev/null | wc -l
# → 10 ✅
```
**Result**: ✅ PASS — `neutral` (no `stack:` key) still returns 24 patterns; empty stack still returns 10.

---

### AC3 — WARN on stderr names profile, searched path, and fail-closed behavior

**Command run**:
```bash
ACTIVE_PROFILE=fastapi bash scripts/pattern-applicability.sh 2>&1 >/dev/null
# → pattern-applicability.sh: WARN profile 'fastapi' not found under .../profiles;
#    FAIL-CLOSED: serving generic patterns only (fix .active-profile or run scripts/profile.sh set <name>)
```
Checked: profile name `fastapi` ✅ | searched path (`profiles` dir) ✅ | `FAIL-CLOSED` behavior ✅ | remedy hint ✅

**Result**: ✅ PASS — all required diagnostic elements present.

---

### AC4 — Both capability providers verified, no hard break

**evolver-lifecycle.sh**:
```bash
ACTIVE_PROFILE=does-not-exist bash scripts/hooks/evolver-lifecycle.sh 2>/dev/null; echo "Exit code: $?"
# → Exit code: 0
```
**pattern-applicability.sh exit 0**:
```bash
ACTIVE_PROFILE=does-not-exist bash scripts/pattern-applicability.sh >/dev/null 2>&1; echo $?
# → 0
```
Test suite additionally covers `get_capability_provider` on unresolvable profile → resolves as `neutral`.

**Result**: ✅ PASS — neither provider hard-breaks; both exit 0.

---

### AC5 — #PATH_DECISION documented in spec

`specs/ABS-269-stack-applicability-fail-closed-spec.md` contains a full `## #PATH_DECISION` section that documents:
- **Chosen**: fail-closed to `generic`, exit stays 0
- **Rejected**: additional exit ≠ 0 (reason: would break consuming seat, WARN already sufficient)
- Both alternatives addressed with rationale.

**Result**: ✅ PASS — PATH_DECISION present, both variants documented.

---

### AC6 — Pre-existing ABS-257 tests remain green

All 22 pre-existing ABS-257 assertions ran and passed inside the 37-count run. The test file header sections `ABS-257: Stack-Applicability-Guard`, `AC1–AC3`, `Back-compat`, `--all` all PASS.

**Result**: ✅ PASS — zero regression on ABS-257 test coverage.

---

## System Architect MEDIUM Finding

The system architect identified (non-blocking) that `get_requested_profile()` returns `neutral` as the default when **nothing** is declared (not just for a *declared* unresolvable name). This means an undeclared project with a missing `profiles/` directory also fails closed (24 → 10 patterns).

**QAS assessment**: Direction is safe — a missing `profiles/` dir *is* a misconfiguration, and the ticket's headline principle explicitly states "eine Fehlkonfiguration muss zu maximalem Schutz führen". The spec's `#PATH_DECISION` rationale is slightly narrower than the implementation. The system architect's recommendation to tighten the spec wording (trigger is *any* unresolvable profile candidate, including the default) is noted here and passed to the Docs station.

This finding does **not** block approval.

---

## Files Changed

- `scripts/lib/profile.sh` — added `get_requested_profile()` + `profile_is_resolvable()`; refactored `get_active_profile()` onto those two
- `scripts/pattern-applicability.sh` — uses new seam to fail-closed on unresolvable profile (ONLY consumer changed)
- `tests/test-pattern-applicability.sh` — 15 new ABS-269 assertions (37 total, 22 pre-existing ABS-257)
- `specs/ABS-269-stack-applicability-fail-closed-spec.md` — new spec with #PATH_DECISION
- `patterns_library/README.md` — minor update

---

## Verdict

**✅ APPROVED**

All six acceptance criteria met. Independent test runs confirm:
- 37/37 test-pattern-applicability (including 22 pre-existing ABS-257 assertions)
- 17/17 test-profile-activation
- test-evolver-lifecycle PASS
- test-harness-parity PASS

No `design` flag on this ticket. Transition target: `Story Acceptance`.

**Iteration**: 0 (first-pass approval, no bounces).
