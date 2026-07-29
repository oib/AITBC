#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Jira Cloud Task-Tracking Adapter (ABS-64)
# =============================================================================
# A drop-in $TRACKER_CMD implementing the nine canonical task-tracking
# operations (profiles/neutral/adapters/task-tracking.md) against the Jira
# Cloud REST API v3. Its CLI surface — subcommands, flags, output shapes, exit
# codes and error messages — mirrors scripts/mock-tracker.sh EXACTLY, so
# scripts/orchestrator.sh runs unmodified with:
#
#     TRACKER_CMD=scripts/jira-tracker.sh scripts/orchestrator.sh
#
# The mock adapter (scripts/mock-tracker.sh) is the conformance reference; this
# adapter is "correct" when it behaves the same from the caller's view.
#
# -----------------------------------------------------------------------------
# Prerequisites (zero third-party deps beyond these harness prerequisites):
#   - bash 3.2+
#   - curl          (HTTP client for the Jira REST API — the only network tool)
#   - python3       (JSON parse/serialize + ADF wrap/unwrap; already a declared
#                    harness prerequisite — see docs/sop/ORCHESTRATOR_SOP.md)
#   NO jq. NO yq. All JSON handling goes through `python3 -c`.
#
# -----------------------------------------------------------------------------
# Environment (human-provisioned; NEVER stored in the repo, NEVER echoed):
#   JIRA_SITE         Jira Cloud base URL, e.g. https://acme.atlassian.net
#   JIRA_EMAIL        Atlassian account email for Basic auth
#   JIRA_API_TOKEN    Atlassian API token (SECRET — scrubbed from all output)
#   JIRA_PROJECT_KEY  Project key used to fence create/search/events (e.g. ABS)
#   JIRA_JQL_FILTER   Optional extra JQL AND-ed into search/events fencing,
#                     e.g. 'labels = orchestrator-live' (first live runs MUST
#                     be fenced — see docs/sop/ORCHESTRATOR_SOP.md).
#
# The API token is passed to curl via a temp netrc-style config (--config), so
# it never appears in the process argument list, in `ps`, or in curl's verbose
# trace. All curl stderr is scrubbed before it can reach a log (scrub_secrets).
#
# -----------------------------------------------------------------------------
# API-call budget per orchestrator poll cycle (ORCH_POLL_INTERVAL=15s default):
#   `events`     -> exactly ONE JQL search sweep of JIRA_PROJECT_KEY
#                   (+ JIRA_JQL_FILTER). That is the whole per-poll cost: 1 call.
#   `get`        -> 1 issue GET + 1 comment-list GET per comment page
#                   (2 calls for a single-page ticket; +1 per extra page).
#   `search`     -> 1 JQL search.
#   `children`   -> 1 JQL search (parent = <epic>).
#   `create`     -> 1 POST (+ 0/1 label PUT when --role is set).
#   `transition` -> 1 GET (transitions list) + 1 POST.
#   `comment`    -> 1 POST.  `link` -> 1 GET + 1 PUT.  `update` -> 1 PUT.
# At ORCH_POLL_INTERVAL=15 the steady-state cost is one JQL sweep per 15s.
#
# -----------------------------------------------------------------------------
# Status mapping: canonical statuses (profiles/neutral/adapters/statuses.yaml)
# map 1:1 to Jira workflow statuses of the SAME NAME — no lossy folding. The
# human-side Jira workflow must define these statuses (documented prerequisite,
# see the SOP). This adapter never invents or folds a status. The ONE sanctioned
# exception is a name-preserving BOUNDARY RENAME (see "Provider status
# normalization" below): a case-only difference is folded to the canonical
# spelling, and a genuinely different Jira name is aliased 1:1 via
# JIRA_STATUS_ALIASES. Both stay one-to-one — no two canonical statuses ever
# collapse onto one Jira status.
#
# Timestamps: Jira returns native ISO-8601 with millis + a numeric offset
# (e.g. 2026-07-04T10:00:00.000+0530). `get` NORMALIZES every emitted timestamp
# (created:/updated: and each comment `### <at>` header) to the mock's canonical
# UTC form `%Y-%m-%dT%H:%M:%SZ`, because the orchestrator's iso_to_epoch parses
# only that form. This keeps the ABS-62 stall subsystem (ticket age, PO-park
# detection) working — orchestrator.sh stays untouched.
#
# Events: Jira has no pollable event stream we use here; like the mock, we keep
# a status snapshot at work/.jira-events-state (gitignored) and diff a JQL
# sweep against it on each `events` call, emitting the mock's exact event lines.
#
# Search endpoint (CHANGE-2046): every JQL sweep (search/children/events) goes
# through POST /rest/api/3/search/jql. The legacy POST /rest/api/3/search was
# removed by Atlassian and now returns HTTP 410 Gone; the new endpoint caps
# maxResults at 100 and its response carries only `issues` (no total/startAt),
# which is all this adapter reads.
#
# Limitation — single-page sweeps: every JQL sweep requests one page of
# maxResults=100 issues and does NOT paginate (the new endpoint is cursor-based
# via nextPageToken, which this adapter does not follow). This is the
# minimal-change default and is safe under the intended FENCED operation: keep
# the fenced set (JIRA_PROJECT_KEY + JIRA_JQL_FILTER) under 100 issues. If a
# fence can exceed 100, tighten JIRA_JQL_FILTER or add nextPageToken paging in
# jql_search.
#
# Env overrides (mainly for the offline test tier):
#   JIRA_TRACKER_STATE   events snapshot path (default: <repo>/work/.jira-events-state)
#   JIRA_CURL            curl binary/shim to use (default: curl) — the offline
#                        contract test points this at a canned-response shim.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

JIRA_SITE="${JIRA_SITE:-}"
JIRA_EMAIL="${JIRA_EMAIL:-}"
JIRA_API_TOKEN="${JIRA_API_TOKEN:-}"
JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY:-}"
JIRA_JQL_FILTER="${JIRA_JQL_FILTER:-}"

EVENTS_STATE="${JIRA_TRACKER_STATE:-$REPO_ROOT/work/.jira-events-state}"
CURL_BIN="${JIRA_CURL:-curl}"

# --- Provider status normalization -------------------------------------------
# The neutral canonical statuses (profiles/neutral/adapters/statuses.yaml) stay
# authoritative everywhere; ONLY this adapter translates, at the Jira boundary,
# for statuses the human Jira workflow happens to spell differently. Two rules:
#   * case-fold — a Jira status that differs from a canonical name only by case
#                 (e.g. "in review") is surfaced with the canonical spelling, so
#                 the orchestrator's case-sensitive map_action still matches.
#   * alias     — a Jira status with a genuinely different name is mapped via
#                 JIRA_STATUS_ALIASES ("Canonical=Jira", newline-separated).
# This is the one sanctioned exception to the "no folding" rule in the header:
# it is a rename at the boundary, not a lossy many-to-one fold.
JIRA_STATUSES="${JIRA_STATUSES:-$REPO_ROOT/profiles/neutral/adapters/statuses.yaml}"
# Default EMPTY — the neutral adapter assumes the Jira workflow uses the canonical
# names (case-fold aside). A deployment whose workflow renames one sets it, e.g.
#   export JIRA_STATUS_ALIASES="Ready for Development=Selected for Development"
# (newline-separated for several). See docs/sop/ORCHESTRATOR_SOP.md (Jira setup).
STATUS_ALIAS_C2J="${JIRA_STATUS_ALIASES:-}"
CANON_STATUS_LIST="$( [ -f "$JIRA_STATUSES" ] && sed -n 's/^  - name: //p' "$JIRA_STATUSES" || true )"
export STATUS_ALIAS_C2J CANON_STATUS_LIST

# One-time sanity check: warn if the same canonical status is aliased twice — the
# python parse is last-wins, which would silently mask the earlier mapping.
if [ -n "$STATUS_ALIAS_C2J" ]; then
    _alias_dups="$(printf '%s\n' "$STATUS_ALIAS_C2J" \
        | awk -F= 'NF>=2 { gsub(/^[ \t]+|[ \t]+$/, "", $1); if ($1 != "") print $1 }' \
        | sort | uniq -d)"
    [ -z "$_alias_dups" ] || printf 'jira-tracker: warning: JIRA_STATUS_ALIASES maps a canonical status more than once (last wins): %s\n' \
        "$(printf '%s' "$_alias_dups" | tr '\n' ' ')" >&2
    unset _alias_dups
fi

# STATUS_NORM_PY — python helper (reads CANON_STATUS_LIST / STATUS_ALIAS_C2J from
# the environment) exposing canon() [jira->canonical] and to_jira()
# [canonical->jira]. Prepended to each py block that emits or filters a status.
STATUS_NORM_PY='
import os as _os
_canon_lc = {s.lower(): s for s in _os.environ.get("CANON_STATUS_LIST","").splitlines() if s}
_c2j, _j2c = {}, {}
for _p in _os.environ.get("STATUS_ALIAS_C2J","").splitlines():
    if "=" in _p:
        _c, _j = (x.strip() for x in _p.split("=", 1))
        if not _c or not _j:
            continue
        _c2j[_c] = _j
        _j2c[_j.lower()] = _c
