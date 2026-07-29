# =============================================================================
# PILOT-38 — the CLOSE seat_spawn `session_stored` sources store_session's
# AUTHORITATIVE drop/keep verdict, fixing the salvage+birth-denials undercount.
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/test-orchestrator.sh
# into the live harness — no shebang, no `set -e` re-entry. Shares assert_eq /
# assert_contains / assert_not_contains, PASS/FAIL/TOTAL, REPO_ROOT, ORCH.
#
# PILOT-27 wired emit_seat_upsert to POST session_stored, but the CLOSE value was
# a recompute inside run_spawn_cmd that read the SALVAGE result's own denials. It
# matches store_session on every DIRECT path and diverges ONLY in the corner of
# ABS-254 / ADR-A-0023 rule 3: a birth spawn hits the turn cap AND carries
# permission_denials, then a CLEAN salvage carries a session_id WITHOUT denials.
# store_session drops that session (force_poison from the birth denials), but the
# clean salvage's recompute emitted session_stored=true — an optimistic undercount
# of "how many sessions do we lose?" (the AC2 forensics query PILOT-24 enabled).
#
# The fix routes both store_session's decision and the CLOSE recompute through one
# predicate, session_stored_verdict, and threads the birth denials into the
# salvage's recompute via SPAWN_FORCE_POISON. This test pins the divergence corner
# end-to-end against the producer->endpoint seam (the same BACKEND_CURL capture
# stub PILOT-27 uses) plus the verdict predicate directly, and re-checks the four
# direct paths for no regression (AC3).
# =============================================================================

echo -e "\n${CYAN}=== PILOT-38 CLOSE session_stored = store_session's authoritative verdict ===${NC}"

# A hex-with-dashes session id extract_session_id accepts (>=8 hex chars).
_p38_sid='1a2b3c4d-1111-2222-3333-444455556666'
# A clean salvage result: carries a session id, EMPTY permission_denials.
_p38_clean='{"type":"result","subtype":"success","session_id":"'"$_p38_sid"'","permission_denials":[]}'
# A poisoned result: same id, a MUTATING-tool (Bash) denial (ABS-598: only a
# mutating denial poisons; the field is the CLI's real `tool_name`).
_p38_poison='{"type":"result","subtype":"success","session_id":"'"$_p38_sid"'","permission_denials":[{"tool_name":"Bash","tool_input":{"command":"rm -rf x"}}]}'
# A no-session result (a first spawn's stdout carries no session id).
_p38_nosid='{"type":"result","subtype":"success","permission_denials":[]}'

# Evaluate session_stored_verdict in a child bash that sources orchestrator.sh.
_p38_verdict() {   # <spawn-out> <force_poison> [ORCH_SESSION_RESUME]
    ORCH_SESSION_RESUME="${3:-1}" bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo SOURCE-FAIL; exit 0; }
        session_stored_verdict "$1" "$2"
    ' _ "$1" "$2"
}

# --- The divergence corner (AC1): clean salvage + birth denials -> false --------
_p38_corner="$(_p38_verdict "$_p38_clean" 1)"
assert_eq "$_p38_corner" "false" \
    "PILOT-38 AC1: clean salvage + birth-denials (force_poison=1) -> session_stored=false (store_session drops it)"

# The bug this fixes: WITHOUT the birth-denials carry, the same clean salvage reads
# true — the optimistic undercount. Pinning it proves force_poison is what flips it.
_p38_bug="$(_p38_verdict "$_p38_clean" 0)"
assert_eq "$_p38_bug" "true" \
    "PILOT-38: the same clean salvage WITHOUT force_poison reads true (the pre-fix undercount the carry corrects)"

# --- Producer->endpoint seam (AC1/AC2): the corner serializes false -------------
_p38_dir="$(mktemp -d)"
_p38_stub="$_p38_dir/curl-stub.sh"
cat > "$_p38_stub" <<'STUB'
#!/usr/bin/env bash
body=""
while [ $# -gt 0 ]; do
    case "$1" in
        --data-binary) body="$2"; shift 2 ;;
        *) shift ;;
    esac
done
printf '%s' "$body" > "$CAPTURE_FILE"
exit 0
STUB
chmod +x "$_p38_stub"

_p38_cap="$_p38_dir/corner.json"
CAPTURE_FILE="$_p38_cap" BACKEND_CURL="$_p38_stub" BACKEND_TOKEN=tok TRACKER_PROJECT=proj \
bash -c '
    source "'"$ORCH"'" >/dev/null 2>&1 || { echo SOURCE-FAIL; exit 0; }
    export CAPTURE_FILE="'"$_p38_cap"'"
    verdict="$(session_stored_verdict "'"$_p38_clean"'" 1)"
    ORCH_RUN_ID=run38 ORCH_INSTANCE_ID=inst38 SPAWN_ATTEMPT=1 \
        emit_seat_upsert close sid1 PILOT-38 be-developer 2026-01-01T00:00:00Z \
            2026-01-01T00:01:00Z 0 "" "'"$_p38_sid"'" "$verdict"
' >/dev/null 2>&1
_p38_body="$(cat "$_p38_cap" 2>/dev/null)"
assert_contains "$_p38_body" '"session_stored":false' \
    "PILOT-38 AC1/AC2: the salvage+birth-denials corner serializes \"session_stored\":false (forensics count is exact)"
assert_not_contains "$_p38_body" '"session_stored":true' \
    "PILOT-38 AC2: the corner never emits session_stored=true (would undercount 'lost sessions')"
rm -rf "$_p38_dir" 2>/dev/null || true

# --- Direct-path parity (AC3): no regression on PILOT-27's four paths -----------
assert_eq "$(_p38_verdict "$_p38_clean" 0)" "true" \
    "PILOT-38 AC3: normal birth (clean result, no force_poison) -> session_stored=true"
assert_eq "$(_p38_verdict "$_p38_poison" 0)" "false" \
    "PILOT-38 AC3: poison-rejection (result carries permission_denials) -> session_stored=false"
assert_eq "$(_p38_verdict "$_p38_nosid" 0)" "false" \
    "PILOT-38 AC3: no-session (result carries no session id) -> session_stored=false"
assert_eq "$(_p38_verdict "$_p38_clean" 0 0)" "false" \
    "PILOT-38 AC3: resume-off (ORCH_SESSION_RESUME=0) -> session_stored=false"

# --- Source-wiring: the salvage carries birth denials; the CLOSE reads it -------
_p38_src="$(cat "$ORCH")"
assert_contains "$_p38_src" 'SPAWN_FORCE_POISON="$birth_denials" run_spawn_cmd' \
    "PILOT-38: the salvage resume threads the birth denials into run_spawn_cmd (SPAWN_FORCE_POISON)"
assert_contains "$_p38_src" 'seat_session_stored="$(session_stored_verdict "$seat_out" "${SPAWN_FORCE_POISON:-0}")"' \
    "PILOT-38: the CLOSE recompute sources the authoritative verdict, honoring SPAWN_FORCE_POISON"
