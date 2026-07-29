#!/usr/bin/env bash
# next-rule-ledger-id.sh — mint the next ticket-scoped rule-ledger id (ABS-600).
#
# WHY: parallel stories that each read the highest R-NNNN off THEIR OWN branch
# and take +1 collide at integration — the Pilot-8 failure that renumbered 12
# ledger rows by hand. The fix is to stop deriving the id from a branch-local
# running counter and derive it from the introducing TICKET instead: the tracker
# mints ticket ids centrally, never in parallel, so `R-<TICKET>-<n>` ids are
# collision-free BY CONSTRUCTION across branches (two different tickets never
# share a prefix; within one ticket, only one seat allocates). This helper makes
# that rule executable — no cross-ref scan needed, unlike the migration case
# (scripts/next-migration-number.sh) whose prefix must encode execution order.
#
# Usage:
#   scripts/next-rule-ledger-id.sh <TICKET> [<ledger-file>]
#       <TICKET>       introducing ticket id, e.g. ABS-600 or PILOT-75
#       <ledger-file>  defaults to docs/rule-ledger.yaml
#
# Prints the next id (e.g. R-ABS-600-1, then R-ABS-600-2) on stdout.
# CLI/usage errors exit 64.
set -uo pipefail

die() { echo "next-rule-ledger-id: $*" >&2; exit 64; }

case "${1:-}" in -h|--help|help) sed -n '2,20p' "$0"; exit 0 ;; esac

TICKET="${1:-}"
[ -n "$TICKET" ] || die "need <TICKET> (e.g. ABS-600)"
printf '%s' "$TICKET" | grep -qE '^[A-Z][A-Z0-9]*-[0-9]+$' \
    || die "bad ticket id '$TICKET' (want <PROJECT>-<number>, e.g. ABS-600)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER="${2:-$SCRIPT_DIR/../docs/rule-ledger.yaml}"
[ -f "$LEDGER" ] || die "ledger not found: $LEDGER"

# Highest <n> already taken by THIS ticket in THIS ledger (0 if none). Only rows
# this ticket owns matter — other tickets' rows can never collide with ours.
max="$(grep -oE "^  - id: R-${TICKET}-[0-9]+" "$LEDGER" \
        | sed -E 's/.*-([0-9]+)$/\1/' | sort -n | tail -1)"
printf 'R-%s-%d\n' "$TICKET" "$(( ${max:-0} + 1 ))"
