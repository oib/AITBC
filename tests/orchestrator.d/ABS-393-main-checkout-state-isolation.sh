# =============================================================================
# ABS-393 — main-checkout seat state isolation (third live-state wipe, 2026-07-17)
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE INCIDENT (v2.26.1 run, 2026-07-17T17:07:13Z)
#   The ABS-355 env-scrub (`env -u ORCH_STATE_DIR ...`) isolates seat WORKTREES:
#   their DEFAULT ${ORCH_STATE_DIR:-$ROOT/work/.orchestrator} re-derives a
#   worktree-local path. But rte/tech-writer/bsa seats run IN the main checkout,
#   so REPO_ROOT == the runner's live state root and the same default re-derives
#   the LIVE dir. An epic-integration RTE seat's suite/cleanup trap then rm'd the
#   ledger/locks/sessions/packets/instance-id (run.log survived) — a PARTIAL wipe:
#   the day budget counter fell to 0 and the TDM visited-throttle vanished.
#
# FIX (three ACs verified below):
#   AC2 — main-checkout seat's default ORCH_STATE_DIR is REDIRECTED to a throwaway
#         root (extends the ABS-205 nested-isolation re-pin), so a seat cleanup
#         trap can no longer touch the live dir; worktree seats keep ABS-205.
#   AC3 — self-heal distinguishes a PARTIAL wipe from a FULL one and names the
#         recreated components (forensic line, not a blanket WARN).
#   AC4 — the wiped spawn-ledger is reconstructed from run.log (budget preserved)
#         instead of silently recreated empty (== 0 == full budget re-opened).
# =============================================================================

echo -e "\n${CYAN}ABS-393 — main-checkout seat state isolation: redirect + forensic self-heal + ledger rebuild${NC}"

# A repo-root-looking dir (has .git + work/tickets) with a COPY of orchestrator.sh
# under scripts/, so a sourced copy resolves REPO_ROOT to it. Prints the path.
_abs393_repo() {
    local d; d="$(mktemp -d "${TMPDIR:-/tmp}/abs393-repo-XXXXXX")"
    # Normalize exactly as orchestrator.sh derives REPO_ROOT (`cd .. && pwd`): a
    # trailing-slash $TMPDIR (macOS) yields a `//` that pwd collapses, so an
    # un-normalized path here would string-differ from the child's REPO_ROOT and
    # misclassify a main-checkout seat as a worktree seat (mirrors the ABS-205 test's
    # clean-/tmp convention).
    d="$(cd "$d" && pwd)"
    mkdir -p "$d/.git" "$d/scripts" "$d/work/tickets"
    cp "$ORCH" "$d/scripts/orchestrator.sh"
    echo "$d"
}

# ---------------------------------------------------------------------------
# AC2 — a MAIN-CHECKOUT nested seat (REPO_ROOT == parent state root) redirects
#       its DEFAULT ORCH_STATE_DIR OFF the live dir; a worktree seat is unchanged.
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC2 — main-checkout seat redirects its default state dir to a throwaway${NC}"
new_env

_ABS393_LIVE="$(_abs393_repo)"          # the main checkout == parent state root
_ABS393_LEDGER="$_ABS393_LIVE/work/.orchestrator/spawn-ledger-$(date -u +%Y%m%d)"
mkdir -p "$_ABS393_LIVE/work/.orchestrator"
printf 'a\nb\nc\nd\ne\n' > "$_ABS393_LEDGER"   # a live day-budget in flight (5 spawns)

# Simulate a main-checkout seat: the ABS-355 scrub unset ORCH_STATE_DIR, the inherited
# ORCH_PARENT_STATE_ROOT sentinel is present, and REPO_ROOT (the sourced copy) == that
# sentinel. A suite/cleanup trap then rm's the DEFAULT ledger path. With the ABS-393
# redirect the default lands on a throwaway, so the LIVE ledger must survive.
_ABS393_SD="$(env -u ORCH_STATE_DIR -u ORCH_STOP_FILE -u ORCH_RUN_LOG -u ORCH_INSTANCE_ID_FILE \
    ORCH_TARGET_REPO="$_ABS393_LIVE" ORCH_PARENT_STATE_ROOT="$_ABS393_LIVE" \
    bash -c '
        source "$1" >/dev/null 2>&1
        rm -f "$ORCH_STATE_DIR"/spawn-ledger-* 2>/dev/null || true   # seat cleanup trap
        printf "%s\n" "$ORCH_STATE_DIR"
    ' _abs393 "$_ABS393_LIVE/scripts/orchestrator.sh")"

