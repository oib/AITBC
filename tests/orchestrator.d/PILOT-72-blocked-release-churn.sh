# =============================================================================
# PILOT-72 — Blocked-auto-release <-> Re-Block churn loop is bounded.
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live on PILOT-43, night 2026-07-25/26)
# The ABS-296 idempotency marker was anchored to the CURRENT Blocked entry. A
# seat that re-blocked a released ticket citing 'facts unchanged' created a NEW
# Blocked entry, the old marker no longer masked it, and the auto-release fired
# again — a structurally unbounded loop (13 cycles, 12 spawns, $9.53, zero
# progress). The only accidental brake was parking to Backlog (a resume-origin
# the sweep excludes).
#
# WHAT PILOT-72 CHANGES
#   AC1/AC2: idempotency hangs on the CAUSE — a fact fingerprint of each
#            dependency's current status — not the Blocked entry. A Re-Block with
#            unchanged dependency facts does NOT re-release; a demonstrable change
#            (a dependency status move) re-enables exactly one further release.
#   AC3:     a per-ticket churn cap (ORCH_BLOCKED_RELEASE_CHURN_CAP) escalates as
#            a visible Attention-Event instead of releasing forever.
#   AC4/AC5: falsification + cost — a no-change re-block yields exactly ONE
#            release (one spawn) per fact state.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-72 blocked-release churn bound ===${NC}\n"

# Local helpers (each orchestrator.d include runs in its own subshell, so the
# ABS-296 helpers are not in scope here).

# Advance a ticket along the standard story chain to Done (terminal, always
# dependency-satisfying regardless of the merge probe).
_p72_to_done() {
    local t="$1"
    local s
    for s in "Ready for Development" "In Progress" "In Review" "In Test" \
             "Ready for Human Acceptance" "Ready for Merge" "Done"; do
        tracker transition "$t" "$s" --actor orchestrator --reason "setup" >/dev/null
    done
}

# Drive a ticket to 'Docs' (post-merge, ABS-266): dependency-satisfying without
# being terminal, so its status can still change to Done (a fact change).
_p72_to_docs() {
    local t="$1"
    local s
    for s in "Ready for Development" "In Progress" "In Review" "In Test" \
             "Design Test" "Story Acceptance" "Merging" "Docs"; do
        tracker transition "$t" "$s" --actor orchestrator --reason "setup" >/dev/null
    done
}

# Park a ticket in Blocked from In Progress, naming the dep in the reason (so the
# ABS-296 blocked_reason_names_dep gate approves the release) + BLOCKED-FROM marker.
_p72_park_blocked() {
    local t="$1" dep="$2"
    tracker transition "$t" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "Blocked" --actor orchestrator \
        --reason "blocked: depends_on $dep not yet satisfied (PILOT-72 test)" >/dev/null
    tracker comment "$t" --kind gate-results --actor orchestrator \
        --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
}

# A seat re-blocks a released ticket (In Progress -> Blocked) citing 'facts
# unchanged', plus a fresh BLOCKED-FROM marker for the new entry.
_p72_reblock() {
    local t="$1" dep="$2"
    tracker transition "$t" "Blocked" --actor orchestrator \
        --reason "re-block: no change, depends_on $dep still has nothing to arm (PILOT-72 test)" >/dev/null
    tracker comment "$t" --kind gate-results --actor orchestrator \
        --body "BLOCKED-FROM=In Progress (orchestrator): new blocked entry." >/dev/null
}

_p72_status() { tracker get "$1" | sed -n 's/^status: //p' | head -1; }

# --- AC4 / AC5: no-change re-block => exactly ONE release per fact state -----------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP=$(tracker create --type ticket --title "PILOT-72 dep")
T=$(tracker create --type ticket --title "PILOT-72 churn story")
tracker link "$T" "$DEP" depends-on >/dev/null
_p72_park_blocked "$T" "$DEP"
_p72_to_done "$DEP"
baseline

# Sweep 1: dependency facts satisfied -> release fires (the ONE legitimate release).
o1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$o1" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "PILOT-72 AC4: first release fires when all depends_on satisfied"
assert_eq "$(_p72_status "$T")" "In Progress" \
    "PILOT-72 AC4: released to BLOCKED-FROM origin (In Progress)"

# The seat re-blocks with 'no change' — a NEW Blocked entry. Under ABS-296 this
# re-armed the release; PILOT-72's cause-keyed idempotency must suppress it.
_p72_reblock "$T" "$DEP"
o2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$o2" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "PILOT-72 AC1/AC4: no re-release after a no-change Re-Block (fact fingerprint unchanged)"
assert_eq "$(_p72_status "$T")" "Blocked" \
    "PILOT-72 AC2: ticket stays Blocked while dependency facts are unchanged"

