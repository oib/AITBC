#!/usr/bin/env bash
# next-migration-number.sh — reserve the next free migration NNN prefix (ABS-449).
#
# WHY (follow-up to ABS-428 runtime guard): parallel seats each pick "the next
# number" off their own branch and collide (008 twice on 17./18.07., 010 twice —
# same filename 010_command_reason.sql — in MR !94). ABS-428 catches the dup at
# *run/merge* time, after the add/add conflict and re-sync cost is already paid.
# This helper moves the decision to *assignment* time: it returns the next free
# number as the union of what is already taken across the refs the caller names.
#
# The set scanned = the base ref (origin/main, else main, else HEAD) + the
# working tree + every --target ref you pass + (with --remotes) already-fetched
# remote epic/ABS heads. Pass the Ziel-Epic-Branch and any open MR branch you
# know about as --target so their reserved numbers count too. git ls-tree based,
# no network unless you fetched the refs; bash 3.2 / BSD safe.
#
# Usage:
#   scripts/next-migration-number.sh                       # next free after main + worktree
#   scripts/next-migration-number.sh --target epic/ABS-000-integration
#   scripts/next-migration-number.sh --target A --target B --remotes
#   scripts/next-migration-number.sh --dir path/to/migrations
#
# Prints the zero-padded NNN (e.g. 011) on stdout. CLI errors exit 64.
set -uo pipefail

DEFAULT_DIR="backend/packages/core/src/migrations"

die() { echo "next-migration-number: $*" >&2; exit 64; }

DIR="$DEFAULT_DIR"
REFS=()
SCAN_REMOTES=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --target) shift; [ -n "${1:-}" ] || die "--target needs a ref"; REFS+=("$1") ;;
        --target=*) REFS+=("${1#*=}") ;;
        --dir) shift; [ -n "${1:-}" ] || die "--dir needs a path"; DIR="$1" ;;
        --dir=*) DIR="${1#*=}" ;;
        --remotes) SCAN_REMOTES=1 ;;
        -h|--help|help) sed -n '2,29p' "$0"; exit 0 ;;
        *) die "unknown arg '$1'" ;;
    esac
    shift
done

git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

# Base ref: first of origin/main, main, HEAD that resolves.
base_ref=""
for r in origin/main main HEAD; do
    if git rev-parse --verify -q "$r^{commit}" >/dev/null 2>&1; then base_ref="$r"; break; fi
done

# Already-fetched remote epic/ABS heads (zero network). Refnames have no spaces.
if [ "$SCAN_REMOTES" = 1 ]; then
    for rr in $(git for-each-ref --format='%(refname)' \
        'refs/remotes/*/epic/*' 'refs/remotes/*/ABS-*' 2>/dev/null); do
        REFS+=("$rr")
    done
fi

# NNN prefixes of the migration .sql files reachable from a git ref.
prefixes_of_ref() {
    git ls-tree -r --name-only "$1" -- "$DIR" 2>/dev/null \
        | sed -n 's#.*/\([0-9][0-9]*\)_.*\.sql$#\1#p'
}

# NNN prefixes of the migration .sql files sitting in the working tree (covers a
# file added locally but not yet committed).
prefixes_of_worktree() {
    ls "$DIR" 2>/dev/null | sed -n 's#^\([0-9][0-9]*\)_.*\.sql$#\1#p'
}

all_prefixes="$(
    { [ -n "$base_ref" ] && prefixes_of_ref "$base_ref"
      for r in "${REFS[@]:-}"; do [ -n "$r" ] && prefixes_of_ref "$r"; done
      prefixes_of_worktree
    } 2>/dev/null
)"

max=0
while IFS= read -r p; do
    [ -n "$p" ] || continue
    n=$((10#$p))                       # 10# => never parse "008" as octal
    [ "$n" -gt "$max" ] && max=$n
done <<EOF
$all_prefixes
EOF

printf '%03d\n' "$((max + 1))"
