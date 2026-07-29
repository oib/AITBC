#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Agentic-Backend Forge Adapter (ABS-350, ABS-230 S3)
# =============================================================================
# Thin curl shim behind $FORGE_CMD: `backend-forge.sh pr-state <key>` queries
# the backend PR mirror and prints canonical state for the orchestrator's
# Done-gate (scripts/orchestrator.sh:story_pr_state).
#
# Output format (stdout, single line on success):
#   STATE #REF ci=CI_STATUS mergeable=BOOL
# where STATE ∈ {OPEN, MERGED, DECLINED}, REF is the PR number prefixed with
# '#' (e.g. #42), CI_STATUS ∈ {passed,failed,pending,unknown}, BOOL is
# true|false.  When no PR is tracked for the item: single token "NONE".
# story_pr_state in orchestrator.sh only reads $1 and $2 (STATE + REF); the
# remaining fields are informational for future consumers.
#
# Exit codes:
#   0 — pr-state returned successfully (including NONE)
#   1 — item not found (404), auth error, or HTTP / network failure
#
# Env (same convention as backend-tracker.sh spec §7):
#   BACKEND_URL       base URL (default http://localhost:8420)
#   BACKEND_TOKEN     required; orchestrator bearer token
#   TRACKER_PROJECT   required; project key (e.g. ABS)
#   ORCH_INSTANCE_ID  optional; sent as X-Orch-Instance header
#   BACKEND_CURL      curl binary/shim (default curl) — test seam
# =============================================================================

BACKEND_URL="${BACKEND_URL:-http://localhost:8420}"
CURL_BIN="${BACKEND_CURL:-curl}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_env() {
    [ -n "${BACKEND_TOKEN:-}" ]   || die "BACKEND_TOKEN is required (mirrors backend-tracker.sh §7)"
    [ -n "${TRACKER_PROJECT:-}" ] || die "TRACKER_PROJECT is required (mirrors backend-tracker.sh §7)"
}

usage() {
    cat <<'EOF'
backend-forge.sh — Agentic-Backend forge/PR-mirror adapter (ABS-350).
Queries the backend PR mirror; output consumed by the orchestrator Done-gate
($FORGE_CMD). Uses the same env convention as backend-tracker.sh.

Usage: scripts/backend-forge.sh pr-state <key>

  pr-state <key>   Print PR state for the given ticket key (e.g. ABS-350).
                   Output (text/plain, single line):
                     STATE #REF ci=CI_STATUS mergeable=BOOL   (PR tracked)
                     NONE                                      (no PR tracked)
                   STATE: OPEN | MERGED | DECLINED
                   Exit 0 on success; non-zero + stderr on error.

Environment (same as backend-tracker.sh spec §7):
  BACKEND_URL      base URL (default http://localhost:8420)
  BACKEND_TOKEN    required; orchestrator bearer token
  TRACKER_PROJECT  required; project key
  BACKEND_CURL     curl binary override (test seam, default curl)
  ORCH_INSTANCE_ID optional instance header
EOF
}

# --- HTTP --------------------------------------------------------------------

HTTP_CODE=""
HTTP_BODY_FILE=""

# http_get <path> — call the agent API with GET. Token rides in a --config file
# (never argv). Response body lands in $HTTP_BODY_FILE; status code in $HTTP_CODE.
http_get() {
    local path="$1"
    local url="$BACKEND_URL$path"
    local cfg err code
    cfg="$(mktemp)"; HTTP_BODY_FILE="$(mktemp)"; err="$(mktemp)"
    {
        printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN"
        [ -z "${ORCH_INSTANCE_ID:-}" ] || printf 'header = "X-Orch-Instance: %s"\n' "$ORCH_INSTANCE_ID"
    } > "$cfg"
    if code="$("$CURL_BIN" -sS --config "$cfg" -o "$HTTP_BODY_FILE" -w '%{http_code}' -X GET "$url" 2>"$err")"; then
        HTTP_CODE="$code"; rm -f "$cfg" "$err"
    else
        local rc=$? msg; msg="$(cat "$err")"; rm -f "$cfg" "$err" "$HTTP_BODY_FILE"
        die "backend request failed (curl exit $rc): $msg"
    fi
}

# --- Commands ----------------------------------------------------------------

cmd_pr_state() {
    [ $# -eq 1 ] || die "usage: pr-state <key>"
    local key="$1"
    http_get "/agent/v1/projects/$TRACKER_PROJECT/items/$key/pr-state"
    local body; body="$(cat "$HTTP_BODY_FILE")"; rm -f "$HTTP_BODY_FILE"
    case "$HTTP_CODE" in
        200)
            printf '%s\n' "$body"
            ;;
        404)
            echo "ERROR: no such item: $key" >&2
            return 1
            ;;
        401|403)
            echo "ERROR: auth failed ($HTTP_CODE): check BACKEND_TOKEN / TRACKER_PROJECT" >&2
            return 1
            ;;
        *)
            echo "ERROR: forge request failed ($HTTP_CODE): ${body:-empty response}" >&2
            return 1
            ;;
    esac
}

# --- Dispatcher --------------------------------------------------------------

main() {
    [ $# -ge 1 ] || { usage >&2; exit 1; }
    local cmd="$1"; shift
    case "$cmd" in
        help|--help|-h) usage; return 0 ;;
    esac
    require_env
    case "$cmd" in
        pr-state) cmd_pr_state "$@" ;;
        *) usage >&2; die "unknown command: $cmd" ;;
    esac
}

main "$@"