# A further sweep (still Blocked, still no change) also does not release.
o3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$o3" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "PILOT-72: idempotency persists across sweeps for the same fact state"

# AC5 cost-assert: across every sweep for this single fact state, exactly ONE release.
rel_total=$(printf '%s\n%s\n%s\n' "$o1" "$o2" "$o3" | grep -cF "INTENT BLOCKED-AUTO-RELEASE ticket=$T")
assert_eq "$rel_total" "1" \
    "PILOT-72 AC5: exactly one release (one spawn) per fact state — no churn"

cleanup_env

# --- AC2: a demonstrable dependency change re-enables exactly one more release ----

new_env
# ORCH_MAX_CONCURRENT=0: this fixture uses a dependency resting in 'Docs' (an
# active, spawnable status) to get a satisfied fact state that can still CHANGE
# (Docs -> Done). Capping concurrency to 0 keeps the dependency inert during the
# live sweeps (no independent tech-writer spawn on it) so we observe the
# auto-release sweep in isolation; the release itself is a direct transition and
# fires regardless of the cap.
export ORCH_MAX_CONCURRENT=0
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1
export ORCH_MAIN_REMOTE=none   # deterministic: 'Docs' satisfies via ABS-266, not a merge-probe hit

DEP2=$(tracker create --type ticket --title "PILOT-72 dep (docs->done)")
T2=$(tracker create --type ticket --title "PILOT-72 progress-predicate story")
tracker link "$T2" "$DEP2" depends-on >/dev/null
_p72_park_blocked "$T2" "$DEP2"
_p72_to_docs "$DEP2"           # fact state 1: DEP2 = Docs (post-merge, satisfied)
baseline

oa=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$oa" "INTENT BLOCKED-AUTO-RELEASE ticket=$T2" \
    "PILOT-72 AC2: release fires at fact state 1 (dep in Docs)"

_p72_reblock "$T2" "$DEP2"
ob=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$ob" "INTENT BLOCKED-AUTO-RELEASE ticket=$T2" \
    "PILOT-72 AC2: no re-release while the dependency fact (Docs) is unchanged"

# Demonstrable change: the dependency advances Docs -> Done -> new fingerprint.
tracker transition "$DEP2" "Done" --actor orchestrator --reason "dep completed" >/dev/null
oc=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$oc" "INTENT BLOCKED-AUTO-RELEASE ticket=$T2" \
    "PILOT-72 AC2: a dependency status change (Docs -> Done) re-enables one release"
assert_eq "$(_p72_status "$T2")" "In Progress" \
    "PILOT-72 AC2: re-released to origin after the demonstrable change"

unset ORCH_MAIN_REMOTE
cleanup_env

# --- AC3: churn cap escalates as a visible Attention-Event instead of releasing ---

new_env
export ORCH_MAX_CONCURRENT=0   # keep the 'Docs' dependency inert during sweeps (see AC2 note)
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1
export ORCH_MAIN_REMOTE=none
export ORCH_BLOCKED_RELEASE_CHURN_CAP=1   # escalate after a single release episode

DEP3=$(tracker create --type ticket --title "PILOT-72 dep (cap)")
T3=$(tracker create --type ticket --title "PILOT-72 churn-cap story")
tracker link "$T3" "$DEP3" depends-on >/dev/null
_p72_park_blocked "$T3" "$DEP3"
_p72_to_docs "$DEP3"           # fact state 1
baseline

# Episode 1 (release count 0 < cap 1): release fires, marker #1 recorded.
oc1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$oc1" "INTENT BLOCKED-AUTO-RELEASE ticket=$T3" \
    "PILOT-72 AC3: first episode releases (below the cap)"

# Re-block, then move the dependency (Docs -> Done) so the fingerprint CHANGES —
# this gets past cause-keyed idempotency to exercise the cap itself.
_p72_reblock "$T3" "$DEP3"
tracker transition "$DEP3" "Done" --actor orchestrator --reason "dep completed" >/dev/null

oc2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$oc2" "INTENT BLOCKED-AUTO-RELEASE ticket=$T3" \
    "PILOT-72 AC3: once the cap is reached the sweep stops releasing"
assert_contains "$oc2" "INTENT BLOCKED-RELEASE-CHURN-CAP ticket=$T3" \
    "PILOT-72 AC3: churn cap escalates instead of releasing"
assert_contains "$oc2" "INTENT NOTIFY ticket=$T3" \
    "PILOT-72 AC3: escalation is a visible Attention-Event (NOTIFY), not silent"
assert_eq "$(_p72_status "$T3")" "Blocked" \
    "PILOT-72 AC3: the ticket stays Blocked at the cap (operator action required)"

unset ORCH_MAIN_REMOTE ORCH_BLOCKED_RELEASE_CHURN_CAP
cleanup_env
