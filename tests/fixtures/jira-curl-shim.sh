#!/usr/bin/env bash
# =============================================================================
# Canned-response curl shim for the offline jira-tracker.sh contract tier.
# =============================================================================
# scripts/jira-tracker.sh invokes curl as:
#   curl --config <cfg> -sS -o <out> -w '%{http_code}' -X <METHOD> \
#        [--data-binary <body>|@<file>] <url>
# This shim mimics that surface: it writes a canned JSON response to the file
# named after -o, and prints the HTTP status code (what -w '%{http_code}'
# would print) to stdout. It NEVER performs network I/O.
#
# It keeps just enough state under $JIRA_SHIM_DIR to make create->get->search->
# events flows coherent:
#   - a monotonically increasing issue counter (first key = ABS-101)
#   - a status-override file (tests flip a status to drive events diffs)
#
# The shim deliberately does NOT read the --config file (which holds the
# credential), proving the adapter delivers auth out-of-band; nothing here can
# leak the token because the token is never observed.
#
# Test hooks (env):
#   JIRA_SHIM_FORCE_HTTP=<code>   force a non-2xx HTTP code (error-path test)
#   JIRA_SHIM_FORCE_CURLFAIL=1    exit non-zero as if curl itself failed
# =============================================================================
set -u

STATE_DIR="${JIRA_SHIM_DIR:-/tmp/jira-shim}"
mkdir -p "$STATE_DIR"
COUNTER_FILE="$STATE_DIR/counter"
STATUS_OVERRIDE="$STATE_DIR/status-override"

# Test control verb: `jira-curl-shim.sh __set_status <id> <status>`
if [ "${1:-}" = "__set_status" ]; then
    printf '%s\t%s\n' "$2" "$3" > "$STATUS_OVERRIDE"
    exit 0
fi

# Simulated curl-level failure (adapter must scrub + die cleanly).
if [ -n "${JIRA_SHIM_FORCE_CURLFAIL:-}" ]; then
    echo "curl: (7) Failed to connect" >&2
    exit 7
fi

# --- Parse the adapter's curl argv --------------------------------------------
method="GET"
outfile=""
url=""
reqbody=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config)      shift 2 ;;         # ignore the credential config entirely
        -sS|-s|-S)     shift ;;
        -o)            outfile="$2"; shift 2 ;;
        -w)            shift 2 ;;         # format string; we print the code ourselves
        -X)            method="$2"; shift 2 ;;
        # --data-binary accepts either an inline body or the "@file" form the
        # adapter now uses for oversized request bodies (ABS-263): resolve @file
        # to its contents so the shim exercises the real (fixed) write path.
        --data-binary)
            if [ "${2#@}" != "$2" ]; then reqbody="$(cat "${2#@}")"; else reqbody="$2"; fi
            shift 2 ;;
        -*)            shift ;;           # any other flag: ignore
        *)             url="$1"; shift ;; # the last bare token is the URL
    esac
done

# Optional request-body capture (JQL-escaping contract test). When
# JIRA_SHIM_CAPTURE_BODY names a path, append each request body there so a test
# can assert the adapter built well-formed JSON/JQL.
if [ -n "${JIRA_SHIM_CAPTURE_BODY:-}" ] && [ -n "$reqbody" ]; then
    printf '%s\n' "$reqbody" >> "$JIRA_SHIM_CAPTURE_BODY"
fi

emit() {
    # emit <http-code> <json>
    if [ -n "${JIRA_SHIM_FORCE_HTTP:-}" ]; then
        [ -n "$outfile" ] && printf '{"errorMessages":["forced error"]}' > "$outfile"
        printf '%s' "$JIRA_SHIM_FORCE_HTTP"
        return 0
    fi
    [ -n "$outfile" ] && printf '%s' "$2" > "$outfile"
    printf '%s' "$1"
}

next_key() {
    local n=100
    [ -f "$COUNTER_FILE" ] && n="$(cat "$COUNTER_FILE")"
    n=$((n + 1))
    echo "$n" > "$COUNTER_FILE"
    echo "ABS-$n"
}

# path = everything after the site host
path="${url#*atlassian.net}"

