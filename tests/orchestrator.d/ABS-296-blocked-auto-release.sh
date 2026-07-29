# =============================================================================
# ABS-296 — Blocked auto-release: dependency-caused Blocked tickets return to
#           their BLOCKED-FROM origin once all depends_on are Done.
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live on ABS-234, 2026-07-13)
# A ticket parked in Blocked purely because of an unmet depends_on held the
# entire Phase-1 tree blocked until an operator released it by hand. The
# depends-gate only catches NEW dispatches; it never looks at tickets already
# resting in Blocked. This story adds a reconcile sweep that re-evaluates
# those Blocked tickets and releases them automatically once all depends_on
# reach Done.
#
# WHAT ABS-296 ADDS
#   1. blocked_auto_release_sweep() in reconcile(): re-evaluates every Blocked
#      ticket with depends_on; releases to its BLOCKED-FROM origin when all
#      deps are Done.
#   2. ORCH_BLOCKED_AUTO_RELEASE knob (default 1; 0 = no auto-release = today's
#      behaviour).
#   3. Audit comment (BLOCKED-AUTO-RELEASED marker) + runlog line on release;
#      idempotent across sweeps (marker-keyed, same anchoring as has_blocked_marker).
#   4. profiles/neutral/adapters/statuses.yaml annotated to document the runner-
#      driven Blocked -> <origin> back-edge (edges already existed; annotation
#      makes the usage explicit).
# =============================================================================

echo -e "\n${CYAN}=== ABS-296 blocked-auto-release ===${NC}\n"

# Helper: advance a ticket along the standard story chain to Done.
# Valid chain: Backlog -> RfD -> InProg -> InReview -> InTest -> RfHA -> RfM -> Done
_abs296_advance_to_done() {
    local t="$1"
    tracker transition "$t" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "In Review"             --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "In Test"               --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "Ready for Human Acceptance" --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "Ready for Merge"       --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "Done"                  --actor orchestrator --reason "dep Done" >/dev/null
}

# Helper: put a ticket in Blocked (from In Progress).
# Valid path: Backlog -> RfD -> InProg -> Blocked
# $1 = ticket id
# $2 = dep_id to name in the transition reason (required for auto-release;
#      omit / empty to simulate a non-dependency park whose reason names no dep).
_abs296_park_blocked() {
    local t="$1" dep_id="${2:-}"
    local reason
    if [ -n "$dep_id" ]; then
        reason="blocked: depends_on $dep_id not yet Done (ABS-296 test)"
    else
        reason="TDM-parked: unresolvable external blocker (not dependency-caused)"
    fi
    tracker transition "$t" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
    tracker transition "$t" "Blocked"               --actor orchestrator \
        --reason "$reason" >/dev/null
    # Post the BLOCKED-FROM marker as record_blocked_from() would (last from = In Progress).
    tracker comment "$t" --kind gate-results --actor orchestrator \
        --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status so TDM (or a human) can resume to origin (ABS-76 / spec §1.3, §3.7)." \
        >/dev/null
}

# --- AC1: dependency-caused Blocked + all deps Done → auto-released to origin ---

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP=$(tracker create --type ticket --title "ABS-296 dep ticket")
T=$(tracker create --type ticket --title "ABS-296 blocked story")
tracker link "$T" "$DEP" depends-on >/dev/null
_abs296_park_blocked "$T" "$DEP"
baseline

# Dep still not Done → no release yet.
out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out1" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "ABS-296 AC2: no release while dependency is not Done"
assert_eq "$(tracker get "$T" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC2: ticket stays Blocked while dep not Done"

# Mark dep Done → next sweep must release T back to In Progress.
_abs296_advance_to_done "$DEP"

out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out2" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "ABS-296 AC1: sweep emits BLOCKED-AUTO-RELEASE intent when all depends_on Done"
new_status=$(tracker get "$T" | sed -n 's/^status: //p' | head -1)
assert_eq "$new_status" "In Progress" \
    "ABS-296 AC1: ticket returns to its BLOCKED-FROM origin (In Progress)"

# AC5: audit comment posted (BLOCKED-AUTO-RELEASED marker).
t_dump=$(tracker get "$T")
assert_contains "$t_dump" "BLOCKED-AUTO-RELEASED=In Progress (orchestrator)" \
    "ABS-296 AC5: BLOCKED-AUTO-RELEASED marker posted on the ticket"

