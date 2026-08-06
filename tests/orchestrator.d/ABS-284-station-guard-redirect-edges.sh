# =============================================================================
# ABS-284 — STATION-GUARD / DONE-GATE redirect edges LAND, or fail LOUDLY
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_eq / assert_not_contains, PASS/FAIL/TOTAL,
# REPO_ROOT / ORCH / TRACKER, new_env / cleanup_env, and every exported env var.
#
# THE DEFECT: both fail-closed runner gates emit a BACKWARD redirect the
# canonical status table must permit. The edges were ABSENT from
# profiles/neutral/adapters/statuses.yaml, so on the DEFAULT adapter
# (scripts/mock-tracker.sh, which ENFORCES the next: table) each gate (1)
# announced an INTENT, (2) attempted a redirect the table rejected, (3) swallowed
# the rejection and STILL returned 0 (INTERVENED), (4) suppressed the seat spawn —
# forever, because the ticket never moved: a silent permanent stall that read in
# the log as enforcement (ABS-284 Defects 1 & 2).
#
# The existing suites (test-station-guard.sh / test-done-gate.sh) STUB `tracker`,
# so they never drove the REAL adapter and never noticed the missing edges — the
# coverage gap that let ABS-136/ABS-211/ABS-247 each ship broken. This suite
# closes it: it drives the gates through the REAL mock adapter (sourced inside a
# `bash -c` subprocess, like ABS-246, so the harness shell is never clobbered) and
# asserts the ticket's STATUS re-read from the adapter, not the INTENT line.
# =============================================================================

# _abs284_gate <gate-fn> <to> <flag-or-empty> <forge-open?> [statuses-override]
#   Drives a fresh ticket to <to> through legal edges on the REAL mock adapter,
#   runs the gate live, and prints four structured lines the parent asserts on:
#     RC=<n>  STATUS=<status re-read from the adapter>  RUNLOG=<...>  GET=<dump>
#   All inside one subprocess so a sourced orchestrator.sh cannot leak into the
#   harness shell. Env (MOCK_TRACKER_TICKETS_DIR / TRACKER_CMD) is inherited.
_abs284_gate() {
    local gate="$1" to="$2" flag="$3" forge_open="$4" statuses="${5:-}"
    ABS284_GATE="$gate" ABS284_TO="$to" ABS284_FLAG="$flag" \
    ABS284_FORGE_OPEN="$forge_open" ABS284_STATUSES="$statuses" \
    bash -c '
        [ -n "$ABS284_STATUSES" ] && export MOCK_TRACKER_STATUSES="$ABS284_STATUSES"
        source "$1" >/dev/null 2>&1
        MODE="live"
        export ORCH_RUN_LOG="$ABS284_RUNLOG"; : > "$ORCH_RUN_LOG"
        cflag=""; [ -n "$ABS284_FLAG" ] && cflag="--flag $ABS284_FLAG"
        # shellcheck disable=SC2086
        id="$(tracker create --type ticket --title "ABS-284 $ABS284_GATE" $cflag)"
        # Drive along the LEGAL edges (mock enforces the next: table, so every
        # hop here is a real, permitted transition — the illegal SKIP the guard
        # then repairs is the single In Review->In Test / In Test->RfHA hop).
        # Statuses contain spaces, so feed them one-per-line via a here-doc.
        while IFS= read -r s; do
            [ -n "$s" ] || continue
            tracker transition "$id" "$s" --actor test --reason step >/dev/null 2>&1
        done <<STEPS
$(printf "%s\n" "Ready for Development" "In Progress" "In Review" "In Test")
$( [ "$ABS284_TO" = "Ready for Human Acceptance" ] || [ "$ABS284_TO" = "Done" ] && printf "%s\n" "Ready for Human Acceptance" )
$( [ "$ABS284_TO" = "Done" ] && printf "%s\n" "Ready for Merge" "Done" )
STEPS
        if [ "$ABS284_FORGE_OPEN" = "1" ]; then
            FORGE_CMD="stub"; forge() { printf "OPEN #133\n"; }
        fi
        rc=0
        "$ABS284_GATE" "$id" "$ABS284_TO" >/dev/null 2>&1 || rc=$?
        printf "RC=%s\n" "$rc"
        printf "STATUS=%s\n" "$(ticket_status "$id")"
        printf "RUNLOG=%s\n" "$(tr "\t" "|" < "$ORCH_RUN_LOG" | tr "\n" ";")"
        printf "GET=%s\n" "$(tracker get "$id" | tr "\n" " ")"
    ' _abs284 "$ORCH"
}

