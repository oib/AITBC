#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Fastlane Eligibility Proposal (ABS-320, epic ABS-314 v3 fastlane)
# =============================================================================
# Computes and records an ADVISORY fastlane-eligibility PROPOSAL for a ticket at
# intake. The Issue Enrichment Agent runs this for each child it creates so a
# human sees a pre-assessed recommendation instead of judging every ticket by
# hand (ADR: eligibility rules from epic ABS-314 requirement (1)).
#
#   scripts/fastlane-eligibility.sh <ticket-id> [--dry-run]
#
# It evaluates four eligibility rules purely from ticket metadata knowable at
# intake and records the verdict as a `kind: decision` annotation via the
# task-tracking adapter ($TRACKER_CMD, default scripts/mock-tracker.sh):
#
#   (a) diff_surface      bounded diff surface   -> fail if type=epic OR the
#                         ticket carries a `model:opus` label (the enrichment
#                         gate's complexity proxy: architecture-heavy => broad,
#                         unbounded diff). At intake no diff exists yet, so this
#                         is the knowable proxy.
#   (b) schema_security   no schema change and no security-sensitive path
#                         -> fail if flags contain `data` (schema/migration) or
#                         `security` (security-sensitive path).
#   (c) depends_on        no depends_on -> fail if depends_on is non-empty or a
#                         `depends-on` link is present.
#   (d) inflight_conflict no conflict with in-flight work -> fail if a sibling
#                         (same parent) is currently in an active work status
#                         (the conservative intake proxy for "could touch the
#                         same area concurrently"; a real diff does not exist
#                         yet, so file overlap cannot be computed here).
#
# fastlane-eligible = yes  iff  all four rules pass.
#
# ADVISORY ONLY: this NEVER sets `lane=fastlane` (that is the human one-click
# confirm, ABS-321). It only records a recommendation. The output field shape is
# stable and machine-readable so the dashboard (ABS-321) can render yes/no + the
# per-rule reasons — see "Output field shape" below.
#
# Output field shape (one `key: value` per line; parseable line-by-line):
#   fastlane-eligible: <yes|no>
#   rule.diff_surface: <pass|fail> - <reason>
#   rule.schema_security: <pass|fail> - <reason>
#   rule.depends_on: <pass|fail> - <reason>
#   rule.inflight_conflict: <pass|fail> - <reason>
#
# bash 3.2 / BSD-tool safe (no grep -P, no associative arrays). Zero deps beyond
# the adapter it already shells out to.
# =============================================================================

TRACKER="${TRACKER_CMD:-scripts/mock-tracker.sh}"

# Sibling statuses that count as "in-flight" (actively being worked — post-claim
# through merge/docs). Not-yet-started (Backlog, Ready for Development, Design,
# epic-pipeline gates) and terminal (Done) statuses are NOT a conflict source.
IN_FLIGHT="In Progress|In Review|Security Review|Test Prep|In Test|Design Test|Story Acceptance|Merging|Docs"

die() { echo "fastlane-eligibility: $*" >&2; exit 2; }

ID=""
DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        -*) die "unknown option '$1'" ;;
        *) [ -z "$ID" ] || die "unexpected extra argument '$1'"; ID="$1"; shift ;;
    esac
done
[ -n "$ID" ] || die "usage: fastlane-eligibility.sh <ticket-id> [--dry-run]"

GET="$("$TRACKER" get "$ID")" || die "cannot read ticket '$ID' via \$TRACKER_CMD"

# Frontmatter region only (between the first two '---' fences) — never the body,
# so a '## depends_on' heading or prose cannot spoof a field.
FM="$(printf '%s\n' "$GET" | awk 'NR==1 && $0=="---"{f=1;next} f && $0=="---"{exit} f{print}')"
field() { printf '%s\n' "$FM" | grep -E "^$1:" | head -1 | sed -E "s/^$1:[[:space:]]*//" || true; }

TYPE="$(field type)"
PARENT="$(field parent)"
FLAGS="$(field flags)"
DEPENDS="$(field depends_on)"
LINKS="$(field links)"
LABELS="$(field labels)"

list_has() { # exact member match: list_has "<yaml list like [a, b]>" <member>
    printf '%s' "$1" | tr -d '[]' | tr ',' '\n' \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -qx "$2"
}

# --- Rule (a): bounded diff surface -----------------------------------------
if [ "$TYPE" = "epic" ]; then
    A=fail; A_REASON="type=epic (inherently broad diff surface)"
elif list_has "$LABELS" "model:opus"; then
    A=fail; A_REASON="model:opus label (architecture-heavy, unbounded diff)"
else
    A=pass; A_REASON="type=${TYPE:-ticket}, no model:opus label"
fi

# --- Rule (b): no schema change and no security-sensitive path --------------
B_HIT=""
list_has "$FLAGS" data && B_HIT="data"
list_has "$FLAGS" security && B_HIT="${B_HIT:+$B_HIT,}security"
if [ -n "$B_HIT" ]; then
    B=fail; B_REASON="flag(s): $B_HIT (schema/security-sensitive)"
else
    B=pass; B_REASON="no data/security flag"
fi

# --- Rule (c): no depends_on -------------------------------------------------
DEP_PRESENT=0
case "$DEPENDS" in ''|'[]') ;; *) DEP_PRESENT=1 ;; esac
printf '%s' "$LINKS" | grep -q 'depends-on' && DEP_PRESENT=1
if [ "$DEP_PRESENT" = 1 ]; then
    C=fail; C_REASON="depends_on present: ${DEPENDS:-$LINKS}"
else
    C=pass; C_REASON="no depends_on links"
fi

# --- Rule (d): no conflict with in-flight work ------------------------------
D=pass; D_REASON="no in-flight sibling${PARENT:+ under $PARENT}"
if [ -n "$PARENT" ]; then
    SIBLINGS="$("$TRACKER" search --parent "$PARENT" 2>/dev/null || true)"
    CONFLICT="$(printf '%s\n' "$SIBLINGS" | awk -F'\t' -v self="$ID" -v pat="$IN_FLIGHT" '
        $1 != self && $1 != "" {
            n = split(pat, a, "|")
            for (i = 1; i <= n; i++) if ($3 == a[i]) { print $1 " (" $3 ")"; break }
        }' | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    if [ -n "$CONFLICT" ]; then
        D=fail; D_REASON="in-flight sibling(s): $CONFLICT"
    fi
fi

# --- Verdict -----------------------------------------------------------------
if [ "$A" = pass ] && [ "$B" = pass ] && [ "$C" = pass ] && [ "$D" = pass ]; then
    VERDICT=yes
else
    VERDICT=no
fi

BODY="$(cat <<EOF
fastlane-eligible: $VERDICT
rule.diff_surface: $A - $A_REASON
rule.schema_security: $B - $B_REASON
rule.depends_on: $C - $C_REASON
rule.inflight_conflict: $D - $D_REASON
EOF
)"

# Always emit the proposal to stdout (enrichment captures it as evidence).
printf '%s\n' "$BODY"

# Record the advisory annotation — unless --dry-run. NEVER touches `lane`.
if [ "$DRY_RUN" = 0 ]; then
    mkdir -p work/scratch
    F="work/scratch/fastlane-eligibility-$ID.md"
    printf '%s\n' "$BODY" > "$F"
    "$TRACKER" comment "$ID" --kind decision --actor issue-enrichment --body-file "$F" >/dev/null
fi
