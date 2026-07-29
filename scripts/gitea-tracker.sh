#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Gitea Task-Tracking Adapter
# =============================================================================
# A drop-in $TRACKER_CMD implementing the canonical task-tracking operations
# (profiles/neutral/adapters/task-tracking.md) against the Gitea REST API v1,
# using this repo's real issue tracker at $GITEA_SITE/$GITEA_OWNER/$GITEA_REPO.
# Its CLI surface — subcommands, flags, output shapes, exit codes and error
# messages — mirrors scripts/mock-tracker.sh, so scripts/orchestrator.sh runs
# unmodified with:
#
#     TRACKER_CMD=scripts/gitea-tracker.sh scripts/orchestrator.sh
#
# The mock adapter (scripts/mock-tracker.sh) is the conformance reference; this
# adapter is "correct" when it behaves the same from the caller's view.
#
# -----------------------------------------------------------------------------
# Prerequisites: bash 3.2+, curl, python3 (JSON parse/build only — no jq/yq).
#
# -----------------------------------------------------------------------------
# Environment (human-provisioned; NEVER stored in the repo, NEVER echoed):
#   GITEA_SITE      Gitea base URL, e.g. https://gitea.bubuit.net
#   GITEA_TOKEN     Gitea access token (SECRET — scrubbed from all output)
#   GITEA_OWNER     Repo owner, e.g. oib
#   GITEA_REPO      Repo name, e.g. aitbc
#   GITEA_TICKET_PREFIX   Cosmetic id prefix (default: AITBC). Ticket identity
#                   is always the Gitea issue number; the prefix is display-only.
# The token is delivered to curl through a --config file (never argv), so it
# never appears in `ps` or in curl's verbose trace. All curl stderr/response
# text is scrubbed before it can reach a log (scrub_secrets).
#
# -----------------------------------------------------------------------------
# Status/field mapping (Gitea has NO native custom-status field — only native
# open/closed — and no native lane/role/priority/parent/depends-on fields):
#
#   canonical field   Gitea representation
#   ---------------   ---------------------------------------------------------
#   type              exclusive scoped label  type/<epic|ticket|subtask>
#   status            exclusive scoped label  status/<CanonicalStatusName>
#                      (+ native open/closed derived from status, cosmetic only
#                      — the label is the sole source of truth read by `get`)
#   lane              exclusive scoped label  lane/<normal|fastlane>
#   role              exclusive scoped label  role/<be-developer|...> (optional)
#   priority          exclusive scoped label  priority/<hotfix|high|normal|low>
#                      (optional -- only-when-given, like the mock adapter)
#   flags             non-exclusive labels    flag/<design|security|...>
#   ac_blocking        plain label             ac-blocking (presence = true)
#   labels (free-form) any other plain label (e.g. orchestrator-ready)
#   parent/depends_on/links/iteration_cap
#                     a hidden metadata block at the top of the issue body:
#                       <!-- aitbc-tracker:meta
#                       parent: AITBC-12
#                       depends_on: [AITBC-5, AITBC-7]
#                       links: [pr:https://...]
#                       iteration_cap: 3
#                       -->
#                     invisible in Gitea's rendered markdown, parsed/rewritten
#                     by this adapter only. Gitea has no native issue hierarchy
#                     or dependency-graph field stable across versions, so this
#                     keeps parent/depends_on/links fully self-contained and
#                     portable rather than depending on an unstable relation API.
#   comments          native Gitea issue comments; this adapter's own `comment`
#                     posts bodies in the mock's exact header form
#                     "### <at> | kind: <kind> | actor: <actor>\n\n<body>" so
#                     `get` can pass them straight through under "## Comments".
#                     A comment posted by a human via the Gitea web UI (no such
#                     header) is passed through as-is -- not required to parse.
#
# `Setup` (idempotent, run once before first use, and safe to re-run):
#     scripts/gitea-tracker.sh setup
# provisions every required label (all 28 canonical statuses + type/lane/
# role/priority/flag scopes + ac-blocking) on $GITEA_OWNER/$GITEA_REPO. Every
# other command ASSUMES these labels already exist (documented prerequisite,
# same shape as jira-tracker.sh's "the human Jira workflow must define these
# statuses") and fails loudly, naming the missing label, if `setup` was never run.
#
# Timestamps: Gitea returns ISO-8601 with a numeric zone offset (not bare Z),
# e.g. 2026-06-12T11:43:31+02:00. `get`/`search` normalize every emitted
# timestamp to the mock's canonical UTC form `%Y-%m-%dT%H:%M:%SZ` (the
# orchestrator's iso_to_epoch parses only that form), same as jira-tracker.sh.
#
# Events: like the mock/jira adapters, a status snapshot is kept at
# $GITEA_TRACKER_STATE (default work/.gitea-events-state, gitignored) and
# diffed against a fresh sweep on each `events` call.
#
# API-call budget per orchestrator poll cycle: `events` costs one label-cache
# GET + one issues-list GET (paged only if >50 issues). `get` costs one issue
# GET + one comments GET (paged only past 50 comments). `create`/`transition`/
# `comment`/`link`/`update`/`assign` cost one or two calls each (label lookups
# reuse a per-invocation label cache, so at most one extra GET /labels).
#
# Env overrides (mainly for the offline test tier):
#   GITEA_TRACKER_STATE   events snapshot path (default: <repo>/work/.gitea-events-state)
#   GITEA_CURL            curl binary/shim to use (default: curl)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GITEA_SITE="${GITEA_SITE:-}"
GITEA_TOKEN="${GITEA_TOKEN:-}"
GITEA_OWNER="${GITEA_OWNER:-}"
GITEA_REPO="${GITEA_REPO:-}"
GITEA_TICKET_PREFIX="${GITEA_TICKET_PREFIX:-AITBC}"

STATUSES_FILE="${GITEA_TRACKER_STATUSES:-$REPO_ROOT/profiles/neutral/adapters/statuses.yaml}"
EVENTS_STATE="${GITEA_TRACKER_STATE:-$REPO_ROOT/work/.gitea-events-state}"
CURL_BIN="${GITEA_CURL:-curl}"

# Terminal statuses close the native Gitea issue (cosmetic mirror only).
is_terminal_status() {
    case "$1" in
        Done|"Epic Done"|Canceled|Rejected) return 0 ;;
        *) return 1 ;;
    esac
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

