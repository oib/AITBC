# =============================================================================
# PILOT-2 — ready-for-Merge wait-state invariant: refuse/repair the UNMERGED
#           Merging->Docs jump (merge-state-aware)
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq /
# assert_not_contains, PASS/FAIL/TOTAL, new_env / cleanup_env / baseline /
# tracker / orch, ORCH / TRACKER / ORCH_STATE_DIR.
#
# FINDING PINNED (origin ABS-492, v3-pilot): PILOT-1's Merging seat jumped
# straight to `Docs` WHILE ITS PR WAS STILL UNMERGED, bypassing the human-owned
# `Ready for Merge` gate; the runner only skip-logged it ("skip current=Docs
# (seat moved elsewhere)") and accepted the bypass.
#
# The invariant is MERGE-STATE-AWARE (Stage-1 review, iteration 1): entry to
# `Docs` from `Merging` is LEGAL after a CONFIRMED merge — the accepted
# auto-merge rte exit declares/self-moves Merging->Docs post-merge (ADR-A-0014,
# statuses.yaml:275). So merging_docs_waitstate_gate (wired into
# apply_handoff_transition) mirrors docs_pr_gate: it probes story_pr_state and
# REPAIRS ONLY the UNMERGED jump — resting the story at `Ready for Merge` with a
# naming gate-results comment — while the merged exit, a direct-to-branch story
# with no PR, and the no-forge placeholder case all pass through untouched.
# This test locks:
#   (1) declared Docs @ current=Merging, PR UNMERGED -> repaired + comment;
#   (2) the observed pilot shape (self-moved to Docs, no target), PR UNMERGED -> repaired;
#   (3) status history carries `Ready for Merge`;
#   (4) MERGE-AWARE carve-out: the auto-merge exit (PR MERGED, declared OR
#       self-moved) is NOT repaired — no false WAIT-STATE REPAIR, no round-trip;
#   (5) no regression: no-forge placeholder, clean target-less rte handoff, and a
#       non-Merging seat are all untouched.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-2 Merging->Docs wait-state invariant (origin ABS-492) ===${NC}\n"

# walk_to_merging <ticket> — drive the v3 story chain into Merging (mock enforces
# the transition table, so this is a valid entry, not a forced set).
_pilot2_walk_to_merging() {
    local t="$1" s
    for s in "Ready for Development" "In Progress" "In Review" "In Test" \
             "Design Test" "Story Acceptance" "Merging"; do
        tracker transition "$t" "$s" --actor agent --reason walk >/dev/null
    done
}
# The subshells below stub the forge seam exactly like tests/test-done-gate.sh:
# story_pr_state calls `forge pr-state <ticket>`, so a `forge()` override + a
# non-empty FORGE_CMD lets each case declare the PR merge state it exercises.

# ---------------------------------------------------------------------------
echo -e "${CYAN}PILOT-2 AC1 — declared Docs @ current=Merging with an UNMERGED PR is repaired to Ready for Merge${NC}"
# ---------------------------------------------------------------------------
new_env
T1=$(tracker create --type ticket --title "PILOT-2 declared Docs jump")
baseline
_pilot2_walk_to_merging "$T1"
# The rte seat hands off DECLARING `to: Docs` while the ticket still rests at
# Merging AND its PR is still OPEN — the direct bypass of the human merge gate.
(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; ORCH_HANDOFF_TRANSITION=1; FORGE_CMD="stub"   # set AFTER source (source resets MODE=dry-run)
  forge() { printf 'OPEN #7\n'; }
  apply_handoff_transition "$T1" "Merging" "rte" "gate-results: PR opened, not yet merged
to: Docs" >/dev/null 2>&1
)
_p2_dump1="$(tracker get "$T1" 2>/dev/null)"
_p2_status1="$(printf '%s\n' "$_p2_dump1" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_p2_status1" "Ready for Merge" \
    "PILOT-2 AC1: an UNMERGED Merging-seat handoff declaring Docs is repaired to the human-owned Ready for Merge gate (not accepted as Docs)"