def canon(name):
    if not name:
        return name
    lc = name.lower()
    if lc in _j2c:
        return _j2c[lc]
    return _canon_lc.get(lc, name)
def to_jira(name):
    return _c2j.get(name, name)
'

# canon_status <jira-name> — echo the canonical spelling (case-fold + alias).
canon_status() {
    py "$STATUS_NORM_PY"'
import sys
sys.stdout.write(canon(sys.argv[1]))
' "$1"
}

# status_to_jira <canonical-name> — echo this Jira project'\''s status name.
status_to_jira() {
    py "$STATUS_NORM_PY"'
import sys
sys.stdout.write(to_jira(sys.argv[1]))
' "$1"
}

usage() {
    cat <<'EOF'
jira-tracker.sh — Jira Cloud task-tracking adapter (ABS-64)

Usage: scripts/jira-tracker.sh <command> [args]

Commands (the nine canonical operations, profiles/neutral/adapters/task-tracking.md):
  get <id>                                 Print the full canonical ticket.       (get_ticket)
  search [--status S] [--type T] [--parent P] [--text Q] [--label L] [--lane L]
                                           Matching tickets, one per line:
                                           id<TAB>type<TAB>status<TAB>title.
                                           --text matches Q case-insensitively
                                           as a substring of the title or body.
                                           --label matches tickets whose labels
                                           frontmatter list contains L exactly.
                                           --lane matches tickets whose lane field
                                           equals L (normal|fastlane).             (search_tickets)
  create --type <epic|ticket|subtask> --title <title> [--prefix <PFX>] [--parent <id>]
         [--fix-version <v>] [--role <be-developer|fe-developer|data-engineer>] [--body-file <path>] [--lane <normal|fastlane>]
         [--flag <design|security|data|skip-review|skip-test>]... [--ac-blocking]
                                           Create a ticket; prints the new id.
                                           Ids are assigned by Jira. Optional
                                           --role sets the implementer-role hint
                                           the orchestrator reads (ABS-36 §2.2),
                                           stored as a label role:<name> since
                                           Jira has no role field. Optional
                                           --flag (repeatable) / --ac-blocking
                                           set the v3 stage flags + JOIN marker,
                                           stored as labels flag:<name> /
                                           ac-blocking (ABS-82). Optional --lane
                                           sets the fastlane routing field
                                           (normal|fastlane, default normal),
                                           stored as label lane:<value> and
                                           re-emitted by get as a first-class
                                           field, never a plain label (ABS-319).
                                           Optional --body-file seeds the ticket
                                           body from a file instead of the _TBD_
                                           template.
                                           Optional --fix-version sets the Jira
                                           fixVersion. When omitted AND --parent
                                           is given, the child INHERITS the
                                           parent epic's fixVersion by default
                                           (an explicit --fix-version wins), so
                                           decomposition children are never
                                           fence-orphaned from dispatch (ABS-330).
                                           If the parent has none, the child is
                                           created with none.                     (create_ticket)
  update <id> <field> <value>              Update a canonical field
                                           (title|type|parent|depends_on|links|
                                           lane|flags|labels|ac_blocking|fix_version;
                                           status changes go through transition).
                                           fix_version sets the Jira fixVersion on
                                           an existing issue (remediation path for
                                           children created before create-time
                                           inheritance; empty value rejected). (ABS-330)
                                           Two extra fields rewrite the ticket BODY
                                           (the Jira description) in place, leaving
                                           comments untouched (AC-rework after
                                           enrichment, ABS-252):
                                             update <id> body <text>
                                             update <id> body-file <path>
                                           Prefer body-file: it keeps shell
                                           redirection chars (< >) off the command
                                           line (ABS-163).                         (update_ticket)
  comment <id> --kind <kind> --actor <actor> (--body <text> | --body-file <path>)
                                           Append a structured comment. --body-file
                                           reads the body from a file so text with
                                           shell redirection chars (< >) never hits
                                           a Bash command line (ABS-163).          (comment)
  transition <id> <to-status> --actor <actor> (--reason <text> | --reason-file <path>) [--expect-from <status>]
                                           Status change (resolves the Jira
                                           transition id for the target status);
                                           records actor + reason as a comment.
                                           --reason-file reads the reason from a
                                           file (ABS-163). --expect-from <status>
                                           is a compare-and-set guard: if the
                                           issue is no longer in <status> the call
                                           is a logged NOOP (exit 0) (ABS-198).    (transition)
  link <id> <other> <link-type>            Record a link; types: parent-child |
                                           depends-on | origin-review | pr |
                                           relates.                              (link)
  children <epic-id>                       Child tickets with status summary.     (get_epic_children)
  parent <id>                              Print the ticket's parent-epic key, or
                                           an empty line when it has none. Thin
                                           read the orchestrator intake classifier
                                           consumes (ABS-104).                    (get_ticket.parent)
  child-count <id>                         Print the count of child issues whose
                                           parent is <id> (0 when none). Thin read
                                           the intake classifier consumes (ABS-104). (get_epic_children.count)
  events                                   Poll: print status-change events since
                                           the last call as
                                           {ticket_id, from, to, at},
                                           then update the snapshot
                                           (work/.jira-events-state).             (subscribe_events)
  assign <id> <accountId>                  Set the assignee of a ticket.          (assign_ticket)

Comment kinds: understanding | transition-reason | gate-results | handoff | decision | notification | follow-up | bsa-decision | skip

Environment: JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY,
optional JIRA_JQL_FILTER. See the script header and docs/sop/ORCHESTRATOR_SOP.md.
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

# --- Secret hygiene ----------------------------------------------------------
# scrub_secrets removes the API token (and its base64 Basic-auth encoding) from
# any text before it can reach a log/error/trace. Belt-and-suspenders: the
# token is never passed on the curl command line to begin with (see http_call).
scrub_secrets() {
    local b64=""
    if [ -n "$JIRA_API_TOKEN" ] && [ -n "$JIRA_EMAIL" ]; then
        b64="$(printf '%s:%s' "$JIRA_EMAIL" "$JIRA_API_TOKEN" | _b64)"
    fi
    if [ -n "$JIRA_API_TOKEN" ]; then
        sed -e "s/${JIRA_API_TOKEN//\//\\/}/***REDACTED***/g" \
            ${b64:+-e "s/${b64//\//\\/}/***REDACTED***/g"}
    else
        cat
    fi
}

_b64() {
    # base64 with no newlines; portable (BSD base64 has no -w flag).
    python3 -c 'import sys,base64; sys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode())'
}

# --- Config / credential preflight -------------------------------------------
require_creds() {
    [ -n "$JIRA_SITE" ]        || die "JIRA_SITE is not set (e.g. https://acme.atlassian.net)"
    [ -n "$JIRA_EMAIL" ]       || die "JIRA_EMAIL is not set"
    [ -n "$JIRA_API_TOKEN" ]   || die "JIRA_API_TOKEN is not set (human-provisioned; never stored in repo)"
    [ -n "$JIRA_PROJECT_KEY" ] || die "JIRA_PROJECT_KEY is not set (fences create/search/events)"
}

# =============================================================================
# HTTP layer
# =============================================================================
# http_call <METHOD> <path> [<json-body>] — perform an authenticated Jira REST
# call and print the raw response body on stdout. The API token is delivered to
# curl through a --config file (never argv), so it never appears in `ps` or in
# curl's verbose output. curl stderr is scrubbed. Non-2xx responses die() with a
# scrubbed message. <path> is relative to $JIRA_SITE (e.g. /rest/api/3/issue).
http_call() {
    require_creds
    local method="$1" path="$2" body="${3:-}"
    local url="${JIRA_SITE%/}$path"

    local cfg out err code
    cfg="$(mktemp "${TMPDIR:-/tmp}/jira-cfg.XXXXXX")"
    out="$(mktemp "${TMPDIR:-/tmp}/jira-out.XXXXXX")"
    err="$(mktemp "${TMPDIR:-/tmp}/jira-err.XXXXXX")"
    # trap-free cleanup: registered locally, removed at the end of the function.
    # (No global trap so nested calls don't clobber each other.)

    # Credentials live only in the config file (mode 600), never in argv.
    {
        printf 'user = "%s:%s"\n' "$JIRA_EMAIL" "$JIRA_API_TOKEN"
        printf 'header = "Accept: application/json"\n'
        if [ -n "$body" ]; then
            printf 'header = "Content-Type: application/json"\n'
        fi
    } > "$cfg"
    chmod 600 "$cfg"

    # Deliver the request body to curl through a temp FILE (--data-binary "@file"),
    # never as an argv string. A multi-KB body (a gate-results/handoff comment)
    # passed on argv dies with "Argument list too long" (E2BIG) — ~32 KB on
    # Windows/MSYS, ~1 MB here — before it ever reaches Jira (ABS-263, the write-
    # path counterpart of ABS-250's read-path fix). Same shape as
    # release-notes.sh:258. The file is removed on the success AND every error path.
    local bodyfile=""
    set +e
    if [ -n "$body" ]; then
        bodyfile="$(mktemp "${TMPDIR:-/tmp}/jira-body.XXXXXX")"
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
        die "jira request failed (curl exit $rc): $msg"
    fi

    case "$code" in
        2*) cat "$out"; rm -f "$out" "$err" ;;
        *)
            local msg
            msg="$(scrub_secrets < "$out" | head -c 500)"
            rm -f "$out" "$err"
            die "jira API $method $path returned HTTP $code: $msg"
            ;;
    esac
}