# AC5 idempotency: a further sweep does NOT re-release (T is no longer Blocked).
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out3" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "ABS-296 AC5: no double-release — T left Blocked so sweep skips it"

# PILOT-72 supersedes the old ABS-296 "new Blocked entry re-releases" behaviour.
# A Re-Block whose dependency FACTS are unchanged (DEP still Done) is the exact
# churn loop PILOT-72 fixes: cause-keyed idempotency (fact fingerprint) survives
# the fresh Blocked entry, so the sweep must NOT re-release. See the dedicated
# PILOT-72 fixture for the full progress-predicate + churn-cap coverage.
tracker transition "$T" "Blocked" --actor orchestrator \
    --reason "ABS-296 test: re-enter Blocked; depends_on $DEP still outstanding" >/dev/null
# Post a fresh BLOCKED-FROM marker for this new entry (the runner would do this
# in its TDM-spawn pass, which runs in the same reconcile sweep as auto-release
# but in the per-ticket dispatch path, AFTER blocked_auto_release_sweep).
tracker comment "$T" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): new blocked entry." >/dev/null

out4=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out4" "INTENT BLOCKED-AUTO-RELEASE ticket=$T" \
    "PILOT-72: Re-Block with unchanged dependency facts does NOT re-release (cause-keyed idempotency)"
assert_eq "$(tracker get "$T" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "PILOT-72: ticket stays Blocked on a no-change Re-Block"

cleanup_env

# --- AC3a: no depends_on at all stays Blocked -------------------------------------
# The trivial case: a ticket with no depends_on never satisfies the dep check.

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

NDB=$(tracker create --type ticket --title "ABS-296 non-dep Blocked")
# No depends_on — simulates TDM-parked / escalation-parked / human-parked ticket.
tracker transition "$NDB" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
tracker transition "$NDB" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
tracker transition "$NDB" "Blocked"               --actor orchestrator \
    --reason "TDM-parked: unresolvable external blocker (not dependency-caused)" >/dev/null
tracker comment "$NDB" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
baseline

out_ndb=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_ndb" "INTENT BLOCKED-AUTO-RELEASE ticket=$NDB" \
    "ABS-296 AC3a: non-dependency Blocked entry (no depends_on) stays Blocked"
assert_eq "$(tracker get "$NDB" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC3a: non-dep-blocked ticket still in Blocked after sweep"

cleanup_env

# --- AC3b: escalation-budget loop-breaker park with satisfied deps stays Blocked --
# A ticket parked by escalation_note_stall (ADR-A-0018 §d, "no re-spawn,
# operator action required") must NOT be auto-released even when all depends_on
# are Done.  The loop-breaker reason text never carries a dep id, so
# blocked_reason_names_dep() returns false → fail-closed.

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP_ESC=$(tracker create --type ticket --title "ABS-296 dep-escalation")
T_ESC=$(tracker create --type ticket --title "ABS-296 escalation-parked story")
tracker link "$T_ESC" "$DEP_ESC" depends-on >/dev/null
tracker transition "$T_ESC" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
tracker transition "$T_ESC" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
# Simulate escalation_note_stall (ADR-A-0018 §d) — reason does NOT name the dep id.
tracker transition "$T_ESC" "Blocked" --actor orchestrator \
    --reason "escalation budget of 3 rounds without status progress exhausted; auto-parked, no re-spawn (ADR-A-0018 §d, ABS-199)." \
    >/dev/null
tracker comment "$T_ESC" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
# Mark dep Done — the sweep MUST still not release (the park reason names no dep).
_abs296_advance_to_done "$DEP_ESC"
baseline

out_esc=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_esc" "INTENT BLOCKED-AUTO-RELEASE ticket=$T_ESC" \
    "ABS-296 AC3b: escalation-budget loop-breaker park stays Blocked even when deps Done"
assert_eq "$(tracker get "$T_ESC" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC3b: escalation-parked ticket still in Blocked (ADR-A-0018 §d integrity)"

cleanup_env