echo -e "\n${CYAN}=== ABS-284 STATION-GUARD / DONE-GATE redirect edges ===${NC}"

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC1 — v1/v2 happy path: In Test -> RfHA redirect to Story Acceptance LANDS${NC}"
# -----------------------------------------------------------------------------
new_env
export ABS284_RUNLOG="$TEST_DIR/ac1.log"
out="$(_abs284_gate station_guard "Ready for Human Acceptance" "" 0)"
assert_contains "$out" "RC=0" "AC1: station_guard INTERVENES (rc 0) on the folded Story Acceptance"
assert_contains "$out" "STATUS=Story Acceptance" "AC1: status RE-READS as 'Story Acceptance' — redirect LANDED, no silent stall"
cleanup_env

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC2 — ABS-247 conditional-mandatory redirects LAND${NC}"
# -----------------------------------------------------------------------------
new_env
export ABS284_RUNLOG="$TEST_DIR/ac2.log"
out="$(_abs284_gate station_guard "In Test" "security" 0)"
assert_contains "$out" "RC=0" "AC2 security: station_guard INTERVENES (rc 0)"
assert_contains "$out" "STATUS=Security Review" "AC2: security-flagged story RE-READS as 'Security Review' (edge In Test -> Security Review landed)"
out="$(_abs284_gate station_guard "In Test" "data" 0)"
assert_contains "$out" "RC=0" "AC2 data: station_guard INTERVENES (rc 0)"
assert_contains "$out" "STATUS=Test Prep" "AC2: data-flagged story RE-READS as 'Test Prep' (edge In Test -> Test Prep landed)"
# design-flagged story lands RfHA -> first folded mandatory is Design Test (idx 8),
# not Story Acceptance (idx 9). The AC5 derivation surfaced this edge; assert it lands.
out="$(_abs284_gate station_guard "Ready for Human Acceptance" "design" 0)"
assert_contains "$out" "RC=0" "AC2 design: station_guard INTERVENES (rc 0)"
assert_contains "$out" "STATUS=Design Test" "AC2: design-flagged story RE-READS as 'Design Test' (edge RfHA -> Design Test landed)"
cleanup_env

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC3 — DONE-GATE: Done with an OPEN PR redirect to Merging LANDS${NC}"
# -----------------------------------------------------------------------------
new_env
export ABS284_RUNLOG="$TEST_DIR/ac3.log"
out="$(_abs284_gate done_pr_gate "Done" "" 1)"
assert_contains "$out" "RC=0" "AC3: done_pr_gate INTERVENES (rc 0) on a Done whose PR is still open"
assert_contains "$out" "STATUS=Merging" "AC3: ticket RE-READS as 'Merging' against the real adapter (edge Done -> Merging landed)"
assert_contains "$out" "#133" "AC3: the gate-results comment names the unmerged PR (#133)"
cleanup_env

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC4 — a rejected redirect is refused LOUDLY, never reported as INTERVENED${NC}"
# -----------------------------------------------------------------------------
# strip_edge removes ONE redirect edge from statuses.yaml, reproducing the
# pre-ABS-284 "edge missing" condition on the real enforcing adapter.
_abs284_strip_edge() {
    awk -v st="$1" -v tg="$2" '
        /^  - name: / { name=$0; sub(/^  - name: /,"",name) }
        { if (name==st && $0=="      - " tg) next; print }
    ' "$MOCK_TRACKER_STATUSES" > "$3"
}
new_env
export ABS284_RUNLOG="$TEST_DIR/ac4sg.log"
BROKEN_SG="$TEST_DIR/statuses-no-sa.yaml"
_abs284_strip_edge "Ready for Human Acceptance" "Story Acceptance" "$BROKEN_SG"
out="$(_abs284_gate station_guard "Ready for Human Acceptance" "" 0 "$BROKEN_SG")"
assert_not_contains "$out" "RC=0" "AC4(a) station-guard: a rejected redirect does NOT report INTERVENED (rc != 0)"
assert_contains "$out" "STATION-GUARD-REJECTED" "AC4(a): the rejection is SURFACED as a run.log event"
assert_contains "$out" "could NOT enforce" "AC4(a): a naming audit comment records the rejected edge"
assert_contains "$out" "Ready for Human Acceptance' -> 'Story Acceptance" "AC4(a): the comment names the exact rejected edge"
assert_contains "$out" "STATUS=Ready for Human Acceptance" "AC4(b): the ticket did NOT silently move (redirect really was rejected)"
# (b) no unbounded no-spawn loop: rc != 0 means the dispatcher is NOT told
# INTERVENED, so the spawn is not suppressed — a repeat visit refuses identically.
out2="$(_abs284_gate station_guard "Ready for Human Acceptance" "" 0 "$BROKEN_SG")"
assert_not_contains "$out2" "RC=0" "AC4(b): a repeat visit again refuses loudly (rc != 0) — no silent no-spawn loop"

