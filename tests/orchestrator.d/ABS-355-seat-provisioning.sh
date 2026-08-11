# =============================================================================
# ABS-355 — seat provisioning: base-freshness guard + env isolation + state-dir
#           self-heal (second live-state wipe, 2026-07-16)
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE INCIDENT (fence-less v2.26.0 run, 2026-07-16 evening)
#   1. Seat worktrees were provisioned from origin/main. origin (Bitbucket) was
#      frozen at a stale tip during an outage while gitlab/main was current — so
#      seats got PRE-RELEASE code, missing the ABS-335 live-state guard.
#   2. Those guard-less checkouts ran tests/tooling/test-orchestrator.sh, which inherited
#      the runner's live ORCH_STATE_DIR/ORCH_STOP_FILE/JIRA_TRACKER_STATE.
#   3. Test teardown/EXIT traps rm -rf'd the LIVE state dir (second wipe of the
#      day), and acquire_lock then fail-closed on the vanished lock parent.
#
# THREE ACs, three sections below:
#   AC1 — provisioning bases on the freshest REACHABLE remote main, never a
#         frozen/unreachable origin (dead-origin seam test + incident replay)
#   AC2 — the spawn seam scrubs live-state vars from the seat env
#   AC3 — the runner self-heals a state dir wiped from under it (+ WARN)
# =============================================================================

echo -e "\n${CYAN}ABS-355 — seat provisioning: base-freshness + env isolation + state-dir self-heal${NC}"

# ---------------------------------------------------------------------------
# Shared helper: call ensure_worktree in an isolated subshell (mirrors ABS-299).
# ---------------------------------------------------------------------------
_abs355_ew() {
    local ticket="$1" target="$2"
    ORCH_TARGET_REPO="$target" \
    ORCH_STATE_DIR="$target/.abs355-orch-state" \
    ORCH_PROTECT_LOCAL_MAIN=0 \
    bash -c '
        mkdir -p "$ORCH_STATE_DIR" 2>/dev/null
        source "$1" >/dev/null 2>&1
        ensure_worktree "$2"
    ' _abs355 "$ORCH" "$ticket" 2>&1
}

_abs355_commit() {   # <repo> <msg> <iso-date>
    GIT_AUTHOR_DATE="$3" GIT_COMMITTER_DATE="$3" \
    git -C "$1" -c user.email=t@t -c user.name=t commit --allow-empty -m "$2" -q
}

# ===========================================================================
# AC1 — Part A: DEAD origin + reachable fresh gitlab → base on gitlab, not the
#               frozen origin (the "Seam-Test mit totem origin")
# ===========================================================================
echo -e "  ${CYAN}AC1a — dead/unreachable origin: provisioning bases on the fresh reachable remote${NC}"
new_env

_ABS355_GITLAB="$(mktemp -d "${TMPDIR:-/tmp}/abs355-gitlab-XXXXXX")"
git -C "$_ABS355_GITLAB" init -q --bare

_ABS355_TARGET="$(mktemp -d "${TMPDIR:-/tmp}/abs355-target-XXXXXX")"
git -C "$_ABS355_TARGET" init -q
_abs355_commit "$_ABS355_TARGET" "release-base" "2026-06-01T00:00:00"
git -C "$_ABS355_TARGET" remote add gitlab "$_ABS355_GITLAB"
git -C "$_ABS355_TARGET" push gitlab HEAD:main -q 2>/dev/null
# origin points at a path that is NOT a git repo → ls-remote fails (dead/frozen).
git -C "$_ABS355_TARGET" remote add origin "${TMPDIR:-/tmp}/abs355-dead-origin-does-not-exist"

_ABS355_FRESH_SHA="$(git -C "$_ABS355_TARGET" rev-parse HEAD)"
# Advance local HEAD (a sibling runner's foreign commit) beyond the remote tip.
_abs355_commit "$_ABS355_TARGET" "foreign-runner-commit" "2026-06-02T00:00:00"
_ABS355_FOREIGN_SHA="$(git -C "$_ABS355_TARGET" rev-parse HEAD)"

# Literal id, NOT `tracker create`: by the time tests/orchestrator.d/*.sh are
# sourced, the harness's ABS-199 section (kept LAST, line ~4581) has already
# `source`d the orchestrator and REPLACED tracker() with a stub whose `create`
# returns EMPTY — so `tracker create` here yields "", ensure_worktree gets a
# blank ticket, and `git worktree add -b -auto` fails ("MISSING"). base
# selection needs a ticket STRING, not a real row, so a literal keeps AC1
# independent of that stub (root cause of the 2026-07-16 review bounce).
_ABS355_T="ABS355STORYA"
_abs355_ew "$_ABS355_T" "$_ABS355_TARGET" || true

