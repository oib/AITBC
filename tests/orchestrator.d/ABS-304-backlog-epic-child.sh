# =============================================================================
# ABS-304 — Backlog PO sweep does not spawn on epic-pipeline children
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env / baseline, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER.
#
# A labelled Backlog child of an epic still in the epic pipeline BEFORE
# "Stories In Flight" (PO Triage..Architecture Review) is architect-released —
# the Backlog -> Ready for Development edge belongs to the Architecture Review
# seat, not the PO sweep. A po-agent spawned there can only score-and-park: a
# guaranteed HANDOFF-NOMOVE, one paid no-op per child per run (ABS-279 had 9).
# The runner now suppresses that spawn (SKIP-EPIC-CHILD), throttled once per
# ticket per run. Parentless Backlog tickets and children of an epic at
# Stories In Flight or later are UNCHANGED.
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-225 include).
tracker() { bash "$TRACKER" "$@"; }

# Drive an epic to a given epic-pipeline status via the legal hop chain.
_abs304_epic_to() {
    local epic="$1" target="$2" s
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Stories In Flight"; do
        tracker transition "$epic" "$s" --actor orchestrator --reason "abs304 setup" >/dev/null 2>&1
        [ "$s" = "$target" ] && break
    done
}

echo -e "\n${CYAN}ABS-304 — epic-pipeline Backlog children are not PO-swept${NC}"

# --- Scenario: one reconcile sweep over a mixed Backlog ------------------------
new_env
E=$(tracker create --type epic --title "ABS-304 epic in pipeline" --label orchestrator-ready | awk '{print $NF}')
_abs304_epic_to "$E" "Architecture Review"
C=$(tracker create --type ticket --title "epic child" --parent "$E" --label orchestrator-ready | awk '{print $NF}')
P=$(tracker create --type ticket --title "parentless labelled" --label orchestrator-ready | awk '{print $NF}')
E2=$(tracker create --type epic --title "ABS-304 epic in flight" --label orchestrator-ready | awk '{print $NF}')
_abs304_epic_to "$E2" "Stories In Flight"
C2=$(tracker create --type ticket --title "in-flight child" --parent "$E2" --label orchestrator-ready | awk '{print $NF}')

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)

# AC: the epic child is skipped, and the intent names child + parent.
assert_contains "$out" "SKIP-EPIC-CHILD ticket=$C" "ABS-304: labelled epic-pipeline child is skipped (no po-agent spawn)"
assert_contains "$out" "parent=$E" "ABS-304: the SKIP-EPIC-CHILD intent names the parent epic"
assert_not_contains "$out" "SPAWN ticket=$C role=po-agent" "ABS-304: no po-agent is spawned on the epic child"
# AC: no no-move is recorded for the child (nothing spawned -> nothing to bounce).
assert_not_contains "$out" "NOMOVE ticket=$C" "ABS-304: no HANDOFF-NOMOVE charged for the skipped child"
# Control (must still spawn): a labelled PARENTLESS Backlog ticket.
assert_contains "$out" "SPAWN ticket=$P role=po-agent" "ABS-304 control: parentless labelled Backlog ticket still spawns po-agent"
# Control (must still spawn): a child whose epic is at Stories In Flight.
assert_contains "$out" "SPAWN ticket=$C2 role=po-agent" "ABS-304 control: child of an epic at Stories In Flight still spawns po-agent"

# Off-switch: ORCH_BACKLOG_SKIP_EPIC_CHILDREN=0 reproduces today's behaviour.
out_off=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_BACKLOG_SKIP_EPIC_CHILDREN=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out_off" "SPAWN ticket=$C role=po-agent" "ABS-304: knob=0 restores today's behaviour (epic child IS spawned)"
assert_not_contains "$out_off" "SKIP-EPIC-CHILD ticket=$C" "ABS-304: knob=0 emits no SKIP-EPIC-CHILD"
cleanup_env

# --- Throttle: at most one SKIP-EPIC-CHILD intent per ticket per run -----------
# Two dispatch sweeps within ONE process (one run): the first emits the intent,
# the second is throttled to a runlog line only. Driven at the dispatch level so
# both sweeps share the in-process SKIPPED_EPIC_CHILD marker.
_abs304_throttle="$(bash -c '
    set -u
    REPO_ROOT="'"$REPO_ROOT"'"; TRACKER="'"$TRACKER"'"
    export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml" TRACKER_CMD="$TRACKER"
    TD="$(mktemp -d /tmp/abs304-thr-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TD/tickets"; mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
    export ORCH_STATE_DIR="$TD/state"; mkdir -p "$ORCH_STATE_DIR"
    export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
    export ORCH_REQUIRE_START_LABEL=1 ORCH_START_LABEL=orchestrator-ready ORCH_BACKLOG_SKIP_EPIC_CHILDREN=1
    source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
    set +o pipefail
    MODE=dry-run
    tracker() { bash "$TRACKER" "$@"; }
    E=$(tracker create --type epic --title epic --label orchestrator-ready | awk "{print \$NF}")
    for s in "PO Triage" Grooming Enrichment "Ticket Review" "Architecture Review"; do
        tracker transition "$E" "$s" --actor orchestrator --reason x >/dev/null 2>&1
    done
    C=$(tracker create --type ticket --title child --parent "$E" --label orchestrator-ready | awk "{print \$NF}")
    # Both dispatches must run in THIS shell (not a $(...) subshell) so the
    # in-process SKIPPED_EPIC_CHILD throttle marker persists between them.
    dispatch "$C" Backlog > "$TD/d1.out"
    dispatch "$C" Backlog > "$TD/d2.out"
    n=$(cat "$TD/d1.out" "$TD/d2.out" | grep -c "INTENT SKIP-EPIC-CHILD" || true)
    thr=$(grep "INTENT-SKIP-EPIC-CHILD" "$ORCH_RUN_LOG" | grep -c "throttled" || true)
    echo "intents=$n throttled=$thr"
    rm -rf "$TD"
')"
assert_contains "$_abs304_throttle" "intents=1" "ABS-304: the SKIP-EPIC-CHILD intent is emitted exactly once per ticket per run"
assert_contains "$_abs304_throttle" "throttled=1" "ABS-304: the second sweep is throttled to a runlog line (no re-emit)"

# Regression note: epic_join_rest_complete() (the EPIC-side of this class) is not
# touched — its behaviour is guarded by tests/tooling/test-epic-join-resting.sh.
unset E C P E2 C2 out out_off _abs304_throttle
