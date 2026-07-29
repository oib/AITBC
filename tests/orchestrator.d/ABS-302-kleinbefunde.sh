# =============================================================================
# Per-story orchestrator test (ABS-302) — Kleinbefunde bundle
# -----------------------------------------------------------------------------
# `source`d by tests/test-orchestrator.sh into the live harness (no shebang, no
# re-`set -e`, no re-source of the harness). Shares assert_*, PASS/FAIL/TOTAL,
# and REPO_ROOT / ORCH / STUB / TRACKER.
#
# Four assertions, one per Kleinbefund:
#   AC1 — kind: header is written correctly (never silently becomes notification)
#   AC2 — every Jira write path uses --data @file (no inline -d with body);
#          äöüß round-trip via jira-tracker.sh's own adf_wrap + adf_to_text code
#   AC3 — account-switch invalidates cached sessions + runlog ACCOUNT-SWITCH
#   AC4 — PushNotification + macOS dialog rule is documented in the operator SOP
# =============================================================================

echo -e "\n${CYAN}=== ABS-302 Kleinbefunde bundle (kind-header / umlaut / account-switch / PushNotification) ===${NC}"

# ---------------------------------------------------------------------------
# AC1: kind: header written correctly — never silently stored as notification.
#
# Round-trip test: write a comment with --kind gate-results, read it back,
# assert the kind header is gate-results (not notification).
#
# Parser-recovery check: grep-verify that jira-tracker.sh's parser has a
# recovery path for a [kind:] header found on a non-first line.
# ---------------------------------------------------------------------------
echo -e "\n  [AC1] kind: header correctness"

new_env
# Title must not contain an id-shaped token — the capture uses | tail -1 to
# grab the last stdout line (the created id), not grep over 2>&1-merged output.
_t302=$(tracker create --type ticket --title "kind-header round-trip" \
    --label orchestrator-ready | tail -1)
tracker comment "$_t302" --kind gate-results --actor be-developer \
    --body "AC1 kind-header round-trip"
_dump302=$(tracker get "$_t302")
assert_contains "$_dump302" "kind: gate-results" \
    "ABS-302 AC1: kind: gate-results preserved on round-trip (not silently notification)"
assert_not_contains "$_dump302" "kind: notification" \
    "ABS-302 AC1: kind: notification not present when gate-results was written"
cleanup_env

# Grep-verify the parser has the ABS-302 recovery path for a header on non-first line.
_precov=$(grep -c 'recovered kind=' "$REPO_ROOT/scripts/jira-tracker.sh" 2>/dev/null || echo 0)
if [ "$_precov" -ge 1 ]; then
    PASS=$((PASS+1)); TOTAL=$((TOTAL+1))
    echo "  PASS ABS-302 AC1: jira-tracker.sh parser has recovery path for header on non-first line"
else
    FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
    echo "  FAIL ABS-302 AC1: jira-tracker.sh parser missing recovery path for header on non-first line"
fi

# ---------------------------------------------------------------------------
# AC2: every Jira write path uses --data @file (no inline -d with body).
#      Plus a round-trip test writing a comment containing äöüß and reading it
#      back byte-identical — via jira-tracker.sh's own adf_wrap (write) and
#      adf_to_text (read) code paths. A tiny JIRA_CURL shim handles network I/O
#      offline, so this test fails if jira-tracker.sh is deleted or misconfigured.
# ---------------------------------------------------------------------------
echo -e "\n  [AC2] umlaut-safe Jira writes (--data @file) + äöüß round-trip via jira-tracker.sh"

# Inline '-d <body>' = the form we must not have.
# pipefail-safe: wrap each grep stage in { ...; } || : so a non-match (exit 1)
# does not propagate through the pipeline — only the count matters.
# The old "|| echo 0" pattern appended a SECOND zero when pipefail fired before
# the `||`, giving "0\n0" ≠ "0" (ABS-302 test-mechanics bug).
_inline_d=$( { grep -- "-d '" "$REPO_ROOT/scripts/jira-tracker.sh" 2>/dev/null || :; } \
    | { grep -v "^[[:space:]]*#" || :; } \
    | { grep -v "tr -d" || :; } \
    | wc -l | tr -d ' ')
assert_eq "$_inline_d" "0" \
    "ABS-302 AC2: no inline '-d <body>' curl calls in scripts/jira-tracker.sh"

# Positive check: --data-binary or --data @file IS present (the safe form).
_data_at=$( { grep -- '--data-binary\|--data @' "$REPO_ROOT/scripts/jira-tracker.sh" 2>/dev/null || :; } \
    | { grep -v "^[[:space:]]*#" || :; } \
    | wc -l | tr -d ' ')
