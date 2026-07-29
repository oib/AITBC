# =============================================================================
# PILOT-43 — ops-sweep Tier A/B activation (the shadow phase is over).
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# WHAT PILOT-43 ADDS
#   ORCH_OPS_SWEEP_TIERS selects which action tiers the cadence ops-sweep seat may
#   EXECUTE. Empty (default) keeps PILOT-42's Phase-0 shadow behaviour byte-for-byte;
#   "A" activates Tier A, "AB" Tier A+B. The dispatch encodes the derived phase +
#   normalized tiers in the OPS-SWEEP intent note and the seat packet.
#
# WHAT THESE TESTS PIN
#   - falsification: interval ON but no tiers => intent stays phase=0 tiers=- (a run
#     that does not opt in is NOT switched into acting).
#   - A => phase=1 tiers=A ; AB => phase=2 tiers=AB (case-insensitive).
#   - a junk tiers value degrades to shadow, never mis-activates.
#   - knob 0 => no dispatch at all, regardless of tiers (byte-identical to legacy).
# The cadence marker is seeded by a first (not-due) sweep, then a later clock fires
# the dispatch whose intent line carries the note (mirrors the PILOT-42 shard).
# =============================================================================

echo -e "\n${CYAN}=== PILOT-43 ops-sweep Tier A/B activation ===${NC}\n"

# Fire one due sweep and echo its dispatch output. $1 = ORCH_OPS_SWEEP_TIERS value
# (may be empty). Seeds the cadence marker at T0, then fires at T0+2*interval.
ops_sweep_fire() {
    ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=1000000 ORCH_RECONCILE_ON_STARTUP=1 \
        orch --dry-run --once >/dev/null 2>&1
    ORCH_OPS_SWEEP_TIERS="$1" ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=1000200 \
        ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null
}

# --- falsification: no tiers => shadow, not activated -------------------------
new_env
outN=$(ops_sweep_fire "")
assert_contains "$outN" "INTENT OPS-SWEEP ticket=ops-sweep role=tdm" \
    "PILOT-43: sweep fires when due"
assert_contains "$outN" "phase=0 tiers=-" \
    "PILOT-43 FALSIFICATION: no ORCH_OPS_SWEEP_TIERS => stays Phase-0 shadow (not activated)"
cleanup_env

# --- Tier A => phase 1 --------------------------------------------------------
new_env
outA=$(ops_sweep_fire "A")
assert_contains "$outA" "phase=1 tiers=A" \
    "PILOT-43: ORCH_OPS_SWEEP_TIERS=A => phase=1 tiers=A"
cleanup_env

# --- Tier A+B => phase 2, case-insensitive ------------------------------------
new_env
outAB=$(ops_sweep_fire "ab")
assert_contains "$outAB" "phase=2 tiers=AB" \
    "PILOT-43: ORCH_OPS_SWEEP_TIERS=ab => phase=2 tiers=AB (case-insensitive)"
cleanup_env

# --- junk value degrades to shadow (typo must not mis-activate) ---------------
new_env
outJ=$(ops_sweep_fire "xyz")
assert_contains "$outJ" "phase=0 tiers=-" \
    "PILOT-43: junk ORCH_OPS_SWEEP_TIERS => degrades to shadow, never mis-activates"
cleanup_env

# --- knob 0 => no dispatch regardless of tiers (byte-identical) ---------------
new_env
out0=$(ORCH_OPS_SWEEP_TIERS=AB ORCH_OPS_SWEEP_INTERVAL=0 ORCH_RECONCILE_ON_STARTUP=1 \
    orch --dry-run --once 2>/dev/null)
assert_not_contains "$out0" "INTENT OPS-SWEEP" \
    "PILOT-43: interval 0 => no sweep even with tiers set (byte-identical to legacy)"
cleanup_env