# --- Secret hygiene -----------------------------------------------------------
scrub_secrets() {
    if [ -n "$GITEA_TOKEN" ]; then
        sed -e "s/${GITEA_TOKEN//\//\\/}/***REDACTED***/g"
    else
        cat
    fi
}

require_creds() {
    [ -n "$GITEA_SITE" ]  || die "GITEA_SITE is not set (e.g. https://gitea.bubuit.net)"
    [ -n "$GITEA_TOKEN" ] || die "GITEA_TOKEN is not set (human-provisioned; never stored in repo)"
    [ -n "$GITEA_OWNER" ] || die "GITEA_OWNER is not set"
    [ -n "$GITEA_REPO" ]  || die "GITEA_REPO is not set"
}

# =============================================================================
# HTTP layer
# =============================================================================
# http_call <METHOD> <path> [<json-body>] — authenticated Gitea REST call;
# prints the raw response body on stdout. Token delivered via --config (never
# argv), so it never appears in `ps` or curl's verbose trace. Non-2xx dies with
# a scrubbed message. <path> is relative to $GITEA_SITE/api/v1.
http_call() {
    require_creds
    local method="$1" path="$2" body="${3:-}"
    local url="${GITEA_SITE%/}/api/v1${path}"

    local cfg out err code
    cfg="$(mktemp "${TMPDIR:-/tmp}/gitea-cfg.XXXXXX")"
    out="$(mktemp "${TMPDIR:-/tmp}/gitea-out.XXXXXX")"
    err="$(mktemp "${TMPDIR:-/tmp}/gitea-err.XXXXXX")"

    {
        printf 'header = "Authorization: token %s"\n' "$GITEA_TOKEN"
        printf 'header = "Accept: application/json"\n'
        if [ -n "$body" ]; then
            printf 'header = "Content-Type: application/json"\n'
        fi
    } > "$cfg"
    chmod 600 "$cfg"

    local bodyfile=""
    set +e
    if [ -n "$body" ]; then
        bodyfile="$(mktemp "${TMPDIR:-/tmp}/gitea-body.XXXXXX")"
        printf '%s' "$body" > "$bodyfile"
        code="$("$CURL_BIN" --config "$cfg" -sS -o "$out" -w '%{http_code}' \
            -X "$method" --data-binary "@$bodyfile" "$url" 2>"$err")"
    else
        code="$("$CURL_BIN" --config "$cfg" -sS -o "$out" -w '%{http_code}' \
            -X "$method" "$url" 2>"$err")"
    fi
    local rc=$?
    set -e

    [ -z "$bodyfile" ] || rm -f "$bodyfile"
    rm -f "$cfg"

    if [ "$rc" -ne 0 ]; then
        local msg
        msg="$(scrub_secrets < "$err")"
        rm -f "$out" "$err"
        die "gitea request failed (curl exit $rc): $msg"
    fi

    case "$code" in
        2*) cat "$out"; rm -f "$out" "$err" ;;
        404) rm -f "$out" "$err"; return 44 ;;
        *)
            local msg
            msg="$(scrub_secrets < "$out" | head -c 500)"
            rm -f "$out" "$err"
            die "gitea API $method $path returned HTTP $code: $msg"
            ;;
    esac
}

# =============================================================================
# Python JSON helpers — all JSON parse/build goes through here (no jq).
# =============================================================================
py() {
    python3 -c "$@"
}

json_str() {
    py 'import sys, json; sys.stdout.write(json.dumps(sys.argv[1]))' "$1"
}

# json_get <python-expr> — read JSON from stdin, evaluate a python expression
# over variable `d`. Missing/None -> empty string.
json_get() {
    py '
import sys, json
d = json.load(sys.stdin)
expr = sys.argv[1]
try:
    v = eval(expr, {"__builtins__": {}}, {"d": d})
except Exception:
    v = ""
if v is None:
    v = ""
sys.stdout.write(str(v))
' "$1"
}

# norm_ts <iso-with-offset> — normalize a Gitea timestamp
# (e.g. 2026-06-12T11:43:31+02:00) to the mock's canonical UTC form.
norm_ts() {
    py '
import sys, datetime
s = sys.argv[1]
if not s:
    sys.exit(0)
dt = datetime.datetime.fromisoformat(s)
if dt.tzinfo is not None:
    dt = dt.astimezone(datetime.timezone.utc)
sys.stdout.write(dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
' "$1"
}

# =============================================================================
# Id formatting — canonical id is "<PREFIX>-<gitea issue number>"; identity is
# the Gitea number, the prefix is cosmetic only (Gitea has one issue-number
# sequence per repo, so unlike the mock adapter, --prefix does not create a
# separate namespace).
# =============================================================================
fmt_id() { printf '%s-%s' "$GITEA_TICKET_PREFIX" "$1"; }

# gitea_num <id> — strip any leading "<PFX>-" and print the bare issue number.
gitea_num() {
    local n="$1"
    case "$n" in
        *-*) n="${n##*-}" ;;
    esac
    case "$n" in
        ''|*[!0-9]*) die "not a valid ticket id: $1" ;;
    esac
    echo "$n"
}

require_ticket() {
    local num
    num="$(gitea_num "$1")"
    http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" > /dev/null \
        || die "ticket not found: $1"
}

# =============================================================================
# Label cache — one GET /labels per invocation, reused by every label lookup.
# Stored as a TSV temp file "id<TAB>name"; bash 3.2 has no associative arrays,
# so lookups go through grep (same portability discipline as mock/jira).
# =============================================================================
LABEL_CACHE=""

load_label_cache() {
    [ -z "$LABEL_CACHE" ] || return 0
    LABEL_CACHE="$(mktemp "${TMPDIR:-/tmp}/gitea-labels.XXXXXX")"
    http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/labels?limit=200" | py '
import sys, json
for l in json.load(sys.stdin):
    sys.stdout.write("%d\t%s\n" % (l["id"], l["name"]))
' > "$LABEL_CACHE"
}

# label_id <name> — id of an existing label, or empty if not found.
label_id() {
    load_label_cache
    awk -F'\t' -v n="$1" '$2 == n { print $1; found=1; exit } END { if (!found) exit 1 }' "$LABEL_CACHE" 2>/dev/null || true
}

