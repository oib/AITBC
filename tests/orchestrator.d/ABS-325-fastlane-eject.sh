# =============================================================================
# ABS-325 — v3 Fastlane: EJECTION instead of parking (Auswurf statt Parkung)
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER, warm_git_repo.
#
# When a `lane=fastlane` ticket trips a safety trigger — (a) red tests from
# iteration >=2, (b) a diff-budget overrun, (c) a touched protected path, or
# (d) a firing station guard — the runner does NOT park it. It DEMOTES the ticket
# to the normal lane (lane=normal), records an ejection-reason comment, and
# resumes it at `Ready for Development` (ADR-A-0002 impl-fix re-entry) — never
# `Blocked`, never a human-wait. The full chain (QAS/review/PO/merge-token/human
# merge) then applies; ejection bypasses no gate. Kill-switch ORCH_FASTLANE_EJECT=0.
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-322 / ABS-324 includes).
tracker() { bash "$TRACKER" "$@"; }

# Walk a story ticket forward to <target> over legal edges (direct transitions).
_abs325_walk() {
    local t="$1" target="$2" s
    for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance"; do
        tracker transition "$t" "$s" --actor orchestrator --reason "abs325 walk" >/dev/null 2>&1
        [ "$s" = "$target" ] && return 0
    done
}

echo -e "\n${CYAN}ABS-325 — fastlane ejection (Auswurf statt Parkung)${NC}"

