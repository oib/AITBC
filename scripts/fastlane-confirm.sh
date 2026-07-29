#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# One-Click Fastlane Confirm Control (ABS-321, epic ABS-314 v3 fastlane)
# =============================================================================
# The human-facing "dashboard" control that surfaces the fastlane-eligibility
# PROPOSAL (recorded by the Issue Enrichment Agent, ABS-320) and turns the human
# decision into a SINGLE action: promote a ticket to `lane=fastlane` (or revert
# to `lane=normal`). The human stays the deciding actor — nothing here promotes a
# lane on its own (ABS-314 requirement (1); guardrail cluster 5: the click grants
# NO merge authority — merge-token, full-suite at epic integration and human
# merge to main are untouched).
#
#   scripts/fastlane-confirm.sh view    <ticket-id>              # render proposal + lane state
#   scripts/fastlane-confirm.sh confirm <ticket-id> [--override] # one-click -> lane=fastlane
#   scripts/fastlane-confirm.sh revert  <ticket-id>              # -> lane=normal
#
# The proposal is read from the ticket's recorded `kind: decision` annotation
# (ABS-320 field shape: `fastlane-eligible: yes|no` + four `rule.<name>:` lines).
# When no annotation is recorded yet, the control falls back to computing it live
# via scripts/fastlane-eligibility.sh --dry-run so the gate is never blind.
#
# `confirm` is ENABLED only when the proposal verdict is `yes`. For a `no` verdict
# it is DISABLED and refuses (non-zero) unless the human passes an explicit
# `--override` — the deliberate "confirm anyway" click. `view` NEVER mutates lane;
# only `confirm`/`revert` change it, and only on this explicit human invocation
# (no auto-promotion anywhere).
#
# bash 3.2 / BSD-tool safe (no grep -P, no associative arrays). Zero deps beyond
# the adapter it already shells out to.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACKER="${TRACKER_CMD:-$SCRIPT_DIR/mock-tracker.sh}"

die() { echo "fastlane-confirm: $*" >&2; exit 2; }

usage() {
    cat >&2 <<'EOF'
usage: fastlane-confirm.sh <view|confirm|revert> <ticket-id> [--override]
  view    <id>              render the eligibility proposal + current lane state
  confirm <id> [--override] one-click promote to lane=fastlane (override a 'no' verdict)
  revert  <id>              return the ticket to lane=normal
EOF
    exit 2
}

# --- arg parse ---------------------------------------------------------------
ACTION="${1:-}"; [ -n "$ACTION" ] || usage
shift || true
ID=""; OVERRIDE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --override) OVERRIDE=1; shift ;;
        -*) die "unknown option '$1'" ;;
        *) [ -z "$ID" ] || die "unexpected extra argument '$1'"; ID="$1"; shift ;;
    esac
done
[ -n "$ID" ] || usage
case "$ACTION" in view|confirm|revert) ;; *) die "unknown action '$ACTION' (view|confirm|revert)" ;; esac

GET="$("$TRACKER" get "$ID")" || die "cannot read ticket '$ID' via \$TRACKER_CMD"

# --- current lane (frontmatter region only — never body, so a '## lane'
# heading cannot spoof the field; absent field defaults to normal, ABS-319) ----
FM="$(printf '%s\n' "$GET" | awk 'NR==1 && $0=="---"{f=1;next} f && $0=="---"{exit} f{print}')"
LANE="$(printf '%s\n' "$FM" | grep -E '^lane:' | head -1 | sed -E 's/^lane:[[:space:]]*//' || true)"
[ -n "$LANE" ] || LANE="normal"