# require_label_id <name> — like label_id but dies with a clear "run setup"
# hint when the label is missing (documented prerequisite).
require_label_id() {
    local id
    id="$(label_id "$1")"
    [ -n "$id" ] || die "required label '$1' not found on $GITEA_OWNER/$GITEA_REPO -- run 'scripts/gitea-tracker.sh setup' first"
    echo "$id"
}

# =============================================================================
# Status machine (statuses.yaml) — identical parsing to mock-tracker.sh.
# =============================================================================
require_statuses_file() {
    [ -f "$STATUSES_FILE" ] || die "status machine not found: $STATUSES_FILE"
}

allowed_next() {
    awk -v from="$1" '
        /^  - name: / { cur = substr($0, 11); in_next = 0; next }
        cur == from && /^    next:/ { in_next = 1; next }
        cur == from && in_next {
            if ($0 ~ /^      - /) { print substr($0, 9) }
            else if ($0 !~ /^[ ]*(#|$)/) { in_next = 0 }
        }
    ' "$STATUSES_FILE"
}

status_exists() {
    grep -q "^  - name: $1\$" "$STATUSES_FILE"
}

all_statuses() {
    sed -n 's/^  - name: //p' "$STATUSES_FILE"
}

# =============================================================================
# Setup — idempotent label provisioning.
# =============================================================================
cmd_setup() {
    require_statuses_file
    load_label_cache
    local created=0 skipped=0

    ensure_label() {
        local name="$1" color="$2" excl="$3"
        if [ -n "$(label_id "$name")" ]; then
            skipped=$((skipped + 1))
            return 0
        fi
        local body
        body="$(py '
import sys, json
name, color, excl = sys.argv[1], sys.argv[2], sys.argv[3] == "true"
sys.stdout.write(json.dumps({"name": name, "color": color, "exclusive": excl}))
' "$name" "$color" "$excl")"
        http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/labels" "$body" > /dev/null
        # Invalidate the cache so subsequent lookups in this same run see it.
        rm -f "$LABEL_CACHE"; LABEL_CACHE=""
        load_label_cache
        created=$((created + 1))
    }

    local s
    while IFS= read -r s; do
        [ -n "$s" ] || continue
        ensure_label "status/$s" "#4a6fa5" true
    done < <(all_statuses)

    ensure_label "type/epic" "#8e44ad" true
    ensure_label "type/ticket" "#2980b9" true
    ensure_label "type/subtask" "#16a085" true

    ensure_label "lane/normal" "#95a5a6" true
    ensure_label "lane/fastlane" "#e67e22" true

    ensure_label "role/be-developer" "#27ae60" true
    ensure_label "role/fe-developer" "#2980b9" true
    ensure_label "role/data-engineer" "#8e44ad" true

    ensure_label "priority/hotfix" "#c0392b" true
    ensure_label "priority/high" "#e74c3c" true
    ensure_label "priority/normal" "#7f8c8d" true
    ensure_label "priority/low" "#95a5a6" true

    ensure_label "flag/design" "#f39c12" false
    ensure_label "flag/security" "#c0392b" false
    ensure_label "flag/data" "#2980b9" false
    ensure_label "flag/skip-review" "#7f8c8d" false
    ensure_label "flag/skip-test" "#7f8c8d" false

    ensure_label "ac-blocking" "#d35400" false
    ensure_label "orchestrator-ready" "#27ae60" false

    echo "setup: $created label(s) created, $skipped already present"
}

# =============================================================================
# Metadata block (parent/depends_on/links/iteration_cap) embedded as a hidden
# HTML comment at the top of the issue body.
# =============================================================================
META_BEGIN='<!-- aitbc-tracker:meta'
META_END='-->'

# meta_get <body-text> <key> — print the value of one metadata key, or empty.
meta_get() {
    printf '%s\n' "$1" | awk -v key="$2" -v begin="$META_BEGIN" -v end="$META_END" '
        $0 == begin { inblk = 1; next }
        inblk && $0 == end { exit }
        inblk && index($0, key ": ") == 1 { print substr($0, length(key) + 3); exit }
    '
}

# meta_block <body-text> — print the raw metadata block (or empty if absent).
meta_block() {
    printf '%s\n' "$1" | awk -v begin="$META_BEGIN" -v end="$META_END" '
        $0 == begin { inblk = 1 }
        inblk { print }
        inblk && $0 == end { exit }
    '
}

# strip_meta <body-text> — print the body with the metadata block removed.
strip_meta() {
    printf '%s\n' "$1" | awk -v begin="$META_BEGIN" -v end="$META_END" '
        $0 == begin { inblk = 1; next }
        inblk && $0 == end { inblk = 0; next }
        inblk { next }
        { print }
    '
}

# rebuild_meta <old-body> <key> <value> — return a new body with metadata key
# set to value (creating the block if absent), rest of the body unchanged.
rebuild_meta() {
    local body="$1" key="$2" value="$3"
    local rest parent deps links itcap
    rest="$(strip_meta "$body")"
    parent="$(meta_get "$body" parent)"
    deps="$(meta_get "$body" depends_on)"
    links="$(meta_get "$body" links)"
    itcap="$(meta_get "$body" iteration_cap)"
    case "$key" in
        parent) parent="$value" ;;
        depends_on) deps="$value" ;;
        links) links="$value" ;;
        iteration_cap) itcap="$value" ;;
    esac
    {
        echo "$META_BEGIN"
        [ -z "$parent" ] || echo "parent: $parent"
        [ -z "$deps" ] || echo "depends_on: $deps"
        [ -z "$links" ] || echo "links: $links"
        [ -z "$itcap" ] || echo "iteration_cap: $itcap"
        echo "$META_END"
        echo ""
        printf '%s' "$rest"
    }
}

# =============================================================================
# Ticket assembly (get) — mock-compatible frontmatter + body + comments text.
# =============================================================================
cmd_get() {
    local id="$1" num
    num="$(gitea_num "$id")"
    local issue
    issue="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")" \
        || die "ticket not found: $id"

    local title body created updated
    title="$(printf '%s' "$issue" | json_get 'd["title"]')"
    body="$(printf '%s' "$issue" | json_get 'd["body"]')"
    created="$(norm_ts "$(printf '%s' "$issue" | json_get 'd["created_at"]')")"
    updated="$(norm_ts "$(printf '%s' "$issue" | json_get 'd["updated_at"]')")"

    local labels type_v status_v lane_v role_v priority_v ac_blocking_v flags_l free_l
    labels="$(printf '%s' "$issue" | py '
