#!/bin/bash
# =============================================================================
# ADR Acceptance-Closeout Drift Detector [ABS-212]
# =============================================================================
#
# A human accepting an ADR (human-only, ADR-A-0004) must flip the ADR *file*
# frontmatter — status: accepted + accepted_by + accepted_date — in the SAME
# acceptance PR. ADR-A-0017 drifted: it was accepted in the tracker on
# 2026-07-11 but its file stayed `proposed`; the gap was flagged 3x and never
# closed, forcing a manual flip during the v2.24.0 release. A-0018/A-0019 were
# similar operator handwork.
#
# This detector flags that drift class locally (no tracker credentials needed).
# An ADR counts as "accepted in the record" when EITHER:
#   (a) the agentic ADR index (adrs/agentic/README.md) marks its row **Accepted**
#       — the human-maintained acceptance summary that mirrors tracker acceptance, OR
#   (b) the ADR file itself already carries accepted_by/accepted_date metadata,
# yet the file's own `status:` frontmatter is still `proposed`.
#
# Advisory: prints one `DRIFT:` line per offending ADR to stdout.
# Exit: 0 = no drift; 1 = drift found (usable as a standalone gate).
#
# Usage:
#   scripts/adr-acceptance-drift.sh [adrs_dir] [index_readme]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADRS_DIR="${1:-$ROOT/adrs}"
INDEX="${2:-$ROOT/adrs/agentic/README.md}"

drift=0

while IFS= read -r f; do
    [ -f "$f" ] || continue

    # File `status:` (strip trailing inline comments + surrounding whitespace).
    status="$(grep -m1 '^status:' "$f" 2>/dev/null \
        | sed -E 's/^status:[[:space:]]*//; s/[[:space:]]*#.*$//; s/[[:space:]]*$//')"
    [ "$status" = "proposed" ] || continue

    id="$(grep -m1 '^id:' "$f" 2>/dev/null | sed -E 's/^id:[[:space:]]*//; s/[[:space:]]*$//')"

    # Signal (b): acceptance metadata present but status never flipped.
    if grep -qE '^accepted_by:[[:space:]]*[^[:space:]]' "$f" 2>/dev/null \
        || grep -qE '^accepted_date:[[:space:]]*[^[:space:]]' "$f" 2>/dev/null; then
        echo "DRIFT: ${id:-$f} carries accepted_by/accepted_date but status: proposed ($f)"
        drift=$((drift + 1))
        continue
    fi

    # Signal (a): index marks the ADR **Accepted** while the file is proposed.
    # Match only the index row whose SUBJECT is this ADR — its markdown link
    # `[ADR-A-nnnn](...)` — not incidental in-text mentions (e.g. another row's
    # "within ADR-A-0004/0005" prose), which would false-positive.
    if [ -n "$id" ] && [ -f "$INDEX" ]; then
        if grep -E "\[${id}\]\(" "$INDEX" 2>/dev/null | grep -qiE '\*\*Accepted\*\*'; then
            echo "DRIFT: ${id} marked **Accepted** in $(basename "$INDEX") but file status: proposed ($f)"
            drift=$((drift + 1))
        fi
    fi
done < <(find "$ADRS_DIR" -type f -name 'ADR-*.md' 2>/dev/null | sort)

if [ "$drift" -gt 0 ]; then
    echo "adr-acceptance-drift: ${drift} ADR(s) accepted in the record but still 'proposed' in file frontmatter."
    echo "Run the acceptance closeout — flip status + accepted_by + accepted_date in the acceptance PR (see docs/sop/ADR_AUTHORING_GUIDE.md)."
    exit 1
fi

exit 0
