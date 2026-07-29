# =============================================================================
# ABS-322 — v3 Fastlane: collapsed chain (Solo-Seat + combined gate + merge-queue)
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER.
#
# A `lane=fastlane` ticket (lane is a first-class field, ABS-319) folds the
# multi-seat story pipeline into ONE Solo-Seat (dev+scoped-tests+self-review) ->
# ONE combined review/test gate (In Review) -> merge-queue. The QAS (In Test)
# and PO (Story Acceptance) tail is folded away by the runner (FASTLANE-COLLAPSE:
# audit comment + forward re-transition, no spawn). `lane=normal` is unchanged —
# it keeps the full v3 chain. The chain ends at the merge-queue (Merging); the
# merge-token and the human merge to main are untouched (AC5).
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-304 include).
tracker() { bash "$TRACKER" "$@"; }

# Walk a story ticket forward to <target> over legal edges (direct transitions,
# never orch, so nothing is skipped during setup).
_abs322_walk() {
    local t="$1" target="$2" s
    for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance"; do
        tracker transition "$t" "$s" --actor orchestrator --reason "abs322 walk" >/dev/null 2>&1
        [ "$s" = "$target" ] && return 0
    done
}

echo -e "\n${CYAN}ABS-322 — fastlane collapsed chain${NC}"