import sys, json
d = json.load(sys.stdin)
for l in d.get("labels") or []:
    sys.stdout.write(l["name"] + "\n")
')"
    type_v="$(printf '%s\n' "$labels" | sed -n 's#^type/##p' | head -1)"
    status_v="$(printf '%s\n' "$labels" | sed -n 's#^status/##p' | head -1)"
    lane_v="$(printf '%s\n' "$labels" | sed -n 's#^lane/##p' | head -1)"
    role_v="$(printf '%s\n' "$labels" | sed -n 's#^role/##p' | head -1)"
    priority_v="$(printf '%s\n' "$labels" | sed -n 's#^priority/##p' | head -1)"
    flags_l="$(printf '%s\n' "$labels" | sed -n 's#^flag/##p' | paste -sd, - | sed 's/,/, /g')"
    ac_blocking_v="false"
    printf '%s\n' "$labels" | grep -qxF "ac-blocking" && ac_blocking_v="true"
    free_l="$(printf '%s\n' "$labels" | grep -vE '^(type|status|lane|role|priority|flag)/' | grep -vxF "ac-blocking" | grep -v '^$' | paste -sd, - | sed 's/,/, /g')"

    [ -n "$lane_v" ] || lane_v="normal"

    local parent deps links itcap
    parent="$(meta_get "$body" parent)"
    deps="$(meta_get "$body" depends_on)"
    [ -n "$deps" ] || deps="[]"
    links="$(meta_get "$body" links)"
    [ -n "$links" ] || links="[]"
    itcap="$(meta_get "$body" iteration_cap)"

    echo "---"
    echo "id: $(fmt_id "$num")"
    echo "type: $type_v"
    echo "title: $title"
    echo "status: $status_v"
    if [ -n "$parent" ]; then echo "parent: $parent"; else echo "parent:"; fi
    echo "lane: $lane_v"
    [ -z "$role_v" ] || echo "role: $role_v"
    [ -z "$flags_l" ] || echo "flags: [$flags_l]"
    [ -z "$free_l" ] || echo "labels: [$free_l]"
    [ "$ac_blocking_v" != "true" ] || echo "ac_blocking: true"
    [ -z "$priority_v" ] || echo "priority: $priority_v"
    [ -z "$itcap" ] || echo "iteration_cap: $itcap"
    echo "depends_on: $deps"
    echo "links: $links"
    echo "created: $created"
    echo "updated: $updated"
    echo "---"
    echo ""
    strip_meta "$body" | sed '/^$/{ N; /^\n$/D }'
    echo ""
    echo "## Comments"

    local cpage=1 cout
    cout="$(mktemp "${TMPDIR:-/tmp}/gitea-comments.XXXXXX")"
    : > "$cout"
    while :; do
        local page_json n
        page_json="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/comments?page=$cpage&limit=50")"
        n="$(printf '%s' "$page_json" | py 'import sys,json; d=json.load(sys.stdin); print(len(d))')"
        printf '%s' "$page_json" | py '
import sys, json
for c in json.load(sys.stdin):
    sys.stdout.write(c["body"])
    sys.stdout.write("\x00")
' >> "$cout"
        [ "$n" -ge 50 ] || break
        cpage=$((cpage + 1))
    done
    if [ -s "$cout" ]; then
        python3 -c '
import sys
data = open(sys.argv[1], "rb").read()
parts = [p for p in data.split(b"\x00") if p]
for p in parts:
    sys.stdout.write("\n")
    sys.stdout.write(p.decode())
    sys.stdout.write("\n")
' "$cout"
    fi
    rm -f "$cout"
}

# =============================================================================
# Search
# =============================================================================
cmd_search() {
    local f_status="" f_type="" f_parent="" f_text="" f_label="" f_lane=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --status) [ $# -ge 2 ] || die "search: --status requires a value"; f_status="$2"; shift 2 ;;
            --type)   [ $# -ge 2 ] || die "search: --type requires a value";   f_type="$2";   shift 2 ;;
            --parent) [ $# -ge 2 ] || die "search: --parent requires a value"; f_parent="$2"; shift 2 ;;
            --text)   [ $# -ge 2 ] || die "search: --text requires a value";   f_text="$2";   shift 2 ;;
            --label)  [ $# -ge 2 ] || die "search: --label requires a value";  f_label="$2";  shift 2 ;;
            --lane)   [ $# -ge 2 ] || die "search: --lane requires a value";   f_lane="$2";   shift 2 ;;
            *) die "search: unknown argument: $1" ;;
        esac
    done

    local qs="type=issues&state=all&limit=50"
    [ -z "$f_status" ] || qs="$qs&labels=$(py 'import sys,urllib.parse; sys.stdout.write(urllib.parse.quote(sys.argv[1]))' "status/$f_status")"
    [ -z "$f_text" ] || qs="$qs&q=$(py 'import sys,urllib.parse; sys.stdout.write(urllib.parse.quote(sys.argv[1]))' "$f_text")"

    # us: internal-only row delimiter (ASCII Unit Separator, \x1f). NOT a bare
    # tab: bash `read` treats tab as "IFS whitespace" per POSIX regardless of
    # what IFS is set to, so a genuinely EMPTY interior field (e.g. a ticket
    # with no type/ label) collapses two adjacent tabs into one delimiter and
    # shifts every following field left by one -- silently corrupting the row.
    # \x1f isn't in that whitespace class, so empty fields round-trip intact.
    # This is purely an internal format; the public tab-separated output
    # contract (ABS-389) is unaffected -- it's assembled fresh via printf/cut
    # below, never re-parsed with `read`.
    local page=1 us rows
    us="$(printf '\x1f')"
    rows="$(mktemp "${TMPDIR:-/tmp}/gitea-search.XXXXXX")"
    while :; do
        local batch n
        batch="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues?$qs&page=$page")"
        n="$(printf '%s' "$batch" | py 'import sys,json; print(len(json.load(sys.stdin)))')"
        printf '%s' "$batch" | py '
