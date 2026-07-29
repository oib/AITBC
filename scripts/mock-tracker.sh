#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Mock Task-Tracking Adapter (blueprint §18)
# =============================================================================
# Zero-dependency reference implementation of the task-tracking capability
# (profiles/neutral/adapters/task-tracking.md): tickets are markdown files with
# YAML frontmatter in work/tickets/, transitions are frontmatter edits
# validated against profiles/neutral/adapters/statuses.yaml, and events are
# polling diffs of ticket statuses against a snapshot (work/.events-state).
#
# Uses only bash + awk/grep (BSD and GNU compatible). No yq/jq/python.
# Doubles as the conformance reference for new adapters: a new adapter is
# correct when the full dry-run (tests/test-mock-tracker.sh) behaves the same.
#
# Environment overrides (mainly for tests):
#   MOCK_TRACKER_TICKETS_DIR  ticket directory (default: <repo>/work/tickets)
#   MOCK_TRACKER_STATUSES     status machine   (default: <repo>/profiles/neutral/adapters/statuses.yaml)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TICKETS_DIR="${MOCK_TRACKER_TICKETS_DIR:-$REPO_ROOT/work/tickets}"
STATUSES_FILE="${MOCK_TRACKER_STATUSES:-$REPO_ROOT/profiles/neutral/adapters/statuses.yaml}"
EVENTS_STATE="$(dirname "$TICKETS_DIR")/.events-state"