# =============================================================================
# Python JSON helpers — all JSON parse/build goes through here (no jq).
# =============================================================================
# py <script> [args...] — run an inline python3 program. The program reads any
# JSON from stdin. We pass structured values through argv (safe — they are our
# own already-parsed strings, never the secret).
py() {
    python3 -c "$@"
}

# adf_wrap <plain-text-on-stdin> — emit a minimal ADF document JSON wrapping the
# text. v3 wants ADF for description/comment bodies. Newlines become separate
# paragraphs; empty input becomes one empty paragraph.
adf_wrap() {
    py '
import sys, json
text = sys.stdin.read()
lines = text.split("\n") if text != "" else [""]
content = []
for ln in lines:
    para = {"type": "paragraph", "content": []}
    if ln != "":
        para["content"] = [{"type": "text", "text": ln}]
    content.append(para)
doc = {"type": "doc", "version": 1, "content": content}
sys.stdout.write(json.dumps(doc))
'
}

# adf_unwrap <adf-json-on-stdin> — best-effort extraction of plain text from an
# ADF document (the inverse of adf_wrap). Recursively concatenates text nodes;
# paragraphs/hard-breaks become newlines. Tolerates null / non-ADF input.
adf_unwrap() {
    py '
import sys, json
try:
    node = json.load(sys.stdin)
except Exception:
    sys.stdout.write("")
    sys.exit(0)
out = []
def walk(n):
    if n is None:
        return
    if isinstance(n, list):
        for x in n:
            walk(x)
        return
    if not isinstance(n, dict):
        return
    t = n.get("type")
    if t == "text":
        out.append(n.get("text", ""))
    elif t == "hardBreak":
        out.append("\n")
    for x in n.get("content", []) or []:
        walk(x)
    if t == "paragraph":
        out.append("\n")
walk(node)
text = "".join(out)
# collapse the trailing paragraph newline
sys.stdout.write(text.rstrip("\n"))
'
}

# json_get <python-expr> — read JSON from stdin, print the value of a dotted/
# indexed expression given as a python expression over the variable `d`.
# Example: json_get 'd["key"]'.  Missing -> empty string.
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

# json_str <string-on-argv> — JSON-encode a bash string (quotes it safely).
json_str() {
    py 'import sys, json; sys.stdout.write(json.dumps(sys.argv[1]))' "$1"
}

# =============================================================================
# Type <-> Jira issuetype mapping
# =============================================================================
# Canonical types map to Jira issue-type names. Kept 1:1 and simple; the human
# Jira project must have these issue types (documented prerequisite).
type_to_jira() {
    case "$1" in
        epic)    echo "Epic" ;;
        ticket)  echo "Story" ;;
        subtask) echo "Sub-task" ;;
        *) die "internal: unknown canonical type '$1'" ;;
    esac
}

jira_to_type() {
    # Best-effort inverse; anything Story-like collapses to 'ticket'.
    case "$1" in
        Epic|epic) echo "epic" ;;
        Sub-task|Subtask|sub-task|subtask) echo "subtask" ;;
        *) echo "ticket" ;;
    esac
}

# =============================================================================
# JQL fencing
# =============================================================================
# JQL trust model: every VALUE this adapter interpolates into a double-quoted
# JQL string literal (project key, --status, --type, --parent, --text, epic id)
# is escaped by jql_quote below (backslash then double-quote), so a value like
# foo"bar cannot break out of its literal or inject clauses. The one exception
# is JIRA_JQL_FILTER, which is an OPERATOR-supplied raw JQL FRAGMENT (e.g.
# 'labels = orchestrator-live') deliberately spliced verbatim — it is a trusted
# configuration knob, not caller/ticket data. Never route untrusted input there.

# jql_quote <value> — escape a value for safe interpolation inside a "..." JQL
# literal: backslash first, then double-quote.
jql_quote() {
    local v="$1"
    v="${v//\\/\\\\}"
    v="${v//\"/\\\"}"
    printf '%s' "$v"
}

# fence_jql — the base project fence AND-ed with the optional JIRA_JQL_FILTER.
# Every search/events/children sweep is scoped by this so a live run can be
# restricted to designated tickets (labels = orchestrator-live).
fence_jql() {
    local pk jql
    pk="$(jql_quote "$JIRA_PROJECT_KEY")"
    jql="project = \"$pk\""
    if [ -n "$JIRA_JQL_FILTER" ]; then
        # Trusted operator-supplied raw JQL fragment (see trust-model note).
        jql="$jql AND ($JIRA_JQL_FILTER)"
    fi
    echo "$jql"
}

# jql_search <jql> — POST /rest/api/3/search/jql, return the merged JSON.
# Requests the fields the adapter surfaces. The legacy /rest/api/3/search
# endpoint was removed by Atlassian (HTTP 410 Gone, CHANGE-2046); the new
# endpoint caps maxResults at 100 and is cursor-paged via nextPageToken.
#
# ABS-308: the cursor IS followed. A single-page sweep silently truncates once
# the fence exceeds 100 issues, and a truncated sweep is a machine for PHANTOM
# events: a ticket past the page boundary falls out of the events snapshot,
# then re-enters a later sweep as "newly seen" (from: null) although nothing
# changed — observed downstream as an infinite PO no-op spawn loop (17 paid
# spawns/24h on one resting Backlog ticket). Pages are merged into one
# {"issues": [...]} document, so every caller keeps its existing contract.
jql_search() {
    local jql="$1"
    local token="" page=0 pdir
    pdir="$(mktemp -d "${TMPDIR:-/tmp}/jira-jql.XXXXXX")"
    while :; do
        local body
        body="$(py '
import sys, json
jql, token = sys.argv[1], sys.argv[2]
req = {
    "jql": jql,
    "maxResults": 100,
    "fields": ["summary", "status", "issuetype", "parent", "labels"],
}
if token:
    req["nextPageToken"] = token
sys.stdout.write(json.dumps(req))
' "$jql" "$token")"
        if ! http_call POST /rest/api/3/search/jql "$body" > "$pdir/$(printf %03d "$page").json"; then
            rm -rf "$pdir"
            return 1
        fi
        token="$(py '
import sys, json
d = json.load(sys.stdin)
tok = d.get("nextPageToken") or ""
if d.get("isLast") is True:
    tok = ""
sys.stdout.write(tok)
' < "$pdir/$(printf %03d "$page").json")"
        page=$((page + 1))
        [ -n "$token" ] || break
        # Hard stop: a buggy cursor must not spin forever. 50 pages = 5000
        # issues, far past any sane fence; tighten JIRA_JQL_FILTER instead.
        if [ "$page" -ge 50 ]; then
            echo "WARN: jql_search stopping after 50 pages (cursor still continuing?)" >&2
            break
        fi
    done
    py '
import sys, json
issues = []
for p in sorted(sys.argv[1:]):
    with open(p) as f:
        issues.extend(json.load(f).get("issues", []))
sys.stdout.write(json.dumps({"issues": issues}))
' "$pdir"/*.json
    local rc=$?
    rm -rf "$pdir"
    return "$rc"
}

# =============================================================================
# Commands
# =============================================================================

