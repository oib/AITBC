# =============================================================================
# ABS-335 — enforce live-state protection
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (Incident 2026-07-16)
# A seat ran the suite without an env scrub while ORCH_STATE_DIR still pointed at
# a LIVE orchestrator: mock intents (DEMO-2/3/4) landed in the live run.log and
# the run took the real spawn path; only a worktree-provisioning failure and the
# C9 fail-closed gate stopped a paid live seat. Two guards close it:
#   (1) tests/test-orchestrator.sh refuses to start when the ambient env resolves
#       to a state dir whose instance-id marker has a LIVE owner process, and
#   (2) scripts/orchestrator.sh refuses to write run.log when its own
#       ORCH_INSTANCE_ID differs from the persisted instance-id of the state dir.
# =============================================================================

echo -e "\n${CYAN}ABS-335 live-state protection${NC}"

_abs335_suite="$REPO_ROOT/tests/test-orchestrator.sh"
_abs335_cksum() { cksum < "$1" 2>/dev/null; }

# --- AC1/AC2: live-state refusal gate in the suite entry point ---------------
# A fake LIVE state: instance-id marker naming a still-running owner process, and
# a pre-existing run.log that MUST NOT be touched by the refused run.
_abs335_live="$(mktemp -d "${TMPDIR:-/tmp}/abs335-live-XXXXXX")"
sleep 300 & _abs335_owner=$!
printf 'testhost-%s-abcd1234\n' "$_abs335_owner" > "$_abs335_live/instance-id"
printf 'LIVE run.log line — must survive the refused test run\n' > "$_abs335_live/run.log"
_abs335_live_before="$(_abs335_cksum "$_abs335_live/run.log")"

# `|| rc=$?` (not `; rc=$?`): this file runs under the suite's set -e, where an
# assignment from a non-zero command substitution would abort the whole suite.
_abs335_rc=0
_abs335_out="$(env ORCH_STATE_DIR="$_abs335_live" LIVESTATE_GUARD_SELFTEST=1 \
    bash "$_abs335_suite" 2>&1)" || _abs335_rc=$?

assert_eq "$_abs335_rc" "1" \
    "ABS-335 AC1: suite refuses to start (exit 1) when ambient state dir has a LIVE instance-id owner"
assert_contains "$_abs335_out" "refusing to run" \
    "ABS-335 AC1: refusal message names the live-state hazard"
assert_contains "$_abs335_out" "owner pid $_abs335_owner is alive" \
    "ABS-335 AC1: refusal identifies the live owner process"
assert_eq "$(_abs335_cksum "$_abs335_live/run.log")" "$_abs335_live_before" \
    "ABS-335 AC2: refused run leaves the live run.log byte-identical"

kill "$_abs335_owner" 2>/dev/null || true
wait "$_abs335_owner" 2>/dev/null || true
rm -rf "$_abs335_live"

# --- AC2: a STALE marker (dead owner) starts the suite normally ---------------
_abs335_stale="$(mktemp -d "${TMPDIR:-/tmp}/abs335-stale-XXXXXX")"
sleep 300 & _abs335_dead=$!
kill "$_abs335_dead" 2>/dev/null || true
wait "$_abs335_dead" 2>/dev/null || true
printf 'testhost-%s-abcd1234\n' "$_abs335_dead" > "$_abs335_stale/instance-id"

_abs335_stale_rc=0
_abs335_stale_out="$(env ORCH_STATE_DIR="$_abs335_stale" LIVESTATE_GUARD_SELFTEST=1 \
    bash "$_abs335_suite" 2>&1)" || _abs335_stale_rc=$?

assert_eq "$_abs335_stale_rc" "0" \
    "ABS-335 AC2: a STALE instance-id marker (dead owner) does NOT block suite start"
assert_contains "$_abs335_stale_out" "live-state gate passed" \
    "ABS-335 AC2: stale-marker run passes the gate"
rm -rf "$_abs335_stale"

# --- AC3: suite scrubs ambient JIRA_* --------------------------------------
# With hostile JIRA_* in the caller env the selftest still passes the gate; the
# grep proves the prefix-unset line is present (structural, bash 3.2-safe).
_abs335_jira_rc=0
_abs335_jira_out="$(env ORCH_STATE_DIR="$_abs335_stale-absent" \
    JIRA_SITE=https://evil.example JIRA_API_TOKEN=dummy LIVESTATE_GUARD_SELFTEST=1 \
    bash "$_abs335_suite" 2>&1)" || _abs335_jira_rc=$?
assert_eq "$_abs335_jira_rc" "0" \
    "ABS-335 AC3: suite runs identically with hostile JIRA_* in the ambient env"
