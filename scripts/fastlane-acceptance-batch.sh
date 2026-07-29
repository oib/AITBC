#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Asynchronous Fastlane PO-Acceptance — daily batch (ABS-323, epic ABS-314 v3)
# =============================================================================
# Moves PO story-acceptance for `lane=fastlane` tickets OFF the synchronous
# per-ticket path (ABS-322 folds the inline Story-Acceptance seat away) and onto
# an asynchronous DAILY BATCH: fastlane tickets that have cleared the combined
# review/test gate AND the merge-queue accumulate in `Docs`, and the PO-Agent
# accepts/rejects the whole set in one pass — throughput is no longer gated on
# inline acceptance, while acceptance SEMANTICS are unchanged (per-ticket
# accept/reject with reasoning against each ticket's AC evidence).
#
#   scripts/fastlane-acceptance-batch.sh list                       # the daily batch
#   scripts/fastlane-acceptance-batch.sh accept <id> --reason-file f  # record accept
#   scripts/fastlane-acceptance-batch.sh reject <id> --reason-file f  # record reject + rework
#
# WHERE the batch collects (ABS-323 AC1/AC3): a ticket is in the batch iff it is
#   * lane=fastlane                         (first-class field, ABS-319)
#   * status = Docs                          (entered_when "Story merged" — it has
#                                             passed the ONE combined gate at In
#                                             Review AND the merge-queue at Merging;
#                                             a gate-less fastlane ticket is at an
#                                             earlier station and never appears here)
#   * has NO recorded acceptance decision yet (so a re-run does not re-list it)
#
# ACCEPTANCE IS NOT MERGE (ABS-323 AC5; guardrail cluster 5): `accept` records a
# `kind: decision` comment ONLY — it performs no transition and no merge. The
# merge-token, the full suite at epic integration, and the HUMAN merge to main
# are all untouched; the accepted ticket still awaits the human merge gate.
#
# REJECTION (ABS-323 AC2/AC4): `reject` records the decision + a defect list and
# transitions `Docs -> Ready for Development` as the po-agent actor. That backward
# agent transition IS the ABS-74 rework counter's input (rework_count derives the
# count from the transition-reason history: a non-human/non-orchestrator backward
# hop), so the counter increments with no separate ledger to mutate. The reject
# edge is a documented legal edge in profiles/neutral/adapters/statuses.yaml.
#
# bash 3.2 / BSD-tool safe (no grep -P, no associative arrays, no mapfile). Zero
# deps beyond the $TRACKER_CMD adapter it already shells out to.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACKER="${TRACKER_CMD:-$SCRIPT_DIR/mock-tracker.sh}"

# The single station where merged-but-unaccepted fastlane work rests (see header).
BATCH_STATUS="Docs"
# The rework bounce target for a rejected ticket (backward, counted by ABS-74).
REJECT_TARGET="Ready for Development"

die() { echo "fastlane-acceptance-batch: $*" >&2; exit 2; }

usage() {
    cat >&2 <<'EOF'
usage: fastlane-acceptance-batch.sh <list|accept|reject> [<ticket-id>] [--reason <text> | --reason-file <path>]
  list                                the daily acceptance batch (fastlane tickets
                                      past the merge-queue, awaiting acceptance)
  accept <id> --reason-file <path>    record an ACCEPT decision (no merge)
  reject <id> --reason-file <path>    record a REJECT decision + defect list, and
                                      route the ticket back to development (rework)
EOF
    exit 2
}

# --- frontmatter helpers -----------------------------------------------------
# lane read from the FRONTMATTER region only, so a '## lane' body heading cannot
# spoof it; an absent field defaults to normal (pre-ABS-319 tickets, ABS-319).
fm_region() {
    printf '%s\n' "$1" | awk 'NR==1 && $0=="---"{f=1;next} f && $0=="---"{exit} f{print}'
}
lane_of()   { printf '%s\n' "$(fm_region "$1")" | grep -E '^lane:'   | head -1 | sed -E 's/^lane:[[:space:]]*//'   || true; }
status_of() { printf '%s\n' "$(fm_region "$1")" | grep -E '^status:' | head -1 | sed -E 's/^status:[[:space:]]*//' || true; }
title_of()  { printf '%s\n' "$(fm_region "$1")" | grep -E '^title:'  | head -1 | sed -E 's/^title:[[:space:]]*//'  || true; }

# A ticket already carries a batch acceptance decision when a recorded comment
# body contains the marker this script writes (accept OR reject).
has_decision() { printf '%s\n' "$1" | grep -qE '^fastlane-acceptance:[[:space:]]*(accept|reject)\b'; }

# --- arg parse ---------------------------------------------------------------
ACTION="${1:-}"; [ -n "$ACTION" ] || usage
shift || true
ID=""; REASON=""; REASON_FILE=""; HAVE_REASON=0
while [ $# -gt 0 ]; do
    case "$1" in
        --reason)      [ $# -ge 2 ] || die "--reason requires a value"; REASON="$2"; HAVE_REASON=1; shift 2 ;;
        --reason-file) [ $# -ge 2 ] || die "--reason-file requires a value"; REASON_FILE="$2"; shift 2 ;;
        -*) die "unknown option '$1'" ;;
        *) [ -z "$ID" ] || die "unexpected extra argument '$1'"; ID="$1"; shift ;;
    esac