usage() {
    cat <<'EOF'
mock-tracker.sh — mock task-tracking adapter (blueprint §18)

Usage: scripts/mock-tracker.sh <command> [args]

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
                                           equals L (normal|fastlane); a ticket
                                           with no lane field counts as normal.    (search_tickets)
  create --type <epic|ticket|subtask> --title <title> [--prefix <PFX>] [--parent <id>]
         [--role <be-developer|fe-developer|data-engineer>] [--body-file <path>] [--lane <normal|fastlane>]
         [--flag <design|security|data|skip-review|skip-test>]... [--label <label>]... [--ac-blocking]
         [--priority <hotfix|high|normal|low>]
                                           Create a ticket; prints the new id.
                                           Optional --lane sets the fastlane
                                           routing field (normal|fastlane,
                                           default normal); it is a first-class
                                           frontmatter field, not a label (ABS-319).
                                           Ids auto-increment per prefix
                                           (default prefix: DEMO). Optional
                                           --role sets the implementer-role hint
                                           the orchestrator reads (ABS-36 §2.2).
                                           Optional --flag (repeatable) sets the
                                           v3 conditional-stage flags; optional
                                           --ac-blocking marks a follow-up story
                                           the JOIN rule must count (ABS-82,
                                           mirroring the role: hint).
                                           Optional --label (repeatable) sets
                                           free-form labels; orchestrator-ready
                                           is the Backlog opt-in gate (ABS-101).
                                           Optional --body-file seeds the ticket
                                           body from a file (enriched goal/scope/
                                           AC) instead of the _TBD_ template.     (create_ticket)
  update <id> <field> <value>              Update a frontmatter field
                                           (title|type|parent|depends_on|links|
                                           lane|flags|labels|ac_blocking|priority;
                                           lane accepts normal|fastlane (ABS-319);
                                           priority is a Human/PO action, ABS-261;
                                           status changes go through transition).
                                           Two extra fields rewrite the ticket
                                           BODY in place, preserving comments
                                           (AC-rework after enrichment, ABS-252):
                                             update <id> body <text>
                                             update <id> body-file <path>
                                           Prefer body-file: it keeps shell
                                           redirection chars (< >) off the
                                           command line (ABS-163).                (update_ticket)
  comment <id> --kind <kind> --actor <actor> (--body <text> | --body-file <path>)
                                           Append a timestamped comment.
                                           --body-file reads the body from a file
                                           so text with shell redirection chars
                                           (< >) never hits a Bash command line
                                           (ABS-163).                             (comment)
  transition <id> <to-status> --actor <actor> (--reason <text> | --reason-file <path>) [--expect-from <status>]
                                           Status change, validated against
                                           statuses.yaml; records actor + reason
                                           as a transition comment. --reason-file
                                           reads the reason from a file (ABS-163).
                                           --expect-from <status> is a
                                           compare-and-set guard: if the ticket
                                           is no longer in <status> the call is a
                                           logged NOOP (exit 0), not a transition
                                           (ABS-198).                             (transition)
  link <id> <other> <link-type>            Record a link; types: parent-child |
                                           depends-on | origin-review | pr |
                                           relates.                              (link)
  children <epic-id>                       Child tickets with status summary.     (get_epic_children)
  parent <id>                              Print the ticket's parent-epic id, or
                                           an empty line when it has none. Thin
                                           read the orchestrator intake classifier
                                           consumes (ABS-104).                    (get_ticket.parent)
  child-count <id>                         Print the count of tickets whose parent
                                           is <id> (0 when none). Thin read the
                                           intake classifier consumes (ABS-104).  (get_epic_children.count)
  events                                   Poll: print status-change events since
                                           the last call as
                                           {ticket_id, from, to, at},
                                           then update the snapshot
                                           (work/.events-state).                  (subscribe_events)
  assign <id> <accountId>                  Set the assignee of a ticket.          (assign_ticket)

Comment kinds: understanding | transition-reason | gate-results | handoff | decision | notification | follow-up | bsa-decision | skip
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

ticket_file() {
    echo "$TICKETS_DIR/$1.md"
}

require_ticket() {
    [ -f "$(ticket_file "$1")" ] || die "ticket not found: $1 (looked in $TICKETS_DIR)"
}

# --- Frontmatter helpers (awk only; BSD/GNU portable) ------------------------

# fm_get <file> <key> — print the value of a frontmatter field (empty if unset).
fm_get() {
    awk -v key="$2" '
        NR == 1 && $0 == "---" { fm = 1; next }
        fm && $0 == "---" { exit }
        fm && index($0, key ": ") == 1 { print substr($0, length(key) + 3); exit }
        fm && $0 == key ":" { print ""; exit }
    ' "$1"
}

# fm_set <file> <key> <value> — rewrite one frontmatter field in place.
fm_set() {
    local tmp="$1.tmp.$$"
    awk -v key="$2" -v value="$3" '
        NR == 1 && $0 == "---" { fm = 1; print; next }
        fm == 1 && $0 == "---" { fm = 2; print; next }
        fm == 1 && (index($0, key ": ") == 1 || $0 == key ":") {
            if (value == "") print key ":"; else print key ": " value
            next
        }
        { print }
    ' "$1" > "$tmp" && mv "$tmp" "$1"
}

# ticket_body <file> — print everything after the frontmatter (the body).
ticket_body() {
    awk '
        NR == 1 && $0 == "---" { fm = 1; next }
        fm == 1 && $0 == "---" { fm = 2; next }
        fm == 2 { print }
    ' "$1"
}

# set_body <file> <text> — replace the ticket body (everything between the
# frontmatter and the '## Comments' section) with <text>. Frontmatter and every
# existing comment survive verbatim, so an AC-rework after enrichment rewrites
# the body instead of patching it with a comment (ABS-252). A body-less ticket
# (no '## Comments' heading yet) is fine: append_comment self-heals the heading.
# BOUNDARY ASSUMPTION: the comment section is delimited by the EXACT line
# `## Comments` — a ticket body that itself contains that heading confuses the
# boundary on a later rewrite (mock storage quirk; the Jira binding is immune,
# as description and comments are separate fields). $text must NOT contain a
# bare `## Comments` line.
set_body() {
    local file="$1" text="$2" tmp="$1.tmp.$$"
    {
        awk '
            NR == 1 && $0 == "---" { fm = 1; print; next }
            fm == 1 { print; if ($0 == "---") exit }
        ' "$file"
        printf '\n%s\n' "$text"
        if grep -q '^## Comments$' "$file"; then
            printf '\n'
            awk '/^## Comments$/ { c = 1 } c { print }' "$file"
        fi
    } > "$tmp" && mv "$tmp" "$file"
}

# text_matches <file> <query> — case-insensitive substring match against the
# ticket title and body.
text_matches() {
    fm_get "$1" title | grep -qiF -- "$2" && return 0
    ticket_body "$1" | grep -qiF -- "$2"
}

# lane_of <file> — print the ticket's lane, defaulting to "normal" when the
# field is absent (pre-ABS-319 tickets are readable; normal is the default lane).
lane_of() {
    local l
    l="$(fm_get "$1" lane)"
    echo "${l:-normal}"
}

# label_matches <file> <label> — 0 (true) when the labels frontmatter list
# contains <label> EXACTLY. Splits "labels: [a, b-c]" on brackets/commas into one
# trimmed token per field; an exact ($i == want) compare avoids the substring
# false-positive a bare grep -w would hit (e.g. "ready" inside "orchestrator-ready").
label_matches() {
    fm_get "$1" labels | tr -d '[]' | awk -v want="$2" -F',' '
        { for (i = 1; i <= NF; i++) { gsub(/^[ \t]+|[ \t]+$/, "", $i); if ($i == want) f = 1 } }
        END { exit(f ? 0 : 1) }'
}

# append_comment <file> <timestamp> <kind> <actor> <body>
append_comment() {
    local file="$1" at="$2" kind="$3" actor="$4" body="$5"
    grep -q '^## Comments$' "$file" || printf '\n## Comments\n' >> "$file"
    printf '\n### %s | kind: %s | actor: %s\n\n%s\n' "$at" "$kind" "$actor" "$body" >> "$file"
}

# --- Status machine (statuses.yaml) ------------------------------------------

require_statuses_file() {
    [ -f "$STATUSES_FILE" ] || die "status machine not found: $STATUSES_FILE"
}

# allowed_next <from> — print the allowed next statuses, one per line.
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

# --- Commands -----------------------------------------------------------------

cmd_get() {
    require_ticket "$1"
    cat "$(ticket_file "$1")"
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
    local f id type status parent title priority created rank tab
    tab="$(printf '\t')"
    # ABS-389: emit id<TAB>type<TAB>status<TAB>priority<TAB>title, ordered by the
    # canonical cross-adapter contract `priority ASC, created ASC` (see
    # profiles/neutral/adapters/task-tracking.md). Rows are prefixed with a
    # priority rank digit (hotfix=0<high=1<normal=2<low=3) then the `created`
    # timestamp, stable-sorted on both, then the two sort keys are stripped.
    # ISO-8601 Z timestamps sort correctly lexicographically; -s keeps the on-disk
    # (id-glob) order as a deterministic tiebreak for equal (priority,created).
    for f in "$TICKETS_DIR"/*.md; do
        [ -e "$f" ] || continue
        id="$(fm_get "$f" id)"
        type="$(fm_get "$f" type)"
        status="$(fm_get "$f" status)"
        parent="$(fm_get "$f" parent)"
        title="$(fm_get "$f" title)"
        priority="$(fm_get "$f" priority)"; priority="${priority:-normal}"
        created="$(fm_get "$f" created)"
        [ -z "$f_status" ] || [ "$status" = "$f_status" ] || continue
        [ -z "$f_type" ]   || [ "$type" = "$f_type" ]     || continue
        [ -z "$f_parent" ] || [ "$parent" = "$f_parent" ] || continue
        [ -z "$f_text" ]   || text_matches "$f" "$f_text" || continue
        [ -z "$f_label" ]  || label_matches "$f" "$f_label" || continue
        [ -z "$f_lane" ]   || [ "$(lane_of "$f")" = "$f_lane" ] || continue
        case "$priority" in hotfix) rank=0 ;; high) rank=1 ;; low) rank=3 ;; *) rank=2 ;; esac
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$rank" "$created" "$id" "$type" "$status" "$priority" "$title"
    done | sort -t "$tab" -k1,1 -k2,2 -s | cut -f3-
}

cmd_create() {
    local type="" title="" prefix="DEMO" parent="" role="" body_file="" flags="" labels="" ac_blocking="" lane="normal" priority=
    while [ $# -gt 0 ]; do
        case "$1" in
            --type)      [ $# -ge 2 ] || die "create: --type requires a value";      type="$2";      shift 2 ;;
            --title)     [ $# -ge 2 ] || die "create: --title requires a value";     title="$2";     shift 2 ;;
            --prefix)    [ $# -ge 2 ] || die "create: --prefix requires a value";    prefix="$2";    shift 2 ;;
            --parent)    [ $# -ge 2 ] || die "create: --parent requires a value";    parent="$2";    shift 2 ;;
            --role)      [ $# -ge 2 ] || die "create: --role requires a value";      role="$2";      shift 2 ;;
            --body-file) [ $# -ge 2 ] || die "create: --body-file requires a value"; body_file="$2"; shift 2 ;;
            --lane)
                # First-class fastlane routing field (ABS-319), default normal.
                [ $# -ge 2 ] || die "create: --lane requires a value"
                case "$2" in
                    normal|fastlane) lane="$2" ;;
                    *) die "create: invalid lane '$2' (normal|fastlane)" ;;
                esac
                shift 2 ;;
            --flag)
                # Repeatable v3 conditional-stage flag (ABS-82).
                [ $# -ge 2 ] || die "create: --flag requires a value"
                case "$2" in
                    design|security|data|skip-review|skip-test) ;;
                    *) die "create: invalid flag '$2' (design|security|data|skip-review|skip-test)" ;;
                esac
                case "$flags" in
                    *"$2"*) ;;  # dedupe repeats of the same flag
                    "") flags="$2" ;;
                    *)  flags="$flags, $2" ;;
                esac
                shift 2 ;;
            --label)
                # Repeatable free-form label (ABS-101). orchestrator-ready is the
                # Backlog opt-in gate the orchestrator reads; others are arbitrary.
                [ $# -ge 2 ] || die "create: --label requires a value"
                case "$2" in
                    ""|*[!A-Za-z0-9._:-]*) die "create: invalid label '$2' (allowed: A-Za-z0-9 . _ - :)" ;;
                esac
                # Dedupe on exact token — a substring check would swallow a
                # distinct label nested in an earlier one (e.g. "ready" inside
                # "orchestrator-ready"), the same pitfall label_matches avoids.
                case ", $labels," in
                    *", $2,"*) ;;
                    ", ,")     labels="$2" ;;
                    *)         labels="$labels, $2" ;;
                esac
                shift 2 ;;
            --ac-blocking) ac_blocking="true"; shift ;;
            --priority)
                # ABS-261/ABS-242 canonical priority. Only-when-given rule (like
                # role/flags) so pre-priority tickets stay byte-identical.
                [ $# -ge 2 ] || die "create: --priority requires a value"
                case "$2" in
                    hotfix|high|normal|low) priority="$2" ;;
                    *) die "create: invalid priority '$2' (hotfix|high|normal|low)" ;;
                esac
                shift 2 ;;
            *) die "create: unknown argument: $1" ;;
        esac
    done
    [ -n "$type" ] || die "create: --type is required (epic|ticket|subtask)"
    case "$type" in
        epic|ticket|subtask) ;;
        *) die "create: invalid type '$type' (epic|ticket|subtask)" ;;
    esac
    [ -n "$title" ] || die "create: --title is required"
    [ -z "$parent" ] || require_ticket "$parent"
    # Optional implementer role hint (spec ABS-36 §2.2 / open question B).
    if [ -n "$role" ]; then
        case "$role" in
            be-developer|fe-developer|data-engineer) ;;
            *) die "create: invalid role '$role' (be-developer|fe-developer|data-engineer)" ;;
        esac
    fi
    # Optional enriched body: seed the ticket body from a file instead of the
    # _TBD_ template. Lets the PO-Agent persist decomposition enrichment
    # (goal/scope/AC) through the adapter, honoring the "adapter-only, never
    # touch work/tickets/*.md directly" boundary (ORCHESTRATOR_SOP Overview, ABS-36).
    [ -z "$body_file" ] || [ -f "$body_file" ] || die "create: --body-file not found: $body_file"

    mkdir -p "$TICKETS_DIR"

    # Auto-increment the id per prefix (highest existing number + 1).
    local max=0 n f base
    for f in "$TICKETS_DIR/$prefix"-*.md; do
        [ -e "$f" ] || continue
        base="$(basename "$f" .md)"
        n="${base##*-}"
        case "$n" in ''|*[!0-9]*) continue ;; esac
        if [ "$n" -gt "$max" ]; then max="$n"; fi
    done
    local id="$prefix-$((max + 1))"
    local now file
    now="$(timestamp)"
    file="$(ticket_file "$id")"

    {
        echo "---"
        echo "id: $id"
        echo "type: $type"
        echo "title: $title"
        echo "status: Backlog"
        if [ -n "$parent" ]; then echo "parent: $parent"; else echo "parent:"; fi
        # First-class fastlane routing field (ABS-319): ALWAYS emitted with the
        # default 'normal' so lane is a structural attribute the orchestrator
        # reads directly — not a label. Replaces the interim batch-candidate label.
        echo "lane: $lane"
        # Optional: only emitted when --role given, so existing tickets and other
        # adapters are unaffected (spec ABS-36 §2.2, open question B).
        if [ -n "$role" ]; then echo "role: $role"; fi
        # Optional v3 flags + AC-blocking marker (ABS-82), same only-when-given
        # rule as role: so pre-v3 tickets stay byte-identical.
        if [ -n "$flags" ]; then echo "flags: [$flags]"; fi
        # Optional free-form labels (ABS-101), same only-when-given rule as flags:
        # so pre-ABS-101 tickets stay byte-identical.
        if [ -n "$labels" ]; then echo "labels: [$labels]"; fi
        if [ -n "$ac_blocking" ]; then echo "ac_blocking: true"; fi
        # ABS-261/ABS-242 canonical priority; only-when-given so pre-priority
        # tickets stay byte-identical (an absent field reads as normal downstream).
        if [ -n "$priority" ]; then echo "priority: $priority"; fi
        echo "depends_on: []"
        echo "links: []"
        echo "created: $now"
        echo "updated: $now"
        echo "---"
        if [ -n "$body_file" ]; then
            # Enriched body supplied by the caller (goal/scope/AC/references).
            # A leading blank line keeps the frontmatter and body separated;
            # a missing '## Comments' heading is self-healed by append_comment.
            echo ""
            cat "$body_file"
        else
            cat <<'BODY'

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

## Comments
BODY
        fi
    } > "$file"

    echo "$id"
}

cmd_update() {
    local id="$1" field="$2" value="$3"
    require_ticket "$id"
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
        priority)
            # ABS-261/ABS-242 canonical priority — a Human/PO board action; seats
            # never raise it (orchestrator _common-rules charter line).
            case "$value" in
                hotfix|high|normal|low) ;;
                *) die "update: invalid priority '$value' (hotfix|high|normal|low)" ;;
            esac
            ;;
        flags)
            # v3 conditional-stage flags (ABS-82): yaml-ish list, members validated.
            case "$value" in
                "["*"]") ;;
                *) die "update: flags value must be a list like '[design, security]'" ;;
            esac
            local member
            for member in $(printf '%s' "$value" | tr -d '[],' ); do
                case "$member" in
                    design|security|data|skip-review|skip-test) ;;
                    *) die "update: invalid flag '$member' (design|security|data|skip-review|skip-test)" ;;
                esac
            done
            ;;
        labels)
            # Free-form labels (ABS-101): yaml-ish list, replace-whole-set. Each
            # member is charset-validated; orchestrator-ready gates the Backlog
            # intake but is not special-cased here (any label is allowed).
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
            # Ticket-body rewrite (ABS-252). `body` takes the text inline;
            # `body-file` reads it from a path and is the form seats should use —
            # it keeps shell redirection chars (< >) off the command line, which
            # the dontAsk permission matcher would otherwise deny (ABS-163).
            if [ "$field" = "body-file" ]; then
                [ -f "$value" ] || die "update: body-file not found: $value"
            fi
            ;;
        *) die "update: unknown field '$field' (title|type|parent|depends_on|links|lane|flags|labels|ac_blocking|priority|iteration_cap|body|body-file)" ;;
    esac
    local f
    f="$(ticket_file "$id")"
    if [ "$field" = "body" ] || [ "$field" = "body-file" ]; then
        local text="$value"
        [ "$field" = "body" ] || text="$(cat "$value")"
        set_body "$f" "$text"
        fm_set "$f" updated "$(timestamp)"
        echo "$id: body updated"
        return
    fi
    if [ "$field" = "flags" ] || [ "$field" = "labels" ] || [ "$field" = "ac_blocking" ] || [ "$field" = "lane" ] || [ "$field" = "priority" ] || [ "$field" = "iteration_cap" ]; then
        # These fields may be absent in the frontmatter — optional (only-when-given
        # at create) for flags/labels/ac_blocking/priority, and absent on
        # pre-ABS-319 tickets for lane; fm_set only rewrites existing keys,
        # so insert on first set.
        if [ -z "$(fm_get "$f" "$field")" ] && ! grep -q "^$field:" "$f"; then
            local tmp="$f.tmp.$$"
            awk -v key="$field" -v value="$value" '
                NR == 1 && $0 == "---" { fm = 1; print; next }
                fm == 1 && index($0, "depends_on:") == 1 {
                    print key ": " value; print; fm = 2; next
                }
                { print }
            ' "$f" > "$tmp" && mv "$tmp" "$f"
        else
            fm_set "$f" "$field" "$value"
        fi
    else
        fm_set "$f" "$field" "$value"
    fi
    fm_set "$f" updated "$(timestamp)"
    echo "$id: $field updated"
}

cmd_comment() {
    local id="$1"; shift
    require_ticket "$id"
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
        # v3 follow-up chain (ABS-75/ABS-82): an agent files a follow-up
        # recommendation; the sweep watcher spawns the BSA, whose reply is the
        # bsa-decision comment that answers it. skip = the orchestrator's
        # SKIP-FORWARD audit trail (ABS-84).
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
    local f now
    f="$(ticket_file "$id")"
    now="$(timestamp)"
    append_comment "$f" "$now" "$kind" "$actor" "$body"
    fm_set "$f" updated "$now"
    echo "$id: comment added"
}

cmd_transition() {
    local id="$1" to="$2"; shift 2
    require_ticket "$id"
    require_statuses_file
    local actor="" reason="" reason_file="" have_reason=0 expect_from=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --actor)  [ $# -ge 2 ] || die "transition: --actor requires a value";  actor="$2";  shift 2 ;;
            --reason) [ $# -ge 2 ] || die "transition: --reason requires a value"; reason="$2"; have_reason=1; shift 2 ;;
            # ABS-163: read the reason from a file (see cmd_comment --body-file).
            --reason-file) [ $# -ge 2 ] || die "transition: --reason-file requires a value"; reason_file="$2"; shift 2 ;;
            # ABS-198 (Measure 3): compare-and-set guard. When given, the
            # transition is applied ONLY if the ticket is still in <status>; if
            # another actor moved it first the call is a logged NOOP (exit 0),
            # never a transition — this ends the actor-overwrite race (tdm vs
            # operator vs decision-seat) the ABS-172 cascade exhibited.
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

    local f from
    f="$(ticket_file "$id")"
    from="$(fm_get "$f" status)"
    # ABS-198 (Measure 3): compare-and-set. If the caller declared the status it
    # expected to move FROM and the ticket has since moved elsewhere, do NOT
    # transition — emit a NOOP the caller can grep and exit 0 (a lost race is a
    # valid outcome, not an error). Checked before the same-status guard so an
    # already-advanced ticket NOOPs cleanly instead of dying.
    if [ -n "$expect_from" ] && [ "$from" != "$expect_from" ]; then
        echo "$id: NOOP compare-and-set expect-from=$expect_from actual=$from (skipped $to)"
        return 0
    fi
    [ "$from" != "$to" ] || die "transition: $id is already in '$to'"
    if ! allowed_next "$from" | grep -qxF "$to"; then
        die "transition: illegal transition '$from' -> '$to' for $id (allowed from '$from': $(allowed_next "$from" | paste -sd, -))"
    fi

    local now
    now="$(timestamp)"
    fm_set "$f" status "$to"
    fm_set "$f" updated "$now"
    append_comment "$f" "$now" "transition-reason" "$actor" "Transition: $from -> $to. Reason: $reason"
    echo "$id: $from -> $to"
}

cmd_link() {
    local id="$1" other="$2" ltype="$3"
    require_ticket "$id"
    case "$ltype" in
        parent-child|depends-on|relates) require_ticket "$other" ;;
        origin-review|pr) ;;  # may reference reviews/PRs outside the ticket store
        *) die "link: invalid link type '$ltype' (parent-child|depends-on|origin-review|pr|relates)" ;;
    esac

    local f entry links
    f="$(ticket_file "$id")"
    entry="$ltype:$other"
    links="$(fm_get "$f" links)"
    case "$links" in
        *"$entry"*) echo "$id: already linked $entry"; return 0 ;;
        ''|'[]') links="[$entry]" ;;
        *) links="${links%]}, $entry]" ;;
    esac
    fm_set "$f" links "$links"

    if [ "$ltype" = "depends-on" ]; then
        local deps
        deps="$(fm_get "$f" depends_on)"
        case "$deps" in
            *"$other"*) ;;
            ''|'[]') fm_set "$f" depends_on "[$other]" ;;
            *) fm_set "$f" depends_on "${deps%]}, $other]" ;;
        esac
    fi

    fm_set "$f" updated "$(timestamp)"
    echo "$id: linked $entry"
}

cmd_children() {
    local epic="$1"
    require_ticket "$epic"
    local f id status title found=0
    for f in "$TICKETS_DIR"/*.md; do
        [ -e "$f" ] || continue
        [ "$(fm_get "$f" parent)" = "$epic" ] || continue
        id="$(fm_get "$f" id)"
        status="$(fm_get "$f" status)"
        title="$(fm_get "$f" title)"
        printf '%s\t[%s]\t%s\n' "$id" "$status" "$title"
        found=1
    done
    [ "$found" -eq 1 ] || echo "(no children)" >&2
}

# cmd_parent <id> — print the ticket's parent-epic id (empty line when none).
# Thin projection of get_ticket consumed by the orchestrator's intake classifier
# (ABS-104); keeps the classifier on the adapter surface (ADR-A-0007).
cmd_parent() {
    require_ticket "$1"
    fm_get "$(ticket_file "$1")" parent
}

# cmd_child_count <id> — print the number of tickets whose parent is <id>.
# Thin projection of get_epic_children (a count, not a listing) consumed by the
# intake classifier (ABS-104).
cmd_child_count() {
    require_ticket "$1"
    local f count=0
    for f in "$TICKETS_DIR"/*.md; do
        [ -e "$f" ] || continue
        [ "$(fm_get "$f" parent)" = "$1" ] && count=$((count + 1))
    done
    echo "$count"
}

cmd_events() {
    mkdir -p "$TICKETS_DIR"
    local now current f
    now="$(timestamp)"
    current="$EVENTS_STATE.current.$$"
    : > "$current"
    for f in "$TICKETS_DIR"/*.md; do
        [ -e "$f" ] || continue
        printf '%s\t%s\n' "$(fm_get "$f" id)" "$(fm_get "$f" status)" >> "$current"
    done

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
    else
        # First poll: every ticket surfaces as a creation event.
        awk -F'\t' -v at="$now" '
            { printf "{ticket_id: %s, from: null, to: %s, at: %s}\n", $1, $2, at }
        ' "$current"
    fi
    mv "$current" "$EVENTS_STATE"
}

# cmd_assign <id> <accountId> — set the assignee frontmatter field. (ABS-126)
# On first set, inserts the field before depends_on: (same insert-before pattern
# as flags/labels/ac_blocking in cmd_update). On subsequent calls, fm_set rewrites
# it in place. accountIds must arrive via env/config — never hardcoded (ADR-A-0010).
cmd_assign() {
    local id="$1" account_id="$2"
    require_ticket "$id"
    local f
    f="$(ticket_file "$id")"
    # Insert assignee: before depends_on: on first set; rewrite thereafter.
    if ! grep -q "^assignee:" "$f"; then
        local tmp="$f.tmp.$$"
        awk -v value="$account_id" '
            NR == 1 && $0 == "---" { fm = 1; print; next }
            fm == 1 && index($0, "depends_on:") == 1 {
                print "assignee: " value; print; fm = 2; next
            }
            fm == 1 && $0 == "---" {
                print "assignee: " value; print; fm = 2; next
            }
            { print }
        ' "$f" > "$tmp" && mv "$tmp" "$f"
    else
        fm_set "$f" assignee "$account_id"
    fi
    fm_set "$f" updated "$(timestamp)"
    echo "$id: assignee set to $account_id"
}

# --- Dispatcher ----------------------------------------------------------------

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