# --- AC3c: cross-visit loop-breaker park with satisfied deps stays Blocked --------
# Same as AC3b but for crossvisit_autopark (ADR-A-0018 §c/§e).

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP_CV=$(tracker create --type ticket --title "ABS-296 dep-crossvisit")
T_CV=$(tracker create --type ticket --title "ABS-296 crossvisit-parked story")
tracker link "$T_CV" "$DEP_CV" depends-on >/dev/null
tracker transition "$T_CV" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
tracker transition "$T_CV" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
# Simulate crossvisit_autopark (ADR-A-0018 §c/§e) — reason does NOT name the dep id.
tracker transition "$T_CV" "Blocked" --actor orchestrator \
    --reason "cross-visit same-blocker loop-breaker: 'be-developer' recurred on 'environment-denial' (2x across visits); auto-parked, no re-spawn (ADR-A-0018, ABS-199)." \
    >/dev/null
tracker comment "$T_CV" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
# Mark dep Done — the sweep MUST still not release (the park reason names no dep).
_abs296_advance_to_done "$DEP_CV"
baseline

out_cv=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_cv" "INTENT BLOCKED-AUTO-RELEASE ticket=$T_CV" \
    "ABS-296 AC3c: cross-visit loop-breaker park stays Blocked even when deps Done"
assert_eq "$(tracker get "$T_CV" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC3c: crossvisit-parked ticket still in Blocked (ADR-A-0018 §c/§e integrity)"

cleanup_env

# --- AC3d: generic human/TDM park reason naming no dep stays Blocked --------------
# A ticket with depends_on but parked by a human/TDM with a reason that names no
# dep id (e.g. an external blocker description) must NOT be auto-released.

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP_HUM=$(tracker create --type ticket --title "ABS-296 dep-human")
T_HUM=$(tracker create --type ticket --title "ABS-296 human-parked story")
tracker link "$T_HUM" "$DEP_HUM" depends-on >/dev/null
tracker transition "$T_HUM" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
tracker transition "$T_HUM" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
# Human/TDM park: reason does NOT name the dep id.
tracker transition "$T_HUM" "Blocked" --actor orchestrator \
    --reason "Blocked by external vendor API outage; awaiting resolution from third party." \
    >/dev/null
tracker comment "$T_HUM" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
# Mark dep Done — must not release (park reason names no dep id).
_abs296_advance_to_done "$DEP_HUM"
baseline

out_hum=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_hum" "INTENT BLOCKED-AUTO-RELEASE ticket=$T_HUM" \
    "ABS-296 AC3d: human/TDM park (reason names no dep id) stays Blocked even when deps Done"
assert_eq "$(tracker get "$T_HUM" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC3d: human-parked ticket still in Blocked after sweep"

cleanup_env

# --- AC4: ORCH_BLOCKED_AUTO_RELEASE=0 reproduces today's behaviour (no release) ---

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=0
export ORCH_DEPENDS_GATING=1

DEP2=$(tracker create --type ticket --title "ABS-296 dep2")
T2=$(tracker create --type ticket --title "ABS-296 knob-off story")
tracker link "$T2" "$DEP2" depends-on >/dev/null
_abs296_park_blocked "$T2" "$DEP2"
_abs296_advance_to_done "$DEP2"
baseline

