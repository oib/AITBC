# =============================================================================
# ABS-518 — EPIC-REVIEW-WAIT: children of a PRE-FILLED epic rest until the
#           epic clears its review stations (epic ABS-514, rule-ledger wave).
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (ABS-392 incident, 2026-07-18 improvement proposal)
# A pre-filled epic (PO decomposes by hand, children set Ready for
# Development, epic returned to Backlog) dispatched its children BEFORE the
# epic's own Ticket Review + Architecture Review ran. STATION-GUARD then
# routed the epic through the skipped stations retroactively, and both gates
# degraded to rubber-stamps ("DoR gate ran late … noted for the record only").
#
# WHAT ABS-518 ADDS
#   epic_review_owed() + the EPIC-REVIEW-WAIT hold in do_spawn_action():
#   a child of a pre-filled epic (has children, never visited Grooming) rests
#   at its entry status until the epic has visited "Architecture Review" —
#   the station that releases stories on the decomposed path. Kill-switch:
#   ORCH_EPIC_REVIEW_GATING=0. Decomposed epics (Grooming visited) are
#   untouched: the BSA path already orders their children.
# =============================================================================

echo -e "\n${CYAN}=== ABS-518 epic-review-wait (pre-filled epic child hold) ===${NC}\n"

# Helper: walk an epic through the v3 epic chain up to (and including) $2.
# TOLERANT walk (|| true): after an orch cycle the runner may already have
# moved the epic (Backlog -> Stories In Flight -> STATION-GUARD redirect), so
# transitions that are invalid from the CURRENT status are skipped — the walk
# picks up at the first station reachable from wherever the epic now rests.
# Never returns non-zero: the include is sourced under the harness's set -e
# (an aborting include is an ABS-370 suite-integrity failure).
_abs518_epic_to() {
    local e="$1" upto="$2" s
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review"; do
        tracker transition "$e" "$s" --actor orchestrator --reason "setup" >/dev/null 2>&1 || true
        [ "$s" = "$upto" ] && return 0
    done
    return 0
}

# --- AC1: pre-filled epic still owes reviews -> child rests (EPIC-REVIEW-WAIT) ---

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_EPIC_REVIEW_GATING=1

E=$(tracker create --type epic --title "ABS-518 pre-filled epic" --label orchestrator-ready)
C=$(tracker create --type ticket --title "ABS-518 pre-filled child" --parent "$E")
# Pre-filled shape: the child is directly dispatchable, the epic never visited
# Grooming (nothing was decomposed by the BSA seat) and owes its reviews.
tracker transition "$C" "Ready for Development" --actor po-agent --reason "pre-filled decomposition" >/dev/null
baseline

out1=$(orch --live --once 2>/dev/null)
assert_contains "$out1" "INTENT EPIC-REVIEW-WAIT ticket=$C" \
    "ABS-518 AC1: child of review-owing pre-filled epic rests (EPIC-REVIEW-WAIT)"
assert_not_contains "$out1" "INTENT SPAWN ticket=$C" \
    "ABS-518 AC1: no implementer spawn for the held child"
assert_eq "$(tracker get "$C" | sed -n 's/^status: //p' | head -1)" "Ready for Development" \
    "ABS-518 AC1: held child rests at its entry status (no marker, no crash)"

# --- AC2: epic clears Architecture Review -> child dispatches ------------------

_abs518_epic_to "$E" "Architecture Review"

out2=$(orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT EPIC-REVIEW-WAIT ticket=$C" \
    "ABS-518 AC2: no hold once the epic has visited Architecture Review"
assert_contains "$out2" "INTENT SPAWN ticket=$C" \
    "ABS-518 AC2: child dispatches after the epic cleared its reviews"

cleanup_env

# --- AC3: kill-switch off -> no hold (pre-ABS-518 behaviour) -------------------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_EPIC_REVIEW_GATING=0

E=$(tracker create --type epic --title "ABS-518 killswitch epic" --label orchestrator-ready)
C=$(tracker create --type ticket --title "ABS-518 killswitch child" --parent "$E")
tracker transition "$C" "Ready for Development" --actor po-agent --reason "pre-filled decomposition" >/dev/null
baseline

out3=$(orch --live --once 2>/dev/null)
assert_not_contains "$out3" "INTENT EPIC-REVIEW-WAIT ticket=$C" \
    "ABS-518 AC3: ORCH_EPIC_REVIEW_GATING=0 restores pre-ABS-518 dispatch"
assert_contains "$out3" "INTENT SPAWN ticket=$C" \
    "ABS-518 AC3: child spawns with the gate off"

cleanup_env

# --- AC4: DECOMPOSED epic (Grooming visited) -> children not held --------------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_EPIC_REVIEW_GATING=1

E=$(tracker create --type epic --title "ABS-518 decomposed epic")
# Decomposed shape: the epic went through Grooming (BSA created the children)
# but — mid-pipeline — has not reached Architecture Review yet. Such children
# are ordered by the epic pipeline itself; the hold must NOT fire (the clamp
# would otherwise re-introduce the ABS-136/ABS-247 forgiveness regression).
_abs518_epic_to "$E" "Grooming"
C=$(tracker create --type ticket --title "ABS-518 decomposed child" --parent "$E")
tracker transition "$C" "Ready for Development" --actor bsa --reason "decomposition" >/dev/null
baseline

out4=$(orch --live --once 2>/dev/null)
assert_not_contains "$out4" "INTENT EPIC-REVIEW-WAIT ticket=$C" \
    "ABS-518 AC4: decomposed-epic child is not held"
assert_contains "$out4" "INTENT SPAWN ticket=$C" \
    "ABS-518 AC4: decomposed-epic child dispatches normally"

cleanup_env

# --- AC5: v1-plain CONTAINER epic (no label, never in pipeline) -> no hold -----
# The ABS-180 packet fixture shape: epic as a grouping shell, child transitioned
# straight to Ready for Development. The v1 happy path must dispatch unchanged.

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_EPIC_REVIEW_GATING=1

E=$(tracker create --type epic --title "ABS-518 container epic")
C=$(tracker create --type ticket --title "ABS-518 container child" --parent "$E" --role be-developer)
tracker transition "$C" "Ready for Development" --actor po --reason "v1 direct dispatch" >/dev/null
baseline

out5=$(orch --live --once 2>/dev/null)
assert_not_contains "$out5" "INTENT EPIC-REVIEW-WAIT ticket=$C" \
    "ABS-518 AC5: v1-plain container-epic child is not held"
assert_contains "$out5" "INTENT SPAWN ticket=$C" \
    "ABS-518 AC5: v1 happy path dispatches unchanged"

cleanup_env