done
case "$ACTION" in list|accept|reject) ;; *) die "unknown action '$ACTION' (list|accept|reject)" ;; esac

# =============================================================================
# list — the daily batch
# =============================================================================
if [ "$ACTION" = "list" ]; then
    [ -z "$ID" ] || die "'list' takes no ticket-id"
    echo "── Fastlane PO-acceptance batch · $(date -u +%Y-%m-%d) ─────────────"
    echo "(fastlane tickets past the combined gate + merge-queue, awaiting acceptance)"
    n=0
    # search emits: id<TAB>type<TAB>status<TAB>title. Restrict to fastlane in the
    # rest station; then drop any ticket that already has a decision recorded.
    while IFS="$(printf '\t')" read -r id _type _status _title; do
        [ -n "$id" ] || continue
        dump="$("$TRACKER" get "$id" 2>/dev/null || true)"
        [ -n "$dump" ] || continue
        has_decision "$dump" && continue
        n=$((n+1))
        echo ""
        echo "• $id — $(title_of "$dump")"
        echo "    status: $(status_of "$dump")  lane: $(lane_of "$dump")"
        echo "    review: check this ticket's Acceptance Criteria against its evidence,"
        echo "            then: accept $id --reason-file <f>  |  reject $id --reason-file <f>"
    done <<EOF
$("$TRACKER" search --lane fastlane --status "$BATCH_STATUS" 2>/dev/null || true)
EOF
    echo ""
    echo "batch size: $n"
    exit 0
fi

# =============================================================================
# accept / reject — per-ticket decision (acceptance semantics unchanged)
# =============================================================================
[ -n "$ID" ] || usage
if [ -n "$REASON_FILE" ]; then
    [ "$HAVE_REASON" -eq 0 ] || die "--reason and --reason-file are mutually exclusive"
    [ -f "$REASON_FILE" ] || die "--reason-file not found: $REASON_FILE"
    REASON="$(cat "$REASON_FILE")"
fi
[ -n "$REASON" ] || die "$ACTION requires a reason (--reason or --reason-file) — the decision must cite the ticket's AC evidence (AC2)"

DUMP="$("$TRACKER" get "$ID" 2>/dev/null)" || die "cannot read ticket '$ID' via \$TRACKER_CMD"
LANE="$(lane_of "$DUMP")"; [ -n "$LANE" ] || LANE="normal"
STATUS="$(status_of "$DUMP")"

# Guardrails shared by accept/reject.
[ "$LANE" = "fastlane" ] || die "$ID is lane='$LANE', not fastlane — the async batch only accepts fastlane tickets"
# AC3: acceptance runs ONLY after the combined gate + merge-queue. A ticket that
# has not reached the rest station has not passed the gate — refuse.
[ "$STATUS" = "$BATCH_STATUS" ] || die "$ID is in '$STATUS', not '$BATCH_STATUS' — it has not cleared the combined gate + merge-queue yet (AC3)"
if has_decision "$DUMP"; then
    die "$ID already has a recorded fastlane acceptance decision — refusing to double-decide"
fi

mkdir -p work/scratch
BODY="work/scratch/fastlane-acceptance-$ID.md"

if [ "$ACTION" = "accept" ]; then
    {
        echo "fastlane-acceptance: accept"
        echo "ticket: $ID"
        echo "decided-by: po-agent (async daily batch, ABS-323)"
        echo "reasoning (vs AC evidence):"
        printf '%s\n' "$REASON" | sed 's/^/  /'
        echo "note: acceptance grants NO merge authority (AC5) — the ticket still awaits the human merge gate."
    } > "$BODY"
    # Decision ONLY: no transition, no merge (AC5).
    "$TRACKER" comment "$ID" --kind decision --actor po-agent --body-file "$BODY" >/dev/null
    echo "accepted: $ID — decision recorded (no merge). Ticket still awaits the human merge gate."
    exit 0
fi

# reject
{
    echo "fastlane-acceptance: reject"
    echo "ticket: $ID"
    echo "decided-by: po-agent (async daily batch, ABS-323)"
    echo "defects (routing back to development):"
    printf '%s\n' "$REASON" | sed 's/^/  /'
} > "$BODY"
"$TRACKER" comment "$ID" --kind decision --actor po-agent --body-file "$BODY" >/dev/null
# AC4: backward agent transition -> ABS-74 rework counter increments (derived from
# the transition-reason history). --expect-from makes a lost race a clean NOOP.
REJ_REASON="work/scratch/fastlane-acceptance-reject-$ID.md"
printf '%s\n' "Fastlane async acceptance (ABS-323): PO rejected — routing back to development for rework. Defect list recorded in the decision comment above." > "$REJ_REASON"
"$TRACKER" transition "$ID" "$REJECT_TARGET" --actor po-agent \
    --reason-file "$REJ_REASON" --expect-from "$BATCH_STATUS" >/dev/null
echo "rejected: $ID — defect list recorded; routed to '$REJECT_TARGET' (rework counter increments, AC4)."
