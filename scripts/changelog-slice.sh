#!/bin/bash
#
# =============================================================================
# changelog-slice.sh -- Emit only the from->to slice of HARNESS_CHANGELOG.yml
# =============================================================================
# The boilerplate-migration driver needs ONLY the release entries between the
# target's installed version and the current version -- breaking changes and
# migration_notes for the versions being skipped. Reading the full changelog
# (1000+ lines, grows every release, multiplies on multi-version jumps) into an
# LLM context is the exact waste this slicer removes (ABS-227 AC2).
#
# Usage:
#   scripts/changelog-slice.sh --since <from> [--to <to>] [--file <changelog>] [--format md|yaml]
#
#   --since <from>   Installed version (EXCLUSIVE lower bound). Only releases
#                    with version > <from> are emitted.
#   --to <to>        Current version (INCLUSIVE upper bound). Omit for "no cap"
#                    (everything newer than <from>).
#   --file <path>    Changelog file (default: repo-root HARNESS_CHANGELOG.yml).
#   --format md|yaml Output format (default: md).
#
# Output: only the sliced release entries, each with its summary, the subset of
# changes flagged breaking: true, and its migration_notes. Nothing else.
#
# Bash 3.2 / BSD-safe. Uses POSIX awk for parsing (no jq/yq/python dependency,
# ADR-A-0009 zero-dep bash).
# =============================================================================

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FROM=""
TO=""
FILE="$REPO_ROOT/HARNESS_CHANGELOG.yml"
FORMAT="md"

die() { echo "ERROR: $*" >&2; exit 2; }

usage() {
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --since) FROM="${2:-}"; shift 2 ;;
        --to)    TO="${2:-}"; shift 2 ;;
        --file)  FILE="${2:-}"; shift 2 ;;
        --format) FORMAT="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[ -n "$FROM" ] || die "--since <from> is required"
[ -f "$FILE" ] || die "changelog file not found: $FILE"
case "$FORMAT" in md|yaml) ;; *) die "--format must be md or yaml" ;; esac

# The parser is a single POSIX-awk pass. It buffers per in-range release so it
# can emit "none" for empty breaking/notes sections deterministically.
awk -v from="$FROM" -v to="$TO" -v fmt="$FORMAT" '
    function vnum(v,   a, n) {
        n = split(v, a, ".")
        return (a[1] + 0) * 1000000 + (a[2] + 0) * 1000 + (a[3] + 0)
    }
    function unquote(s) {
        sub(/^"/, "", s); sub(/"$/, "", s); return s
    }
    function fieldval(line, key,   s) {
        s = line
        sub("^ *" key ": *", "", s)
        return unquote(s)
    }
    function flush_change() {
        # emit the buffered change into the current release if it was breaking
        if (cur_rel >= 1 && pending_change && pending_breaking) {
            rel_breaking[cur_rel] = rel_breaking[cur_rel] "- " pending_path ": " pending_desc "\n"
        }
        pending_change = 0; pending_breaking = 0; pending_path = ""; pending_desc = ""
    }
    BEGIN { in_releases = 0; cur_rel = 0; count = 0; mode = "" }
    /^releases:/ { in_releases = 1; next }
    in_releases == 0 { next }

    /^  - version:/ {
        flush_change()
        ver = $0; sub(/^  - version: */, "", ver); ver = unquote(ver)
        vn = vnum(ver)
        in_range = (vn > vnum(from)) && (to == "" || vn <= vnum(to))
        mode = ""
        if (in_range) {
            count++
            cur_rel = count
            rel_ver[cur_rel] = ver
            rel_date[cur_rel] = ""
            rel_summary[cur_rel] = ""
            rel_breaking[cur_rel] = ""
            rel_notes[cur_rel] = ""
        } else {
            cur_rel = 0
        }
        next
    }

    cur_rel == 0 { next }

    /^    date:/    { rel_date[cur_rel] = fieldval($0, "date"); next }
    /^    summary:/ { rel_summary[cur_rel] = fieldval($0, "summary"); next }
    /^    changes:/ { flush_change(); mode = "changes"; next }
    /^    migration_notes:/ { flush_change(); mode = "notes"; next }
    /^    upgrade_doc:/ { next }

    mode == "changes" && /^      - path:/ {
        flush_change()
        pending_change = 1
        pending_path = $0; sub(/^      - path: */, "", pending_path); pending_path = unquote(pending_path)
        next
    }
    mode == "changes" && /^        description:/ { pending_desc = fieldval($0, "description"); next }
    mode == "changes" && /^        breaking: *true/  { pending_breaking = 1; next }
    mode == "changes" && /^        breaking: *false/ { pending_breaking = 0; next }

    mode == "notes" && /^      - / {
        s = $0
        sub(/^      - /, "", s)
        rel_notes[cur_rel] = rel_notes[cur_rel] "- " unquote(s) "\n"
        next
    }

    END {
        flush_change()
        if (fmt == "yaml") {
            print "# Sliced from " from " (exclusive) to " (to == "" ? "HEAD" : to) " (inclusive)"
            print "releases:"
        }
        for (i = 1; i <= count; i++) {
            if (fmt == "yaml") {
                print "  - version: \"" rel_ver[i] "\""
                print "    date: \"" rel_date[i] "\""
                print "    breaking_changes:"
                if (rel_breaking[i] == "") { print "      []" }
                else { n = split(rel_breaking[i], b, "\n"); for (j = 1; j <= n; j++) if (b[j] != "") { s = b[j]; sub(/^- /, "", s); print "      - \"" s "\"" } }
                print "    migration_notes:"
                if (rel_notes[i] == "") { print "      []" }
                else { n = split(rel_notes[i], m, "\n"); for (j = 1; j <= n; j++) if (m[j] != "") { s = m[j]; sub(/^- /, "", s); print "      - \"" s "\"" } }
                continue
            }
            # markdown
            print "## " rel_ver[i] " (" rel_date[i] ")"
            print ""
            if (rel_summary[i] != "") { print rel_summary[i]; print "" }
            print "### Breaking changes"
            if (rel_breaking[i] == "") { print "- none" }
            else { printf "%s", rel_breaking[i] }
            print ""
            print "### Migration notes"
            if (rel_notes[i] == "") { print "- none" }
            else { printf "%s", rel_notes[i] }
            print ""
        }
        if (count == 0 && fmt == "md") {
            print "_No boilerplate changelog entries between " from " and " (to == "" ? "HEAD" : to) "._"
        }
    }
' "$FILE"