import sys, json
for i in json.load(sys.stdin):
    labels = [l["name"] for l in (i.get("labels") or [])]
    def scoped(pfx):
        for l in labels:
            if l.startswith(pfx):
                return l[len(pfx):]
        return ""
    typ = scoped("type/")
    status = scoped("status/")
    lane = scoped("lane/") or "normal"
    priority = scoped("priority/") or "normal"
    sys.stdout.write("\x1f".join([
        str(i["number"]), typ, status, lane, priority, i["created_at"], i["title"],
    ]))
    sys.stdout.write("\n")
' >> "$rows"
        [ "$n" -ge 50 ] || break
        page=$((page + 1))
        [ "$page" -le 50 ] || { echo "WARN: search stopping after 50 pages" >&2; break; }
    done

    # Filter (type/parent/label/lane) + priority-rank + emit in canonical order.
    while IFS="$us" read -r num typ status lane priority created title; do
        [ -n "$num" ] || continue
        [ -z "$f_type" ]  || [ "$typ" = "$f_type" ] || continue
        [ -z "$f_lane" ]  || [ "$lane" = "$f_lane" ] || continue
        if [ -n "$f_parent" ] || [ -n "$f_label" ]; then
            local raw
            raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
            if [ -n "$f_parent" ]; then
                local body p
                body="$(printf '%s' "$raw" | json_get 'd["body"]')"
                p="$(meta_get "$body" parent)"
                [ "$p" = "$f_parent" ] || continue
            fi
            if [ -n "$f_label" ]; then
                printf '%s' "$raw" | py '
import sys, json
d = json.load(sys.stdin)
names = [l["name"] for l in (d.get("labels") or [])]
sys.exit(0 if sys.argv[1] in names else 1)
' "$f_label" || continue
            fi
        fi
        local rank
        case "$priority" in hotfix) rank=0 ;; high) rank=1 ;; low) rank=3 ;; *) rank=2 ;; esac
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$rank" "$created" "$(fmt_id "$num")" "$typ" "$status" "$priority" "$title"
    done < "$rows" | sort -t "$(printf '\t')" -k1,1 -k2,2 -s | cut -f3-
    rm -f "$rows"
}

# =============================================================================
# Create
# =============================================================================
cmd_create() {
    local type="" title="" prefix="" parent="" role="" body_file="" flags="" labels="" ac_blocking="" lane="normal" priority=
    while [ $# -gt 0 ]; do
        case "$1" in
            --type)      [ $# -ge 2 ] || die "create: --type requires a value";      type="$2";      shift 2 ;;
            --title)     [ $# -ge 2 ] || die "create: --title requires a value";     title="$2";     shift 2 ;;
            --prefix)    [ $# -ge 2 ] || die "create: --prefix requires a value";    prefix="$2";    shift 2 ;;
            --parent)    [ $# -ge 2 ] || die "create: --parent requires a value";    parent="$2";    shift 2 ;;
            --role)      [ $# -ge 2 ] || die "create: --role requires a value";      role="$2";      shift 2 ;;
            --body-file) [ $# -ge 2 ] || die "create: --body-file requires a value"; body_file="$2"; shift 2 ;;
            --lane)
                [ $# -ge 2 ] || die "create: --lane requires a value"
                case "$2" in normal|fastlane) lane="$2" ;; *) die "create: invalid lane '$2' (normal|fastlane)" ;; esac
                shift 2 ;;
            --flag)
                [ $# -ge 2 ] || die "create: --flag requires a value"
                case "$2" in design|security|data|skip-review|skip-test) ;; *) die "create: invalid flag '$2'" ;; esac
                case "$flags" in *"$2"*) ;; "") flags="$2" ;; *) flags="$flags $2" ;; esac
                shift 2 ;;
            --label)
                [ $# -ge 2 ] || die "create: --label requires a value"
                case "$2" in ""|*[!A-Za-z0-9._:-]*) die "create: invalid label '$2'" ;; esac
                case " $labels " in *" $2 "*) ;; *) labels="$labels $2" ;; esac
                shift 2 ;;
            --ac-blocking) ac_blocking="true"; shift ;;
            --priority)
                [ $# -ge 2 ] || die "create: --priority requires a value"
                case "$2" in hotfix|high|normal|low) priority="$2" ;; *) die "create: invalid priority '$2'" ;; esac
                shift 2 ;;
            *) die "create: unknown argument: $1" ;;
        esac
    done
    [ -n "$type" ] || die "create: --type is required (epic|ticket|subtask)"
    case "$type" in epic|ticket|subtask) ;; *) die "create: invalid type '$type'" ;; esac
    [ -n "$title" ] || die "create: --title is required"
    [ -z "$parent" ] || require_ticket "$parent"
    if [ -n "$role" ]; then
        case "$role" in be-developer|fe-developer|data-engineer) ;; *) die "create: invalid role '$role'" ;; esac
    fi
    [ -z "$body_file" ] || [ -f "$body_file" ] || die "create: --body-file not found: $body_file"

    local flags_csv="" ; for f in $flags; do flags_csv="${flags_csv:+$flags_csv, }$f"; done
    local labels_csv="" ; for l in $labels; do labels_csv="${labels_csv:+$labels_csv, }$l"; done

    local body_text
    if [ -n "$body_file" ]; then
        body_text="$(cat "$body_file")"
    else
        body_text='## Goal

_TBD_

## Scope

**In scope:**

- _TBD_

**Out of scope:**

- _TBD_

## Acceptance Criteria

- [ ] _TBD_

## Definition of Done

- [ ] _TBD_

## Test Plan

- _TBD_

## ADR Context

_None embedded yet._'
    fi
    if [ -n "$parent" ]; then
        body_text="$(rebuild_meta "

$body_text" parent "$parent")"
    fi

    local label_ids
    load_label_cache
    label_ids="$(require_label_id "type/$type")"
    label_ids="$label_ids,$(require_label_id "status/Backlog")"
    label_ids="$label_ids,$(require_label_id "lane/$lane")"
    [ -z "$role" ] || label_ids="$label_ids,$(require_label_id "role/$role")"
    [ -z "$priority" ] || label_ids="$label_ids,$(require_label_id "priority/$priority")"
    [ -z "$ac_blocking" ] || label_ids="$label_ids,$(require_label_id "ac-blocking")"
    for f in $flags; do label_ids="$label_ids,$(require_label_id "flag/$f")"; done
    for l in $labels; do
        local lid; lid="$(label_id "$l")"
        if [ -z "$lid" ]; then
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/labels" \
                "$(py 'import sys,json; sys.stdout.write(json.dumps({"name": sys.argv[1], "color": "#3498db", "exclusive": False}))' "$l")" > /dev/null
            LABEL_CACHE=""; load_label_cache
            lid="$(label_id "$l")"
        fi
        label_ids="$label_ids,$lid"
    done

    local body
    body="$(py '
