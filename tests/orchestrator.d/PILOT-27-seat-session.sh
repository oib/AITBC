# =============================================================================
# PILOT-27 — the PRIMARY producer carries PILOT-24's session_id + session_stored.
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/tooling/test-orchestrator.sh
# into the live harness — no shebang, no `set -e` re-entry. Shares assert_eq /
# assert_contains / assert_not_contains, PASS/FAIL/TOTAL, REPO_ROOT, ORCH.
#
# PILOT-24 delivered session_id + session_stored end-to-end (schema/API/UI) but
# NO producer wrote them on a live spawn. PILOT-27 wires emit_seat_upsert to POST
# them. This test proves the producer->row path at the SEAM (AC4): it captures the
# EXACT JSON body emit_seat_upsert POSTs (via a BACKEND_CURL capture stub) and
# asserts the two fields are serialized correctly:
#   - session_id: a quoted string when present, JSON null when empty (a first
#     spawn's OPEN carries no session yet).
#   - session_stored: the JSON literals true / false (never a quoted "false" that
#     an SQL `WHERE session_stored = false` would miss — AC2's forensics query).
# The live POST round-trip (row persists, Seat-Drawer shows it) is proven against
# the running backend by the docker-backed suites; here we pin the seam contract
# without a network, mirroring PILOT-26's offline seam conformance.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-27 producer carries session_id + session_stored (seam conformance) ===${NC}"

# Capture the emit body by standing in a stub for BACKEND_CURL that writes the
# --data-binary payload to $CAPTURE_FILE and exits 0 (emit is fire-and-forget).
_pilot27_dir="$(mktemp -d)"
_pilot27_stub="$_pilot27_dir/curl-stub.sh"
cat > "$_pilot27_stub" <<'STUB'
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
chmod +x "$_pilot27_stub"

# Drive the REAL emit_seat_upsert in a child bash that sources orchestrator.sh.
# args after diag: <session_id> <session_stored>
_pilot27_emit() {   # <capture-file> <session_id> <session_stored>
    CAPTURE_FILE="$1" BACKEND_CURL="$_pilot27_stub" BACKEND_TOKEN=tok TRACKER_PROJECT=proj \
    bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo SOURCE-FAIL; exit 0; }
        export CAPTURE_FILE="'"$1"'"
        ORCH_RUN_ID=run7 ORCH_INSTANCE_ID=inst9 SPAWN_ATTEMPT=1 \
            emit_seat_upsert close sid1 PILOT-27 be-developer 2026-01-01T00:00:00Z \
                2026-01-01T00:01:00Z 0 "" "'"$2"'" "'"$3"'"
    '
}

# Case A: a stored session -> session_id quoted string, session_stored=true literal.
_pilot27_cap="$_pilot27_dir/a.json"
_pilot27_emit "$_pilot27_cap" "sess-abc-123" "true" >/dev/null 2>&1
_pilot27_body="$(cat "$_pilot27_cap" 2>/dev/null)"
assert_contains "$_pilot27_body" '"session_id":"sess-abc-123"' \
    "PILOT-27: emit_seat_upsert serializes a present session_id as a quoted string"
assert_contains "$_pilot27_body" '"session_stored":true' \
    "PILOT-27: session_stored=true is a JSON boolean literal (not a quoted string)"

# Case B: a poison-dropped session -> session_stored=false literal (AC2 query).
_pilot27_capb="$_pilot27_dir/b.json"
_pilot27_emit "$_pilot27_capb" "sess-xyz-999" "false" >/dev/null 2>&1
_pilot27_bodyb="$(cat "$_pilot27_capb" 2>/dev/null)"
assert_contains "$_pilot27_bodyb" '"session_stored":false' \
    "PILOT-27: session_stored=false is a JSON boolean literal — AC2 'lost sessions' SQL stays exact"
assert_not_contains "$_pilot27_bodyb" '"session_stored":"false"' \
    "PILOT-27: session_stored is never a quoted \"false\" (would break WHERE session_stored = false)"

# Case C: absent session (a first spawn's OPEN, no session yet) -> both null.
_pilot27_capc="$_pilot27_dir/c.json"
_pilot27_emit "$_pilot27_capc" "" "" >/dev/null 2>&1
_pilot27_bodyc="$(cat "$_pilot27_capc" 2>/dev/null)"
assert_contains "$_pilot27_bodyc" '"session_id":null' \
    "PILOT-27: an absent session_id is serialized as JSON null"
assert_contains "$_pilot27_bodyc" '"session_stored":null' \
    "PILOT-27: an unknown session_stored (OPEN, pre-reap) is serialized as JSON null"

# Source-wiring: both call sites now thread the session args (AC1 OPEN resume-id,
# AC1/AC2 CLOSE result session) — a refactor that drops them is caught here.
_pilot27_src="$(cat "$ORCH")"
assert_contains "$_pilot27_src" 'emit_seat_upsert open "$seat_sid" "$ticket" "$role" "$seat_started" "" "" "" "${SPAWN_RESUME_ID:-}"' \
    "PILOT-27: the OPEN upsert carries the resumed session id (AC3 repair-respawn path)"
assert_contains "$_pilot27_src" 'emit_seat_upsert close "$seat_sid" "$ticket" "$role" "$seat_started" "$seat_completed" "$rc" "$seat_diag" "$seat_session_id" "$seat_session_stored"' \
    "PILOT-27: the CLOSE upsert carries the spawn result's session_id + session_stored"

rm -rf "$_pilot27_dir" 2>/dev/null || true
