# =============================================================================
# ABS-246 consumer-feedback quick fixes — drain_pending IFS + stat portability
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_eq, PASS/FAIL/TOTAL, REPO_ROOT / ORCH.
#
# Consumer Befund (Buschenschankkalender, BUSCH-58): drain_pending dispatched
# under a leaked newline-only IFS, so depends_unmet saw a multi-ticket
# depends_on list as ONE token and parked the ticket as ':unreadable' forever.
# Second Befund: BSD-first `stat -f %m` on GNU coreutils SUCCEEDS as a
# filesystem query (prints text), feeding non-numeric input into arithmetic.
# =============================================================================

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}ABS-246 Part A — drain_pending restores IFS before dispatch${NC}"
# -----------------------------------------------------------------------------
# Source the orchestrator in a subshell, stub dispatch() to record the IFS it
# runs under (default bash IFS = space+tab+newline = length 3; the leaked
# newline-only IFS of the bug = length 1) plus its argv.
_abs246_drain() {
    bash -c '
        source "$1" >/dev/null 2>&1
        dispatch() { printf "DISPATCHED=%s|%s|%s IFSLEN=%s\n" "$1" "$2" "$3" "${#IFS}"; return 0; }
        pending_add() { :; }
        BUDGET_HALT=0
        PENDING="[T-1|Ready for Development|] [T-2|Design|Backlog]"
        drain_pending
    ' _abs246 "$ORCH" 2>/dev/null
}
_abs246_out="$(_abs246_drain)"
assert_contains "$_abs246_out" "DISPATCHED=T-1|Ready for Development| IFSLEN=3" \
    "ABS-246 AC1: first drained entry dispatches under the DEFAULT ambient IFS"
assert_contains "$_abs246_out" "DISPATCHED=T-2|Design|Backlog IFSLEN=3" \
    "ABS-246 AC1: second drained entry parses (ticket|to|from) and dispatches under default IFS"
assert_eq "$(printf '%s\n' "$_abs246_out" | grep -c DISPATCHED)" "2" \
    "ABS-246 AC1: both pending entries are drained (newline split still works)"

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-246 Part B — stat numeric guard (GNU-first, text-proof)${NC}"
# -----------------------------------------------------------------------------
# PATH-shim `stat` that always prints a mount point ("/"), emulating GNU
# coreutils answering the BSD spelling `stat -f %m` as a filesystem query.
_abs246_tmp="$(mktemp -d)"
cat > "$_abs246_tmp/stat" <<'SHIM'
#!/usr/bin/env bash
echo "/"
SHIM
chmod +x "$_abs246_tmp/stat"

# lock_age_for: non-numeric mtime must sanitize to "now" (age 0..5), never an
# arithmetic crash (the consumer runner died with 'unbound variable' here).
_abs246_age="$(bash -c '
    shim="$1"; orch="$2"
    source "$orch" >/dev/null 2>&1
    LOCKS_DIR="$(mktemp -d)"; mkdir -p "$LOCKS_DIR/T-9"
    PATH="$shim:$PATH" lock_age_for T-9
' _abs246 "$_abs246_tmp" "$ORCH" 2>/dev/null)"
case "$_abs246_age" in
    ''|*[!0-9]*) assert_eq "$_abs246_age" "0-5" \
        "ABS-246 AC2: lock_age_for survives text-emitting stat (numeric guard)" ;;
    *) if [ "$_abs246_age" -le 5 ]; then
           assert_eq "sane" "sane" \
               "ABS-246 AC2: lock_age_for sanitizes non-numeric mtime to now (age=$_abs246_age)"
       else
           assert_eq "$_abs246_age" "<=5" \
               "ABS-246 AC2: lock_age_for sanitizes non-numeric mtime to now"
       fi ;;
esac

# file_mtime_epoch: text output must yield return 1 (miss), never text output.
_abs246_fme_rc=0
_abs246_fme="$(bash -c '
    shim="$1"; orch="$2"
    source "$orch" >/dev/null 2>&1
    f="$(mktemp)"
    PATH="$shim:$PATH" file_mtime_epoch "$f"
' _abs246 "$_abs246_tmp" "$ORCH" 2>/dev/null)" || _abs246_fme_rc=$?
assert_eq "${_abs246_fme}:${_abs246_fme_rc}" ":1" \
    "ABS-246 AC2: file_mtime_epoch rejects non-numeric stat output (empty + rc 1)"

# Positive path with the REAL stat: both helpers stay numeric on this platform.
_abs246_real="$(bash -c '
    source "$1" >/dev/null 2>&1
    f="$(mktemp)"
    file_mtime_epoch "$f"
' _abs246 "$ORCH" 2>/dev/null)"
case "$_abs246_real" in
    *[!0-9]*|'') assert_eq "$_abs246_real" "<epoch digits>" \
        "ABS-246 AC2: file_mtime_epoch still returns epoch seconds with real stat" ;;
    *) assert_eq "ok" "ok" \
        "ABS-246 AC2: file_mtime_epoch still returns epoch seconds with real stat" ;;
esac

rm -rf "$_abs246_tmp"
