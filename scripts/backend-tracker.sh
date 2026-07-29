#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Agentic-Backend Task-Tracking Adapter (spec ABS-229 §7, story ABS-237 / S5)
# =============================================================================
# A thin curl shim that hangs the Agentic Delivery Backend behind $TRACKER_CMD,
# CLI-byte-identical to scripts/mock-tracker.sh so the orchestrator, seats and
# skills run unchanged (ADR-A-0021 §d). The backend already renders canonical
# text (mock format, byte-for-byte — spec §5), so responses are printed VERBATIM;
# this adapter only parses the mock CLI and maps HTTP status -> mock-identical
# exit codes / stderr (spec §7 table). Uses only bash + curl (BSD/GNU-portable).
#
# Env (spec §7): BACKEND_URL (default http://localhost:8420), BACKEND_TOKEN and
# TRACKER_PROJECT (both required), ORCH_INSTANCE_ID (optional -> X-Orch-Instance
# header, §4/§8), BACKEND_CURL (curl binary/shim, default curl — test seam).
# =============================================================================

BACKEND_URL="${BACKEND_URL:-http://localhost:8420}"
CURL_BIN="${BACKEND_CURL:-curl}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_env() {
    [ -n "${BACKEND_TOKEN:-}" ]   || die "BACKEND_TOKEN is required (spec §7)"
    [ -n "${TRACKER_PROJECT:-}" ] || die "TRACKER_PROJECT is required (spec §7)"
}

usage() {
    cat <<'EOF'
backend-tracker.sh — Agentic-Backend task-tracking adapter (spec §7).
CLI-identical to mock-tracker.sh; see it for full flag docs.

Usage: scripts/backend-tracker.sh <command> [args]
  get <id> | get --brief <id> | packet <id> | capabilities |
  search [--status/--type/--parent/--text/--label/--lane V] |
  create --type T --title T [--prefix/--parent/--role/--priority/--lane/--fix-version/--body-file V] [--flag F]... [--label L]... [--ac-blocking] |
  update <id> <field> <value> | comment <id> --kind K --actor A (--body T|--body-file P) |
  transition <id> <to> --actor A (--reason T|--reason-file P) [--expect-from S] |
  link <id> <other> <type> | children <id> | parent <id> | child-count <id> | events [--wait <sec>] | assign <id> <accountId> |
  policies [--audience <role>] |
  attach <id> <file> | attachments <id> | attachment-get <att-id> <out-path>
EOF
}

# --- JSON helpers (no jq) -----------------------------------------------------

# json_escape <string> — emit a JSON-escaped string value WITHOUT surrounding
# quotes. Handles the characters that break a JSON document: backslash, double
# quote, newline, tab, carriage return. Bodies/reasons are arbitrary markdown.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '%s' "$s"
}

# json_field <body> <key> — extract a top-level JSON string value (backend error
# payloads only; statuses/keys never contain quotes, so this stays simple).
json_field() {
    printf '%s' "$1" | sed -n 's/.*"'"$2"'":"\([^"]*\)".*/\1/p'
}

# append_json_str <key> <value> — emit `,"key":"escaped-value"` (nothing when the
# value is empty). % in <value> is safe: only the format string is interpreted.
append_json_str() {
    [ -z "$2" ] || printf ',"%s":"%s"' "$1" "$(json_escape "$2")"
}

# append_json_array <key> <values...> — emit `,"key":["v1","v2"]` (nothing when
# no values are given).
append_json_array() {
    local key="$1"; shift
    [ "$#" -gt 0 ] || return 0
    local out=",\"$key\":[" first=1 v
    for v in "$@"; do [ "$first" -eq 1 ] && first=0 || out="$out,"; out="$out\"$(json_escape "$v")\""; done
    printf '%s]' "$out"
}

# --- HTTP -------------------------------------------------------------------

HTTP_CODE=""
HTTP_BODY_FILE=""

