#!/bin/bash
# Fail if the committed OpenAPI specs differ from what the applications produce.
#
# The guard itself is not new -- `make openapi-check` has existed since v0.22 and works.
# Nothing invoked it, so it only ever reported when someone thought to ask, and it was red on
# main for most of v0.23: agent-coordinator was missing a route, blockchain-node was missing a
# route, and coordinator-api's money fields still published as `"type": "number"` after the
# Decimal work, so a generated client would have parsed a decimal string as a float. This
# script is the same check with two changes that let it be wired to a hook (V23-82).
#
#   1. It does not write into the working tree. The old target ran `make openapi` and then
#      `git diff`, so *asking* whether the specs were current rewrote them -- fine by hand,
#      hostile in a hook, where pre-commit stashes unstaged changes and a hook that modifies
#      files can collide with the restore. Generation goes to a temporary directory instead.
#
#   2. It compares only the generated files, and it learns which those are from the generator
#      rather than repeating the list. docs/api/ also holds hand-written markdown and two
#      subdirectories, which a recursive diff of the whole directory would report as
#      differences -- and a list written out here would be one more thing that could fall
#      quietly out of step with the apps, which is the bug being fixed.
#
# The extractor's own exit code matters as much as the diff: it used to print "✗ Failed" for
# an app that would not import and exit 0 anyway, leaving that app's stale spec on disk for
# the diff to compare against itself. It now exits non-zero, and that is checked below.

set -euo pipefail

cd "$(dirname "$0")/../.."

# Same resolution as the Makefile: prefer the repo's venv, fall back to whatever is on PATH so
# this still works from a git worktree, which has no venv/ of its own.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x ./venv/bin/python ]; then PYTHON=./venv/bin/python; else PYTHON=python3; fi
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# The apps are chatty on the way up -- missing zk verification keys, a duplicate operation id
# -- and none of it is this check's business. Held back unless generation actually fails,
# where it is the only thing that explains why.
if ! "$PYTHON" scripts/extract_openapi_specs.py --output-dir "$tmp" >/dev/null 2>"$tmp/.stderr"; then
  echo "Could not generate the specs, so drift could not be checked:" >&2
  cat "$tmp/.stderr" >&2
  exit 1
fi

specs=()
while IFS= read -r path; do
  specs+=("$(basename "$path")")
done < <(find "$tmp" -maxdepth 1 -name '*-openapi.json' | sort)

if [ ${#specs[@]} -eq 0 ]; then
  echo "The extractor succeeded but produced no specs, so nothing was compared." >&2
  exit 1
fi

drifted=()
for spec in "${specs[@]}"; do
  if ! diff -q "docs/api/$spec" "$tmp/$spec" >/dev/null 2>&1; then
    drifted+=("$spec")
  fi
done

if [ ${#drifted[@]} -eq 0 ]; then
  echo "✅ OpenAPI: docs/api/ matches the applications (${#specs[@]} specs)"
  exit 0
fi

echo ""
echo "docs/api/ is out of date with the applications:"
for spec in "${drifted[@]}"; do
  if [ ! -f "docs/api/$spec" ]; then
    # A new app was added to the extractor and its spec has never been committed.
    echo "  $spec  (not committed at all)"
    continue
  fi
  # Counted in the direction `make openapi` would move the committed file.
  added=$(diff "docs/api/$spec" "$tmp/$spec" | grep -c '^>' || true)
  removed=$(diff "docs/api/$spec" "$tmp/$spec" | grep -c '^<' || true)
  echo "  $spec  ($added lines to add, $removed to remove)"
done
echo ""
echo "These files are generated, not written. Regenerate and commit the result:"
echo "    make openapi"
echo ""
echo "If the change was not intended, the app changed a published contract -- check that"
echo "before committing, because clients are generated from these files."
exit 1
