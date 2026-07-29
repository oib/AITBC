# =============================================================================
# PILOT-37 (ABS-495 twin) — a dependency-wait is a MACHINE state: it rests in
#   Backlog, never Blocked, and never surfaces as human attention.
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (operator retro point #1, v3 pilot #2, 2026-07-20)
# A ticket whose only impediment is an unfinished depends_on was moved to Blocked
# and thereby appeared in the Mission-Control attention inbox as "Item is Blocked
# — investigate blocker". The human can do nothing there; the only cure is the
# predecessor finishing. The flow itself is healthy (depends-gating withholds
# dispatch); wrong is only the STATE and its visibility class.
#
# WHAT PILOT-37 ADDS
#   depends_unmet() now also gates the "Backlog" resting status: a Backlog ticket
#   with an unfinished depends_on is HELD in Backlog (DEPENDS-WAIT), never triaged
#   or dispatched, and never transitioned to Blocked. Once every dependency is
#   satisfied the reconcile sweep re-derives the dispatch automatically.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-37 dependency-wait stays in Backlog (never Blocked) ===${NC}\n"

# --- AC1: unfinished depends_on holds the ticket in Backlog (no dispatch, no Blocked) ---

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_DEPENDS_GATING=1
# PILOT-19: depends_unmet probes the blocker's merge state; a bogus remote makes
# the forge-less probe fail offline-fast (NONE = not merged = waits) instead of
# reaching for the real origin over the network.
export ORCH_MAIN_REMOTE=none

DEP=$(tracker create --type ticket --title "PILOT-37 dependency" --role be-developer)
T=$(tracker create --type ticket --title "PILOT-37 dependent" --role be-developer --label orchestrator-ready)
tracker update "$T" depends_on "[$DEP]" >/dev/null
baseline

out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out1" "INTENT DEPENDS-WAIT ticket=$T" \
    "PILOT-37 AC1: Backlog ticket with unfinished depends_on rests (DEPENDS-WAIT)"
assert_not_contains "$out1" "INTENT SPAWN ticket=$T" \
    "PILOT-37 AC1: not dispatched while the dependency is unfinished"
assert_not_contains "$out1" "ticket=$T to=Blocked" \
    "PILOT-37 AC1: a dependency-wait never transitions to Blocked"
assert_eq "$(tracker get "$T" | sed -n 's/^status: //p' | head -1)" "Backlog" \
    "PILOT-37 AC1: ticket stays in Backlog"

# Dependency reaches Done → the ticket must become dispatchable next sweep.
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$DEP" "$s" --actor orchestrator --reason setup >/dev/null
done

out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out2" "INTENT DEPENDS-WAIT ticket=$T" \
    "PILOT-37 AC1: dependency Done → the ticket no longer waits"
assert_contains "$out2" "INTENT SPAWN ticket=$T" \
    "PILOT-37 AC1: dependency Done → the ticket becomes dispatchable"

cleanup_env