cmd_get() {
    local id="$1"
    # Issue with the canonical fields + rendered description.
    local issue
    issue="$(http_call GET "/rest/api/3/issue/$id?fields=summary,status,issuetype,parent,labels,description,created,updated,fixVersions")"

    # Frontmatter + body, assembled by python so multi-word / special chars in
    # titles and bodies survive. Comments are fetched separately and appended in
    # the mock's exact "### <at> | kind: <k> | actor: <a>" format.
    # Comments can span multiple Jira API pages. The comment endpoint returns
    # them oldest-first, so a single-page fetch would silently drop the NEWEST
    # comments once a ticket exceeds one page — fatal for claim adjudication,
    # which must see the freshest peer claim, and for the ABS-62 stall subsystem
    # reading the same headers (ABS-182; spec §8). Exhaust every page.
    local cdir start total fetched page counts
    cdir="$(mktemp -d "${TMPDIR:-/tmp}/jira-comments.XXXXXX")"
    start=0
    page=0
    while :; do
        http_call GET "/rest/api/3/issue/$id/comment?startAt=$start&maxResults=100" > "$cdir/$page.json"
        # Take the parse exit code by hand (`|| { ... }` opts this out of `set -e`)
        # so a malformed page frees the page dir instead of leaking it when the
        # script aborts mid-loop (predates ABS-250; fixed here in ABS-263).
        counts="$(py '
import sys, json
d = json.load(sys.stdin)
cs = d.get("comments", [])
print(int(d.get("total", len(cs))), len(cs))
' < "$cdir/$page.json")" || { rm -rf "$cdir"; die "get: malformed comment page from Jira ($id, page $page)"; }
        set -- $counts
        total="$1"; fetched="$2"
        start=$(( start + fetched ))
        page=$(( page + 1 ))
        [ "$fetched" -gt 0 ] || break
        [ "$start" -lt "$total" ] || break
    done
    # The issue JSON arrives on stdin and the comment pages are read from disk by
    # page path (ABS-250): a full Jira response passed as an argv argument blows
    # the OS argument limit on Windows/MSYS ("Argument list too long") once a
    # ticket accumulates comments. Only the (small) page directory is argv.
    local rc=0
    printf '%s' "$issue" | JIRA_ADF_MODE=body py "$STATUS_NORM_PY"'
import sys, json, re, glob, os

issue = json.load(sys.stdin)
_cdir = sys.argv[1]
comments = {"comments": []}
for _f in sorted(glob.glob(os.path.join(_cdir, "*.json")),
                 key=lambda p: int(os.path.basename(p).split(".")[0])):
    with open(_f) as _fh:
        comments["comments"].extend(json.load(_fh).get("comments", []))

def jira_ts_to_z(ts):
    # Normalize a Jira-native timestamp (e.g. 2026-07-04T10:00:00.000+0530) to
    # the mock adapter'"'"'s canonical UTC form (2026-07-04T04:30:00Z) so the
    # orchestrator'"'"'s iso_to_epoch (which only parses %Y-%m-%dT%H:%M:%SZ) can
    # read the created:/updated:/### <at> values the ABS-62 stall subsystem
    # depends on. Strips millis and converts any +HHMM/-HHMM offset to UTC.
    if not ts:
        return ts
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?"
                 r"(Z|[+-]\d{2}:?\d{2})?$", ts)
    if not m:
        return ts  # unrecognized -> pass through unchanged (best-effort)
    import datetime
    y, mo, d, hh, mm, ss = (int(m.group(i)) for i in range(1, 7))
    off = m.group(7) or "Z"
    try:
        dt = datetime.datetime(y, mo, d, hh, mm, ss)
        if off not in ("Z", None):
            sign = 1 if off[0] == "+" else -1
            digits = off[1:].replace(":", "")
            oh, om = int(digits[:2]), int(digits[2:4])
            dt = dt - sign * datetime.timedelta(hours=oh, minutes=om)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ts

def adf_to_text(node):
    out = []
    def walk(n):
        if n is None:
            return
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "text":
            out.append(n.get("text",""))
        elif t == "hardBreak":
            out.append("\n")
        for x in n.get("content", []) or []:
            walk(x)
        if t == "paragraph":
            out.append("\n")
    walk(node)
    return "".join(out).rstrip("\n")

f = issue.get("fields", {})
key = issue.get("key","")
summary = f.get("summary","") or ""
status = canon((f.get("status") or {}).get("name","") or "")
itype = (f.get("issuetype") or {}).get("name","") or ""

def canon_type(name):
    if name in ("Epic","epic"): return "epic"
    if name in ("Sub-task","Subtask","sub-task","subtask"): return "subtask"
    return "ticket"

parent = ""
p = f.get("parent")
if p: parent = p.get("key","") or ""

labels = f.get("labels", []) or []
role = ""
depends_on = []
links = []
flags = []
plain_labels = []
ac_blocking = False
lane = "normal"  # First-class fastlane field (ABS-319); default normal.
priority = "normal"  # Canonical priority (ABS-261); default normal.
iteration_cap = ""  # Typed iteration-guard cap (PILOT-77); unset by default.
for lb in labels:
    if lb.startswith("role:"):
        role = lb[len("role:"):]
    elif lb.startswith("lane:"):
        # First-class fastlane routing field (ABS-319), persisted as label
        # lane:<value>; re-emitted as a frontmatter field, never a plain label.
        lane = lb[len("lane:"):]
    elif lb.startswith("priority:"):
        # Canonical priority (ABS-261), persisted as label priority:<value>
        # (same technique as lane); re-emitted as a frontmatter field.
        priority = lb[len("priority:"):]
    elif lb.startswith("iteration-cap:"):
        # Typed iteration-guard cap (PILOT-77 / ADR-A-0026 P1), persisted as label
        # iteration-cap:<N> (same technique as lane/priority); re-emitted as a
        # frontmatter field only-when-set.
        iteration_cap = lb[len("iteration-cap:"):]
    elif lb.startswith("depends-on:"):
        depends_on.append(lb[len("depends-on:"):])
    elif lb.startswith("link:"):
        links.append(lb[len("link:"):])
    elif lb.startswith("flag:"):
        # v3 conditional-stage flags (ABS-82), label flag:<name>.
        flags.append(lb[len("flag:"):])
    elif lb == "ac-blocking":
        ac_blocking = True
    else:
        # Free-form Jira labels with no adapter prefix (ABS-101). Surfaced as the
        # canonical labels frontmatter so the orchestrator Backlog opt-in gate
        # (orchestrator-ready) reads the same field across every adapter.
        plain_labels.append(lb)

created = jira_ts_to_z(f.get("created","") or "")
updated = jira_ts_to_z(f.get("updated","") or "")

# fix_version (PILOT-12): assigned release read from the native Jira
# fixVersions[]. The backend fix_version field (PILOT-7) is single-valued, so
# when an issue carries MULTIPLE fixVersions we deterministically take the
# first (primary) entry as Jira returns them; empty/unset -> no line at all.
fix_version = ""
fvs = f.get("fixVersions", []) or []
if fvs:
    fix_version = (fvs[0] or {}).get("name", "") or ""

body = adf_to_text(f.get("description"))

def yaml_list(items):
    if not items: return "[]"
    return "[" + ", ".join(items) + "]"

lines = []
lines.append("---")
lines.append("id: " + key)
lines.append("type: " + canon_type(itype))
lines.append("title: " + summary)
lines.append("status: " + status)
lines.append("parent: " + parent)
# First-class fastlane field (ABS-319): ALWAYS emitted (default normal), in the
# same position as the mock adapter so `get` output matches across adapters.
lines.append("lane: " + lane)
# Canonical priority (ABS-261): ALWAYS emitted (default normal), mirroring the
# mock adapter default-when-absent behaviour.
lines.append("priority: " + priority)
if role:
    lines.append("role: " + role)
# v3 flags + AC-blocking marker (ABS-82): emitted only when present, mirroring
# the mock adapter only-when-given rule so pre-v3 dumps stay identical.
if flags:
    lines.append("flags: " + yaml_list(sorted(flags)))
# Free-form labels (ABS-101): emitted only when present, same only-when-given
# rule as flags so pre-ABS-101 dumps stay identical.
if plain_labels:
    lines.append("labels: " + yaml_list(sorted(plain_labels)))
if ac_blocking:
    lines.append("ac_blocking: true")
# fix_version (PILOT-12): emitted ONLY when set, at the same position as
# backend-tracker.sh get (immediately before depends_on) so the fix_version:
# line is byte-identical across adapters; an issue with no fixVersions stays
# byte-identical to the pre-PILOT-12 render.
if fix_version:
    lines.append("fix_version: " + fix_version)
# iteration_cap (PILOT-77): typed control field emitted ONLY when set, in the same
# position as the mock/backend renderers (before depends_on) so the line is byte-
# identical across adapters (ADR-A-0021).
if iteration_cap:
    lines.append("iteration_cap: " + iteration_cap)
lines.append("depends_on: " + yaml_list(depends_on))
lines.append("links: " + yaml_list(links))
lines.append("created: " + created)
lines.append("updated: " + updated)
lines.append("---")
sys.stdout.write("\n".join(lines) + "\n")

if body:
    sys.stdout.write("\n" + body + "\n")