assert_not_contains "$_ABS393_SD" "$_ABS393_LIVE/work/.orchestrator" \
    "ABS-393 AC2: main-checkout seat's default ORCH_STATE_DIR is redirected OFF the live dir"
assert_eq "$([ -f "$_ABS393_LEDGER" ] && echo yes || echo no)" "yes" \
    "ABS-393 AC2: a main-checkout seat cleanup trap can no longer wipe the LIVE spawn-ledger"

# Control: a WORKTREE seat (repo root != parent) keeps the ABS-205 re-pin to its OWN tree.
_ABS393_WT="$(_abs393_repo)"
_ABS393_WSD="$(env -u ORCH_STATE_DIR \
    ORCH_TARGET_REPO="$_ABS393_LIVE" ORCH_PARENT_STATE_ROOT="$_ABS393_LIVE" \
    bash -c 'source "$1" >/dev/null 2>&1; printf "%s\n" "$ORCH_STATE_DIR"' \
    _abs393 "$_ABS393_WT/scripts/orchestrator.sh")"
assert_contains "$_ABS393_WSD" "$_ABS393_WT/work/.orchestrator" \
    "ABS-393 AC2 (regression): a worktree seat still pins state under its OWN tree (ABS-205 intact)"

rm -rf "$_ABS393_LIVE" "$_ABS393_WT"

# ---------------------------------------------------------------------------
# ABS-415 — harden the seat-classification seam:
#   (a) a TRAILING-SLASH ORCH_TARGET_REPO still classifies as a main-checkout seat
#       (trailing slash normalized before the compare) and still redirects state;
#   (b) the throwaway base is a real `mktemp -d` directory (atomic, exists on disk),
#       not the old predictable ${TMPDIR}/orch-seat-state-$$-$RANDOM interpolation
#       (which was only a string and never created a directory).
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}ABS-415 — trailing-slash classification + non-guessable mktemp -d base${NC}"

_ABS415_LIVE="$(_abs393_repo)"          # the main checkout == parent state root
_ABS415_LEDGER="$_ABS415_LIVE/work/.orchestrator/spawn-ledger-$(date -u +%Y%m%d)"
mkdir -p "$_ABS415_LIVE/work/.orchestrator"
printf 'a\nb\nc\nd\ne\n' > "$_ABS415_LEDGER"   # a live day-budget in flight (5 spawns)

# Same main-checkout seat as AC2 but ORCH_TARGET_REPO carries a TRAILING SLASH. Without
# the ABS-415 normalization the seam would compare unequal and misclassify this as a
# worktree seat, defeating the redirect. Print both ORCH_STATE_DIR and the throwaway base.
_ABS415_OUT="$(env -u ORCH_STATE_DIR -u ORCH_STOP_FILE -u ORCH_RUN_LOG -u ORCH_INSTANCE_ID_FILE \
    ORCH_TARGET_REPO="$_ABS415_LIVE/" ORCH_PARENT_STATE_ROOT="$_ABS415_LIVE" \
    bash -c '
        source "$1" >/dev/null 2>&1
        rm -f "$ORCH_STATE_DIR"/spawn-ledger-* 2>/dev/null || true   # seat cleanup trap
        # the throwaway base is two levels up from $base/work/.orchestrator
        _base="$(dirname "$(dirname "$ORCH_STATE_DIR")")"
        printf "%s\n" "$ORCH_STATE_DIR"
        printf "BASE_IS_DIR=%s\n" "$([ -d "$_base" ] && echo yes || echo no)"
    ' _abs415 "$_ABS415_LIVE/scripts/orchestrator.sh")"
_ABS415_SD="$(printf '%s\n' "$_ABS415_OUT" | head -n1)"

assert_not_contains "$_ABS415_SD" "$_ABS415_LIVE/work/.orchestrator" \
    "ABS-415: a trailing-slash ORCH_TARGET_REPO still classifies as a main-checkout seat and redirects OFF the live dir"
assert_eq "$([ -f "$_ABS415_LEDGER" ] && echo yes || echo no)" "yes" \
    "ABS-415: with the trailing slash normalized, a seat cleanup trap still cannot wipe the LIVE spawn-ledger"
assert_contains "$_ABS415_OUT" "BASE_IS_DIR=yes" \
    "ABS-415: the throwaway base is a real mktemp -d directory on disk, not the predictable interpolated string"

rm -rf "$_ABS415_LIVE"
# clean up the mktemp -d throwaway the seat created (dirname twice off ORCH_STATE_DIR)
rm -rf "$(dirname "$(dirname "$_ABS415_SD")")" 2>/dev/null || true
unset _ABS415_LIVE _ABS415_LEDGER _ABS415_OUT _ABS415_SD