_ABS355_TIP="$(git -C "$_ABS355_TARGET" rev-parse --verify "refs/heads/$_ABS355_T-auto" 2>/dev/null || echo MISSING)"
assert_eq "$_ABS355_TIP" "$_ABS355_FRESH_SHA" \
    "ABS-355 AC1a: worktree bases on the reachable fresh remote main (not the dead origin, not foreign HEAD)"
if git -C "$_ABS355_TARGET" merge-base --is-ancestor "$_ABS355_FOREIGN_SHA" "$_ABS355_T-auto" 2>/dev/null; then
    _ABS355_REACH=yes; else _ABS355_REACH=no; fi
assert_eq "$_ABS355_REACH" "no" \
    "ABS-355 AC1a: foreign HEAD commit is NOT dragged into the new branch"

rm -rf "$_ABS355_GITLAB" "$_ABS355_TARGET"
cleanup_env

# ===========================================================================
# AC1 — Part B: incident replay. origin REACHABLE but frozen at an OLDER tip;
#               gitlab reachable and NEWER → base on gitlab (freshest wins).
# ===========================================================================
echo -e "  ${CYAN}AC1b — frozen-but-reachable origin (older) loses to the fresher gitlab${NC}"
new_env

_ABS355_ORIGIN="$(mktemp -d "${TMPDIR:-/tmp}/abs355-origin-XXXXXX")"
git -C "$_ABS355_ORIGIN" init -q --bare
_ABS355_GITLAB="$(mktemp -d "${TMPDIR:-/tmp}/abs355-gitlab-XXXXXX")"
git -C "$_ABS355_GITLAB" init -q --bare

_ABS355_TARGET="$(mktemp -d "${TMPDIR:-/tmp}/abs355-target-XXXXXX")"
git -C "$_ABS355_TARGET" init -q
# commit1 = the STALE tip origin is frozen at (old committer date)
_abs355_commit "$_ABS355_TARGET" "origin-frozen-stale" "2026-06-01T00:00:00"
git -C "$_ABS355_TARGET" remote add origin "$_ABS355_ORIGIN"
git -C "$_ABS355_TARGET" push origin HEAD:main -q 2>/dev/null
_ABS355_STALE_SHA="$(git -C "$_ABS355_TARGET" rev-parse HEAD)"
# commit2 = the FRESH tip gitlab carries (newer committer date)
_abs355_commit "$_ABS355_TARGET" "gitlab-fresh-release" "2026-06-10T00:00:00"
git -C "$_ABS355_TARGET" remote add gitlab "$_ABS355_GITLAB"
git -C "$_ABS355_TARGET" push gitlab HEAD:main -q 2>/dev/null
_ABS355_FRESH_SHA="$(git -C "$_ABS355_TARGET" rev-parse HEAD)"
# commit3 = a local foreign HEAD (newest wall-clock, but on no remote)
_abs355_commit "$_ABS355_TARGET" "foreign-head" "2026-06-11T00:00:00"

# Literal id (see AC1a note): the .d loop runs under the ABS-199 tracker stub, so
# `tracker create` would return "" and MISS the branch.
_ABS355_T="ABS355STORYB"
_abs355_ew "$_ABS355_T" "$_ABS355_TARGET" || true

_ABS355_TIP="$(git -C "$_ABS355_TARGET" rev-parse --verify "refs/heads/$_ABS355_T-auto" 2>/dev/null || echo MISSING)"
assert_eq "$_ABS355_TIP" "$_ABS355_FRESH_SHA" \
    "ABS-355 AC1b: freshest remote (gitlab) wins over the frozen origin tip"
assert_not_contains "$_ABS355_TIP" "$_ABS355_STALE_SHA" \
    "ABS-355 AC1b: the frozen origin tip is NOT chosen as the base"

rm -rf "$_ABS355_ORIGIN" "$_ABS355_GITLAB" "$_ABS355_TARGET"
cleanup_env

# ===========================================================================
# AC2 — the spawn seam scrubs live-state vars from the seat env
# ===========================================================================
echo -e "  ${CYAN}AC2 — spawn seam scrubs live-state vars (ORCH_STATE_DIR/STOP_FILE/RUN_LOG/INSTANCE_ID_FILE/JIRA_TRACKER_STATE)${NC}"

_ABS355_ENVDUMP="$(mktemp "${TMPDIR:-/tmp}/abs355-envdump-XXXXXX")"
_ABS355_DUMPCMD="$(mktemp "${TMPDIR:-/tmp}/abs355-dumpcmd-XXXXXX.sh")"
cat > "$_ABS355_DUMPCMD" <<DUMP
#!/usr/bin/env bash
env > "$_ABS355_ENVDUMP"
exit 0
DUMP
chmod +x "$_ABS355_DUMPCMD"
_ABS355_PF="$(mktemp "${TMPDIR:-/tmp}/abs355-packet-XXXXXX")"
printf 'context packet\n' > "$_ABS355_PF"