# Comments: reproduce the mock dump exactly, including the structured header
# line the orchestrator stall-detection guard parses:
#   ### <at> | kind: <kind> | actor: <actor>
# We encode kind+actor into the FIRST line of each Jira comment body as
#   [kind: <kind> | actor: <actor>]
# on create; parse it back here. Comments without that header fall back to
# kind: notification / actor: <displayName>.
sys.stdout.write("\n## Comments\n")
for c in comments.get("comments", []):
    at = jira_ts_to_z(c.get("created",""))
    author = (c.get("author") or {}).get("displayName","") or ""
    text = adf_to_text(c.get("body"))
    kind = "notification"; actor = author
    first_nl = text.find("\n")
    firstline = text if first_nl < 0 else text[:first_nl]
    rest = "" if first_nl < 0 else text[first_nl+1:]
    fl = firstline.strip()
    if fl.startswith("[") and fl.endswith("]") and "kind:" in fl and "actor:" in fl:
        inner = fl[1:-1]
        # inner: "kind: <k> | actor: <a>"
        try:
            parts = inner.split("|")
            for pt in parts:
                pt = pt.strip()
                if pt.startswith("kind:"):
                    kind = pt[len("kind:"):].strip()
                elif pt.startswith("actor:"):
                    actor = pt[len("actor:"):].strip()
            body_text = rest
        except Exception:
            body_text = text
    else:
        body_text = text
        # ABS-302: [kind:] header not on first line — recover, never silent.
        # Scan the full body for the first well-formed [kind: … | actor: …] line;
        # adopt its kind/actor and strip that line from body_text so marker scanners
        # see the correct classification. Warn to stderr so the operator knows.
        # (sys is already imported at the top of this block)
        _recovered = False
        _new_lines = []
        for _ck_ln in text.split("\n"):
            _ck = _ck_ln.strip()
            if not _recovered and _ck.startswith("[") and _ck.endswith("]") \
                    and "kind:" in _ck and "actor:" in _ck:
                try:
                    _inner = _ck[1:-1]
                    _parts = _inner.split("|")
                    _rk = kind; _ra = actor
                    for _p in _parts:
                        _p = _p.strip()
                        if _p.startswith("kind:"):
                            _rk = _p[len("kind:"):].strip()
                        elif _p.startswith("actor:"):
                            _ra = _p[len("actor:"):].strip()
                    kind = _rk; actor = _ra
                    _recovered = True
                    sys.stderr.write(
                        "WARNING ABS-302: [kind:] header found on non-first line "
                        "in comment (at=%s) — recovered kind=%s actor=%s. "
                        "Re-post via the adapter to avoid this.\n" % (at, kind, actor))
                except Exception:
                    _new_lines.append(_ck_ln)
            else:
                _new_lines.append(_ck_ln)
        if _recovered:
            body_text = "\n".join(_new_lines)
    sys.stdout.write("\n### %s | kind: %s | actor: %s\n\n%s\n" % (at, kind, actor, body_text))
' "$cdir" || rc=$?
    # The page files are the python input, so cleanup can only run AFTER it. Take
    # the exit code by hand (`|| rc=$?` opts this one command out of `set -e`) so
    # a parse failure still frees the page dir instead of leaking it on every
    # poll, and still propagates as a non-zero return.
    rm -rf "$cdir"
    return "$rc"
}

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

    local jql
    jql="$(fence_jql)"
    # status filter: alias-translate canonical -> Jira name. Case-only differences
    # need no fold here — JQL `status =` matches status names case-insensitively.
    if [ -n "$f_status" ]; then jql="$jql AND status = \"$(jql_quote "$(status_to_jira "$f_status")")\""; fi
    if [ -n "$f_type" ]; then jql="$jql AND issuetype = \"$(jql_quote "$(type_to_jira "$f_type")")\""; fi
    if [ -n "$f_parent" ]; then jql="$jql AND parent = \"$(jql_quote "$f_parent")\""; fi
    # --text: JQL `text ~` is fuzzy; mock semantics are a case-insensitive
    # substring over title+body. We over-fetch with `text ~` (or the fence
    # alone) and filter to true substring matches in python for parity.
    if [ -n "$f_text" ]; then jql="$jql AND text ~ \"$(jql_quote "$f_text")\""; fi
    # --label: canonical labels are plain (un-prefixed) Jira labels, so the
    # exact-match mock semantics map straight onto JQL `labels =`.
    if [ -n "$f_label" ]; then jql="$jql AND labels = \"$(jql_quote "$f_label")\""; fi
    # --lane (ABS-319): the field persists as label lane:<value>, so an exact
    # lane match maps onto JQL `labels = lane:<value>`. Tickets predating the
    # field carry no lane label and so are excluded — lane is authoritative
    # going forward, mirroring the mock's default-normal semantics for new work.
    if [ -n "$f_lane" ]; then jql="$jql AND labels = \"lane:$(jql_quote "$f_lane")\""; fi

    # ABS-331/ABS-389: age-ASC within the fence so the priority-dispatch tiebreak
    # (ABS-261) holds on the LIVE adapter instead of degrading to Jira's default
    # order. Priority itself is a *label* (priority:<value>), not a JQL-orderable
    # field, so the canonical cross-adapter `priority ASC, created ASC` contract
    # (task-tracking.md) is completed by a STABLE priority re-sort of these
    # age-ASC rows in the emit step below. The ORDER BY clause must be the FINAL
    # element of the JQL, after every AND filter.
    jql="$jql ORDER BY created ASC"

    local resp
    resp="$(jql_search "$jql")"

    printf '%s' "$resp" | py "$STATUS_NORM_PY"'
import sys, json
resp = json.load(sys.stdin)
needle = sys.argv[1].lower()

def adf_to_text(node):
    out = []
    def walk(n):
        if n is None:
            return
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if not isinstance(n, dict):
            return
        if n.get("type") == "text":
            out.append(n.get("text",""))
        for x in n.get("content", []) or []:
            walk(x)
    walk(node)
    return "".join(out)

def canon_type(name):
    if name in ("Epic","epic"): return "epic"
    if name in ("Sub-task","Subtask","sub-task","subtask"): return "subtask"
    return "ticket"

def row_priority(labels):
    # ABS-331/ABS-261: canonical priority persists as a priority:<value> label
    # (label technique, ABS-242 mapping — same as lane:/role:). Emitted as a
    # search column so the orchestrator reads it without an extra per-row `get`.
    # Absent/unmapped => normal (backward compat with pre-priority tickets).
    prio = "normal"
    for lb in labels or []:
        if lb.startswith("priority:"):
            prio = lb[len("priority:"):]
    return prio if prio in ("hotfix","high","normal","low") else "normal"

# ABS-389: canonical cross-adapter row order is `priority ASC, created ASC`.
# JQL already delivered the issues age-ASC (created ASC); rank-sort STABLY on
# priority (hotfix=0<high=1<normal=2<low=3) to add the priority-first primary
# sort while preserving age-ASC within each band. Unmapped => normal.
RANK = {"hotfix": 0, "high": 1, "normal": 2, "low": 3}
rows = []
for iss in resp.get("issues", []):
    f = iss.get("fields", {})
    key = iss.get("key","")
    summary = f.get("summary","") or ""
    status = canon((f.get("status") or {}).get("name","") or "")
    itype = canon_type((f.get("issuetype") or {}).get("name","") or "")
    priority = row_priority(f.get("labels", []))
    if needle:
        hay = (summary + "\n" + adf_to_text(f.get("description"))).lower()
        if needle not in hay:
            continue
    rows.append((key, itype, status, priority, summary))
rows.sort(key=lambda r: RANK.get(r[3], 2))  # stable => age-ASC preserved within band
for key, itype, status, priority, summary in rows:
    # id<TAB>type<TAB>status<TAB>priority<TAB>title — priority sits BEFORE the
    # free-form title so title stays the trailing catch-all (robust parsing).
    sys.stdout.write("%s\t%s\t%s\t%s\t%s\n" % (key, itype, status, priority, summary))
' "$f_text"
}

cmd_create() {
    local type="" title="" prefix="" parent="" role="" body_file="" flags="" ac_blocking="" lane="normal" fix_version=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --type)      [ $# -ge 2 ] || die "create: --type requires a value";      type="$2";      shift 2 ;;
            --title)     [ $# -ge 2 ] || die "create: --title requires a value";     title="$2";     shift 2 ;;
            --prefix)    [ $# -ge 2 ] || die "create: --prefix requires a value";    prefix="$2";    shift 2 ;;
            --parent)    [ $# -ge 2 ] || die "create: --parent requires a value";    parent="$2";    shift 2 ;;
            --fix-version) [ $# -ge 2 ] || die "create: --fix-version requires a value"; fix_version="$2"; shift 2 ;;
            --role)      [ $# -ge 2 ] || die "create: --role requires a value";      role="$2";      shift 2 ;;
            --body-file) [ $# -ge 2 ] || die "create: --body-file requires a value"; body_file="$2"; shift 2 ;;
            --lane)
                # First-class fastlane routing field (ABS-319), default normal.
                # Jira has no native lane field, so it persists as a label
                # lane:<value> (like role:) and `get` re-emits it as a frontmatter
                # field, never in the plain labels list — parity with the mock.
                [ $# -ge 2 ] || die "create: --lane requires a value"
                case "$2" in
                    normal|fastlane) lane="$2" ;;
                    *) die "create: invalid lane '$2' (normal|fastlane)" ;;
                esac
                shift 2 ;;
            --flag)
                # Repeatable v3 conditional-stage flag (ABS-82), label flag:<name>.
                [ $# -ge 2 ] || die "create: --flag requires a value"
                case "$2" in
                    design|security|data|skip-review|skip-test) ;;
                    *) die "create: invalid flag '$2' (design|security|data|skip-review|skip-test)" ;;
                esac
                case "$flags" in
                    *"$2"*) ;;
                    "") flags="$2" ;;
                    *)  flags="$flags $2" ;;
                esac
                shift 2 ;;
            --ac-blocking) ac_blocking="true"; shift ;;
            *) die "create: unknown argument: $1" ;;
        esac
    done
    [ -n "$type" ] || die "create: --type is required (epic|ticket|subtask)"
    case "$type" in
        epic|ticket|subtask) ;;
        *) die "create: invalid type '$type' (epic|ticket|subtask)" ;;
    esac
    [ -n "$title" ] || die "create: --title is required"
    # --prefix is accepted for CLI parity with the mock; in Jira the project key
    # (JIRA_PROJECT_KEY) determines the id prefix, so --prefix is informational.
    if [ -n "$role" ]; then
        case "$role" in
            be-developer|fe-developer|data-engineer) ;;
            *) die "create: invalid role '$role' (be-developer|fe-developer|data-engineer)" ;;
        esac
    fi
    [ -z "$body_file" ] || [ -f "$body_file" ] || die "create: --body-file not found: $body_file"

    require_creds

    # fixVersion (ABS-330): an explicit --fix-version always wins; otherwise a
    # child created under --parent INHERITS the parent epic's fixVersion so
    # fixVersion-based run fences never orphan freshly-decomposed children from
    # dispatch (root-cause of the ABS-314 / ABS-319..325 orphaning). If the
    # parent has no fixVersion — or there is no parent — the issue is created
    # with none (no error), leaving the POST payload byte-identical to today.
    if [ -z "$fix_version" ] && [ -n "$parent" ]; then
        fix_version="$(http_call GET "/rest/api/3/issue/$parent?fields=fixVersions" | py '
