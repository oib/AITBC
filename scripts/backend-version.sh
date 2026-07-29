#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# backend-version.sh — Agentic-Backend project-version (release) helper (PILOT-7)
# =============================================================================
# The backend pendant of scripts/jira-version.sh, CLI-identical (ADR-A-0021 §d):
# releases are planned as backend project versions; the release tooling resolves
# the next tag from here instead of a hand-typed argument.
#
#   scripts/backend-version.sh list             all versions: name<TAB>released<TAB>id
#   scripts/backend-version.sh next             name of the LOWEST unreleased version
#                                               (the planned next jump); exit 1 if none
#   scripts/backend-version.sh create <name>    create an unreleased version (idempotent:
#                                               exit 0 + notice when it already exists)
#   scripts/backend-version.sh release <name>   mark the version released (today's date)
#   scripts/backend-version.sh release <name> --description-file <f>
#                                               mark released AND set the version
#                                               description from <f> in the same write
#                                               (atomic). Without the flag, the release
#                                               behaviour is unchanged.
#
# Environment (identical to scripts/backend-tracker.sh — spec §7):
#   BACKEND_URL (default http://localhost:8420), BACKEND_TOKEN and TRACKER_PROJECT
#   (both required), ORCH_INSTANCE_ID (optional), BACKEND_CURL (curl binary/shim).
#
# The server renders canonical text (jira-version.sh format, byte-for-byte), so
# responses are printed VERBATIM; this adapter maps HTTP status -> exit codes.
# Marking a version released stays a printed HUMAN follow-up of promotion — this
# script never runs implicitly. bash 3.2 + curl only.
# =============================================================================

BACKEND_URL="${BACKEND_URL:-http://localhost:8420}"
CURL_BIN="${BACKEND_CURL:-curl}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_env() {
    [ -n "${BACKEND_TOKEN:-}" ]   || die "BACKEND_TOKEN is required (spec §7)"
    [ -n "${TRACKER_PROJECT:-}" ] || die "TRACKER_PROJECT is required (spec §7)"
}

# json_escape <string> — JSON-escape a string value WITHOUT surrounding quotes.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '%s' "$s"
}

HTTP_CODE=""
HTTP_BODY_FILE=""

# http_request <METHOD> <PATH> [JSON_BODY] — call the agent API. The token rides in a
# --config file (never argv). Body is left in $HTTP_BODY_FILE; status in $HTTP_CODE.
http_request() {
    local method="$1" path="$2" data="${3-}"
    local url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT$path"
    local cfg err code
    cfg="$(mktemp)"; HTTP_BODY_FILE="$(mktemp)"; err="$(mktemp)"
    {
        printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN"
        [ -z "${ORCH_INSTANCE_ID:-}" ] || printf 'header = "X-Orch-Instance: %s"\n' "$ORCH_INSTANCE_ID"
    } > "$cfg"
    local args=( -sS --config "$cfg" -o "$HTTP_BODY_FILE" -w '%{http_code}' -X "$method" )
    [ -z "$data" ] || args+=( -H "Content-Type: application/json" --data-binary "$data" )
    if code="$("$CURL_BIN" "${args[@]}" "$url" 2>"$err")"; then
        HTTP_CODE="$code"; rm -f "$cfg" "$err"
    else
        local rc=$? msg; msg="$(cat "$err")"; rm -f "$cfg" "$err" "$HTTP_BODY_FILE"
        die "backend request failed (curl exit $rc): $msg"
    fi
}

# emit_body <file> — print a response body VERBATIM, normalized to one trailing newline.
emit_body() {
    [ -s "$1" ] || return 0
    cat "$1"
    [ "$(tail -c1 "$1" | wc -l)" -eq 1 ] || echo
}

# respond — 2xx -> body to stdout, exit 0; else -> body to stderr, exit != 0.
respond() {
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        emit_body "$HTTP_BODY_FILE"; rm -f "$HTTP_BODY_FILE"; return 0
    fi
    local body; body="$(cat "$HTTP_BODY_FILE")"; rm -f "$HTTP_BODY_FILE"
    case "$HTTP_CODE" in
        401|403) echo "ERROR: auth failed ($HTTP_CODE): check BACKEND_TOKEN / TRACKER_PROJECT" >&2 ;;
        *)       echo "ERROR: ${body:-request failed ($HTTP_CODE)}" >&2 ;;
    esac
    return 1
}

cmd_list() { http_request GET "/versions"; respond; }

cmd_next() { http_request GET "/versions/next"; respond; }

cmd_create() {
    [ -n "${1:-}" ] || die "create: version name required"
    local json="{\"name\":\"$(json_escape "$1")\"}"
    http_request POST "/versions" "$json"; respond
}

cmd_release() {
    local name="" descfile="" description=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --description-file)
                [ $# -ge 2 ] || die "release: --description-file requires a value"
                descfile="$2"; shift 2 ;;
            --*) die "release: unknown flag '$1'" ;;
            *)  [ -z "$name" ] || die "release: unexpected argument '$1'"
                name="$1"; shift ;;
        esac
    done
    [ -n "$name" ] || die "release: version name required"
    local json="{}"
    if [ -n "$descfile" ]; then
        [ -f "$descfile" ] || die "release: --description-file '$descfile' not found"
        description="$(cat "$descfile")"
        json="{\"description\":\"$(json_escape "$description")\"}"
    fi
    http_request POST "/versions/$name/release" "$json"; respond
}

main() {
    case "${1:-}" in
        help|--help|-h)
            sed -n '4,32p' "$0"; return 0 ;;
    esac
    require_env
    local cmd="${1:-}"; shift || true
    case "$cmd" in
        list)    [ $# -eq 0 ] || die "usage: backend-version.sh list"; cmd_list ;;
        next)    [ $# -eq 0 ] || die "usage: backend-version.sh next"; cmd_next ;;
        create)  cmd_create "${1:-}" ;;
        release) cmd_release "$@" ;;
        *) die "usage: backend-version.sh list | next | create <name> | release <name> [--description-file <f>]" ;;
    esac
}

main "$@"