import sys, json
title, text, ids = sys.argv[1], sys.argv[2], sys.argv[3]
label_ids = [int(x) for x in ids.split(",") if x]
sys.stdout.write(json.dumps({"title": title, "body": text, "labels": label_ids}))
' "$title" "$body_text" "$label_ids")"

    local resp num
    resp="$(http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues" "$body")"
    num="$(printf '%s' "$resp" | json_get 'd["number"]')"
    fmt_id "$num"
}

# =============================================================================
# Update
# =============================================================================
cmd_update() {
    local id="$1" field="$2" value="$3" num
    num="$(gitea_num "$id")"
    require_ticket "$id"
    case "$field" in
        status) die "update: status changes must go through 'transition' (validated + reasoned)" ;;
        id|created|updated) die "update: field '$field' is managed by the tracker" ;;
        title)
            http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" "$(json_str_field title "$value")" > /dev/null
            echo "$id: title updated"; return ;;
        type)
            case "$value" in epic|ticket|subtask) ;; *) die "update: invalid type '$value'" ;; esac
            load_label_cache
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                "$(py 'import sys,json; sys.stdout.write(json.dumps({"labels":[int(sys.argv[1])]}))' "$(require_label_id "type/$value")")" > /dev/null
            echo "$id: type updated"; return ;;
        lane)
            case "$value" in normal|fastlane) ;; *) die "update: lane must be 'normal' or 'fastlane'" ;; esac
            load_label_cache
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                "$(py 'import sys,json; sys.stdout.write(json.dumps({"labels":[int(sys.argv[1])]}))' "$(require_label_id "lane/$value")")" > /dev/null
            echo "$id: lane updated"; return ;;
        priority)
            case "$value" in hotfix|high|normal|low) ;; *) die "update: invalid priority '$value'" ;; esac
            load_label_cache
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                "$(py 'import sys,json; sys.stdout.write(json.dumps({"labels":[int(sys.argv[1])]}))' "$(require_label_id "priority/$value")")" > /dev/null
            echo "$id: priority updated"; return ;;
        flags)
            case "$value" in "["*"]") ;; *) die "update: flags value must be a list like '[design, security]'" ;; esac
            load_label_cache
            local ids="" member
            for member in $(printf '%s' "$value" | tr -d '[],'); do
                case "$member" in design|security|data|skip-review|skip-test) ;; *) die "update: invalid flag '$member'" ;; esac
                ids="$ids,$(require_label_id "flag/$member")"
            done
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                "$(py 'import sys,json; ids=[int(x) for x in sys.argv[1].split(",") if x]; sys.stdout.write(json.dumps({"labels": ids}))' "${ids#,}")" > /dev/null
            echo "$id: flags updated"; return ;;
        labels)
            case "$value" in "["*"]") ;; *) die "update: labels value must be a list like '[orchestrator-ready]'" ;; esac
            load_label_cache
            local ids="" lbl lid
            for lbl in $(printf '%s' "$value" | tr -d '[],'); do
                case "$lbl" in *[!A-Za-z0-9._:-]*) die "update: invalid label '$lbl'" ;; esac
                lid="$(label_id "$lbl")"
                if [ -z "$lid" ]; then
                    http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/labels" \
                        "$(py 'import sys,json; sys.stdout.write(json.dumps({"name": sys.argv[1], "color": "#3498db", "exclusive": False}))' "$lbl")" > /dev/null
                    LABEL_CACHE=""; load_label_cache
                    lid="$(label_id "$lbl")"
                fi
                ids="$ids,$lid"
            done
            http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                "$(py 'import sys,json; ids=[int(x) for x in sys.argv[1].split(",") if x]; sys.stdout.write(json.dumps({"labels": ids}))' "${ids#,}")" > /dev/null
            echo "$id: labels updated"; return ;;
        ac_blocking)
            case "$value" in
                true)
                    load_label_cache
                    http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
                        "$(py 'import sys,json; sys.stdout.write(json.dumps({"labels":[int(sys.argv[1])]}))' "$(require_label_id "ac-blocking")")" > /dev/null
                    ;;
                false)
                    load_label_cache
                    local lid; lid="$(label_id "ac-blocking")"
                    [ -z "$lid" ] || http_call DELETE "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels/$lid" > /dev/null
                    ;;
                *) die "update: ac_blocking must be 'true' or 'false'" ;;
            esac
            echo "$id: ac_blocking updated"; return ;;
        parent|depends_on|links|iteration_cap)
            local raw body
            raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
            body="$(printf '%s' "$raw" | json_get 'd["body"]')"
            body="$(rebuild_meta "$body" "$field" "$value")"
            http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" "$(json_str_field body "$body")" > /dev/null
            echo "$id: $field updated"; return ;;
        body|body-file)
            local text raw old_body new_body
            text="$value"
            [ "$field" = "body-file" ] && { [ -f "$value" ] || die "update: body-file not found: $value"; text="$(cat "$value")"; }
            raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
            old_body="$(printf '%s' "$raw" | json_get 'd["body"]')"
            local meta; meta="$(meta_block "$old_body")"
            if [ -n "$meta" ]; then
                new_body="$meta

$text"
            else
                new_body="$text"
            fi
            http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" "$(json_str_field body "$new_body")" > /dev/null
            echo "$id: body updated"; return ;;
        *) die "update: unknown field '$field' (title|type|parent|depends_on|links|lane|flags|labels|ac_blocking|priority|iteration_cap|body|body-file)" ;;
    esac
}

# json_str_field <key> <value> — {"key": "value"} as compact JSON.
json_str_field() {
    py 'import sys, json; sys.stdout.write(json.dumps({sys.argv[1]: sys.argv[2]}))' "$1" "$2"
}

