#!/usr/bin/env bash
# =============================================================================
# Canned-response curl shim for scripts/jira-version.sh (ABS-226 offline tier).
# =============================================================================
# jira-version.sh invokes curl as:
#   curl -sS --config <cfg> -H "Accept: application/json" -X <METHOD> <url> \
#        [-H "Content-Type: application/json" --data <body>]
# and reads the response from STDOUT (no -o/-w). This shim mirrors that surface:
# it writes the canned JSON response to stdout and NEVER performs network I/O.
# It deliberately does not read the --config file (which holds the credential),
# so the token can never be observed here.
#
# Test hook: JV_CAPTURE=<path> appends each request body (one JSON per line) so a
# test can assert the PUT body shape (released + optional description).
# =============================================================================
set -u

method="GET"; url=""; body=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config)      shift 2 ;;
        -sS|-s|-S)     shift ;;
        -H)            shift 2 ;;
        -X)            method="$2"; shift 2 ;;
        --data)        body="$2"; shift 2 ;;
        # Resolve the "@file" form the adapter uses for oversized bodies (ABS-263).
        --data-binary)
            if [ "${2#@}" != "$2" ]; then body="$(cat "${2#@}")"; else body="$2"; fi
            shift 2 ;;
        -*)            shift ;;
        *)             url="$1"; shift ;;
    esac
done

path="${url#*atlassian.net}"

if [ -n "${JV_CAPTURE:-}" ] && [ -n "$body" ]; then
    printf '%s\n' "$body" >> "$JV_CAPTURE"
fi

case "$method $path" in
    "GET /rest/api/3/project/"*"/versions")
        printf '%s' '[{"name":"9.9.0","released":false,"id":"55501"},{"name":"9.9.1","released":false,"id":"55502"}]' ;;
    "GET /rest/api/3/project/"*)
        printf '%s' '{"id":"12345"}' ;;
    "PUT /rest/api/3/version/"*)
        printf '%s' '' ;;
    *)
        printf '%s' '{}' ;;
esac