# --- Route ---------------------------------------------------------------------
case "$method $path" in

    "POST /rest/api/3/issue")
        # create — echo a fresh key
        key="$(next_key)"
        emit 201 "{\"id\":\"10000\",\"key\":\"$key\",\"self\":\"x\"}"
        ;;

    "POST /rest/api/3/search")
        # Legacy search endpoint — removed by Atlassian (CHANGE-2046). Simulate
        # the HTTP 410 Gone the real API now returns, so a test can assert the
        # adapter no longer calls it (any use surfaces as a clean 410 error).
        emit 410 '{"errorMessages":["The requested resource /rest/api/3/search has been removed. Use /rest/api/3/search/jql instead."]}'
        ;;

    "POST /rest/api/3/search/jql")
        # JQL sweep (new endpoint) — return a canned fixed set (fenced project ABS).
        # status of ABS-102 respects the override file (for events tests).
        s102="Backlog"
        if [ -f "$STATUS_OVERRIDE" ]; then
            ov="$(awk -F'\t' '$1=="ABS-102"{print $2}' "$STATUS_OVERRIDE")"
            [ -n "$ov" ] && s102="$ov"
        fi
        # ABS-308: partial-sweep mode — ABS-103 is missing from the response,
        # as with a transient API hiccup or paging gap. The events snapshot
        # must NOT drop it (a dropped entry re-enters later as a phantom
        # "from: null" event and restarts the PO no-op spawn loop).
        if [ -n "${JIRA_SHIM_PARTIAL:-}" ]; then
            emit 200 "$(cat <<JSON
{"issues":[
  {"key":"ABS-101","fields":{"summary":"Conformance demo epic","status":{"name":"Backlog"},"issuetype":{"name":"Epic"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"An epic about conformance."}]}]}}},
  {"key":"ABS-102","fields":{"summary":"First child ticket","status":{"name":"$s102"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}}
]}
JSON
)"
            exit 0
        fi
        # ABS-308: pagination mode — the same three issues split over two
        # cursor pages, so a test can prove jql_search follows nextPageToken
        # instead of silently truncating (the phantom-events machine).
        if [ -n "${JIRA_SHIM_PAGINATE:-}" ]; then
            case "$reqbody" in
                *'"nextPageToken"'*'"P2"'*)
                    emit 200 "$(cat <<JSON
{"isLast":true,"issues":[
  {"key":"ABS-103","fields":{"summary":"Backend role","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["role:be-developer"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}}
]}
JSON
)"
                    ;;
                *)
                    emit 200 "$(cat <<JSON
{"nextPageToken":"P2","isLast":false,"issues":[
  {"key":"ABS-101","fields":{"summary":"Conformance demo epic","status":{"name":"Backlog"},"issuetype":{"name":"Epic"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"An epic about conformance."}]}]}}},
  {"key":"ABS-102","fields":{"summary":"First child ticket","status":{"name":"$s102"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}}
]}
JSON
)"
                    ;;
            esac
            exit 0
        fi
        # ABS-389: priority-ordering fixture — five issues delivered in age-ASC
        # order (as JQL `ORDER BY created ASC` would) with SCRAMBLED priority
        # labels, so a test can prove the adapter's emit step re-sorts them into
        # the canonical `priority ASC, created ASC` order (two normals prove the
        # stable within-band age tiebreak). Priority persists as a priority:<v>
        # label (ABS-261 mapping), the same technique the adapter reads on get.
        if [ -n "${JIRA_SHIM_PRIOORDER:-}" ]; then
            emit 200 "$(cat <<JSON
{"issues":[
  {"key":"ABS-390","fields":{"summary":"prio order normal old","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["priority:normal"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}},
  {"key":"ABS-391","fields":{"summary":"prio order hotfix","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["priority:hotfix"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}},
  {"key":"ABS-392","fields":{"summary":"prio order low","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["priority:low"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}},
  {"key":"ABS-393","fields":{"summary":"prio order high","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["priority:high"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}},
  {"key":"ABS-394","fields":{"summary":"prio order normal young","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["priority:normal"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}}
]}
JSON
)"
            exit 0
        fi
        emit 200 "$(cat <<JSON
{"issues":[
  {"key":"ABS-101","fields":{"summary":"Conformance demo epic","status":{"name":"Backlog"},"issuetype":{"name":"Epic"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"An epic about conformance."}]}]}}},
  {"key":"ABS-102","fields":{"summary":"First child ticket","status":{"name":"$s102"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}},
  {"key":"ABS-103","fields":{"summary":"Backend role","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["role:be-developer"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]}}}
]}
JSON
)"
        ;;

    "GET /rest/api/3/issue/ABS-103"*)
        emit 200 '{"key":"ABS-103","fields":{"summary":"Backend role","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["role:be-developer"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/ABS-101/comment"*)
        # Comments encoded the way the adapter writes them: first body line is
        # "[kind: <k> | actor: <a>]". Timestamps are Jira-native (millis + a
        # NON-UTC +0530 offset) so `get`'s normalization to ...Z is exercised.
        # Two comments: (1) the orchestrator's stall-raise decision, and (2) a
        # PO-park transition ("Needs PO Decision -> Backlog") so the orchestrator
        # helper last_po_park_epoch can detect the park from the emitted dump.
        # `total` matches the returned count -> the adapter's page loop stops
        # after one page (single-page ticket).
        emit 200 '{"startAt":0,"maxResults":100,"total":2,"comments":[
          {"created":"2026-07-04T17:30:00.000+0530","author":{"displayName":"Orchestrator"},"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"[kind: decision | actor: orchestrator]"}]},{"type":"paragraph","content":[{"type":"text","text":"STALL-RAISE rule=1 (orchestrator)"}]}]}},
          {"created":"2026-07-04T18:00:00.000+0530","author":{"displayName":"PO Agent"},"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"[kind: transition-reason | actor: po-agent]"}]},{"type":"paragraph","content":[{"type":"text","text":"Transition: Needs PO Decision -> Backlog. Reason: decided: leave in backlog"}]}]}}
        ]}'
        ;;

    # ABS-182: a ticket whose comments span TWO Jira API pages. The adapter's
    # page-exhaustion loop must fetch page 2 (startAt=2) and merge, so `get`
    # returns the full list — critical for claim adjudication, which must see
    # the freshest peer claim (spec §8). Route on the startAt offset.
    "GET /rest/api/3/issue/ABS-105/comment?startAt=0"*)
        emit 200 '{"startAt":0,"maxResults":2,"total":3,"comments":[
          {"created":"2026-07-04T10:00:00.000+0000","author":{"displayName":"Machine A"},"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"[kind: claim | actor: orchestrator]"}]},{"type":"paragraph","content":[{"type":"text","text":"page-one-oldest-claim"}]}]}},
          {"created":"2026-07-04T10:01:00.000+0000","author":{"displayName":"Machine A"},"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"[kind: notification | actor: orchestrator]"}]},{"type":"paragraph","content":[{"type":"text","text":"page-one-second"}]}]}}
        ]}'
        ;;
    "GET /rest/api/3/issue/ABS-105/comment?startAt=2"*)
        emit 200 '{"startAt":2,"maxResults":2,"total":3,"comments":[
          {"created":"2026-07-04T10:02:00.000+0000","author":{"displayName":"Machine B"},"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"[kind: claim | actor: orchestrator]"}]},{"type":"paragraph","content":[{"type":"text","text":"page-two-newest-claim"}]}]}}
        ]}'
        ;;
    "GET /rest/api/3/issue/ABS-105"*)
        emit 200 '{"key":"ABS-105","fields":{"summary":"Paginated comments","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:02:00.000+0000"}}'
        ;;

    # ABS-250: an OVERSIZED comment history (~1.5 MB — past this host's ARG_MAX,
    # and far past Windows/MSYS's ~32 KB CreateProcess limit). A response of this
    # size passed to python as an argv ARGUMENT dies with "Argument list too
    # long"; the adapter must hand it over out-of-band (stdin / page files).
    # `total` equals the returned count, so the page loop stops after one page.
    "GET /rest/api/3/issue/ABS-106/comment"*)
        if [ -n "$outfile" ]; then
            python3 - "$outfile" <<'PY'
import json, sys
blob = "EVIDENCE " * 400          # ~3.6 KB of body per comment
n = 400                           # -> ~1.5 MB total response
comments = []
for i in range(n):
    text = "LAST-COMMENT-MARKER" if i == n - 1 else "comment-%d %s" % (i, blob)
    comments.append({
        "created": "2026-07-04T10:00:00.000+0000",
        "author": {"displayName": "QAS"},
        "body": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "[kind: gate-results | actor: qas]"}]},
            {"type": "paragraph", "content": [
                {"type": "text", "text": text}]}]},
    })
