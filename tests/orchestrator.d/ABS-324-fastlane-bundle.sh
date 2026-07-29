# =============================================================================
# ABS-324 — v3 Fastlane: bundling (several tickets share ONE Solo-Seat run /
#           branch / PR)
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER / TEST_DIR.
#
# Several eligible `lane=fastlane` tickets (ABS-319 field; ABS-322 collapsed
# chain) waiting at "Ready for Development" under the same parent are grouped
# into deterministic, capped bundles. The lexicographically-first member of a
# bundle is the LEAD: it spawns ONE Solo-Seat carrying the whole roster in its
# seat_note (so the seat commits each ticket atomically as [ABS-XXX] on the ONE
# shared branch <lead>-auto and opens ONE PR referencing every id). Every
# non-lead member FOLDS (FASTLANE-BUNDLE-FOLD: no separate spawn/branch/PR). The
# In Review combined gate for a lead evaluates the WHOLE bundle and attributes
# pass/fail per ticket. `lane=normal` and ineligible (flagged / depends_on)
# fastlane tickets are never bundled. The bundle still ends at the merge-queue —
# no self-merge, no merge token (guardrail cluster 5). Kill-switch
# ORCH_FASTLANE_BUNDLE=0; cap ORCH_FASTLANE_BUNDLE_MAX.
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-322 include).
tracker() { bash "$TRACKER" "$@"; }

# Create a fastlane child of $E, walk it to Ready for Development, echo its id.
# $2.. are extra `create` args (e.g. --flag data).
_abs324_mk_fl() {
    local epic="$1"; shift
    local id
    id="$(tracker create --type ticket --title "fl child" --role be-developer \
        --lane fastlane --parent "$epic" "$@" | awk '{print $NF}')"
    tracker transition "$id" "Ready for Development" --actor orchestrator \
        --reason "abs324 walk" >/dev/null 2>&1
    printf '%s' "$id"
}

echo -e "\n${CYAN}ABS-324 — fastlane bundling (shared Solo-Seat / branch / PR)${NC}"

# --- AC1: two eligible fastlane tickets -> ONE Solo-Seat run / branch / PR -----
new_env
E=$(tracker create --type epic --title "bundle epic" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
B=$(_abs324_mk_fl "$E")
lead=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | head -1)
other=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | tail -1)
roster=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | paste -sd, -)
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$lead role=be-developer to=Ready for Development note=fastlane-bundle-solo-seat" \
    "ABS-324 AC1: the bundle lead spawns exactly ONE Solo-Seat run"
assert_contains "$out" "bundle=$roster" \
    "ABS-324 AC1: the Solo-Seat spawn references BOTH ticket ids (one shared run)"
assert_contains "$out" "branch=$lead-auto" \
    "ABS-324 AC1: the bundle shares ONE branch (<lead>-auto -> one PR)"
assert_contains "$out" "INTENT FASTLANE-BUNDLE-FOLD ticket=$other role=- to=Ready for Development note=lead=$lead" \
    "ABS-324 AC1: the non-lead member folds into the shared run"
assert_not_contains "$out" "INTENT SPAWN ticket=$other role=be-developer to=Ready for Development" \
    "ABS-324 AC1: the non-lead member does NOT spawn its own Solo-Seat/branch/PR"
cleanup_env

# --- AC2: the bundle directive REACHES the Solo-Seat packet (per-ticket commits)
new_env
PKT="$TEST_DIR/pkt-bundle.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
E=$(tracker create --type epic --title "bundle epic pkt" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
B=$(_abs324_mk_fl "$E")
lead=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | head -1)
roster=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | paste -sd, -)
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
pkt="$(cat "$PKT")"
assert_contains "$pkt" "seat_note: fastlane-bundle-solo-seat:dev+scoped-tests+self-review bundle=$roster branch=$lead-auto" \
    "ABS-324 AC2: the bundle Solo-Seat directive REACHES the seat packet (not just the run.log)"
assert_contains "$pkt" "SEPARATE atomic commit tagged with that ticket's id ([ABS-XXX])" \
    "ABS-324 AC2: the packet instructs per-ticket atomic commits tagged [ABS-XXX] on the shared branch"
assert_contains "$pkt" "open ONE PR whose body references ALL bundle ids" \
    "ABS-324 AC1/AC2: the packet instructs ONE PR referencing all bundle ids"
unset STUB_PACKET_COPY
cleanup_env