# --- AC1: red tests from iteration >=2 eject to the normal lane ---------------
# A fastlane ticket bounced back from the combined gate (In Review -> Ready for
# Development, a backward rework by a non-human actor: the tests were still red).
# On the next dispatch it is EJECTED, not re-spawned in-lane and not escalated.
new_env
F=$(tracker create --type ticket --title "fastlane red tests" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker transition "$F" "Ready for Development" --actor be-developer --reason "combined gate: tests still red, fresh implementer" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-EJECT ticket=$F role=- to=Ready for Development" "ABS-325 AC1: red tests at iteration >=2 eject the fastlane ticket"
assert_contains "$out" "trigger=red-tests" "ABS-325 AC1: the ejection names the red-tests trigger"
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$F" "ABS-325 AC1/AC5: no human-wait escalation for an ejected ticket"
assert_not_contains "$out" "INTENT REWORK-LIMIT ticket=$F" "ABS-325 AC1/AC5: ejection replaces the rework->PO escalation"
cleanup_env

# --- AC5: no Blocked / no human-wait; an ejection reason is recorded (LIVE) ---
new_env
F=$(tracker create --type ticket --title "fastlane eject live" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker transition "$F" "Ready for Development" --actor be-developer --reason "tests still red" >/dev/null 2>&1
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
dump=$(tracker get "$F")
assert_contains "$dump" "lane: normal" "ABS-325 AC5: the ejected ticket is demoted to the normal lane"
assert_contains "$dump" "FASTLANE-EJECT trigger=red-tests" "ABS-325 AC5: an ejection-reason comment is recorded on the ticket"
assert_not_contains "$dump" "status: Blocked" "ABS-325 AC5: the ejected ticket never enters Blocked"
assert_not_contains "$dump" "status: Needs PO Decision" "ABS-325 AC5: the ejected ticket never waits on a human (Needs PO Decision)"
assert_not_contains "$dump" "status: Ready for Human Acceptance" "ABS-325 AC5: the ejected ticket never waits on a human (RfHA)"
cleanup_env

# --- AC2: exceeding the diff budget ejects the ticket ------------------------
# The fastlane Solo-Seat's handoff claims a commit whose diff exceeds the budget;
# fastlane_diff_offense reads the same `commits:` field the ABS-255 verifier does.
new_env
GITREPO="$TEST_DIR/target-repo"; mkdir -p "$GITREPO"; warm_git_repo "$GITREPO"
{ printf 'line %s\n' $(seq 1 30); } > "$GITREPO/big.txt"
git -C "$GITREPO" add big.txt >/dev/null 2>&1
git -C "$GITREPO" -c user.email=t@t -c user.name=t commit -q -m "big change [ABS-XXX]"
SHA=$(git -C "$GITREPO" rev-parse HEAD)
export ORCH_TARGET_REPO="$GITREPO"
F=$(tracker create --type ticket --title "fastlane diff budget" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker comment "$F" --kind handoff --actor be-developer --body "## Handoff
- commits: $SHA" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_FASTLANE_DIFF_BUDGET=5 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-EJECT ticket=$F role=- to=In Review" "ABS-325 AC2: a diff-budget overrun ejects the fastlane ticket"
assert_contains "$out" "trigger=diff-budget" "ABS-325 AC2: the ejection names the diff-budget trigger"
unset ORCH_TARGET_REPO
cleanup_env

# Control (AC2): the SAME commit under a generous budget does NOT eject.
new_env
GITREPO="$TEST_DIR/target-repo"; mkdir -p "$GITREPO"; warm_git_repo "$GITREPO"
{ printf 'line %s\n' $(seq 1 30); } > "$GITREPO/big.txt"
git -C "$GITREPO" add big.txt >/dev/null 2>&1
git -C "$GITREPO" -c user.email=t@t -c user.name=t commit -q -m "big change [ABS-XXX]"
SHA=$(git -C "$GITREPO" rev-parse HEAD)
export ORCH_TARGET_REPO="$GITREPO"
F=$(tracker create --type ticket --title "fastlane within budget" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker comment "$F" --kind handoff --actor be-developer --body "## Handoff
- commits: $SHA" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_FASTLANE_DIFF_BUDGET=500 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "FASTLANE-EJECT ticket=$F" "ABS-325 AC2: a within-budget diff does not eject (the combined gate runs)"
assert_contains "$out" "note=fastlane-combined-gate" "ABS-325 AC2: a within-budget fastlane ticket stays on the collapsed chain"
unset ORCH_TARGET_REPO
cleanup_env

# --- AC3: touching a protected path ejects the ticket ------------------------
new_env
GITREPO="$TEST_DIR/target-repo"; mkdir -p "$GITREPO"; warm_git_repo "$GITREPO"
mkdir -p "$GITREPO/db/migrations"
printf 'ALTER TABLE t ADD COLUMN c int;\n' > "$GITREPO/db/migrations/001_add.sql"
git -C "$GITREPO" add db/migrations/001_add.sql >/dev/null 2>&1
git -C "$GITREPO" -c user.email=t@t -c user.name=t commit -q -m "schema [ABS-XXX]"
SHA=$(git -C "$GITREPO" rev-parse HEAD)
export ORCH_TARGET_REPO="$GITREPO"
F=$(tracker create --type ticket --title "fastlane protected path" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker comment "$F" --kind handoff --actor be-developer --body "## Handoff
- commits: $SHA" >/dev/null 2>&1
# Generous budget so ONLY the protected-path trigger can fire (it is checked first).
out=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_FASTLANE_DIFF_BUDGET=9999 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-EJECT ticket=$F role=- to=In Review" "ABS-325 AC3: touching a protected path ejects the fastlane ticket"
assert_contains "$out" "trigger=protected-path" "ABS-325 AC3: the ejection names the protected-path trigger"
unset ORCH_TARGET_REPO
cleanup_env

# --- AC4: a firing station guard ejects the ticket ---------------------------
# A `security`-flagged fastlane ticket lands In Test via the legal-but-skipping
# `In Review -> In Test` edge; the flag makes the jumped Security Review station
# mandatory (ABS-247), so the guard WOULD fire. For a fastlane ticket that guard
# firing EJECTS instead of the in-lane STATION-GUARD redirect.
new_env
F=$(tracker create --type ticket --title "fastlane guard fire" --role be-developer --lane fastlane --flag security | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker transition "$F" "In Test" --actor be-developer --reason "skip security review" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT FASTLANE-EJECT ticket=$F role=- to=In Test" "ABS-325 AC4: a firing station guard ejects the fastlane ticket"
assert_contains "$out" "trigger=guard" "ABS-325 AC4: the ejection names the guard trigger"
assert_not_contains "$out" "INTENT STATION-GUARD ticket=$F" "ABS-325 AC4: the in-lane STATION-GUARD redirect is replaced by ejection"
cleanup_env

# Control (AC4): a NORMAL-lane security ticket taking the same skip is redirected
# by the STATION-GUARD as before — ejection is fastlane-only.
new_env
N=$(tracker create --type ticket --title "normal guard fire" --role be-developer --flag security | awk '{print $NF}')
_abs325_walk "$N" "In Review"
tracker transition "$N" "In Test" --actor be-developer --reason "skip security review" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STATION-GUARD ticket=$N" "ABS-325 AC4: a normal-lane ticket keeps the STATION-GUARD redirect"
assert_not_contains "$out" "FASTLANE-EJECT ticket=$N" "ABS-325 AC4: a normal-lane ticket is never ejected"
cleanup_env

# --- AC6: ejecting a bundle member never ejects its eligible bundle-mates -----
# Two eligible lane=fastlane siblings under one parent share a bundle. One trips a
# trigger (red tests) and is ejected; the other stays lane=fastlane, un-touched.
new_env
P=$(tracker create --type epic --title "bundle parent" | awk '{print $NF}')
A=$(tracker create --type ticket --title "bundle member A" --role be-developer --lane fastlane --parent "$P" | awk '{print $NF}')
B=$(tracker create --type ticket --title "bundle member B" --role be-developer --lane fastlane --parent "$P" | awk '{print $NF}')
# A bounces (red tests) -> eligible for ejection; B stays clean at Ready for Development.
_abs325_walk "$A" "In Review"
tracker transition "$A" "Ready for Development" --actor be-developer --reason "tests still red" >/dev/null 2>&1
tracker transition "$B" "Ready for Development" --actor orchestrator --reason "abs325 walk" >/dev/null 2>&1
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
assert_contains "$(tracker get "$A")" "lane: normal" "ABS-325 AC6: the triggering bundle member A is ejected to normal"
assert_contains "$(tracker get "$B")" "lane: fastlane" "ABS-325 AC6: the still-eligible bundle-mate B keeps lane=fastlane (per-ticket attribution)"
assert_not_contains "$(tracker get "$B")" "FASTLANE-EJECT" "ABS-325 AC6: B carries no ejection — only the offending ticket is demoted"
cleanup_env

# --- Kill-switch: ORCH_FASTLANE_EJECT=0 restores parking behaviour ------------
new_env
F=$(tracker create --type ticket --title "fastlane eject off" --role be-developer --lane fastlane | awk '{print $NF}')
_abs325_walk "$F" "In Review"
tracker transition "$F" "Ready for Development" --actor be-developer --reason "tests still red" >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 ORCH_FASTLANE_EJECT=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "FASTLANE-EJECT ticket=$F" "ABS-325: knob=0 emits no ejection"
cleanup_env