# =============================================================================
# Comment
# =============================================================================
cmd_comment() {
    local id="$1"; shift
    local num; num="$(gitea_num "$id")"
    require_ticket "$id"
    local kind="" actor="" body="" body_file="" have_body=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --kind)  [ $# -ge 2 ] || die "comment: --kind requires a value";  kind="$2";  shift 2 ;;
            --actor) [ $# -ge 2 ] || die "comment: --actor requires a value"; actor="$2"; shift 2 ;;
            --body)  [ $# -ge 2 ] || die "comment: --body requires a value";  body="$2"; have_body=1; shift 2 ;;
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
    case "$kind" in
        understanding|transition-reason|gate-results|handoff|decision|notification) ;;
        follow-up|bsa-decision|skip) ;;
        claim) ;;
        invariant-violation) ;;
        *) die "comment: invalid kind '$kind'" ;;
    esac
    local now full
    now="$(timestamp)"
    full="### $now | kind: $kind | actor: $actor

$body"
    http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/comments" "$(json_str_field body "$full")" > /dev/null
    echo "$id: comment added"
}

# =============================================================================
# Transition
# =============================================================================
cmd_transition() {
    local id="$1" to="$2"; shift 2
    local num; num="$(gitea_num "$id")"
    require_ticket "$id"
    require_statuses_file
    local actor="" reason="" reason_file="" have_reason=0 expect_from=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --actor)  [ $# -ge 2 ] || die "transition: --actor requires a value";  actor="$2";  shift 2 ;;
            --reason) [ $# -ge 2 ] || die "transition: --reason requires a value"; reason="$2"; have_reason=1; shift 2 ;;
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
    status_exists "$to" || die "transition: unknown status '$to' (see $STATUSES_FILE)"

    local issue from
    issue="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
    from="$(printf '%s' "$issue" | py '
import sys, json
d = json.load(sys.stdin)
for l in d.get("labels") or []:
    if l["name"].startswith("status/"):
        sys.stdout.write(l["name"][len("status/"):])
        break
')"

    if [ -n "$expect_from" ] && [ "$from" != "$expect_from" ]; then
        echo "$id: NOOP compare-and-set expect-from=$expect_from actual=$from (skipped $to)"
        return 0
    fi
    [ "$from" != "$to" ] || die "transition: $id is already in '$to'"
    if ! allowed_next "$from" | grep -qxF "$to"; then
        die "transition: illegal transition '$from' -> '$to' for $id (allowed from '$from': $(allowed_next "$from" | paste -sd, -))"
    fi

    load_label_cache
    http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/labels" \
        "$(py 'import sys,json; sys.stdout.write(json.dumps({"labels":[int(sys.argv[1])]}))' "$(require_label_id "status/$to")")" > /dev/null

    local want_state="open"
    is_terminal_status "$to" && want_state="closed"
    http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" "$(py 'import sys,json; sys.stdout.write(json.dumps({"state": sys.argv[1]}))' "$want_state")" > /dev/null

    local now full
    now="$(timestamp)"
    full="### $now | kind: transition-reason | actor: $actor

Transition: $from -> $to. Reason: $reason"
    http_call POST "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num/comments" "$(json_str_field body "$full")" > /dev/null

    echo "$id: $from -> $to"
}

# =============================================================================
# Link
# =============================================================================
cmd_link() {
    local id="$1" other="$2" ltype="$3" num
    num="$(gitea_num "$id")"
    require_ticket "$id"
    case "$ltype" in
        parent-child|depends-on|relates) require_ticket "$other" ;;
        origin-review|pr) ;;
        *) die "link: invalid link type '$ltype' (parent-child|depends-on|origin-review|pr|relates)" ;;
    esac

    local raw body links entry
    raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
    body="$(printf '%s' "$raw" | json_get 'd["body"]')"
    links="$(meta_get "$body" links)"
    entry="$ltype:$other"
    case "$links" in
        *"$entry"*) echo "$id: already linked $entry"; return 0 ;;
        ''|'[]') links="[$entry]" ;;
        *) links="${links%]}, $entry]" ;;
    esac
    body="$(rebuild_meta "$body" links "$links")"

    if [ "$ltype" = "depends-on" ]; then
        local deps
        deps="$(meta_get "$body" depends_on)"
        case "$deps" in
            *"$other"*) ;;
            ''|'[]') body="$(rebuild_meta "$body" depends_on "[$other]")" ;;
            *) body="$(rebuild_meta "$body" depends_on "${deps%]}, $other]")" ;;
        esac
    fi
    if [ "$ltype" = "parent-child" ]; then
        body="$(rebuild_meta "$body" parent "$other")"
    fi

    http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" "$(json_str_field body "$body")" > /dev/null
    echo "$id: linked $entry"
}

# =============================================================================
# children / parent / child-count
# =============================================================================
cmd_children() {
    local epic="$1"
    require_ticket "$epic"
    # us: internal-only row delimiter (see cmd_search's comment for why a bare
    # tab is unsafe -- bash `read` collapses consecutive tabs as IFS
    # whitespace, corrupting rows where `status` is empty, e.g. a ticket
    # created outside this adapter with no status/ label).
    local page=1 found=0 us
    us="$(printf '\x1f')"
    while :; do
        local batch n
        batch="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues?type=issues&state=all&limit=50&page=$page")"
        n="$(printf '%s' "$batch" | py 'import sys,json; print(len(json.load(sys.stdin)))')"
        while IFS="$us" read -r num status title parent; do
            [ -n "$num" ] || continue
            [ "$parent" = "$epic" ] || continue
            printf '%s\t[%s]\t%s\n' "$(fmt_id "$num")" "$status" "$title"
            found=1
        done < <(printf '%s' "$batch" | py '
import sys, json
for i in json.load(sys.stdin):
    labels = [l["name"] for l in (i.get("labels") or [])]
    status = ""
    for l in labels:
        if l.startswith("status/"):
            status = l[len("status/"):]
    print("\x1f".join([str(i["number"]), status, i["title"], ""]))
' | while IFS="$us" read -r num status title _; do
            local raw body parent
            raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
            body="$(printf '%s' "$raw" | json_get 'd["body"]')"
            parent="$(meta_get "$body" parent)"
            printf '%s%s%s%s%s%s%s\n' "$num" "$us" "$status" "$us" "$title" "$us" "$parent"
        done)
        [ "$n" -ge 50 ] || break
        page=$((page + 1))
    done
    [ "$found" -eq 1 ] || echo "(no children)" >&2
}