out_off=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_off" "INTENT BLOCKED-AUTO-RELEASE ticket=$T2" \
    "ABS-296 AC4: ORCH_BLOCKED_AUTO_RELEASE=0 suppresses auto-release (today's behaviour)"
assert_eq "$(tracker get "$T2" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC4: ticket stays Blocked when ORCH_BLOCKED_AUTO_RELEASE=0"

cleanup_env

# --- AC2 (no release while any dep not Done) — multi-dep variant ---------------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DA=$(tracker create --type ticket --title "ABS-296 dep-A")
DB=$(tracker create --type ticket --title "ABS-296 dep-B")
TM=$(tracker create --type ticket --title "ABS-296 multi-dep story")
tracker link "$TM" "$DA" depends-on >/dev/null
tracker link "$TM" "$DB" depends-on >/dev/null
# Reason names DA (the first dep discovered); naming any one dep is sufficient.
_abs296_park_blocked "$TM" "$DA"

# Mark only DA Done; DB still in Backlog.
_abs296_advance_to_done "$DA"
baseline

out_partial=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_partial" "INTENT BLOCKED-AUTO-RELEASE ticket=$TM" \
    "ABS-296 AC2: no release when only some depends_on are Done (DB still pending)"

# Now mark DB Done too → release fires.
_abs296_advance_to_done "$DB"

out_both=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out_both" "INTENT BLOCKED-AUTO-RELEASE ticket=$TM" \
    "ABS-296 AC2: release fires once ALL depends_on are Done"
assert_eq "$(tracker get "$TM" | sed -n 's/^status: //p' | head -1)" "In Progress" \
    "ABS-296: multi-dep ticket released to BLOCKED-FROM origin (In Progress) after all deps Done"

cleanup_env

# --- AC3e: dep-id prefix collision stays Blocked ----------------------------------
# Park reason names a DIFFERENT ticket id that starts with the dep id
# (e.g. reason cites "DEP_ID0" when dep is "DEP_ID").  Without whole-token
# matching, the unanchored substring test would accept this as dependency-caused
# and reverse a human/TDM park (CRITICAL-2, Stage-1 Iteration-2 review).

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1

DEP_PC=$(tracker create --type ticket --title "ABS-296 dep-prefix-collision")
T_PC=$(tracker create --type ticket --title "ABS-296 prefix-collision story")
tracker link "$T_PC" "$DEP_PC" depends-on >/dev/null
tracker transition "$T_PC" "Ready for Development" --actor orchestrator --reason "setup" >/dev/null
tracker transition "$T_PC" "In Progress"           --actor orchestrator --reason "setup" >/dev/null
# Park reason cites "${DEP_PC}0" — a longer id that has DEP_PC as a prefix.
# An unanchored substring match would treat this as dependency-caused; the
# whole-token matcher must NOT.
tracker transition "$T_PC" "Blocked" --actor orchestrator \
    --reason "Human park: blocked by infra incident tracked in ${DEP_PC}0; not dependency-caused." \
    >/dev/null
tracker comment "$T_PC" --kind gate-results --actor orchestrator \
    --body "BLOCKED-FROM=In Progress (orchestrator): recording pre-blocked status." >/dev/null
# Mark the real dep Done — sweep must still not release (reason named the wrong id).
_abs296_advance_to_done "$DEP_PC"
baseline

out_pc=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_pc" "INTENT BLOCKED-AUTO-RELEASE ticket=$T_PC" \
    "ABS-296 AC3e: prefix-collision dep id in reason does not satisfy whole-token match"
assert_eq "$(tracker get "$T_PC" | sed -n 's/^status: //p' | head -1)" "Blocked" \
    "ABS-296 AC3e: ticket stays Blocked when reason names a prefix-colliding id not the actual dep"

cleanup_env

# --- PILOT-44: a dependency-caused Blocked ticket is auto-released once its dep
#     reaches 'Docs' (POST-MERGE per ABS-266) — no need to wait for Done. ---------
# blocked_auto_release_sweep re-uses depends_unmet, so the 'Docs' short-circuit
# applies here too. ORCH_MAIN_REMOTE=none forces the merge probe to report NONE,
# so the release can ONLY come from the 'Docs' status (not a lucky ancestry hit).
# This is the exact v3-pilot #5 scenario: PILOT-30/PILOT-32 Blocked on
# PILOT-29-in-Docs held until Done, stalling the whole downstream wave.

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_BLOCKED_AUTO_RELEASE=1
export ORCH_DEPENDS_GATING=1
export ORCH_MAIN_REMOTE=none

DEP_DOCS=$(tracker create --type ticket --title "PILOT-44 dep -> Docs")
T_DOCS=$(tracker create --type ticket --title "PILOT-44 blocked-on-docs story")
tracker link "$T_DOCS" "$DEP_DOCS" depends-on >/dev/null
_abs296_park_blocked "$T_DOCS" "$DEP_DOCS"

# Drive the dep to 'Docs' (post-merge) — NOT Done.
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    tracker transition "$DEP_DOCS" "$s" --actor orchestrator --reason "setup" >/dev/null
done
assert_eq "$(tracker get "$DEP_DOCS" | sed -n 's/^status: //p' | head -1)" "Docs" \
    "PILOT-44 setup: dependency rests in 'Docs' (not Done)"
baseline

out_docs=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out_docs" "INTENT BLOCKED-AUTO-RELEASE ticket=$T_DOCS" \
    "PILOT-44: blocked ticket auto-released when its dep reaches 'Docs' (ABS-266 post-merge), before Done"
assert_eq "$(tracker get "$T_DOCS" | sed -n 's/^status: //p' | head -1)" "In Progress" \
    "PILOT-44: ticket returns to its BLOCKED-FROM origin once the dep is in 'Docs'"

unset ORCH_MAIN_REMOTE
cleanup_env