with open(sys.argv[1], "w") as fh:
    json.dump({"startAt": 0, "maxResults": 1000, "total": n,
               "comments": comments}, fh)
PY
        fi
        printf '200'
        ;;
    "GET /rest/api/3/issue/ABS-106"*)
        emit 200 '{"key":"ABS-106","fields":{"summary":"Oversized comment history","status":{"name":"In Progress"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"big"}]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    # ABS-263: a MALFORMED comment page. cmd_get's page-loop parse must free its
    # mktemp dir and die cleanly instead of aborting mid-`set -e` and leaking it.
    "GET /rest/api/3/issue/ABS-107/comment"*)
        emit 200 '{"comments": [ this is not valid json'
        ;;
    "GET /rest/api/3/issue/ABS-107"*)
        emit 200 '{"key":"ABS-107","fields":{"summary":"Malformed comment page","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/"*"/comment"*)
        emit 200 '{"startAt":0,"maxResults":100,"total":0,"comments":[]}'
        ;;

    "GET /rest/api/3/issue/ABS-101"*)
        # Jira-native timestamps with a NON-UTC +0530 offset; `get` must
        # normalize created:/updated: to the mock's ...Z UTC form.
        emit 200 '{"key":"ABS-101","fields":{"summary":"Conformance demo epic","status":{"name":"Backlog"},"issuetype":{"name":"Epic"},"parent":null,"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"An epic about conformance."}]}]},"created":"2026-07-04T15:30:00.000+0530","updated":"2026-07-04T17:30:00.000+0530"}}'
        ;;

    "GET /rest/api/3/issue/ABS-102/transitions")
        # Only one legal onward transition is offered (to Ready for Development).
        emit 200 '{"transitions":[{"id":"21","name":"Start","to":{"name":"Ready for Development"}}]}'
        ;;

    "GET /rest/api/3/issue/"*"/transitions")
        emit 200 '{"transitions":[{"id":"31","name":"Advance","to":{"name":"Ready for Development"}}]}'
        ;;

    "GET /rest/api/3/issue/ABS-102"*)
        emit 200 '{"key":"ABS-102","fields":{"summary":"First child ticket","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":[],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/ABS-104"*)
        # v3 flags fixture (ABS-82): labels carry role + two flags + ac-blocking.
        emit 200 '{"key":"ABS-104","fields":{"summary":"Flagged v3 story","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":{"key":"ABS-101"},"labels":["role:fe-developer","flag:design","flag:security","ac-blocking"],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/ABS-108"*)
        # PILOT-12: an issue carrying a SINGLE native fixVersion. `get` must
        # render exactly one `fix_version: v3.1.0` frontmatter line (only-when-set),
        # byte-identical to backend-tracker.sh get, immediately before depends_on.
        emit 200 '{"key":"ABS-108","fields":{"summary":"Versioned story","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["role:be-developer"],"fixVersions":[{"name":"v3.1.0"}],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/ABS-109"*)
        # PILOT-12: an issue carrying MULTIPLE native fixVersions. The backend
        # fix_version field is single-valued, so `get` deterministically renders
        # the FIRST (primary) entry (v3.1.0) as one line — never two.
        emit 200 '{"key":"ABS-109","fields":{"summary":"Multi-versioned story","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":["role:be-developer"],"fixVersions":[{"name":"v3.1.0"},{"name":"v4.0.0"}],"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[]}]},"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "GET /rest/api/3/issue/ABS-201"*)
        # ABS-330: a parent epic carrying a fixVersion, for create-time
        # inheritance (create --parent ABS-201 with no --fix-version copies
        # v3.0.0 onto the child). Reached via GET .../ABS-201?fields=fixVersions.
        emit 200 '{"key":"ABS-201","fields":{"summary":"Versioned epic","status":{"name":"Backlog"},"issuetype":{"name":"Epic"},"parent":null,"labels":[],"fixVersions":[{"name":"v3.0.0"}],"description":null,"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    "POST /rest/api/3/issue/"*"/comment")
        emit 201 '{"id":"10100","self":"x"}'
        ;;

    "POST /rest/api/3/issue/"*"/transitions")
        emit 204 ''
        ;;

    "PUT /rest/api/3/issue/"*)
        emit 204 ''
        ;;

    "GET /rest/api/3/issue/"*)
        # generic issue GET (labels-only reads etc.)
        emit 200 '{"key":"ABS-000","fields":{"summary":"generic","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":[],"description":null,"created":"2026-07-04T10:00:00.000+0000","updated":"2026-07-04T10:00:00.000+0000"}}'
        ;;

    *)
        emit 404 '{"errorMessages":["shim: unrouted '"$method $path"'"]}'
        ;;
esac
