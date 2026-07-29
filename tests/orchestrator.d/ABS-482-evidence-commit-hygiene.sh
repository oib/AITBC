# =============================================================================
# ABS-482 — QAS/evidence-commit hygiene: a QA report must ride the STORY BRANCH
#           of the ticket under test and carry nothing else.
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/test-orchestrator.sh
# into the live harness — no shebang, no `set -e`, no re-sourcing. Runs in an
# ISOLATED child via _run_d_include (ABS-370). Shares: assert_contains /
# assert_not_contains / assert_eq, PASS/FAIL/TOTAL, REPO_ROOT, ORCH
# (orchestrator.sh path), TRACKER (mock-tracker.sh path), MOCK_TRACKER_STATUSES.
#
# THE INCIDENT (2026-07-19). ABS-461's QA validation report (APPROVED) was
# committed onto ABS-444-docs — a stale leftover branch — instead of the story
# branch ABS-461-auto, and the SAME commit bundled 6 unrelated dirty-workspace
# files (scripts/orchestrator.sh edits, test files: 391 insertions). QA evidence
# riding a wrong branch breaks the evidence chain, and the dirty-workspace files
# smuggle unreviewed runner-script edits toward main.
#
# THE GUARD (runner-side, evidence_commit_failures wired into handoff_followthrough).
# For every commit a handoff CLAIMS that TOUCHES the evidence path
# (docs/agent-outputs/**), the runner refuses the handoff on the ABS-255 mis-report
# path when the commit either (a) bundles non-evidence files, or (b) is not on the
# ticket's own story branch refs/heads/<ticket>-*. Non-evidence (product-code)
# commits are IGNORED so the epic-branch exemption for real work is untouched.
#
# Test method: call the real post-handoff entry point handoff_followthrough()
# directly in a subshell that sources orchestrator.sh, then re-points
# ORCH_STATE_ROOT at a throwaway git repo carrying the incident's exact commit
# shapes on a story branch and a stale foreign branch. Marker-duty gate off, no
# seat lock planted (seat-race guard fails open) — only the evidence-hygiene path
# is under test.
# =============================================================================

echo -e "\n${CYAN}=== ABS-482 QAS/evidence-commit hygiene (branch + allowlist) ===${NC}"

_abs482_dir="$(mktemp -d /tmp/abs482-XXXXXX)"
_abs482_tdir="$_abs482_dir/tickets"
_abs482_repo="$_abs482_dir/repo"
_abs482_hf="$_abs482_dir/handoff.txt"
mkdir -p "$_abs482_tdir"

