#!/bin/bash
# append-changelog.sh <changelog-file> — append a release entry read from stdin.
#
# Changelog entries get appended over ssh often enough that heredoc-in-ssh
# quoting damage has written half-formed duplicates twice already. Reading the
# entry on stdin removes the quoting surface entirely, and refusing when the
# entry's "### " header already exists in the file makes a re-appended entry
# impossible — it is always a mistake.
#
# Usage:
#   scripts/release/append-changelog.sh docs/releases/v0.25/v0.25.2_change.log < entry.txt
#   cat entry.txt | ssh node2 'cd /opt/aitbc && scripts/release/append-changelog.sh docs/releases/v0.25/v0.25.2_change.log'

set -euo pipefail

file="${1:?usage: append-changelog.sh <changelog-file> < entry}"

[ -f "$file" ] || { echo "append-changelog: no such file: $file" >&2; exit 1; }
[ -w "$file" ] || { echo "append-changelog: not writable: $file" >&2; exit 1; }

entry="$(cat)"
[ -n "$entry" ] || { echo "append-changelog: empty entry on stdin" >&2; exit 1; }

header=$(printf '%s\n' "$entry" | grep -m1 '^### ' || true)
[ -n "$header" ] || { echo "append-changelog: entry has no '### <title>' header line" >&2; exit 1; }

if grep -qxF -- "$header" "$file"; then
    echo "append-changelog: refusing — this header already exists in $file:" >&2
    echo "  $header" >&2
    exit 1
fi

# One blank line between sections.
[ -n "$(tail -c1 "$file")" ] && printf '\n' >> "$file"
[ -z "$(tail -n1 "$file")" ] || printf '\n' >> "$file"

printf '%s\n' "$entry" >> "$file"
echo "appended: $header" >&2