# --- AC1: the implementer spawn is the single Solo-Seat (dev+tests+self-review) --
new_env
F=$(tracker create --type ticket --title "fastlane story" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "Ready for Development"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$F role=be-developer to=Ready for Development" "ABS-322 AC1: fastlane implementer spawns exactly one Solo-Seat"
assert_contains "$out" "note=fastlane-solo-seat" "ABS-322 AC2: the Solo-Seat spawn is marked dev+scoped-tests+self-review"
cleanup_env

# Control (AC4): a normal-lane ticket routes to the plain dev role, no fastlane mark.
new_env
N=$(tracker create --type ticket --title "normal story" --role be-developer | awk '{print $NF}')
_abs322_walk "$N" "Ready for Development"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$N role=be-developer to=Ready for Development" "ABS-322 AC4: normal-lane implementer is unchanged"
assert_not_contains "$out" "note=fastlane-solo-seat" "ABS-322 AC4: normal-lane spawn carries no fastlane Solo-Seat mark"
cleanup_env

# --- AC3: In Review is the single COMBINED review/test gate ------------------
new_env
F=$(tracker create --type ticket --title "fastlane gate" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "In Review"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$F role=system-architect to=In Review" "ABS-322 AC3: fastlane In Review spawns the single combined gate"
assert_contains "$out" "note=fastlane-combined-gate" "ABS-322 AC3: the gate is marked review+scoped-tests (one gate)"
cleanup_env

# Control (AC4): normal-lane In Review is the plain architect review, no fastlane mark.
new_env
N=$(tracker create --type ticket --title "normal gate" --role be-developer | awk '{print $NF}')
_abs322_walk "$N" "In Review"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$N role=system-architect to=In Review" "ABS-322 AC4: normal-lane In Review unchanged"
assert_not_contains "$out" "note=fastlane-combined-gate" "ABS-322 AC4: normal-lane gate carries no fastlane mark"
cleanup_env

# --- AC1/AC3: the QAS station (In Test) is folded into the combined gate ------
new_env
F=$(tracker create --type ticket --title "fastlane qas-fold" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "In Test"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-COLLAPSE ticket=$F role=- to=In Test note=target=Design Test" "ABS-322 AC1: fastlane In Test is folded forward, not spawned as a separate QAS seat"
assert_not_contains "$out" "SPAWN ticket=$F role=qas" "ABS-322 AC1: no separate QAS spawn for a fastlane ticket"
cleanup_env

# Control (AC4): a normal-lane ticket still runs the QAS gate at In Test.
new_env
N=$(tracker create --type ticket --title "normal qas" --role be-developer | awk '{print $NF}')
_abs322_walk "$N" "In Test"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$N role=qas to=In Test" "ABS-322 AC4: normal-lane In Test still spawns QAS"
assert_not_contains "$out" "FASTLANE-COLLAPSE ticket=$N" "ABS-322 AC4: normal-lane ticket is never fastlane-collapsed"
cleanup_env

# --- AC3/AC5: Story Acceptance folds into the merge-queue (Merging) -----------
new_env
F=$(tracker create --type ticket --title "fastlane merge-enqueue" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "Story Acceptance"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-COLLAPSE ticket=$F role=- to=Story Acceptance note=target=Merging" "ABS-322 AC5: passing fastlane work is enqueued onto the merge-queue (Merging)"
assert_not_contains "$out" "SPAWN ticket=$F role=po-agent to=Story Acceptance" "ABS-322 AC3: no synchronous PO seat in the collapsed chain (deferred to ABS-323)"
# AC5: the collapse ENQUEUES onto the merge-queue — it never itself merges or mints a token.
assert_not_contains "$out" "MERGE-TOKEN" "ABS-322 AC5: the collapse issues no merge token"
cleanup_env

# --- Kill-switch: ORCH_FASTLANE_COLLAPSE=0 restores the full v3 chain ---------
new_env
F=$(tracker create --type ticket --title "fastlane knob-off" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "In Test"
out=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_FASTLANE_COLLAPSE=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$F role=qas to=In Test" "ABS-322: knob=0 restores the full chain (QAS runs for a fastlane ticket)"
assert_not_contains "$out" "FASTLANE-COLLAPSE ticket=$F" "ABS-322: knob=0 emits no FASTLANE-COLLAPSE"
cleanup_env

# =============================================================================
# AC2 & AC3 at the PACKET seam (iter-2, architect bounce B1/B2/B3): assert the
# Solo-Seat / combined-gate directive actually REACHES the seat's stdin packet —
# not just the intent-SPAWN run.log line where it used to dead-end. The stub
# spawn appends its drained packet to STUB_PACKET_COPY, so a LIVE spawn lets us
# inspect exactly what the seat received. `seat_note` is threaded do_spawn_action
# -> live_spawn -> attempt_spawn -> build_packet and rendered as a `seat_note:`
# header line + a `seat_note_directive:` telling the seat to run scoped tests.
# =============================================================================

# --- AC2: the Solo-Seat packet carries the dev+scoped-tests+self-review directive
new_env
PKT="$TEST_DIR/pkt-solo.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
F=$(tracker create --type ticket --title "fastlane solo packet" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "Ready for Development"
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
pkt="$(cat "$PKT")"
assert_contains "$pkt" "seat_note: fastlane-solo-seat:dev+scoped-tests+self-review" "ABS-322 AC2: the Solo-Seat directive REACHES the seat packet (not just the run.log)"
assert_contains "$pkt" "run the ticket-scoped tests" "ABS-322 AC2/B2: the packet instructs the Solo-Seat to actually run scoped tests + self-review"
unset STUB_PACKET_COPY
cleanup_env

# Control (AC4): a normal-lane implementer packet carries NO seat_note at all.
new_env
PKT="$TEST_DIR/pkt-normal.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
N=$(tracker create --type ticket --title "normal solo packet" --role be-developer | awk '{print $NF}')
_abs322_walk "$N" "Ready for Development"
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$PKT")" "seat_note:" "ABS-322 AC4: normal-lane packet carries no seat_note (byte-unchanged header)"
unset STUB_PACKET_COPY
cleanup_env

# --- AC3: the combined-gate reviewer packet is told to RUN scoped tests --------
new_env
PKT="$TEST_DIR/pkt-gate.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
F=$(tracker create --type ticket --title "fastlane gate packet" --role be-developer --lane fastlane | awk '{print $NF}')
_abs322_walk "$F" "In Review"
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
pkt="$(cat "$PKT")"
assert_contains "$pkt" "seat_note: fastlane-combined-gate:review+scoped-tests" "ABS-322 AC3: the combined-gate directive REACHES the reviewer packet"
assert_contains "$pkt" "the tests must actually execute here before the ticket enters the merge-queue" "ABS-322 AC3/B2: the combined gate is instructed to run scoped tests (one gate replaces QAS+review)"
unset STUB_PACKET_COPY
cleanup_env

# Control (AC4): a normal-lane In Review reviewer packet carries no seat_note.
new_env
PKT="$TEST_DIR/pkt-gate-normal.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
N=$(tracker create --type ticket --title "normal gate packet" --role be-developer | awk '{print $NF}')
_abs322_walk "$N" "In Review"
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$PKT")" "seat_note:" "ABS-322 AC4: normal-lane In Review packet carries no seat_note"
unset STUB_PACKET_COPY
cleanup_env
