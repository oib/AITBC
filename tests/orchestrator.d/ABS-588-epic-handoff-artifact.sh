# =============================================================================
# ABS-588 — epic-handoff artifact contract (RTE) + marker↔sensor coherence
# -----------------------------------------------------------------------------
# `source`d by tests/tooling/test-orchestrator.sh (no shebang, no re-`set -e`). Shares the
# harness: assert_contains / assert_not_contains / assert_eq, REPO_ROOT, counters.
#
# The gap (Pilot 7, epic PILOT-58): the RTE correctly closes epic integration and
# releases to `Ready for Epic Acceptance`, but the handoff pointed at a bare branch
# name — the human had to reassemble the story list / verification / MR by hand
# (MR !231). Fix (paths b+c, boundary-neutral): the RTE gate-results comment IS a
# reviewable artifact carrying the story list, the verification state, and the ONE
# copy-paste human MR command; a marker line lets the ops-sweep sensor flag a
# missing artifact. This test pins that contract so it cannot silently regress.
# =============================================================================
_rte="$REPO_ROOT/harness/claude/agents/rte.md"
_sensors="$REPO_ROOT/scripts/ops-sweep-sensors.sh"

# AC2 — the ADR-A-0014 boundary stays verbatim (proven, not merely asserted): the
# RTE seat still never opens or merges the main-bound PR.
assert_contains "$(cat "$_rte")" "never open or merge a PR to \`main\` from this seat" \
    "ABS-588 AC2: rte.md keeps the 'never open or merge to main' boundary verbatim"
assert_contains "$(cat "$_rte")" "RTE does not open or touch that \`main\`-bound PR" \
    "ABS-588 AC2: rte.md keeps 'RTE does not open or touch that main-bound PR'"

# AC1/AC3 — the artifact carries the ONE next step, the story list, and rides the
# verification state; and it is marked so the sensor can detect its absence.
assert_contains "$(cat "$_rte")" "EPIC-HANDOFF-READY" \
    "ABS-588 AC4: rte.md handoff artifact carries the load-bearing marker line"
assert_contains "$(cat "$_rte")" "Human next step (the ONE step" \
    "ABS-588 AC1: rte.md handoff names exactly ONE human next step"
assert_contains "$(cat "$_rte")" "glab mr create --source-branch epic/" \
    "ABS-588 AC1: the ONE step is a copy-paste MR-create command (human runs it)"
assert_contains "$(cat "$_rte")" "**Stories** (all Done):" \
    "ABS-588 AC1: handoff lists the child stories (no reconstruction from the log)"

# marker↔sensor coherence: the token the RTE writes is exactly the one the sensor
# looks for — a rename on one side without the other would silently break the gate.
assert_contains "$(cat "$_sensors")" 'OPS_EPIC_HANDOFF_MARKER:-EPIC-HANDOFF-READY' \
    "ABS-588: sensor default marker matches the rte.md artifact marker"

# AC4 — the sensor is registered and mechanically flags a missing artifact.
assert_contains "$(bash "$_sensors" --list)" "epic-handoff-missing" \
    "ABS-588 AC4: epic-handoff-missing detector is registered"
_ehd="$(mktemp -d "${TMPDIR:-/tmp}/abs588-XXXXXX")"
cat > "$_ehd/EPIC-1.md" <<'EOF'
---
id: EPIC-1
status: Ready for Epic Acceptance
---
released, branch only — no artifact.
EOF
_out="$(OPS_TICKETS_DIR="$_ehd" bash "$_sensors" epic-handoff-missing)"
assert_contains "$_out" "epic-handoff-missing EPIC-1 status=Ready-for-Epic-Acceptance,artifact=absent" \
    "ABS-588 AC4: epic at the human gate without the artifact -> reported as a finding"
rm -rf "$_ehd" 2>/dev/null || true
