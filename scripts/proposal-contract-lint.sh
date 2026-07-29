#!/bin/bash
# =============================================================================
# Improvement-Proposal Change-Contract Lint (ABS-521 / epic ABS-514)
# =============================================================================
# Governed harness mutation (ADR-A-0028, survey arXiv 2605.18747 §3.5): every
# proposed harness change should carry a change contract — which invariants it
# preserves, which eval would falsify it, and how to roll it back. The
# work/improvement-proposals/ template carries these sections since ABS-521;
# this lint enforces them on proposals FILED AFTER THE CUTOVER DATE (the
# filename's YYYY-MM-DD prefix). Earlier proposals are grandfathered — history
# is not rewritten. Human forwarding stays manual (ADR-A-0004).
#
# Required H2 sections (post-cutoff): Rationale, Suggested Boilerplate Change,
# Impact, Invariants Preserved, Falsifying Eval, Rollback.
#
# Fixture overrides: PROPOSAL_DIR (default work/improvement-proposals),
# PROPOSAL_CUTOFF (default 2026-07-21; strictly-greater dates are enforced).
# Exit 0 = all post-cutoff proposals carry the contract. Exit 1 = violation.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIR="${PROPOSAL_DIR:-$REPO_ROOT/work/improvement-proposals}"
CUTOFF="${PROPOSAL_CUTOFF:-2026-07-21}"

REQUIRED="Rationale
Suggested Boilerplate Change
Impact
Invariants Preserved
Falsifying Eval
Rollback"

fail=0
[ -d "$DIR" ] || { printf 'proposal-contract-lint: missing dir: %s\n' "$DIR" >&2; exit 2; }

for f in "$DIR"/*.md; do
    [ -e "$f" ] || continue
    base="$(basename "$f")"
    case "$base" in README.md) continue ;; esac
    d="$(printf '%s' "$base" | sed -nE 's/^([0-9]{4}-[0-9]{2}-[0-9]{2})-.*/\1/p')"
    [ -n "$d" ] || continue                     # undated file: naming SOP's concern, not this lint's
    # String compare works for ISO dates; grandfather everything <= cutoff.
    [ "$d" \> "$CUTOFF" ] || continue
    while IFS= read -r sec; do
        [ -n "$sec" ] || continue
        grep -qE "^## $sec" "$f" && continue
        printf 'CONTRACT: %s (filed %s) is missing the required "## %s" section\n' "$base" "$d" "$sec" >&2
        fail=1
    done <<EOF
$REQUIRED
EOF
done

if [ "$fail" -ne 0 ]; then
    printf '\nproposal-contract-lint: FAIL — post-%s proposals must carry the full change contract (see work/improvement-proposals/README.md).\n' "$CUTOFF" >&2
    exit 1
fi
printf 'proposal-contract-lint: OK — every post-%s proposal carries the change contract.\n' "$CUTOFF"
exit 0