# --- AC3: the combined gate evaluates the bundle with per-ticket attribution ---
new_env
E=$(tracker create --type epic --title "bundle epic gate" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
B=$(_abs324_mk_fl "$E")
lead=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | head -1)
roster=$(printf '%s\n%s\n' "$A" "$B" | LC_ALL=C sort | paste -sd, -)
# 1) run the Solo-Seat dispatch so the runner persists the bundle roster marker.
ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1
# 2) walk the lead to In Review and dispatch the combined gate.
tracker transition "$lead" "In Progress" --actor orchestrator --reason "abs324" >/dev/null 2>&1
tracker transition "$lead" "In Review"  --actor orchestrator --reason "abs324" >/dev/null 2>&1
out=$(orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$lead role=system-architect to=In Review note=fastlane-combined-gate:review+scoped-tests bundle=$roster per-ticket-attribution" \
    "ABS-324 AC3: the combined gate evaluates the WHOLE bundle and attributes pass/fail per ticket"
cleanup_env

# --- AC4: bundle size respects a configurable cap -----------------------------
new_env
export ORCH_FASTLANE_BUNDLE_MAX=2
E=$(tracker create --type epic --title "bundle epic cap" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
B=$(_abs324_mk_fl "$E")
C=$(_abs324_mk_fl "$E")
s1=$(printf '%s\n%s\n%s\n' "$A" "$B" "$C" | LC_ALL=C sort | sed -n 1p)
s2=$(printf '%s\n%s\n%s\n' "$A" "$B" "$C" | LC_ALL=C sort | sed -n 2p)
s3=$(printf '%s\n%s\n%s\n' "$A" "$B" "$C" | LC_ALL=C sort | sed -n 3p)
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "note=fastlane-bundle-solo-seat:dev+scoped-tests+self-review bundle=$s1,$s2 branch=$s1-auto" \
    "ABS-324 AC4: a bundle respects the configurable cap (max=2 -> exactly 2 tickets)"
assert_not_contains "$out" "bundle=$s1,$s2,$s3" \
    "ABS-324 AC4: the cap keeps a 3rd ticket out of the bundle"
assert_contains "$out" "INTENT SPAWN ticket=$s3 role=be-developer to=Ready for Development note=fastlane-solo-seat" \
    "ABS-324 AC4: the ticket beyond the cap is not pulled in — it dispatches on its own"
unset ORCH_FASTLANE_BUNDLE_MAX
cleanup_env

# --- AC5: ineligible (flagged) fastlane ticket is never pulled into a bundle ---
new_env
E=$(tracker create --type epic --title "bundle epic elig" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
Bf=$(_abs324_mk_fl "$E" --flag data)   # data flag -> forces the full chain, not bundle-eligible
C=$(_abs324_mk_fl "$E")
roster=$(printf '%s\n%s\n' "$A" "$C" | LC_ALL=C sort | paste -sd, -)
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "bundle=$roster" \
    "ABS-324 AC5: the two ELIGIBLE fastlane tickets bundle together"
assert_not_contains "$out" "FASTLANE-BUNDLE-FOLD ticket=$Bf" \
    "ABS-324 AC5: the data-flagged fastlane ticket is NOT folded into the bundle"
cleanup_env

# --- AC5 control: lane=normal tickets are never bundled ------------------------
new_env
E=$(tracker create --type epic --title "bundle epic normal" | awk '{print $NF}')
N1=$(tracker create --type ticket --title "normal one" --role be-developer --parent "$E" | awk '{print $NF}')
N2=$(tracker create --type ticket --title "normal two" --role be-developer --parent "$E" | awk '{print $NF}')
tracker transition "$N1" "Ready for Development" --actor orchestrator --reason "abs324" >/dev/null 2>&1
tracker transition "$N2" "Ready for Development" --actor orchestrator --reason "abs324" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "fastlane-bundle-solo-seat" \
    "ABS-324 AC5: normal-lane tickets are never bundled"
assert_not_contains "$out" "FASTLANE-BUNDLE-FOLD" \
    "ABS-324 AC5: no normal-lane ticket folds into a bundle"
assert_contains "$out" "INTENT SPAWN ticket=$N1 role=be-developer to=Ready for Development" \
    "ABS-324 AC5: each normal-lane ticket dispatches on its own (full v3 chain)"
assert_not_contains "$out" "note=fastlane-solo-seat" \
    "ABS-324 AC5: normal-lane spawn carries no fastlane mark at all"
cleanup_env

# --- kill-switch: ORCH_FASTLANE_BUNDLE=0 falls back to single-ticket collapse --
new_env
export ORCH_FASTLANE_BUNDLE=0
E=$(tracker create --type epic --title "bundle epic knob" | awk '{print $NF}')
A=$(_abs324_mk_fl "$E")
B=$(_abs324_mk_fl "$E")
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "fastlane-bundle-solo-seat" \
    "ABS-324: knob=0 disables bundling"
assert_not_contains "$out" "FASTLANE-BUNDLE-FOLD" \
    "ABS-324: knob=0 emits no fold"
assert_contains "$out" "INTENT SPAWN ticket=$A role=be-developer to=Ready for Development note=fastlane-solo-seat" \
    "ABS-324: knob=0 falls back to the ABS-322 single-ticket collapsed chain"
assert_contains "$out" "INTENT SPAWN ticket=$B role=be-developer to=Ready for Development note=fastlane-solo-seat" \
    "ABS-324: knob=0 dispatches each fastlane ticket on its own Solo-Seat"
unset ORCH_FASTLANE_BUNDLE
cleanup_env
