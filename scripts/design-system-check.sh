#!/usr/bin/env bash
#
# design-system-check.sh — concrete backing for the design-system adapter's
# check(change_ref) operation and the `design-system-check` quality gate.
#
# Implements ADR-A-0017 (design-quality detector as backing for the
# design-system-check gate). The backing engine is the vendored, version-pinned
# `impeccable` detector (Apache-2.0, see vendor/impeccable/). No LLM/API call;
# deterministic; runs in the Bash-only headless lane.
#
# Consumed by the qas-design seat, which runs this script over the RENDERED UI
# and posts the per-rule PASS/FAIL evidence through $TRACKER_CMD. It AUGMENTS the
# designer's hand-authored DACs — it never replaces them, and a green detector run
# does not make a DAC-failing design pass (designer→tester separation intact).
#
# Usage:
#   scripts/design-system-check.sh <target> [-- <extra impeccable detect args>]
#
#   <target>  A RENDERED HTML file, a directory of rendered HTML, or a live URL.
#             Feed rendered output (e.g. the Playwright-rendered DOM), NOT raw
#             .tsx/.jsx — the high-value DOM rules (contrast, gray-on-color,
#             palette, fonts) fire on rendered output (ADR-A-0017 / ABS-191 §7.1).
#             (Live-URL scanning needs Puppeteer, an optionalDependency omitted
#             from the vendored payload; prefer rendered-HTML input.)
#
# Profile gate (ADR-A-0017 constraint 3):
#   Runs ONLY when the design system is enabled. Enablement is signalled by the
#   environment variable DESIGN_SYSTEM_ENABLED=true (set by a profile whose
#   design-system provider is not `none`). When unset/false the gate is INERT:
#   it exits 0 and executes no detector — the neutral/backend profiles pull
#   nothing.
#
# Waivers (ADR-A-0017 constraint 4):
#   Project waivers live in .impeccable/config.json (shared) and
#   .impeccable/config.local.json (local, gitignored). Use detector.ignoreRules
#   to fence the content/text rule class (e.g. marketing-buzzword) so it cannot
#   false-positive on legitimate prose; DOM rules stay accurate. Pass
#   `-- --scope type,layout` to restrict to design-domain rules.
#
# Evidence lane (ADR-A-0017 constraint 5):
#   Exit code 0 = clean (gate PASS); 2 = findings (gate FAIL). The detector's
#   JSON is grouped per rule (jq group_by(.antipattern)). This script prints a
#   Markdown evidence block on stdout for the caller to post via
#   `$TRACKER_CMD comment --kind gate-results`. The script's own exit code is the
#   gate boolean (0 pass / 2 fail / 1 usage-or-environment error).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/vendor/impeccable"
CLI="$VENDOR_DIR/node_modules/impeccable/cli/bin/cli.js"

# --- Profile gate: inert unless the design system is enabled ------------------
if [ "${DESIGN_SYSTEM_ENABLED:-false}" != "true" ]; then
    echo "design-system-check: SKIPPED — design system not enabled (DESIGN_SYSTEM_ENABLED != true). Gate inert." >&2
    exit 0
fi

# --- Args ---------------------------------------------------------------------
if [ "$#" -lt 1 ]; then
    echo "ERROR: usage: design-system-check.sh <target> [-- <extra detect args>]" >&2
    exit 1
fi
TARGET="$1"; shift
EXTRA_ARGS=()
if [ "${1:-}" = "--" ]; then
    shift
    EXTRA_ARGS=("$@")
fi

# --- Ensure the pinned detector payload is present (pinned, non-floating) -----
# node_modules/ is gitignored repo-wide; the vendored payload is pinned by
# vendor/impeccable/package-lock.json (integrity-hashed). `npm ci --omit=optional`
# is a PINNED fetch — never a floating/unpinned npx. Behavior is fully determined
# by the committed lockfile (ADR-A-0013 / ADR-A-0017 constraint 2).
if [ ! -f "$CLI" ]; then
    command -v npm >/dev/null 2>&1 || { echo "ERROR: npm not found; cannot materialize the pinned detector." >&2; exit 1; }
    echo "design-system-check: materializing pinned detector (npm ci --omit=optional)…" >&2
    ( cd "$VENDOR_DIR" && npm ci --omit=optional --no-audit --no-fund >/dev/null 2>&1 )
fi
[ -f "$CLI" ] || { echo "ERROR: detector CLI missing at $CLI after install." >&2; exit 1; }

# --- Run the detector ---------------------------------------------------------
JSON="$(mktemp)"; ERRLOG="$(mktemp)"; trap 'rm -f "$JSON" "$ERRLOG"' EXIT
set +e
node "$CLI" detect --json "$TARGET" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} >"$JSON" 2>"$ERRLOG"
DETECT_EXIT=$?
set -e

# The detector uses exit 0 = clean, 2 = findings. Anything else is a real error.
if [ "$DETECT_EXIT" != "0" ] && [ "$DETECT_EXIT" != "2" ]; then
    echo "ERROR: detector exited $DETECT_EXIT (not 0/2)." >&2
    cat "$ERRLOG" >&2 || true
    cat "$JSON" >&2 || true
    exit 1
fi

# --- Evidence block (Markdown on stdout) --------------------------------------
DETECTOR_VERSION="$(node -e "console.log(require('$VENDOR_DIR/node_modules/impeccable/package.json').version)" 2>/dev/null || echo unknown)"
TOTAL="$(jq 'length' "$JSON")"

echo "## design-system-check (impeccable@${DETECTOR_VERSION}) — detector evidence"
echo
echo "- **Target:** \`${TARGET}\`"
echo "- **Detector exit code:** ${DETECT_EXIT} ($([ "$DETECT_EXIT" = "0" ] && echo 'clean' || echo 'findings'))"
echo "- **Gate verdict:** $([ "$DETECT_EXIT" = "0" ] && echo 'PASS' || echo 'FAIL')"
echo "- **Total findings:** ${TOTAL}"
echo
echo "### Per-rule results"
echo
if [ "$TOTAL" = "0" ]; then
    echo "_No anti-pattern findings. All detector rules PASS._"
else
    echo "| Rule | Verdict | Count | Example |"
    echo "| ---- | ------- | ----- | ------- |"
    jq -r 'group_by(.antipattern)[]
           | "| \(.[0].antipattern) | FAIL | \(length) | \(.[0].snippet // .[0].name | tostring | gsub("\\|";"/")) |"' "$JSON"
fi
echo
echo "> Detector evidence AUGMENTS the hand-authored DACs; it does not replace them."
echo "> The designer authors DACs; qas-design executes them (ADR-A-0017)."

# --- Gate boolean = script exit code ------------------------------------------
exit "$DETECT_EXIT"
