#!/usr/bin/env bash
# migration-number-collision-check.sh — pre-merge migration-number collision gate (ABS-449).
#
# WHY (same family as the ABS-397/398 rebase-gate): the ABS-428 test only sees a
# duplicate prefix once BOTH files sit on one tree — i.e. after the merge/add-add
# conflict. A story branch on its own (forked off an older tip) carries only ITS
# migration file, so the dup is invisible until it lands. This check compares the
# branch against the ref it will merge into and fails BEFORE the merge if both
# sides independently added the same migration number.
#
# THE primitive (merge-base, like rebase-gate-check.sh): a number that appears on
# BOTH sides *relative to the merge-base* was picked twice in parallel. Files that
# were already on the common base are not a collision — they are shared history.
#
#   migration-number-collision-check.sh <target-ref> [<branch-ref=HEAD>] [--dir P]
#       0  OK      — no number added on both sides
#       1  COLLISION — a number was added on both sides (message names the number
#                     and the colliding files on stderr)
#      64  usage / bad ref (fails closed — never a false OK)
set -uo pipefail

DEFAULT_DIR="backend/packages/core/src/migrations"

die() { echo "migration-number-collision-check: $*" >&2; exit 64; }

DIR="$DEFAULT_DIR"
POS=()
[ "$#" -gt 0 ] || { sed -n '2,25p' "$0"; exit 0; }
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dir) shift; [ -n "${1:-}" ] || die "--dir needs a path"; DIR="$1" ;;
        --dir=*) DIR="${1#*=}" ;;
        -h|--help|help) sed -n '2,25p' "$0"; exit 0 ;;
        -*) die "unknown flag '$1'" ;;
        *) POS+=("$1") ;;
    esac
    shift
done

target="${POS[0]:-}"
branch="${POS[1]:-HEAD}"
[ -n "$target" ] || die "need <target-ref> [<branch-ref>]"

git rev-parse --verify -q "$target^{commit}" >/dev/null 2>&1 || die "unknown target ref '$target'"
git rev-parse --verify -q "$branch^{commit}" >/dev/null 2>&1 || die "unknown branch ref '$branch'"
base="$(git merge-base "$target" "$branch" 2>/dev/null)" || die "no merge-base between '$target' and '$branch'"
[ -n "$base" ] || die "no merge-base between '$target' and '$branch'"

tmp="$(mktemp -d "${TMPDIR:-/tmp}/mig-collide-XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# Basenames of migration .sql files reachable from a ref, restricted to DIR.
files_of() { git ls-tree -r --name-only "$1" -- "$DIR" 2>/dev/null | sed -n 's#.*/##p'; }

files_of "$base"   | sort -u > "$tmp/base"
files_of "$branch" | sort -u > "$tmp/branch"
files_of "$target" | sort -u > "$tmp/target"

# comm -13 A B => lines only in B (added on that side vs the common base).
comm -13 "$tmp/base" "$tmp/branch" > "$tmp/branch_added"
comm -13 "$tmp/base" "$tmp/target" > "$tmp/target_added"

collision=0
while IFS= read -r bf; do
    [ -n "$bf" ] || continue
    bp="$(printf '%s\n' "$bf" | sed -n 's#^\([0-9][0-9]*\)_.*\.sql$#\1#p')"
    [ -n "$bp" ] || continue
    tf="$(sed -n "s#^\\(${bp}_.*\\.sql\\)\$#\\1#p" "$tmp/target_added" | head -1)"
    if [ -n "$tf" ]; then
        echo "COLLISION: migration number ${bp} was added on both sides —" >&2
        echo "  branch '$branch' adds:  $bf" >&2
        echo "  target '$target' adds:  $tf" >&2
        echo "  Renumber the branch file to the next free number, then rebase:" >&2
        echo "    scripts/next-migration-number.sh --target $target" >&2
        collision=1
    fi
done < "$tmp/branch_added"

if [ "$collision" = 0 ]; then
    echo "OK: no migration-number collision between '$branch' and '$target'"
    exit 0
fi
exit 1