import sys, json
data = json.load(sys.stdin)
fvs = (data.get("fields", {}) or {}).get("fixVersions") or []
sys.stdout.write(fvs[0].get("name", "") if fvs else "")
')"
    fi

    # Body: enriched from file, else the _TBD_ template (same text as the mock).
    local body_text
    if [ -n "$body_file" ]; then
        body_text="$(cat "$body_file")"
    else
        body_text="$(cat <<'BODY'
## Goal

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

_None embedded yet._
BODY
)"
    fi

    local desc_adf
    desc_adf="$(printf '%s' "$body_text" | adf_wrap)"

    # The description ADF streams over stdin, never argv: a large description on
    # argv dies with E2BIG on Windows/MSYS (ABS-263). Only small control values
    # (project/type/title/parent/role/flags) stay in argv.
    local body
    body="$(printf '%s' "$desc_adf" | py '
import sys, json
project, itype, summary, parent, role, flags, ac_blocking, lane, fix_version = sys.argv[1:10]
desc = sys.stdin.read()
fields = {
    "project": {"key": project},
    "summary": summary,
    "issuetype": {"name": itype},
    "description": json.loads(desc),
}
# fixVersion (ABS-330): only added when set (explicit --fix-version or inherited
# from --parent), so a create with no fixVersion keeps the payload unchanged.
if fix_version:
    fields["fixVersions"] = [{"name": fix_version}]
labels = []
if role:
    labels.append("role:" + role)
# v3 flags + AC-blocking marker as labels (ABS-82).
for fl in flags.split():
    labels.append("flag:" + fl)
if ac_blocking == "true":
    labels.append("ac-blocking")
# First-class fastlane routing field (ABS-319), persisted as label lane:<value>
# (default normal) and re-emitted as a frontmatter field by get.
labels.append("lane:" + lane)
if labels:
    fields["labels"] = labels
if parent:
    fields["parent"] = {"key": parent}
sys.stdout.write(json.dumps({"fields": fields}))
' "$JIRA_PROJECT_KEY" "$(type_to_jira "$type")" "$title" "$parent" "$role" "$flags" "$ac_blocking" "$lane" "$fix_version")"

    local resp key
    resp="$(http_call POST /rest/api/3/issue "$body")"
    key="$(printf '%s' "$resp" | json_get 'd["key"]')"
    [ -n "$key" ] || die "create: Jira did not return an issue key"
    echo "$key"
}

cmd_update() {
    local id="$1" field="$2" value="$3"
    case "$field" in
        status) die "update: status changes must go through 'transition' (validated + reasoned)" ;;
        id|created|updated) die "update: field '$field' is managed by the tracker" ;;
        title|type|parent|depends_on|links) ;;
        lane)
            # First-class fastlane routing field (ABS-319): scalar, closed set.
            case "$value" in
                normal|fastlane) ;;
                *) die "update: lane must be 'normal' or 'fastlane'" ;;
            esac
            ;;
        flags)
            # v3 flags (ABS-82): replace-whole-set contract, yaml-ish list value
            # (same shape as the mock adapter), members validated.
            case "$value" in
                "["*"]") ;;
                *) die "update: flags value must be a list like '[design, security]'" ;;
            esac
            local member
            for member in $(printf '%s' "$value" | tr -d '[],'); do
                case "$member" in
                    design|security|data|skip-review|skip-test) ;;
                    *) die "update: invalid flag '$member' (design|security|data|skip-review|skip-test)" ;;
                esac
            done
            ;;
        labels)
            # Free-form labels (ABS-101): replace-whole-set of the PLAIN (un-
            # prefixed) Jira labels; same list shape + charset as the mock adapter.
            case "$value" in
                "["*"]") ;;
                *) die "update: labels value must be a list like '[orchestrator-ready]'" ;;
            esac
            local lbl
            for lbl in $(printf '%s' "$value" | tr -d '[],'); do
                case "$lbl" in
                    *[!A-Za-z0-9._:-]*) die "update: invalid label '$lbl' (allowed: A-Za-z0-9 . _ - :)" ;;
                esac
            done
            ;;
        ac_blocking)
            case "$value" in
                true|false) ;;
                *) die "update: ac_blocking must be 'true' or 'false'" ;;
            esac
            ;;
        priority)
            # ABS-261/ABS-242 canonical priority — a Human/PO board action; seats
            # never raise it (orchestrator _common-rules charter line).
            case "$value" in
                hotfix|high|normal|low) ;;
                *) die "update: invalid priority '$value' (hotfix|high|normal|low)" ;;
            esac
            ;;
        fix_version)
            # fixVersion (ABS-330): scalar version name — the remediation path
            # for children created before inheritance existed. Empty/missing is
            # rejected with a clear die, consistent with the other field checks.
            [ -n "$value" ] || die "update: fix_version requires a non-empty value"
            ;;
        iteration_cap)
            # PILOT-77 / ADR-A-0026 P1: typed, audited iteration-guard cap — a
            # positive integer. Replaces the "Iteration N of M" comment marker as
            # the control input the dispatch/guard reads (mock/live parity).
            case "$value" in
                ''|*[!0-9]*) die "update: iteration_cap must be a positive integer" ;;
            esac
            [ "$value" -ge 1 ] || die "update: iteration_cap must be a positive integer"
            ;;
        body|body-file)
            # Ticket-body rewrite (ABS-252) — the Jira `description` field.
            # `body` takes the text inline; `body-file` reads it from a path and
            # is the form seats should use (keeps < > off the command line, ABS-163).
            # Jira comments live outside `description`, so they survive untouched —
            # the same preserve-comments contract the mock implements.
            if [ "$field" = "body-file" ]; then
                [ -f "$value" ] || die "update: body-file not found: $value"
            fi
            ;;
        *) die "update: unknown field '$field' (title|type|parent|depends_on|links|lane|flags|labels|ac_blocking|priority|iteration_cap|body|body-file)" ;;
    esac
    require_creds

    local body
    case "$field" in
        title)
            body="$(py 'import sys,json; sys.stdout.write(json.dumps({"fields":{"summary":sys.argv[1]}}))' "$value")"
            http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
            ;;
        type)
            body="$(py 'import sys,json; sys.stdout.write(json.dumps({"fields":{"issuetype":{"name":sys.argv[1]}}}))' "$(type_to_jira "$value")")"
            http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
            ;;
        parent)
            body="$(py 'import sys,json; sys.stdout.write(json.dumps({"fields":{"parent":{"key":sys.argv[1]}}}))' "$value")"
            http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
            ;;
        depends_on|links)
            # Canonical list fields have no native Jira home; we persist them as
            # labels (depends-on:<id> / link:<entry>) so `get` round-trips them.
            # `update` here replaces the label set for that prefix.
            update_list_labels "$id" "$field" "$value"
            ;;
        flags)
            # v3 flags as labels flag:<name> (ABS-82), replace-whole-set.
            update_list_labels "$id" "$field" "$value"
            ;;
        lane)
            # First-class fastlane field (ABS-319) persisted as a single
            # lane:<value> label; replace any existing lane:* label in place.
            update_lane_label "$id" "$value"
            ;;
        priority)
            # Canonical priority (ABS-261) persisted as a single priority:<value>
            # label (same technique as lane); native Jira priority mapping is a
            # documented follow-up.
            update_priority_label "$id" "$value"
            ;;
        iteration_cap)
            # Typed iteration-guard cap (PILOT-77) persisted as a single
            # iteration-cap:<N> label (same technique as lane/priority); native
            # Jira has no home for it. `get` re-emits it as a frontmatter field.
            update_iteration_cap_label "$id" "$value"
            ;;
        fix_version)
            # fixVersion (ABS-330): native Jira fixVersions array — replace with
            # the single named version. Remediation path for children created
            # before create-time inheritance existed.
            body="$(py 'import sys, json; sys.stdout.write(json.dumps({"fields":{"fixVersions":[{"name":sys.argv[1]}]}}))' "$value")"
            http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
            ;;
        labels)
            # Free-form Jira labels (ABS-101), replace-whole-set of the plain ones.
            update_plain_labels "$id" "$value"
            ;;
        ac_blocking)
            # Boolean marker label; true adds "ac-blocking", false removes it.
            update_ac_blocking_label "$id" "$value"
            ;;
        body|body-file)
            # Replace the description with the new body, ADF-wrapped exactly as
            # `create --body-file` does (ABS-252).
            local body_text desc_adf
            body_text="$value"
            [ "$field" = "body" ] || body_text="$(cat "$value")"
            desc_adf="$(printf '%s' "$body_text" | adf_wrap)"
            # The ADF description streams over stdin, never argv (ABS-263 —
            # this cmd_update site was the third argv payload, found by the
            # ABS-245 epic smoke).
            body="$(printf '%s' "$desc_adf" | py 'import sys, json; sys.stdout.write(json.dumps({"fields":{"description":json.loads(sys.stdin.read())}}))')"
            http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
            ;;
    esac
    # body/body-file are two spellings of the same write; both report `body`
    # so the success line is identical across adapters (parity contract).
    case "$field" in
        body|body-file) echo "$id: body updated" ;;
        *)              echo "$id: $field updated" ;;
    esac
}