assert_eq "$(grep -cE '^unset "\$\{!JIRA_@\}"' "$_abs335_suite")" "1" \
    "ABS-335 AC3: suite prefix-unsets the ambient JIRA_* env"

# --- AC4: orchestrator refuses run.log writes on instance-id mismatch ---------
# Foreign state dir with a persisted instance-id + run.log; start the runner with
# a DIFFERENT ORCH_INSTANCE_ID (operator override, ABS-183) => loud failure, no
# log append, foreign run.log byte-identical.
_abs335_foreign="$(mktemp -d "${TMPDIR:-/tmp}/abs335-foreign-XXXXXX")/work/.orchestrator"
mkdir -p "$_abs335_foreign"
printf 'foreignhost-99999-deadbeef\n' > "$_abs335_foreign/instance-id"
printf 'FOREIGN run.log line — must not be appended to\n' > "$_abs335_foreign/run.log"
_abs335_foreign_before="$(_abs335_cksum "$_abs335_foreign/run.log")"

# The foreign instance's session store must survive too: check_account_switch
# (ABS-302) wipes session files and rewrites .account-id inside the state dir,
# so it must run AFTER the guard. ORCH_SESSION_RESUME=1 + a stored account id
# that can never match arms exactly that wipe path — pre-fix ordering deletes
# the session file below before the mismatch die.
mkdir -p "$_abs335_foreign/sessions"
printf 'account-of-the-foreign-instance\n' > "$_abs335_foreign/sessions/.account-id"
printf 'sess-keepme\n' > "$_abs335_foreign/sessions/DEMO-1.be-developer.session"

_abs335_g_rc=0
_abs335_g_out="$(env ORCH_STATE_DIR="$_abs335_foreign" \
    ORCH_INSTANCE_ID="myhost-11111-cafebabe" ORCH_SESSION_RESUME=1 \
    bash "$ORCH" --once --dry-run 2>&1)" || _abs335_g_rc=$?

assert_eq "$_abs335_g_rc" "1" \
    "ABS-335 AC4: runner exits non-zero when its ORCH_INSTANCE_ID != persisted instance-id"
assert_contains "$_abs335_g_out" "instance-id mismatch" \
    "ABS-335 AC4: runner names the instance-id mismatch on stderr"
assert_eq "$(_abs335_cksum "$_abs335_foreign/run.log")" "$_abs335_foreign_before" \
    "ABS-335 AC4: refused runner leaves the foreign run.log byte-identical"
if [ -f "$_abs335_foreign/sessions/DEMO-1.be-developer.session" ]; then _abs335_sess=survived; else _abs335_sess=wiped; fi
assert_eq "$_abs335_sess" "survived" \
    "ABS-335 AC4: refused runner does not wipe the foreign session store (ABS-302 runs after the guard)"
assert_eq "$(cat "$_abs335_foreign/sessions/.account-id")" "account-of-the-foreign-instance" \
    "ABS-335 AC4: refused runner does not rewrite the foreign .account-id"

# --- AC5 regression: matching instance-id (ABS-183 restart reuse) proceeds ----
# Same state dir, but the runner's ORCH_INSTANCE_ID MATCHES the persisted file —
# the guard must NOT fire (this is the ABS-183 restart-reuse path).
_abs335_ok_tickets="$(mktemp -d "${TMPDIR:-/tmp}/abs335-tk-XXXXXX")"
_abs335_ok_rc=0
_abs335_ok_out="$(env ORCH_STATE_DIR="$_abs335_foreign" \
    ORCH_INSTANCE_ID="foreignhost-99999-deadbeef" ORCH_SESSION_RESUME=0 \
    MOCK_TRACKER_TICKETS_DIR="$_abs335_ok_tickets" \
    bash "$ORCH" --once --dry-run 2>&1)" || _abs335_ok_rc=$?
rm -rf "$_abs335_ok_tickets"
assert_eq "$_abs335_ok_rc" "0" \
    "ABS-335 AC5: matching instance-id (restart reuse) is NOT blocked by the guard"
assert_not_contains "$_abs335_ok_out" "instance-id mismatch" \
    "ABS-335 AC5: no mismatch error when instance-id matches the persisted file"

rm -rf "$(dirname "$(dirname "$_abs335_foreign")")"

unset _abs335_suite _abs335_live _abs335_owner _abs335_live_before _abs335_out \
      _abs335_rc _abs335_stale _abs335_dead _abs335_stale_out _abs335_stale_rc \
      _abs335_jira_out _abs335_jira_rc _abs335_foreign _abs335_foreign_before \
      _abs335_g_out _abs335_g_rc _abs335_ok_out _abs335_ok_rc _abs335_ok_tickets \
      _abs335_sess
unset -f _abs335_cksum