assert_contains "$_p2_dump1" "WAIT-STATE REPAIR" \
    "PILOT-2 AC1: a naming gate-results comment records the repair"
assert_contains "$_p2_dump1" "Transition: Merging -> Ready for Merge" \
    "PILOT-2 AC1: status history contains the Merging -> Ready for Merge repair edge"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}PILOT-2 AC1 (pilot shape) — a seat that SELF-MOVED to Docs with an UNMERGED PR is repaired, not skip-logged${NC}"
# ---------------------------------------------------------------------------
# The exact PILOT-1 observation: the seat transitioned Merging->Docs itself with
# the PR still open and handed off with NO declared target; the runner used to log
# "skip current=Docs (seat moved elsewhere)" and walk away. Now it repairs.
new_env
T2=$(tracker create --type ticket --title "PILOT-2 self-moved Docs jump")
baseline
_pilot2_walk_to_merging "$T2"
tracker transition "$T2" "Docs" --actor rte --reason "seat self-moved" >/dev/null   # the illegal seat-side jump
_p2_out2="$(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; ORCH_HANDOFF_TRANSITION=1; FORGE_CMD="stub"
  forge() { printf 'OPEN #7\n'; }
  # spawn-status is Merging; the seat declared no target (target-less handoff).
  apply_handoff_transition "$T2" "Merging" "rte" "gate-results: awaiting human merge" 2>&1
)"
_p2_dump2="$(tracker get "$T2" 2>/dev/null)"
_p2_status2="$(printf '%s\n' "$_p2_dump2" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_p2_status2" "Ready for Merge" \
    "PILOT-2 AC1: a seat that self-moved Merging->Docs with an unmerged PR is repaired back to Ready for Merge"
assert_contains "$_p2_out2" "INTENT MERGING-DOCS-WAITSTATE" \
    "PILOT-2: the repair is an auditable intent, replacing the old passive 'seat moved elsewhere' skip-log"
assert_not_contains "$_p2_out2" "skip current=Docs (seat moved elsewhere)" \
    "PILOT-2: the runner no longer merely skip-logs the bypass"
assert_contains "$_p2_dump2" "Transition: Docs -> Ready for Merge" \
    "PILOT-2 AC1: status history contains the Docs -> Ready for Merge repair edge"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}PILOT-2 merge-aware carve-out — the auto-merge exit (PR MERGED) reaches Docs UNTOUCHED (ADR-A-0014)${NC}"
# ---------------------------------------------------------------------------
# (a) declared Docs @ Merging with the PR CONFIRMED MERGED: the accepted
#     auto-merge rte exit (statuses.yaml:275). The gate must NOT fire — no false
#     WAIT-STATE REPAIR comment, no Ready-for-Merge round-trip; the story reaches
#     Docs as ADR-A-0014 intends.
new_env
T5=$(tracker create --type ticket --title "PILOT-2 auto-merge declared Docs")
baseline
_pilot2_walk_to_merging "$T5"
_p5_out="$(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; ORCH_HANDOFF_TRANSITION=1; FORGE_CMD="stub"
  forge() { printf 'MERGED #7\n'; }
  apply_handoff_transition "$T5" "Merging" "rte" "gate-results: merged
to: Docs" 2>&1
)"
_p5_dump="$(tracker get "$T5" 2>/dev/null)"
_p5_status="$(printf '%s\n' "$_p5_dump" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_p5_status" "Docs" \
    "PILOT-2 carve-out: a MERGED auto-merge exit declaring Docs reaches Docs (ADR-A-0014), not repaired"
assert_not_contains "$_p5_out" "INTENT MERGING-DOCS-WAITSTATE" \
    "PILOT-2 carve-out: the gate does NOT fire on a confirmed-merged exit (no false alarm)"
assert_not_contains "$_p5_dump" "WAIT-STATE REPAIR" \
    "PILOT-2 carve-out: no repair comment on the auto-merge happy path"