# http_request <METHOD> <PATH> [JSON_BODY] — call the agent API. The token rides
# in a --config file (never argv), so it never appears in `ps`. The response body
# is left in $HTTP_BODY_FILE (VERBATIM, so `get` stays byte-identical); the status
# code lands in $HTTP_CODE. Extra --data-urlencode pairs (search) follow the body.
http_request() {
    local method="$1" path="$2" data="${3-}"; shift $(( $# > 3 ? 3 : $# ))
    local url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT$path"
    local cfg err code
    cfg="$(mktemp)"; HTTP_BODY_FILE="$(mktemp)"; err="$(mktemp)"
    {
        printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN"
        [ -z "${ORCH_INSTANCE_ID:-}" ] || printf 'header = "X-Orch-Instance: %s"\n' "$ORCH_INSTANCE_ID"
    } > "$cfg"
    local args=( -sS --config "$cfg" -o "$HTTP_BODY_FILE" -w '%{http_code}' -X "$method" )
    [ -z "$data" ] || args+=( -H "Content-Type: application/json" --data-binary "$data" )
    if code="$("$CURL_BIN" "${args[@]}" "$@" "$url" 2>"$err")"; then
        HTTP_CODE="$code"; rm -f "$cfg" "$err"
    else
        local rc=$? msg; msg="$(cat "$err")"; rm -f "$cfg" "$err" "$HTTP_BODY_FILE"
        # Network/transport failure: mirror the mock's die() (exit != 0); the
        # orchestrator's outage machinery takes over from here (spec §7).
        die "backend request failed (curl exit $rc): $msg"
    fi
}

# emit_body <file> — print a response body VERBATIM, normalized to exactly one
# trailing newline (the mock always newline-terminates its stdout; the backend
# omits the trailing newline on single-line replies). An empty body prints
# nothing (mock parity: a no-match search emits no output at all).
emit_body() {
    [ -s "$1" ] || return 0
    cat "$1"
    [ "$(tail -c1 "$1" | wc -l)" -eq 1 ] || echo
}

# respond — default handler: 2xx -> body to stdout (verbatim), exit 0; anything
# else -> body to stderr (backend already words item-op errors mock-identically),
# exit != 0 (spec §7). Auth codes get a hint.
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

# --- Commands ---------------------------------------------------------------

cmd_get() {
    # get --brief <id>: the §6 brief view (frontmatter + Goal + AC + latest handoff).
    if [ "${1:-}" = "--brief" ]; then
        [ $# -eq 2 ] || die "usage: get --brief <id>"
        http_request GET "/items/$2?view=brief"; respond; return
    fi
    [ $# -eq 1 ] || die "usage: get <id> | get --brief <id>"
    http_request GET "/items/$1"; respond
}

# packet <id> — server-composed context packet (spec §6). Printed verbatim like get.
cmd_packet() {
    [ $# -eq 1 ] || die "usage: packet <id>"
    http_request GET "/items/$1/packet"; respond
}

# capabilities — plain list of optional ops this adapter/backend supports (spec §6/§7).
# The route is project-independent and unauthenticated, so this bypasses the
# project-scoped http_request helper. Non-2xx / transport error -> exit != 0, which
# the orchestrator probe reads as "packet not available" and falls back to full-dump.
cmd_capabilities() {
    [ $# -eq 0 ] || die "usage: capabilities"
    local out code
    out="$(mktemp)"
    if code="$("$CURL_BIN" -sS -o "$out" -w '%{http_code}' "$BACKEND_URL/capabilities" 2>/dev/null)" \
       && [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
        emit_body "$out"; rm -f "$out"; return 0
    fi
    rm -f "$out"; return 1
}

cmd_search() {
    local -a q=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --status) [ $# -ge 2 ] || die "search: --status requires a value"; q+=( --data-urlencode "status=$2" ); shift 2 ;;
            --type)   [ $# -ge 2 ] || die "search: --type requires a value";   q+=( --data-urlencode "type=$2" );   shift 2 ;;
            --parent) [ $# -ge 2 ] || die "search: --parent requires a value"; q+=( --data-urlencode "parent=$2" ); shift 2 ;;
            --text)   [ $# -ge 2 ] || die "search: --text requires a value";   q+=( --data-urlencode "text=$2" );   shift 2 ;;
            --label)  [ $# -ge 2 ] || die "search: --label requires a value";  q+=( --data-urlencode "label=$2" );  shift 2 ;;
            --lane)   [ $# -ge 2 ] || die "search: --lane requires a value";   q+=( --data-urlencode "lane=$2" );   shift 2 ;;
            *) die "search: unknown argument: $1" ;;
        esac
    done
    # -G moves the urlencoded pairs onto the query string of a GET. The
    # ${q[@]+…} guard keeps an empty array safe under bash 3.2 + set -u (macOS).
    http_request GET "/items" "" -G ${q[@]+"${q[@]}"}; respond
}

cmd_create() {
    local type="" title="" prefix="" parent="" role="" body_file="" ac_blocking="" priority="" lane="" fix_version=""
    local -a flags=() labels=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --type)      [ $# -ge 2 ] || die "create: --type requires a value";      type="$2";      shift 2 ;;
            --title)     [ $# -ge 2 ] || die "create: --title requires a value";     title="$2";     shift 2 ;;
            --prefix)    [ $# -ge 2 ] || die "create: --prefix requires a value";    prefix="$2";    shift 2 ;;
            --parent)    [ $# -ge 2 ] || die "create: --parent requires a value";    parent="$2";    shift 2 ;;
            --role)      [ $# -ge 2 ] || die "create: --role requires a value";      role="$2";      shift 2 ;;
            --priority)  [ $# -ge 2 ] || die "create: --priority requires a value";  priority="$2";  shift 2 ;;
            --lane)      [ $# -ge 2 ] || die "create: --lane requires a value";      lane="$2";      shift 2 ;;
            --fix-version) [ $# -ge 2 ] || die "create: --fix-version requires a value"; fix_version="$2"; shift 2 ;;
            --body-file) [ $# -ge 2 ] || die "create: --body-file requires a value"; body_file="$2"; shift 2 ;;
            --flag)      [ $# -ge 2 ] || die "create: --flag requires a value";      flags+=( "$2" );  shift 2 ;;
            --label)     [ $# -ge 2 ] || die "create: --label requires a value";     labels+=( "$2" ); shift 2 ;;
            --ac-blocking) ac_blocking="true"; shift ;;
            *) die "create: unknown argument: $1" ;;
        esac
    done
    [ -n "$type" ]  || die "create: --type is required (epic|ticket|subtask)"
    [ -n "$title" ] || die "create: --title is required"
    # ABS-490: without --prefix, keys default to the PROJECT key, not the mock's
    # DEMO- (a PILOT project silently accumulated DEMO-n items). The mock adapter
    # keeps its DEMO default; here the project is always known (required above).
    [ -n "$prefix" ] || prefix="$TRACKER_PROJECT"
    # Role is a closed set the backend does not police; validate here for mock
    # parity (mock rejects an unknown role; the backend would accept it).
    if [ -n "$role" ]; then
        case "$role" in be-developer|fe-developer|data-engineer) ;; *) die "create: invalid role '$role' (be-developer|fe-developer|data-engineer)" ;; esac
    fi
    local body=""
    if [ -n "$body_file" ]; then
        [ -f "$body_file" ] || die "create: --body-file not found: $body_file"
        body="$(cat "$body_file")"
    fi
    # Assemble the JSON payload (POST /items, spec §4).
    local json="{\"type\":\"$(json_escape "$type")\",\"title\":\"$(json_escape "$title")\""
    json="$json$(append_json_str prefix "$prefix")$(append_json_str parent "$parent")$(append_json_str role "$role")$(append_json_str priority "$priority")$(append_json_str lane "$lane")$(append_json_str fix_version "$fix_version")"
    [ -z "$ac_blocking" ] || json="$json,\"ac_blocking\":true"
    json="$json$(append_json_array flags ${flags[@]+"${flags[@]}"})"
    json="$json$(append_json_array labels ${labels[@]+"${labels[@]}"})"
    json="$json$(append_json_str body "$body")}"
    http_request POST "/items" "$json"; respond
}

cmd_update() {
    [ $# -eq 3 ] || die "usage: update <id> <field> <value>"
    local json="{\"field\":\"$(json_escape "$2")\",\"value\":\"$(json_escape "$3")\"}"
    http_request PATCH "/items/$1" "$json"; respond
}

cmd_comment() {
    [ $# -ge 1 ] || die "usage: comment <id> --kind <kind> --actor <actor> (--body <text> | --body-file <path>)"
    local id="$1"; shift
    local kind="" actor="" body="" body_file="" have_body=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --kind)      [ $# -ge 2 ] || die "comment: --kind requires a value";      kind="$2";      shift 2 ;;
            --actor)     [ $# -ge 2 ] || die "comment: --actor requires a value";     actor="$2";     shift 2 ;;
            --body)      [ $# -ge 2 ] || die "comment: --body requires a value";      body="$2"; have_body=1; shift 2 ;;
            --body-file) [ $# -ge 2 ] || die "comment: --body-file requires a value"; body_file="$2"; shift 2 ;;
            *) die "comment: unknown argument: $1" ;;
        esac
    done
    [ "$have_body" -eq 0 ] || [ -z "$body_file" ] || die "comment: --body and --body-file are mutually exclusive"
    if [ -n "$body_file" ]; then
        [ -f "$body_file" ] || die "comment: --body-file not found: $body_file"
        body="$(cat "$body_file")"
    fi
    [ -n "$kind" ] && [ -n "$actor" ] && [ -n "$body" ] || die "comment: --kind, --actor and --body (or --body-file) are required"
    local json="{\"kind\":\"$(json_escape "$kind")\",\"actor\":\"$(json_escape "$actor")\",\"body\":\"$(json_escape "$body")\"}"
    http_request POST "/items/$id/comments" "$json"; respond
}

cmd_transition() {
    [ $# -ge 2 ] || die "usage: transition <id> <to-status> --actor <actor> (--reason <text> | --reason-file <path>)"
    local id="$1" to="$2"; shift 2
    local actor="" reason="" reason_file="" have_reason=0 expect_from=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --actor)       [ $# -ge 2 ] || die "transition: --actor requires a value";       actor="$2";       shift 2 ;;
            --reason)      [ $# -ge 2 ] || die "transition: --reason requires a value";      reason="$2"; have_reason=1; shift 2 ;;
            --reason-file) [ $# -ge 2 ] || die "transition: --reason-file requires a value"; reason_file="$2"; shift 2 ;;
            --expect-from) [ $# -ge 2 ] || die "transition: --expect-from requires a value"; expect_from="$2"; shift 2 ;;
            *) die "transition: unknown argument: $1" ;;
        esac
    done
    [ "$have_reason" -eq 0 ] || [ -z "$reason_file" ] || die "transition: --reason and --reason-file are mutually exclusive"
    if [ -n "$reason_file" ]; then
        [ -f "$reason_file" ] || die "transition: --reason-file not found: $reason_file"
        reason="$(cat "$reason_file")"
    fi
    [ -n "$actor" ] && [ -n "$reason" ] || die "transition: --actor and --reason (or --reason-file) are required"
    local json="{\"to\":\"$(json_escape "$to")\",\"actor\":\"$(json_escape "$actor")\",\"reason\":\"$(json_escape "$reason")\""
    [ -z "$expect_from" ] || json="$json,\"expect_from\":\"$(json_escape "$expect_from")\""
    json="$json}"
    http_request POST "/items/$id/transition" "$json"
    local body; body="$(cat "$HTTP_BODY_FILE")"; rm -f "$HTTP_BODY_FILE"
    case "$HTTP_CODE" in
        2*) printf '%s\n' "$body" ;;
        409)
            # ABS-198 compare-and-set: a peer already moved the ticket. The mock
            # logs a NOOP on STDOUT and exits 0 (a lost race is not an error, §7).
            local actual; actual="$(json_field "$body" actual)"
            echo "$id: NOOP compare-and-set expect-from=$expect_from actual=$actual (skipped $to)"
            ;;
        400)
            # Illegal edge (spec §4). Re-word the JSON payload to the mock phrase
            # so callers/tests grep "illegal transition" identically.
            local ef et; ef="$(json_field "$body" from)"; et="$(json_field "$body" to)"
            if [ -n "$ef$et" ]; then
                echo "ERROR: transition: illegal transition '$ef' -> '$et' for $id" >&2
            else
                echo "ERROR: transition: ${body:-rejected}" >&2
            fi
            return 1 ;;
        404) echo "ERROR: no such ticket: $id" >&2; return 1 ;;
        401|403) echo "ERROR: auth failed ($HTTP_CODE): check BACKEND_TOKEN / TRACKER_PROJECT" >&2; return 1 ;;
        *)   echo "ERROR: transition failed ($HTTP_CODE): $body" >&2; return 1 ;;
    esac
}