# update_lane_label <id> <normal|fastlane> — set the fastlane routing field
# (ABS-319), persisted as a single lane:<value> label. Drops any prior lane:*
# label and adds the new one, preserving every other label.
update_lane_label() {
    local id="$1" value="$2"
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
value = sys.argv[1]
labels = (existing.get("fields",{}).get("labels",[]) or [])
labels = [l for l in labels if not l.startswith("lane:")]
labels.append("lane:" + value)
sys.stdout.write(json.dumps({"fields":{"labels": labels}}))
' "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

# update_priority_label <id> <hotfix|high|normal|low> — set the canonical
# priority (ABS-261), persisted as a single priority:<value> label. Drops any
# prior priority:* label, preserves every other label.
update_priority_label() {
    local id="$1" value="$2"
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
value = sys.argv[1]
labels = (existing.get("fields",{}).get("labels",[]) or [])
labels = [l for l in labels if not l.startswith("priority:")]
labels.append("priority:" + value)
sys.stdout.write(json.dumps({"fields":{"labels": labels}}))
' "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

# update_iteration_cap_label <id> <N> — set the typed iteration-guard cap
# (PILOT-77), persisted as a single iteration-cap:<N> label. Drops any prior
# iteration-cap:* label, preserves every other label.
update_iteration_cap_label() {
    local id="$1" value="$2"
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
value = sys.argv[1]
labels = (existing.get("fields",{}).get("labels",[]) or [])
labels = [l for l in labels if not l.startswith("iteration-cap:")]
labels.append("iteration-cap:" + value)
sys.stdout.write(json.dumps({"fields":{"labels": labels}}))
' "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

# update_ac_blocking_label <id> <true|false> — add/remove the ac-blocking
# marker label (ABS-82), preserving every other label.
update_ac_blocking_label() {
    local id="$1" value="$2"
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
want = sys.argv[1] == "true"
labels = (existing.get("fields",{}).get("labels",[]) or [])
labels = [l for l in labels if l != "ac-blocking"]
if want:
    labels.append("ac-blocking")
sys.stdout.write(json.dumps({"fields":{"labels": labels}}))
' "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

# update_list_labels <id> <depends_on|links> <yaml-list-value> — replace the
# labels representing a canonical list field. Value is the mock's yaml-ish list
# ("[a, b]" or "[]"); we translate to labels prefixed depends-on: / link:.
update_list_labels() {
    local id="$1" field="$2" value="$3" prefix
    case "$field" in
        depends_on) prefix="depends-on:" ;;
        links)      prefix="link:" ;;
        flags)      prefix="flag:" ;;
    esac
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
prefix = sys.argv[1]
value = sys.argv[2]
labels = (existing.get("fields",{}).get("labels",[]) or [])
# strip the target prefix, then re-add from the parsed list value
kept = [l for l in labels if not l.startswith(prefix)]
inner = value.strip()
if inner.startswith("[") and inner.endswith("]"):
    inner = inner[1:-1]
items = [x.strip() for x in inner.split(",") if x.strip()]
# Jira labels cannot contain spaces; join multiword entries with underscores.
for it in items:
    kept.append(prefix + it.replace(" ", "_"))
sys.stdout.write(json.dumps({"fields":{"labels": kept}}))
' "$prefix" "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

# update_plain_labels <id> <value> — replace the whole set of PLAIN (un-prefixed)
# Jira labels with the parsed list value, preserving the adapter-managed prefixed
# labels (role:/depends-on:/link:/flag:/ac-blocking) so they round-trip (ABS-101).
update_plain_labels() {
    local id="$1" value="$2" existing body
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
value = sys.argv[1]
labels = (existing.get("fields",{}).get("labels",[]) or [])
MANAGED = ("role:", "depends-on:", "link:", "flag:")
# keep every adapter-managed label; drop the previous plain set
kept = [l for l in labels if l.startswith(MANAGED) or l == "ac-blocking"]
inner = value.strip()
if inner.startswith("[") and inner.endswith("]"):
    inner = inner[1:-1]
for it in [x.strip() for x in inner.split(",") if x.strip()]:
    kept.append(it)
sys.stdout.write(json.dumps({"fields":{"labels": kept}}))
' "$value")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
}

cmd_comment() {
    local id="$1"; shift
    local kind="" actor="" body="" body_file="" have_body=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --kind)  [ $# -ge 2 ] || die "comment: --kind requires a value";  kind="$2";  shift 2 ;;
            --actor) [ $# -ge 2 ] || die "comment: --actor requires a value"; actor="$2"; shift 2 ;;
            --body)  [ $# -ge 2 ] || die "comment: --body requires a value";  body="$2"; have_body=1; shift 2 ;;
            # ABS-163: read the body from a file so callers can post text
            # containing shell redirection characters (< >) without those chars
            # ever reaching a Bash command line, where a restrictive permission
            # matcher parses them as redirection and denies the call.
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
        # v3 follow-up chain (ABS-75/ABS-82) + SKIP-FORWARD audit kind (ABS-84).
        follow-up|bsa-decision|skip) ;;
        # claim = the orchestrator stakes a distributed ticket claim via the
        # existing comment op — no new adapter operation (ABS-182).
        claim) ;;
        # invariant-violation = the ABS-406 wait-state watchdog's loud,
        # operator-visible signal (actor watchdog). Detection-only, never a
        # transition — degraded adapter-lane parity of ABS-391.
        invariant-violation) ;;
        *) die "comment: invalid kind '$kind'" ;;
    esac
    require_creds
    post_structured_comment "$id" "$kind" "$actor" "$body"
    echo "$id: comment added"
}

# post_structured_comment <id> <kind> <actor> <body> — POST a comment whose
# first body line encodes kind+actor as "[kind: <k> | actor: <a>]" so `get` can
# reconstruct the mock's "### <at> | kind: <k> | actor: <a>" header line. This
# is the format the orchestrator stall-detection guard parses.
#
# Newlines are byte-verbatim here (ABS-111 / Live-Run 1). The body arrives with
# REAL newlines and adf_wrap splits it into one ADF paragraph per line. The
# literal-"\n" artifact seen in live run 1 (an agent's multi-line handoff arriving
# as one line with embedded backslash-n) is fixed at its ROOT, upstream and
# tracker-agnostically: the orchestrator's extract_handoff_from_result now
# JSON-unescapes the spawn's `result` field before it ever reaches an adapter
# (scripts/orchestrator.sh, json_unescape). So this path — like the
# create/description path — stays verbatim; a body that legitimately contains the
# two characters backslash-n is posted as-is, not silently turned into a newline.
post_structured_comment() {
    local id="$1" kind="$2" actor="$3" body="$4"
    local full adf reqbody
    full="[kind: $kind | actor: $actor]
$body"
    adf="$(printf '%s' "$full" | adf_wrap)"
    # The ADF body streams over stdin, never argv: a multi-KB comment (gate-results
    # / handoff) on argv dies with E2BIG on Windows/MSYS before curl runs (ABS-263).
    reqbody="$(printf '%s' "$adf" | py 'import sys,json; sys.stdout.write(json.dumps({"body": json.loads(sys.stdin.read())}))')"
    http_call POST "/rest/api/3/issue/$id/comment" "$reqbody" >/dev/null
}

