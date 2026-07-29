#!/usr/bin/env bash
# =============================================================================
# Sandbox Guard Check (PILOT-46 / ABS-546)
# =============================================================================
# Fails CI if a tests/ entrypoint that TOUCHES the backend or a tracker adapter
# does not source tests/sandbox-guard.sh. The guard strips inherited
# BACKEND_URL / BACKEND_TOKEN / TRACKER_CMD / ORCH_INSTANCE_ID so a seat's test
# fixture cannot write into the PROD backend by inheritance (the leak that
# flooded the Mission Control board twice — see tests/sandbox-guard.sh).
#
# "Touches backend/tracker" is derived MECHANICALLY, the same way rule-ledger-
# check derives its scope: any entrypoint whose text references one of the
# leak-carrying tokens is required to source the guard. run-all.sh (the
# aggregate entrypoint) is always required. This keeps the required set honest
# — a NEW backend-touching test cannot silently skip the guard.
#
# Entrypoints = tests/run-all.sh, tests/scoped-tests.sh, tests/e2e-*.sh and
# tests/test-*.sh. The guard file and this checker are not entrypoints.
#
# Usage:
#   scripts/sandbox-guard-check.sh          # check, exit 0/1
# Fixture override (regression tests): SANDBOX_GUARD_TESTS_DIR (tests dir root).
# Exit 0 = every backend/tracker entrypoint sources the guard.
# Exit 1 = a violation (details on stderr). Exit 2 = setup error.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TESTS_DIR="${SANDBOX_GUARD_TESTS_DIR:-$REPO_ROOT/tests}"
GUARD="$TESTS_DIR/sandbox-guard.sh"

# Tokens whose presence marks an entrypoint as backend/tracker-touching. Kept in
# lockstep with what the guard unsets, plus the adapter/shipper script names.
TOUCH_RE='BACKEND_URL|BACKEND_TOKEN|TRACKER_CMD|ORCH_INSTANCE_ID|backend-tracker|mock-tracker|backend-shipper|shipper'
# Match CODE only, never full-comment lines: a token that appears solely in an
# explanatory comment (e.g. a test that merely NAMES backend-shipper.sh in its
# header) does not touch the backend at runtime, and flagging it is a false RED
# (PILOT-62 — 'shipper' matched in comments of test-fixture-integrity.sh and
# test-signal-trap-hygiene.sh, both of which never read a leak-carrying var).
touches_backend() { grep -vE '^[[:space:]]*#' "$1" | grep -qE "$TOUCH_RE"; }
# A file sources the guard when it names the guard file.
SOURCE_RE='sandbox-guard\.sh'

fail=0
err() { printf 'SANDBOX-GUARD: %s\n' "$1" >&2; fail=1; }

[ -f "$GUARD" ] || { printf 'sandbox-guard-check: missing guard: %s\n' "$GUARD" >&2; exit 2; }

checked=0
for f in "$TESTS_DIR"/run-all.sh "$TESTS_DIR"/scoped-tests.sh \
         "$TESTS_DIR"/e2e-*.sh "$TESTS_DIR"/test-*.sh; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    # The guard and this checker's own regression test are excluded from the
    # "touches backend" rule ONLY as the guard file itself; the test file DOES
    # source the guard and is checked like any other entrypoint.
    [ "$base" = "sandbox-guard.sh" ] && continue

    required=0
    [ "$base" = "run-all.sh" ] && required=1
    if [ "$required" -eq 0 ] && touches_backend "$f"; then
        required=1
    fi
    [ "$required" -eq 1 ] || continue

    checked=$((checked + 1))
    if ! grep -qE "$SOURCE_RE" "$f"; then
        err "tests/$base touches backend/tracker but does not source tests/sandbox-guard.sh"
        err "    add near the top (after 'set -...'):"
        err "    . \"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)/sandbox-guard.sh\""
    fi
done

if [ "$fail" -ne 0 ]; then
    printf '\nsandbox-guard-check: FAIL — a backend/tracker entrypoint does not isolate its env (see above).\n' >&2
    exit 1
fi
printf 'sandbox-guard-check: OK — all %s backend/tracker entrypoints source the guard.\n' "$checked"
exit 0