cmd_parent() {
    local num raw body
    num="$(gitea_num "$1")"
    require_ticket "$1"
    raw="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num")"
    body="$(printf '%s' "$raw" | json_get 'd["body"]')"
    meta_get "$body" parent
}

cmd_child_count() {
    local epic="$1" count
    require_ticket "$epic"
    count="$(cmd_children "$epic" 2>/dev/null | grep -c . || true)"
    case "$(cmd_children "$epic" 2>&1 >/dev/null)" in
        "(no children)") echo 0; return ;;
    esac
    echo "$count"
}

# =============================================================================
# assign
# =============================================================================
cmd_assign() {
    local id="$1" account_id="$2" num
    num="$(gitea_num "$id")"
    require_ticket "$id"
    if [ -z "$account_id" ]; then
        echo "$id: assign no-op (empty accountId)"
        return 0
    fi
    http_call PATCH "/repos/$GITEA_OWNER/$GITEA_REPO/issues/$num" \
        "$(py 'import sys,json; sys.stdout.write(json.dumps({"assignees":[sys.argv[1]]}))' "$account_id")" > /dev/null
    echo "$id: assignee set to $account_id"
}

# =============================================================================
# events — polling diff against a snapshot, same shape as mock/jira adapters.
# =============================================================================
cmd_events() {
    mkdir -p "$(dirname "$EVENTS_STATE")"
    local now current page=1
    now="$(timestamp)"
    current="$EVENTS_STATE.current.$$"
    : > "$current"
    while :; do
        local batch n
        batch="$(http_call GET "/repos/$GITEA_OWNER/$GITEA_REPO/issues?type=issues&state=all&limit=50&page=$page")"
        n="$(printf '%s' "$batch" | py 'import sys,json; print(len(json.load(sys.stdin)))')"
        printf '%s' "$batch" | py '
import sys, json
for i in json.load(sys.stdin):
    labels = [l["name"] for l in (i.get("labels") or [])]
    status = ""
    for l in labels:
        if l.startswith("status/"):
            status = l[len("status/"):]
    sys.stdout.write("%s\t%s\n" % (i["number"], status))
' >> "$current"
        [ "$n" -ge 50 ] || break
        page=$((page + 1))
    done

    if [ -f "$EVENTS_STATE" ]; then
        awk -F'\t' -v at="$now" -v state="$EVENTS_STATE" -v pfx="$GITEA_TICKET_PREFIX" '
            FILENAME == state { prev[$1] = $2; next }
            {
                id = pfx "-" $1
                if ($1 in prev) {
                    if (prev[$1] != $2)
                        printf "{ticket_id: %s, from: %s, to: %s, at: %s}\n", id, prev[$1], $2, at
                } else {
                    printf "{ticket_id: %s, from: null, to: %s, at: %s}\n", id, $2, at
                }
            }
        ' "$EVENTS_STATE" "$current"
    else
        awk -F'\t' -v at="$now" -v pfx="$GITEA_TICKET_PREFIX" '
            { printf "{ticket_id: %s-%s, from: null, to: %s, at: %s}\n", pfx, $1, $2, at }
        ' "$current"
    fi
    mv "$current" "$EVENTS_STATE"
}

# =============================================================================
# Dispatcher
# =============================================================================
usage() {
    cat <<'EOF'
gitea-tracker.sh — Gitea task-tracking adapter

Usage: scripts/gitea-tracker.sh <command> [args]

  setup                                     Idempotently provision every
                                             required label (statuses/type/
                                             lane/role/priority/flags/
                                             ac-blocking). Run once before
                                             first use; safe to re-run.
  get <id>
  search [--status S] [--type T] [--parent P] [--text Q] [--label L] [--lane L]
  create --type <epic|ticket|subtask> --title <title> [--prefix <PFX>] [--parent <id>]
         [--role <role>] [--body-file <path>] [--lane <normal|fastlane>]
         [--flag <flag>]... [--label <label>]... [--ac-blocking] [--priority <p>]
  update <id> <field> <value>
  comment <id> --kind <kind> --actor <actor> (--body <text> | --body-file <path>)
  transition <id> <to-status> --actor <actor> (--reason <text> | --reason-file <path>) [--expect-from <status>]
  link <id> <other> <link-type>
  children <epic-id>
  parent <id>
  child-count <id>
  events
  assign <id> <accountId>

Env: GITEA_SITE, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO, GITEA_TICKET_PREFIX (default AITBC)
EOF
}

main() {
    [ $# -ge 1 ] || { usage >&2; exit 1; }
    local cmd="$1"; shift
    case "$cmd" in
        setup)      [ $# -eq 0 ] || die "usage: setup";                          cmd_setup ;;
        get)        [ $# -eq 1 ] || die "usage: get <id>";                       cmd_get "$@" ;;
        search)     cmd_search "$@" ;;
        create)     cmd_create "$@" ;;
        update)     [ $# -eq 3 ] || die "usage: update <id> <field> <value>";    cmd_update "$@" ;;
        comment)    [ $# -ge 1 ] || die "usage: comment <id> --kind <kind> --actor <actor> (--body <text> | --body-file <path>)"; cmd_comment "$@" ;;
        transition) [ $# -ge 2 ] || die "usage: transition <id> <to-status> --actor <actor> (--reason <text> | --reason-file <path>)"; cmd_transition "$@" ;;
        link)       [ $# -eq 3 ] || die "usage: link <id> <other> <link-type>";  cmd_link "$@" ;;
        children)   [ $# -eq 1 ] || die "usage: children <epic-id>";             cmd_children "$@" ;;
        parent)      [ $# -eq 1 ] || die "usage: parent <id>";                    cmd_parent "$@" ;;
        child-count) [ $# -eq 1 ] || die "usage: child-count <id>";               cmd_child_count "$@" ;;
        events)     [ $# -eq 0 ] || die "usage: events";                         cmd_events ;;
        assign)     [ $# -eq 2 ] || die "usage: assign <id> <accountId>";       cmd_assign "$@" ;;
        help|--help|-h) usage ;;
        *) usage >&2; die "unknown command: $cmd" ;;
    esac
}

main "$@"