if [ "$_data_at" -ge 1 ]; then
    PASS=$((PASS+1)); TOTAL=$((TOTAL+1))
    echo "  PASS ABS-302 AC2: --data-binary/@file present in jira-tracker.sh ($_data_at uses)"
else
    FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
    echo "  FAIL ABS-302 AC2: --data-binary/@file not found in jira-tracker.sh"
fi

# äöüß round-trip through jira-tracker.sh's adf_wrap + adf_to_text (ABS-302, AC2).
# A minimal JIRA_CURL shim stores the POST /comment body (ADF JSON) and replays
# it as a Jira comment on GET /comment, so adf_to_text in cmd_get decodes it.
# This is NOT the mock-tracker path — deleting jira-tracker.sh breaks this test.
_uml_dir="$(mktemp -d /tmp/abs302-uml-XXXXXX)"
cat > "$_uml_dir/shim.sh" << 'SHIMEOF'
#!/bin/bash
# Minimal round-trip shim: stores POST /comment body, replays on GET /comment.
set -u
SD="${JIRA_SHIM_DIR:?}"
mkdir -p "$SD"
outf=""; meth="GET"; body=""; url=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config)      shift 2;;
        -sS|-s|-S)    shift;;
        -o)            outf="$2"; shift 2;;
        -w)            shift 2;;
        -X)            meth="$2"; shift 2;;
        --data-binary)
            if [ "${2#@}" != "$2" ]; then body="$(cat "${2#@}")"; else body="$2"; fi
            shift 2;;
        *)             url="$1"; shift;;
    esac
done
path="${url#*atlassian.net}"
_emit() { [ -n "$outf" ] && printf '%s' "$2" > "$outf"; printf '%s' "$1"; }
case "$meth $path" in
    "POST /rest/api/3/issue/"*"/comment"*)
        printf '%s' "$body" > "$SD/last-comment.json"
        _emit 201 '{"id":"1","self":"x"}';;
    "GET /rest/api/3/issue/"*"/comment"*)
        if [ -f "$SD/last-comment.json" ]; then
            python3 - "$SD/last-comment.json" "$outf" <<'PYEOF'
import sys, json
src, dst = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
try:
    d = json.load(open(src))
    adf = d.get('body', {})
except Exception:
    adf = {}
resp = json.dumps({'startAt':0,'maxResults':100,'total':1,'comments':[
    {'created':'2026-07-14T10:00:00.000+0000',
     'author':{'displayName':'bot'},
     'body':adf}
]})
if dst:
    open(dst, 'w').write(resp)
PYEOF
        else
            [ -n "$outf" ] && printf '{"startAt":0,"maxResults":100,"total":0,"comments":[]}' > "$outf"
        fi
        printf '200';;
    "GET /rest/api/3/issue/"*)
        _emit 200 '{"key":"ABS-101","fields":{"summary":"umlaut test","status":{"name":"Backlog"},"issuetype":{"name":"Story"},"parent":null,"labels":[],"description":null,"created":"2026-07-14T10:00:00.000+0000","updated":"2026-07-14T10:00:00.000+0000"}}';;
    *)
        _emit 404 '{"errorMessages":["shim: unrouted"]}';;
esac
SHIMEOF
chmod +x "$_uml_dir/shim.sh"

_uml_out=$(
    JIRA_SITE="https://test.atlassian.net" \
    JIRA_EMAIL="test@test.com" \
    JIRA_API_TOKEN="test-token-uml302" \
    JIRA_PROJECT_KEY="ABS" \
    JIRA_SHIM_DIR="$_uml_dir" \
    JIRA_CURL="$_uml_dir/shim.sh" \
    bash "$REPO_ROOT/scripts/jira-tracker.sh" comment ABS-101 \
        --kind gate-results --actor be-developer \
        --body "Umlauts: äöüß" 2>/dev/null \
    && JIRA_SITE="https://test.atlassian.net" \
    JIRA_EMAIL="test@test.com" \
    JIRA_API_TOKEN="test-token-uml302" \
    JIRA_PROJECT_KEY="ABS" \
    JIRA_SHIM_DIR="$_uml_dir" \
    JIRA_CURL="$_uml_dir/shim.sh" \
    bash "$REPO_ROOT/scripts/jira-tracker.sh" get ABS-101 2>/dev/null \
    || true
)
rm -rf "$_uml_dir"

if printf '%s' "$_uml_out" | grep -qF "äöüß"; then
    PASS=$((PASS+1)); TOTAL=$((TOTAL+1))
    echo "  PASS ABS-302 AC2: jira-tracker.sh round-trip preserves äöüß byte-identical (adf_wrap + adf_to_text)"