cmd_link() {
    [ $# -eq 3 ] || die "usage: link <id> <other> <link-type>"
    local json="{\"other\":\"$(json_escape "$2")\",\"kind\":\"$(json_escape "$3")\"}"
    http_request POST "/items/$1/links" "$json"; respond
}

cmd_children()    { [ $# -eq 1 ] || die "usage: children <epic-id>"; http_request GET "/items/$1/children"; respond; }
cmd_parent()      { [ $# -eq 1 ] || die "usage: parent <id>";        http_request GET "/items/$1/parent"; respond; }
cmd_child_count() { [ $# -eq 1 ] || die "usage: child-count <id>";   http_request GET "/items/$1/child-count"; respond; }
# events [--wait <sec>] — poll the agent event feed (GET /events?since=auto).
# S4/PILOT-30 long-poll: with --wait <sec> the server HOLDS the request until a
# feed-relevant event arrives or <sec> elapses (re-capped server-side at
# EVENT_WAIT_CAP_SECONDS, ADR-A-0029 §7). curl --max-time = wait + a buffer so a
# genuinely hung connection (proxy/Cisco-SWG intercept) FAILS (curl exit != 0 ->
# die, the orchestrator degrades to interval polling) instead of blocking forever;
# a normal cap-elapsed empty answer returns before the buffer. The request's
# ingress books the orchestrator heartbeat server-side (auth touches last_seen).
# --wait 0 / no flag is byte-identical to the pre-S4 immediate read.
cmd_events() {
    local wait=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --wait) [ $# -ge 2 ] || die "events: --wait requires a value"; wait="$2"; shift 2 ;;
            *) die "events: unknown argument: $1" ;;
        esac
    done
    if [ -n "$wait" ] && [ "$wait" -gt 0 ] 2>/dev/null; then
        local maxt=$(( wait + ${BACKEND_WAIT_MAX_TIME_BUFFER:-10} ))
        http_request GET "/events?since=auto&wait=$wait" "" --max-time "$maxt"; respond
    else
        http_request GET "/events?since=auto"; respond
    fi
}

cmd_assign() {
    [ $# -eq 2 ] || die "usage: assign <id> <accountId>"
    local json="{\"accountId\":\"$(json_escape "$2")\"}"
    http_request POST "/items/$1/assign" "$json"; respond
}

# policies [--audience <role>] — GET /policies (read-only, S4 / ABS-381).
# Prints the §3 rendered effective-policy text + `policy_rev: <sha256>` line
# verbatim. Omitting --audience returns the all-audiences union.
cmd_policies() {
    local -a q=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --audience) [ $# -ge 2 ] || die "policies: --audience requires a value"; q+=( --data-urlencode "audience=$2" ); shift 2 ;;
            *) die "policies: unknown argument: $1" ;;
        esac
    done
    http_request GET "/policies" "" -G ${q[@]+"${q[@]}"}; respond
}

# --- Attachments (PILOT-9 / twin ABS-489) -----------------------------------
# Sanctioned mock difference (ADR-A-0021): mock-tracker.sh has NO attachment ops;
# these three are backend-only, documented in docs/guides/AGENTIC-BACKEND-API.md
# §Behavioral differences (analogous to the policies difference).

# http_upload <path> <file> <filename> — POST a raw file body with the token in a
# --config file (never argv). Filename rides X-Attachment-Filename; body is sent as
# application/octet-stream. Response lands in $HTTP_BODY_FILE / $HTTP_CODE like http_request.
http_upload() {
    local path="$1" file="$2" name="$3"
    local url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT$path"
    local cfg err code
    cfg="$(mktemp)"; HTTP_BODY_FILE="$(mktemp)"; err="$(mktemp)"
    {
        printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN"
        [ -z "${ORCH_INSTANCE_ID:-}" ] || printf 'header = "X-Orch-Instance: %s"\n' "$ORCH_INSTANCE_ID"
    } > "$cfg"
    local args=( -sS --config "$cfg" -o "$HTTP_BODY_FILE" -w '%{http_code}' -X POST
                 -H "Content-Type: application/octet-stream"
                 -H "X-Attachment-Filename: $name"
                 --data-binary "@$file" )
    if code="$("$CURL_BIN" "${args[@]}" "$url" 2>"$err")"; then
        HTTP_CODE="$code"; rm -f "$cfg" "$err"
    else
        local rc=$? msg; msg="$(cat "$err")"; rm -f "$cfg" "$err" "$HTTP_BODY_FILE"
        die "backend request failed (curl exit $rc): $msg"
    fi
}

# attach <id> <file> — upload a file to a work item. Prints the new attachment id.
cmd_attach() {
    [ $# -eq 2 ] || die "usage: attach <id> <file>"
    local id="$1" file="$2"
    [ -f "$file" ] || die "attach: file not found: $file"
    http_upload "/items/$id/attachments" "$file" "$(basename "$file")"
    respond
}

# attachments <id> — list an item's attachments (one `{...}` line each, size + sha256).
cmd_attachments() {
    [ $# -eq 1 ] || die "usage: attachments <id>"
    http_request GET "/items/$1/attachments"; respond
}

# attachment-get <att-id> <out-path> — download attachment bytes to <out-path>
# (byte-identical; binary-safe via curl -o). Non-2xx -> stderr + exit != 0.
cmd_attachment_get() {
    [ $# -eq 2 ] || die "usage: attachment-get <att-id> <out-path>"
    http_request GET "/attachments/$1/content"
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        mv "$HTTP_BODY_FILE" "$2"; return 0
    fi
    respond
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
        get)          cmd_get "$@" ;;
        packet)       cmd_packet "$@" ;;
        capabilities) cmd_capabilities "$@" ;;
        search)      cmd_search "$@" ;;
        create)      cmd_create "$@" ;;
        update)      cmd_update "$@" ;;
        comment)     cmd_comment "$@" ;;
        transition)  cmd_transition "$@" ;;
        link)        cmd_link "$@" ;;
        children)    cmd_children "$@" ;;
        parent)      cmd_parent "$@" ;;
        child-count) cmd_child_count "$@" ;;
        events)      cmd_events "$@" ;;
        assign)      cmd_assign "$@" ;;
        policies)    cmd_policies "$@" ;;
        attach)          cmd_attach "$@" ;;
        attachments)     cmd_attachments "$@" ;;
        attachment-get)  cmd_attachment_get "$@" ;;
        *) usage >&2; die "unknown command: $cmd" ;;
    esac
}

main "$@"
