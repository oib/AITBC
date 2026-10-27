#!/bin/sh
# hold-check.sh — exit 1 if <host> is named in an active hold that covers
# restarts/pulls/deploys in the workspace holds file.
#
# The holds file is a markdown doc whose "## Binding now" section is a
# table of `| hold | scope | until | source |` rows. This check is a
# mechanical gate: any binding-table row that names the host AND mentions
# restart/pull/deploy in its scope blocks the action. It is deliberately
# conservative — a row whose hold has lapsed but is still listed still
# fails the check; remove the row (or wait for the editor) to clear it.
#
# Usage: hold-check.sh <host> [holds-file]
# Env:   HOLDS_FILE — holds file path when the argument is omitted
#        (default: tasks/HOLDS.md relative to the current directory).
#
# Exit: 0 = no blocking hold, 1 = hold active, 2 = holds file unreadable
# (a missing file is a failed check, never a silent pass).

set -euo pipefail

host="${1:?usage: hold-check.sh <host> [holds-file]}"
file="${2:-${HOLDS_FILE:-tasks/HOLDS.md}}"

[ -r "$file" ] || { echo "hold-check: cannot read holds file: $file" >&2; exit 2; }

if awk -v host="$host" '
  /^## Binding now/  { inb=1; next }
  /^## /             { if (inb) exit }
  inb && /^\|/ {
    # host must appear as a whole word (hub must not match hub1)
    if ($0 ~ "(^|[^A-Za-z0-9])" host "([^A-Za-z0-9]|$)" &&
        $0 ~ /restart|pull|deploy/) {
      print "hold-check: HOLD ACTIVE — " $0 > "/dev/stderr"; found=1
    }
  }
  END { exit (found ? 1 : 0) }
' "$file"; then
  echo "hold-check: no blocking hold for $host"
else
  exit 1
fi