cmd_transition() {
    local id="$1" to="$2"; shift 2
    local actor="" reason="" reason_file="" have_reason=0 expect_from=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --actor)  [ $# -ge 2 ] || die "transition: --actor requires a value";  actor="$2";  shift 2 ;;
            --reason) [ $# -ge 2 ] || die "transition: --reason requires a value"; reason="$2"; have_reason=1; shift 2 ;;
            # ABS-163: read the reason from a file (see cmd_comment --body-file).
            --reason-file) [ $# -ge 2 ] || die "transition: --reason-file requires a value"; reason_file="$2"; shift 2 ;;
            # ABS-198 (Measure 3): compare-and-set guard, mirroring the mock
            # adapter. Applies the transition only if the issue is still in
            # <status>; a lost race is a logged NOOP (exit 0), not a transition.
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
    require_creds

    # Resolve the current status and the Jira transition id that lands on <to>.
    local issue from
    issue="$(http_call GET "/rest/api/3/issue/$id?fields=status")"
    from="$(canon_status "$(printf '%s' "$issue" | json_get 'd["fields"]["status"]["name"]')")"
    # ABS-198 (Measure 3): compare-and-set. If the caller declared the status it
    # expected to move FROM and the issue has since moved, NOOP (exit 0) instead
    # of transitioning — ends the actor-overwrite race. Checked before the
    # same-status guard so an already-advanced issue NOOPs cleanly.
    if [ -n "$expect_from" ] && [ "$from" != "$expect_from" ]; then
        echo "$id: NOOP compare-and-set expect-from=$expect_from actual=$from (skipped $to)"
        return 0
    fi
    [ "$from" != "$to" ] || die "transition: $id is already in '$to'"

    local trans tid
    trans="$(http_call GET "/rest/api/3/issue/$id/transitions")"
    tid="$(printf '%s' "$trans" | py "$STATUS_NORM_PY"'
import sys, json
trans = json.load(sys.stdin)
# want is the canonical target; translate to this project'\''s Jira name and
# match case-insensitively (the workflow may spell it "in review" etc.).
want = to_jira(sys.argv[1]).lower()
for t in trans.get("transitions", []):
    to = (t.get("to") or {}).get("name","")
    if to.lower() == want or t.get("name","").lower() == want:
        sys.stdout.write(str(t.get("id","")))
        break
' "$to")"
    [ -n "$tid" ] || die "transition: no Jira transition to '$to' available for $id from '$from' (check the project workflow)"

    local body
    body="$(py 'import sys,json; sys.stdout.write(json.dumps({"transition":{"id":sys.argv[1]}}))' "$tid")"
    http_call POST "/rest/api/3/issue/$id/transitions" "$body" >/dev/null

    # Record actor + reason as a transition-reason comment, mirroring the mock's
    # body text exactly so downstream parsers (e.g. last_po_park_epoch) match.
    post_structured_comment "$id" "transition-reason" "$actor" "Transition: $from -> $to. Reason: $reason"
    echo "$id: $from -> $to"
}

cmd_link() {
    local id="$1" other="$2" ltype="$3"
    case "$ltype" in
        parent-child|depends-on|origin-review|pr|relates) ;;
        *) die "link: invalid link type '$ltype' (parent-child|depends-on|origin-review|pr|relates)" ;;
    esac
    require_creds

    # Persist links as labels (link:<type>:<other>) so `get` surfaces them the
    # same way the mock's `links:` list does; depends-on is additionally mirrored
    # into the depends_on list (via a depends-on:<other> label).
    local existing
    existing="$(http_call GET "/rest/api/3/issue/$id?fields=labels")"
    local entry="$ltype:$other"

    local already
    already="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
entry = sys.argv[1].replace(" ", "_")
labels = existing.get("fields",{}).get("labels",[]) or []
sys.stdout.write("yes" if ("link:"+entry) in labels else "no")
' "$entry")"
    if [ "$already" = "yes" ]; then
        echo "$id: already linked $entry"
        return 0
    fi

    local body
    body="$(printf '%s' "$existing" | py '
import sys, json
existing = json.load(sys.stdin)
entry = sys.argv[1].replace(" ", "_")
ltype = sys.argv[2]
other = sys.argv[3].replace(" ", "_")
labels = existing.get("fields",{}).get("labels",[]) or []
labels.append("link:" + entry)
if ltype == "depends-on":
    dep = "depends-on:" + other
    if dep not in labels:
        labels.append(dep)
sys.stdout.write(json.dumps({"fields":{"labels": labels}}))
' "$entry" "$ltype" "$other")"
    http_call PUT "/rest/api/3/issue/$id" "$body" >/dev/null
    echo "$id: linked $entry"
}

cmd_children() {
    local epic="$1"
    require_creds
    local jql resp
    jql="$(fence_jql) AND parent = \"$(jql_quote "$epic")\""
    resp="$(jql_search "$jql")"
    local out
    out="$(printf '%s' "$resp" | py "$STATUS_NORM_PY"'
import sys, json
resp = json.load(sys.stdin)
lines = []
for iss in resp.get("issues", []):
    f = iss.get("fields", {})
    key = iss.get("key","")
    status = canon((f.get("status") or {}).get("name","") or "")
    summary = f.get("summary","") or ""
    lines.append("%s\t[%s]\t%s" % (key, status, summary))
sys.stdout.write("\n".join(lines))
')"
    if [ -n "$out" ]; then
        printf '%s\n' "$out"
    else
        echo "(no children)" >&2
    fi
}

# cmd_parent <id> — print the issue's parent-epic key (empty line when none).
# Thin projection of get_ticket consumed by the orchestrator's intake classifier
# (ABS-104); keeps the classifier on the adapter surface (ADR-A-0007). Jira only
# returns the "parent" field when set, so a missing parent yields "" (KeyError
# swallowed by json_get).
cmd_parent() {
    local id="$1"
    require_creds
    local issue
    issue="$(http_call GET "/rest/api/3/issue/$id?fields=parent")"
    printf '%s' "$issue" | json_get 'd["fields"]["parent"]["key"]'
    echo
}

# cmd_child_count <id> — print the number of child issues whose parent is <id>.
# One fenced JQL sweep (same budget as `children`), counting the issues array.
# Thin projection of get_epic_children consumed by the intake classifier (ABS-104).
cmd_child_count() {
    local id="$1"
    require_creds
    local jql resp
    jql="$(fence_jql) AND parent = \"$(jql_quote "$id")\""
    resp="$(jql_search "$jql")"
    printf '%s' "$resp" | py 'import sys, json; print(len(json.load(sys.stdin).get("issues", [])))'
}

cmd_events() {
    require_creds
    mkdir -p "$(dirname "$EVENTS_STATE")"
    local now current resp
    now="$(timestamp)"
    current="$EVENTS_STATE.current.$$"

    # ONE JQL sweep of the fenced project — the entire per-poll API budget.
    resp="$(jql_search "$(fence_jql)")"
    printf '%s' "$resp" | py "$STATUS_NORM_PY"'
import sys, json
resp = json.load(sys.stdin)
lines = []
for iss in resp.get("issues", []):
    key = iss.get("key","")
    status = canon((iss.get("fields",{}).get("status") or {}).get("name","") or "")
    lines.append("%s\t%s" % (key, status))
sys.stdout.write("\n".join(lines) + ("\n" if lines else ""))
' > "$current"

    if [ -f "$EVENTS_STATE" ]; then
        awk -F'\t' -v at="$now" -v state="$EVENTS_STATE" '
            FILENAME == state { prev[$1] = $2; next }
            {
                if ($1 in prev) {
                    if (prev[$1] != $2)
                        printf "{ticket_id: %s, from: %s, to: %s, at: %s}\n", $1, prev[$1], $2, at
                } else {
                    printf "{ticket_id: %s, from: null, to: %s, at: %s}\n", $1, $2, at
                }
            }
        ' "$EVENTS_STATE" "$current"
        # ABS-308: the new snapshot MERGES rather than replaces — a ticket the
        # sweep did not return (transient API hiccup, over-tight filter, a
        # paging gap) keeps its last-seen entry instead of being dropped. A
        # dropped entry re-enters the next sweep as a phantom "from: null"
        # creation event and re-classifies a RESTING ticket as freshly
        # transitioned — the PO no-op spawn loop this ticket fixes (17 paid
        # spawns/24h on one resting Backlog ticket downstream). Consequence: a
        # genuinely deleted ticket lingers in the snapshot — harmless, since an
        # absent ticket can never diff again.
        awk -F'\t' '
            NR == FNR { cur[$1] = 1; print; next }
            !($1 in cur) { print }
        ' "$current" "$EVENTS_STATE" > "$current.merged"
        mv "$current.merged" "$EVENTS_STATE"
        rm -f "$current"
    else
        awk -F'\t' -v at="$now" '
            { printf "{ticket_id: %s, from: null, to: %s, at: %s}\n", $1, $2, at }
        ' "$current"
        mv "$current" "$EVENTS_STATE"
    fi
}

# cmd_assign <id> <accountId> — PUT /rest/api/3/issue/{id}/assignee. (ABS-126)
# Mirrors mock-tracker.sh cmd_assign exactly from the caller's view.
# accountIds must arrive via env/config — never hardcoded (ADR-A-0010).
cmd_assign() {
    local id="$1" account_id="$2"
    require_creds
    local body
    body="$(py 'import sys,json; sys.stdout.write(json.dumps({"accountId": sys.argv[1]}))' "$account_id")"
    http_call PUT "/rest/api/3/issue/$id/assignee" "$body" >/dev/null
    echo "$id: assignee set to $account_id"
}

# =============================================================================
# Dispatcher — identical command surface / arity checks to mock-tracker.sh
# =============================================================================
main() {
    [ $# -ge 1 ] || { usage >&2; exit 1; }
    local cmd="$1"; shift
    case "$cmd" in
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
