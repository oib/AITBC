#!/bin/bash
# =============================================================================
# ORCH_* Knob Documentation Drift Guard (ABS-517 / epic ABS-514)
# =============================================================================
# Reverse direction of scripts/docs-identifier-check.sh:
#   docs-identifier-check:  doc cites ORCH_X  -> ORCH_X must exist in code
#   THIS guard:             code reads ORCH_X -> ORCH_X must be documented in
#                           the ORCHESTRATOR_SOP knob surface
#
# Rationale (rule ledger R-row "Environment Knobs"): the SOP knob table is the
# operator's control-surface contract. A knob added in scripts/ but absent from
# the SOP is invisible to the operator — the exact drift class the
# ABS-514 review named for the instruction surface, in the code->doc direction.
#
# Mechanics: every `${ORCH_...}` read in scripts/*.sh and scripts/hooks/*.sh
# must appear (word match) somewhere in docs/sop/ORCHESTRATOR_SOP.md. The SOP
# as a whole — not only the knob table — counts as documented: several knobs
# are described in their feature sections instead of the table, which is fine;
# what matters is that the operator can find them.
#
# Fixture overrides (regression tests): KNOB_SCRIPTS_GLOB_DIR (dir whose *.sh
# and hooks/*.sh are scanned), KNOB_SOP_FILE (SOP path).
# Exit 0 = every knob documented. Exit 1 = drift (list on stderr).
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SCRIPTS_DIR="${KNOB_SCRIPTS_GLOB_DIR:-$REPO_ROOT/scripts}"
SOP="${KNOB_SOP_FILE:-$REPO_ROOT/docs/sop/ORCHESTRATOR_SOP.md}"

[ -d "$SCRIPTS_DIR" ] || { printf 'orch-knob-doc-drift: missing scripts dir: %s\n' "$SCRIPTS_DIR" >&2; exit 2; }
[ -f "$SOP" ]         || { printf 'orch-knob-doc-drift: missing SOP: %s\n' "$SOP" >&2; exit 2; }

fail=0
missing=""
while IFS= read -r knob; do
    [ -n "$knob" ] || continue
    grep -qw -- "$knob" "$SOP" && continue
    printf 'KNOB-DRIFT: %s is read in scripts/ but not documented in %s\n' "$knob" "${SOP##*/}" >&2
    missing="$missing $knob"
    fail=1
done < <(grep -ohE '\$\{ORCH_[A-Z0-9_]+' "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/hooks/*.sh 2>/dev/null \
             | sed 's/^\${//' | sort -u)

if [ "$fail" -ne 0 ]; then
    printf '\norch-knob-doc-drift: FAIL — undocumented operator knob(s):%s\n' "$missing" >&2
    printf 'fix: add the knob(s) to the Environment Knobs table (or feature section) in the SOP.\n' >&2
    exit 1
fi
printf 'orch-knob-doc-drift: OK — every ORCH_* knob read in scripts/ is documented in the SOP.\n'
exit 0
