# =============================================================================
# ABS-377 — ensure_worktree re-provisions .claude/settings.local.json into a
#            REUSED seat worktree that predates the v2.26.1 provisioning fix
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS
# ensure_worktree() returned early — `[ -d "$wt" ] && return 0` — for a worktree
# that already exists on disk, WITHOUT provisioning .claude/settings.local.json.
# A tmp/<ticket>-work reused from before the v2.26.1 provisioning fix carried
# only settings.template.json, so every mutation tool-call in the dispatched seat
# was denied under --permission-mode dontAsk. ABS-348 ran two NOMOVE->NPD
# escalation rounds on exactly this (16.-17.07.) and the operator hand-copied the
# file.
#
# THE FIX
# The existing-worktree branch now heals: when .claude/settings.local.json is
# absent it re-provisions via provision_worktree_settings (the SAME mechanism as
# fresh creation) and emits a SEAT-SETTINGS-HEAL run.log line. Keyed on the
# file's absence, so an already-provisioned reuse is a no-op (no heal line).
#
# TWO SCENARIOS
#   Part A — reused worktree missing settings.local.json: dispatch re-provisions
#            it from the main checkout + SEAT-SETTINGS-HEAL logged
#   Part B — reused worktree already has settings.local.json: no-op, no heal line
# =============================================================================

echo -e "\n${CYAN}ABS-377 — ensure_worktree heals settings.local.json in a reused seat worktree${NC}"

# ---------------------------------------------------------------------------
# Helper: call ensure_worktree in an isolated subshell against $target as the
# main checkout (ORCH_STATE_ROOT follows ORCH_TARGET_REPO), with ORCH_RUN_LOG
# pinned to $runlog so the SEAT-SETTINGS-HEAL line is assertable. $ORCH is
# visible from the harness scope. Combined stdout+stderr merged so log() output
# is capturable.
# ---------------------------------------------------------------------------
_abs377_ew() {
    local ticket="$1" target="$2" runlog="$3"
    ORCH_TARGET_REPO="$target" \
    ORCH_STATE_DIR="$target/.abs377-orch-state" \
    ORCH_RUN_LOG="$runlog" \
    ORCH_PROTECT_LOCAL_MAIN=0 \
    bash -c '
        mkdir -p "$ORCH_STATE_DIR" 2>/dev/null
        source "$1" >/dev/null 2>&1
        ensure_worktree "$2"
    ' _abs377 "$ORCH" "$ticket" 2>&1
}

# ---------------------------------------------------------------------------
# Part A — reused worktree WITHOUT settings.local.json: heal on dispatch
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Part A — reused worktree missing settings.local.json: dispatch re-provisions it${NC}"
new_env

_ABS377_TARGET="$(mktemp -d "${TMPDIR:-/tmp}/abs377-target-XXXXXX")"
# Sourcing orchestrator.sh validates ORCH_TARGET_REPO is a git repo root, so the
# target must be a real (if empty) repo — the heal path returns before any git op.
git -C "$_ABS377_TARGET" init -q
git -C "$_ABS377_TARGET" -c user.email=t@t -c user.name=t commit --allow-empty -m base -q
# Main checkout source that provision_worktree_settings copies from
# ($ORCH_STATE_ROOT/.claude/settings.local.json). Valid JSON with a marker key
# that survives the jq allow-grant merge, proving the healed file came from here.
mkdir -p "$_ABS377_TARGET/.claude"
printf '%s\n' '{"_abs377_marker":"MAIN-CHECKOUT-SOURCE","permissions":{"allow":[]}}' \
    > "$_ABS377_TARGET/.claude/settings.local.json"

# A pre-v2.26.1 reused worktree: exists on disk, .claude/ carries ONLY the
# template, no settings.local.json.
_ABS377_WT="$_ABS377_TARGET/tmp/ABS377STORYA-work"
mkdir -p "$_ABS377_WT/.claude"
printf '%s\n' '{"note":"template only, no local grants"}' \
    > "$_ABS377_WT/.claude/settings.template.json"

_ABS377_RUNLOG="$(mktemp "${TMPDIR:-/tmp}/abs377-runlog-XXXXXX")"
_abs377_ew "ABS377STORYA" "$_ABS377_TARGET" "$_ABS377_RUNLOG" >/dev/null 2>&1 || true

_ABS377_HEALED=no
[ -f "$_ABS377_WT/.claude/settings.local.json" ] && _ABS377_HEALED=yes
assert_eq "$_ABS377_HEALED" "yes" \
    "ABS-377 A1: reused worktree gets settings.local.json provisioned on dispatch"

assert_contains "$(cat "$_ABS377_WT/.claude/settings.local.json" 2>/dev/null)" "MAIN-CHECKOUT-SOURCE" \
    "ABS-377 A2: healed file was provisioned from the main checkout (same mechanism)"

assert_contains "$(cat "$_ABS377_RUNLOG" 2>/dev/null)" "SEAT-SETTINGS-HEAL" \
    "ABS-377 A3: SEAT-SETTINGS-HEAL run.log line documents the re-provisioning"

rm -rf "$_ABS377_TARGET" "$_ABS377_RUNLOG"
cleanup_env

# ---------------------------------------------------------------------------
# Part B — reused worktree that ALREADY has settings.local.json: no-op
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Part B — reused worktree already provisioned: no heal, no SEAT-SETTINGS-HEAL line${NC}"
new_env

_ABS377_TARGET="$(mktemp -d "${TMPDIR:-/tmp}/abs377-target-XXXXXX")"
git -C "$_ABS377_TARGET" init -q
git -C "$_ABS377_TARGET" -c user.email=t@t -c user.name=t commit --allow-empty -m base -q
mkdir -p "$_ABS377_TARGET/.claude"
printf '%s\n' '{"permissions":{"allow":[]}}' \
    > "$_ABS377_TARGET/.claude/settings.local.json"

_ABS377_WT="$_ABS377_TARGET/tmp/ABS377STORYB-work"
mkdir -p "$_ABS377_WT/.claude"
printf '%s\n' '{"_abs377_marker":"ALREADY-PRESENT","permissions":{"allow":[]}}' \
    > "$_ABS377_WT/.claude/settings.local.json"

_ABS377_RUNLOG="$(mktemp "${TMPDIR:-/tmp}/abs377-runlog-XXXXXX")"
_abs377_ew "ABS377STORYB" "$_ABS377_TARGET" "$_ABS377_RUNLOG" >/dev/null 2>&1 || true

assert_not_contains "$(cat "$_ABS377_RUNLOG" 2>/dev/null)" "SEAT-SETTINGS-HEAL" \
    "ABS-377 B1: an already-provisioned reuse is a no-op (no SEAT-SETTINGS-HEAL line)"
assert_contains "$(cat "$_ABS377_WT/.claude/settings.local.json" 2>/dev/null)" "ALREADY-PRESENT" \
    "ABS-377 B2: the existing settings.local.json is left untouched (not overwritten)"

rm -rf "$_ABS377_TARGET" "$_ABS377_RUNLOG"
cleanup_env

unset _ABS377_TARGET _ABS377_WT _ABS377_RUNLOG _ABS377_HEALED
unset -f _abs377_ew
