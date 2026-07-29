#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# jira-version.sh — Jira project-version (release) helper (ABS-111)
# =============================================================================
# Makes Jira the source of truth for the boilerplate's NEXT version: releases
# are planned as Jira project versions; the release tooling resolves the next
# tag from here instead of a hand-typed argument.
#
#   scripts/jira-version.sh list             all versions: name<TAB>released<TAB>id
#   scripts/jira-version.sh next             name of the LOWEST unreleased version
#                                            (the planned next jump); exit 1 if none
#   scripts/jira-version.sh create <name>    create an unreleased version (idempotent:
#                                            exit 0 + notice when it already exists)
#   scripts/jira-version.sh release <name>   mark the version released (today's date)
#   scripts/jira-version.sh release <name> --description-file <f>
#                                            mark released AND set the version
#                                            description from <f> in the same PUT
#                                            (atomic; ABS-226). Without the flag,
#                                            the release behaviour is unchanged.
#
# Environment (identical to scripts/jira-tracker.sh — human-provisioned):
#   JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN (secret), JIRA_PROJECT_KEY
#
# Consumers: scripts/promote-release.sh and scripts/pre-release-check.sh fall
# back to `next` when no version argument is given (Jira-first, arg still wins).
# Marking the version released stays a printed HUMAN follow-up of promotion —
# this script never runs implicitly.
#
# Token safety mirrors jira-tracker.sh: the token reaches curl via a mode-600
# --config file (never argv), and never appears in output. bash 3.2 + python3.
# =============================================================================

JIRA_SITE="${JIRA_SITE:-}"
JIRA_EMAIL="${JIRA_EMAIL:-}"
JIRA_API_TOKEN="${JIRA_API_TOKEN:-}"
JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY:-}"
CURL_BIN="${JIRA_CURL:-curl}"   # test seam, same name as the adapter's

die() { echo "ERROR: $*" >&2; exit 1; }

[ -n "$JIRA_SITE" ]        || die "JIRA_SITE is not set (e.g. https://acme.atlassian.net)"
[ -n "$JIRA_EMAIL" ]       || die "JIRA_EMAIL is not set"
[ -n "$JIRA_API_TOKEN" ]   || die "JIRA_API_TOKEN is not set"
[ -n "$JIRA_PROJECT_KEY" ] || die "JIRA_PROJECT_KEY is not set"

py() { python3 -c "$1" "${@:2}"; }

# http <METHOD> <path> [json-body] — one authenticated Jira REST call.
http() {
    local method="$1" path="$2" body="${3:-}"
    local cfg out rc=0
    cfg="$(mktemp)"
    chmod 600 "$cfg"
    printf 'user = "%s:%s"\n' "$JIRA_EMAIL" "$JIRA_API_TOKEN" > "$cfg"
    set -- -sS --config "$cfg" -H "Accept: application/json" -X "$method" "$JIRA_SITE$path"
    if [ -n "$body" ]; then
        set -- "$@" -H "Content-Type: application/json" --data "$body"
    fi
    out="$("$CURL_BIN" "$@" 2>/dev/null)" || rc=$?
    rm -f "$cfg"
    [ "$rc" -eq 0 ] || die "jira API $method $path failed (curl exit $rc)"
    printf '%s' "$out"
}

versions_json() { http GET "/rest/api/3/project/$JIRA_PROJECT_KEY/versions"; }

cmd_list() {
    versions_json | py '
import sys, json
for v in json.load(sys.stdin):
    print("%s\t%s\t%s" % (v.get("name",""), "released" if v.get("released") else "unreleased", v.get("id","")))
'
}

cmd_next() {
    local name
    name="$(versions_json | py '
import sys, json, re
def semkey(n):
    m = re.findall(r"\d+", n)
    return [int(x) for x in m[:3]] + [0] * (3 - len(m[:3]))
un = [v["name"] for v in json.load(sys.stdin) if not v.get("released") and not v.get("archived")]
if un:
    print(sorted(un, key=semkey)[0])
')"
    [ -n "$name" ] || die "no unreleased version planned in $JIRA_PROJECT_KEY (create one: scripts/jira-version.sh create <name>)"
    printf '%s\n' "$name"
}

project_id() {
    http GET "/rest/api/3/project/$JIRA_PROJECT_KEY" | py '
import sys, json
print(json.load(sys.stdin)["id"])
'
}

version_id() {
    versions_json | py '
import sys, json
want = sys.argv[1]
for v in json.load(sys.stdin):
    if v.get("name") == want:
        print(v["id"]); break
' "$1"
}

cmd_create() {
    local name="$1" pid body
    if [ -n "$(version_id "$name")" ]; then
        echo "version '$name' already exists in $JIRA_PROJECT_KEY (unchanged)"
        return 0
    fi
    pid="$(project_id)"
    body="$(py '
import sys, json
print(json.dumps({"name": sys.argv[1], "projectId": int(sys.argv[2]), "released": False}))
' "$name" "$pid")"
    http POST "/rest/api/3/version" "$body" >/dev/null
    echo "created version '$name' in $JIRA_PROJECT_KEY"
}

cmd_release() {
    local name="" descfile="" description="" vid body
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
    vid="$(version_id "$name")"
    [ -n "$vid" ] || die "version '$name' not found in $JIRA_PROJECT_KEY"
    if [ -n "$descfile" ]; then
        [ -f "$descfile" ] || die "release: --description-file '$descfile' not found"
        description="$(cat "$descfile")"
    fi
    # The description (plain string on the version object) is stamped in the SAME
    # PUT that marks the version released — atomic, no window where a released
    # version lacks its notes link (ABS-226 AC1). Empty description => field omitted
    # => unchanged behaviour.
    body="$(py '
import sys, json, datetime
obj = {"released": True, "releaseDate": datetime.date.today().isoformat()}
if len(sys.argv) > 1 and sys.argv[1]:
    obj["description"] = sys.argv[1]
print(json.dumps(obj))
' "$description")"
    http PUT "/rest/api/3/version/$vid" "$body" >/dev/null
    echo "released version '$name' in $JIRA_PROJECT_KEY"
}

case "${1:-}" in
    list)    cmd_list ;;
    next)    cmd_next ;;
    create)  [ $# -ge 2 ] || die "create: version name required"; cmd_create "$2" ;;
    release) shift; cmd_release "$@" ;;
    *) die "usage: jira-version.sh list | next | create <name> | release <name> [--description-file <f>]" ;;
esac