# --- eligibility proposal: last recorded `fastlane-eligible:` block ----------
# ABS-320 shape: a `fastlane-eligible: yes|no` line followed by four `rule.` lines.
extract_proposal() {
    printf '%s\n' "$1" | awk '
        /^fastlane-eligible:[[:space:]]*(yes|no)[[:space:]]*$/ { buf=$0; cap=1; next }
        cap==1 && /^rule\./ { buf=buf "\n" $0; next }
        cap==1 { cap=0; last=buf }
        END { if (cap==1) last=buf; if (last!="") print last }
    '
}
PROPOSAL="$(extract_proposal "$GET")"
SOURCE="recorded annotation"
if [ -z "$PROPOSAL" ]; then
    # No annotation yet — compute it live (advisory, records nothing).
    if PROPOSAL="$(TRACKER_CMD="$TRACKER" "$SCRIPT_DIR/fastlane-eligibility.sh" "$ID" --dry-run 2>/dev/null)"; then
        SOURCE="computed live (no annotation recorded)"
    else
        PROPOSAL=""
    fi
fi

VERDICT=""
if [ -n "$PROPOSAL" ]; then
    VERDICT="$(printf '%s\n' "$PROPOSAL" | grep -E '^fastlane-eligible:' | head -1 | sed -E 's/^fastlane-eligible:[[:space:]]*//')"
fi

# confirm-control state, derived purely from lane + verdict (never mutates).
if [ "$LANE" = "fastlane" ]; then
    CONTROL="already-fastlane"
elif [ "$VERDICT" = "yes" ]; then
    CONTROL="enabled"
else
    CONTROL="disabled"   # verdict 'no' or unknown -> override required
fi

render() {
    echo "── Fastlane control · $ID ─────────────────────────────"
    echo "lane: $LANE"
    if [ -n "$PROPOSAL" ]; then
        echo "proposal ($SOURCE):"
        printf '%s\n' "$PROPOSAL" | sed 's/^/  /'
    else
        echo "proposal: none recorded (run enrichment / fastlane-eligibility.sh)"
    fi
    echo "confirm-control: $CONTROL"
}

case "$ACTION" in
    view)
        render
        ;;

    confirm)
        if [ "$LANE" = "fastlane" ]; then
            render
            echo "note: already on lane=fastlane — nothing to confirm (use 'revert' to undo)."
            exit 0
        fi
        if [ "$VERDICT" != "yes" ] && [ "$OVERRIDE" -eq 0 ]; then
            render
            echo "fastlane-confirm: confirm DISABLED — verdict is '${VERDICT:-unknown}', not 'yes'." >&2
            echo "fastlane-confirm: pass --override to promote anyway (explicit human decision)." >&2
            exit 3
        fi
        mkdir -p work/scratch
        REASON="work/scratch/fastlane-confirm-$ID.md"
        if [ "$VERDICT" = "yes" ]; then
            printf '%s\n' "One-click fastlane confirm (ABS-321): eligibility verdict=yes; human confirmed lane=fastlane." > "$REASON"
        else
            printf '%s\n' "One-click fastlane confirm (ABS-321): verdict='${VERDICT:-unknown}' OVERRIDDEN by explicit human --override; lane=fastlane." > "$REASON"
        fi
        "$TRACKER" update "$ID" lane fastlane >/dev/null
        "$TRACKER" comment "$ID" --kind decision --actor fastlane-confirm --body-file "$REASON" >/dev/null 2>&1 || true
        LANE="fastlane"; CONTROL="already-fastlane"
        render
        echo "confirmed: $ID promoted to lane=fastlane."
        ;;

    revert)
        if [ "$LANE" != "fastlane" ]; then
            render
            echo "note: lane is already '$LANE' — nothing to revert."
            exit 0
        fi
        mkdir -p work/scratch
        REASON="work/scratch/fastlane-confirm-$ID.md"
        printf '%s\n' "Fastlane revert (ABS-321): human returned $ID to lane=normal." > "$REASON"
        "$TRACKER" update "$ID" lane normal >/dev/null
        "$TRACKER" comment "$ID" --kind decision --actor fastlane-confirm --body-file "$REASON" >/dev/null 2>&1 || true
        LANE="normal"
        # recompute control after revert
        if [ "$VERDICT" = "yes" ]; then CONTROL="enabled"; else CONTROL="disabled"; fi
        render
        echo "reverted: $ID returned to lane=normal."
        ;;
esac
