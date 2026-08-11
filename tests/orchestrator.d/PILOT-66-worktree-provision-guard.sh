# =============================================================================
# PILOT-66 — worktree provisioning: count failures, back off, escalate
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS
# The fail-closed decision (never spawn a write-capable seat in the main
# checkout when its isolated worktree cannot be provisioned) is correct; the
# DEFECT was the unbounded, alarmless, BUDGET-DRAINING retry — 131
# INTENT-SKIP-NOWORKTREE in one pilot over ~4h, with no attempt counter, no
# backoff, no escalation, and no git error text in the runlog.
#
# THE FIX (this include is AC4's falsification of it)
#   AC1 — each failure is counted per ticket; after N attempts the runner
#         ESCALATES to Blocked with an Attention-Event (NOTIFY) instead of
#         retrying silently.
#   AC2 — git's own `git worktree add` stderr is surfaced (attempt line + log).
#   AC4 — across the N attempts + escalation the spawn seam is never invoked and
#         NOTHING is billed to the daily spawn-budget ledger (budget unchanged).
#
# FIXTURE. A representative, deterministic failure: occupy the <ticket>-auto
# branch in the MAIN working tree, so every `git worktree add` for that branch
# fails ("already checked out"). Backoff is OFF here (new_env pins
# ORCH_BACKOFF_BASE_SECONDS=0), so each --once sweep re-attempts and increments
# the counter; N=3 keeps the walk short.
# =============================================================================

echo -e "\n${CYAN}PILOT-66 — worktree provisioning: count → backoff → escalate${NC}"

new_env
export ORCH_WORKTREE_SPAWNS=1
export ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS=3
_P66_TARGET="$(mktemp -d /tmp/pilot66-target-XXXXXX)"
warm_git_repo "$_P66_TARGET"
export ORCH_TARGET_REPO="$_P66_TARGET"
_P66_T=$(tracker create --type ticket --title "wt provision fail story" --role be-developer)
git -C "$_P66_TARGET" checkout -q -b "$_P66_T-auto"   # occupy the branch -> `worktree add` fails
export STUB_RECORD_FILE="$TEST_DIR/p66-records"; : > "$STUB_RECORD_FILE"
baseline
tracker transition "$_P66_T" "Ready for Development" --actor po --reason go >/dev/null

# --- attempt 1: counted + fail-closed, git error surfaced, NOT escalated ------
_P66_OUT1=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null || true)
assert_contains "$_P66_OUT1" "INTENT SKIP-NOWORKTREE ticket=$_P66_T" \
    "PILOT-66 AC1: attempt 1 fail-closes (rests the ticket)"
assert_contains "$_P66_OUT1" "attempt=1/3" \
    "PILOT-66 AC1: the fail-closed intent carries the per-ticket attempt counter"
assert_contains "$_P66_OUT1" "already" \
    "PILOT-66 AC2: git's own 'git worktree add' stderr is surfaced (…already checked out…)"
assert_not_contains "$_P66_OUT1" "WORKTREE-PROVISION-ESCALATE" \
    "PILOT-66 AC1: no escalation before N attempts"

# --- attempt 2: still counted, still not escalated ----------------------------
# The ticket rests at "Ready for Development"; the reconcile sweep re-derives the
# spawn and re-attempts provisioning (as the fail-closed code comment promises).
_P66_OUT2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
assert_contains "$_P66_OUT2" "attempt=2/3" \
    "PILOT-66 AC1: attempt 2 increments the counter"
assert_not_contains "$_P66_OUT2" "WORKTREE-PROVISION-ESCALATE" \
    "PILOT-66 AC1: still no escalation at attempt 2"

# --- AC4 (measured across the pure fail-closed retries, before escalation): the
# unbounded retry loop is exactly what drained the budget. Two failed
# provisioning attempts must have invoked the spawn seam ZERO times and billed
# NOTHING to the daily budget ledger — the fail-closed gate returns before the
# budget/lock/seam are ever touched.
assert_eq "$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')" "0" \
    "PILOT-66 AC4: the spawn seam was never invoked by the failed-provisioning retries"
_P66_LEDGER_LINES=$(cat "$ORCH_STATE_DIR"/spawn-ledger-* 2>/dev/null | wc -l | tr -d ' ')
assert_eq "$_P66_LEDGER_LINES" "0" \
    "PILOT-66 AC4: no spawn billed to the daily budget ledger (budget unchanged)"

# --- attempt 3: reaches N -> escalate to Blocked with an Attention-Event -------
_P66_OUT3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
assert_contains "$_P66_OUT3" "INTENT WORKTREE-PROVISION-ESCALATE ticket=$_P66_T role=be-developer to=Blocked" \
    "PILOT-66 AC1: escalates to Blocked after N attempts"
assert_contains "$_P66_OUT3" "INTENT NOTIFY ticket=$_P66_T" \
    "PILOT-66 AC1: escalation emits an Attention-Event (NOTIFY)"
# Durable evidence of the Blocked transition + human-facing comment (survives the
# separate v3 Blocked-entry triage that may route the ticket onward afterwards).
_P66_DUMP="$(tracker get "$_P66_T")"
assert_contains "$_P66_DUMP" "Worktree provisioning failed 3 consecutive times" \
    "PILOT-66 AC1: escalation posts the visible gate-results comment"

unset ORCH_TARGET_REPO STUB_RECORD_FILE ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$_P66_TARGET"
cleanup_env
unset _P66_TARGET _P66_T _P66_OUT1 _P66_OUT2 _P66_OUT3 _P66_LEDGER_LINES _P66_DUMP
