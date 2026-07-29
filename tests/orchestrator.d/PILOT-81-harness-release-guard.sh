# =============================================================================
# PILOT-81 — harness-release preflight: a LIVE start is refused unless the
#            governing harness checkout ($ORCH_HARNESS_HOME) is EXACTLY on an
#            annotated release tag with a clean tree, and the resolved harness
#            version (tag+SHA) is stamped into the run.log head.
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live: ABS-594, 2026-07-26)
# The governing stable checkout sat on epic/PILOT-58-... four commits past
# v2.32.0, so a whole pilot ran UNPUBLISHED code while its report claimed the
# release. The operator launcher's guard compared `git describe --tags` against a
# PREFIX ("v2.32"); "v2.32.0-4-g<sha>" matched and passed. A prefix match does not
# prove HEAD is exactly on a release tag with a clean tree.
#
# WHAT PILOT-81 ADDS
#   check_harness_release() in main() (after init_run_id, so RUN-START is first):
#   1. AC1  describe --exact-match --tags HEAD must succeed (prefix is insufficient).
#   2. AC2  status --porcelain must be empty (no uncommitted/untracked change).
#   3. AC3  the check lives in the RUNNER (consumer installs have no launcher).
#   6. AC6  a HARNESS-VERSION run.log line records tag+SHA, pass or fail.
#   Kill switch ORCH_HARNESS_RELEASE_GUARD (default 1); gated on MODE=live.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-81 harness-release preflight guard ===${NC}\n"

# Build a throwaway "harness" checkout the guard will inspect. Only its git state
# matters (HEAD tag + tree cleanliness); it is never spawned into.
_p81_mk_harness() {
    local h; h="$(mktemp -d /tmp/pilot81-harness-XXXXXX)"
    git -C "$h" init -q
    git -C "$h" config user.email t@t.t; git -C "$h" config user.name t
    echo v1 > "$h/VERSION"
    git -C "$h" add -A; git -C "$h" commit -qm "release commit"
    git -C "$h" tag -a v9.9.9 -m "v9.9.9"   # annotated release tag on HEAD
    echo "$h"
}

# --- AC5 case 2: harness on a story branch (past the tag) => start REFUSED -------
new_env
H="$(_p81_mk_harness)"
git -C "$H" checkout -q -b PILOT-99-story
echo change >> "$H/VERSION"; git -C "$H" add -A; git -C "$H" commit -qm "story work"
rc=0
out=$(ORCH_HARNESS_HOME="$H" ORCH_HARNESS_RELEASE_GUARD=1 ORCH_RECONCILE_ON_STARTUP=0 \
    orch --live --once 2>&1) || rc=$?
assert_eq "$rc" "1" "PILOT-81 AC5: story-branch harness => start refused (exit 1)"
assert_contains "$out" "not exactly on an annotated release tag" \
    "PILOT-81 AC1: refusal names the exact-tag failure"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "HARNESS-VERSION" \
    "PILOT-81 AC6: HARNESS-VERSION stamped to run.log even on refusal"
rm -rf "$H"

# --- AC5 case 3: harness on the tag but a DIRTY tree => start REFUSED ------------
new_env
H="$(_p81_mk_harness)"
echo untracked > "$H/scratch.txt"   # untracked change to a versioned path
rc=0
out=$(ORCH_HARNESS_HOME="$H" ORCH_HARNESS_RELEASE_GUARD=1 ORCH_RECONCILE_ON_STARTUP=0 \
    orch --live --once 2>&1) || rc=$?
assert_eq "$rc" "1" "PILOT-81 AC5: dirty harness on tag => start refused (exit 1)"
assert_contains "$out" "working tree is DIRTY" "PILOT-81 AC2: refusal names the dirty tree"
rm -rf "$H"

# --- AC5 case 1: harness EXACTLY on the tag, tree clean => start ALLOWED ---------
new_env
H="$(_p81_mk_harness)"
rc=0
out=$(ORCH_HARNESS_HOME="$H" ORCH_HARNESS_RELEASE_GUARD=1 ORCH_RECONCILE_ON_STARTUP=0 \
    orch --live --once 2>&1) || rc=$?
assert_eq "$rc" "0" "PILOT-81 AC5: clean harness on tag => start allowed (exit 0)"
assert_contains "$out" "harness-release guard: OK" "PILOT-81 AC5: allowed start logs OK"
# AC6: the resolved version is measured, not asserted — tag+SHA in the run.log head.
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "HARNESS-VERSION" \
    "PILOT-81 AC6: HARNESS-VERSION line written to run.log"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "tag=v9.9.9" \
    "PILOT-81 AC6: run.log records the resolved release tag"
rm -rf "$H"

# --- AC (kill switch): guard OFF => a story-branch harness starts anyway ---------
new_env
H="$(_p81_mk_harness)"
git -C "$H" checkout -q -b PILOT-99-story
echo change >> "$H/VERSION"; git -C "$H" add -A; git -C "$H" commit -qm "story work"
rc=0
out=$(ORCH_HARNESS_HOME="$H" ORCH_HARNESS_RELEASE_GUARD=0 ORCH_RECONCILE_ON_STARTUP=0 \
    orch --live --once 2>&1) || rc=$?
assert_eq "$rc" "0" "PILOT-81 kill switch: ORCH_HARNESS_RELEASE_GUARD=0 => legacy start allowed"
rm -rf "$H"
