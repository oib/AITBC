#!/usr/bin/env bash
# =============================================================================
# Test: sandbox-guard.sh + sandbox-guard-check.sh (PILOT-46 / ABS-546, AC1)
# =============================================================================
# The suite-side mechanical stop against sandbox-env leakage. Asserts:
#   - the guard unsets BACKEND_URL/BACKEND_TOKEN/TRACKER_CMD/ORCH_INSTANCE_ID
#   - ORCH_TEST_ALLOW_BACKEND=1 leaves the env intact (live-conformance mode)
#   - a locally-assigned value AFTER sourcing survives (only inherited stripped)
#   - the CI check passes on the real repo (every backend/tracker entrypoint
#     sources the guard)
#   - the CI check FAILS a fixture entrypoint that touches backend but omits the
#     guard, and always requires run-all.sh
#
# Run from repo root: bash tests/test-sandbox-guard.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$SCRIPT_DIR/sandbox-guard.sh"
CHECK="$REPO_ROOT/scripts/sandbox-guard-check.sh"
# Mirrors TOUCH_RE in sandbox-guard-check.sh — used only to pick a real
# backend-touching entrypoint for the AC3 counter-proof below.
TOUCH_RE_SELFTEST='BACKEND_URL|BACKEND_TOKEN|TRACKER_CMD|ORCH_INSTANCE_ID|backend-tracker|mock-tracker|backend-shipper|shipper'

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { TOTAL=$((TOTAL+1)); PASS=$((PASS+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
bad() { TOTAL=$((TOTAL+1)); FAIL=$((FAIL+1)); echo -e "  ${RED}FAIL${NC} $1"; }
assert_eq()       { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (want '$2' got '$1')"; fi; }
assert_contains() { if echo "$1" | grep -qF -- "$2"; then ok "$3"; else bad "$3 (missing: $2)"; fi; }

echo "== guard strips inherited backend/tracker env =="
res="$(BACKEND_URL=http://prod BACKEND_TOKEN=t TRACKER_CMD=x ORCH_INSTANCE_ID=devops01.local-1-a \
  bash -c ". '$GUARD'; echo \"\${BACKEND_URL:-U} \${BACKEND_TOKEN:-U} \${TRACKER_CMD:-U} \${ORCH_INSTANCE_ID:-U}\"")"
assert_eq "$res" "U U U U" "all four vars unset by default"

echo "== escape hatch keeps env =="
res="$(BACKEND_URL=http://prod ORCH_TEST_ALLOW_BACKEND=1 \
  bash -c ". '$GUARD' 2>/dev/null; echo \"\${BACKEND_URL:-U}\"")"
assert_eq "$res" "http://prod" "ORCH_TEST_ALLOW_BACKEND=1 leaves BACKEND_URL intact"

echo "== locally-assigned value after sourcing survives =="
res="$(BACKEND_URL=http://prod \
  bash -c ". '$GUARD'; export BACKEND_URL=http://localhost:9; echo \"\$BACKEND_URL\"")"
assert_eq "$res" "http://localhost:9" "post-source local assignment survives"

echo "== CI check passes on the real repo =="
out="$(bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "0" "sandbox-guard-check exits 0 on repo"
assert_contains "$out" "OK" "reports OK"

echo "== CI check FAILS a fixture that omits the guard =="
# NOT under work/scratch: that path is gitignored (.gitignore), so it does not
# exist in a fresh clone or worktree. There mktemp fails, FIX ends up EMPTY,
# SANDBOX_GUARD_TESTS_DIR="" falls back to the REAL tests/ dir — and the negative
# cases below then assert against a repo that legitimately passes. The guard's own
# negative test was therefore vacuous exactly where it matters: in a clean checkout.
FIX="$(mktemp -d "${TMPDIR:-/tmp}/sgc-fixture-XXXXXX")"
trap 'rm -rf "$FIX"' EXIT
cp "$GUARD" "$FIX/sandbox-guard.sh"
# run-all.sh is always required — omit the source → must fail.
printf '#!/usr/bin/env bash\nset -e\necho hi\n' > "$FIX/run-all.sh"
# a backend-touching test that omits the guard → must fail.
printf '#!/usr/bin/env bash\nset -e\nexport BACKEND_URL=http://x\n' > "$FIX/test-leaky.sh"
out="$(SANDBOX_GUARD_TESTS_DIR="$FIX" bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "1" "check fails when entrypoints omit the guard"
assert_contains "$out" "run-all.sh" "flags run-all.sh"
assert_contains "$out" "test-leaky.sh" "flags backend-touching test"

echo "== CI check passes once the fixture entrypoints source the guard =="
printf '#!/usr/bin/env bash\nset -e\n. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"\necho hi\n' > "$FIX/run-all.sh"
printf '#!/usr/bin/env bash\nset -e\n. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"\nexport BACKEND_URL=http://x\n' > "$FIX/test-leaky.sh"
out="$(SANDBOX_GUARD_TESTS_DIR="$FIX" bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "0" "check passes once the guard is sourced"

echo "== counter-proof: removing the guard line from a REAL entrypoint turns the check red =="
# PILOT-62 AC3/AC4: the fixture above uses SYNTHETIC files, so it only proves the
# mechanism works when pointed at hand-built input. This proves the SAME check
# catches a REAL backend-touching entrypoint that loses its guard line — i.e. the
# "all N entrypoints OK" message on the real repo is NOT vacuum-green. Hermetic:
# operate on a COPY of the real tests dir; the working tree is never mutated.
REAL="$(mktemp -d "${TMPDIR:-/tmp}/sgc-real-XXXXXX")"
trap 'rm -rf "$FIX" "$REAL"' EXIT
cp "$SCRIPT_DIR"/*.sh "$REAL"/ 2>/dev/null
# baseline: an unmutated copy of the real tests dir must pass, so any redness
# below is attributable to the removed line, not to a pre-existing gap.
out="$(SANDBOX_GUARD_TESTS_DIR="$REAL" bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "0" "unmutated copy of the real tests dir passes"
# pick a real entrypoint that touches backend/tracker AND currently sources the guard.
victim=""
for f in "$REAL"/test-*.sh; do
  b="$(basename "$f")"
  if grep -qE "$TOUCH_RE_SELFTEST" "$f" && grep -qE 'sandbox-guard\.sh' "$f"; then victim="$b"; break; fi
done
if [ -z "$victim" ]; then
  bad "found no real backend-touching entrypoint that sources the guard to mutate"
else
  grep -v 'sandbox-guard\.sh' "$REAL/$victim" > "$REAL/$victim.tmp" && mv "$REAL/$victim.tmp" "$REAL/$victim"
  out="$(SANDBOX_GUARD_TESTS_DIR="$REAL" bash "$CHECK" 2>&1)"; rc=$?
  assert_eq "$rc" "1" "removing the guard line from real entrypoint $victim turns the check red"
  assert_contains "$out" "$victim" "check names the real entrypoint $victim"
fi

echo ""
echo "sandbox-guard: $PASS/$TOTAL passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
