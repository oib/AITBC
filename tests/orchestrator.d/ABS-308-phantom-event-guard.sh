# =============================================================================
# ABS-308 — phantom-event guard: no oscillating from_status / no-op spawn loop
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh. In scope:
# assert_*, REPO_ROOT / ORCH / TRACKER, PASS/FAIL/TOTAL.
#
# A resting ticket can re-surface from the adapter's events-snapshot diff as a
# bogus status-change whose `from` oscillates over the ticket's PAST statuses
# while its REAL status never moved (snapshot drift: two runners sharing
# JIRA_TRACKER_STATE, or a lagging JQL sweep). Each phantom used to spawn a paid
# no-op seat and stamp an oscillating from_status into the packet (consumer
# BUSCH-54: 17 po-agent spawns in 24h on one resting Backlog story). The runner
# now cross-checks a non-creation event against the ticket's ACTUAL last recorded
# transition and drops it when no real transition landed in `to`.
#
# Driven at the process_events() level in an isolated subshell (fresh budget /
# globals), exactly the layer the phantom enters.
# =============================================================================

echo -e "\n${CYAN}ABS-308 — phantom events are dropped; real events still dispatch${NC}"

# Run one process_events scenario in a clean orchestrator process. Args: the raw
# event line(s), plus env overrides. Echoes the intent stream + a runlog summary.
_abs308="$(bash -c '
    set -u
    REPO_ROOT="'"$REPO_ROOT"'"; TRACKER="'"$TRACKER"'"
    export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml" TRACKER_CMD="$TRACKER"
    TD="$(mktemp -d /tmp/abs308-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TD/tickets"; mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
    export ORCH_STATE_DIR="$TD/state"; mkdir -p "$ORCH_STATE_DIR"
    export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
    export ORCH_REQUIRE_START_LABEL=0
    source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
    set +o pipefail; MODE=dry-run
    tracker() { bash "$TRACKER" "$@"; }
    X=$(tracker create --type ticket --title resting | awk "{print \$NF}")   # rests in Backlog

    # (1) PHANTOM into the current status, guard ON -> dropped, no spawn.
    SEEN_EVENTS=""; out=$(process_events "{ticket_id: $X, from: In Review, to: Backlog, at: 2026-01-01T00:00:00Z}")
    echo "P1_SPAWN=$(printf %s "$out" | grep -c "INTENT SPAWN")"
    echo "P1_PHANTOM=$(grep -c SKIP-PHANTOM-EVENT "$ORCH_RUN_LOG")"

    # (2) Same PHANTOM, guard OFF -> reaches dispatch (todays behaviour).
    SEEN_EVENTS=""; out=$(ORCH_PHANTOM_EVENT_GUARD=0 process_events "{ticket_id: $X, from: Story Acceptance, to: Backlog, at: 2026-01-01T00:00:01Z}")
    # It reaches the spawn path (po-agent); the exact terminal intent depends on
    # budget, so assert it did NOT get phantom-skipped and DID try to act.
    echo "P2_DISPATCHED=$(printf %s "$out" | grep -Ec "INTENT (SPAWN|SKIP-BUDGET|SKIP-DRAIN-INTAKE|DEFER)")"

    # (3) A REAL transition still dispatches (no false drop), guard ON.
    tracker transition "$X" "Ready for Development" --actor po --reason go >/dev/null 2>&1
    SEEN_EVENTS=""; out=$(process_events "{ticket_id: $X, from: Backlog, to: Ready for Development, at: 2026-01-01T00:00:02Z}")
    echo "P3_DISPATCHED=$(printf %s "$out" | grep -Ec "INTENT (SPAWN|SKIP-BUDGET|SKIP-DRAIN-INTAKE|DEFER)")"
    echo "P3_PHANTOM_DELTA=$(grep -c SKIP-PHANTOM-EVENT "$ORCH_RUN_LOG")"

    # (4) Collapsed MULTI-STEP: net event {from: In Progress, to: In Review} whose
    # `to` matches the real last transition still dispatches (not a false drop).
    tracker transition "$X" "In Progress" --actor be-developer --reason start >/dev/null 2>&1
    tracker transition "$X" "In Review" --actor be-developer --reason handoff >/dev/null 2>&1
    SEEN_EVENTS=""; out=$(process_events "{ticket_id: $X, from: In Progress, to: In Review, at: 2026-01-01T00:00:03Z}")
    echo "P4_DISPATCHED=$(printf %s "$out" | grep -Ec "INTENT (SPAWN|SKIP-BUDGET|SKIP-DRAIN-INTAKE|DEFER)")"
    rm -rf "$TD"
')"

assert_contains "$_abs308" "P1_SPAWN=0"       "ABS-308 AC1: a phantom event into a resting status spawns NO seat"
assert_contains "$_abs308" "P1_PHANTOM=1"     "ABS-308 AC1: the phantom event is logged as SKIP-PHANTOM-EVENT"
assert_contains "$_abs308" "P2_DISPATCHED=1"  "ABS-308: knob=0 restores today's behaviour (phantom is dispatched)"
assert_contains "$_abs308" "P3_DISPATCHED=1"  "ABS-308 AC2: a REAL transition still dispatches (no false drop)"
assert_contains "$_abs308" "P3_PHANTOM_DELTA=1" "ABS-308 AC2: the real transition is not counted as a phantom"
assert_contains "$_abs308" "P4_DISPATCHED=1"  "ABS-308: a collapsed multi-step event whose to matches the real last transition dispatches"

unset _abs308
