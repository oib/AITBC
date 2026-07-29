# =============================================================================
# ABS-371 — _bounded_git must never SIGTERM its caller
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (shared assert helpers / counters).
#
# _bounded_git (scripts/orchestrator.sh, arrived with ABS-355) bounds a git
# remote probe with a portable sleep-then-kill watcher when timeout(1)/gtimeout
# is absent (stock macOS). The latent trap: a plain-statement invocation against
# a still-hanging remote could let the watcher's signal / a reused pid reach the
# CALLER shell (exit 143). This asserts the hardened contract:
#   AC1 — plain-statement call vs a blackhole remote: caller survives, rc is a
#         plain non-zero (NOT a raw 143 signal), bounded within the deadline.
#   AC2 — a call that returns BEFORE the deadline fires no stray watcher signal
#         at a later, unrelated statement in the same shell.
# All checks run offline against a non-routable address (10.255.255.1) — no live
# remote, no credentials.
# =============================================================================
echo -e "\n${CYAN}ABS-371 — _bounded_git caller-safety (plain-statement watcher hardening)${NC}"

_abs371_out="$(bash -c '
    set -e
    source "$1" >/dev/null 2>&1
    repo="$(mktemp -d)"
    git -C "$repo" init -q 2>/dev/null
    # Blackhole HTTPS remote: connect neither completes nor RSTs → would hang
    # unboundedly without the wall-clock ceiling (the ABS-355 raison-dêtre).
    git -C "$repo" remote add bh "https://10.255.255.1/x.git" 2>/dev/null

    # AC1 — PLAIN STATEMENT (not $(...)) against the hanging remote, bounded to 3s.
    # Guard with || so we can read rc; the point is the caller SHELL keeps running.
    _t0=$(date +%s)
    _rc=0; _bounded_git 3 "$repo" ls-remote --heads bh main >/dev/null 2>&1 || _rc=$?
    _elapsed=$(( $(date +%s) - _t0 ))
    echo "PLAIN_RC=$_rc"
    echo "PLAIN_ELAPSED=$_elapsed"
    echo "CALLER_ALIVE_AFTER_PLAIN=yes"

    # AC2 — a call that RETURNS before its deadline must leave no armed watcher.
    # Fast local op with a 1s bound; then sleep PAST that 1s deadline. If a stray
    # watcher were still queued it would fire ~1s in and could signal this shell —
    # reaching the final sentinel proves it was cancelled + reaped.
    _bounded_git 1 "$repo" rev-parse --git-dir >/dev/null 2>&1 || true
    sleep 2
    echo "NO_STRAY_SIGNAL=yes"
' _ "$ORCH" 2>&1)"

# AC1: the calling shell survived the plain-statement bound (no SIGTERM/SIGKILL).
assert_contains "$_abs371_out" "CALLER_ALIVE_AFTER_PLAIN=yes" \
    "ABS-371 AC1: caller shell survives a plain-statement _bounded_git vs a hanging remote"

# AC1: the returned rc is a plain non-zero, NOT a propagated 143 (128+SIGTERM).
_abs371_plain_rc="$(printf '%s\n' "$_abs371_out" | sed -n 's/^PLAIN_RC=//p' | head -1)"
assert_eq "${_abs371_plain_rc:-unset}" "124" \
    "ABS-371 AC1: bounded probe returns a normalised non-zero (124), not a raw signal 143"

# AC1: the probe was actually bounded (< a generous 10s, deadline was 3s).
_abs371_elapsed="$(printf '%s\n' "$_abs371_out" | sed -n 's/^PLAIN_ELAPSED=//p' | head -1)"
if [ -n "$_abs371_elapsed" ] && [ "$_abs371_elapsed" -lt 10 ]; then
    echo -e "  ${GREEN}PASS${NC} ABS-371 AC1: blackhole probe returned within the wall-clock bound (${_abs371_elapsed}s)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-371 AC1: probe not bounded (elapsed='${_abs371_elapsed}')"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# AC2: a before-deadline return leaves no stray watcher to signal a later statement.
assert_contains "$_abs371_out" "NO_STRAY_SIGNAL=yes" \
    "ABS-371 AC2: no stray watcher signal after a call that returns before its deadline"

unset _abs371_out _abs371_plain_rc _abs371_elapsed