else
    FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
    echo "  FAIL ABS-302 AC2: äöüß NOT found after jira-tracker.sh round-trip (adf_wrap/adf_to_text)"
fi

# ---------------------------------------------------------------------------
# AC3: account-switch invalidates cached sessions + runlog ACCOUNT-SWITCH.
#
# Scenario:
#   1. Store a fake account id (not matching what current_claude_account() will
#      return) as the last-run account in $SESSIONS_DIR/.account-id.
#   2. Create a fake session file.
#   3. Start the orchestrator (--dry-run --once).
#   4. Assert: the session file is gone (invalidated).
#   5. Assert: run.log contains ACCOUNT-SWITCH with both stored and current ids.
#
# current_claude_account() reads ${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json for
# oauthAccount.accountUuid (composed as uuid@configdir). When the dir has no
# .claude.json it falls back to the dir path itself. Setting CLAUDE_CONFIG_DIR
# to a non-existent temp path exercises the fallback, giving a known current id.
# ---------------------------------------------------------------------------
echo -e "\n  [AC3] account-switch invalidates cached sessions"

new_env
export ORCH_SESSION_RESUME=1
_acct_a="acct-uuid-A-abs302-$$"
_sess_dir="$ORCH_STATE_DIR/sessions"
mkdir -p "$_sess_dir"
printf '%s\n' "$_acct_a" > "$_sess_dir/.account-id"
printf '%s\n%s\n' "fake-session-id-abs302" "old-gen" > "$_sess_dir/FAKE-302.be-developer.In_Progress"
# Point CLAUDE_CONFIG_DIR at a non-existent temp path (no .claude.json there)
# so current_claude_account() falls back to the dir path — a known, distinct value.
_acct_b_dir="/tmp/claude-account-B-abs302-$$"
export CLAUDE_CONFIG_DIR="$_acct_b_dir"
_out302=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 || true)
# Session file must be gone.
[ ! -f "$_sess_dir/FAKE-302.be-developer.In_Progress" ] \
    && { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); \
         echo "  PASS ABS-302 AC3: session file removed after account switch"; } \
    || { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); \
         echo "  FAIL ABS-302 AC3: session file still present after account switch"; }
_rl="$ORCH_STATE_DIR/run.log"
assert_contains "$(cat "$_rl" 2>/dev/null || true)" "ACCOUNT-SWITCH" \
    "ABS-302 AC3: run.log contains ACCOUNT-SWITCH event"
assert_contains "$(cat "$_rl" 2>/dev/null || true)" "stored-account=$_acct_a" \
    "ABS-302 AC3: ACCOUNT-SWITCH line names the stored account"
# current_claude_account() falls back to cfg_dir when no .claude.json is found.
assert_contains "$(cat "$_rl" 2>/dev/null || true)" "current-account=$_acct_b_dir" \
    "ABS-302 AC3: ACCOUNT-SWITCH line names the current account (dir fallback)"
unset CLAUDE_CONFIG_DIR
cleanup_env

# ---------------------------------------------------------------------------
# AC4: PushNotification + macOS dialog rule documented in operator SOP.
#
# pipefail-safe: grep -qF directly on the file instead of cat-into-variable.
# Passing a 160 KB file as a shell argument to assert_contains triggers SIGPIPE
# (printf writes past the grep -q early-exit, gets SIGPIPE=141, pipefail turns
# that into a false FAIL, the FAIL dump SIGPIPEs too, set -e kills the suite
# before printing its tally — ABS-302 test-mechanics bug).
# ---------------------------------------------------------------------------
echo -e "\n  [AC4] PushNotification rule in operator SOP"

_sop="$REPO_ROOT/docs/sop/ORCHESTRATOR_SOP.md"
for _sop_needle in "PushNotification" "osascript" "session-local"; do
    case "$_sop_needle" in
        PushNotification) _sop_desc="PushNotification mentioned" ;;
        osascript)        _sop_desc="osascript (macOS dialog) mentioned" ;;
        session-local)    _sop_desc="session-local watcher rule mentioned" ;;
    esac
    if grep -qF "$_sop_needle" "$_sop" 2>/dev/null; then
        PASS=$((PASS+1)); TOTAL=$((TOTAL+1))
        echo "  PASS ABS-302 AC4: ORCHESTRATOR_SOP.md $_sop_desc"
    else
        FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
        echo "  FAIL ABS-302 AC4: ORCHESTRATOR_SOP.md missing '$_sop_needle'"
    fi
done