# Drive the real run_spawn_cmd choke point with a stub that dumps its env, while
# the RUNNER env carries hostile live-state values. Everything the seam scrubs
# must be absent from the child; the vars the seam sets (ORCH_ROLE/TICKET) prove
# the dump captured a real child env, not an empty file.
env ORCH_STATE_DIR="/live/state/dir-abs355" \
    ORCH_STOP_FILE="/live/state/dir-abs355/stop" \
    ORCH_RUN_LOG="/live/state/dir-abs355/run.log" \
    ORCH_INSTANCE_ID_FILE="/live/state/dir-abs355/instance-id" \
    JIRA_TRACKER_STATE="/live/state/jira-events" \
    ORCH_SPAWN_CMD="$_ABS355_DUMPCMD" \
    ORCH_MODEL="sonnet" \
    ORCH_WORKTREE_SPAWNS=0 \
    ORCH_WATCHDOG_IDLE=0 \
    ORCH_AGENT_TIMEOUT=30 \
    bash -c '
        source "$1" >/dev/null 2>&1
        run_spawn_cmd be-developer ABS355-SEAM "$2" "In Progress" >/dev/null 2>&1
    ' _abs355 "$ORCH" "$_ABS355_PF" || true

for _abs355_v in ORCH_STATE_DIR ORCH_STOP_FILE ORCH_RUN_LOG ORCH_INSTANCE_ID_FILE JIRA_TRACKER_STATE; do
    assert_not_contains "$(cat "$_ABS355_ENVDUMP" 2>/dev/null)" "${_abs355_v}=" \
        "ABS-355 AC2: seat env does NOT contain live-state var $_abs355_v"
done
# Sanity: the child env WAS captured (the seam's own vars survive the scrub).
assert_contains "$(cat "$_ABS355_ENVDUMP" 2>/dev/null)" "ORCH_ROLE=be-developer" \
    "ABS-355 AC2: seat still receives its own ORCH_ROLE (scrub is surgical, not total)"

rm -f "$_ABS355_ENVDUMP" "$_ABS355_DUMPCMD" "$_ABS355_PF"

# ===========================================================================
# AC3 — runner self-heals a state dir wiped from under it (+ WARN); acquire_lock
#       no longer fail-closes on the vanished lock parent.
# ===========================================================================
echo -e "  ${CYAN}AC3 — state-dir self-heal survives a mid-run wipe (no operator)${NC}"

_ABS355_HEAL="$(mktemp -d "${TMPDIR:-/tmp}/abs355-heal-XXXXXX")/work/.orchestrator"
_ABS355_HEAL_OUT="$(ORCH_STATE_DIR="$_ABS355_HEAL" ORCH_INSTANCE_ID="abs355-heal-owner" \
    bash -c '
        source "$1" >/dev/null 2>&1
        mkdir -p "$ORCH_STATE_DIR"
        printf "%s\n" "$ORCH_INSTANCE_ID" > "$ORCH_INSTANCE_ID_FILE"
        rm -rf "$ORCH_STATE_DIR"                       # wipe from under the runner
        heal_state_dir                                  # AC3: recreate + WARN
        if [ -d "$ORCH_STATE_DIR" ]; then echo DIR_OK; fi
        if [ -f "$ORCH_INSTANCE_ID_FILE" ] && \
           [ "$(cat "$ORCH_INSTANCE_ID_FILE")" = "$ORCH_INSTANCE_ID" ]; then echo MARKER_MINE; fi
        rm -rf "$LOCKS_DIR"                             # locks parent gone too
        if acquire_lock ABS355-LOCK; then echo LOCK_OK; fi
    ' _abs355 "$ORCH" 2>&1)"

assert_contains "$_ABS355_HEAL_OUT" "DIR_OK" \
    "ABS-355 AC3: heal_state_dir recreates the wiped state dir"
assert_contains "$_ABS355_HEAL_OUT" "MARKER_MINE" \
    "ABS-355 AC3: self-heal re-stamps OUR instance-id marker (we own it — it was wiped, not taken)"
assert_contains "$_ABS355_HEAL_OUT" "WARN state-dir self-heal" \
    "ABS-355 AC3: self-heal emits a WARN event"
assert_contains "$_ABS355_HEAL_OUT" "LOCK_OK" \
    "ABS-355 AC3: acquire_lock recovers after the lock parent is wiped (no ENOENT fail-close)"

rm -rf "$(dirname "$(dirname "$_ABS355_HEAL")")"

unset _ABS355_GITLAB _ABS355_ORIGIN _ABS355_TARGET _ABS355_T _ABS355_TIP \
      _ABS355_FRESH_SHA _ABS355_FOREIGN_SHA _ABS355_STALE_SHA _ABS355_REACH \
      _ABS355_ENVDUMP _ABS355_DUMPCMD _ABS355_PF _abs355_v \
      _ABS355_HEAL _ABS355_HEAL_OUT
unset -f _abs355_ew _abs355_commit
