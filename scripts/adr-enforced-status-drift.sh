#!/bin/bash
# =============================================================================
# ADR Enforcement-Status Drift Detector — reverse direction [PILOT-52 / ABS-561]
# =============================================================================
#
# scripts/adr-acceptance-drift.sh guards ONE direction: an ADR marked accepted
# in the record whose FILE frontmatter is still `proposed`. The real, opposite
# drift class has no sensor: an ADR whose MECHANIC is already enforced by
# code/sensors — it is shipped, load-bearing, default-on — yet whose file still
# says `status: proposed` because nobody flipped it. ADR-A-0021 (the whole
# operation's backend substrate) sits `proposed` while the ACCEPTED ADR-A-0026
# normatively builds on it; the authority order of ADR-A-0001 becomes
# unevaluable.
#
# This detector reads the machine-readable rule ledger (docs/rule-ledger.yaml,
# ADR-A-0028). A ledger row of `kind: enforced` or `kind: derived` names at
# least one deterministic sensor (ADR-A-0028 §2) — so when such a row's heading
# NAMES an ADR (`ADR-A-NNNN`), that ADR's mechanic is demonstrably enforced by
# code. If that ADR's FILE frontmatter is still `proposed`, that is the
# reverse-direction drift.
#
# HONEST SEMANTICS: the detector treats an enforced/derived ledger row that
# NAMES an ADR as evidence that the ADR's mechanic is enforced. It reports the
# named enforcing row + sensors as the Belegstelle. It never proves the sensor
# is wired to that exact ADR (that is the sensor's own test's job), and — per
# ADR-A-0004 — it REPORTS ONLY: flipping an ADR to `accepted` stays a human act.
# This script never edits an ADR status.
#
# Modes:
#   (default / gate)  one `DRIFT:` line per offending ADR to stdout.
#                     Exit 0 = no drift; 1 = drift found. ADVISORY — do NOT wire
#                     as a blocking CI gate: the live tree is EXPECTED to carry
#                     drift until a human works the flip-list (ADR-A-0004).
#   --flip-list       operator decision vehicle (ADR-A-0004): one line per
#                     drifting ADR with its enforcement Belegstelle, ready to
#                     paste into a flip decision. Same exit semantics.
#
# Usage:
#   scripts/adr-enforced-status-drift.sh [--flip-list] [adrs_dir] [ledger_file]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="gate"
POS=()
for arg in "$@"; do
    case "$arg" in
        --flip-list) MODE="flip-list" ;;
        *) POS+=("$arg") ;;
    esac
done
ADRS_DIR="${POS[0]:-$ROOT/adrs}"
LEDGER="${POS[1]:-$ROOT/docs/rule-ledger.yaml}"

# Resolve an ADR id -> file path (by frontmatter `id:`, not filename). Portable
# (bash 3.2, no associative arrays). Empty if the id has no file in the tree.
adr_file() {
    grep -rlE "^id:[[:space:]]*$1[[:space:]]*$" "$ADRS_DIR" 2>/dev/null \
        --include='ADR-*.md' | head -1
}
# Read an ADR file's `status:` (strip inline comment + whitespace).
adr_status() {
    grep -m1 '^status:' "$1" 2>/dev/null \
        | sed -E 's/^status:[[:space:]]*//; s/[[:space:]]*#.*$//; s/[[:space:]]*$//'
}

# --- Collect enforced/derived ledger rows and the ADRs they name. -----------
# awk emits, for every enforced|derived row whose heading names an ADR-A-NNNN,
# one `ADRID<TAB>ROWID<TAB>SENSORS` line (one per named ADR).
drift=0
while IFS=$'\t' read -r adrid rowid sensors; do
    [ -n "$adrid" ] || continue
    file="$(adr_file "$adrid")"
    [ -n "$file" ] || continue          # id named in ledger but no ADR file: skip
    status="$(adr_status "$file")"
    # Only proposed ADRs drift; accepted/other statuses skip.
    [ "$status" = "proposed" ] || continue
    drift=$((drift + 1))
    if [ "$MODE" = "flip-list" ]; then
        printf '%-12s | proposed -> accepted? | enforced by %s [%s] | HUMAN-ONLY flip (ADR-A-0004)\n' \
            "$adrid" "$rowid" "$sensors"
    else
        echo "DRIFT: ${adrid} status:proposed but its mechanic is enforced — ledger ${rowid} [sensors: ${sensors}] (${file})"
    fi
done < <(awk '
    /^  - id: R-/       { flush(); id=$3; kind=""; heading=""; sensors="" }
    /^    kind:/         { kind=$2 }
    /^    heading:/      { heading=$0; sub(/^    heading:[[:space:]]*/,"",heading) }
    /^    sensors:/      { sensors=$0; sub(/^    sensors:[[:space:]]*/,"",sensors)
                           gsub(/^\[|\]$/,"",sensors) }
    END { flush() }
    function flush(   tok,seen) {
        if (kind != "enforced" && kind != "derived") return
        # extract every ADR-A-NNNN token from the heading (dedup within the row)
        while (match(heading, /ADR-A-[0-9]+/)) {
            tok = substr(heading, RSTART, RLENGTH)
            heading = substr(heading, RSTART + RLENGTH)
            if (!(tok in seen)) { seen[tok]=1; print tok "\t" id "\t" sensors }
        }
    }
' "$LEDGER")

if [ "$drift" -gt 0 ]; then
    if [ "$MODE" = "gate" ]; then
        echo "adr-enforced-status-drift: ${drift} ADR(s) enforced by code/sensors but still 'proposed' in file frontmatter."
        echo "Review the flip-list (scripts/adr-enforced-status-drift.sh --flip-list) and, per ADR-A-0004, a HUMAN flips status + accepted_by + accepted_date."
    fi
    exit 1
fi

exit 0