cleanup_env

# ---------------------------------------------------------------------------
# AC3 + AC4 — self-heal reports partial-vs-full, names recreated components, and
#             reconstructs the spawn-ledger from run.log (budget preserved).
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC3/AC4 — forensic self-heal + spawn-ledger reconstruction${NC}"

_ABS393_HEAL="$(mktemp -d "${TMPDIR:-/tmp}/abs393-heal-XXXXXX")/work/.orchestrator"
_ABS393_RUNLOG="$(mktemp "${TMPDIR:-/tmp}/abs393-runlog-XXXXXX")"
_ABS393_DAY="$(date -u +%Y-%m-%d)"
# 3 of today's INTENT-SPAWN events + noise the counter must ignore (a LOG row and a
# stale-day spawn). run.log is TSV: <timestamp>\t<event>\t<ticket>\t<role>\t<to>\t<note>.
printf '%s\tINTENT-SPAWN\tABS-1\tbe-developer\tIn Progress\t-\n' "${_ABS393_DAY}T10:00:01Z" >> "$_ABS393_RUNLOG"
printf '%s\tINTENT-SPAWN\tABS-2\tqas\tIn Test\t-\n'              "${_ABS393_DAY}T10:00:02Z" >> "$_ABS393_RUNLOG"
printf '%s\tINTENT-SPAWN\tABS-3\trte\tReady for Merge\t-\n'      "${_ABS393_DAY}T10:00:03Z" >> "$_ABS393_RUNLOG"
printf '%s\tLOG\t-\t-\t-\tnot a spawn\n'                         "${_ABS393_DAY}T10:00:04Z" >> "$_ABS393_RUNLOG"
printf '%s\tINTENT-SPAWN\tABS-old\tbe\tX\t-\n'                   "2020-01-01T10:00:00Z"      >> "$_ABS393_RUNLOG"

_ABS393_HEAL_OUT="$(ORCH_STATE_DIR="$_ABS393_HEAL" ORCH_RUN_LOG="$_ABS393_RUNLOG" \
    ORCH_INSTANCE_ID="abs393-heal-owner" bash -c '
        source "$1" >/dev/null 2>&1
        mkdir -p "$ORCH_STATE_DIR" "$LOCKS_DIR" "$PACKETS_DIR" "$SESSIONS_DIR"
        printf "%s\n" "$ORCH_INSTANCE_ID" > "$ORCH_INSTANCE_ID_FILE"
        # PARTIAL wipe: substructure + marker gone, the top-level dir survives (mirrors
        # the incident where run.log survived but locks/sessions/packets/ledger did not).
        rm -rf "$LOCKS_DIR" "$SESSIONS_DIR" "$PACKETS_DIR" "$ORCH_INSTANCE_ID_FILE"
        heal_state_dir
        echo "LEDGER_LINES=$(wc -l < "$(daily_ledger)" | tr -d " ")"
    ' _abs393 "$ORCH" 2>&1)"

assert_contains "$_ABS393_HEAL_OUT" "partial wipe" \
    "ABS-393 AC3: self-heal reports a PARTIAL wipe when the dir survives but substructure is gone"
assert_contains "$_ABS393_HEAL_OUT" "locks/" \
    "ABS-393 AC3: forensic line names the recreated locks/ component"
assert_contains "$_ABS393_HEAL_OUT" "sessions/" \
    "ABS-393 AC3: forensic line names the recreated sessions/ component"
assert_contains "$_ABS393_HEAL_OUT" "instance-id" \
    "ABS-393 AC3: forensic line names the recreated instance-id component"
assert_contains "$_ABS393_HEAL_OUT" "spawn-ledger reconstructed from run.log (3 entries" \
    "ABS-393 AC4: spawn-ledger reconstructed from today's 3 INTENT-SPAWN events (noise ignored)"
assert_contains "$_ABS393_HEAL_OUT" "LEDGER_LINES=3" \
    "ABS-393 AC4: reconstructed ledger line count is accurate so daily_budget_exhausted stays correct"

rm -rf "$(dirname "$(dirname "$_ABS393_HEAL")")" "$_ABS393_RUNLOG"

unset _ABS393_LIVE _ABS393_LEDGER _ABS393_SD _ABS393_WT _ABS393_WSD \
      _ABS393_HEAL _ABS393_RUNLOG _ABS393_DAY _ABS393_HEAL_OUT
unset -f _abs393_repo