# (b) self-moved to Docs with the PR MERGED (the literal auto-merge exit shape):
#     the gate is a no-op and the story rests at Docs — no repair round-trip.
T6=$(tracker create --type ticket --title "PILOT-2 auto-merge self-moved Docs")
baseline
_pilot2_walk_to_merging "$T6"
tracker transition "$T6" "Docs" --actor rte --reason "auto-merge exit" >/dev/null
_p6_out="$(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; ORCH_HANDOFF_TRANSITION=1; FORGE_CMD="stub"
  forge() { printf 'MERGED #7\n'; }
  apply_handoff_transition "$T6" "Merging" "rte" "gate-results: merged" 2>&1
)"
_p6_dump="$(tracker get "$T6" 2>/dev/null)"
_p6_status="$(printf '%s\n' "$_p6_dump" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_p6_status" "Docs" \
    "PILOT-2 carve-out: a MERGED self-moved auto-merge exit rests at Docs, not repaired"
assert_not_contains "$_p6_out" "INTENT MERGING-DOCS-WAITSTATE" \
    "PILOT-2 carve-out: the gate does NOT fire on a confirmed-merged self-moved exit"
assert_not_contains "$_p6_dump" "WAIT-STATE REPAIR" \
    "PILOT-2 carve-out: no repair comment on the merged self-moved exit"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}PILOT-2 regression — placeholder / legitimate handoffs are UNTOUCHED${NC}"
# ---------------------------------------------------------------------------
# (a) No forge platform (boilerplate placeholder / mock env) -> nothing to gate:
#     even a declared Docs jump falls open (parity with docs_pr_gate/done_pr_gate).
new_env
T7=$(tracker create --type ticket --title "PILOT-2 no-forge placeholder")
baseline
_pilot2_walk_to_merging "$T7"
_p7_gate="$(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; FORGE_CMD=""   # no forge configured
  merging_docs_waitstate_gate "$T7" "Merging" "Docs" "Merging" "rte" >/dev/null 2>&1 && echo FIRED || echo NOOP
)"
assert_eq "$_p7_gate" "NOOP" \
    "PILOT-2 regression: no \$FORGE_CMD -> the gate falls open (placeholder parity with docs_pr_gate)"
cleanup_env

# (b) A clean target-less rte handoff at Merging still rests at Ready for Merge
#     via the ABS-133 default — NOT via the wait-state gate (no false alarm).
new_env
T3=$(tracker create --type ticket --title "PILOT-2 clean rte handoff")
baseline
_pilot2_walk_to_merging "$T3"
_p3_out="$(
  source "$ORCH" >/dev/null 2>&1
  MODE="live"; ORCH_HANDOFF_TRANSITION=1; FORGE_CMD="stub"
  forge() { printf 'OPEN #7\n'; }
  apply_handoff_transition "$T3" "Merging" "rte" "gate-results: PR opened, awaiting human merge" 2>&1
)"
_p3_status="$(tracker get "$T3" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_p3_status" "Ready for Merge" \
    "PILOT-2 regression: a clean target-less Merging handoff still rests at Ready for Merge (ABS-133 default)"
assert_not_contains "$_p3_out" "INTENT MERGING-DOCS-WAITSTATE" \
    "PILOT-2 regression: the wait-state gate does NOT fire on a legit clean handoff (target != Docs)"
assert_not_contains "$(tracker get "$T3" 2>/dev/null)" "WAIT-STATE REPAIR" \
    "PILOT-2 regression: no repair comment on a legit clean handoff"
cleanup_env

# (c) A non-Merging spawn status is never touched by the gate.
new_env
T4=$(tracker create --type ticket --title "PILOT-2 non-merging seat" --role be-developer)
baseline
tracker transition "$T4" "Ready for Development" --actor po --reason go >/dev/null
_p4_gate="$(
  source "$ORCH" >/dev/null 2>&1
  FORGE_CMD="stub"; forge() { printf 'OPEN #7\n'; }
  merging_docs_waitstate_gate "$T4" "In Review" "Docs" "In Review" "qas" >/dev/null 2>&1 && echo FIRED || echo NOOP
)"
assert_eq "$_p4_gate" "NOOP" \
    "PILOT-2 regression: the wait-state gate is Merging-only — a non-Merging spawn status is a no-op"
cleanup_env
