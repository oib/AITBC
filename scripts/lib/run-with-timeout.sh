#!/usr/bin/env bash
# =============================================================================
# run_with_timeout — portable per-suite wall-clock timeout (PILOT-60 / ABS-573)
# -----------------------------------------------------------------------------
# The release gate (scripts/pre-release-check.sh) and the parallel test runner
# (tests/run-all.sh) must never hang unbounded on a single wedged suite. A
# SIGTERM-swallowing shipper child once hung the release check for an HOUR
# (PILOT-60): the check has carried the warning "no timeout/gtimeout found —
# running suites without a per-suite timeout" for months, so a hanging suite
# hung the WHOLE gate instead of failing by name.
#
# `timeout(1)`/`gtimeout(1)` are GNU coreutils and absent on stock macOS — the
# release host — so this is a bash-native watchdog with the SAME contract:
#
#   run_with_timeout <secs> <cmd> [args...]
#     -> runs cmd; returns cmd's exit code, or 124 when it exceeds <secs>
#        (124 == GNU timeout's timeout code, so callers name the overrun).
#        On timeout the WHOLE process tree of cmd is TERM'd, then KILL'd after a
#        short grace — no survivor is left behind (the incident's exact failure:
#        a live child outliving its killed parent).
#
# Reuses the proven shape of orchestrator.sh:_bounded_git (ABS-355/ABS-371): the
# watcher runs in its own subshell, signals only pids WE started (ABS-243
# kill-scope: pgrep -P walks children of a pid we own, never a name/pattern), and
# is fully wait-reaped the instant cmd returns so no delayed kill outlives the
# call.
# =============================================================================

# _rwt_kill_tree <pid> <signal> — signal a pid and all its descendants, deepest
# first. Uses only `pgrep -P` (children of a pid we started) — never a
# name/pattern kill (ABS-243/ABS-244).
_rwt_kill_tree() {
    local _pid="$1" _sig="$2" _child
    for _child in $(pgrep -P "$_pid" 2>/dev/null); do
        _rwt_kill_tree "$_child" "$_sig"
    done
    kill "-$_sig" "$_pid" 2>/dev/null || true
}

# run_with_timeout <secs> <cmd...> — see header contract.
run_with_timeout() {
    local _secs="$1"; shift
    # Prefer real timeout(1)/gtimeout: they bound + kill in their OWN child
    # process group, the strongest isolation. -k 5: hard-KILL if TERM at the
    # deadline is ignored. Both return 124 on timeout — same as the fallback.
    if command -v timeout >/dev/null 2>&1; then
        timeout -k 5 "$_secs" "$@"; return $?
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout -k 5 "$_secs" "$@"; return $?
    fi

    # Portable fallback (stock macOS has neither): sleep-then-kill watcher in its
    # own subshell, tree-killing so a wedged child of cmd cannot survive.
    "$@" &
    local _pid=$!
    # A unique-per-call marker the watcher creates ONLY when it fires (its
    # presence == "we timed out"). No pre-created temp file, no race.
    local _fired="${TMPDIR:-/tmp}/rwt-$$-${RANDOM}.fired"
    (
        sleep "$_secs"
        : > "$_fired"
        _rwt_kill_tree "$_pid" TERM
        sleep 5
        _rwt_kill_tree "$_pid" KILL
    ) &
    local _wpid=$!
    local _rc=0
    wait "$_pid" 2>/dev/null || _rc=$?
    # Cancel + reap the watcher the instant cmd returns (tree-kill so its own
    # `sleep` child dies too — no orphaned sleep, no delayed kill outliving us).
    _rwt_kill_tree "$_wpid" TERM
    wait "$_wpid" 2>/dev/null || true
    if [ -f "$_fired" ]; then _rc=124; rm -f "$_fired"; fi
    return "$_rc"
}