# _abs482_tracker <args...> — mock tracker backed by the test's isolated dirs.
_abs482_tracker() { MOCK_TRACKER_TICKETS_DIR="$_abs482_tdir" \
    MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" bash "$TRACKER" "$@"; }

_abs482_git() { git -C "$_abs482_repo" "$@"; }

# --- four tickets, one per scenario (fresh ticket => uncontaminated comments) --
# The mock tracker only accepts implementer roles for --role; the ticket's role
# is irrelevant here (the guard is PATH-based, keyed on docs/agent-outputs/**),
# so all four are created as be-developer while the handoff still carries the
# real QAS seat role below.
_abs482_t_refuse=$(_abs482_tracker create --type ticket --title "ABS-482 QA evidence off-branch + bundled" --role be-developer 2>/dev/null)
_abs482_t_accept=$(_abs482_tracker create --type ticket --title "ABS-482 clean QA evidence on story branch" --role be-developer 2>/dev/null)
_abs482_t_exempt=$(_abs482_tracker create --type ticket --title "ABS-482 product-code commit off-branch (exempt)" --role be-developer 2>/dev/null)
_abs482_t_ks=$(_abs482_tracker create --type ticket --title "ABS-482 kill-switch off" --role be-developer 2>/dev/null)

# --- a throwaway git repo carrying the incident's commit shapes ---------------
mkdir -p "$_abs482_repo"
_abs482_git init -q
_abs482_git config user.email "test@example.com"
_abs482_git config user.name "Test"
echo "seed" > "$_abs482_repo/seed.txt"
_abs482_git add seed.txt
_abs482_git commit -qm "base"
_abs482_base="$(_abs482_git rev-parse HEAD)"

# story branches exist (like ABS-461-auto did), plus a stale FOREIGN branch (the
# ABS-444-docs leftover) that carries no relation to the ticket under test.
_abs482_git branch "$_abs482_t_refuse-auto" "$_abs482_base"
_abs482_git branch "$_abs482_t_ks-auto"     "$_abs482_base"
_abs482_git branch "$_abs482_t_exempt-auto" "$_abs482_base"
_abs482_git branch "stale-foreign-docs"     "$_abs482_base"

# CLEAN — a well-behaved QA report: ONLY docs/agent-outputs/** on the story branch.
_abs482_git checkout -q -b "$_abs482_t_accept-auto" "$_abs482_base"
mkdir -p "$_abs482_repo/docs/agent-outputs/qa-validations"
echo "APPROVED" > "$_abs482_repo/docs/agent-outputs/qa-validations/$_abs482_t_accept-qa-validation.md"
_abs482_git add "docs/agent-outputs/qa-validations/$_abs482_t_accept-qa-validation.md"
_abs482_git commit -qm "docs(qa): $_abs482_t_accept validation [ABS-482]"
_abs482_clean="$(_abs482_git rev-parse HEAD)"

# EVIL — the incident: a QA report committed onto the stale FOREIGN branch AND
# bundling unrelated dirty-workspace files (runner-script + a test file).
_abs482_git checkout -q stale-foreign-docs
mkdir -p "$_abs482_repo/docs/agent-outputs/qa-validations" "$_abs482_repo/scripts" "$_abs482_repo/tests"
echo "APPROVED" > "$_abs482_repo/docs/agent-outputs/qa-validations/$_abs482_t_refuse-qa-validation.md"
echo "runner edit" >> "$_abs482_repo/scripts/orchestrator.sh"
echo "test edit"   >  "$_abs482_repo/tests/foo.sh"
_abs482_git add -A
_abs482_git commit -qm "qa evidence + dirty workspace [evil]"
_abs482_evil="$(_abs482_git rev-parse HEAD)"

# CODE — a product-code-only commit, also off the story branch. NOT an evidence
# commit (touches nothing under docs/agent-outputs/**), so the guard must IGNORE
# it: the ABS-255 epic-branch exemption for real work stays intact.
echo "print('x')" > "$_abs482_repo/scripts/bar.sh"
_abs482_git add "scripts/bar.sh"
_abs482_git commit -qm "code only, off-branch"
_abs482_code="$(_abs482_git rev-parse HEAD)"

# _abs482_run <state-dir> <ticket> <to> <role> <extra-env> <handoff>
# Calls handoff_followthrough() in an isolated subshell with ORCH_STATE_ROOT
# re-pointed at the test git repo. <extra-env> is eval'd after the source.
_abs482_run() {
    local sdir="$1" tkt="$2" to="$3" role="$4" extra="$5"
    printf '%s' "$6" > "$_abs482_hf"
    ORCH_STATE_DIR="$sdir" bash -c '
        export ORCH_STATE_DIR="$4"
        source "$1" >/dev/null 2>&1
        ORCH_STATE_ROOT="'"$_abs482_repo"'"   # git checks run against the test repo
        export TRACKER_CMD="$2"
        export MOCK_TRACKER_TICKETS_DIR="$3"
        export MOCK_TRACKER_STATUSES="'"$MOCK_TRACKER_STATUSES"'"
        export ORCH_RUN_LOG="$4/run.log"
        MODE=live
        ORCH_VERIFY_MARKERS=0
        ORCH_RESPAWN_LIMIT=99
        '"$extra"'
        HANDOFF="$(cat "$5")"
        handoff_followthrough "$6" "$7" "$8" "$HANDOFF"
    ' _ "$ORCH" "$TRACKER" "$_abs482_tdir" "$sdir" \
      "$_abs482_hf" "$tkt" "$to" "$role" 2>/dev/null || true
}

_abs482_status() { _abs482_tracker get "$1" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}'; }

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC3: dirty workspace + QA doc committed on a NON-story branch is REFUSED${NC}"
# ---------------------------------------------------------------------------
_abs482_sd1="$_abs482_dir/s1"; mkdir -p "$_abs482_sd1"
_abs482_to_refuse="$(_abs482_status "$_abs482_t_refuse")"
_abs482_h1="## QA Validation — APPROVED
- role: qas
- ticket: $_abs482_t_refuse
- commits: $_abs482_evil
Evidence committed and pushed."
_abs482_run "$_abs482_sd1" "$_abs482_t_refuse" "$_abs482_to_refuse" "qas" "" "$_abs482_h1"
_abs482_dump1="$(_abs482_tracker get "$_abs482_t_refuse" 2>/dev/null)"

assert_contains "$_abs482_dump1" "HANDOFF-MISREPORT" \
    "ABS-482 AC3: an off-branch, file-bundling QA-evidence commit is REFUSED on the mis-report path"
assert_contains "$_abs482_dump1" "not on the story branch" \
    "ABS-482 AC1: the refusal names the off-branch failure (commit must ride refs/heads/<ticket>-*)"
assert_contains "$_abs482_dump1" "bundles" \
    "ABS-482 AC2: the refusal names the foreign-file bundling failure (evidence-path allowlist)"
assert_contains "$_abs482_dump1" "scripts/orchestrator.sh" \
    "ABS-482 AC2: the refusal names the smuggled dirty-workspace file(s) for a clear message"
assert_contains "$_abs482_dump1" "$_abs482_evil" \
    "ABS-482: the refusal names the failing commit hash"
assert_eq "$(_abs482_status "$_abs482_t_refuse")" "$_abs482_to_refuse" \
    "ABS-482 AC3: the declared transition is NOT applied — the ticket rests on its spawn status"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC1/AC2 control: a clean QA report (evidence-only, on the story branch) is ACCEPTED${NC}"
# ---------------------------------------------------------------------------
_abs482_sd2="$_abs482_dir/s2"; mkdir -p "$_abs482_sd2"
_abs482_to_accept="$(_abs482_status "$_abs482_t_accept")"
_abs482_h2="## QA Validation — APPROVED
- role: qas
- ticket: $_abs482_t_accept
- commits: $_abs482_clean
Evidence committed and pushed."
_abs482_run "$_abs482_sd2" "$_abs482_t_accept" "$_abs482_to_accept" "qas" "" "$_abs482_h2"
assert_not_contains "$(_abs482_tracker get "$_abs482_t_accept" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "ABS-482 control: an evidence-only commit ON the story branch is never refused"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Regression: a product-code commit off the story branch is IGNORED (epic-branch exemption intact)${NC}"
# ---------------------------------------------------------------------------
_abs482_sd3="$_abs482_dir/s3"; mkdir -p "$_abs482_sd3"
_abs482_to_exempt="$(_abs482_status "$_abs482_t_exempt")"
_abs482_h3="## Implementation handoff
- role: be-developer
- ticket: $_abs482_t_exempt
- commits: $_abs482_code
Committed and pushed."
_abs482_run "$_abs482_sd3" "$_abs482_t_exempt" "$_abs482_to_exempt" "be-developer" "" "$_abs482_h3"
assert_not_contains "$(_abs482_tracker get "$_abs482_t_exempt" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "ABS-482 regression: a NON-evidence (product-code) commit is not subject to the evidence-branch guard"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Kill switch: ORCH_VERIFY_EVIDENCE=0 restores the pre-ABS-482 behaviour${NC}"
# ---------------------------------------------------------------------------
_abs482_sd4="$_abs482_dir/s4"; mkdir -p "$_abs482_sd4"
_abs482_to_ks="$(_abs482_status "$_abs482_t_ks")"
_abs482_h4="## QA Validation — APPROVED
- role: qas
- ticket: $_abs482_t_ks
- commits: $_abs482_evil
Evidence committed and pushed."
_abs482_run "$_abs482_sd4" "$_abs482_t_ks" "$_abs482_to_ks" "qas" "ORCH_VERIFY_EVIDENCE=0" "$_abs482_h4"
assert_not_contains "$(_abs482_tracker get "$_abs482_t_ks" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "ABS-482 kill-switch: ORCH_VERIFY_EVIDENCE=0 disables the evidence-hygiene refusal"

rm -rf "$_abs482_dir"
unset _abs482_dir _abs482_tdir _abs482_repo _abs482_hf _abs482_base \
      _abs482_t_refuse _abs482_t_accept _abs482_t_exempt _abs482_t_ks \
      _abs482_clean _abs482_evil _abs482_code \
      _abs482_sd1 _abs482_sd2 _abs482_sd3 _abs482_sd4 \
      _abs482_to_refuse _abs482_to_accept _abs482_to_exempt _abs482_to_ks \
      _abs482_h1 _abs482_h2 _abs482_h3 _abs482_h4 _abs482_dump1
unset -f _abs482_tracker _abs482_git _abs482_run _abs482_status