export ABS284_RUNLOG="$TEST_DIR/ac4dg.log"
BROKEN_DG="$TEST_DIR/statuses-no-merging.yaml"
_abs284_strip_edge "Done" "Merging" "$BROKEN_DG"
out="$(_abs284_gate done_pr_gate "Done" "" 1 "$BROKEN_DG")"
assert_not_contains "$out" "RC=0" "AC4(a) done-gate: a rejected redirect does NOT report INTERVENED (rc != 0)"
assert_contains "$out" "DONE-PR-GATE-REJECTED" "AC4(a): the rejection is SURFACED as a run.log event"
assert_contains "$out" "could NOT enforce" "AC4(a): a naming audit comment records the rejected edge"
assert_contains "$out" "STATUS=Done" "AC4(b): the ticket did NOT silently move (redirect really was rejected)"
cleanup_env

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC5 — mechanical completeness lock (anti-rot)${NC}"
# -----------------------------------------------------------------------------
# Derive, from the guard's OWN chain helpers, every (landing -> target) redirect
# the gates can emit over all LEGAL table edges x conditional-flag subsets, and
# assert statuses.yaml contains each. Adding a chain station or a gate without its
# edge FAILS here — the enumeration cannot silently go stale.
new_env
missing="$(bash -c '
    source "$1" >/dev/null 2>&1
    S="$MOCK_TRACKER_STATUSES"
    edges="$(awk '"'"'
        /^  - name: / { name=$0; sub(/^  - name: /,"",name); innext=0; next }
        /^    next:/  { innext=1; next }
        /^    [a-z]/  { innext=0 }
        /^      - /   { if (innext) { t=$0; sub(/^      - /,"",t); print name "\t" t } }
    '"'"' "$S")"
    edge_exists() { printf "%s\n" "$edges" | grep -qF -- "$(printf "%s\t%s" "$1" "$2")"; }
    subsets=("" "design" "security" "data" "design security" "design data" "security data" "design security data")
    miss=""
    while IFS="$(printf "\t")" read -r lf lt; do
        [ -n "$lf" ] || continue
        [ "$(guard_chain_index "$lt")" -gt 1 ] || continue
        for fl in "${subsets[@]}"; do
            if forward_skip_illegitimate "$lf" "$lt" "$fl"; then
                tgt="$(first_skipped_mandatory "$(guard_chain_index "$lf")" "$(guard_chain_index "$lt")" "$fl")"
                [ -n "$tgt" ] || continue
                edge_exists "$lt" "$tgt" || miss="$miss [$lt -> $tgt (via $lf->$lt flags=\"$fl\")]"
            fi
        done
    done <<EOF
$edges
EOF
    # DONE-GATE emits exactly one edge, independent of the chain walk.
    edge_exists "Done" "Merging" || miss="$miss [Done -> Merging (DONE-GATE)]"
    printf "%s" "$miss"
' _abs284 "$ORCH")"
assert_eq "$missing" "" "AC5: statuses.yaml contains EVERY redirect edge the gates can emit"
cleanup_env

# -----------------------------------------------------------------------------
echo -e "${CYAN}ABS-284 AC7 — the deliberate constraints survive (no blanket backward legality)${NC}"
# -----------------------------------------------------------------------------
# A representative forbidden bounce (ADR-A-0002 / ABS-90: Done is terminal with
# ONE reopen edge, Ready for Development) must still be rejected by the real adapter.
new_env
T7="$(tracker create --type ticket --title "ABS-284 forbidden edge")"
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$T7" "$s" --actor test --reason step >/dev/null 2>&1
done
reject_rc=0
tracker transition "$T7" "In Progress" --actor test --reason x >/dev/null 2>&1 || reject_rc=$?
# assert_ne is not in the harness; map "rejected" to a stable token for assert_eq.
[ "$reject_rc" != "0" ] && rej="rejected" || rej="ACCEPTED"
assert_eq "$rej" "rejected" "AC7: 'Done -> In Progress' is STILL rejected (no blanket backward legality)"
assert_eq "$(tracker get "$T7" | awk -F': ' '/^status: /{print $2; exit}')" "Done" "AC7: the forbidden transition did not move the ticket"
cleanup_env
