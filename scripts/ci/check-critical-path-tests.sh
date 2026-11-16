#!/bin/bash
# Critical-path test-coverage ratchet (#1860).
#
# Same "manifest + floor" shape as the c901/except ratchets, applied to test
# coverage of the money-and-consensus critical path: for every module listed
# in scripts/ci/critical-paths.txt the check counts how many test files under
# apps/*/tests and tests/ reference the module basename (for a package-dir
# row, the basenames of its direct .py children) and fails when the count
# drops below the recorded floor — or when the module path itself is gone,
# which is the deletion case a pure count cannot see.
#
# Matching is a plain substring grep for the basename: `pbft` also matches
# `pbft_view_change`, `escrow` matches `protocol_escrow`. That is deliberate —
# the floor is the observed count, so the gate only prevents erosion of
# existing coverage, never demands a particular import style. After a
# deliberate coverage improvement, regenerate the floors:
#
#   scripts/ci/check-critical-path-tests.sh --update
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
MANIFEST="scripts/ci/critical-paths.txt"

if [ ! -f "$MANIFEST" ]; then
    echo "critical-path ratchet: manifest missing: $MANIFEST" >&2
    exit 1
fi

# Test dirs per the manifest header: every apps/<app>/tests plus the
# repo-level tests/ tree. nullglob keeps an app without tests/ from
# contributing the literal pattern.
shopt -s nullglob
TEST_DIRS=(apps/*/tests tests)
shopt -u nullglob
if [ "${#TEST_DIRS[@]}" -eq 0 ]; then
    echo "critical-path ratchet: no test dirs found (apps/*/tests, tests/) — refusing to score an empty scan as green" >&2
    exit 1
fi

# Search tokens for one manifest path: a .py file contributes its stem; a
# directory contributes the stems of its direct .py children (__init__
# excluded — it names the package, not a module under test).
tokens_for() {
    local path="$1" f base
    if [ -d "$path" ]; then
        for f in "$path"/*.py; do
            [ -e "$f" ] || continue
            base="$(basename "$f" .py)"
            [ "$base" = "__init__" ] && continue
            printf '%s\n' "$base"
        done
    else
        basename "$path" .py
    fi
}

# Count distinct test files referencing any of the given tokens.
count_refs() {
    local pattern_file="$1"; shift
    # -F fixed strings, one per line via -f; --include keeps the scan to
    # Python sources so a token in a fixture or doc cannot inflate the count.
    grep -rlF --include='*.py' -f "$pattern_file" "${TEST_DIRS[@]}" 2>/dev/null | sort -u | wc -l
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

status=0
updated="$(mktemp)"
trap 'rm -rf "$tmpdir"; rm -f "$updated"' EXIT

while IFS=$'\t' read -r path floor _rest; do
    # Skip blank lines and comments; a malformed row (no tab/floor) is a
    # manifest bug, not a coverage result.
    case "$path" in ''|\#*) continue ;; esac
    if [ -z "${floor:-}" ] || ! [[ "$floor" =~ ^[0-9]+$ ]]; then
        echo "critical-path ratchet: malformed manifest row (need <path><TAB><int>): $path" >&2
        status=1
        continue
    fi
    if [ ! -e "$path" ]; then
        echo "critical-path coverage regression: $path has no module on disk (floor: $floor) — deleted or moved?"
        status=1
        continue
    fi
    : > "$tmpdir/patterns"
    tokens_for "$path" > "$tmpdir/tokens"
    if [ ! -s "$tmpdir/tokens" ]; then
        echo "critical-path ratchet: $path yields no search tokens" >&2
        status=1
        continue
    fi
    # grep -f treats every line as a pattern; drop empties defensively.
    grep -v '^$' "$tmpdir/tokens" > "$tmpdir/patterns" || true
    count="$(count_refs "$tmpdir/patterns")"
    if [ "${1:-}" = "--update" ]; then
        printf '%s\t%s\n' "$path" "$count" >> "$updated"
        continue
    fi
    if [ "$count" -lt "$floor" ]; then
        echo "critical-path coverage regression: $path has $count referencing test files (floor: $floor)"
        status=1
    elif [ "$count" -gt "$floor" ]; then
        echo "critical-path coverage improvement: $path has $count referencing test files (floor: $floor) — run $0 --update"
    fi
done < "$MANIFEST"

if [ "${1:-}" = "--update" ]; then
    # Rewrite only the data rows, preserving order; every comment/blank line
    # before the first data row is kept as the header.
    awk 'BEGIN{p=1} /^#/{if(p)print; next} /^[[:space:]]*$/{if(p)print; next} {p=0}' "$MANIFEST" > "$tmpdir/header"
    cat "$tmpdir/header" "$updated" > "$MANIFEST"
    echo "critical-path manifest updated: $(wc -l < "$updated") rows"
    exit 0
fi

if [ "$status" -eq 0 ]; then
    echo "critical-path ratchet: all modules at or above floor ($(grep -cvE '^\s*(#|$)' "$MANIFEST") modules)"
else
    cat >&2 <<'EOF'

A critical-path module lost test coverage or was deleted/renamed. Restore
the referencing tests, or if the module genuinely moved, update
scripts/ci/critical-paths.txt to the new path and re-run with --update.
Do NOT raise a floor to hide lost coverage:

    scripts/ci/check-critical-path-tests.sh --update
EOF
fi
exit "$status"
