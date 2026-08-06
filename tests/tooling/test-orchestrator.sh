#!/bin/bash
# =============================================================================
# Test: Orchestrator event loop (ABS-52 / ABS-53 / ABS-54)
# =============================================================================
# Drives scripts/orchestrator.sh against the mock task-tracking adapter with a
# temp ticket store and a STUB spawn command (tests/fixtures/stub-spawn.sh) —
# never a real model. Exercises the spec (specs/ABS-36-orchestrator-spec.md):
#   §2 mapping (SPAWN / NOOP / SPAWN-then-NOTIFY), §2.2 role selection,
#   §5.2 single-flight lock, §5.3 kill switch, §5.4 spawn budget,
#   §5.5 iteration-guard -> Blocked, §5.1 concurrency defer + reconciliation,
#   §6 retry-once-then-escalate, and dry-run vs --live handoff posting.
#
# Run from repo root: bash tests/tooling/test-orchestrator.sh
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

# ABS-335: LIVE-STATE REFUSAL GATE — runs BEFORE the ORCH_*/JIRA_* scrub below
# (the scrub would erase the very evidence this gate reads). On 2026-07-16 a seat
# ran this suite without an env scrub while ORCH_STATE_DIR still pointed at a LIVE
# orchestrator: the mock intents (DEMO-2/3/4) landed in the live run.log and the
# run took the real spawn path. This gate makes that mechanically impossible: if
# the AMBIENT env resolves to a state dir whose instance-id marker has a still-live
# owner process (ADR-A-0026 P13 liveness: a marker is honoured only while its
# process is alive), refuse loudly and exit non-zero before any test runs. A stale
# marker (dead owner) or no marker starts the suite normally.
_ls_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ls_state_dir="${ORCH_STATE_DIR:-${ORCH_TARGET_REPO:-$_ls_repo_root}/work/.orchestrator}"
_ls_iid_file="$_ls_state_dir/instance-id"
if [ -s "$_ls_iid_file" ]; then
    _ls_iid="$(head -n1 "$_ls_iid_file")"
    # mint_instance_id() format is <host>-<pid>-<rand>; the pid is the
    # second-to-last '-' field, robust to hostnames that contain dashes.
    _ls_pid="$(printf '%s\n' "$_ls_iid" | awk -F- '{print $(NF-1)}')"
    if [ -n "$_ls_pid" ] && kill -0 "$_ls_pid" 2>/dev/null; then
        echo "ERROR (ABS-335): refusing to run — ambient env points at a LIVE orchestrator state dir." >&2
        echo "  state dir : $_ls_state_dir" >&2
        echo "  instance  : $_ls_iid (owner pid $_ls_pid is alive)" >&2
        echo "  Running the suite here would write mock intents into the live run.log." >&2
        echo "  Unset ORCH_STATE_DIR and re-run with a scrubbed env (env -i PATH=... HOME=...)." >&2
        exit 1
    fi
fi
unset _ls_repo_root _ls_state_dir _ls_iid_file _ls_iid _ls_pid
# ABS-335 self-test hook: exit 0 immediately after the gate (no full-suite run).
# The gate above still fires first, so a live owner exits non-zero regardless.
# tests/orchestrator.d/ABS-335-live-state-guard.sh uses this to assert the gate
# verdict fast. Read BEFORE the scrub because the gate is.
if [ -n "${LIVESTATE_GUARD_SELFTEST:-}" ]; then
    echo "ABS-335: live-state gate passed (no live owner)"; exit 0
fi

# ABS-286/ABS-291: results must be a function of the COMMIT, not of the SEAT.
# An orchestrator seat exports 70+ ORCH_* vars (ORCH_MAX_TURNS_QAS,
# ORCH_REQUIRE_START_LABEL, ORCH_HARNESS_HOME, …) that leak into the runner
# under test and flip assertions depending on WHO runs the suite. Prefix-unset
# (bash 3.2-safe, proven across nine files in ABS-285) instead of the
# enumerated 44-name list, which missed 67 of the 109 read variables —
# including ORCH_OVERRIDES_DIR, the leaker ABS-285 found. Tests that need an
# ORCH_* value set (and clean up) their own, explicitly.
unset "${!ORCH_@}"
# ABS-335: also scrub JIRA_* (JIRA_SITE/JIRA_API_TOKEN/…). A seat's live Jira
# credentials must never leak into a suite that drives the tracker adapter;
# prefix-unset (bash 3.2-safe, same idiom as the ORCH_* scrub) so the result is
# a function of the commit, not of who ran it.
unset "${!JIRA_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"
# ABS-111: the legacy suite body encodes the SYNCHRONOUS scheduling semantics
# (same-ticket sequential spawns, fixed per-cycle spawn counts) — pin the
# legacy modes so those guarantees stay asserted verbatim. The new default-on
# behaviors (async spawns, depends_on gate, session resume, worktree
# provisioning) are exercised in their own "ABS-111" section near the end.
export ORCH_ASYNC_SPAWNS=0
export ORCH_DEPENDS_GATING=0
export ORCH_SESSION_RESUME=0
export ORCH_WORKTREE_SPAWNS=0
# PILOT-81: the harness-release preflight fail-closes a live start unless the
# harness checkout is exactly on a release tag with a clean tree. This suite runs
# --live scenarios from the DEV checkout (not on a tag), so disable it here; its
# own behavior is covered by tests/orchestrator.d/PILOT-81-harness-release-guard.sh,
# which re-enables it against a purpose-built temp repo. (Exported here so the
# orchestrator.d/* story-includes running in child processes inherit it.)
export ORCH_HARNESS_RELEASE_GUARD=0

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    # ABS-310 D2: match via here-string, never `echo "$output" | grep` — a pipe
    # into grep -q (which short-circuits) makes echo take SIGPIPE, and under a
    # leaked `pipefail` (D1) that turns a PRESENT match into a false FAIL. A
    # here-string is file-backed: no pipe, no early-closing reader, no SIGPIPE.
    if grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -20 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    # ABS-310 D2: see assert_contains — here-string match, SIGPIPE-proof.
    if ! grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -20 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

# ABS-370: run a `tests/orchestrator.d/*.sh` story-include in an ISOLATED child so
# an abort under `set -e` (an unexpected non-zero command — e.g. a stray same-status
# tracker transition — or a `exit` in the include) cannot kill the include loop and
# SILENTLY drop every later file. That was the false-green hole: the loop died at
# the ABS-295->296 boundary, ~19 later includes never ran, yet the aggregate tally
# still printed a green-looking summary while the process exited non-zero.
#
# The child subshell inherits the whole harness (functions, exported env, and the
# current PASS/FAIL/TOTAL by value); on CLEAN completion it writes its cumulative
# counters to a marker file which we adopt. A child that ABORTS never reaches the
# marker write -> empty marker -> we record ONE failure for that include and keep
# going (fail loud, not silent). Returns 0 when the include completed, 1 on abort.
_run_d_include() {
    local file="$1" marker rc=0
    marker="$(mktemp "${TMPDIR:-/tmp}/orch-dinc-XXXXXX")"
    # The subshell is the condition of `if`, so the parent's errexit is suppressed
    # for it (a non-zero child cannot abort the loop); errexit stays ON *inside*
    # the child, matching every include's historical semantics.
    if ( set -e; source "$file"; printf 'PASS=%s\nFAIL=%s\nTOTAL=%s\n' "$PASS" "$FAIL" "$TOTAL" >"$marker" ); then :; else :; fi
    if [ -s "$marker" ]; then
        # shellcheck disable=SC1090
        . "$marker"     # adopt the child's cumulative PASS/FAIL/TOTAL
    else
        echo -e "  ${RED}FAIL${NC} $(basename "$file"): story include ABORTED under set -e (non-zero/exit); later includes were NOT skipped (ABS-370)"
        FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); rc=1
    fi
    rm -f "$marker"
    return "$rc"
}

# Per-test isolated environment. Sets a fresh ticket store + orchestrator state,
# then baseline-polls events so ticket creations don't leak into the scenario.
new_env() {
    TEST_DIR="$(mktemp -d /tmp/orchestrator-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    # State isolation: a self-hosting harness pins ORCH_RUN_LOG to the target
    # repo's run.log; drop it so the per-test $ORCH_STATE_DIR/run.log default
    # applies and run.log assertions see this scenario's events only.
    unset ORCH_RUN_LOG
    # Reset any knobs a prior test set.
    unset ORCH_MAX_CONCURRENT ORCH_MAX_SPAWNS_PER_RUN ORCH_SPAWN_CMD ORCH_NOTIFY_TICKET
    unset ORCH_PRIORITY_DISPATCH ORCH_HOTFIX_CAP_BONUS   # ABS-261 priority dispatch (NOT ORCH_ASYNC_SPAWNS: the suite pins it =0 globally at line 41)
    unset ORCH_RECONCILE_ON_STARTUP ORCH_RECONCILE_EVERY_N_CYCLES STUB_RECORD_FILE
    unset STUB_FAIL STUB_HANG STUB_HANG_SECONDS STUB_NO_HANDOFF STUB_MAX_TURNS_EXIT STUB_TRANSITION_TO
    unset STUB_MAX_TURNS STUB_SALVAGE_FAIL ORCH_SALVAGE_MAX_TURNS   # ABS-175 turn-cap salvage
    unset STUB_HANDOFF_TO ORCH_RESPAWN_LIMIT ORCH_HANDOFF_TRANSITION
    unset STUB_USAGE STUB_TOKENS_IN STUB_TOKENS_OUT STUB_COST
    unset STUB_TOOLS_FILE ORCH_REVIEW_TOOLS ORCH_TOOLS STUB_TURNS_FILE
    unset ORCH_MAX_TURNS ORCH_MAX_TURNS_IMPLEMENTER ORCH_MAX_TURNS_BE_DEVELOPER
    unset ORCH_REWORK_LIMIT ORCH_CRASH_LIMIT ORCH_MAX_SPAWNS_PER_DAY ORCH_AGENT_TIMEOUT
    unset ORCH_AGENT_TIMEOUT_BE_DEVELOPER   # ABS-157 per-seat watchdog override
    unset ORCH_WATCHDOG_IDLE ORCH_AGENT_IDLE_TIMEOUT ORCH_AGENT_MAX_LIFETIME ORCH_WATCHDOG_POLL  # ABS-225 idle watchdog
    unset STUB_HANG_NOCHILD STUB_LOOP       # ABS-225 idle-watchdog fixtures
    unset STUB_ORPHAN_PIDFILE STUB_ASYNC_WAIT ORCH_ASYNC_WAIT_SENSOR ORCH_REAP_SPAWN_CHILDREN   # ABS-601 async-wait stall + orphan reap
    unset ORCH_STUCK_SWEEPS ORCH_CONFIG_GENERATION ORCH_AGENTS_DIR
    unset ORCH_INPROGRESS_HEAL_SWEEPS   # ABS-451 In Progress orphan self-heal knob
    unset ORCH_SESSION_POISON_GUARD STUB_PERMISSION_DENIALS STUB_MAX_TURNS_DENIALS   # ABS-254 poison guard
    unset ORCH_CLAUDE_ACCOUNT   # ABS-302 account-switch invalidation
    unset ORCH_CRASH_REPAIR_SECONDS   # ABS-295 crash-repair knob
    unset ORCH_FOLLOWUP_REPAIR_SECONDS   # ABS-298 follow-up repair knob
    unset ORCH_MAIN_REMOTE   # PILOT-19: depends_unmet merge-probe remote; set per-block, reset here
    unset ORCH_INSTANCE_ID ORCH_INSTANCE_ID_FILE   # ABS-183 per-run identity
    unset ORCH_RUN_ID ORCH_RUN_ID_SEPARATION       # ABS-347 per-run artifact namespace
    unset ORCH_NOW ORCH_FASTFAIL_SECONDS ORCH_PROBE_INTERVALS ORCH_OUTAGE_RESUME
    unset ORCH_TELEMETRY ORCH_TRANSCRIPT_DIR
    unset ORCH_BACKOFF_FACTOR ORCH_BACKOFF_MAX_SECONDS
    unset ORCH_BUDGET_PAUSE_EXIT_CODE ORCH_BUDGET_PUSH ORCH_STANDSTILL_SWEEPS ORCH_STANDSTILL_PUSH   # ABS-455 budget-pause handshake knobs
    # ABS-118: the legacy suite body encodes retry-at-cadence semantics (crash
    # tests re-derive freely); pin backoff + outage detection OFF here and
    # enable them explicitly in the ABS-118 section.
    export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=0
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

# Fixture prewarming (test-runtime-diet): many worktree-provisioning scenarios
# start from the same `git init` + one empty commit. Build that template once
# per process, then `cp -R` it into each freshly-mktemp'd target — identical
# result, none of the repeated init/commit cost. Cache is process-local, so it
# also warms once per parallel shard. $1 is an existing (empty) target dir.
_WARM_GIT_TEMPLATE=""
warm_git_repo() {
    local dst="$1"
    if [ -z "$_WARM_GIT_TEMPLATE" ]; then
        _WARM_GIT_TEMPLATE="$(mktemp -d "${TMPDIR:-/tmp}/orch-fixture-tmpl-XXXXXX")"
        # Sole EXIT trap in this suite; covers serial runs and each shard child.
        trap 'rm -rf "$_WARM_GIT_TEMPLATE"' EXIT
        git -C "$_WARM_GIT_TEMPLATE" init -q
        git -C "$_WARM_GIT_TEMPLATE" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
    fi
    cp -R "$_WARM_GIT_TEMPLATE/." "$dst/"
}

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }
# Baseline: consume all creation events so the next --once sees only the change
# we made. Disable startup reconcile so it does not act on Backlog tickets.
baseline() { ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1; }
# rework_of <ticket> — the rework counter the runner itself derives from a ticket's
# dump. orchestrator.sh is source-guarded (main does not run on source); the subshell
# keeps its globals out of the suite. Lets the ABS-267 cases assert the COUNT, not
# just its downstream SPAWN-vs-REWORK-LIMIT effect.
rework_of() {
    local dump; dump="$(tracker get "$1")"
    ( source "$ORCH" >/dev/null 2>&1; rework_count "$dump" )
}

# =============================================================================
# Parallel shard dispatcher (test-runtime-diet)
# -----------------------------------------------------------------------------
# The suite body is a flat sequence of fully self-contained scenario blocks:
# each `new_env` mints a fresh mktemp state root and `cleanup_env` tears it
# down, so blocks share no mutable state beyond the PASS/FAIL/TOTAL counters.
# That lets us split the body into TEST_JOBS contiguous line ranges — cutting
# ONLY at `cleanup_env` block boundaries — and run each range in its own child
# process, then aggregate the tallies.
#
#   TEST_JOBS=1  -> dispatcher returns 0; the original inline body runs verbatim
#                   (exact serial behaviour, zero change).
#   TEST_JOBS=N  -> N parallel shards (default N=4).
#
# Isolation: every block already uses `mktemp -d` for its state, and each child
# gets its own TMPDIR, so there are no fixed paths/ports to collide on.
# NOTE: the full suite remains mandatory at the QAS gate — see tests/scoped-tests.sh.
_shard_self="${BASH_SOURCE[0]}"
_shard_dispatch() {
    local self="$_shard_self"
    local bstart bend
    bstart=$(grep -n '^#@SHARD-BODY-START@$' "$self" | head -1 | cut -d: -f1)
    bend=$(grep -n '^#@SHARD-BODY-END@$' "$self" | head -1 | cut -d: -f1)
    local body_first=$((bstart + 1)) body_last=$((bend - 1))

    # Child: run our assigned slice, then emit a machine tally.
    # ABS-525: the dispatcher pre-cuts every slice at dispatch time and hands
    # children a slice FILE (_SHARD_SLICE) — never a line range to re-extract.
    # A range re-`sed` from "$self" reads the file on disk AT CHILD TIME, so a
    # mid-run edit/checkout of this file (routine in an active agent worktree)
    # would tear the slices at arbitrary block boundaries. _SHARD_RANGE remains
    # as a manual debug affordance only.
    if [ -n "${_SHARD_SLICE:-}" ] || [ -n "${_SHARD_RANGE:-}" ]; then
        set -e   # match the serial body's errexit semantics
        # Source from a real temp file, not `<(...)`: bash 3.2 (macOS default)
        # cannot reliably `source` a process-substitution fd.
        local _slice _slice_own=0
        if [ -n "${_SHARD_SLICE:-}" ]; then
            _slice="$_SHARD_SLICE"
        else
            local a="${_SHARD_RANGE%%:*}" b="${_SHARD_RANGE##*:}"
            _slice="$(mktemp "${TMPDIR:-/tmp}/orch-slice-XXXXXX")"; _slice_own=1
            sed -n "${a},${b}p" "$self" > "$_slice"
        fi
        source "$_slice"
        if [ "$_slice_own" = 1 ]; then rm -f "$_slice"; fi
        printf '\n##SHARDRESULT PASS=%s FAIL=%s TOTAL=%s\n' "$PASS" "$FAIL" "$TOTAL"
        if [ "$FAIL" -gt 0 ]; then exit 1; fi
        exit 0
    fi

    local jobs="${TEST_JOBS:-4}"
    case "$jobs" in ''|*[!0-9]*) jobs=4 ;; esac
    if [ "$jobs" -le 1 ]; then return 0; fi   # serial: caller runs the inline body

    set +e   # dispatcher does its own error handling below

    # Candidate cut lines: every `cleanup_env` block boundary inside the body.
    local cuts=() ln
    while IFS=: read -r ln _; do
        if [ "$ln" -gt "$body_first" ] && [ "$ln" -lt "$body_last" ]; then
            cuts+=("$ln")
        fi
    done < <(grep -n '^cleanup_env$' "$self")
    local ncuts=${#cuts[@]}
    if [ "$ncuts" -lt 1 ]; then set -e; return 0; fi   # unsplittable: run serial
    if [ "$jobs" -gt $((ncuts + 1)) ]; then jobs=$((ncuts + 1)); fi

    # Build `jobs` contiguous ranges by splitting the cut list evenly.
    local starts=() ends=() i seg cut prev=$body_first
    for ((i = 1; i < jobs; i++)); do
        seg=$(( i * (ncuts + 1) / jobs ))
        if [ "$seg" -lt 1 ]; then seg=1; fi
        if [ "$seg" -gt "$ncuts" ]; then seg=$ncuts; fi
        cut=${cuts[$((seg - 1))]}
        starts+=("$prev"); ends+=("$cut")
        prev=$((cut + 1))
    done
    starts+=("$prev"); ends+=("$body_last")

    echo -e "${CYAN}=== Orchestrator suite: ${#starts[@]} parallel shards (TEST_JOBS=$jobs) ===${NC}\n"
    local tmpd; tmpd=$(mktemp -d /tmp/orch-shards-XXXXXX)
    # ABS-525: cut EVERY slice now, from one point-in-time read of "$self",
    # BEFORE any child starts. Children previously re-`sed`ed their line range
    # from the file on disk, so an edit/checkout of this file while the suite
    # ran (routine in an active agent worktree) tore the slices mid-block.
    local slices=() idx
    for idx in "${!starts[@]}"; do
        sed -n "${starts[$idx]},${ends[$idx]}p" "$self" > "$tmpd/slice-$idx.sh"
        slices+=("$tmpd/slice-$idx.sh")
    done
    local pids=() logs=()
    for idx in "${!starts[@]}"; do
        logs+=("$tmpd/shard-$idx.log")
        _SHARD_SLICE="${slices[$idx]}" TMPDIR="$tmpd" \
            bash "$self" >"$tmpd/shard-$idx.log" 2>&1 &
        pids+=("$!")
    done

    local rc=0 st
    for idx in "${!pids[@]}"; do
        if wait "${pids[$idx]}"; then st=0; else st=$?; fi
        if [ "$st" -ne 0 ]; then rc=1; fi
    done

    local tPASS=0 tFAIL=0 tTOTAL=0 p f t aborted=0 sline vfails esc
    esc=$(printf '\033')
    for idx in "${!logs[@]}"; do
        # Surface each shard's output (minus the machine tally) so no failure hides.
        grep -v '^##SHARDRESULT' "${logs[$idx]}"
        # ABS-370: a shard that dies (set -e abort, crash) emits NO ##SHARDRESULT
        # sentinel. Never fold that silently into a green aggregate — count it as
        # an aborted shard so the summary is non-green AND the run exits non-zero.
        sline=$(sed -n 's/^##SHARDRESULT PASS=\([0-9]*\) FAIL=\([0-9]*\) TOTAL=\([0-9]*\)$/\1 \2 \3/p' "${logs[$idx]}" | head -1)
        if [ -z "$sline" ]; then
            aborted=$((aborted + 1)); rc=1
            echo -e "\n  ${RED}FAIL${NC} shard $idx ABORTED before emitting its tally — its remaining files were skipped (ABS-370)"
            continue
        fi
        read -r p f t <<<"$sline"
        tPASS=$((tPASS + ${p:-0})); tFAIL=$((tFAIL + ${f:-0})); tTOTAL=$((tTOTAL + ${t:-0}))
        # ABS-525 LOST-FAIL GUARD: every visible assert-FAIL verdict line in a
        # shard's log must be covered by that shard's tallied FAIL count. A FAIL
        # that PRINTS but is not COUNTED (e.g. an assert that ran in a subshell,
        # or any future counter-plumbing hole) would otherwise aggregate green.
        # Sound because every deliberately-induced-then-rolled-back FAIL in the
        # suite is print-suppressed (ABS-310 AC3 probe, ABS-370 abort fixture).
        vfails=$(grep -c "^  ${esc}\[0;31mFAIL${esc}\[0m " "${logs[$idx]}" || true)
        if [ "${vfails:-0}" -gt "${f:-0}" ]; then
            rc=1; tFAIL=$((tFAIL + vfails - f)); tTOTAL=$((tTOTAL + vfails - f))
            echo -e "\n  ${RED}FAIL${NC} shard $idx printed $vfails FAIL verdict line(s) but tallied only ${f} — counting the difference (lost-fail guard, ABS-525)"
        fi
    done
    rm -rf "$tmpd"

    echo -e "\n${CYAN}=== Test Results (aggregated over ${#starts[@]} shards) ===${NC}\n"
    echo -e "  Total:  $tTOTAL"
    echo -e "  ${GREEN}Passed: $tPASS${NC}"
    if [ "$tFAIL" -gt 0 ] || [ "$rc" -ne 0 ] || [ "$aborted" -gt 0 ]; then
        # Show a non-zero failure count even when the only fault is an aborted
        # shard (which contributes no tally) — so the summary can never read green.
        local _abnote=""
        if [ "$aborted" -gt 0 ]; then _abnote="  (incl. $aborted aborted shard(s))"; fi
        echo -e "  ${RED}Failed: $((tFAIL + aborted))${NC}${_abnote}"
        exit 1
    fi
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
}

# ── Staged-suite include-only mode (PILOT-50) ────────────────────────────────
# Run exactly ONE tests/orchestrator.d story-include with the harness loaded,
# then exit — WITHOUT the scenario-block dispatch below. The full include loop
# (lines near SHARD-BODY-END) runs the ~48 includes SERIALLY and is the ~7-min
# runtime dominator that pushes the whole tentpole past a gate seat's 10-min
# single-call limit. tests/staged-suite.sh fans the includes out one-per-process
# in parallel as their own bounded stage; each such process sets SUITE_INCLUDE_ONLY
# and lands here. Counters (PASS/FAIL/TOTAL, line 86) and _run_d_include (line 141)
# are already defined; `tracker`/`orch` are still the canonical surface here — the
# mid-body overrides (abs199/abs210) live AFTER this point and never run in this
# mode, so no restore is needed (contrast the loop's line ~5200 restore).
# NOTE: the selector is NOT ORCH_*-prefixed on purpose — the ABS-286 env scrub
# near the top (`unset "${!ORCH_@}"`) would wipe it before we get here. SUITE_*
# survives, like TEST_JOBS, and only selects WHICH tests run (not their behavior).
if [ -n "${SUITE_INCLUDE_ONLY:-}" ]; then
    _io_dir="$(cd "$(dirname "${_shard_self:-${BASH_SOURCE[0]}}")/.." && pwd)/orchestrator.d"
    _io_file="$_io_dir/$SUITE_INCLUDE_ONLY"
    if [ ! -f "$_io_file" ]; then
        echo "SUITE_INCLUDE_ONLY: no such include: $SUITE_INCLUDE_ONLY" >&2; exit 2
    fi
    echo -e "${CYAN}=== Story include (isolated, PILOT-50): $SUITE_INCLUDE_ONLY ===${NC}"
    # CONSUME the selector before running the include: guard-tests like ABS-525 /
    # ABS-370 spawn their OWN synthetic test-orchestrator subprocess, which would
    # otherwise inherit SUITE_INCLUDE_ONLY and divert into this same mode (against
    # a synthetic orchestrator.d that lacks the file) — a false "no such include"
    # red. Unset so children run as the test intends. (The ABS-286 ORCH_-scrub can't
    # cover this var — it would wipe it before we read it here.)
    unset SUITE_INCLUDE_ONLY
    _run_d_include "$_io_file" || true
    echo -e "\n  Total: $TOTAL  ${GREEN}Passed: $PASS${NC}  Failed: $FAIL"
    [ "$FAIL" -gt 0 ] && exit 1
    exit 0
fi
_shard_dispatch

echo -e "${CYAN}=== Orchestrator (ABS-52/53/54) ===${NC}\n"
#@SHARD-BODY-START@

# =============================================================================
echo -e "${CYAN}§2 mapping — SPAWN rows spawn, keyed on destination status${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "Map epic")
T=$(tracker create --type ticket --title "Impl" --parent "$E" --role fe-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=fe-developer to=Ready for Development" "Ready for Development -> SPAWN implementer (role from ticket)"
cleanup_env

# --- §2 NOOP rows: In Progress and Ready for Merge never spawn ----------------
new_env
E=$(tracker create --type epic --title "Noop epic")
T=$(tracker create --type ticket --title "Noop" --parent "$E")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
# The net event is Ready for Development -> In Progress; keyed on `to`=In Progress -> NOOP.
assert_contains "$out" "INTENT NOOP ticket=$T" "In Progress -> NOOP (no spawn)"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "In Progress does not spawn"
cleanup_env

# --- §2 role selection: absent role -> be-developer + note --------------------
new_env
T=$(tracker create --type ticket --title "No role")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "role=be-developer" "absent role defaults to be-developer"
assert_contains "$out" "note=no-role-frontmatter-defaulting-to-be-developer" "absent role records a note"
cleanup_env

# =============================================================================
echo -e "${CYAN}§2.2 design-first routing (ABS-213 / ADR-A-0020) — architect-first, then dev${NC}"
# =============================================================================
# AC1: a `design-first`-labelled ticket's FIRST Ready-for-Development spawn goes
# to system-architect (proposed-ADR authoring), NOT the dev role.
new_env
T=$(tracker create --type ticket --title "Design-first" --role be-developer --label design-first)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=system-architect to=Ready for Development" "design-first -> first spawn is system-architect"
assert_not_contains "$out" "INTENT SPAWN ticket=$T role=be-developer" "design-first does NOT spawn the dev role first"
cleanup_env

# AC1 (latch consumed): once the architect handoff appended `design-first-done`,
# the NEXT sweep re-resolves to the dev role — regular Ready for Development.
new_env
T=$(tracker create --type ticket --title "Design-first done" --role be-developer --label design-first --label design-first-done)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=Ready for Development" "design-first-done -> dev role resumes (latch consumed)"
assert_not_contains "$out" "role=system-architect to=Ready for Development" "design-first-done does NOT re-spawn the architect"
cleanup_env

# AC2: a ticket WITHOUT the marker is unchanged — dev role as before.
new_env
T=$(tracker create --type ticket --title "No marker" --role fe-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=fe-developer to=Ready for Development" "unmarked ticket routes to the dev role unchanged"
cleanup_env

# Kill-switch: ORCH_DESIGN_FIRST_ROUTING=0 restores label-blind resolution.
new_env
T=$(tracker create --type ticket --title "Kill switch" --role be-developer --label design-first)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_DESIGN_FIRST_ROUTING=0 ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=Ready for Development" "kill-switch=0 ignores design-first, dev role spawns"
cleanup_env

# --- §2 In Review -> SPAWN system-architect; In Test -> SPAWN qas ---------------------
new_env
T=$(tracker create --type ticket --title "Review path")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=system-architect to=In Review" "In Review -> SPAWN system-architect"
cleanup_env

# --- ABS-57 In Review spawn runs read-only (separation of duties) -------------
# The reviewer reuses the write-capable system-architect role; the runner must
# hand the In Review spawn a read-only toolset so it can review but not edit.
new_env
export STUB_TOOLS_FILE="$TEST_DIR/tools.log"
T=$(tracker create --type ticket --title "Readonly review")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tools_line=$(grep '^system-architect' "$STUB_TOOLS_FILE" | head -1)
assert_contains "$tools_line" "Read, Bash, Grep, Glob" "In Review spawn gets read-only toolset"
assert_not_contains "$tools_line" "Write" "In Review spawn toolset has no Write"
assert_not_contains "$tools_line" "Edit" "In Review spawn toolset has no Edit"
cleanup_env

# --- ABS-57 In Test (qas) spawn is NOT narrowed — qas needs its own tools ------
# qas ships read-only-for-code already (no Write/Edit) and needs its tracker
# comment tools, so the runner must leave its toolset untouched (empty override).
new_env
export STUB_TOOLS_FILE="$TEST_DIR/tools.log"
T=$(tracker create --type ticket --title "QA not narrowed")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
tracker transition "$T" "In Test" --actor system-architect --reason reviewed >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
qas_tools=$(awk -F'\t' '/^qas\t/{print $2; exit}' "$STUB_TOOLS_FILE")
assert_eq "$qas_tools" "" "In Test spawn passes empty override (qas keeps frontmatter tools)"
cleanup_env

# --- §2 SPAWN-then-NOTIFY: Ready for Human Acceptance -------------------------
new_env
T=$(tracker create --type ticket --title "RHA path")
baseline
# ABS-216 taught the STATION-GUARD that a direct 'In Test -> RfHA' hop folds the
# mandatory Story Acceptance station and is redirected. To exercise the RfHA
# DISPATCH (SPAWN-NOTIFY po-agent) rather than the guard, park the ticket in RfHA
# via the guard-EXEMPT Blocked-unblock edge (Blocked is off-chain, index 0, so the
# last transition Blocked -> RfHA is never flagged as a forward station skip).
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Blocked" "Ready for Human Acceptance"; do
    case "$s" in
        "Ready for Development") actor=po ;;
        *) actor=agent ;;
    esac
    tracker transition "$T" "$s" --actor "$actor" --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Ready for Human Acceptance" "RHA -> SPAWN po-agent"
assert_contains "$out" "INTENT NOTIFY" "RHA -> NOTIFY (SPAWN-then-NOTIFY)"
cleanup_env

# --- ABS-61 Needs PO Decision: plain SPAWN po-agent (no NOTIFY) ----------------
# The tenth canonical status spawns the PO-Agent on demand; unlike Blocked/RHA it
# is a plain SPAWN with no human NOTIFY (the PO-Agent decides autonomously).
new_env
T=$(tracker create --type ticket --title "PO decision")
baseline
# Any active status may request a product decision; drive Backlog -> Needs PO Decision.
tracker transition "$T" "Needs PO Decision" --actor be-developer --reason "scope question for PO" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Needs PO Decision" "Needs PO Decision -> SPAWN po-agent"
assert_not_contains "$out" "INTENT NOTIFY" "Needs PO Decision is a plain SPAWN (no human NOTIFY)"
cleanup_env

# --- ABS-61 Needs PO Decision is reconciliation-swept (transient work state) ---
# A ticket resting in Needs PO Decision with no live lock is a dropped/lost spawn
# the startup reconciliation sweep must re-dispatch (is_reconcilable_status, §5.1).
new_env
STUB_RECORD_FILE="$TEST_DIR/rec_npd.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "PO decision recon")
tracker transition "$T" "Needs PO Decision" --actor be-developer --reason "needs product call" >/dev/null
# Advance the events baseline so the transition is NOT redelivered (simulate a
# lost spawn: the ticket rests in Needs PO Decision with no lock).
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker events >/dev/null
# A fresh runner's STARTUP reconciliation sweep must find + dispatch it once.
out=$(orch --live --once 2>&1)
assert_contains "$out" "reconciliation sweep" "startup reconciliation runs"
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Needs PO Decision" "reconcile re-derives the resting Needs PO Decision ticket"
recon_spawns=$(grep -c "	$T$" "$STUB_RECORD_FILE" || true)
assert_eq "$recon_spawns" "1" "reconcile dispatches the Needs PO Decision ticket exactly once"
cleanup_env

# --- ABS-150 stale-lock reclaim in reconcile — an orphaned lock must not deadlock -
# A spawn orphaned by a killed/interrupted runner leaves a lock dir behind.
# Reconcile skips a FRESH lock (single-flight preserved) but must RECLAIM one
# older than ORCH_LOCK_TTL and re-dispatch — the TTL reclaim previously lived
# only in acquire_lock, which a locked ticket never reached from reconcile, so an
# orphaned lock froze the ticket forever (ABS-129 live run).
new_env
STUB_RECORD_FILE="$TEST_DIR/rec_lock.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Stale lock recon")
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Drain the transition event so the ticket RESTS (reconcile is the only actor).
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker events >/dev/null
# Simulate the orphaned lock left by a killed spawn.
mkdir -p "$ORCH_STATE_DIR/locks/$T"
# Case A — a FRESH lock (age < default TTL) is respected: no reclaim, no dispatch.
out=$(orch --dry-run --once 2>&1)
assert_not_contains "$out" "reclaiming stale lock for $T" "fresh lock: reconcile does not reclaim"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "fresh lock: reconcile does not re-dispatch"
if [ -d "$ORCH_STATE_DIR/locks/$T" ]; then lockstate=present; else lockstate=absent; fi
assert_eq "$lockstate" "present" "fresh lock: single-flight lock preserved"
# Case B — a STALE lock (ORCH_LOCK_TTL=0 makes any lock stale) is reclaimed and
# the ticket re-dispatches exactly once.
out=$(ORCH_LOCK_TTL=0 orch --live --once 2>&1)
assert_contains "$out" "reconcile: reclaiming stale lock for $T" "stale lock: reconcile reclaims it"
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=Ready for Development" "stale lock: ticket re-dispatches after reclaim"
recon_spawns=$(grep -c "	$T$" "$STUB_RECORD_FILE" || true)
assert_eq "$recon_spawns" "1" "stale lock: reclaimed ticket dispatches exactly once"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§1.4 dedupe — same transition dispatched once per (ticket,to,at)${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Dedupe")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Two poll passes in ONE process would dedupe; simulate via a wrapper single run
# that polls twice is not possible with --once, so assert the event delivers
# once across two --once processes is guarded by the tracker (advance-on-read).
out1=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
out2=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out1" "INTENT SPAWN ticket=$T" "first pass dispatches the transition"
assert_not_contains "$out2" "INTENT SPAWN ticket=$T" "second pass does not re-dispatch (advance-on-read)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.4 stale-event guard — moved-on ticket is skipped${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Stale")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Move it on BEFORE the orchestrator polls: the event's `to` (Ready for
# Development) no longer matches the current status.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
# Net event to=In Progress is NOOP; ensure no SPAWN fired for the stale RfD.
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "moved-on ticket does not spawn (re-read guard)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.2 single-flight lock — a held lock blocks a second dispatch${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Locked")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Pre-create the lock dir to simulate an in-flight spawn from a concurrent cycle.
mkdir -p "$ORCH_STATE_DIR/locks/$T"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-LOCKED ticket=$T" "held lock -> SKIP-LOCKED, no double spawn"
assert_not_contains "$out" "INTENT HANDOFF ticket=$T" "locked ticket produces no handoff"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.3 kill switch — halts the run, no new spawns${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Kill")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
touch "$ORCH_STOP_FILE"
ec=0
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1) || ec=$?
assert_eq "$ec" "0" "kill switch -> exit 0"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "kill switch -> no new spawn"
assert_contains "$out" "kill-switch present" "kill switch logged"
cleanup_env

# --- ABS-59 kill switch in LOOPING mode exits 0 (set -e must not swallow rc) ---
# The --once path uses `one_cycle || true`, but the real loop is unbounded. Under
# `set -euo pipefail` a bare `one_cycle` returning 10 (clean stop) aborted the
# script with status 10 before the rc check ran. Assert the loop-mode kill-switch
# stop exits 0. ORCH_POLL_INTERVAL=0 keeps it from sleeping; the switch is present
# at the first cycle top so it returns 10 immediately (no spawn, no busy-loop).
new_env
T=$(tracker create --type ticket --title "Loop kill")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
touch "$ORCH_STOP_FILE"
ec=0
out=$(ORCH_POLL_INTERVAL=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>&1) || ec=$?
assert_eq "$ec" "0" "kill switch in LOOPING mode -> exit 0 (set -e does not swallow rc)"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "looping kill switch -> no new spawn"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.4 spawn budget — soft cap DRAINS new intake (PILOT-47)${NC}"
# =============================================================================
# PILOT-47: the per-run SOFT cap no longer hard-stops. With cap=1 the first
# intake spawns; the second NEW intake (no progress in a single dry cycle, so no
# auto-extend) is held for DRAIN (SKIP-DRAIN-INTAKE), not braked to exit-75.
new_env
export ORCH_MAX_SPAWNS_PER_RUN=1
export ORCH_NOTIFY_TICKET=""
export ORCH_BUDGET_PUSH=0   # suppress the operator dialog (as ORCH_STANDSTILL_PUSH=0 does for standstill tests)
export ORCH_SPAWN_BUDGET_AUTOEXTEND=0   # isolate the drain path from auto-extend
E=$(tracker create --type epic --title "Budget epic")
T1=$(tracker create --type ticket --title "B1" --parent "$E")
T2=$(tracker create --type ticket --title "B2" --parent "$E")
baseline
tracker transition "$T1" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1) || true
spawn_count=$(echo "$out" | grep -c "INTENT SPAWN " || true)
assert_eq "$spawn_count" "1" "soft cap 1 -> exactly one SPAWN this run"
assert_contains "$out" "INTENT SKIP-DRAIN-INTAKE" "second NEW intake held for drain, not braked to a hard stop"
assert_not_contains "$out" "INTENT SKIP-BUDGET " "soft-cap exhaustion is drain, not the exit-75 hard backstop"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.5 iteration-guard — at cap -> Needs PO Decision instead of spawn${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Iter cap")
# Seed 2 REAL bounces at the In Test gate (ABS-115: marker-bearing gate comment
# + backward transition), leaving the ticket at In Review before the baseline.
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
tracker transition "$T" "In Test" --actor system-architect --reason reviewed >/dev/null
tracker comment "$T" --kind gate-results --actor qas --body "Iteration 1 of 3 — tests failed" >/dev/null
tracker transition "$T" "In Progress" --actor qas --reason bounce >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason rework >/dev/null
tracker transition "$T" "In Test" --actor system-architect --reason reviewed >/dev/null
tracker comment "$T" --kind gate-results --actor qas --body "Iteration 2 of 3 — tests failed again" >/dev/null
tracker transition "$T" "In Progress" --actor qas --reason bounce >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason rework >/dev/null
baseline
# Re-entering In Test (next would be bounce N=3 at that gate -> at cap 3).
# ORCH_REWORK_LIMIT is raised so §5.5 (not §3.2's marker-independent counter,
# which also sees the two backward transitions) is the check under test.
tracker transition "$T" "In Test" --actor system-architect --reason reviewed >/dev/null
out=$(ORCH_REWORK_LIMIT=99 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT BLOCK-ITERATION-CAP ticket=$T" "at cap -> BLOCK-ITERATION-CAP intent"
assert_not_contains "$out" "INTENT SPAWN ticket=$T role=qas" "at cap -> no qas spawn"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Needs PO Decision" "at cap -> ticket escalated to Needs PO Decision (ABS-115)"
gate=$(tracker get "$T" | grep -c "kind: gate-results | actor: orchestrator" || true)
assert_eq "$gate" "1" "at cap -> orchestrator gate-results comment recorded"
# Regression (ABS-107 false-positive fix): informational markers with only
# forward transitions must NOT block the gate spawn.
T2=$(tracker create --type ticket --title "Iter approve")
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T2" "In Progress" --actor be-developer --reason start >/dev/null
tracker comment "$T2" --kind gate-results --actor sa --body "APPROVE — Iteration 1 of 3 (no bounce)" >/dev/null
tracker comment "$T2" --kind gate-results --actor sa --body "APPROVE — Iteration 2 of 3 (no bounce)" >/dev/null
baseline
tracker transition "$T2" "In Review" --actor be-developer --reason handoff >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT BLOCK-ITERATION-CAP ticket=$T2" "informational markers -> no false-positive cap (ABS-107)"
assert_contains "$out" "INTENT SPAWN ticket=$T2" "informational markers -> gate seat still spawns"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-116 bounce routing — backward into In Progress spawns the implementer${NC}"
# =============================================================================
new_env
T=$(tracker create --type ticket --title "Bounced story" --role fe-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor fe-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor fe-developer --reason handoff >/dev/null
baseline
# The observed live deadlock (ABS-108): reviewer bounces In Review -> In Progress.
tracker transition "$T" "In Progress" --actor system-architect --reason "review findings, back to implementer" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=fe-developer to=In Progress" "backward bounce into In Progress -> implementer spawn (role from ticket)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "BOUNCE-REROUTE" "backward bounce records BOUNCE-REROUTE in run.log"
cleanup_env

# Forward entry (normal work start) must stay NOOP — single-flight regression.
new_env
T=$(tracker create --type ticket --title "Normal start" --role fe-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
tracker transition "$T" "In Progress" --actor fe-developer --reason start >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --once 2>/dev/null)
assert_contains "$out" "INTENT NOOP ticket=$T role=- to=In Progress" "forward Ready for Development -> In Progress stays NOOP"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "forward entry -> no implementer spawn"
cleanup_env

# Blocked -> In Progress (unblock resume) is neutral, not a bounce.
new_env
T=$(tracker create --type ticket --title "Unblocked" --role fe-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor fe-developer --reason start >/dev/null
tracker transition "$T" "Blocked" --actor fe-developer --reason "env down" >/dev/null
baseline
tracker transition "$T" "In Progress" --actor human --reason unblocked >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "Blocked -> In Progress unblock -> no spawn (neutral)"
cleanup_env

# Any later chain stage bounces the same way (In Test -> In Progress).
new_env
T=$(tracker create --type ticket --title "Test bounce" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
tracker transition "$T" "In Test" --actor system-architect --reason reviewed >/dev/null
baseline
tracker transition "$T" "In Progress" --actor qas --reason "tests failed" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=In Progress" "In Test -> In Progress bounce -> implementer spawn"
cleanup_env

# The §3.2 rework backstop applies to the In Progress bounce respawn too.
new_env
T=$(tracker create --type ticket --title "Rework capped" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
tracker transition "$T" "In Progress" --actor system-architect --reason bounce1 >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason rework >/dev/null
baseline
tracker transition "$T" "In Progress" --actor system-architect --reason bounce2 >/dev/null
out=$(ORCH_REWORK_LIMIT=2 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$T" "bounce respawn at rework limit -> escalation, not spawn"
assert_not_contains "$out" "INTENT SPAWN ticket=$T role=be-developer" "rework-capped bounce -> no implementer spawn"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-116 stuck detector — unowned resting status NOTIFYs once per episode${NC}"
# =============================================================================
new_env
export ORCH_NOTIFY_TICKET=""
# ABS-451: this block exercises the ABS-116 NOTIFY/throttle MECHANISM on an
# unowned In Progress fixture. With the ABS-451 heal ON (default 3 sweeps) that
# same fixture would be DOWNGRADED to Ready for Development before the NOTIFY,
# so pin the heal OFF here to keep testing the pure NOTIFY safety net (the
# heal-off path is itself asserted by tests/orchestrator.d/ABS-451-*.sh).
export ORCH_INPROGRESS_HEAL_SWEEPS=0
T=$(tracker create --type ticket --title "Stuck story" --role fe-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor fe-developer --reason start >/dev/null
baseline
# (This fixture is state-identical to the PRIMARY real trigger: an implementer
# that crashed after setting In Progress — lock released, no session, ABS-74's
# crash escalation can never re-derive because In Progress is not reconcilable.)
# Sweeps 1..2: under threshold (default ORCH_STUCK_SWEEPS=3) -> silent.
out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
assert_not_contains "$out1$out2" "stuck detected" "sweeps below threshold -> no NOTIFY"
assert_not_contains "$out1" "INTENT SPAWN ticket=$T" "reconcile passes no from -> resting In Progress is never re-derived"
# Sweep 3: threshold reached -> exactly one NOTIFY + STUCK-DETECT event.
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
assert_contains "$out3" "stuck detected: $T" "sweep 3 -> stuck NOTIFY fires"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "STUCK-DETECT" "STUCK-DETECT recorded in run.log"
# Sweep 4: same episode -> throttled (no second NOTIFY), but run.log keeps a line.
out4=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
assert_not_contains "$out4" "stuck detected" "sweep 4 same episode -> NOTIFY throttled"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "throttled" "throttled sweep still logged"
# Ticket moves on -> episode ends; falling back later starts a FRESH episode.
tracker transition "$T" "In Review" --actor fe-developer --reason handoff >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --once >/dev/null 2>&1   # clears the row (In Review is owned)
tracker transition "$T" "In Progress" --actor system-architect --reason bounce >/dev/null
o1=$(ORCH_RECONCILE_ON_STARTUP=0 orch --once 2>/dev/null)  # consumes the bounce event (spawn intent)
f1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
f2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
f3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)
assert_contains "$f3" "stuck detected: $T" "fresh episode after fall-back -> NOTIFY may fire again"
cleanup_env

# Lock present (in-flight spawn) and legit-rest statuses are never stuck.
new_env
T=$(tracker create --type ticket --title "Working story" --role fe-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor fe-developer --reason start >/dev/null
B=$(tracker create --type ticket --title "Blocked story")
tracker transition "$B" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$B" "Blocked" --actor po --reason blocked >/dev/null
baseline
mkdir -p "$ORCH_STATE_DIR/locks/$T"   # simulate an in-flight spawn holding the lock
out=""
for _ in 1 2 3 4; do out="$out$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)"; done
assert_not_contains "$out" "stuck detected: $T" "in-flight lock -> working implementer is not stuck"
assert_not_contains "$out" "stuck detected: $B" "Blocked (legit rest) -> never stuck"
rm -rf "$ORCH_STATE_DIR/locks/$T"
# Backoff marker (ABS-118 forward-compat) reads as a legitimate wait.
touch "$ORCH_STATE_DIR/backoff-$T"
out=""
for _ in 1 2 3 4; do out="$out$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)"; done
assert_not_contains "$out" "stuck detected: $T" "backoff marker -> pending wait is not stuck"
rm -f "$ORCH_STATE_DIR/backoff-$T"
# ORCH_STUCK_SWEEPS=0 disables the detector.
out=""
for _ in 1 2 3 4; do out="$out$(ORCH_STUCK_SWEEPS=0 ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)"; done
assert_not_contains "$out" "stuck detected" "ORCH_STUCK_SWEEPS=0 disables the detector"
cleanup_env

# Generic promise: an UNKNOWN status (future edge) is flagged; a reconcilable
# resting status is not (reconcile re-derives its seat instead).
new_env
export ORCH_NOTIFY_TICKET=""
T=$(tracker create --type ticket --title "Weird status")
baseline
# Force a status the state machine does not know (simulates a future/foreign
# status slipping in) — written directly into the mock store on purpose.
sed -i '' "s/^status: .*/status: Somewhere Odd/" "$MOCK_TRACKER_TICKETS_DIR/$T.md"
R=$(tracker create --type ticket --title "Reviewable" --role be-developer)
tracker transition "$R" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$R" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$R" "In Review" --actor be-developer --reason handoff >/dev/null
out=""
for _ in 1 2 3; do out="$out$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)"; done
assert_contains "$out" "stuck detected: $T" "unknown status -> generic detector flags it"
assert_not_contains "$out" "stuck detected: $R" "reconcilable resting status -> reconcile owns it, never stuck"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.1 concurrency cap — (N+1)th deferred, spawns next pass${NC}"
# =============================================================================
new_env
export ORCH_MAX_CONCURRENT=1
E=$(tracker create --type epic --title "Cap epic")
T1=$(tracker create --type ticket --title "C1" --parent "$E")
T2=$(tracker create --type ticket --title "C2" --parent "$E")
baseline
tracker transition "$T1" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
# Both events surface in ONE poll; cap=1 -> one spawns this pass, the other is
# deferred to the in-memory pending set and RETRIED at the start of the next
# cycle once a slot frees (§5.1). We drive a deterministic 2-cycle loop via the
# ORCH_MAX_CYCLES test hook (no timing race, no kill-switch timer). The stub does
# NOT transition, so the deferred ticket stays in Ready for Development and the
# pending-set retry — not reconciliation — must pick it up (reconcile disabled).
STUB_RECORD_FILE="$TEST_DIR/rec.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
out=$(ORCH_MAX_CONCURRENT=1 ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 \
      ORCH_RECONCILE_ON_STARTUP=0 ORCH_RECONCILE_EVERY_N_CYCLES=0 \
      orch --live 2>/dev/null)
assert_contains "$out" "INTENT DEFER-CAP" "cap=1: the (N+1)th event is deferred, not dropped"
total=$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')
assert_eq "$total" "2" "cap=1: both ready tickets spawn exactly once across cycles (deferred one retried next pass)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§5.1 reconciliation sweep — re-derives a dropped event${NC}"
# =============================================================================
new_env
STUB_RECORD_FILE="$TEST_DIR/rec2.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Recon")
# Simulate a crashed runner: the ticket is already in a SPAWN-mapped status AND
# the events snapshot already reflects it (so `events` returns nothing for it).
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Advance the events baseline so the transition is NOT redelivered.
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
# Confirm no event remains for it.
ev=$(tracker events); tracker events >/dev/null   # (drain twice to be safe)
# A fresh runner's STARTUP reconciliation sweep must find + dispatch it once.
# Capture stderr too: the "reconciliation sweep" log line is a runner log (stderr).
out=$(orch --live --once 2>&1)
assert_contains "$out" "reconciliation sweep" "startup reconciliation runs"
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=Ready for Development" "reconcile re-derives the dropped Ready for Development ticket"
recon_spawns=$(grep -c "	$T$" "$STUB_RECORD_FILE" || true)
assert_eq "$recon_spawns" "1" "reconcile dispatches the ticket exactly once"
cleanup_env

# --- reconcile no-op on an already-advanced/locked ticket (re-read guard) -----
new_env
T=$(tracker create --type ticket --title "Recon noop")
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1  # drain events
# Ticket already moved on to In Progress (a NOOP status) before reconcile.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker events >/dev/null   # drain that event too
out=$(orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "reconcile is a no-op on an advanced ticket (In Progress is NOOP)"
cleanup_env

# --- reconcile does NOT re-derive tickets RESTING in entry/terminal states ----
# Regression: Backlog (ungroomed) and Done (terminal) are legitimate resting
# states. The startup sweep must NOT mass-spawn them, and a periodic sweep must
# not re-spawn them every cadence (would loop forever, e.g. Done -> tech-writer,
# and blow the ADR-A-0009 budget). is_reconcilable_status() gates this (§5.1).
new_env
STUB_RECORD_FILE="$TEST_DIR/rec_rest.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
BL=$(tracker create --type ticket --title "Resting in backlog")   # stays Backlog
DN=$(tracker create --type ticket --title "Resting done")
# Drive DN all the way to Done so it rests in the terminal status.
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$DN" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1   # drain creation/transition events
# Force reconcile to run (startup sweep, no pending events) across two cycles.
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=1 \
      orch --live 2>&1)
assert_not_contains "$out" "INTENT SPAWN ticket=$BL" "reconcile does not spawn a ticket resting in Backlog"
assert_not_contains "$out" "INTENT SPAWN ticket=$DN" "reconcile does not spawn a ticket resting in Done"
resting_spawns=$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')
assert_eq "$resting_spawns" "0" "reconcile never invokes the spawn seam for resting Backlog/Done tickets"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}§6 failure handling — retry once then SPAWN-CRASH marker (v3, ABS-74)${NC}"
# =============================================================================
new_env
export STUB_FAIL=1
T=$(tracker create --type ticket --title "Fail path")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RETRY ticket=$T" "spawn failure -> retry once"
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "second failure -> SPAWN-CRASH marker (v3, no Blocked)"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" "crash leaves the ticket RESTING in its status"
crash_body=$(tracker get "$T")
assert_contains "$crash_body" "SPAWN-CRASH status=Ready for Development " "crash marker comment landed on the ticket"
# ABS-151: on a non-zero-exit crash the marker is no longer opaque — it surfaces
# the spawn's exit code AND captured stderr tail so a transient hiccup can be
# told apart from a permanent fault.
assert_contains "$crash_body" "Diagnostic:" "ABS-151: crash marker carries a diagnostic (not opaque)"
assert_contains "$crash_body" "exit=7" "ABS-151: non-zero-exit diagnostic surfaces the spawn exit code"
assert_contains "$crash_body" "stub-spawn: forced failure" "ABS-151: non-zero-exit diagnostic surfaces the captured stderr tail"
cleanup_env

# --- §6 missing handoff -> retry then SPAWN-CRASH marker ----------------------
new_env
export STUB_NO_HANDOFF=1
T=$(tracker create --type ticket --title "No handoff")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
# ABS-151 AC4: an empty/unparseable handoff is handled DETERMINISTICALLY —
# retried once per §6 policy, then escalated to a SPAWN-CRASH marker.
assert_contains "$out" "INTENT RETRY ticket=$T" "ABS-151: missing handoff is retried per §6 before escalation"
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "missing handoff -> SPAWN-CRASH after retry"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" "missing-handoff crash leaves the ticket RESTING"
nh_body=$(tracker get "$T")
assert_contains "$nh_body" "SPAWN-CRASH status=Ready for Development " "missing-handoff crash marker landed on the ticket"
# ABS-151 AC3: the empty-handoff crash marker NAMES its failure mode, distinct
# from the non-zero-exit diagnostic above (transient vs permanent).
assert_contains "$nh_body" "no parseable handoff" "ABS-151: empty-handoff crash marker names the failure mode"
cleanup_env

# --- ABS-151 root cause: TURN-CEILING abort named distinctly (operator Befund) -
# The dominant silent SPAWN-CRASH is the CLI hitting --max-turns and aborting
# mid-work (result subtype=error_max_turns, no handoff). This is a TRANSIENT
# fault and must be NAMED as such in the crash diagnostic — distinct from a
# genuine empty handoff — so an operator can act (raise ORCH_MAX_TURNS_<ROLE>).
new_env
export STUB_MAX_TURNS_EXIT=1
T=$(tracker create --type ticket --title "Turn ceiling" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RETRY ticket=$T" "ABS-151: turn-ceiling abort is retried per §6 before escalation"
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "turn-ceiling abort -> SPAWN-CRASH after retry (deterministic)"
tc_body=$(tracker get "$T")
assert_contains "$tc_body" "TURN CEILING" "ABS-151: crash marker names the turn-ceiling root cause"
assert_contains "$tc_body" "error_max_turns" "ABS-151: crash marker cites the CLI signal (error_max_turns)"
cleanup_env

# --- ABS-151 AC2: concurrent-epic-seat scenario ------------------------------
# The ABS-126 run recorded the be-developer crash while ABS-114 was concurrently
# active in the epic pipeline. Two tickets crashing in the SAME cycle (async
# spawns run in isolated background subshells; each attempt keys its diag file to
# a unique per-attempt packet path) must each carry their OWN diagnostic — no
# cross-contamination between the concurrent seats.
new_env
export STUB_FAIL=1
T=$(tracker create --type ticket --title "Concurrent crash A")
T2=$(tracker create --type ticket --title "Concurrent crash B")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "concurrent seat A -> SPAWN-CRASH"
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T2" "concurrent seat B -> SPAWN-CRASH"
assert_contains "$(tracker get "$T")" "Diagnostic:" "ABS-151: concurrent seat A carries its own diagnostic"
assert_contains "$(tracker get "$T2")" "Diagnostic:" "ABS-151: concurrent seat B carries its own diagnostic"
cleanup_env

# --- §6.1 watchdog timeout -> treated as a spawn failure -> SPAWN-CRASH -------
new_env
export STUB_HANG=1 STUB_HANG_SECONDS=10
export ORCH_AGENT_TIMEOUT=1   # short watchdog so the hang is killed fast
T=$(tracker create --type ticket --title "Hang path")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "watchdog timeout -> retry-once-then-SPAWN-CRASH"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" "timeout crash leaves the ticket RESTING"
assert_contains "$(tracker get "$T")" "SPAWN-CRASH status=Ready for Development " "timeout crash marker landed on the ticket"
cleanup_env

# --- ABS-157 per-seat watchdog override ORCH_AGENT_TIMEOUT_<ROLE> beats global -
# Same resolution seam (run_spawn_cmd) every seat uses, incl. qas. A short global
# watchdog WOULD kill the spawn, but the per-role override gives it enough room to
# finish -> no kill, spawn succeeds. Proves the override precedence resolves.
new_env
export STUB_HANG=1 STUB_HANG_SECONDS=3
export ORCH_AGENT_TIMEOUT=1                  # global would kill after 1s
export ORCH_AGENT_TIMEOUT_BE_DEVELOPER=30    # per-seat override gives 30s -> survives
T=$(tracker create --type ticket --title "Per-role timeout override" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF ticket=$T" "per-role timeout override -> spawn survives global watchdog and hands off"
assert_not_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "per-role timeout override -> no watchdog kill / crash"
assert_not_contains "$out" "spawn watchdog: killing $T" "per-role override suppresses the watchdog kill the global would have triggered"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}dry-run vs --live — dry-run logs intents but never invokes the stub${NC}"
# =============================================================================
new_env
STUB_RECORD_FILE="$TEST_DIR/rec3.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Dry vs live" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "dry-run logs the SPAWN intent"
assert_eq "$([ -s "$STUB_RECORD_FILE" ] && echo nonempty || echo empty)" "empty" "dry-run does NOT invoke the stub spawn"
assert_not_contains "$out" "INTENT HANDOFF" "dry-run posts no handoff"
cleanup_env

new_env
STUB_RECORD_FILE="$TEST_DIR/rec4.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Live handoff" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF ticket=$T" "--live posts a handoff intent"
assert_eq "$([ -s "$STUB_RECORD_FILE" ] && echo nonempty || echo empty)" "nonempty" "--live invokes the stub spawn"
handoff_blocks=$(tracker get "$T" | grep -c "kind: handoff | actor: orchestrator" || true)
assert_eq "$handoff_blocks" "1" "--live lands a kind:handoff comment on the ticket"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-132 transition-on-handoff — runner applies the declared target${NC}"
# =============================================================================
# The handoff declares `- to: In Progress` but the seat does NOT transition; the
# runner applies the target itself via the adapter (actor = seat role).
new_env
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Runner applies target" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=be-developer to=In Progress" "runner applies the declared handoff target"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "ticket moved to the declared target"
# run.log carries a runner-applied transition event (new event type).
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "INTENT-RUNNER-TRANSITION" "run.log records a runner-applied transition event (ABS-132)"
# The runner-applied transition-reason comment is attributed to the seat role so
# the rework counter counts it like a seat bounce (scope item 4).
assert_contains "$(tracker get "$T")" "actor: be-developer" "runner-applied transition attributed to the seat role"
unset STUB_HANDOFF_TO
cleanup_env

# --- idempotent: seat already at target -> no double transition ----------------
# The seat transitions to In Progress AND the handoff declares the same target;
# the runner sees Ist=Soll and does not transition a second time (no error).
new_env
STUB_TRANSITION_TO="In Progress"; export STUB_TRANSITION_TO
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Seat already moved" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "seat-driven target reached"
moves=$(tracker get "$T" | grep -c "Transition: Ready for Development -> In Progress" || true)
assert_eq "$moves" "1" "no double transition when seat already reached the target (Ist=Soll)"
assert_not_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=be-developer to=In Progress" "runner does not re-apply an already-reached target"
unset STUB_TRANSITION_TO STUB_HANDOFF_TO
cleanup_env

# --- loop-guard: k unmoved respawns escalate to Needs PO Decision --------------
# The handoff parses but carries NO declared target and the seat never moves the
# ticket; after ORCH_RESPAWN_LIMIT no-move respawns the runner escalates.
new_env
T=$(tracker create --type ticket --title "Endless nomove" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Sweep 1: parse handoff, no move -> first HANDOFF-NOMOVE marker (no escalation).
ORCH_RESPAWN_LIMIT=2 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
after1=$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')
assert_eq "$after1" "Ready for Development" "still resting after the first no-move respawn"
# Sweep 2: second no-move -> escalation to Needs PO Decision + decision comment.
out=$(ORCH_RESPAWN_LIMIT=2 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>&1)
assert_contains "$out" "INTENT RESPAWN-LIMIT ticket=$T" "k no-move respawns emit a RESPAWN-LIMIT intent"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Needs PO Decision" "k no-move respawns escalate to Needs PO Decision"
assert_contains "$(tracker get "$T")" "Respawn limit reached" "escalation lands a reasoned decision comment"
cleanup_env

# --- kill-switch: ORCH_HANDOFF_TRANSITION=0 keeps legacy seat-only behavior ----
new_env
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Legacy off" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_HANDOFF_TRANSITION=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T" "ORCH_HANDOFF_TRANSITION=0 disables runner-applied transitions"
unset STUB_HANDOFF_TO
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-133 SKIP-LOCKED re-queue — a lock-skipped dispatch on a legit-rest status is retried${NC}"
# =============================================================================
# Befund 5 (run ABS-126): a tech-writer dispatch on Done was SKIP-LOCKED while a
# DIFFERENT in-flight spawn held the ticket lock. Done is legit-rest, so reconcile
# never re-derived it and the dispatch was LOST. Now SKIP-LOCKED defers into the
# pending set (rc 3, like a cap defer) and the pending-set retry catches it once
# the lock releases.
#
# Deterministic model of the concurrent in-flight spawn: pre-create the ticket's
# single-flight lock dir (same simulation the §5.2 test uses) and release it from
# a background job shortly after — the "other" spawn finishing. The lock is held
# for cycle 1 (the Done net-event -> SKIP-LOCKED -> re-queued) and freed well
# before the run's cycles are exhausted, so a later drain retries + executes the
# tech-writer exactly once. Reconcile is OFF, so ONLY the ABS-133 rc-3 re-queue
# can rescue it (Done is legit-rest, never reconciled).
new_env
STUB_RECORD_FILE="$TEST_DIR/skiplocked.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Lost done dispatch" --role be-developer)
baseline
# Walk validly to In Test (spawns qas). ABS-137 made Done map to NOOP (docs come
# from the pre-merge Docs station), so the original Done->tech-writer target of
# this test no longer dispatches; the SKIP-LOCKED re-queue mechanic under test is
# status-agnostic and reconcile is OFF here, so In Test proves the same path.
# The walk collapses to ONE net In-Test event on the next poll (the mock emits
# status diffs).
for s in "Ready for Development" "In Progress" "In Review" "In Test"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
# A DIFFERENT in-flight spawn (from a prior cycle) still holds the ticket lock,
# and finishes ~2s in — freeing it for the re-queued dispatch to retry.
mkdir -p "$ORCH_STATE_DIR/locks/$T"
( sleep 2; rmdir "$ORCH_STATE_DIR/locks/$T" 2>/dev/null || true ) &
out=$(ORCH_POLL_INTERVAL=1 ORCH_MAX_CYCLES=6 \
      ORCH_RECONCILE_ON_STARTUP=0 ORCH_RECONCILE_EVERY_N_CYCLES=0 \
      orch --live 2>&1)
wait 2>/dev/null || true
assert_contains "$out" "INTENT SKIP-LOCKED ticket=$T" "dispatch behind a held lock is SKIP-LOCKED (re-queued, not dropped)"
qas_spawns=$(grep -c "qas" "$STUB_RECORD_FILE" || true)
assert_eq "$qas_spawns" "1" "the SKIP-LOCKED qas dispatch (reconcile off) is retried + EXECUTED exactly once"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-133 Merging human-gate rest — a clean rte handoff lands on Ready for Merge${NC}"
# =============================================================================
# Befund 7 (run ABS-126): Merging is NOT a rest status, so while the PR waited for
# the human merge, reconcile re-spawned a fresh rte (~$0.75) every cadence. Now a
# clean rte handoff with NO declared target defaults (handoff_default_target) to
# Ready for Merge (a legit-rest, human-owned gate) so reconcile stops re-deriving.
new_env
STUB_RECORD_FILE="$TEST_DIR/merging.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "PR awaiting human merge")
baseline
# Walk validly into Merging via the v3 story chain (Story Acceptance -> Merging),
# then drain the walk events so the ticket simply RESTS at Merging and reconcile
# is the actor that re-derives the rte spawn.
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Design Test" "Story Acceptance" "Merging"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1   # drain the walk events
# Reconcile ON every cycle: without the default target the Merging ticket would be
# re-derived (a fresh rte) each sweep. The seat hands off cleanly (no STUB_HANDOFF_TO)
# so the runner applies the Merging default itself.
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=3 ORCH_RECONCILE_EVERY_N_CYCLES=1 \
      ORCH_RECONCILE_ON_STARTUP=1 orch --live 2>&1)
assert_contains "$out" "INTENT SPAWN ticket=$T role=rte to=Merging" "Merging spawns the rte seat"
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=rte to=Ready for Merge" "clean rte handoff defaults Merging -> Ready for Merge"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Ready for Merge" "ticket rests at the human-owned Ready for Merge gate"
rte_spawns=$(grep -c "rte" "$STUB_RECORD_FILE" || true)
assert_eq "$rte_spawns" "1" "rte spawns exactly once — no re-spawn loop while the PR waits for the human"
assert_not_contains "$out" "INTENT HANDOFF-NOMOVE ticket=$T" "the default target moves the ticket, so the loop-guard never fires"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-133 regression — legit-rest unchanged; the default target is Merging-only${NC}"
# =============================================================================
# (a) The Merging default must NOT leak to other spawn statuses: a be-developer
# clean handoff at Ready for Development with no declared target still rests and
# trips the loop-guard (HANDOFF-NOMOVE), exactly as before ABS-133.
new_env
T=$(tracker create --type ticket --title "No default leak" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1)
assert_not_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T" "no default target for a non-Merging status (Ready for Development still rests)"
assert_contains "$out" "INTENT HANDOFF-NOMOVE ticket=$T" "the loop-guard is still the backstop for statuses with no default"
cleanup_env

# (b) A genuine resting Ready for Merge ticket is never re-spawned by reconcile
# (legit-rest, human-owned) — the ABS-133 Merging landing zone stays quiescent.
new_env
STUB_RECORD_FILE="$TEST_DIR/rest_rfm.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "Resting at human merge gate")
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1   # drain the walk events
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=1 \
      orch --live 2>&1)
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "reconcile never re-spawns a ticket resting at Ready for Merge"
assert_eq "$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')" "0" "no spawn seam invocation for a ticket at the human-owned merge gate"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-62 stall detection — mechanical raise of Needs PO Decision${NC}"
# =============================================================================
# The reconciliation sweep runs two mechanical, bash-only stall rules over resting
# Backlog tickets and raises "Needs PO Decision" (which the ABS-61 mapping routes
# to a fresh PO-Agent). Judgment stays with the PO-Agent; the sweep only detects.
# Tests backdate the frontmatter timestamps directly (a fixture manipulation, not
# an adapter path) to simulate an aged ticket without waiting real seconds.

# backdate_field <ticket-id> <field> <iso-value> — rewrite one frontmatter
# timestamp in place (test fixture helper; the adapter never backdates).
backdate_field() {
    local file="$MOCK_TRACKER_TICKETS_DIR/$1.md" field="$2" value="$3" tmp
    tmp="$file.bd.$$"
    awk -v k="$field" -v v="$value" '
        NR==1 && $0=="---" { fm=1; print; next }
        fm==1 && $0=="---" { fm=2; print; next }
        fm==1 && index($0, k ": ")==1 { print k ": " v; next }
        { print }
    ' "$file" > "$tmp" && mv "$tmp" "$file"
}

# --- (a) bare epic older than threshold in Backlog -> raised (dry-run intent) ---
new_env
E=$(tracker create --type epic --title "Undecomposed epic" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null    # drain creation events
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E role=- to=Needs PO Decision note=rule=1" "dry-run: aged bare epic -> INTENT STALL-RAISE (rule 1)"
status=$(tracker get "$E" | grep '^status:' | head -1)
assert_eq "$status" "status: Backlog" "dry-run: stall detection does not transition the ticket"
cleanup_env

# --- (a) live mode -> transition to Needs PO Decision + reason comment (rule 1) --
new_env
E=$(tracker create --type epic --title "Undecomposed epic live" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E" "live: aged bare epic -> INTENT STALL-RAISE"
status=$(tracker get "$E" | grep '^status:' | head -1)
assert_eq "$status" "status: Needs PO Decision" "live: raise transitions ticket to Needs PO Decision"
raise_comment=$(tracker get "$E" | grep -c "STALL-RAISE rule=1 (orchestrator)" || true)
assert_eq "$raise_comment" "1" "live: orchestrator kind:decision comment names rule 1"
raise_kind=$(tracker get "$E" | grep -B2 "STALL-RAISE rule=1 (orchestrator)" | grep -c "kind: decision | actor: orchestrator" || true)
assert_eq "$raise_kind" "1" "live: the stall-raise marker lives in a kind:decision comment"
actor_reason=$(tracker get "$E" | grep -c "Transition: Backlog -> Needs PO Decision" || true)
assert_eq "$actor_reason" "1" "live: raise is a tracked Backlog -> Needs PO Decision transition (ADR-A-0006)"
cleanup_env

# --- (b) second sweep does NOT re-raise -----------------------------------------
new_env
E=$(tracker create --type epic --title "No double raise" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
ORCH_STALL_EPIC_SECONDS=900 orch --live --once >/dev/null 2>&1   # first sweep raises
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --live --once 2>/dev/null)  # second sweep
raise_count=$(echo "$out" | grep -c "INTENT STALL-RAISE ticket=$E" || true)
assert_eq "$raise_count" "0" "second sweep does not re-raise (ticket parked in Needs PO Decision)"
# ...and after the PO routes it back to Backlog ("leave it in Backlog"), the
# re-raise guard must STILL suppress — otherwise it loops forever.
tracker transition "$E" "Backlog" --actor po-agent --reason "leave in Backlog, not ready" >/dev/null
backdate_field "$E" created "2000-01-01T00:00:00Z"   # still aged
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --live --once 2>/dev/null)
reraise=$(echo "$out" | grep -c "INTENT STALL-RAISE ticket=$E" || true)
assert_eq "$reraise" "0" "PO 'leave it in Backlog' decision does not re-raise (re-raise guard, no infinite loop)"
cleanup_env

# --- (b) edit-after-park RE-ARMS -> a fresh edit after the PO decision re-raises -
# The `updated:` contract: skip a raised+parked ticket UNLESS `updated:` changed
# since the PO's park. A `tracker update` (no transition, no comment) bumps
# `updated:` past the park timestamp and must re-arm both rules.
new_env
E=$(tracker create --type epic --title "Edit after park" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
ORCH_STALL_EPIC_SECONDS=900 orch --live --once >/dev/null 2>&1        # raise
tracker transition "$E" "Backlog" --actor po-agent --reason "leave it" >/dev/null   # PO park
# No edit yet: still suppressed.
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$E" "parked, no edit -> still suppressed"
# Now an edit bumps `updated:` strictly past the park -> must re-raise.
tracker update "$E" title "edited after the PO parked it" >/dev/null
backdate_field "$E" updated "2099-01-01T00:00:00Z"   # unambiguously newer than the park
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E" "edit after park (updated: newer than park) RE-RAISES (updated: contract)"
cleanup_env

# --- (b) cross-rule: a rule-1 raise the PO parked is NOT re-flagged by rule 2 ----
# "Never re-flag a ticket the PO already routed" must hold ACROSS rules. With both
# knobs enabled, a ticket raised under rule 1 and parked back to Backlog must not
# be re-raised by rule 2 (whose own marker was never written).
new_env
E=$(tracker create --type epic --title "Cross rule guard" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
backdate_field "$E" updated "2000-01-01T00:00:00Z"
tracker events >/dev/null
# Raise under rule 1 only (resting off), so only a rule=1 marker exists.
ORCH_STALL_EPIC_SECONDS=900 ORCH_STALL_RESTING_SECONDS=0 orch --live --once >/dev/null 2>&1
tracker transition "$E" "Backlog" --actor po-agent --reason "leave it" >/dev/null   # PO park
backdate_field "$E" created "2000-01-01T00:00:00Z"   # still aged for BOTH rules
backdate_field "$E" updated "2000-01-01T00:00:00Z"   # no edit after park (== park -> suppressed)
tracker events >/dev/null
# Now BOTH knobs on: rule 2 would fire on age alone, but the cross-rule guard must suppress it.
out=$(ORCH_STALL_EPIC_SECONDS=900 ORCH_STALL_RESTING_SECONDS=100 orch --dry-run --once 2>/dev/null)
reflag=$(echo "$out" | grep -c "INTENT STALL-RAISE ticket=$E" || true)
assert_eq "$reflag" "0" "cross-rule: rule-1 raise the PO parked is not re-flagged by rule 2 (guard holds across rules)"
cleanup_env

# --- (b) PO routes to Ready for Development, then deprioritized back -> re-raise --
# Suppression applies ONLY to a live PO park (Needs PO Decision -> Backlog). If the
# PO instead routed the ticket to Ready for Development and it was LATER
# deprioritized back to Backlog (still bare + aged), that is a fresh stall the
# sweep must raise again. Guarding it forever off the mere presence of a marker
# (the earlier FINDING-1 bug) would deadlock detection.
new_env
E=$(tracker create --type epic --title "Routed to dev then back" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
ORCH_STALL_EPIC_SECONDS=900 orch --live --once >/dev/null 2>&1        # raise -> Needs PO Decision
# PO decides "work it" -> Ready for Development (NOT a park).
tracker transition "$E" "Ready for Development" --actor po-agent --reason "prioritize" >/dev/null
# Later deprioritized back to Backlog; epic is still bare and aged.
tracker transition "$E" "Backlog" --actor po-agent --reason "deprioritized" >/dev/null
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E" "routed to dev then deprioritized back to Backlog RE-RAISES (no Needs-PO-Decision park exists)"
cleanup_env

# --- (b) half-raise (comment landed, transition failed) -> the raise is retried --
# If a live raise posts the marker comment but its transition fails, the ticket is
# left in Backlog with a marker but NO park transition. The sweep must retry the
# raise so a PO-Agent is actually spawned — not suppress forever.
new_env
E=$(tracker create --type epic --title "Half raise" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
# Simulate the half-raise directly: only the orchestrator decision+marker comment
# exists; no Backlog -> Needs PO Decision transition happened.
tracker comment "$E" --kind decision --actor orchestrator \
    --body "Stall detected: undecomposed epic [STALL-RAISE rule=1 (orchestrator)]" >/dev/null
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
status=$(tracker get "$E" | grep '^status:' | head -1)
assert_eq "$status" "status: Backlog" "half-raise leaves the ticket in Backlog (transition never happened)"
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E" "half-raise (marker but no park) is RETRIED, not suppressed forever"
cleanup_env

# --- (b) anchored marker: comment PROSE merely quoting the marker does not disarm -
# The guard's marker check is anchored to a kind:decision + actor:orchestrator
# comment body, so a ticket whose own prose merely quotes the marker text (common
# for a ticket about ABS-62 itself) is NOT treated as already-raised.
new_env
E=$(tracker create --type epic --title "Prose mentions the marker" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker comment "$E" --kind understanding --actor be-developer \
    --body "This ticket documents the STALL-RAISE rule=1 (orchestrator) marker format." >/dev/null
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$E" "prose merely quoting the marker does not disarm detection (anchored match)"
cleanup_env

# --- (c) disable via knob -> no raise -------------------------------------------
new_env
E=$(tracker create --type epic --title "Aged but disabled" --label orchestrator-ready)
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$E" "ORCH_STALL_EPIC_SECONDS=0 disables rule 1"
cleanup_env

# --- (c) rule 2 opt-in: resting Backlog ticket raised only when knob enabled ----
new_env
R=$(tracker create --type ticket --title "Resting too long" --label orchestrator-ready)
backdate_field "$R" updated "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=0 ORCH_STALL_RESTING_SECONDS=100 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT STALL-RAISE ticket=$R role=- to=Needs PO Decision note=rule=2" "resting knob on -> rule 2 raises the aged Backlog ticket"
out=$(ORCH_STALL_EPIC_SECONDS=0 ORCH_STALL_RESTING_SECONDS=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$R" "resting knob off (default 0) -> rule 2 disabled"
cleanup_env

# --- (d) non-Backlog states untouched; young/childed epics untouched ------------
new_env
# Aged epic that has already left Backlog must not be stall-raised.
ED=$(tracker create --type epic --title "Aged in dev" --label orchestrator-ready)
backdate_field "$ED" created "2000-01-01T00:00:00Z"
tracker transition "$ED" "Ready for Development" --actor po --reason go >/dev/null
# Aged epic WITH a child is decomposed -> rule 1 does not apply.
EC=$(tracker create --type epic --title "Aged with child" --label orchestrator-ready)
backdate_field "$EC" created "2000-01-01T00:00:00Z"
tracker create --type ticket --title "child" --parent "$EC" >/dev/null
# Young bare epic in Backlog -> under threshold, no raise.
EY=$(tracker create --type epic --title "Young bare epic" --label orchestrator-ready)
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$ED" "non-Backlog aged epic is untouched (rule 1 is Backlog-only)"
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$EC" "aged epic WITH children is not raised (already decomposed)"
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$EY" "young bare epic under threshold is not raised"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-101 Backlog opt-in gate — orchestrator-ready label${NC}"
# =============================================================================
# The orchestrator only acts on a Backlog ticket carrying $ORCH_START_LABEL
# (default orchestrator-ready). Unlabelled tickets are fully inert: no PO sweep,
# no stall raise, no reconcile re-derive. Gate ON is the fail-safe default.

# --- (a) gate ON (default): unlabelled Backlog ticket is skipped ----------------
new_env
T=$(tracker create --type ticket --title "Ungated backlog")
out=$(orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-UNLABELLED ticket=$T role=- to=Backlog" "gate on: unlabelled Backlog ticket -> SKIP-UNLABELLED"
assert_not_contains "$out" "INTENT SPAWN ticket=$T role=po-agent" "gate on: unlabelled ticket never spawns po-agent"
cleanup_env

# --- (b) gate ON: labelled Backlog ticket flows to the PO sweep ------------------
new_env
T=$(tracker create --type ticket --title "Gated backlog" --label orchestrator-ready)
out=$(orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Backlog" "gate on: labelled Backlog ticket -> SPAWN po-agent"
assert_not_contains "$out" "INTENT SKIP-UNLABELLED ticket=$T" "gate on: labelled ticket is not skipped"
cleanup_env

# --- (c) gate OFF (ORCH_REQUIRE_START_LABEL=0): legacy behaviour -----------------
new_env
T=$(tracker create --type ticket --title "Gate disabled")
out=$(ORCH_REQUIRE_START_LABEL=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Backlog" "gate off: unlabelled Backlog ticket -> SPAWN po-agent (legacy)"
assert_not_contains "$out" "INTENT SKIP-UNLABELLED ticket=$T" "gate off: nothing is skipped for the label"
cleanup_env

# --- (d) custom label via ORCH_START_LABEL --------------------------------------
new_env
T=$(tracker create --type ticket --title "Custom label" --label go-now)
out=$(ORCH_START_LABEL=go-now orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Backlog" "custom ORCH_START_LABEL: matching label -> SPAWN"
cleanup_env

# --- (e) runtime label-add is picked up by reconcile, no restart / no event -----
# A labelled ticket whose creation event was already consumed (drained here to
# simulate a label added to an already-resting ticket) is still re-derived by the
# reconcile sweep — the ABS-101 exception to Backlog's normal reconcile exclusion.
new_env
T=$(tracker create --type ticket --title "Labelled after resting" --label orchestrator-ready)
tracker events >/dev/null   # drain the creation event: only reconcile can see it now
out=$(orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent to=Backlog" "reconcile re-derives a labelled resting Backlog ticket (no fresh event, no restart)"
cleanup_env

# --- (f) an unlabelled resting ticket is fully inert (no event, no reconcile) ----
new_env
T=$(tracker create --type ticket --title "Unlabelled resting")
tracker events >/dev/null   # drain the creation event
out=$(orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "reconcile does not re-derive an unlabelled resting Backlog ticket"
cleanup_env

# --- (g) stall gate: an unlabelled aged bare epic is NOT stall-raised ------------
new_env
E=$(tracker create --type epic --title "Unlabelled aged epic")
backdate_field "$E" created "2000-01-01T00:00:00Z"
tracker events >/dev/null
out=$(ORCH_STALL_EPIC_SECONDS=900 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT STALL-RAISE ticket=$E" "gate on: unlabelled aged bare epic is NOT stall-raised (resting, not stalled)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-92 stable-governs-dev — work-state follows ORCH_TARGET_REPO${NC}"
# =============================================================================
# With ORCH_TARGET_REPO set to a separate (fake) git-root dev repo, all work-state
# (state dir, stop file, packets) is created under the TARGET's work/, NOT the
# harness/script repo's. The mock ticket store is retargeted too, and a kill-switch
# file placed in the TARGET stops the run. Defaults (no seam) still land under the
# harness repo — a placement regression check.

# make_target_repo — a temp dir that is a git repo root (has a .git), with a
# tickets dir seeded so the mock adapter can operate against it. Prints the path.
make_target_repo() {
    local d
    d="$(mktemp -d /tmp/orchestrator-target-XXXXXX)"
    mkdir -p "$d/.git" "$d/work/tickets"
    echo "$d"
}

# --- (a) H2b placement: state dir/stop file/packets under the TARGET -----------
new_env
# Drop the per-env state/ticket overrides so the seam's target-relative defaults
# take effect (explicit env would otherwise win).
unset ORCH_STATE_DIR ORCH_STOP_FILE MOCK_TRACKER_TICKETS_DIR
TARGET="$(make_target_repo)"
export ORCH_TARGET_REPO="$TARGET"
# Seed a ticket directly into the target store (the tracker function is invoked
# outside orchestrator.sh, so it does not inherit the seam's export — mirror it
# here for setup). The orchestrator run below inherits the seam and must read it.
T=$(MOCK_TRACKER_TICKETS_DIR="$TARGET/work/tickets" tracker create --type ticket --title "Target placement" --role be-developer)
assert_eq "$([ -f "$TARGET/work/tickets/$T.md" ] && echo yes || echo no)" "yes" "ticket seeded under ORCH_TARGET_REPO/work/tickets"
# The orchestrator (with no explicit MOCK_TRACKER_TICKETS_DIR) must find the
# seeded target ticket via the seam's auto-export -> it surfaces as a creation event.
seam_events=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 | grep -F "ticket=$T" | head -1)
assert_contains "$seam_events" "$T" "seam auto-exports MOCK_TRACKER_TICKETS_DIR -> orchestrator reads the target store"
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
assert_eq "$([ -d "$TARGET/work/.orchestrator" ] && echo yes || echo no)" "yes" "state dir created under TARGET work/.orchestrator"
assert_eq "$([ -d "$TARGET/work/.orchestrator/packets" ] && echo yes || echo no)" "yes" "packets dir created under TARGET work/.orchestrator"
# Provenance line names harness + target.
prov=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 | grep "provenance:" | head -1)
assert_contains "$prov" "target=$TARGET" "startup provenance line reports target=<dev repo>"
assert_contains "$prov" "harness=$REPO_ROOT" "startup provenance line reports harness=<stable repo>"
# Kill-switch file in the TARGET stops the run.
touch "$TARGET/work/.orchestrator-stop"
ec=0
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1) || ec=$?
assert_eq "$ec" "0" "kill switch under TARGET work/ -> exit 0"
assert_contains "$out" "kill-switch present" "kill switch under TARGET is honored"
unset ORCH_TARGET_REPO
rm -rf "$TARGET"
cleanup_env

# --- (a2) non-existent / non-git target dies with a clear message --------------
new_env
unset ORCH_STATE_DIR ORCH_STOP_FILE MOCK_TRACKER_TICKETS_DIR
ec=0
out=$(ORCH_TARGET_REPO="/tmp/orchestrator-no-such-$$" orch --dry-run --once 2>&1) || ec=$?
assert_eq "$ec" "1" "missing ORCH_TARGET_REPO -> exit 1"
assert_contains "$out" "does not exist" "missing target reports a clear error"
NONGIT="$(mktemp -d /tmp/orchestrator-nongit-XXXXXX)"
ec=0
out=$(ORCH_TARGET_REPO="$NONGIT" orch --dry-run --once 2>&1) || ec=$?
assert_eq "$ec" "1" "non-git ORCH_TARGET_REPO -> exit 1"
assert_contains "$out" "not a git repo root" "non-git target reports a clear error"
rm -rf "$NONGIT"
cleanup_env

# --- (b) defaults regression: no seam -> state under the SCRIPT/harness repo ----
# An explicit temp state dir (as new_env sets) still wins; assert the seam-free
# ORCH_STATE_ROOT resolves to REPO_ROOT by unsetting the override and checking the
# default placement in an isolated HOME-free run against the harness repo's work/.
new_env
# new_env sets explicit ORCH_STATE_DIR/STOP_FILE; those must be honored unchanged.
T=$(tracker create --type ticket --title "Defaults regression")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
assert_eq "$([ -d "$ORCH_STATE_DIR" ] && echo yes || echo no)" "yes" "no seam: explicit ORCH_STATE_DIR override still honored"
prov=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 | grep "provenance:" | head -1)
assert_contains "$prov" "harness=$REPO_ROOT" "no seam: provenance harness == script repo"
assert_contains "$prov" "target=$REPO_ROOT" "no seam: provenance target == harness (single-repo)"
cleanup_env

# --- (c) spawn cwd == target when the seam is set ------------------------------
# Point ORCH_SPAWN_CMD at the REAL spawn seam (which does the cd to the target)
# but with ORCH_CLAUDE_BIN as a recorder that prints its $PWD. Assert the recorded
# cwd is the target repo, not the harness. A minimal role def is placed in a temp
# harness so the seam materializes it.
new_env
unset ORCH_STATE_DIR ORCH_STOP_FILE MOCK_TRACKER_TICKETS_DIR ORCH_SPAWN_CMD
TARGET="$(make_target_repo)"
HARNESS="$(mktemp -d /tmp/orchestrator-harness-XXXXXX)"
mkdir -p "$HARNESS/.claude/agents"
cat > "$HARNESS/.claude/agents/be-developer.md" <<'ROLEDEF'
---
name: be-developer
description: test role
tools: [Read, Bash]
---
Minimal role body for the ABS-92 spawn-cwd test.
ROLEDEF
# Recorder claude bin: print cwd (where the real seam cd'd to) then a JSON result.
CWDLOG="$TARGET/cwd.log"
RECORDER="$(mktemp /tmp/orchestrator-recorder-XXXXXX.sh)"
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
pwd -P > "$CWDLOG"
echo '{"result": "handoff recorded", "session_id": "rec"}'
exit 0
RECBIN
chmod +x "$RECORDER"
export ORCH_TARGET_REPO="$TARGET"
export ORCH_HARNESS_HOME="$HARNESS"
export ORCH_SPAWN_CMD="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"
export ORCH_CLAUDE_BIN="$RECORDER"
# Seed the ticket in the TARGET store, driven to a reconcilable status (Ready for
# Development). The startup reconciliation sweep (default on) dispatches it once,
# routing to the real spawn seam -> the recorder logs its cwd.
TSTORE="$TARGET/work/tickets"
T=$(MOCK_TRACKER_TICKETS_DIR="$TSTORE" tracker create --type ticket --title "Spawn cwd" --role be-developer)
MOCK_TRACKER_TICKETS_DIR="$TSTORE" tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
orch --live --once >/dev/null 2>&1
recorded_cwd="$(cat "$CWDLOG" 2>/dev/null || true)"
target_phys="$(cd "$TARGET" && pwd -P)"
assert_eq "$recorded_cwd" "$target_phys" "spawn cwd == ORCH_TARGET_REPO when the seam is set"
unset ORCH_TARGET_REPO ORCH_HARNESS_HOME ORCH_CLAUDE_BIN
rm -rf "$TARGET" "$HARNESS" "$RECORDER"
cleanup_env

# --- (d) namespace-preferred agent-def resolution (ABS-96/97) ------------------
# The spawn seam (scripts/orchestrator-spawn-claude.sh) resolves ORCH_AGENTS_DIR
# unset -> prefers $ORCH_HARNESS_HOME/harness/claude/agents, else the pre-v2.23.0
# $ORCH_HARNESS_HOME/harness/.claude/agents when that dir exists,
# else falls back to $ORCH_HARNESS_HOME/.claude/agents (ABS-96 decision doc §6).
# This test does NOT hardcode the resolution logic — it builds BOTH candidate
# dirs with distinguishable role-def bodies and asserts the seam's own choice
# (via the recorder relaying which body it read) is the namespace one. The
# fixture deliberately uses the DOTTED harness/.claude namespace to simulate a
# pre-v2.23.0 stable checkout, exercising the seam's legacy fallback.
new_env
unset ORCH_STATE_DIR ORCH_STOP_FILE MOCK_TRACKER_TICKETS_DIR ORCH_SPAWN_CMD
TARGET="$(make_target_repo)"
HARNESS="$(mktemp -d /tmp/orchestrator-harness-ns-XXXXXX)"
mkdir -p "$HARNESS/harness/.claude/agents" "$HARNESS/.claude/agents"
cat > "$HARNESS/harness/.claude/agents/be-developer.md" <<'ROLEDEF'
---
name: be-developer
description: test role (namespace source)
tools: [Read, Bash]
---
NAMESPACE role body — should win when harness/.claude/agents exists.
ROLEDEF
cat > "$HARNESS/.claude/agents/be-developer.md" <<'ROLEDEF'
---
name: be-developer
description: test role (legacy live copy)
tools: [Read, Bash]
---
LEGACY role body — should lose to the namespace when both exist.
ROLEDEF
PROMPTLOG="$TARGET/prompt.log"
RECORDER="$(mktemp /tmp/orchestrator-recorder-ns-XXXXXX.sh)"
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$PROMPTLOG"
echo '{"result": "handoff recorded", "session_id": "rec"}'
exit 0
RECBIN
chmod +x "$RECORDER"
export ORCH_TARGET_REPO="$TARGET"
export ORCH_HARNESS_HOME="$HARNESS"
export ORCH_SPAWN_CMD="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"
export ORCH_CLAUDE_BIN="$RECORDER"
TSTORE="$TARGET/work/tickets"
T=$(MOCK_TRACKER_TICKETS_DIR="$TSTORE" tracker create --type ticket --title "Namespace pref" --role be-developer)
MOCK_TRACKER_TICKETS_DIR="$TSTORE" tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
orch --live --once >/dev/null 2>&1
recorded_prompt="$(cat "$PROMPTLOG" 2>/dev/null || true)"
assert_contains "$recorded_prompt" "NAMESPACE role body" "seam prefers harness/.claude/agents (pre-rename fallback) over .claude/agents when both exist"
assert_not_contains "$recorded_prompt" "LEGACY role body" "seam does not read the legacy .claude/agents copy when the namespace exists"
unset ORCH_TARGET_REPO ORCH_HARNESS_HOME ORCH_CLAUDE_BIN
rm -rf "$TARGET" "$HARNESS" "$RECORDER"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-205 worktree state isolation — nested orchestrator does not write LIVE state${NC}"
# =============================================================================
# A parent orchestrator EXPORTS ORCH_PARENT_STATE_ROOT = the state root it owns.
# A child orchestrator invoked from within a worktree (e.g. a QAS smoke/dry-run)
# inherits both the parent's ORCH_TARGET_REPO and that sentinel. The mechanical
# criterion (inherited sentinel + own repo root != parent root) must re-pin the
# child's state to ITS OWN worktree, never the parent's LIVE state dir — while a
# fresh operator self-hosting run (sentinel absent) still lands under the target.
#
# make_wt_repo — a temp dir that looks like a repo root (has .git + work/tickets)
# with a COPY of orchestrator.sh under scripts/, so REPO_ROOT resolves to it.
# Prints the path.
make_wt_repo() {
    local d
    d="$(mktemp -d /tmp/orchestrator-wt-XXXXXX)"
    mkdir -p "$d/.git" "$d/scripts" "$d/work/tickets"
    cp "$ORCH" "$d/scripts/orchestrator.sh"
    echo "$d"
}

new_env
unset ORCH_STATE_DIR ORCH_STOP_FILE MOCK_TRACKER_TICKETS_DIR
LIVE="$(make_target_repo)"          # parent's LIVE state root (the inherited target)
WT="$(make_wt_repo)"                 # the worktree the child runs from
# Point the tracker + spawn seam at the real repo copies so the WT copy of
# orchestrator.sh needs nothing beyond itself. The spawn stub never fires here
# (reconcile off, no eligible ticket) — this asserts startup state PLACEMENT.
export TRACKER_CMD="$TRACKER"
export MOCK_TRACKER_TICKETS_DIR="$WT/work/tickets"
export ORCH_SPAWN_CMD="$STUB"
# Simulate the nested invocation: parent exported ORCH_TARGET_REPO=LIVE and the
# sentinel ORCH_PARENT_STATE_ROOT=LIVE; the child runs from the worktree copy.
ORCH_TARGET_REPO="$LIVE" ORCH_PARENT_STATE_ROOT="$LIVE" \
    ORCH_RECONCILE_ON_STARTUP=0 bash "$WT/scripts/orchestrator.sh" --dry-run --once >/dev/null 2>&1
assert_eq "$([ -d "$WT/work/.orchestrator" ] && echo yes || echo no)" "yes" \
    "ABS-205: nested/worktree orchestrator writes state under its OWN worktree"
assert_eq "$([ -d "$LIVE/work/.orchestrator" ] && echo yes || echo no)" "no" \
    "ABS-205: nested/worktree orchestrator does NOT write into the LIVE/parent state dir"
# Control: a FRESH self-hosting run (no inherited sentinel) still lands under the
# target — the ABS-92 model must not regress.
ORCH_TARGET_REPO="$LIVE" ORCH_RECONCILE_ON_STARTUP=0 \
    bash "$WT/scripts/orchestrator.sh" --dry-run --once >/dev/null 2>&1
assert_eq "$([ -d "$LIVE/work/.orchestrator" ] && echo yes || echo no)" "yes" \
    "ABS-205: fresh self-hosting (no sentinel) still places state under ORCH_TARGET_REPO"
rm -rf "$LIVE" "$WT"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== v3 epic pipeline map rows (ABS-71) ===${NC}\n"
# =============================================================================
# One dry-run intent assertion per epic-pipeline row (spec §1.1): the mapped
# SPAWN/NOTIFY/NOOP fires when a ticket ENTERS the status. This is also the
# ABS-71 executed AC: a scripted walk PO Triage -> ... -> Epic Done against the
# mock adapter, asserting the intent at every hop.
new_env
E=$(tracker create --type epic --title "v3 epic walk")
baseline
walk_assert() {
    # walk_assert <to-status> <expected-intent-fragment> <label> [absent-fragment]
    local to="$1" want="$2" label="$3" absent="${4:-}"
    tracker transition "$E" "$to" --actor agent --reason "walk to $to" >/dev/null
    out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
    assert_contains "$out" "$want" "$label"
    if [ -n "$absent" ]; then
        assert_not_contains "$out" "$absent" "$label (no spurious intent)"
    fi
}
walk_assert "PO Triage"           "INTENT SPAWN ticket=$E role=po-agent to=PO Triage"                   "PO Triage -> SPAWN po-agent"
walk_assert "Grooming"            "INTENT SPAWN ticket=$E role=bsa to=Grooming"                         "Grooming -> SPAWN bsa"
walk_assert "Enrichment"          "INTENT SPAWN ticket=$E role=issue-enrichment to=Enrichment"          "Enrichment -> SPAWN issue-enrichment"
walk_assert "Ticket Review"       "INTENT SPAWN ticket=$E role=qas to=Ticket Review"                    "Ticket Review -> SPAWN qas (DoR gate)"
walk_assert "Architecture Review" "INTENT SPAWN ticket=$E role=system-architect to=Architecture Review" "Architecture Review -> SPAWN system-architect"
walk_assert "Stories In Flight"   "INTENT NOOP ticket=$E"                                               "Stories In Flight -> NOOP (rests; JOIN advances)" "INTENT SPAWN ticket=$E"
walk_assert "Epic Integration"    "INTENT SPAWN ticket=$E role=rte to=Epic Integration"                 "Epic Integration -> SPAWN rte"
walk_assert "Ready for Epic Acceptance" "INTENT NOTIFY"                                                 "Ready for Epic Acceptance -> NOTIFY (no spawn)" "INTENT SPAWN ticket=$E"
# The one human notification carries the ready-to-test text.
assert_contains "$out" "ready-to-test" "Ready for Epic Acceptance NOTIFY says ready-to-test"
walk_assert "Epic Done"           "INTENT SPAWN ticket=$E role=self-improvement to=Epic Done"           "Epic Done -> SPAWN self-improvement (retro auto-trigger)"
cleanup_env

# --- DoR rework bounce: Ticket Review -> Grooming re-spawns the BSA -----------
new_env
E=$(tracker create --type epic --title "v3 DoR bounce")
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
baseline
tracker transition "$E" "Grooming" --actor qas --reason "DoR rework verdict" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$E role=bsa to=Grooming" "Ticket Review -> Grooming bounce re-spawns bsa"
cleanup_env

# --- reconcile re-derives every agent-owned epic status ------------------------
# A ticket resting in a transient epic seat with no live lock is a lost event
# the startup sweep must recover; the two resting states and terminal Epic Done
# must NEVER be re-derived (mass-spawn/loop protection, ABS-71).
for combo in \
    "PO Triage:po-agent" "Grooming:bsa" "Enrichment:issue-enrichment" \
    "Ticket Review:qas" "Architecture Review:system-architect" "Epic Integration:rte"; do
    st="${combo%%:*}"; role="${combo#*:}"
    new_env
    E=$(tracker create --type epic --title "recon $st")
    tracker transition "$E" "PO Triage" --actor agent --reason walk >/dev/null
    for s in "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Stories In Flight" "Epic Integration"; do
        [ "$st" = "PO Triage" ] && break
        tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
        [ "$s" = "$st" ] && break
    done
    tracker events >/dev/null 2>&1   # drain: only the sweep can recover now
    out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
    assert_contains "$out" "INTENT SPAWN ticket=$E role=$role to=$st" "reconcile re-derives $st -> $role"
    cleanup_env
done

for st in "Stories In Flight" "Ready for Epic Acceptance" "Epic Done"; do
    new_env
    E=$(tracker create --type epic --title "resting $st")
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" \
             "Stories In Flight" "Epic Integration" "Ready for Epic Acceptance" "Epic Done"; do
        tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
        [ "$s" = "$st" ] && break
    done
    tracker events >/dev/null 2>&1
    out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
    assert_not_contains "$out" "INTENT SPAWN ticket=$E" "reconcile never re-derives resting '$st'"
    cleanup_env
done

# =============================================================================
echo -e "\n${CYAN}=== v3 story pipeline map rows + SKIP-FORWARD (ABS-72/83/84) ===${NC}\n"
# =============================================================================
# Max-flag story (design+security+data): every conditional seat spawns; this is
# the ABS-72 executed AC for the flagged walk (sim S13 role set).
new_env
E=$(tracker create --type epic --title "v3 story map epic")
S=$(tracker create --type ticket --title "max-flag story" --parent "$E" \
    --role fe-developer --flag design --flag security --flag data)
baseline
walk_story() {
    local to="$1" want="$2" label="$3"
    tracker transition "$S" "$to" --actor agent --reason "walk to $to" >/dev/null
    out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
    assert_contains "$out" "$want" "$label"
}
walk_story "Design"                "INTENT SPAWN ticket=$S role=ui-ux-design to=Design"               "flagged: Design -> SPAWN ui-ux-design"
walk_story "Ready for Development" "INTENT SPAWN ticket=$S role=fe-developer to=Ready for Development" "Ready for Development -> implementer (role hint intact)"
walk_story "In Progress"           "INTENT NOOP ticket=$S"                                            "In Progress stays NOOP (spawn-count-neutral mapping)"
walk_story "In Review"             "INTENT SPAWN ticket=$S role=system-architect to=In Review"        "In Review row unchanged (ABS-57 reviewer)"
walk_story "Security Review"       "INTENT SPAWN ticket=$S role=security-engineer to=Security Review" "flagged: Security Review -> SPAWN security-engineer"
walk_story "Test Prep"             "INTENT SPAWN ticket=$S role=data-provisioning-eng to=Test Prep"   "flagged: Test Prep -> SPAWN data-provisioning-eng"
walk_story "In Test"               "INTENT SPAWN ticket=$S role=qas to=In Test"                       "In Test row unchanged (qas)"
walk_story "Design Test"           "INTENT SPAWN ticket=$S role=qas-design to=Design Test"            "flagged: Design Test -> SPAWN qas-design"
walk_story "Story Acceptance"      "INTENT SPAWN ticket=$S role=po-agent to=Story Acceptance"         "Story Acceptance -> SPAWN po-agent"
walk_story "Merging"               "INTENT SPAWN ticket=$S role=rte to=Merging"                       "Merging -> SPAWN rte"
walk_story "Docs"                  "INTENT SPAWN ticket=$S role=tech-writer to=Docs"                  "Docs -> SPAWN tech-writer"
# Docs -> Done must NOT re-spawn tech-writer (v3 already documented the story).
tracker transition "$S" "Done" --actor tech-writer --reason "docs done" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-DOCS-DONE ticket=$S" "Docs -> Done skips the v2 tech-writer row (no double docs)"
assert_not_contains "$out" "INTENT SPAWN ticket=$S" "no tech-writer double-spawn after the Docs seat"
cleanup_env

# --- ABS-137: Ready for Merge -> Done does NOT spawn tech-writer --------------
# Docs come solely from the Docs station (before the human gate); the Done row
# is NOOP, so a post-merge Done event must not spawn a tech-writer.
new_env
T=$(tracker create --type ticket --title "v2 docs path")
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
baseline
# baseline drained the walk; re-surface Done via reconcile? Done is NOT
# reconcilable — drive the event explicitly instead: recreate the net change.
cleanup_env
new_env
T=$(tracker create --type ticket --title "v2 docs path")
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
baseline
tracker transition "$T" "Done" --actor human --reason merged >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$T role=tech-writer to=Done" "ABS-137: Ready for Merge -> Done does NOT spawn tech-writer (no post-merge docs)"
cleanup_env

# --- SKIP-FORWARD: unflagged story entering Design (live, ABS-84 executed AC) --
new_env
E=$(tracker create --type epic --title "skip epic")
P=$(tracker create --type ticket --title "plain story" --parent "$E")
baseline
tracker transition "$P" "Design" --actor system-architect --reason "released" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$P role=- to=Ready for Development note=unflagged=design at=Design" "unflagged Design -> SKIP-FORWARD intent to Ready for Development"
assert_not_contains "$out" "INTENT SPAWN ticket=$P role=ui-ux-design" "unflagged Design never spawns ui-ux-design"
dump=$(tracker get "$P")
assert_contains "$dump" "status: Ready for Development" "runner re-transitioned the unflagged ticket itself"
assert_contains "$dump" "kind: skip | actor: orchestrator" "audit comment (kind: skip, actor: orchestrator) recorded"
assert_contains "$dump" "SKIP-FORWARD: conditional stage 'Design' skipped (flag 'design' not set)" "audit comment names stage + missing flag"
cleanup_env

# --- SKIP-FORWARD cascade: Security Review -> Test Prep -> In Test (no flags) --
new_env
P=$(tracker create --type ticket --title "cascade story")
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$P" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
done
baseline
tracker transition "$P" "Security Review" --actor system-architect --reason "review passed" >/dev/null
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=3 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null)
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$P role=- to=Test Prep" "cascade 1: Security Review skipped (no security flag)"
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$P role=- to=In Test" "cascade 2: Test Prep skipped (no data flag)"
assert_contains "$out" "INTENT SPAWN ticket=$P role=qas to=In Test" "cascade lands at In Test -> qas spawns"
dump=$(tracker get "$P")
skips=$(printf '%s\n' "$dump" | grep -c "kind: skip | actor: orchestrator" || true)
assert_eq "$skips" "2" "exactly two skip audit comments (one per skipped stage)"
cleanup_env

# --- flagged ticket is NOT skipped even when other flags are absent ------------
new_env
P=$(tracker create --type ticket --title "security-only story" --flag security)
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$P" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
done
baseline
tracker transition "$P" "Security Review" --actor system-architect --reason "review passed" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$P role=security-engineer to=Security Review" "security-flagged ticket spawns security-engineer (not skipped)"
assert_not_contains "$out" "INTENT SKIP-FORWARD ticket=$P" "flagged conditional stage is never skip-forwarded"
cleanup_env

# --- reconcile re-derives story seats (sample: Design flagged, Merging) --------
new_env
P=$(tracker create --type ticket --title "recon design" --flag design)
tracker transition "$P" "Design" --actor system-architect --reason released >/dev/null
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$P role=ui-ux-design to=Design" "reconcile re-derives Design -> ui-ux-design"
cleanup_env
new_env
P=$(tracker create --type ticket --title "recon merging")
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging"; do
    tracker transition "$P" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
done
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$P role=rte to=Merging" "reconcile re-derives Merging -> rte"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== v3 JOIN rule + guards (ABS-73) ===${NC}\n"
# =============================================================================
# Helpers for this section: walk an epic to Stories In Flight / a story to Done.
epic_to_sif() {
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Stories In Flight"; do
        tracker transition "$1" "$s" --actor agent --reason walk >/dev/null
    done
}
story_to_done() {
    for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
             "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done"; do
        tracker transition "$1" "$s" --actor agent --reason walk >/dev/null
    done
}

# --- (a) executed AC: two-child epic — JOIN fires exactly once, on the LAST Done
new_env
E=$(tracker create --type epic --title "join epic")
A=$(tracker create --type ticket --title "story A" --parent "$E")
# B is design-flagged so it RESTS in Design during the live sweep below
# (an unflagged story would be SKIP-FORWARDed out of Design by the runner).
B=$(tracker create --type ticket --title "story B" --parent "$E" --flag design)
epic_to_sif "$E"
story_to_done "$A"
tracker events >/dev/null 2>&1
tracker transition "$B" "Design" --actor agent --reason walk >/dev/null 2>&1 || true
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT JOIN ticket=$E" "first child Done alone does not JOIN"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Stories In Flight" "epic still rests in Stories In Flight"
# Now finish B (it is in Design; continue the chain to Done) and poll: the
# child's Done event triggers the JOIN from dispatch (no sweep needed).
for s in "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done"; do
    tracker transition "$B" "$s" --actor agent --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "last child Done -> JOIN fires"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Epic Integration" "epic transitioned to Epic Integration exactly once"
# Idempotency: further sweeps never re-fire (epic left Stories In Flight).
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "JOIN never re-fires after the epic advanced"
cleanup_env

# --- (b) empty-epic guard: zero children -> Needs PO Decision, no NOTIFY -------
new_env
E=$(tracker create --type epic --title "empty epic")
epic_to_sif "$E"
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN-EMPTY ticket=$E role=- to=Needs PO Decision" "empty epic -> JOIN-EMPTY intent"
assert_not_contains "$out" "ready-to-test" "empty epic never fires the ready-to-test NOTIFY"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "empty epic escalated to Needs PO Decision"
assert_contains "$dump" "JOIN empty-epic guard" "escalation reason recorded on the ticket"
cleanup_env

# --- (c) quiescence guard: unprocessed follow-up blocks JOIN; answer unblocks --
new_env
E=$(tracker create --type epic --title "quiescent epic")
A=$(tracker create --type ticket --title "story w/ follow-up" --parent "$E")
epic_to_sif "$E"
story_to_done "$A"
tracker comment "$A" --kind follow-up --actor qas \
    --body "Follow-up: found a gap while testing; recommend a hardening story." >/dev/null
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN-WAIT ticket=$E" "unprocessed follow-up -> JOIN waits (quiescence)"
assert_not_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "JOIN does not race an unprocessed follow-up"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Stories In Flight" "epic still waiting"
# The BSA answers (ABS-75 chain); the next sweep re-evaluates and JOINs.
tracker comment "$A" --kind bsa-decision --actor bsa \
    --body "Decision: create outside the epic (not AC-blocking)." >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "answered follow-up -> JOIN re-evaluates and fires"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== v3 safety guards (ABS-74) ===${NC}\n"
# =============================================================================
# Two DERIVED counters (parsed from the ticket dump, never shell state, so they
# survive a runner restart for free): the cross-stage rework counter (§3.2) and
# the consecutive-crash counter (§3.8); plus the per-DAY spawn ledger (§5.4).
# The story/epic walk helpers epic_to_sif and story_to_done are defined in the
# ABS-73 section above.

# --- (a) S12 cross-stage rework: 3 bounces by 3 different agents -> REWORK-LIMIT
# A security+design flagged story RESTS at In Review / Security Review (unflagged
# conditional stages would be SKIP-FORWARDed by the live runner, defeating the
# scenario). Three backward transitions to Ready for Development, each by a
# DIFFERENT agent actor, since the last PO decision -> the 3rd dispatch escalates.
new_env
E=$(tracker create --type epic --title "S12 rework epic")
S=$(tracker create --type ticket --title "S12 bouncy story" --parent "$E" \
    --role be-developer --flag security --flag design)
baseline
# walk to In Review, bounce 1 (In Review -> Ready for Development, system-architect)
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor system-architect --reason "rework: findings" >/dev/null
# forward In Progress -> In Review -> Security Review, bounce 2 (security-engineer)
for s in "In Progress" "In Review" "Security Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor security-engineer --reason "rework: vuln" >/dev/null
# forward to In Test, bounce 3 (In Test -> Ready for Development, qas)
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas --reason "rework: test fail" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "3rd cross-stage bounce -> REWORK-LIMIT (not another spawn)"
assert_not_contains "$out" "INTENT SPAWN ticket=$S role=be-developer to=Ready for Development" "no implementer spawn on the escalating dispatch"
dump=$(tracker get "$S")
assert_contains "$dump" "status: Needs PO Decision" "rework-limit escalates the story to Needs PO Decision"
assert_contains "$dump" "Rework limit reached" "rework-limit gate-results comment recorded"
cleanup_env

# --- (b) S16 epic DoR bounces: 3x Ticket Review -> Grooming -> REWORK-LIMIT ----
new_env
E=$(tracker create --type epic --title "S16 DoR epic")
baseline
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 1" >/dev/null
for s in "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 2" >/dev/null
for s in "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 3" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$E" "3rd epic DoR bounce -> REWORK-LIMIT"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "epic DoR rework-limit escalates to Needs PO Decision"
cleanup_env

# --- (c) window reset: a PO decision re-arms the counter (1 < 3 -> SPAWN) ------
# Continue the (a)-style story: after the escalation, the PO routes it back to
# Ready for Development; one more bounce leaves the derived count at 1, so the
# next dispatch SPAWNS the implementer normally instead of re-escalating.
new_env
E=$(tracker create --type epic --title "reset epic")
S=$(tracker create --type ticket --title "reset story" --parent "$E" \
    --role be-developer --flag security --flag design)
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor system-architect --reason "rework 1" >/dev/null
for s in "In Progress" "In Review" "Security Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor security-engineer --reason "rework 2" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas --reason "rework 3" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "reset: story first hits the rework limit"
# Drain events so the diff-based poll snapshots the ticket at Needs PO Decision;
# the PO routing it back to Ready for Development then registers as a real event.
tracker events >/dev/null 2>&1
# PO routes it back onward: Needs PO Decision -> Ready for Development re-arms.
tracker transition "$S" "Ready for Development" --actor po-agent --reason "PO: proceed" >/dev/null
# one more bounce (count re-armed to 1). End at In Review so the net status
# differs from the snapshot; the reconcile sweep re-derives the resting seat.
for s in "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor system-architect --reason "post-reset rework" >/dev/null
tracker events >/dev/null 2>&1   # snapshot the resting Ready for Development seat
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S role=be-developer to=Ready for Development" "post-reset bounce (1<3) SPAWNS normally"
assert_not_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "post-reset dispatch does NOT re-escalate"
cleanup_env

# --- (d) human transitions never count toward the rework limit ----------------
# Three backward transitions by actor human, then a poll must still SPAWN
# (human rejection is forward-fix, not a counted bounce).
new_env
E=$(tracker create --type epic --title "human epic")
S=$(tracker create --type ticket --title "human story" --parent "$E" \
    --role be-developer --flag security --flag design)
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor human --reason "human bounce 1" >/dev/null
for s in "In Progress" "In Review" "Security Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor human --reason "human bounce 2" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor human --reason "human bounce 3" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S role=be-developer to=Ready for Development" "3 human bounces still SPAWN (human excluded)"
assert_not_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "human transitions never trip the rework limit"
cleanup_env

# --- (d2) ABS-267: the runner's OWN redirects never count toward the limit -----
# station_guard() and done_pr_gate() redirect BACKWARD as --actor orchestrator.
# Those are mechanical station corrections, not a seat rejecting the work, so they
# must not bill a rework unit — counting them made ONE QA bounce burn TWO of three
# units (QAS bounce + the guard's redirect) and escalated sound stories (ABS-235).
new_env
E=$(tracker create --type epic --title "orchestrator epic")
S=$(tracker create --type ticket --title "orchestrator story" --parent "$E" \
    --role be-developer --flag security --flag design)
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor orchestrator --reason "STATION-GUARD redirect 1" >/dev/null
for s in "In Progress" "In Review" "Security Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor orchestrator --reason "STATION-GUARD redirect 2" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor orchestrator --reason "STATION-GUARD redirect 3" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S role=be-developer to=Ready for Development" "3 orchestrator redirects still SPAWN (runner excluded, ABS-267)"
assert_not_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "orchestrator redirects never trip the rework limit"
cleanup_env

# --- (d3) ABS-267: a RUNNER-APPLIED transition still counts (it carries the SEAT)
# The anti-regression that keeps the fix honest: transition-on-handoff (ABS-132)
# attributes the runner's adapter call to the SEAT ROLE, not to `orchestrator`. The
# exclusion is on the ACTOR, not on "who called the adapter" — so the canonical QA
# bounce (qas hands off In Test -> In Progress and the RUNNER applies it) is a real
# seat bounce and MUST still increment the counter. A blanket "the runner applied
# it, so it doesn't count" exclusion would mute every genuine bounce; this test
# fails loudly if someone ever writes one.
new_env
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "runner-applied qa bounce" --role be-developer)
baseline
for s in "Ready for Development" "In Progress" "In Review" "In Test"; do
    tracker transition "$T" "$s" --actor agent --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=qas to=In Progress" "runner applies the qas seat's backward handoff target"
assert_contains "$(tracker get "$T")" "kind: transition-reason | actor: qas" "runner-applied bounce carries the SEAT actor, not orchestrator"
assert_eq "$(rework_of "$T")" "1" "runner-applied SEAT bounce still counts as rework (ABS-267 AC3)"
unset STUB_HANDOFF_TO
cleanup_env

# --- (e) S15 crash escalation: 3 separate --live --once runs -> CRASH-LIMIT ----
# STUB_FAIL=1 makes every spawn crash twice (attempt + retry). Each fresh
# invocation is a NEW process; ORCH_RECONCILE_ON_STARTUP=1 re-derives the resting
# ticket and crashes again -> proves restart persistence of the DERIVED counter.
new_env
export STUB_FAIL=1
STUB_RECORD_FILE="$TEST_DIR/rec_crash.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "S15 crasher" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker events >/dev/null 2>&1   # drain so each run relies on the startup sweep
out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out1" "INTENT SPAWN-CRASH ticket=$T" "crash run 1: SPAWN-CRASH marker"
assert_not_contains "$out1" "INTENT CRASH-LIMIT ticket=$T" "crash run 1: below limit, no escalation"
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out2" "INTENT SPAWN-CRASH ticket=$T" "crash run 2: SPAWN-CRASH marker (fresh process re-derives)"
assert_not_contains "$out2" "INTENT CRASH-LIMIT ticket=$T" "crash run 2: still below limit"
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out3" "INTENT CRASH-LIMIT ticket=$T" "crash run 3: 3rd consecutive marker -> CRASH-LIMIT"
dump=$(tracker get "$T")
assert_contains "$dump" "status: Needs PO Decision" "crash-limit escalates to Needs PO Decision"
markers=$(printf '%s\n' "$dump" | grep -c "SPAWN-CRASH status=Ready for Development " || true)
assert_eq "$markers" "3" "exactly 3 SPAWN-CRASH markers accumulated in the dump (be-developer at Ready for Development)"
# Each be-developer dispatch = attempt + retry = 2 stub invocations; 3 dispatches
# = 6. On run 3 the CRASH-LIMIT transition to Needs PO Decision fires a fresh
# po-agent dispatch in the SAME poll, which also crashes under STUB_FAIL=1
# (+2), so the stub is invoked 8 times total. The 3-marker invariant above is
# the meaningful assertion; this documents the escalation's own spawn.
attempts=$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')
assert_eq "$attempts" "8" "6 be-developer attempts + 2 for the escalation's po-agent spawn = 8"
cleanup_env

# --- (f) crash reset on success: an intervening handoff clears the counter -----
# One crashing dispatch, then a successful one (handoff lands, resets the run),
# then two more crashing dispatches -> still below the limit (2 < 3).
new_env
T=$(tracker create --type ticket --title "crash-reset story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker events >/dev/null 2>&1
STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1   # crash 1
outok=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)          # success -> handoff resets
assert_contains "$outok" "INTENT HANDOFF ticket=$T" "successful sweep lands a handoff (resets crash run)"
# The handoff advances the story? No — the stub posts a handoff but does not
# transition; the ticket rests in Ready for Development for the next sweep.
STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1   # crash 1 of the new run
outf=$(STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null) # crash 2 of the new run
assert_contains "$outf" "INTENT SPAWN-CRASH ticket=$T" "post-handoff crashes record markers again"
assert_not_contains "$outf" "INTENT CRASH-LIMIT ticket=$T" "handoff reset the run: 2<3, no CRASH-LIMIT"
dump=$(tracker get "$T")
assert_contains "$dump" "status: Ready for Development" "ticket still resting (crash-limit not reached)"
cleanup_env

# --- (g) per-day budget: dated ledger caps spawns ACROSS runs ------------------
new_env
export ORCH_MAX_SPAWNS_PER_DAY=1
export ORCH_BUDGET_PUSH=0   # ABS-455: --live budget test; suppress the operator dialog
E=$(tracker create --type epic --title "budget epic")
T1=$(tracker create --type ticket --title "budget story 1" --parent "$E" --role be-developer)
T2=$(tracker create --type ticket --title "budget story 2" --parent "$E" --role fe-developer)
baseline
# baseline is a dry-run poll and dry-run also writes the dated ledger (mirrors
# the per-run budget accounting); clear it so the scenario budget starts clean.
rm -f "$ORCH_STATE_DIR"/spawn-ledger-* 2>/dev/null || true
tracker transition "$T1" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker transition "$T2" "Ready for Development" --actor po-agent --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null) || true   # ABS-455: day-budget exhaustion now exits 75 (restart handshake); tolerate it under set -e
# First spawns (either ticket), the second is skipped by the day budget.
first_spawns=$(printf '%s\n' "$out" | grep -c "INTENT SPAWN ticket=" || true)
assert_eq "$first_spawns" "1" "day budget=1: exactly one SPAWN in the first poll"
assert_contains "$out" "INTENT SKIP-BUDGET-DAY" "second ticket in the same poll -> SKIP-BUDGET-DAY"
# A SECOND fresh invocation (same ORCH_STATE_DIR) halts on its first spawn: the
# ledger persisted across runs. Re-surface the still-resting T2 via the sweep.
tracker events >/dev/null 2>&1
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null) || true   # ABS-455: budget already exhausted -> exits 75; tolerate it under set -e
assert_contains "$out2" "INTENT SKIP-BUDGET-DAY" "fresh run halts immediately: ledger persisted across runs"
assert_not_contains "$out2" "INTENT HANDOFF ticket=" "no spawn seam invoked once the day budget is exhausted"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== v3 follow-up watcher + containment (ABS-75) ===${NC}\n"
# =============================================================================
# The watcher (reconcile()'s first pass, ahead of join_check_epic) scans for
# kind:follow-up comments with no kind:bsa-decision reply and spawns bsa once
# per unanswered follow-up (comment-keyed idempotency guard, the ABS-62
# stall-marker pattern). Per-epic budget: ORCH_FOLLOWUP_BUDGET (default 5);
# the (budget+1)th follow-up escalates to Needs PO Decision instead of
# spawning (spec §3.4, S7).

# --- (a) unanswered follow-up -> the watcher spawns bsa exactly once ----------
new_env
E=$(tracker create --type epic --title "watcher epic")
A=$(tracker create --type ticket --title "story w/ follow-up" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas \
    --body "Follow-up: found a gap; recommend a hardening story." >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$A role=bsa" "unanswered follow-up -> watcher spawns bsa"
assert_contains "$out" "INTENT HANDOFF ticket=$A role=bsa" "watcher spawn lands a handoff"
dump=$(tracker get "$A")
assert_contains "$dump" "FOLLOWUP-SPAWN n=1" "watcher marker recorded on the ticket (ABS-62-style guard)"
cleanup_env

# --- (b) second reconcile pass does NOT double-spawn the same follow-up ------
new_env
E=$(tracker create --type epic --title "watcher epic 2")
A=$(tracker create --type ticket --title "story w/ follow-up" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas \
    --body "Follow-up: found a gap." >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT SPAWN ticket=$A role=bsa" "second sweep does not re-spawn (marker guard holds)"
marker_count=$(tracker get "$A" | grep -c "FOLLOWUP-SPAWN n=1" || true)
assert_eq "$marker_count" "1" "exactly one FOLLOWUP-SPAWN marker for the one follow-up"
cleanup_env

# --- (c) a kind:bsa-decision reply disarms the watcher (no spawn at all) -----
new_env
E=$(tracker create --type epic --title "watcher epic 3")
A=$(tracker create --type ticket --title "story w/ answered follow-up" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas \
    --body "Follow-up: found a gap." >/dev/null
tracker comment "$A" --kind bsa-decision --actor bsa \
    --body "Decision: discard. Already covered by existing enabler." >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$A role=bsa" "answered follow-up (bsa-decision reply present) -> watcher never spawns"
cleanup_env

# --- (d) per-epic budget of 5: the 6th follow-up -> Needs PO Decision --------
# Raise ORCH_MAX_CONCURRENT so all 6 follow-ups clear the concurrency cap in
# one sweep (isolating the BUDGET behavior from the unrelated §5.1 defer path).
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "budget epic")
A=$(tracker create --type ticket --title "story w/ follow-up storm" --parent "$E")
baseline
for i in 1 2 3 4 5 6; do
    tracker comment "$A" --kind follow-up --actor qas --body "finding $i" >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
spawn_count=$(printf '%s\n' "$out" | grep -c "INTENT SPAWN ticket=$A role=bsa" || true)
assert_eq "$spawn_count" "5" "budget=5: exactly 5 of the 6 follow-ups spawn bsa"
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$E role=- to=Needs PO Decision" "6th follow-up -> FOLLOWUP-BUDGET intent instead of a spawn"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "epic escalated to Needs PO Decision on budget overflow"
assert_contains "$dump" "Follow-up budget reached" "budget-overflow reason recorded on the epic"
# Re-raise guard: a further sweep does not re-escalate (marker already posted).
tracker events >/dev/null 2>&1
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT FOLLOWUP-BUDGET ticket=$E" "budget overflow does not re-raise on the next sweep"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== v3 Blocked -> TDM triage, resume-to-origin (ABS-76) ===${NC}\n"
# =============================================================================
# Blocked (any stage) SPAWNs tdm exactly once per Blocked ENTRY (comment-keyed
# guard, the ABS-62/ABS-75 marker idiom). The runner records the pre-blocked
# status (BLOCKED-FROM=<status> marker) before the spawn; TDM (simulated here
# via a plain `tracker transition`, like a real TDM spawn would perform per
# docs/sop/ORCHESTRATOR_SOP.md) resumes the ticket to that recorded status.
# Re-entering Blocked later is a NEW entry and gets a fresh spawn.

# --- (a) Blocked entry -> SPAWN tdm + BLOCKED-FROM marker recorded -----------
new_env
T=$(tracker create --type ticket --title "Blocked from In Progress")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "Blocked" --actor be-developer --reason "credentials missing" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=tdm to=Blocked" "Blocked -> SPAWN tdm (not po-agent)"
assert_contains "$out" "INTENT HANDOFF ticket=$T role=tdm to=Blocked" "tdm spawn lands a handoff"
dump=$(tracker get "$T")
assert_contains "$dump" "BLOCKED-FROM=In Progress (orchestrator)" "pre-blocked status (In Progress) persisted in a BLOCKED-FROM marker"
cleanup_env

# --- (b) second reconcile pass does NOT double-spawn tdm for the same entry --
new_env
T=$(tracker create --type ticket --title "Blocked no double spawn")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "Blocked" --actor be-developer --reason "credentials missing" >/dev/null
# ADR-A-0019: model a well-behaved tdm that DECLARES it wants to keep the ticket
# parked (to: Blocked) so the ticket stays in Blocked and the once-per-entry marker
# guard — not the auto-resume — is what this block exercises.
STUB_HANDOFF_TO="Blocked" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
# Blocked rests (is_reconcilable_status excludes it) AND carries the marker
# guard now — assert both: a further sweep/poll must not re-spawn.
out2=$(STUB_HANDOFF_TO="Blocked" ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT SPAWN ticket=$T role=tdm" "second reconcile pass does not re-spawn tdm"
marker_count=$(tracker get "$T" | grep -c "BLOCKED-FROM=" || true)
assert_eq "$marker_count" "1" "exactly one BLOCKED-FROM marker after the second pass"
cleanup_env

# --- (c) resume-to-origin restores the recorded pre-blocked status (origin 1: In Progress) ---
new_env
T=$(tracker create --type ticket --title "Resume to In Progress")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "Blocked" --actor be-developer --reason "credentials missing" >/dev/null
# ADR-A-0019 (ABS-204): the tdm handoff declares no target, so the RUNNER drives
# the resume — deterministically back to the recorded BLOCKED-FROM origin.
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
dump=$(tracker get "$T")
assert_contains "$dump" "BLOCKED-FROM=In Progress (orchestrator)" "recorded pre-blocked status is In Progress"
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=tdm to=In Progress" "target-less tdm handoff resumes to the recorded origin (ADR-A-0019)"
assert_contains "$dump" "status: In Progress" "resume-to-origin restores the recorded pre-blocked status (In Progress)"
cleanup_env

# --- (d) resume-to-origin with a DIFFERENT origin (Grooming, epic pipeline) --
new_env
E=$(tracker create --type epic --title "Epic blocked during grooming")
baseline
tracker transition "$E" "PO Triage" --actor po-agent --reason triage >/dev/null
tracker transition "$E" "Grooming" --actor po-agent --reason groom >/dev/null
tracker transition "$E" "Blocked" --actor bsa --reason "missing domain input" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
dump=$(tracker get "$E")
assert_contains "$dump" "BLOCKED-FROM=Grooming (orchestrator)" "recorded pre-blocked status is Grooming (epic pipeline, spec §3.7/S14)"
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$E role=tdm to=Grooming" "target-less tdm handoff resumes to a DIFFERENT recorded origin (Grooming, ADR-A-0019)"
assert_contains "$dump" "status: Grooming" "resume-to-origin restores a DIFFERENT recorded status (Grooming)"
cleanup_env

# --- (e) re-entering Blocked later is a NEW entry -> a fresh tdm spawn -------
new_env
T=$(tracker create --type ticket --title "Re-entry gets a fresh spawn")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "Blocked" --actor be-developer --reason "first blocker" >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1   # tdm spawns; ADR-A-0019 auto-resumes to In Progress
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1   # drain the In Progress NOOP event
tracker transition "$T" "Blocked" --actor be-developer --reason "second blocker" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=tdm to=Blocked" "re-entering Blocked spawns tdm again (new entry)"
marker_count=$(tracker get "$T" | grep -c "BLOCKED-FROM=In Progress (orchestrator)" || true)
assert_eq "$marker_count" "2" "a second BLOCKED-FROM marker is recorded for the new entry"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== ADR-A-0019 escalation resume — legit PO-deprioritize vs. mis-dump (ABS-204) ===${NC}\n"
# =============================================================================
# ADR-A-0019 (ABS-204, split from ABS-198 M2): an ESCALATION seat (tdm at Blocked,
# po-agent at Needs PO Decision) that hands off with NO declared target must route
# DETERMINISTICALLY — resume-to-origin via the recorded BLOCKED-FROM marker, or
# halt in the single canonical park (Blocked) — and NEVER land in Backlog by
# discretion, which last_po_park_epoch would misread as a legit PO deprioritise.
# A seat that DECLARES `target: Backlog` still parks legitimately (the shipped,
# guarded PO-park path stays functional — AC#3).

# --- AC#2 (a) tdm at Blocked, no declared target, real recorded origin -> resume-to-origin
new_env
T=$(tracker create --type ticket --title "Escalation no-target resumes to origin")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker events >/dev/null 2>&1   # drain the walk so only the Blocked entry is fresh
tracker transition "$T" "Blocked" --actor be-developer --reason "blocker" >/dev/null
# tdm spawns at Blocked and hands off with NO declared target (no STUB_HANDOFF_TO).
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=tdm to=Blocked" "escalation seat (tdm) spawns at Blocked"
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=tdm to=In Progress" "no-target escalation handoff resumes to the recorded BLOCKED-FROM origin"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "resume-to-origin restores the pre-blocked origin (In Progress)"
assert_eq "$(tracker get "$T" | grep -c 'Transition: Blocked -> Backlog' || true)" "0" "never routed Blocked -> Backlog by discretion"
cleanup_env

# --- AC#2 (b) tdm at Blocked, no declared target, only an escalation-status origin -> halt in Blocked
new_env
T=$(tracker create --type ticket --title "Escalation no-target halts in Blocked")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "Needs PO Decision" --actor be-developer --reason "product question" >/dev/null
tracker events >/dev/null 2>&1   # drain so only the Blocked entry is fresh
# The only recorded pre-blocked origin is an escalation status (Needs PO Decision),
# which is never a resume origin -> halt in the single canonical park (Blocked).
tracker transition "$T" "Blocked" --actor po-agent --reason "cannot decide yet" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=tdm to=Blocked" "escalation seat (tdm) spawns at Blocked"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Blocked" "no usable origin -> halt in the single canonical park (Blocked)"
assert_not_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=tdm to=Needs PO Decision" "an escalation status is never a resume origin (no ping-pong)"
assert_not_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=tdm to=Backlog" "never routed to Backlog by discretion"
cleanup_env

# --- AC#3 legit PO-deprioritize: a DECLARED target: Backlog still parks ---------
# Regression: the runner-applied `Needs PO Decision -> Backlog` that
# last_po_park_epoch / stall_raise_suppressed key off must still fire when the
# seat declares the deprioritise target — ADR-A-0019 is additive, it only sets
# the missing-declaration default and NEVER diverts a declared target.
new_env
T=$(tracker create --type ticket --title "Legit PO deprioritize stays functional" --role be-developer)
baseline
tracker transition "$T" "Needs PO Decision" --actor be-developer --reason "product question" >/dev/null
export STUB_HANDOFF_TO="Backlog"   # po-agent declares an explicit deprioritise target
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
unset STUB_HANDOFF_TO
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$T role=po-agent to=Backlog" "a declared deprioritise target is honoured (not diverted to Blocked/origin)"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Backlog" "legit PO-deprioritize lands in Backlog"
assert_eq "$(tracker get "$T" | grep -c 'Transition: Needs PO Decision -> Backlog' || true)" "1" "the Needs PO Decision -> Backlog transition last_po_park_epoch keys off is intact"
cleanup_env

# =============================================================================
# =============================================================================
echo -e "\n${CYAN}ABS-111 — async spawns, session resume, handoff repair, depends_on, worktrees${NC}"
# =============================================================================

# --- A1 (a): two live spawns actually OVERLAP under async ---------------------
new_env
export ORCH_ASYNC_SPAWNS=1
A=$(tracker create --type ticket --title "async one" --role be-developer)
B=$(tracker create --type ticket --title "async two" --role be-developer)
baseline
tracker transition "$A" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$B" "Ready for Development" --actor po --reason go >/dev/null
export STUB_TIMING_FILE="$TEST_DIR/timing" STUB_SLEEP=2
ORCH_MAX_CONCURRENT=2 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_eq "$(wc -l < "$STUB_TIMING_FILE" | tr -d ' ')" "2" "A1a: both tickets spawned within one cycle"
max_start=$(cut -f2 "$STUB_TIMING_FILE" | sort -n | tail -1)
min_end=$(cut -f3 "$STUB_TIMING_FILE" | sort -n | head -1)
TOTAL=$((TOTAL + 1))
if [ "$max_start" -lt "$min_end" ]; then
    echo -e "  ${GREEN}PASS${NC} A1a: the two spawns overlap in time (async, not serial)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} A1a: spawns did not overlap (max_start=$max_start min_end=$min_end)"; FAIL=$((FAIL + 1))
fi
unset STUB_TIMING_FILE STUB_SLEEP
export ORCH_ASYNC_SPAWNS=0
cleanup_env

# --- A1 (b): ORCH_MAX_CONCURRENT is enforced (the 3rd is deferred, not spawned)
new_env
export ORCH_ASYNC_SPAWNS=1
A=$(tracker create --type ticket --title "cap one" --role be-developer)
B=$(tracker create --type ticket --title "cap two" --role be-developer)
C=$(tracker create --type ticket --title "cap three" --role be-developer)
baseline
for t in "$A" "$B" "$C"; do tracker transition "$t" "Ready for Development" --actor po --reason go >/dev/null; done
export STUB_RECORD_FILE="$TEST_DIR/records" STUB_SLEEP=2
out=$(ORCH_MAX_CONCURRENT=2 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT DEFER-CAP" "A1b: the over-cap spawn is deferred"
assert_eq "$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')" "2" "A1b: exactly cap-many (2) spawns ran this cycle"
unset STUB_RECORD_FILE STUB_SLEEP
export ORCH_ASYNC_SPAWNS=0
cleanup_env

# --- A2 (a): session stored on spawn, RESUMED on the rework bounce ------------
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="12345678-abcd-4ea1-9c0e-abcdef123456"
export STUB_RECORD_FILE="$TEST_DIR/records"
T=$(tracker create --type ticket --title "resume story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
# Drain the intermediate events (the mock's `events` is a snapshot diff — a
# poll between transitions keeps the rework bounce visible as its own event).
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason "rework: defects" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T role=be-developer to=Ready for Development note=session=$STUB_SESSION_ID" \
    "A2a: rework bounce resumes the stored dev session"
assert_contains "$(cat "$STUB_RECORD_FILE")" "resume=$STUB_SESSION_ID" "A2a: the seam received ORCH_RESUME_SESSION_ID"
# --- A2 (b): acceptance ends the resume scope (sessions cleared on Done) ------
# Count the DEV session specifically: the Done event itself spawns tech-writer,
# which legitimately stores its own (post-acceptance seats are out of scope).
dev_sessions() { ls "$ORCH_STATE_DIR/sessions" 2>/dev/null | grep -c "^$T.be-developer" || true; }
sessions_before=$(dev_sessions)
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
tracker transition "$T" "In Test" --actor system-architect --reason approved >/dev/null
tracker transition "$T" "Ready for Human Acceptance" --actor qas --reason tested >/dev/null
tracker transition "$T" "Ready for Merge" --actor po-agent --reason accepted >/dev/null
tracker transition "$T" "Done" --actor human --reason merged >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
sessions_after=$(dev_sessions)
assert_eq "$sessions_before" "1" "A2b: a dev session was stored before acceptance"
assert_eq "$sessions_after" "0" "A2b: entering Done drops the ticket's stored sessions"
unset STUB_SESSION_ID STUB_RECORD_FILE
export ORCH_SESSION_RESUME=0
cleanup_env

# --- A2 (c): handoff REPAIR — missing handoff is fetched by resuming the same
# session with a tiny budget, instead of a full duplicate re-spawn -------------
new_env
export ORCH_SESSION_RESUME=1
export STUB_NO_HANDOFF=1
export STUB_SESSION_ID="deadbeef-1111-4222-8333-444455556666"
export STUB_RECORD_FILE="$TEST_DIR/records"
T=$(tracker create --type ticket --title "repair story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REPAIR-HANDOFF ticket=$T" "A2c: missing handoff triggers the repair resume"
assert_contains "$out" "INTENT HANDOFF ticket=$T" "A2c: the repaired handoff counts as success"
assert_not_contains "$out" "INTENT RETRY ticket=$T" "A2c: no duplicate re-spawn was needed"
assert_contains "$(cat "$STUB_RECORD_FILE")" "resume=$STUB_SESSION_ID" "A2c: repair reused the SAME session"
unset STUB_NO_HANDOFF STUB_SESSION_ID STUB_RECORD_FILE
export ORCH_SESSION_RESUME=0
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-175 turn-cap salvage — a cap exit is resumed once, not discarded${NC}"
# =============================================================================
# --- salvage SUCCESS: a max-turns exit resumes the SAME session with a small
# cap, the salvage produces the handoff, and NO fresh respawn happens ----------
new_env
export ORCH_SESSION_RESUME=1
export STUB_MAX_TURNS=1
export STUB_SESSION_ID="cafe0001-1111-4222-8333-444455556666"
export STUB_RECORD_FILE="$TEST_DIR/records"
export STUB_TURNS_FILE="$TEST_DIR/turns"
export ORCH_SALVAGE_MAX_TURNS=3   # prove the small cap wires through to the resume
T=$(tracker create --type ticket --title "salvage story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SALVAGE-RESUME ticket=$T" "turn-cap exit triggers a salvage resume"
assert_contains "$out" "cap=3" "salvage resume uses the small ORCH_SALVAGE_MAX_TURNS cap"
assert_contains "$out" "INTENT HANDOFF ticket=$T" "salvage produced the handoff -> spawn succeeds"
assert_not_contains "$out" "INTENT RETRY ticket=$T" "no full fresh respawn after the cap event"
assert_not_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "successful salvage is not a crash"
salvages=$(printf '%s\n' "$out" | grep -c "INTENT SALVAGE-RESUME ticket=$T" || true)
assert_eq "$salvages" "1" "exactly ONE salvage per spawn (no endless salvage)"
assert_contains "$(cat "$STUB_RECORD_FILE")" "resume=$STUB_SESSION_ID" "salvage reused the SAME session (not a cold respawn)"
assert_contains "$(cat "$STUB_TURNS_FILE")" "	3" "the salvage resume ran under the small turn cap"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "INTENT-SALVAGE-RESUME" "run.log records the salvage event"
unset STUB_MAX_TURNS STUB_SESSION_ID STUB_RECORD_FILE STUB_TURNS_FILE ORCH_SALVAGE_MAX_TURNS
export ORCH_SESSION_RESUME=0
cleanup_env

# --- salvage FAILURE: the salvage itself crashes -> the existing crash path
# takes over (retry once, then SPAWN-CRASH marker); no endless salvage ----------
new_env
export ORCH_SESSION_RESUME=1
export STUB_MAX_TURNS=1
export STUB_SALVAGE_FAIL=1
export STUB_SESSION_ID="cafe0002-1111-4222-8333-444455556666"
T=$(tracker create --type ticket --title "salvage crash story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SALVAGE-RESUME ticket=$T" "cap exit still attempts a salvage"
assert_contains "$out" "INTENT RETRY ticket=$T" "a failed salvage falls into the existing retry path"
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "a salvage that also fails ends in the crash marker"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" "salvage-crash leaves the ticket RESTING in its status"
assert_contains "$(tracker get "$T")" "SPAWN-CRASH status=Ready for Development " "salvage-crash marker landed on the ticket"
unset STUB_MAX_TURNS STUB_SALVAGE_FAIL STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- dry-run never salvages (no live resume in a dry-run cycle) ----------------
new_env
export ORCH_SESSION_RESUME=1
export STUB_MAX_TURNS=1
export STUB_SESSION_ID="cafe0003-1111-4222-8333-444455556666"
T=$(tracker create --type ticket --title "salvage dryrun story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT SALVAGE-RESUME ticket=$T" "dry-run does not salvage (no spawn, no resume)"
unset STUB_MAX_TURNS STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-117: config-generation stamp — stale sessions are invalidated --------
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="11111111-2222-4333-8444-555566667777"
export STUB_RECORD_FILE="$TEST_DIR/records"
T=$(tracker create --type ticket --title "gen story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_CONFIG_GENERATION=genA ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
# Stamp is written: line 2 of the session file carries the active generation.
sf=$(ls "$ORCH_STATE_DIR/sessions/$T".* 2>/dev/null | head -1)
assert_eq "$(sed -n '2p' "$sf" 2>/dev/null)" "genA" "ABS-117: stored session carries the generation stamp"
# Same generation -> resume works (regression).
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_CONFIG_GENERATION=genA ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
out=$(ORCH_CONFIG_GENERATION=genA ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T" "ABS-117: matching generation -> resume unchanged"
# Changed generation -> the stored session is invalidated, spawn goes fresh.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_CONFIG_GENERATION=genB ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework2 >/dev/null
out=$(ORCH_CONFIG_GENERATION=genB ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-117: generation mismatch -> no resume"
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer" "ABS-117: invalidated session -> fresh spawn still happens"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-INVALIDATED" "ABS-117: invalidation is a run.log event"
sf=$(ls "$ORCH_STATE_DIR/sessions/$T".be-developer* 2>/dev/null | head -1)
assert_eq "$(sed -n '2p' "$sf" 2>/dev/null)" "genB" "ABS-117: fresh spawn re-stamps with the new generation"
# Legacy single-line session file (pre-ABS-117) -> unknown context -> invalidate.
L=$(tracker create --type ticket --title "legacy story" --role be-developer)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1   # consume creation event
mkdir -p "$ORCH_STATE_DIR/sessions"
printf '%s' "99999999-8888-4777-8666-555544443333" > "$ORCH_STATE_DIR/sessions/$L.be-developer.Ready_for_Development"
tracker transition "$L" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_CONFIG_GENERATION=genB ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT RESUME ticket=$L" "ABS-117: legacy unstamped session -> no resume"
assert_contains "$out" "INTENT SPAWN ticket=$L role=be-developer" "ABS-117: legacy session invalidated -> fresh spawn"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "stored=genA current=genB" "ABS-117: invalidation payload names stored+current generation"
unset STUB_SESSION_ID STUB_RECORD_FILE
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-117: the REAL hash path (no ORCH_CONFIG_GENERATION override) ---------
# A controlled, mutable agent-defs dir isolates the hash surface under test.
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="aaaaaaaa-bbbb-4ccc-8ddd-eeeeffff0000"
export ORCH_AGENTS_DIR="$TEST_DIR/agents"
mkdir -p "$ORCH_AGENTS_DIR"
printf -- '---\nname: be-developer\ndescription: t\n---\nprompt\n' > "$ORCH_AGENTS_DIR/be-developer.md"
T=$(tracker create --type ticket --title "real hash story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
sf=$(ls "$ORCH_STATE_DIR/sessions/$T".* 2>/dev/null | head -1)
gen1="$(sed -n '2p' "$sf" 2>/dev/null)"
TOTAL=$((TOTAL + 1))
if [ -n "$gen1" ] && [ "$gen1" -eq "$gen1" ] 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} ABS-117: real hash path produces a numeric generation stamp"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-117: real hash stamp missing/non-numeric (got '$gen1')"; FAIL=$((FAIL + 1))
fi
# Determinism: unchanged inputs -> the rework bounce still resumes.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T" "ABS-117: unchanged real inputs -> same generation -> resume"
# Editing an agent def changes the generation -> the next resume is refused.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework2 >/dev/null
printf 'changed\n' >> "$ORCH_AGENTS_DIR/be-developer.md"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-117: agent-def edit changes the generation -> no resume"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-INVALIDATED" "ABS-117: real-hash invalidation logged"
unset STUB_SESSION_ID ORCH_AGENTS_DIR
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-254 / ADR-A-0023: a denial-poisoned session is never resumed ----------
# A resume re-reads the live permission surface but NOT its own transcript: a
# session whose spawn hit permission denials carries the `denied` history and
# keeps re-reporting the phantom blocker after the settings were fixed underneath
# it (consumer: 6+ spawns). So the runner must not store such a session.
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="dddddddd-eeee-4fff-8000-111122223333"
T=$(tracker create --type ticket --title "poison story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
sf="$ORCH_STATE_DIR/sessions/$T.be-developer.Ready_for_Development"
# Control: a CLEAN spawn ("permission_denials": []) stores its session as before.
STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_eq "$(sed -n '1p' "$sf" 2>/dev/null)" "$STUB_SESSION_ID" "ABS-254: a clean spawn still stores its session (guard inert on the healthy path)"
# The seat bounces back and THIS spawn hits a denial. It resumed the healthy
# session, so the guard must also drop the file it inherited — skipping the write
# alone would leave the now-poisoned session behind for the next spawn.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
out=$(STUB_PERMISSION_DENIALS=1 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-254: the stored clean session was resumed (pre-condition for the drop)"
assert_eq "$(cat "$sf" 2>/dev/null)" "" "ABS-254: a denial-hit spawn stores no session — and drops the one it resumed"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-POISONED" "ABS-254: the drop is a run.log event"
# The next bounce therefore starts FRESH — no denial history to inherit.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework2 >/dev/null
out=$(STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-254: a denial-hit session is never resumed"
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer" "ABS-254: the next spawn starts fresh against the fixed permission surface"
unset STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-254: kill-switch restores the legacy store-anyway behaviour -----------
new_env
export ORCH_SESSION_RESUME=1
export ORCH_SESSION_POISON_GUARD=0
export STUB_SESSION_ID="dddddddd-eeee-4fff-8000-999988887777"
T=$(tracker create --type ticket --title "poison killswitch story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
STUB_PERMISSION_DENIALS=1 ORCH_CONFIG_GENERATION=genP ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_eq "$(sed -n '1p' "$ORCH_STATE_DIR/sessions/$T.be-developer.Ready_for_Development" 2>/dev/null)" "$STUB_SESSION_ID" "ABS-254: ORCH_SESSION_POISON_GUARD=0 stores the denial-hit session anyway"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-POISONED" "ABS-254: kill-switch off -> no drop event"
unset STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-254 salvage co-occurrence: a birth spawn that hit BOTH the turn cap AND
# permission denials must NOT be re-stored via the ABS-175 salvage path ---------
# The salvage resumes the SAME session id, so it inherits the birth spawn's
# poisoned transcript even though the salvage's OWN output is clean. The birth
# store drops the result; the salvage store must ALSO drop it, or the poisoned
# session is silently re-admitted (system-architect In Review iteration 1). This
# is the ticket's own denial-loop-burns-turns scenario.
new_env
export ORCH_SESSION_RESUME=1
export STUB_MAX_TURNS=1
export STUB_MAX_TURNS_DENIALS=1
export STUB_SESSION_ID="beef0001-2222-4333-8444-555566667777"
T=$(tracker create --type ticket --title "salvage poison story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
sf="$ORCH_STATE_DIR/sessions/$T.be-developer.Ready_for_Development"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SALVAGE-RESUME ticket=$T" "ABS-254: a denial+cap birth spawn still salvage-resumes (work is not discarded)"
assert_contains "$out" "INTENT HANDOFF ticket=$T" "ABS-254: the salvage produced a clean handoff"
assert_eq "$(cat "$sf" 2>/dev/null)" "" "ABS-254: the salvaged session is NOT stored — birth-spawn denials poison the resumed transcript"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-POISONED" "ABS-254: the salvage-store drop is a run.log event"
unset STUB_MAX_TURNS STUB_MAX_TURNS_DENIALS STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-254 salvage co-occurrence control: WITHOUT birth denials a salvaged
# session stores normally — proves the drop is driven by the birth-denial capture,
# not by the salvage path itself -------------------------------------------------
new_env
export ORCH_SESSION_RESUME=1
export STUB_MAX_TURNS=1
export STUB_SESSION_ID="beef0002-2222-4333-8444-555566667777"
T=$(tracker create --type ticket --title "salvage clean story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
sf="$ORCH_STATE_DIR/sessions/$T.be-developer.Ready_for_Development"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SALVAGE-RESUME ticket=$T" "ABS-254 control: a clean cap birth spawn salvage-resumes"
assert_eq "$(sed -n '1p' "$sf" 2>/dev/null)" "$STUB_SESSION_ID" "ABS-254 control: a clean salvage DOES store its session (the drop is birth-denial-driven)"
unset STUB_MAX_TURNS STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-598: a denied READ-only tool must NOT poison the session --------------
# The poison verdict is classified by the tool's MUTATION property, not by "a
# denial occurred". A refused Read/Grep/Glob leaves nothing inconsistent (the model
# just did not see a file), so its session is fully usable and must be stored; only
# a refused Write/Edit/Bash can leave the tree/process state inconsistent.
echo -e "\n${CYAN}=== ABS-598 read-only denials do not poison the session ===${NC}"

# AC1/AC2 at the predicate level, in a child bash that sources orchestrator.sh.
_598_pred() {   # <spawn-out>  -> prints "mut" if it poisons, else "clean"
    bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo SOURCE-FAIL; exit 0; }
        if result_has_mutating_denial "$1"; then echo mut; else echo clean; fi
    ' _ "$1"
}
_598_read='{"permission_denials":[{"tool_name":"Read","tool_input":{"file_path":"/Users/sahan/boilerplate-stable/tests/staged-suite.sh","limit":80}}]}'
_598_grep='{"permission_denials":[{"tool_name":"Grep","tool_input":{"pattern":"x"}}]}'
_598_write='{"permission_denials":[{"tool_name":"Write","tool_input":{"file_path":"/etc/hosts"}}]}'
_598_bash='{"permission_denials":[{"tool_name":"Bash","tool_input":{"command":"rm -rf x"}}]}'
_598_mixed='{"permission_denials":[{"tool_name":"Read","tool_input":{"file_path":"/a"}},{"tool_name":"Edit","tool_input":{"file_path":"/b"}}]}'
_598_empty='{"permission_denials":[]}'
assert_eq "$(_598_pred "$_598_read")"  "clean" "ABS-598 AC1: a denied Read does NOT poison"
assert_eq "$(_598_pred "$_598_grep")"  "clean" "ABS-598 AC1: a denied Grep does NOT poison"
assert_eq "$(_598_pred "$_598_empty")" "clean" "ABS-598: an empty permission_denials array does NOT poison"
assert_eq "$(_598_pred "$_598_write")" "mut"   "ABS-598 AC2: a denied Write poisons"
assert_eq "$(_598_pred "$_598_bash")"  "mut"   "ABS-598 AC2: a denied Bash poisons"
assert_eq "$(_598_pred "$_598_mixed")" "mut"   "ABS-598 AC2: a mixed Read+Edit denial poisons (the mutating one triggers)"

# AC3: the SESSION-POISONED log summary names the triggering tool AND its target.
_598_sum() {
    bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo SOURCE-FAIL; exit 0; }
        result_denial_summary "$1"
    ' _ "$1"
}
assert_eq "$(_598_sum "$_598_write")" "tool=Write target=/etc/hosts" "ABS-598 AC3: the log summary names the mutating tool + file target"
assert_contains "$(_598_sum "$_598_bash")" "tool=Bash target=rm -rf x" "ABS-598 AC3: the log summary names a denied Bash command target"
assert_eq "$(_598_sum "$_598_read")" "" "ABS-598 AC3: a read-only denial yields no mutating summary"

# AC4 end-to-end: a denied Read stores the session (and resumes it); a denied Write
# drops it and logs SESSION-POISONED naming the tool.
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="a5980000-1111-4222-8333-444455556666"
T=$(tracker create --type ticket --title "readonly denial story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
sf="$ORCH_STATE_DIR/sessions/$T.be-developer.Ready_for_Development"
# A denied READ-only tool: the session is STILL stored (ABS-598 AC1/AC4).
out=$(STUB_PERMISSION_DENIALS=readonly ORCH_CONFIG_GENERATION=gen598 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(sed -n '1p' "$sf" 2>/dev/null)" "$STUB_SESSION_ID" "ABS-598 AC4: a denied Read stores the session (full cap, no poison)"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-POISONED" "ABS-598 AC4: a denied Read logs no SESSION-POISONED"
# The stored read-denial session is resumed on the next spawn — proves full-cap reuse.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=gen598 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
out=$(STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=gen598 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-598 AC4: the read-denial session was stored and later resumed"
# Now a denied MUTATING tool on the same key: dropped + logged with the tool named.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
STUB_PERMISSION_DENIALS=0 ORCH_CONFIG_GENERATION=gen598 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework2 >/dev/null
out=$(STUB_PERMISSION_DENIALS=1 ORCH_CONFIG_GENERATION=gen598 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(cat "$sf" 2>/dev/null)" "" "ABS-598 AC4: a denied Write drops the session"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "tool=Write" "ABS-598 AC3/AC4: the SESSION-POISONED log names the triggering mutating tool"
unset STUB_SESSION_ID
export ORCH_SESSION_RESUME=0
cleanup_env

# --- ABS-254 AC3: an ALLOWLIST edit must NOT invalidate stored sessions --------
# Retro 2026-07-10, upheld + proven by ADR-A-0023: the permission surface is
# spawn-fresh (re-read on every resume), so it stays OUT of the config generation.
# This guards the exact regression the ADR exists to prevent — someone re-adds
# settings.local.json to the hash and one operator allowlist fix cold-starts the
# entire session store. Runs the REAL hash path (no ORCH_CONFIG_GENERATION).
new_env
export ORCH_SESSION_RESUME=1
export STUB_SESSION_ID="cccccccc-dddd-4eee-8fff-000011112222"
export ORCH_AGENTS_DIR="$TEST_DIR/agents"
export ORCH_HARNESS_HOME="$TEST_DIR/harness"
mkdir -p "$ORCH_AGENTS_DIR" "$ORCH_HARNESS_HOME/.claude"
printf -- '---\nname: be-developer\ndescription: t\n---\nprompt\n' > "$ORCH_AGENTS_DIR/be-developer.md"
printf '{"permissions": {"deny": ["Bash(echo:*)"]}}\n' > "$ORCH_HARNESS_HOME/.claude/settings.local.json"
T=$(tracker create --type ticket --title "allowlist story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
# The operator fixes the permission surface mid-run — the consumer's scenario.
printf '{"permissions": {"allow": ["Bash(echo:*)", "Read(//tmp/**)"]}}\n' > "$ORCH_HARNESS_HOME/.claude/settings.local.json"
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT RESUME ticket=$T role=be-developer" "ABS-254 AC3: an allowlist edit does NOT invalidate stored sessions (retro upheld)"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "SESSION-INVALIDATED" "ABS-254 AC3: a permission-surface edit causes no generation churn"
unset STUB_SESSION_ID ORCH_AGENTS_DIR ORCH_HARNESS_HOME
export ORCH_SESSION_RESUME=0
cleanup_env

# --- C7: status evidence — work that advanced the ticket is success, not crash
new_env
T=$(tracker create --type ticket --title "synth story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
export STUB_NO_HANDOFF=1 STUB_TRANSITION_TO="In Progress"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SYNTH-HANDOFF ticket=$T" "C7: advanced ticket without handoff -> synthesized success"
assert_not_contains "$out" "INTENT RETRY ticket=$T" "C7: no phantom-crash retry for completed work"
unset STUB_NO_HANDOFF STUB_TRANSITION_TO
cleanup_env

# --- C8: depends_on gate — unmet dependency rests, cleared dependency spawns --
new_env
export ORCH_DEPENDS_GATING=1
# PILOT-19: depends_unmet probes the blocker's merge state; point it at a bogus
# remote so the forge-less probe fails offline-fast (NONE = not merged = waits)
# instead of reaching for the real origin over the network.
export ORCH_MAIN_REMOTE=none
D=$(tracker create --type ticket --title "the dependency" --role be-developer)
T=$(tracker create --type ticket --title "the dependent" --role be-developer)
tracker update "$T" depends_on "[$D]" >/dev/null
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "C8: unmet depends_on rests the ticket (no spawn)"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "C8: no spawn while the dependency is open"
tracker update "$T" depends_on "[]" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 ORCH_RECONCILE_EVERY_N_CYCLES=1 ORCH_MAX_CYCLES=1 orch --dry-run 2>/dev/null || true)
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=Ready for Development" \
    "C8: cleared dependency -> the reconcile sweep spawns it"
export ORCH_DEPENDS_GATING=0
cleanup_env

# --- C9: runner-provisioned worktree for the implementer spawn ----------------
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-wt-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "worktree story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
TOTAL=$((TOTAL + 1))
if [ -e "$TARGET/tmp/$T-work/.git" ] && git -C "$TARGET" show-ref --verify --quiet "refs/heads/$T-auto"; then
    echo -e "  ${GREEN}PASS${NC} C9: worktree tmp/$T-work on branch $T-auto was runner-provisioned"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} C9: worktree/branch missing under $TARGET"; FAIL=$((FAIL + 1))
fi
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- C9b: worktree provisioning FAILURE fails closed (no spawn in main checkout)
# If the runner cannot provision the isolated worktree it must NOT fall back to
# the main checkout — it rests the ticket (INTENT SKIP-NOWORKTREE) so the reconcile
# sweep retries. Force a representative failure on an otherwise-healthy repo: occupy
# the <ticket>-auto branch in the MAIN working tree, so `git worktree add` for the
# same branch fails ("already checked out elsewhere").
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-wtfail-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "worktree fail story" --role be-developer)
git -C "$TARGET" checkout -q -b "$T-auto"   # occupy the branch -> `worktree add` must fail
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null || true)
assert_contains "$out" "INTENT SKIP-NOWORKTREE ticket=$T" "C9b: provisioning failure rests the ticket (fail-closed)"
assert_not_contains "$out" "INTENT HANDOFF ticket=$T" "C9b: no spawn completed in the main checkout on provisioning failure"
assert_eq "$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')" "0" "C9b: the spawn seam was never invoked"
unset ORCH_TARGET_REPO STUB_RECORD_FILE
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-131 — settings.local.json + local allows travel into the worktree${NC}"
# =============================================================================
# Befund 1 (run ABS-126): a fresh implementer worktree carried only tracked files,
# so the gitignored settings.local.json (the operator's local Write/Edit grants)
# never rode along and the seat failed closed on its first edit. Provisioning must
# copy the file in and merge a worktree-only safe allow extension.

# --- copy present source + default extra-allow merge --------------------------
new_env
export ORCH_WORKTREE_SPAWNS=1
unset ORCH_WORKTREE_EXTRA_ALLOW   # exercise the built-in default
TARGET="$(mktemp -d /tmp/orchestrator-wtset-XXXXXX)"
warm_git_repo "$TARGET"
mkdir -p "$TARGET/.claude"
printf '%s\n' '{"permissions":{"allow":["Bash(ls:*)"]}}' > "$TARGET/.claude/settings.local.json"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "wt settings story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
DST="$TARGET/tmp/$T-work/.claude/settings.local.json"
TOTAL=$((TOTAL + 1))
if [ -f "$DST" ]; then
    echo -e "  ${GREEN}PASS${NC} ABS-131: settings.local.json provisioned into the worktree .claude/"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-131: settings.local.json missing from $DST"; FAIL=$((FAIL + 1))
fi
assert_contains "$(cat "$DST" 2>/dev/null)" "Bash(ls:*)" "ABS-131: operator's own grants are preserved in the copy"
if command -v jq >/dev/null 2>&1; then
    # ABS-154: the default extra-allow now grants bare Bash/Write/Edit so an
    # implementer seat can read/write/commit/push reliably in the isolated tree
    # instead of depending on the (possibly restrictive) copied target allowlist.
    # Bare Bash covers compound commands, heredocs and `git push`.
    assert_eq "$(jq -r '.permissions.allow | index("Bash") != null' "$DST" 2>/dev/null)" "true" "ABS-154: default extra-allow grants bare Bash (compound cmds + git push)"
    assert_eq "$(jq -r '.permissions.allow | index("Write") != null' "$DST" 2>/dev/null)" "true" "ABS-154: default extra-allow grants bare Write"
    assert_eq "$(jq -r '.permissions.allow | index("Edit") != null' "$DST" 2>/dev/null)" "true" "ABS-154: default extra-allow grants bare Edit"
fi
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- missing source = graceful no-op with a log event, no crash ---------------
new_env
export ORCH_WORKTREE_SPAWNS=1
unset ORCH_WORKTREE_EXTRA_ALLOW
TARGET="$(mktemp -d /tmp/orchestrator-wtnosrc-XXXXXX)"
warm_git_repo "$TARGET"
# deliberately NO $TARGET/.claude/settings.local.json
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "wt nosrc story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# retro 2026-07-10: target-checkout provisioning would create the file at startup;
# disable it here — this scenario asserts the worktree no-op path specifically.
out=$(ORCH_RECONCILE_ON_STARTUP=0 ORCH_SYNC_TARGET_ALLOWLIST=0 orch --live --once 2>&1)
assert_contains "$out" "no settings.local.json in main checkout" "ABS-131: absent source logs a no-op event"
TOTAL=$((TOTAL + 1))
if [ -e "$TARGET/tmp/$T-work/.git" ]; then
    echo -e "  ${GREEN}PASS${NC} ABS-131: worktree still provisioned when source is absent (no crash)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-131: worktree missing after absent-source provisioning"; FAIL=$((FAIL + 1))
fi
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-272 — no seat may git stash (refs/stash is SHARED across all worktrees)${NC}"
# =============================================================================
# `git stash` writes to ONE refs/stash that ALL worktrees of a repo share (only
# HEAD, refs/bisect, refs/worktree, refs/rewritten are per-worktree). The runner
# operates seats CONCURRENTLY in their own worktrees, so a seat that stashes for a
# baseline comparison and pops afterwards can pop a SIBLING seat's stash and eat
# its uncommitted work (3 incidents 2026-07-13: ABS-251←ABS-255, ABS-254←ABS-265).
# Two mechanical layers, both asserted here, plus the stash-free recipe itself.

STASH_HOOK="$REPO_ROOT/harness/claude/hooks/pre-bash-stash-guard.sh"

# --- AC2a: the GENERATED seat-worktree config carries the deny rule -----------
new_env
export ORCH_WORKTREE_SPAWNS=1
unset ORCH_WORKTREE_EXTRA_ALLOW
TARGET="$(mktemp -d /tmp/orchestrator-stashdeny-XXXXXX)"
git -C "$TARGET" init -q
git -C "$TARGET" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
mkdir -p "$TARGET/.claude"
printf '%s\n' '{"permissions":{"allow":["Bash(ls:*)"]}}' > "$TARGET/.claude/settings.local.json"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "stash deny story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
DST="$TARGET/tmp/$T-work/.claude/settings.local.json"
assert_contains "$(cat "$DST" 2>/dev/null)" "Bash(git stash:*)" "ABS-272: generated seat-worktree config carries the git-stash deny rule"
if command -v jq >/dev/null 2>&1; then
    assert_eq "$(jq -r '.permissions.deny | index("Bash(git stash:*)") != null' "$DST" 2>/dev/null)" "true" \
        "ABS-272: the rule sits in permissions.deny (not merely in the file text)"
    assert_eq "$(jq -r '.permissions.allow | index("Bash(ls:*)") != null' "$DST" 2>/dev/null)" "true" \
        "ABS-272: the operator's own allow grants survive the deny injection"
fi
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- AC2b: kill switch — ORCH_STASH_GUARD=0 injects no deny rule (ABS-111) ----
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-stashoff-XXXXXX)"
git -C "$TARGET" init -q
git -C "$TARGET" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
mkdir -p "$TARGET/.claude"
printf '%s\n' '{"permissions":{"allow":["Bash(ls:*)"]}}' > "$TARGET/.claude/settings.local.json"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "stash switch story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 ORCH_STASH_GUARD=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$TARGET/tmp/$T-work/.claude/settings.local.json" 2>/dev/null)" "Bash(git stash:*)" \
    "ABS-272: ORCH_STASH_GUARD=0 restores legacy behavior (no deny rule injected)"
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- AC2c: the guard hook REFUSES a mutating stash and names the recipe -------
# Second layer: the deny rule blocks, but only a hook can hand the seat the
# stash-free recipe in its refusal message (PreToolUse contract: exit 2 = refused,
# stderr fed back to the model). Driven exactly like the ABS-243 kill guard.
if command -v jq >/dev/null 2>&1 && [ -f "$STASH_HOOK" ]; then
    # NOTE the `|| ec=$?` form everywhere below: this file runs under `set -e`
    # (line 16), so a bare `out=$(stash_hook …); ec=$?` on a REFUSED command would
    # abort the whole suite file at the guard's exit 2 instead of asserting on it.
    stash_hook() {  # <command> -> prints stderr, returns the hook's exit code
        printf '{"tool_name":"Bash","tool_input":{"command":%s}}' "$(printf '%s' "$1" | jq -Rs .)" \
            | ORCH_SEAT=1 ORCH_ROLE=be-developer ORCH_TICKET=ABS-272 \
              ORCH_STASH_GUARD_LOG="$TEST_DIR/stash-guard.log" bash "$STASH_HOOK" 2>&1
    }
    new_env

    for c in "git stash" "git stash pop" "git stash push -u" "git stash save wip" \
             "git stash apply" "git stash drop" "git stash clear" \
             "cd /tmp && git stash pop" "git -C /tmp/wt stash pop"; do
        ec=0; out=$(stash_hook "$c") || ec=$?
        assert_eq "$ec" "2" "ABS-272: guard REFUSES '$c' (exit 2 = command never runs)"
    done

    ec=0; out=$(stash_hook "git stash pop") || ec=$?
    assert_contains "$out" "git worktree add --detach" "ABS-272: the refusal message names the allowed stash-free recipe"
    assert_contains "$out" "SHARED by ALL worktrees" "ABS-272: the refusal message states WHY (shared refs/stash)"
    assert_contains "$(cat "$TEST_DIR/stash-guard.log" 2>/dev/null)" "BLOCKED" "ABS-272: blocked stashes are logged (ABS-66 observability)"

    # No false positives: read-only inspection never writes refs/stash.
    for c in "git stash list" "git stash show -p" "git commit -m 'stash the idea'" "git status"; do
        ec=0; stash_hook "$c" >/dev/null 2>&1 || ec=$?
        assert_eq "$ec" "0" "ABS-272: guard ALLOWS '$c' (no false positive)"
    done

    # A HUMAN shell (no seat marker) is never guarded; kill switch restores legacy.
    ec=0
    printf '{"tool_name":"Bash","tool_input":{"command":"git stash pop"}}' \
        | env -u ORCH_SEAT -u ORCH_ROLE -u ORCH_TICKET bash "$STASH_HOOK" >/dev/null 2>&1 || ec=$?
    assert_eq "$ec" "0" "ABS-272: a human shell (no ORCH_SEAT marker) is never guarded"
    ec=0
    printf '{"tool_name":"Bash","tool_input":{"command":"git stash pop"}}' \
        | ORCH_SEAT=1 ORCH_STASH_GUARD=0 bash "$STASH_HOOK" >/dev/null 2>&1 || ec=$?
    assert_eq "$ec" "0" "ABS-272: ORCH_STASH_GUARD=0 restores legacy behavior (hook allows)"

    cleanup_env
else
    echo -e "  ${YELLOW}SKIP${NC} ABS-272 guard-hook cases (jq or $STASH_HOOK missing)"
fi

# --- AC3: the codified recipe is a non-regression of the bug ------------------
# Drive the recipe from _common-rules.md §9 end to end in a repo that ALREADY has a
# sibling seat's stash on the shared stack, and prove the two properties the three
# incidents violated: (1) the shared stash stack is BYTE-IDENTICAL afterwards — the
# sibling's work is untouched; (2) the throwaway worktree is removed — no leak.
new_env
BASEREPO="$(mktemp -d /tmp/orchestrator-stashrecipe-XXXXXX)"
git -C "$BASEREPO" init -q
git -C "$BASEREPO" config user.email t@t; git -C "$BASEREPO" config user.name t
printf 'v1\n' > "$BASEREPO/suite.txt"
git -C "$BASEREPO" add suite.txt
git -C "$BASEREPO" commit -q -m "base"
BASE_SHA="$(git -C "$BASEREPO" rev-parse HEAD)"

# A SIBLING seat's uncommitted work, parked on the SHARED stash stack (the exact
# thing ABS-251/ABS-254 popped away from ABS-255/ABS-265).
printf 'sibling work in progress\n' > "$BASEREPO/sibling.txt"
git -C "$BASEREPO" add sibling.txt
git -C "$BASEREPO" stash push -q -m "sibling seat: uncommitted work"
STASH_BEFORE="$(git -C "$BASEREPO" stash list)"
WT_BEFORE="$(git -C "$BASEREPO" worktree list | wc -l | tr -d ' ')"

# THIS seat: uncommitted work in its own tree + a baseline comparison via the recipe.
printf 'v2 (my uncommitted work)\n' > "$BASEREPO/suite.txt"
RECIPE_WT="$BASEREPO/../stash-recipe-wt-$$"
git -C "$BASEREPO" worktree add --detach -q "$RECIPE_WT" "$BASE_SHA"
BASELINE_RESULT="$(cat "$RECIPE_WT/suite.txt")"          # the suite's view at base
git -C "$BASEREPO" worktree remove --force "$RECIPE_WT"

assert_eq "$BASELINE_RESULT" "v1" "ABS-272: the throwaway worktree really shows the BASE state (baseline is meaningful)"
assert_eq "$(cat "$BASEREPO/suite.txt")" "v2 (my uncommitted work)" "ABS-272: the seat's OWN uncommitted work survives the baseline run"
assert_eq "$(git -C "$BASEREPO" stash list)" "$STASH_BEFORE" "ABS-272: the SHARED stash stack is unchanged (sibling's work untouched)"
assert_eq "$(git -C "$BASEREPO" worktree list | wc -l | tr -d ' ')" "$WT_BEFORE" "ABS-272: the throwaway worktree is removed (no worktree leak)"
TOTAL=$((TOTAL + 1))
if [ ! -d "$RECIPE_WT" ]; then
    echo -e "  ${GREEN}PASS${NC} ABS-272: recipe leaves no directory behind"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-272: throwaway worktree dir $RECIPE_WT still exists"; FAIL=$((FAIL + 1))
fi
rm -rf "$BASEREPO" "$RECIPE_WT"
cleanup_env

# --- AC1: the recipe is CODIFIED in the common seat rules (ABS-174 seam) ------
RULES="$REPO_ROOT/harness/claude/agents/_common-rules.md"
assert_contains "$(cat "$RULES" 2>/dev/null)" "git worktree add --detach" "ABS-272 AC1: _common-rules.md carries the stash-free baseline recipe"
assert_contains "$(cat "$RULES" 2>/dev/null)" "refs/stash" "ABS-272 AC1: the rule states the reason (shared refs/stash across worktrees)"
# The recipe block itself must not teach `git stash` — strip the prose lines that
# NAME the forbidden command and assert the remaining command block is stash-free.
assert_not_contains "$(sed -n '/^```bash$/,/^```$/p' "$RULES" 2>/dev/null | grep -A2 'worktree add --detach' || true)" \
    "git stash" "ABS-272 AC1: the codified recipe contains no git stash"
# _common-rules.md IS setup-template-substituted (it already carries AITBC),
# so the recipe's base branch MUST use the main token like every sibling agent
# def (rte.md). Hardcoding origin/main would make the recipe error out for any consumer
# whose main branch is master/develop — while git stash is denied at the same time,
# leaving that seat with NO baseline method at all: the very deadlock this ticket removes.
assert_contains "$(cat "$RULES" 2>/dev/null)" 'git merge-base HEAD origin/main' \
    "ABS-272 AC1: the recipe's base branch uses the main token (consumer-portable)"
assert_not_contains "$(cat "$RULES" 2>/dev/null)" 'origin/main)' \
    "ABS-272 AC1: the recipe does not hardcode origin/main (breaks non-main consumers)"

# =============================================================================
echo -e "\n${CYAN}ABS-194 — every spawn emits a SEAT-CWD diagnostic with the effective worktree cwd${NC}"
# =============================================================================
# Origin — ABS-166: a resume spawn silently ran in the main checkout (lost cwd)
# and burned a full escalation cycle. run_spawn_cmd (the single spawn choke
# point) now logs the resolved seat cwd per spawn so a Cwd loss is immediately
# visible in run.log, and re-derives the worktree identically to the first spawn.
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-seatcwd-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "seat cwd story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
RUNLOG="$ORCH_STATE_DIR/run.log"
seatcwd_line=$(grep 'SEAT-CWD' "$RUNLOG" 2>/dev/null | grep -F "$T" | head -1)
assert_contains "$seatcwd_line" "SEAT-CWD" "ABS-194: live spawn emits a SEAT-CWD run.log event"
assert_contains "$seatcwd_line" "$T" "ABS-194: SEAT-CWD row carries the ticket-id"
assert_contains "$seatcwd_line" "cwd=$TARGET/tmp/$T-work" "ABS-194: SEAT-CWD shows the provisioned worktree path (not the main checkout)"
assert_not_contains "$seatcwd_line" "cwd=<main-checkout>" "ABS-194: a worktree-eligible spawn does NOT fall back to the main checkout"
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-207 — the ABS-116 BOUNCE-REROUTE resume at In Progress lands in the ticket worktree${NC}"
# =============================================================================
# Residual ABS-166 cwd-loss: In Progress was NOT worktree-eligible, so the ABS-116
# reviewer/gate backward bounce (In Review -> In Progress) that re-routes to the
# implementer resumed in the MAIN checkout (write-refused / wasted escalation).
# In Progress is now worktree-eligible for that BOUNCE-REROUTE seat ONLY (forward
# and neutral In Progress transitions map to NOOP and never spawn), so the resume
# re-derives the ticket's EXISTING worktree via the ABS-194 resolve_seat_cwd path.
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-abs207-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "bounce resume story" --role be-developer)
baseline
# First spawn at Ready for Development provisions the ticket worktree.
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
TOTAL=$((TOTAL + 1))
if [ -e "$TARGET/tmp/$T-work/.git" ]; then
    echo -e "  ${GREEN}PASS${NC} ABS-207: RfD spawn provisioned the worktree (precondition)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} ABS-207: worktree not provisioned at RfD"; FAIL=$((FAIL + 1))
fi
# Drive forward to In Review, then the reviewer bounces backward into In Progress.
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
baseline
tracker transition "$T" "In Progress" --actor system-architect --reason "review findings, back to implementer" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
RUNLOG="$ORCH_STATE_DIR/run.log"
assert_contains "$out" "INTENT SPAWN ticket=$T role=be-developer to=In Progress" "ABS-207: backward bounce re-routes to the implementer at In Progress"
assert_contains "$(cat "$RUNLOG" 2>/dev/null)" "BOUNCE-REROUTE" "ABS-207: run.log records the BOUNCE-REROUTE"
seatcwd_line=$(grep 'SEAT-CWD' "$RUNLOG" 2>/dev/null | grep -F "$T" | grep -F "In Progress" | tail -1)
assert_contains "$seatcwd_line" "cwd=$TARGET/tmp/$T-work" "ABS-207: the In Progress resume cwd is the ticket worktree (not the main checkout)"
assert_not_contains "$seatcwd_line" "cwd=<main-checkout>" "ABS-207: the In Progress resume does NOT fall back to the main checkout"
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- ABS-207 fail-closed: bounce resume with NO worktree provisionable rests ---
# If worktree provisioning fails for the In Progress bounce resume it must NOT
# fall through to the main checkout — the same C9 fail-closed guarantee, now on
# the In Progress path. Force the failure by occupying the <ticket>-auto branch
# in the main checkout so `git worktree add` fails, and never provisioning the
# worktree first (so resolve_seat_cwd cannot reconnect an existing one).
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-abs207fail-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
T=$(tracker create --type ticket --title "bounce fail story" --role be-developer)
git -C "$TARGET" checkout -q -b "$T-auto"   # occupy the branch -> `worktree add` must fail
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
# Drive forward via the tracker only (no orch spawn -> worktree never provisioned).
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
baseline
tracker transition "$T" "In Progress" --actor system-architect --reason "review findings, back to implementer" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null || true)
assert_contains "$out" "INTENT SKIP-NOWORKTREE ticket=$T" "ABS-207: In Progress bounce with unprovisionable worktree rests (fail-closed)"
assert_not_contains "$out" "INTENT HANDOFF ticket=$T" "ABS-207: no In Progress spawn completed in the main checkout on provisioning failure"
assert_eq "$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')" "0" "ABS-207: the spawn seam was never invoked for the failed In Progress resume"
unset ORCH_TARGET_REPO STUB_RECORD_FILE
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# --- extra-allow OVERRIDE via env (and no pre-existing source file) -----------
if command -v jq >/dev/null 2>&1; then
    new_env
    export ORCH_WORKTREE_SPAWNS=1
    export ORCH_WORKTREE_EXTRA_ALLOW="Write(custom/**),Bash(echo:*)"
    TARGET="$(mktemp -d /tmp/orchestrator-wtover-XXXXXX)"
    warm_git_repo "$TARGET"
    export ORCH_TARGET_REPO="$TARGET"
    T=$(tracker create --type ticket --title "wt override story" --role be-developer)
    baseline
    tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
    ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
    DST="$TARGET/tmp/$T-work/.claude/settings.local.json"
    assert_eq "$(jq -r '.permissions.allow | index("Write(custom/**)") != null' "$DST" 2>/dev/null)" "true" "ABS-131: override grant Write(custom/**) applied"
    assert_eq "$(jq -r '.permissions.allow | index("Bash(echo:*)") != null' "$DST" 2>/dev/null)" "true" "ABS-131: override grant Bash(echo:*) applied"
    assert_eq "$(jq -r '.permissions.allow | index("Write(scripts/**)") != null' "$DST" 2>/dev/null)" "false" "ABS-131: override REPLACES the default (no scripts/** leak)"
    unset ORCH_TARGET_REPO ORCH_WORKTREE_EXTRA_ALLOW
    export ORCH_WORKTREE_SPAWNS=0
    rm -rf "$TARGET"
    cleanup_env
else
    echo -e "  ${YELLOW}SKIP${NC} ABS-131 extra-allow override test (jq not installed)"
fi

# =============================================================================
echo -e "\n${CYAN}ABS-118 crash backoff — exponential per (ticket,status), reset on success${NC}"
# =============================================================================
new_env
export ORCH_BACKOFF_BASE_SECONDS=60
T=$(tracker create --type ticket --title "backoff story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(STUB_FAIL=1 ORCH_NOW=1000000 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "crash recorded on the failing spawn"
assert_eq "$(cat "$ORCH_STATE_DIR/backoff-$T" 2>/dev/null | cut -f3)" "60" "first crash writes the base delay"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "BACKOFF" "BACKOFF event in run.log"
# Inside the delay window the sweep passes the ticket over — free of charge.
out=$(STUB_FAIL=1 ORCH_NOW=1000030 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-BACKOFF ticket=$T" "sweep inside the delay -> SKIP-BACKOFF"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "no spawn inside the backoff window"
# Past expiry the retry runs; a second crash doubles the delay.
out=$(STUB_FAIL=1 ORCH_NOW=1000100 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "expired delay -> spawn retried"
assert_eq "$(cat "$ORCH_STATE_DIR/backoff-$T" 2>/dev/null | cut -f3)" "120" "second crash doubles the delay"
# Success clears the marker.
out=$(ORCH_NOW=1000400 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF ticket=$T" "healed spawn succeeds after the delay"
TOTAL=$((TOTAL + 1))
if [ ! -f "$ORCH_STATE_DIR/backoff-$T" ]; then
    echo -e "  ${GREEN}PASS${NC} success removes the backoff marker"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} backoff marker survived a successful spawn"; FAIL=$((FAIL + 1))
fi
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-118 outage pause — fast-fail burst, probes, auto-resume${NC}"
# =============================================================================
new_env
export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=3
export ORCH_PROBE_INTERVALS="100 200" ORCH_OUTAGE_RESUME=auto ORCH_NOTIFY_TICKET=""
A=$(tracker create --type ticket --title "o1" --role be-developer)
B=$(tracker create --type ticket --title "o2" --role be-developer)
C=$(tracker create --type ticket --title "o3" --role be-developer)
D=$(tracker create --type ticket --title "o4" --role be-developer)
baseline
for t in "$A" "$B" "$C"; do tracker transition "$t" "Ready for Development" --actor po --reason go >/dev/null; done
out=$(STUB_FAIL=1 ORCH_NOW=1000000 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
TOTAL=$((TOTAL + 1))
if [ -f "$ORCH_STATE_DIR/outage" ]; then
    echo -e "  ${GREEN}PASS${NC} 3 consecutive instant crashes declare an outage"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} outage file missing after the fast-fail burst"; FAIL=$((FAIL + 1))
fi
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "OUTAGE-PAUSE" "OUTAGE-PAUSE event in run.log"
assert_contains "$out" "environment outage" "outage NOTIFY visible"
# While paused (before the first probe interval) every dispatch is refused.
tracker transition "$D" "Ready for Development" --actor po --reason go >/dev/null
out=$(STUB_FAIL=1 ORCH_NOW=1000050 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-OUTAGE ticket=$D" "paused loop refuses spawns"
assert_not_contains "$out" "INTENT SPAWN ticket=$D" "no spawn during the pause"
# Probe time: exactly one probe runs; still failing -> pause extends.
out=$(STUB_FAIL=1 ORCH_NOW=1000150 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
probe_lines=$(grep -c "PROBE" "$ORCH_STATE_DIR/run.log" || true)
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "PROBE" "probe admitted at the interval"
TOTAL=$((TOTAL + 1))
if [ -f "$ORCH_STATE_DIR/outage" ]; then
    echo -e "  ${GREEN}PASS${NC} failed probe keeps the pause"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} failed probe cleared the outage"; FAIL=$((FAIL + 1))
fi
next_probe=$(cut -f3 "$ORCH_STATE_DIR/outage" 2>/dev/null)
assert_eq "$next_probe" "1000350" "failed probe walks to the next interval (200s)"
# Healed environment: the next probe succeeds and resumes the run.
out=$(ORCH_NOW=1000400 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "AUTO-RESUME" "successful probe logs AUTO-RESUME"
TOTAL=$((TOTAL + 1))
if [ ! -f "$ORCH_STATE_DIR/outage" ]; then
    echo -e "  ${GREEN}PASS${NC} successful probe clears the outage"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} outage survived a successful probe"; FAIL=$((FAIL + 1))
fi
out=$(ORCH_NOW=1000500 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "SKIP-OUTAGE" "resumed loop spawns normally again"
cleanup_env

# Manual mode: no probes; only removing the outage file resumes.
new_env
export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=3 ORCH_OUTAGE_RESUME=manual
T=$(tracker create --type ticket --title "manual story" --role be-developer)
baseline
printf '%s\t%s\t%s\n' 1000000 0 1000100 > "$ORCH_STATE_DIR/outage"
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_NOW=1000500 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-OUTAGE ticket=$T" "manual mode: probe time passed but no probe fires"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log")" "PROBE" "manual mode: no PROBE event"
rm -f "$ORCH_STATE_DIR/outage"
out=$(ORCH_NOW=1000600 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "operator removed the outage file -> loop resumes"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-118 escalation-seat crash — NOTIFY + halt, never a respawn loop${NC}"
# =============================================================================
new_env
export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=0 ORCH_NOTIFY_TICKET=""
T=$(tracker create --type ticket --title "escalation story" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
tracker transition "$T" "Needs PO Decision" --actor qas --reason "product question" >/dev/null
out=$(STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "ESCALATION-CRASH" "NPD seat crash logs ESCALATION-CRASH"
assert_contains "$out" "escalation seat" "ops NOTIFY sent for the crashed escalation seat"
TOTAL=$((TOTAL + 1))
if [ -f "$ORCH_STATE_DIR/halt-$T" ]; then
    echo -e "  ${GREEN}PASS${NC} halt marker written for the crashed escalation seat"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} halt marker missing"; FAIL=$((FAIL + 1))
fi
# Sweeps do NOT respawn the halted seat — and the stuck detector stays silent.
out=""
for _ in 1 2 3 4; do out="$out$(STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)"; done
assert_contains "$out" "INTENT SKIP-HALT ticket=$T" "halted ticket is skipped by the sweep"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" "no respawn while halted"
assert_not_contains "$out" "stuck detected: $T" "stuck detector silent for the halted ticket"
# Operator resume: removing the marker re-enables the dispatch.
rm -f "$ORCH_STATE_DIR/halt-$T"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T role=po-agent" "operator removed the halt -> seat respawns"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-125 spawn telemetry — tool usage counts + ordered sequence${NC}"
# =============================================================================
new_env
export STUB_SESSION_ID="deadbeef-aaaa-4bbb-8ccc-dddd00001111"
export ORCH_TRANSCRIPT_DIR="$TEST_DIR/transcripts"
mkdir -p "$ORCH_TRANSCRIPT_DIR/some-cwd-slug"
# Fixture transcript: known call order, plus a payload marker that must NEVER
# reach the telemetry (names only).
# Includes the architect-F1/F2 traps: a parallel-call line (two tool_use
# blocks in ONE message) and an MCP block whose INPUT carries a key literally
# named "name" (the payload-leak case a greedy match falls for).
cat > "$ORCH_TRANSCRIPT_DIR/some-cwd-slug/$STUB_SESSION_ID.jsonl" <<'TRANSCRIPT'
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"SECRET-PAYLOAD-MARKER"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"Read","input":{"file_path":"b"}},{"type":"tool_use","id":"t3","name":"Bash","input":{"command":"SECRET-PAYLOAD-MARKER"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t4","name":"mcp__jira__get","input":{"name":"PAYLOAD-NAME-MARKER"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t5","name":"Skill","input":{"skill":"code-review"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t6","name":"Edit","input":{"file_path":"c"}}]}}
TRANSCRIPT
T=$(tracker create --type ticket --title "telemetry story" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tele=$(grep "TELEMETRY" "$ORCH_STATE_DIR/run.log" | head -1)
assert_contains "$tele" "Read=2" "telemetry aggregates counts (Read=2, incl. the parallel-call line)"
assert_contains "$tele" "Bash=1" "telemetry counts the SECOND block of a parallel-call line (F2)"
assert_contains "$tele" "mcp__jira__get=1" "MCP tool recorded by its TOOL name, not its input.name payload (F1)"
assert_contains "$tele" "Skill=1" "telemetry counts skill invocations (plain Skill — sub-name is payload)"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log")" "SECRET-PAYLOAD-MARKER" "no arguments/payloads in the run.log"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log")" "PAYLOAD-NAME-MARKER" "input.name payload never leaks (F1)"
seqfile=$(ls "$ORCH_STATE_DIR/telemetry/"*.seq 2>/dev/null | head -1)
assert_eq "$(sed -n '1p' "$seqfile" 2>/dev/null)" "Read" "sequence preserves call order (1st)"
assert_eq "$(sed -n '3p' "$seqfile" 2>/dev/null)" "Bash" "sequence preserves call order (3rd, parallel block)"
assert_eq "$(sed -n '4p' "$seqfile" 2>/dev/null)" "mcp__jira__get" "sequence preserves call order (4th, MCP)"
assert_eq "$(sed -n '6p' "$seqfile" 2>/dev/null)" "Edit" "sequence preserves call order (6th)"
assert_not_contains "$(cat "$seqfile" 2>/dev/null)" "PAYLOAD-NAME-MARKER" "no payloads in the sequence file"
# Report: used vs granted names the never-used granted tools.
report=$(bash "$REPO_ROOT/scripts/orchestrator-report.sh" "$ORCH_STATE_DIR/run.log" 2>/dev/null)
assert_contains "$report" "tools used vs granted" "report prints the telemetry section"
assert_contains "$report" "granted but never used" "report lists least-privilege candidates"
# Missing transcript -> graceful 'unavailable', spawn unaffected.
rm -rf "$ORCH_TRANSCRIPT_DIR"
U=$(tracker create --type ticket --title "no transcript" --role fe-developer)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$U" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(grep "TELEMETRY" "$ORCH_STATE_DIR/run.log" | grep "$U")" "unavailable" "missing transcript degrades to unavailable"
assert_contains "$(grep "HANDOFF" "$ORCH_STATE_DIR/run.log" | grep "$U" || true)" "$U" "telemetry failure never breaks the spawn"
# ORCH_TELEMETRY=0 disables both outputs.
V=$(tracker create --type ticket --title "telemetry off" --role fe-developer)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$V" "Ready for Development" --actor po --reason go >/dev/null
ORCH_TELEMETRY=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(grep "TELEMETRY" "$ORCH_STATE_DIR/run.log" | grep "$V" || true)" "$V" "ORCH_TELEMETRY=0 writes no telemetry"
unset STUB_SESSION_ID ORCH_TRANSCRIPT_DIR
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-123 built-in skills for seats — tools wiring + invocation unlock${NC}"
# =============================================================================
# Mapped seats carry the Skill tool (harness namespace — .claude/ is the
# governor artifact, see the ABS-120 note); judgment seats stay untouched.
for ns in "harness/claude/agents"; do
    for r in be-developer fe-developer data-engineer system-architect qas rte; do
        assert_contains "$(grep '^tools:' "$REPO_ROOT/$ns/$r.md")" "Skill" "$ns/$r.md toolset includes Skill"
    done
    assert_not_contains "$(grep '^tools:' "$REPO_ROOT/$ns/po-agent.md" 2>/dev/null || true)" "Skill" "$ns/po-agent.md stays without Skill (least privilege)"
done
# The seam adds the invocation unlock exactly for Skill-carrying toolsets.
new_env
mkdir -p "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/claude" <<'FAKECLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS_FILE:?}"
cat >/dev/null
echo '{"result":"ok","session_id":"11111111-2222-4333-8444-555566667777"}'
FAKECLAUDE
chmod +x "$TEST_DIR/bin/claude"
printf 'packet' > "$TEST_DIR/packet.txt"
export FAKE_ARGS_FILE="$TEST_DIR/args"
ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" qas DEMO-1 "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>&1 || true
assert_contains "$(cat "$FAKE_ARGS_FILE" 2>/dev/null)" "--allowedTools Skill" "Skill toolset -> seam passes the invocation unlock"
ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" po-agent DEMO-1 "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>&1 || true
assert_not_contains "$(cat "$FAKE_ARGS_FILE" 2>/dev/null)" "--allowedTools" "Skill-less toolset -> no unlock passed"
unset FAKE_ARGS_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-174 shared common-rules — spawn seam prepends _common-rules.md${NC}"
# =============================================================================
# build_agents_json() prepends the frontmatter-stripped body of
# <agents-dir>/_common-rules.md ahead of the role body (the commons file is fed
# to awk FIRST, the role def SECOND; the role still supplies name/description/
# tools). Absent file -> fail-open (byte-identical to pre-ABS-174). Underscore-
# prefixed defs are never spawnable roles. Isolated ORCH_AGENTS_DIR fixture, a
# fake claude that records its argv, ORCH_RESUME_SESSION_ID cleared so the fresh
# --agents path (not the resume path) is exercised.
new_env
mkdir -p "$TEST_DIR/bin" "$TEST_DIR/adir"
cat > "$TEST_DIR/bin/claude" <<'FAKECLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS_FILE:?}"
cat >/dev/null
echo '{"result":"ok"}'
FAKECLAUDE
chmod +x "$TEST_DIR/bin/claude"
printf 'packet' > "$TEST_DIR/packet.txt"
export FAKE_ARGS_FILE="$TEST_DIR/args"
cat > "$TEST_DIR/adir/testrole.md" <<'ROLEDEF'
---
name: testrole
description: a test seat
tools: [Read, Bash]
---
ROLE-BODY-UNIQUE-MARKER
ROLEDEF
cat > "$TEST_DIR/adir/_common-rules.md" <<'COMMONS'
---
name: _common-rules
description: COMMONS-FRONTMATTER-SHOULD-NOT-LEAK
---
COMMON-RULES-BODY-MARKER
COMMONS
abs174_spawn() {
    ORCH_RESUME_SESSION_ID= ORCH_TOOLS= ORCH_MODEL= \
    ORCH_AGENTS_DIR="$TEST_DIR/adir" ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" \
    bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" "$1" DEMO-1 \
        "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>"$TEST_DIR/err"
}

# 1) Commons present: the --agents prompt carries BOTH bodies; frontmatter stripped.
abs174_spawn testrole || true
agents="$(sed -n 's/.*--agents \(.*\) --agent .*/\1/p' "$FAKE_ARGS_FILE")"
assert_contains "$agents" "COMMON-RULES-BODY-MARKER" "ABS-174: commons body is prepended into the --agents prompt"
assert_contains "$agents" "ROLE-BODY-UNIQUE-MARKER" "ABS-174: role body preserved after the commons"
assert_not_contains "$agents" "COMMONS-FRONTMATTER-SHOULD-NOT-LEAK" "ABS-174: commons frontmatter stripped (description absent from prompt)"
assert_contains "$agents" "\"testrole\":" "ABS-174: role def still supplies the agent name/key"

# 2) Not spawnable: an underscore-prefixed role is refused before any spawn.
# (Guarded by `if` so the expected non-zero exit does not trip the suite's set -e.)
if abs174_spawn _common-rules; then rc=0; else rc=$?; fi
assert_eq "$rc" "1" "ABS-174: underscore-prefixed _common-rules is refused as a role (die)"
assert_contains "$(cat "$TEST_DIR/err" 2>/dev/null)" "not spawnable" "ABS-174: refusal explains why (_common-rules not spawnable)"

# 3) Fail-open: remove the commons file -> role body intact, no commons, exit 0.
rm -f "$TEST_DIR/adir/_common-rules.md"
if abs174_spawn testrole; then rc=0; else rc=$?; fi
assert_eq "$rc" "0" "ABS-174: fail-open — seam still exits 0 without _common-rules.md"
agents="$(sed -n 's/.*--agents \(.*\) --agent .*/\1/p' "$FAKE_ARGS_FILE")"
assert_contains "$agents" "ROLE-BODY-UNIQUE-MARKER" "ABS-174: fail-open — role body still present"
assert_not_contains "$agents" "COMMON-RULES-BODY-MARKER" "ABS-174: fail-open — no commons when the file is absent"
unset FAKE_ARGS_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-251 argv-size gate — oversized agent def falls back to --agent (Windows ~32KB CreateProcess limit)${NC}"
# =============================================================================
# Failure mode (consumer repro, BUSCH): Windows caps a command line at ~32 KB, so
# passing a large def inline via --agents crashes every spawn of that role
# (system-architect, 37.6 KB). The seam now gates on ${#AGENTS_JSON} >
# ORCH_AGENTS_ARG_MAX (PILOT-55: platform-dependent default — Windows 24000, POSIX
# ≈ getconf ARG_MAX) and falls back to --agent <role> (on-disk def), narrowing write
# tools explicitly so a read-only seat stays read-only.
new_env
mkdir -p "$TEST_DIR/bin" "$TEST_DIR/adir"
cat > "$TEST_DIR/bin/claude" <<'FAKECLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS_FILE:?}"
cat >/dev/null
echo '{"result":"ok"}'
FAKECLAUDE
chmod +x "$TEST_DIR/bin/claude"
printf 'packet' > "$TEST_DIR/packet.txt"
export FAKE_ARGS_FILE="$TEST_DIR/args"
# A small def (well under the gate) and a big one (~31 KB body, over the gate).
cat > "$TEST_DIR/adir/smallrole.md" <<'SMALLDEF'
---
name: smallrole
description: a small test seat
tools: [Read, Bash]
---
SMALL-ROLE-BODY
SMALLDEF
{
    printf -- '---\nname: bigrole\ndescription: a big test seat\ntools: [Read, Bash, Write, Edit]\n---\n'
    awk 'BEGIN { for (i = 0; i < 600; i++) print "BIG-DEF-PADDING-0123456789-0123456789-0123456789" }'
} > "$TEST_DIR/adir/bigrole.md"
abs251_spawn() {  # <role> — extra env (ORCH_TOOLS/ORCH_AGENTS_ARG_MAX) inherited from the caller
    # PILOT-55: the gate default is now platform-dependent (POSIX ≈ getconf ARG_MAX,
    # ~1 MB here), which would take the ~31 KB bigrole INLINE and void the fallback
    # assertions below. Pin the gate to the historic 24000 B unless the caller
    # overrides it, so these cases test the MECHANISM at a fixed threshold, not the
    # ambient platform default (which its own case above/below sets explicitly).
    ORCH_RESUME_SESSION_ID= ORCH_MODEL= ORCH_AGENTS_ARG_MAX="${ORCH_AGENTS_ARG_MAX:-24000}" \
    ORCH_AGENTS_DIR="$TEST_DIR/adir" ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" \
    bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" "$1" DEMO-251 \
        "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>"$TEST_DIR/err"
}

# AC4 — under the gate: the inline --agents path is unchanged (no fallback, no narrowing).
ORCH_TOOLS= abs251_spawn smallrole || true
args="$(cat "$FAKE_ARGS_FILE")"
assert_contains "$args" "--agents" "ABS-251: def under the gate still passes the inline --agents JSON (byte-identical macOS/Linux path)"
assert_contains "$args" "--agent smallrole" "ABS-251: under the gate the --agent selector is still passed"
assert_not_contains "$args" "--disallowedTools" "ABS-251: under the gate no narrowing flag is added (no behavior change)"
assert_not_contains "$(cat "$TEST_DIR/err")" "ORCH_AGENTS_ARG_MAX" "ABS-251: under the gate the seam stays silent about the fallback"

# AC1 — over the gate: --agents is OMITTED, the on-disk def is selected via --agent.
ORCH_TOOLS= abs251_spawn bigrole || true
args="$(cat "$FAKE_ARGS_FILE")"
assert_not_contains "$args" "--agents" "ABS-251 AC1: oversized def -> inline --agents JSON is omitted (argv stays under the Windows limit)"
assert_contains "$args" "--agent bigrole" "ABS-251 AC1: oversized def -> falls back to --agent <role> (on-disk def)"
assert_contains "$(cat "$TEST_DIR/err")" "ORCH_AGENTS_ARG_MAX" "ABS-251 AC3: the fallback is announced with the gate that triggered it"

# AC1 — the gate is configurable: raise it and the same def goes inline again.
ORCH_TOOLS= ORCH_AGENTS_ARG_MAX=999999 abs251_spawn bigrole || true
assert_contains "$(cat "$FAKE_ARGS_FILE")" "--agents" "ABS-251 AC1: ORCH_AGENTS_ARG_MAX raises the gate (oversized def goes inline again)"
# ...and lowering it forces the fallback even for a small def.
ORCH_TOOLS= ORCH_AGENTS_ARG_MAX=10 abs251_spawn smallrole || true
assert_not_contains "$(cat "$FAKE_ARGS_FILE")" "--agents" "ABS-251 AC1: a lowered gate forces the fallback for any def (gate is the only trigger)"

# AC2 — tool-narrowing parity: a read-only ORCH_TOOLS override survives the fallback.
# (The on-disk bigrole def grants Write+Edit — without the narrowing the fallback
# would silently re-grant them to a seat the runner handed a read-only toolset.)
ORCH_TOOLS="Read, Bash" abs251_spawn bigrole || true
assert_contains "$(cat "$FAKE_ARGS_FILE")" "--disallowedTools Write,Edit,NotebookEdit" \
    "ABS-251 AC2: fallback + read-only ORCH_TOOLS -> write tools denied (read-only seat stays read-only)"
# A write-granting override is left alone (no bogus denial of tools the seat owns).
ORCH_TOOLS="Read, Write, Edit" abs251_spawn bigrole || true
assert_not_contains "$(cat "$FAKE_ARGS_FILE")" "--disallowedTools" \
    "ABS-251 AC2: fallback + write-granting ORCH_TOOLS -> no denial (writer seats keep their tools)"
# No override at all -> the on-disk tools ARE what the JSON would have carried; nothing to narrow.
ORCH_TOOLS= abs251_spawn bigrole || true
assert_not_contains "$(cat "$FAKE_ARGS_FILE")" "--disallowedTools" \
    "ABS-251 AC2: fallback without ORCH_TOOLS -> no denial (def frontmatter is the same toolset either way)"
unset FAKE_ARGS_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-195 background-task orphan — seat-rule present + prepended; In Progress stays NOTIFY-only${NC}"
# =============================================================================
# Failure mode (ABS-151 Iteration-5-Befund): a seat backgrounds a long task
# (the test suite) and returns an interim final message; its claude process then
# ends WHILE the task still runs, so the result is lost and the ticket is left
# orphaned in "In Progress" with no owning seat, no lock and no live session.
# Fix (a): common seat-rule #5 forbids ending a spawn with a running background
# task, present on the shared seat-prompt surface (_common-rules.md) and so
# prepended into every seat's --agents prompt by the spawn seam.
# Decision (b): STUCK-DETECT on In Progress originally stayed NOTIFY-only (no auto
# resume-spawn of the SAME dead seat — ADR-A-0004 "eyes not hands"). ABS-451
# REVISED the default: the runner now SELF-HEALS an unowned In Progress orphan by
# downgrading it to Ready for Development (a spawnable status → a FRESH seat, not a
# session-resume of the dead one). This block keeps guarding the legacy NOTIFY-only
# SAFETY NET, retained when the heal is disabled (ORCH_INPROGRESS_HEAL_SWEEPS=0);
# the heal-ON default is asserted by tests/orchestrator.d/ABS-451-*.sh.

# --- (a) The seat-rule lives on the shared seat-prompt surface ---------------
common_rules="$REPO_ROOT/harness/claude/agents/_common-rules.md"
assert_contains "$(cat "$common_rules" 2>/dev/null)" "Background-Task-Disziplin" \
    "ABS-195: background-task rule present in _common-rules.md (shared seat-prompt surface)"
assert_contains "$(cat "$common_rules" 2>/dev/null)" "end your spawn while a background task" \
    "ABS-195: rule states the prohibition (never end a spawn with a running background task)"

# --- (a) The spawn seam prepends the rule into a real seat's --agents prompt --
new_env
mkdir -p "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/claude" <<'FAKECLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS_FILE:?}"
cat >/dev/null
echo '{"result":"ok"}'
FAKECLAUDE
chmod +x "$TEST_DIR/bin/claude"
printf 'packet' > "$TEST_DIR/packet.txt"
export FAKE_ARGS_FILE="$TEST_DIR/args"
# ORCH_AGENTS_ARG_MAX raised for this case: it asserts the PREPEND behavior,
# not the size policy — the real agents dir has grown past the 24000B default,
# which would silently fall back to `--agent` (on-disk def) and void the assert
# (ABS-286: this was one of the deterministic-red cases).
ORCH_RESUME_SESSION_ID= ORCH_TOOLS= ORCH_MODEL= \
ORCH_AGENTS_DIR="$REPO_ROOT/harness/claude/agents" \
ORCH_AGENTS_ARG_MAX=200000 \
ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" \
    bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" be-developer DEMO-195 \
        "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>"$TEST_DIR/err" || true
agents="$(sed -n 's/.*--agents \(.*\) --agent .*/\1/p' "$FAKE_ARGS_FILE")"
assert_contains "$agents" "Background-Task-Disziplin" \
    "ABS-195: spawn seam prepends the background-task rule into the seat's --agents prompt"
unset FAKE_ARGS_FILE
cleanup_env

# --- (b) Reproduction + NOTIFY-only SAFETY NET (heal disabled): orphaned In
#         Progress is flagged, not routed. ABS-451: pin the heal OFF so this
#         guards the legacy fallback; the heal-ON default is covered by ABS-451-*.
new_env
export ORCH_NOTIFY_TICKET=""
export ORCH_INPROGRESS_HEAL_SWEEPS=0
T=$(tracker create --type ticket --title "Backgrounded test suite, seat exited mid-run" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason "start; suite backgrounded" >/dev/null
baseline
# End state is identical to the ABS-195 failure: In Progress, lock released, no
# session, result discarded. Sweep to threshold (default ORCH_STUCK_SWEEPS=3).
out=""
for _ in 1 2 3; do out="$out$(ORCH_RECONCILE_ON_STARTUP=1 orch --once 2>/dev/null)"; done
assert_contains "$out" "stuck detected: $T" \
    "ABS-195: orphaned In Progress (backgrounded task, seat exited) is flagged by STUCK-DETECT"
assert_not_contains "$out" "INTENT SPAWN ticket=$T" \
    "ABS-195: NOTIFY-only retained — In Progress orphan is NOT auto resume-spawned (ADR-A-0004)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-124 review-gate sizing — opt-out skip flags per the approved matrix${NC}"
# =============================================================================
new_env
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
E=$(tracker create --type epic --title "Sizing epic")
# Docs-only story: both gates sized away; the ticket must still reach the
# PO acceptance seat (Story Acceptance) without ANY review/test spawn.
T=$(tracker create --type ticket --title "docs only" --parent "$E" --role be-developer --flag skip-review --flag skip-test)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
out=$(ORCH_POLL_INTERVAL=0 ORCH_RECONCILE_ON_STARTUP=0 ORCH_RECONCILE_EVERY_N_CYCLES=1 ORCH_MAX_CYCLES=5 orch --live 2>/dev/null || true)
assert_contains "$out" "INTENT GATE-SKIP ticket=$T" "sized gate skipped (GATE-SKIP intent)"
assert_not_contains "$(grep "system-architect" "$STUB_RECORD_FILE" || true)" "$T" "no review seat spawned"
assert_not_contains "$(grep -w "qas" "$STUB_RECORD_FILE" || true)" "$T" "no qas seat spawned"
assert_contains "$(grep "po-agent" "$STUB_RECORD_FILE")" "$T" "PO acceptance seat still runs (Story Acceptance)"
assert_contains "$(tracker get "$T")" "kind: skip" "gate skip leaves an audit comment"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_not_contains "$status" "Ready for Merge" "v3 tail: docs-only story does not detour to the v1 human gate"
cleanup_env

# skip-review alone: review sized away, the qas gate still runs (allowed combo).
new_env
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
E=$(tracker create --type epic --title "Half sizing epic")
T=$(tracker create --type ticket --title "review only skip" --parent "$E" --role be-developer --flag skip-review)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
out=$(ORCH_POLL_INTERVAL=0 ORCH_RECONCILE_ON_STARTUP=0 ORCH_RECONCILE_EVERY_N_CYCLES=1 ORCH_MAX_CYCLES=4 orch --live 2>/dev/null || true)
assert_contains "$out" "INTENT GATE-SKIP ticket=$T" "skip-review alone: review gate sized away"
assert_contains "$(grep -w "qas" "$STUB_RECORD_FILE")" "$T" "skip-review alone: the qas gate still spawns"
cleanup_env

# Fail-safe matrix: contradictions and ineligible tickets run ALL gates.
new_env
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
E=$(tracker create --type epic --title "Failsafe epic")
# skip-test without skip-review = contradiction (skip-test is a strict subset).
T1=$(tracker create --type ticket --title "contradiction one" --parent "$E" --role be-developer --flag skip-test)
# skip flag + opt-in flag = contradiction; the security flag still forces its gate.
T2=$(tracker create --type ticket --title "contradiction two" --parent "$E" --role be-developer --flag skip-review --flag security)
baseline
for t in "$T1" "$T2"; do
    tracker transition "$t" "Ready for Development" --actor po --reason go >/dev/null
    tracker transition "$t" "In Progress" --actor be-developer --reason start >/dev/null
    tracker transition "$t" "In Review" --actor be-developer --reason handoff >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null || true)
assert_contains "$(grep "system-architect" "$STUB_RECORD_FILE")" "$T1" "skip-test w/o skip-review -> all gates (review spawns)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "GATE-SKIP-CONTRADICTION" "contradiction is a run.log event"
assert_contains "$(grep "system-architect" "$STUB_RECORD_FILE")" "$T2" "skip flag + security flag -> all gates"
# skip-test on a PARENTLESS ticket = ineligible (would bypass the human gate).
: > "$STUB_RECORD_FILE"
T4=$(tracker create --type ticket --title "parentless test skip" --role be-developer --flag skip-review --flag skip-test)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$T4" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T4" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T4" "In Review" --actor be-developer --reason handoff >/dev/null
tracker transition "$T4" "In Test" --actor system-architect --reason reviewed >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null || true)
assert_contains "$(grep -w "qas" "$STUB_RECORD_FILE")" "$T4" "parentless skip-test is ineligible -> qas gate runs"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "GATE-SKIP-INELIGIBLE" "ineligible skip is a run.log event"
unset STUB_RECORD_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-122 per-role spawn provider override (ORCH_SPAWN_CMD_<ROLE>)${NC}"
# =============================================================================
new_env
# Alternative provider stub: records its invocations separately, honors the
# same seam contract (drains stdin, prints a handoff).
ALT="$TEST_DIR/alt-provider.sh"
cat > "$ALT" <<'ALTSTUB'
#!/usr/bin/env bash
cat >/dev/null
printf '%s\t%s\n' "$1" "$2" >> "${ALT_RECORD_FILE:?}"
printf '## Handoff\n\n- role: %s\n- ticket: %s\n- summary: alt provider ran.\n' "$1" "$2"
ALTSTUB
chmod +x "$ALT"
export ALT_RECORD_FILE="$TEST_DIR/alt-records"; : > "$ALT_RECORD_FILE"
export STUB_RECORD_FILE="$TEST_DIR/records"; : > "$STUB_RECORD_FILE"
A=$(tracker create --type ticket --title "default provider" --role be-developer)
B=$(tracker create --type ticket --title "cursor provider" --role be-developer)
baseline
tracker transition "$A" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$B" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$B" "In Progress" --actor qas --reason x >/dev/null
tracker transition "$B" "In Review" --actor qas --reason x >/dev/null
tracker transition "$B" "In Test" --actor qas --reason x >/dev/null
ORCH_SPAWN_CMD_QAS="$ALT" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$ALT_RECORD_FILE")" "qas	$B" "qas seat runs on the per-role override provider"
assert_contains "$(cat "$STUB_RECORD_FILE")" "be-developer	$A" "other seats stay on the default provider"
assert_not_contains "$(cat "$ALT_RECORD_FILE")" "be-developer" "override is scoped to its role"
unset ALT_RECORD_FILE STUB_RECORD_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-156 implementer turn-cap default + override precedence${NC}"
# =============================================================================
# turns_for <role-to-spawn> — drive a live spawn for a seat and echo the turn
# ceiling the runner resolved (recorded by the stub via STUB_TURNS_FILE). Reaches
# the right seat by transitioning to the status that spawns it.
turns_for() {
    local want_role="$1" T
    T=$(tracker create --type ticket --title "turns $want_role" --role be-developer)
    baseline
    tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
    if [ "$want_role" = "qas" ]; then
        tracker transition "$T" "In Progress" --actor be-developer --reason x >/dev/null
        tracker transition "$T" "In Review" --actor be-developer --reason x >/dev/null
        tracker transition "$T" "In Test" --actor system-architect --reason x >/dev/null
    fi
    ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
    awk -F'\t' -v r="$want_role" '$1==r{print $2; exit}' "$STUB_TURNS_FILE"
}

# 1. Implementer seat with no env override -> higher built-in default
# (PILOT-65: raised 90 -> 140; the old 90 was hugged as a target, median 80).
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
assert_eq "$(turns_for be-developer)" "140" "be-developer default cap is the implementer default (140, PILOT-65)"
cleanup_env

# 2. Known-hungry seat carries its built-in per-seat ceiling (PILOT-65: qas 180 —
# calibrated 1.5x above the observed max 119; the old cap 80 sat BELOW that max).
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
assert_eq "$(turns_for qas)" "180" "qas gets its calibrated built-in per-seat ceiling (180, PILOT-65)"
cleanup_env

# (Direct per-seat built-in value checks — qas 180, tech-writer 80, the four
# formerly-capless seats at 50, and the ORCH_MAX_TURNS_DEFAULT_ROLE fallback — run
# in the ABS-199 block below, which SOURCES orchestrator.sh so the functions and
# config vars are in scope; here we only have the spawn-driven `turns_for`.)

# 2b. An explicit operator-wide cap beats the built-in per-seat ceiling too.
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
export ORCH_MAX_TURNS=15
assert_eq "$(turns_for qas)" "15" "explicit operator-wide cap overrides the qas built-in"
unset ORCH_MAX_TURNS
cleanup_env

# 3. Per-role override beats the global cap (AC: per-role > global precedence).
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
export ORCH_MAX_TURNS=15 ORCH_MAX_TURNS_BE_DEVELOPER=30
assert_eq "$(turns_for be-developer)" "30" "ORCH_MAX_TURNS_BE_DEVELOPER beats global ORCH_MAX_TURNS"
cleanup_env

# 4. An explicit operator-wide ORCH_MAX_TURNS overrides the implementer default.
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
export ORCH_MAX_TURNS=15
assert_eq "$(turns_for be-developer)" "15" "explicit operator-wide cap overrides the implementer default"
cleanup_env

# 5. ORCH_MAX_TURNS_IMPLEMENTER tunes the implementer default.
new_env
export STUB_TURNS_FILE="$TEST_DIR/turns.log"; : > "$STUB_TURNS_FILE"
export ORCH_MAX_TURNS_IMPLEMENTER=42
assert_eq "$(turns_for be-developer)" "42" "ORCH_MAX_TURNS_IMPLEMENTER tunes the implementer default"
cleanup_env

# The cursor adapter (EVALUATION) satisfies the seam contract shape offline:
# role-def preamble + packet reach the provider binary as one prompt.
new_env
mkdir -p "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/fake-cursor" <<'FAKECURSOR'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${CURSOR_ARGS_FILE:?}"
echo '{"result": "## Handoff\n- ok", "chatId": "abc-123"}'
FAKECURSOR
chmod +x "$TEST_DIR/bin/fake-cursor"
printf 'PACKET-BODY-MARKER' > "$TEST_DIR/packet.txt"
export CURSOR_ARGS_FILE="$TEST_DIR/cursor-args"
out=$(ORCH_CURSOR_BIN="$TEST_DIR/bin/fake-cursor" ORCH_MODEL="sonnet-4-thinking" \
    bash "$REPO_ROOT/scripts/orchestrator-spawn-cursor.sh" qas DEMO-9 "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" 2>/dev/null)
assert_contains "$(cat "$CURSOR_ARGS_FILE" 2>/dev/null)" "--output-format json" "cursor adapter: headless JSON invocation"
assert_contains "$(cat "$CURSOR_ARGS_FILE" 2>/dev/null)" "PACKET-BODY-MARKER" "cursor adapter: packet reaches the prompt"
assert_contains "$(cat "$CURSOR_ARGS_FILE" 2>/dev/null)" "--model sonnet-4-thinking" "cursor adapter: ORCH_MODEL passes through"
assert_contains "$out" "Handoff" "cursor adapter: provider stdout reaches the seam"
unset CURSOR_ARGS_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-121 per-ticket model label — precedence Env > Label > Frontmatter${NC}"
# =============================================================================
new_env
export STUB_RECORD_FILE="$TEST_DIR/records"
T=$(tracker create --type ticket --title "labelled story" --role be-developer --label "model:sonnet")
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$STUB_RECORD_FILE")" "model=sonnet" "model:sonnet label reaches the seat (no env set)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL" "label use is a run.log event"
# Env beats the label (operator emergency lever).
: > "$STUB_RECORD_FILE"
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$T" "In Review" --actor be-developer --reason done >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$T" "Ready for Development" --actor system-architect --reason rework >/dev/null
ORCH_MODEL_BE_DEVELOPER="claude-opus-4-8" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$STUB_RECORD_FILE")" "model=claude-opus-4-8" "ORCH_MODEL_<ROLE> env beats the ticket label"
# No label, no env -> the seat resolves the frontmatter (runner passes nothing).
: > "$STUB_RECORD_FILE"
U=$(tracker create --type ticket --title "unlabelled story" --role fe-developer)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$U" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(grep "$U" "$STUB_RECORD_FILE")" "model=" "no label + no env -> frontmatter fallback (runner passes no model)"
# Invalid label value -> WARN + ignored, no crash.
: > "$STUB_RECORD_FILE"
I=$(tracker create --type ticket --title "invalid label" --role fe-developer --label "model:gpt5")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$I" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(grep "$I" "$STUB_RECORD_FILE")" "model=" "invalid model label is ignored"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "WARN-MODEL-LABEL" "invalid label logs a WARN event"
assert_contains "$(cat "$STUB_RECORD_FILE")" "$I" "invalid label does not block the spawn"
unset STUB_RECORD_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-128 role-aware model:-label — downsize only for implementer seats${NC}"
# =============================================================================
# Label = IMPLEMENTATION effort, not review effort. A model:sonnet/haiku DOWNSIZE
# may only take effect for mechanical seats (allowlist); review/judgment seats
# (system-architect at In Review, po-agent, …) keep their role default. A
# model:opus UPSIZE applies to ALL roles. Env override still wins everywhere.
new_env
export STUB_RECORD_FILE="$TEST_DIR/records"

# drive_to_review <ticket> — walk a be-developer story to In Review, where the
# runner spawns the reused system-architect reviewer (a non-allowlist seat).
drive_to_review() {
    tracker transition "$1" "Ready for Development" --actor po --reason go >/dev/null
    tracker transition "$1" "In Progress" --actor be-developer --reason start >/dev/null
    tracker transition "$1" "In Review" --actor be-developer --reason done >/dev/null
}

# --- (a) DOWNSIZE (model:sonnet) on a system-architect review -> IGNORED --------
A=$(tracker create --type ticket --title "downsize on architect" --role be-developer --label "model:sonnet")
baseline
drive_to_review "$A"
: > "$STUB_RECORD_FILE"
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL-SKIP	$A	system-architect" "downsize label on a system-architect review -> MODEL-LABEL-SKIP"
assert_not_contains "$(grep "$A" "$STUB_RECORD_FILE")" "model=" "review/judgment seat keeps its role default (no downsized model reaches the seat)"

# --- (b) REGRESSION: DOWNSIZE on an allowlist seat (be-developer) -> APPLIED -----
: > "$STUB_RECORD_FILE"
B=$(tracker create --type ticket --title "downsize on implementer" --role be-developer --label "model:sonnet")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$B" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(grep "$B" "$STUB_RECORD_FILE")" "model=sonnet" "downsize label on be-developer still reaches the seat (allowlist regression)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL	$B	be-developer" "allowlist seat logs MODEL-LABEL (applied)"

# --- (c) UPSIZE (model:opus) on a system-architect review -> APPLIED to all ------
: > "$STUB_RECORD_FILE"
C=$(tracker create --type ticket --title "upsize on architect" --role be-developer --label "model:opus")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
drive_to_review "$C"
: > "$STUB_RECORD_FILE"
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(grep "$C" "$STUB_RECORD_FILE")" "model=opus" "upsize label (opus) reaches even a non-allowlist review seat"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL	$C	system-architect" "upsize label logs MODEL-LABEL (applied) for the architect"

# --- (d) ORCH_MODEL_<ROLE> env keeps HIGHEST precedence, even for a review seat --
: > "$STUB_RECORD_FILE"
D=$(tracker create --type ticket --title "env beats label on architect" --role be-developer --label "model:sonnet")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
drive_to_review "$D"
: > "$STUB_RECORD_FILE"
ORCH_MODEL_SYSTEM_ARCHITECT="claude-opus-4-8" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(grep "$D" "$STUB_RECORD_FILE")" "model=claude-opus-4-8" "ORCH_MODEL_<ROLE> beats the label AND the downsize filter"

# --- (e) blank ORCH_MODEL_LABEL_ROLES -> WARN + built-in default, no crash -------
: > "$STUB_RECORD_FILE"
E=$(tracker create --type ticket --title "blank allowlist config" --role be-developer --label "model:sonnet")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$E" "Ready for Development" --actor po --reason go >/dev/null
ORCH_MODEL_LABEL_ROLES="  " ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(grep "$E" "$STUB_RECORD_FILE")" "model=sonnet" "blank allowlist -> falls back to built-in default (be-developer still gets the downsize)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "WARN-MODEL-LABEL-ROLES" "blank ORCH_MODEL_LABEL_ROLES logs a WARN event"

# --- (f) dry-run surfaces the decision: MODEL-LABEL only for the allowlist seat --
: > "$STUB_RECORD_FILE"
: > "$ORCH_STATE_DIR/run.log"
F=$(tracker create --type ticket --title "dry-run implementer" --role be-developer --label "model:sonnet")
G=$(tracker create --type ticket --title "dry-run architect" --role be-developer --label "model:sonnet")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
tracker transition "$F" "Ready for Development" --actor po --reason go >/dev/null
drive_to_review "$G"
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL	$F	be-developer" "dry-run: allowlist seat -> MODEL-LABEL event"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL-SKIP	$G	system-architect" "dry-run: review seat -> MODEL-LABEL-SKIP (never MODEL-LABEL)"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log")" "MODEL-LABEL	$G	system-architect" "dry-run: review seat never emits an applied MODEL-LABEL"
unset STUB_RECORD_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}PILOT-19 depends_on MERGE-FACT release (ex-ABS-119) + epic-branch worktree basing${NC}"
# =============================================================================
new_env
export ORCH_DEPENDS_GATING=1 ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-abs119-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
GIT119() { git -C "$TARGET" -c user.email=t@t -c user.name=t -c commit.gpgsign=false "$@"; }
MAIN="$(GIT119 symbolic-ref --short HEAD)"
# PILOT-19: the depends_on gate now releases on the MERGE FACT, proven by the
# forge-less probe (story_git_merge_state) against a bare "remote" — so give the
# target a real remote; "the human merge" is a real push to it, no network.
REM_DIR="$(mktemp -d /tmp/orchestrator-abs119-rem-XXXXXX)"; REM="$REM_DIR/rem.git"
git init -q --bare "$REM"
GIT119 remote add rem "$REM"
export ORCH_MAIN_REMOTE=rem
GIT119 push -q rem "$MAIN"
E=$(tracker create --type epic --title "Chain epic")
D=$(tracker create --type ticket --title "the dep" --parent "$E" --role be-developer)
T=$(tracker create --type ticket --title "the dependent" --parent "$E" --role be-developer)
tracker update "$T" depends_on "[$D]" >/dev/null
# The epic integration branch (initially WITHOUT the dep's code) and the dep's
# story branch carrying its not-yet-merged file.
GIT119 checkout -q -b "epic/$E-integration" "$MAIN"
GIT119 push -q rem "epic/$E-integration"
GIT119 checkout -q -b "$D-auto" "$MAIN"
echo "merged dependency code" > "$TARGET/dep-file.txt"
GIT119 add dep-file.txt
GIT119 commit -qm "dep impl [${D}]"
GIT119 push -q rem "$D-auto"
GIT119 checkout -q "$MAIN"
# Drive the dep to Merging (accepted, NOT yet merged onto the epic branch).
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging"; do
    tracker transition "$D" "$s" --actor test --reason drive >/dev/null
done
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "PILOT-19 AC2: dep head not yet an ancestor of the epic branch -> dependent waits"
# ABS-530 merge-fact regression: "the human merges" — the dep's head becomes an
# ancestor of the epic branch and is pushed. While the dep is STILL at 'Merging'
# (not yet Docs/Done), the MERGE FACT alone (not any label) releases the
# dependent, and its provisioned worktree bases on the epic branch tip (sees the
# merged file). This is the pure PILOT-19/ABS-530 path, independent of PILOT-44.
GIT119 checkout -q "epic/$E-integration"
GIT119 merge -q --no-ff -m "Merge $D-auto [$D]" "$D-auto"
GIT119 push -q rem "epic/$E-integration"
GIT119 checkout -q "$MAIN"
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "ABS-530 regression: dep head merged (still 'Merging') -> merge-fact releases the dependent"
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
TOTAL=$((TOTAL + 1))
if [ -f "$TARGET/tmp/$T-work/dep-file.txt" ]; then
    echo -e "  ${GREEN}PASS${NC} PILOT-19 AC1: dep head merged -> dependent spawns; worktree bases on the epic branch (merged file visible)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} dependent worktree missing the epic-branch file (merge-fact release/basing coupling)"; FAIL=$((FAIL + 1))
fi
# Dep -> Blocked (tech-writer blocked) is harmless for the RUNNING dependent:
# the gate is entry-only; a mid-pipeline dependent is never re-gated.
tracker transition "$D" "Blocked" --actor tech-writer --reason "docs env down" >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "dep -> Blocked -> running dependent is not re-gated"
unset ORCH_TARGET_REPO ORCH_MAIN_REMOTE
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET" "$REM_DIR"
cleanup_env

# Cross-epic and multi-dep regressions: an unmerged dep (any epic) holds the gate.
new_env
export ORCH_DEPENDS_GATING=1
export ORCH_MAIN_REMOTE=none   # PILOT-19: offline-fast merge probe (NONE=not merged)
E1=$(tracker create --type epic --title "Epic one")
E2=$(tracker create --type epic --title "Epic two")
DX=$(tracker create --type ticket --title "foreign dep" --parent "$E2" --role be-developer)
T=$(tracker create --type ticket --title "cross dependent" --parent "$E1" --role be-developer)
tracker update "$T" depends_on "[$DX]" >/dev/null
# Walk to 'Merging' (a PRE-Docs, unmerged status): with ORCH_MAIN_REMOTE=none the
# merge probe reports NONE, so an unmerged cross-epic dep holds the gate. (A dep
# in 'Docs' would release under PILOT-44 — covered by its own block below.)
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging"; do
    tracker transition "$DX" "$s" --actor test --reason drive >/dev/null
done
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "cross-epic dep at 'Merging' but UNMERGED -> dependent waits (PILOT-19: label alone doesn't release)"
# Merging -> Done is not a legal edge; reach Done via Ready for Merge.
tracker transition "$DX" "Ready for Merge" --actor test --reason drive >/dev/null
tracker transition "$DX" "Done" --actor human --reason done >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "cross-epic dep Done -> dependent releases (terminal satisfaction)"
# Multi-dep: one at Docs (satisfied under PILOT-44), one still open -> the OPEN
# one holds the gate, so the dependent still waits.
D1=$(tracker create --type ticket --title "dep one" --parent "$E1" --role be-developer)
D2=$(tracker create --type ticket --title "dep two" --parent "$E1" --role be-developer)
T2=$(tracker create --type ticket --title "multi dependent" --parent "$E1" --role be-developer)
tracker update "$T2" depends_on "[$D1, $D2]" >/dev/null
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    tracker transition "$D1" "$s" --actor test --reason drive >/dev/null
done
tracker transition "$D2" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1   # drain events
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$T2" "one of two deps still open -> dependent waits"
export ORCH_DEPENDS_GATING=0
cleanup_env

# --- PILOT-19 AC3: 'depends-strict' opts OUT of merge-fact release (waits for Done) --
new_env
export ORCH_DEPENDS_GATING=1
TARGET="$(mktemp -d /tmp/orchestrator-p19strict-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
GITS() { git -C "$TARGET" -c user.email=t@t -c user.name=t -c commit.gpgsign=false "$@"; }
MAIN="$(GITS symbolic-ref --short HEAD)"
REM_DIR="$(mktemp -d /tmp/orchestrator-p19strict-rem-XXXXXX)"; REM="$REM_DIR/rem.git"
git init -q --bare "$REM"; GITS remote add rem "$REM"; export ORCH_MAIN_REMOTE=rem
GITS push -q rem "$MAIN"
E=$(tracker create --type epic --title "strict epic")
D=$(tracker create --type ticket --title "strict dep" --parent "$E" --role be-developer)
# A dependent that needs the blocker's OWN finished artifact carries depends-strict.
T=$(tracker create --type ticket --title "strict dependent" --parent "$E" --role be-developer --label depends-strict)
tracker update "$T" depends_on "[$D]" >/dev/null
# Give the dep a genuinely MERGED head (this WOULD release a normal dependent) ...
GITS checkout -q -b "epic/$E-integration" "$MAIN"; GITS push -q rem "epic/$E-integration"
GITS checkout -q -b "$D-auto" "$MAIN"; echo x > "$TARGET/d.txt"; GITS add d.txt; GITS commit -qm "impl [${D}]"
GITS checkout -q "epic/$E-integration"; GITS merge -q --no-ff -m "merge [$D]" "$D-auto"; GITS push -q rem "epic/$E-integration"
GITS checkout -q "$MAIN"
# ... but the dep is only at Docs, not Done.
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    tracker transition "$D" "$s" --actor test --reason drive >/dev/null
done
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "PILOT-19 AC3: 'depends-strict' dependent ignores the merge fact and waits for Done"
tracker transition "$D" "Done" --actor human --reason done >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "PILOT-19 AC3: 'depends-strict' releases once the dep is Done"
unset ORCH_TARGET_REPO ORCH_MAIN_REMOTE
export ORCH_DEPENDS_GATING=0
rm -rf "$TARGET" "$REM_DIR"
cleanup_env

# --- PILOT-19 AC4: epic-completion gate UNCHANGED — a child in Docs blocks JOIN ----
new_env
export ORCH_MAIN_REMOTE=none   # offline-fast merge probe for any Docs-resting child
E=$(tracker create --type epic --title "ac4 epic")
A=$(tracker create --type ticket --title "ac4 child" --parent "$E")
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Stories In Flight"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    tracker transition "$A" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT JOIN ticket=$E" "PILOT-19 AC4: a child in Docs (not Done) does NOT complete the epic"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Stories In Flight" "PILOT-19 AC4: epic still rests in Stories In Flight while a child is in Docs"
cleanup_env

echo -e "\n${CYAN}PILOT-44 'Docs' counts as a satisfied dependency (Depends-Gate; ABS-266 post-merge)${NC}"
# =============================================================================
# AC1: a dependency resting in 'Docs' is POST-MERGE (ABS-266) — the Depends-Gate
# treats it as SATISFIED WITHOUT the ancestry probe, closing the v3-pilot #5
# stall (PILOT-30/PILOT-32 blocked on PILOT-29-in-Docs even though its code was
# already merged). ORCH_MAIN_REMOTE=none forces the merge probe to report NONE
# (exactly the flaky/unconfirmed case), so a release here can ONLY come from the
# 'Docs' short-circuit, not a lucky ancestry hit.
new_env
export ORCH_DEPENDS_GATING=1
export ORCH_MAIN_REMOTE=none
E=$(tracker create --type epic --title "docs-release epic")
D=$(tracker create --type ticket --title "docs dep" --parent "$E" --role be-developer)
T=$(tracker create --type ticket --title "docs dependent" --parent "$E" --role be-developer)
tracker update "$T" depends_on "[$D]" >/dev/null
for s in "Ready for Development" "In Progress" "In Review" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    tracker transition "$D" "$s" --actor test --reason drive >/dev/null
done
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$T" "PILOT-44 AC1: dep in 'Docs' (probe=NONE) releases the dependent — Docs implies the merge fact (ABS-266)"
assert_not_contains "$out" "INTENT DEPENDS-WAIT ticket=$T" "PILOT-44 AC1: no depends-wait once the dep reaches 'Docs'"
# AC3-strict guard preserved: a 'depends-strict' dependent still waits at 'Docs'.
TS=$(tracker create --type ticket --title "strict-on-docs dependent" --parent "$E" --role be-developer --label depends-strict)
tracker update "$TS" depends_on "[$D]" >/dev/null
tracker transition "$TS" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT DEPENDS-WAIT ticket=$TS" "PILOT-44: 'depends-strict' still waits while the dep is only in 'Docs' (needs Done)"
export ORCH_DEPENDS_GATING=0
cleanup_env

# Multiple epic branches -> deterministic (lexicographic) pick + warning.
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$(mktemp -d /tmp/orchestrator-abs119b-XXXXXX)"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
E=$(tracker create --type epic --title "Twin epic")
T=$(tracker create --type ticket --title "twin child" --parent "$E" --role be-developer)
git -C "$TARGET" branch "epic/$E-aaa"
echo marker > "$TARGET/on-aaa.txt"
git -C "$TARGET" checkout -q "epic/$E-aaa"
git -C "$TARGET" -c user.email=t@t -c user.name=t add on-aaa.txt
git -C "$TARGET" -c user.email=t@t -c user.name=t commit -qm marker
git -C "$TARGET" checkout -q -
git -C "$TARGET" branch "epic/$E-zzz"
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
err=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1 >/dev/null)
TOTAL=$((TOTAL + 1))
if [ -f "$TARGET/tmp/$T-work/on-aaa.txt" ]; then
    echo -e "  ${GREEN}PASS${NC} multiple epic branches -> lexicographically first is picked"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} deterministic epic-branch pick failed"; FAIL=$((FAIL + 1))
fi
assert_contains "$err" "multiple epic branches" "multi-match logs a warning"
unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
rm -rf "$TARGET"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-120 token accounting — SPAWN-USAGE lines + cost report + model defaults${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "Cost epic")
T=$(tracker create --type ticket --title "Costly story" --parent "$E" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
STUB_USAGE=1 STUB_TOKENS_IN=1234 STUB_CACHE_READ=98765 STUB_CACHE_CREATE=4321 STUB_TOKENS_OUT=567 STUB_COST=0.42 \
    ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
usage_line=$(grep "SPAWN-USAGE" "$ORCH_STATE_DIR/run.log" | head -1)
# ABS-165: all five fields, incl. the cache_* fields where real input volume lives.
assert_contains "$usage_line" "tokens_in=1234 cache_read=98765 cache_create=4321 tokens_out=567 cost_usd=0.42" "spawn JSON usage fields (incl. cache) land in run.log"
assert_contains "$usage_line" "$T" "usage line names the ticket"
# ABS-165: run end emits a RUN-USAGE rollup, per ticket and per role, over the
# same run.log (purely mechanical awk) — the cache fields sum too.
runusage_ticket=$(grep "RUN-USAGE" "$ORCH_STATE_DIR/run.log" | grep "$T" | head -1)
assert_contains "$runusage_ticket" "spawns=" "RUN-USAGE rollup names the ticket with a spawn count"
assert_contains "$runusage_ticket" "cache_read=98765" "RUN-USAGE rollup sums the ticket's cache_read"
runusage_role=$(grep "RUN-USAGE" "$ORCH_STATE_DIR/run.log" | grep "be-developer" | head -1)
assert_contains "$runusage_role" "cache_create=4321" "RUN-USAGE rollup sums the role's cache_create"
# Crash -> the line still appears, with empty fields (graceful degradation).
C=$(tracker create --type ticket --title "Crashy story" --parent "$E" --role fe-developer)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1   # consume creation event
tracker transition "$C" "Ready for Development" --actor po --reason go >/dev/null
STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
crash_usage=$(grep "SPAWN-USAGE" "$ORCH_STATE_DIR/run.log" | grep "$C" | head -1)
assert_contains "$crash_usage" "tokens_in= cache_read= cache_create= tokens_out= cost_usd=" "crashed spawn degrades to empty usage fields"
# Report: per-seat, per-story and per-epic aggregation over the same run.log.
report=$(TRACKER_CMD="$TRACKER" bash "$REPO_ROOT/scripts/orchestrator-report.sh" "$ORCH_STATE_DIR/run.log" 2>/dev/null)
assert_contains "$report" "Per seat (role)" "report prints the per-seat section"
assert_contains "$report" "be-developer" "report aggregates the seat"
assert_contains "$report" "$T" "report aggregates the story"
assert_contains "$report" "$E" "report aggregates the epic (parent via adapter)"
report_notracker=$(env -u TRACKER_CMD bash "$REPO_ROOT/scripts/orchestrator-report.sh" "$ORCH_STATE_DIR/run.log" 2>/dev/null)
assert_contains "$report_notracker" "epic aggregation skipped" "report degrades gracefully without a tracker"
cleanup_env

# Right-sizing defaults: mechanical seats on sonnet, judgment seats on opus —
# in the HARNESS namespace (the seam's primary resolution, ABS-96). The live
# .claude/ is the generated governor artifact pinned at the release tag
# (ABS-92, test-harness-parity) and picks the change up at promotion.
for ns in "harness/claude/agents"; do
    for r in qas tech-writer rte; do
        assert_contains "$(grep '^model:' "$REPO_ROOT/$ns/$r.md")" "model: sonnet" "$ns/$r.md defaults to sonnet"
    done
    for r in system-architect po-agent; do
        assert_contains "$(grep '^model:' "$REPO_ROOT/$ns/$r.md")" "model: opus" "$ns/$r.md stays on opus"
    done
done

# Seam resolution: frontmatter sonnet reaches --model (via the operator's
# Sonnet-4.6 pin), and ORCH_MODEL still overrides the frontmatter.
new_env
mkdir -p "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/claude" <<'FAKECLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS_FILE:?}"
cat >/dev/null
echo '{"result":"ok","session_id":"11111111-2222-4333-8444-555566667777"}'
FAKECLAUDE
chmod +x "$TEST_DIR/bin/claude"
printf 'packet' > "$TEST_DIR/packet.txt"
export FAKE_ARGS_FILE="$TEST_DIR/args"
ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" qas DEMO-1 "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>&1 || true
assert_contains "$(cat "$FAKE_ARGS_FILE" 2>/dev/null)" "--model claude-sonnet-4-6" "qas frontmatter sonnet -> pinned sonnet-4-6 at the seam"
ORCH_MODEL="claude-opus-4-8" ORCH_CLAUDE_BIN="$TEST_DIR/bin/claude" bash "$REPO_ROOT/scripts/orchestrator-spawn-claude.sh" qas DEMO-1 "$TEST_DIR/packet.txt" < "$TEST_DIR/packet.txt" >/dev/null 2>&1 || true
assert_contains "$(cat "$FAKE_ARGS_FILE" 2>/dev/null)" "--model claude-opus-4-8" "ORCH_MODEL env overrides the frontmatter (precedence regression)"
unset FAKE_ARGS_FILE
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-135 packet from_status carries THIS ticket's status, never a leak${NC}"
# =============================================================================
# Befund 2 (run ABS-126): a Story packet carried from_status "Ready for Epic
# Acceptance" — an EPIC status the story never had. Root cause: live_spawn read
# the process-global $ev_from (the LAST parsed event) instead of the per-ticket
# `from` threaded down the dispatch chain. A spawn NOT immediately preceded by
# its own parse (reconcile sweep, cross-cycle) inherited a different ticket's
# status. Fix: thread `from` dispatch -> spawn_dispatch -> live_spawn.
# story_from_status <packet-file> <ticket> — the from_status value of <ticket>'s
# packet in a file of concatenated packets (empty string when the header carried
# an empty from_status; "<no-packet>" when the ticket was never spawned).
story_from_status() {
    awk -v t="$2" '
        /^ticket_id: /   { cur=$2 }
        /^from_status:/  { if (cur==t) { sub(/^from_status:[[:space:]]*/,""); print; found=1; exit } }
        END              { if (!found) print "<no-packet>" }
    ' "$1"
}

# --- (a) forward poll transition: packet from_status == the story's SOURCE -----
new_env
PKT="$TEST_DIR/packets_fwd.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
E=$(tracker create --type epic --title "ABS-135 fwd epic")
T=$(tracker create --type ticket --title "ABS-135 fwd story" --parent "$E" --role be-developer)
baseline
# Drive the story to In Progress and DRAIN, so the isolated event under test is
# the single In Progress -> In Review transition (source status = In Progress).
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason start >/dev/null
tracker events >/dev/null 2>&1
tracker transition "$T" "In Review" --actor be-developer --reason handoff >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_eq "$(story_from_status "$PKT" "$T")" "In Progress" "poll spawn: packet from_status == the story's real source status"
unset STUB_PACKET_COPY
cleanup_env

# --- (b) cross-cycle reconcile: story packet does NOT inherit the epic status --
# Cycle 1 poll parses an EPIC event whose source is "Ready for Epic Acceptance"
# (seeds the stale $ev_from). Cycle 2 reconcile re-derives the RESTING story at
# "Ready for Development" (no direction). Pre-fix: the story packet leaked the
# epic status. Post-fix: from_status is empty. This is the Befund-2 resume case.
new_env
PKT="$TEST_DIR/packets_recon.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
E=$(tracker create --type epic --title "ABS-135 leak epic")
T=$(tracker create --type ticket --title "ABS-135 leak story" --parent "$E" --role be-developer)
baseline
# Story rests at Ready for Development, drained so cycle-1 poll ignores it.
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
# Walk the epic through the LEGAL v3 pipeline (the mock rejects illegal jumps)
# so it truly reaches an epic-only status the story never has.
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" \
         "Architecture Review" "Stories In Flight" "Epic Integration" \
         "Ready for Epic Acceptance"; do
    tracker transition "$E" "$s" --actor agent --reason "walk to $s" >/dev/null
done
tracker events >/dev/null 2>&1
# The one unconsumed epic event: from "Ready for Epic Acceptance" -> sets the
# process-global $ev_from that the pre-fix live_spawn wrongly reused (Befund 2).
tracker transition "$E" "Epic Done" --actor agent --reason accept >/dev/null
ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_ON_STARTUP=0 \
    ORCH_RECONCILE_EVERY_N_CYCLES=2 orch --live >/dev/null 2>&1
recon_from="$(story_from_status "$PKT" "$T")"
assert_not_contains "$recon_from" "Ready for Epic Acceptance" "reconcile spawn: story packet does NOT inherit the epic's status (Befund 2)"
assert_eq "$recon_from" "" "reconcile spawn: resting story packet from_status is empty (no direction)"
unset STUB_PACKET_COPY
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-180 packet header carries the RESOLVED tracker_cmd + duty-note${NC}"
# =============================================================================
# Befund (watch-run 2026-07-09, ADR-A-0007): ABS-155 moved the agent-defs onto
# the $TRACKER_CMD variable-call form, but the seat allowlist matches the
# LITERAL adapter path, not the expanded form — so `"$TRACKER_CMD" get …` was
# permission-denied and all 6 po-agent intake seats fell back to the mock store
# (store-location split -> RESPAWN-LIMIT -> Needs PO Decision). Fix (lands the
# operator hotfix into Git): build_packet writes the RESOLVED $TRACKER_CMD
# literal path plus a duty-note into the packet header, so seats invoke the
# allowlisted literal and know the comment + exit transition are their duty.
new_env
PKT="$TEST_DIR/packets_trackercmd.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
E=$(tracker create --type epic --title "ABS-180 epic")
T=$(tracker create --type ticket --title "ABS-180 story" --parent "$E" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$PKT")" "tracker_cmd: $TRACKER" "packet header carries the resolved tracker_cmd literal path"
assert_contains "$(cat "$PKT")" "note: use tracker_cmd above" "packet header carries the tracker-cmd duty-note"
assert_contains "$(cat "$PKT")" "performing your exit transition are YOUR duty" "duty-note states comment + exit transition are the seat's duty"
# ABS-193: the duty-note also pins the PATH FORM. A restrictive main-checkout
# allowlist matches the literal adapter prefix (scripts/jira-tracker.sh or the
# absolute path) but NOT a ./-prefixed spelling — ./scripts/... is a different
# prefix and is denied under --permission-mode dontAsk (live-run ABS-181 drove
# the enrichment seat to RESPAWN-LIMIT). The fix is that the note instructs
# verbatim invocation with an explicit "do NOT prepend ./" so a seat that copies
# the packet literal never emits the denied form.
assert_contains "$(cat "$PKT")" "invoked VERBATIM as printed" "ABS-193: duty-note pins verbatim adapter invocation"
assert_contains "$(cat "$PKT")" "do NOT prepend ./" "ABS-193: duty-note forbids the ./-prefixed adapter form (allowlist path-prefix denial class)"
unset STUB_PACKET_COPY
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-382 build_packet policy injection — revision-pinned, cached, audited (§10/Case 5)${NC}"
# =============================================================================
# S5 (ABS-231 Phase 3 / §10/Case 5): with a `policies`-capable adapter, build_packet prepends
# the seat role's effective policy as a `=== POLICY (policy_rev: <hash>) ===`
# block BEFORE `=== TICKET ===`, folds policy_rev into the cache sig, and audits
# it per spawn in run.log. Default-safe: an adapter without `policies` (mock/jira)
# AND ORCH_POLICY_INJECT=off both yield a byte-identical legacy packet (no block).
CAP="$REPO_ROOT/tests/fixtures/policies-cap-tracker.sh"

# --- capable adapter, injection ON: POLICY block + rendered text + run.log audit
new_env
PSRC="$TEST_DIR/policy.txt"; printf 'Test policy: human-only merges.\n' > "$PSRC"
PKT="$TEST_DIR/pkt_on.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
T=$(tracker create --type ticket --title "ABS-382 injection on" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
TRACKER_CMD="$CAP" POLICY_SRC="$PSRC" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_contains "$(cat "$PKT")" "=== POLICY (policy_rev: " "ABS-382 AC1: packet carries the === POLICY (policy_rev: <hash>) === block"
assert_contains "$(cat "$PKT")" "Test policy: human-only merges" "ABS-382 AC1: rendered effective-policy text is injected"
# ordering: the POLICY block precedes === TICKET ===
assert_contains "$(awk '/=== POLICY/{p=1} /=== TICKET ===/{print (p?"POLICY-FIRST":"TICKET-FIRST"); exit}' "$PKT")" "POLICY-FIRST" "ABS-382 AC1: POLICY block precedes === TICKET ==="
# the trailing `policy_rev:` line is stripped from the body (hash rides in header)
assert_not_contains "$(grep -v '=== POLICY' "$PKT")" "policy_rev:" "ABS-382 AC1: trailing policy_rev line stripped from the injected body"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "POLICY-INJECT	$T	be-developer" "ABS-382 AC5: run.log records a per-spawn POLICY-INJECT audit line with policy_rev"
unset STUB_PACKET_COPY
cleanup_env

# --- capable adapter, ORCH_POLICY_INJECT=off: byte-identical legacy packet
new_env
PSRC="$TEST_DIR/policy.txt"; printf 'Test policy: human-only merges.\n' > "$PSRC"
PKT="$TEST_DIR/pkt_off.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
T=$(tracker create --type ticket --title "ABS-382 injection off" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
TRACKER_CMD="$CAP" POLICY_SRC="$PSRC" ORCH_POLICY_INJECT=off ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$PKT")" "=== POLICY" "ABS-382 AC3: ORCH_POLICY_INJECT=off yields no POLICY block on a capable adapter"
assert_contains "$(cat "$PKT")" "=== TICKET ===" "ABS-382 AC3: the legacy packet is still assembled"
unset STUB_PACKET_COPY
cleanup_env

# --- mock adapter (no policies op): byte-identical legacy packet, no POLICY block
new_env
PKT="$TEST_DIR/pkt_mock.txt"; export STUB_PACKET_COPY="$PKT"; : > "$PKT"
T=$(tracker create --type ticket --title "ABS-382 mock adapter" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$PKT")" "=== POLICY" "ABS-382 AC2: mock adapter (no policies op) yields no POLICY block"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "POLICY-INJECT	$T	be-developer	Ready for Development	policy_rev=none" "ABS-382 AC5: run.log audits policy_rev=none when the adapter lacks the policies op"
unset STUB_PACKET_COPY
cleanup_env

# --- §10/Case 5 / AC#5: packet cache-invalidation — policy change → different packet policy_rev
# Proves that mutating the policy content causes the packet POLICY block header to change,
# making a pre-change cached packet byte-distinct from a post-change packet (cache invalidated).
new_env
PSRC_V1="$TEST_DIR/policy_cache_v1.txt"; printf 'Policy v1: no force-push to main.\n' > "$PSRC_V1"
PKT_V1="$TEST_DIR/pkt_cache_v1.txt"; export STUB_PACKET_COPY="$PKT_V1"; : > "$PKT_V1"
T=$(tracker create --type ticket --title "ABS-384 §10/5 cache-invalidation-v1" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
TRACKER_CMD="$CAP" POLICY_SRC="$PSRC_V1" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
rev_cache_v1=$(grep '=== POLICY (policy_rev:' "$PKT_V1" | sed 's/.*policy_rev: //; s/).*//')
unset STUB_PACKET_COPY
cleanup_env

new_env
PSRC_V2="$TEST_DIR/policy_cache_v2.txt"; printf 'Policy v2: squash all commits + sign off.\n' > "$PSRC_V2"
PKT_V2="$TEST_DIR/pkt_cache_v2.txt"; export STUB_PACKET_COPY="$PKT_V2"; : > "$PKT_V2"
T=$(tracker create --type ticket --title "ABS-384 §10/5 cache-invalidation-v2" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
TRACKER_CMD="$CAP" POLICY_SRC="$PSRC_V2" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
rev_cache_v2=$(grep '=== POLICY (policy_rev:' "$PKT_V2" | sed 's/.*policy_rev: //; s/).*//')
unset STUB_PACKET_COPY
cleanup_env

# assert_eq is the harness helper (assert_true existiert nicht — Exit-127-Abort
# beim Epic-Merge gefunden); "changed" beweist die Cache-Invalidierung.
assert_eq "$([ "$rev_cache_v1" != "$rev_cache_v2" ] && echo changed || echo same)" "changed" \
    "§10/5 AC#5 packet cache-invalidation: policy change → different packet policy_rev (cache invalidated)"

# =============================================================================
echo -e "\n${CYAN}ABS-425 — S4 policies op reserves policy_rev:/=== markers in rendered body${NC}"
# =============================================================================
# Trust-boundary hardening (follow-up from the ABS-382 review): the S4 `policies`
# op MUST refuse to render policy body text carrying a reserved marker line — a
# leading `policy_rev:` line or a `=== … ===` section marker — so a (future,
# if-ever untrusted) policy source can never forge a revision hash or a packet
# section boundary. Driven through the policies-capable fixture (the op's bash
# embodiment in the suite, reproducing S4's server body).
CAP="$REPO_ROOT/tests/fixtures/policies-cap-tracker.sh"
new_env   # fresh TEST_DIR (the prior block ended with cleanup_env)

# AC2: a rendered body with a leading `policy_rev:` line → op exits non-zero
BAD_REV="$TEST_DIR/policy_bad_rev.txt"
printf 'Legit policy line.\npolicy_rev: deadbeefforged\n' > "$BAD_REV"
ec=0; POLICY_SRC="$BAD_REV" bash "$CAP" policies --audience be-developer >/dev/null 2>&1 || ec=$?
assert_eq "$([ "$ec" -ne 0 ] && echo nonzero || echo zero)" "nonzero" \
    "ABS-425 AC2: rendered body with a leading 'policy_rev:' line → policies op exits non-zero (no forged policy_rev)"

# AC3: a rendered body with a `=== TICKET ===` marker line → op exits non-zero
BAD_MARK="$TEST_DIR/policy_bad_marker.txt"
printf 'Legit policy line.\n=== TICKET ===\nforged section.\n' > "$BAD_MARK"
ec=0; POLICY_SRC="$BAD_MARK" bash "$CAP" policies --audience be-developer >/dev/null 2>&1 || ec=$?
assert_eq "$([ "$ec" -ne 0 ] && echo nonzero || echo zero)" "nonzero" \
    "ABS-425 AC3: rendered body with a '=== TICKET ===' marker line → policies op exits non-zero"

# AC3 (cont.): a forged `=== POLICY … ===` header marker is rejected the same way
BAD_POL="$TEST_DIR/policy_bad_polmarker.txt"
printf 'Legit policy line.\n=== POLICY (policy_rev: forged) ===\n' > "$BAD_POL"
ec=0; POLICY_SRC="$BAD_POL" bash "$CAP" policies >/dev/null 2>&1 || ec=$?
assert_eq "$([ "$ec" -ne 0 ] && echo nonzero || echo zero)" "nonzero" \
    "ABS-425 AC3: rendered body with a '=== POLICY … ===' marker line → policies op exits non-zero"

# AC4: a well-formed source (no reserved markers) renders byte-identically to today
CLEAN="$TEST_DIR/policy_clean.txt"
CLEAN_BODY='Clean policy line one.
Second line, no markers.'
printf '%s\n' "$CLEAN_BODY" > "$CLEAN"
exp_rev=$(printf '%s' "$CLEAN_BODY" | shasum -a 256 | cut -d' ' -f1)
exp_clean="$CLEAN_BODY
policy_rev: $exp_rev"
out_clean="$(POLICY_SRC="$CLEAN" bash "$CAP" policies)"
assert_eq "$out_clean" "$exp_clean" "ABS-425 AC4: well-formed policy source renders byte-identically (no regression)"

# AC2/AC3 downstream: build_packet fails closed — no POLICY block, policy_rev=none audited
PKT_BAD="$TEST_DIR/pkt_bad.txt"; export STUB_PACKET_COPY="$PKT_BAD"; : > "$PKT_BAD"
T=$(tracker create --type ticket --title "ABS-425 guarded source" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
TRACKER_CMD="$CAP" POLICY_SRC="$BAD_REV" ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
assert_not_contains "$(cat "$PKT_BAD")" "=== POLICY" "ABS-425: a guarded (violating) policy source injects NO POLICY block (fail-closed)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log")" "POLICY-INJECT	$T	be-developer	Ready for Development	policy_rev=none" "ABS-425: build_packet audits policy_rev=none for a guarded source (no forged hash)"
unset STUB_PACKET_COPY
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-163 — adapter --body-file / --reason-file (redirection-char safe)${NC}"
# =============================================================================
# A restrictive main-checkout seat (PO/architect/QAS/BSA — no bare-Bash grant)
# cannot post a comment/transition whose text contains the shell redirection
# characters < and >: Claude Code's Bash permission matcher parses them as
# redirection even inside quotes and denies the call. The seat-side fix is to
# keep those characters OFF the command line entirely — write the text to a file
# (via the Write tool, no shell) and hand the adapter a file PATH. These tests
# prove the adapter round-trips an angle-bracket body/reason verbatim through
# --body-file / --reason-file, with the inline forms still working unchanged.
new_env
BFDIR="$TEST_DIR/bodyfiles"; mkdir -p "$BFDIR"
# Body carries BOTH redirection characters, plus a pipe for good measure.
ANGLE='Decision: route A -> B when input <threshold> exceeds <max> | escalate otherwise.'
printf '%s\n' "$ANGLE" > "$BFDIR/comment-body.md"
printf '%s\n' "$ANGLE" > "$BFDIR/transition-reason.md"

T=$(tracker create --type ticket --title "ABS-163 body-file story" --role be-developer)

# comment --body-file: succeeds and stores the angle-bracket body verbatim.
cmt_out=$(tracker comment "$T" --kind decision --actor po-agent --body-file "$BFDIR/comment-body.md" 2>&1)
assert_contains "$cmt_out" "$T: comment added" "ABS-163: comment --body-file succeeds"
assert_contains "$(tracker get "$T" 2>&1)" "$ANGLE" "ABS-163: comment body with < and > round-trips verbatim"

# transition --reason-file: succeeds and records the angle-bracket reason.
tr_out=$(tracker transition "$T" "Ready for Development" --actor po-agent --reason-file "$BFDIR/transition-reason.md" 2>&1)
assert_contains "$tr_out" "$T: Backlog -> Ready for Development" "ABS-163: transition --reason-file succeeds"
assert_contains "$(tracker get "$T" 2>&1)" "$ANGLE" "ABS-163: transition reason with < and > round-trips verbatim"

# Inline forms are unchanged (backward compatible).
T2=$(tracker create --type ticket --title "ABS-163 inline story" --role be-developer)
assert_contains "$(tracker comment "$T2" --kind decision --actor po --body "plain inline body" 2>&1)" "$T2: comment added" "ABS-163: inline --body still works"

# Guards: mutual exclusivity and missing file both fail cleanly (exit != 0).
me_out=$(tracker comment "$T2" --kind decision --actor po --body x --body-file "$BFDIR/comment-body.md" 2>&1 || true)
assert_contains "$me_out" "mutually exclusive" "ABS-163: --body + --body-file is rejected"
mf_out=$(tracker comment "$T2" --kind decision --actor po --body-file "$BFDIR/does-not-exist.md" 2>&1 || true)
assert_contains "$mf_out" "not found" "ABS-163: missing --body-file is rejected"
rme_out=$(tracker transition "$T2" "Ready for Development" --actor po --reason x --reason-file "$BFDIR/transition-reason.md" 2>&1 || true)
assert_contains "$rme_out" "mutually exclusive" "ABS-163: --reason + --reason-file is rejected"
cleanup_env

echo -e "\n${CYAN}=== ABS-208 orchestrator-ready label propagation Epic -> children ===${NC}\n"
# =============================================================================
# A labelled epic's children must carry the start label so a mid-flight or
# pre-gate child is not dropped from the Backlog opt-in sweep after a restart
# (operator retro 2026-07-11). The runner propagates deterministically at two
# points: right after the issue-enrichment seat creates children (AC1) and on
# every reconcile sweep over a labelled epic (AC2). Parentless / unlabelled trees
# never gain a label (AC3). The mechanism uses only the shared adapter surface
# (get / children / update labels), so it works identically on the mock here and
# the jira adapter (byte-compatible children rows + labels frontmatter).

# --- AC1: enrichment-time propagation — children labelled right after the spawn
new_env
E=$(tracker create --type epic --title "abs208 AC1 enrich" --label orchestrator-ready)
# The children the enrichment seat produces (the stub cannot create tickets, so
# they are pre-seeded here); each starts WITHOUT the label.
C1=$(tracker create --type ticket --title "enriched child one" --parent "$E")
C2=$(tracker create --type ticket --title "enriched child two" --parent "$E")
baseline
for s in "PO Triage" "Grooming" "Enrichment"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$E role=issue-enrichment to=Enrichment" "AC1: issue-enrichment seat spawned on the labelled epic"
assert_contains "$out" "INTENT LABEL-PROPAGATE ticket=$C1" "AC1: child C1 label propagated immediately after enrichment"
assert_contains "$out" "INTENT LABEL-PROPAGATE ticket=$C2" "AC1: child C2 label propagated immediately after enrichment"
assert_contains "$(tracker get "$C1")" "orchestrator-ready" "AC1: child C1 carries the start label after the spawn"
assert_contains "$(tracker get "$C2")" "orchestrator-ready" "AC1: child C2 carries the start label after the spawn"
cleanup_env

# --- AC2: sweep reconcile — laggard non-Done children gain the label; Done ones
#         are left untouched (the restart / VPN-drop case).
new_env
E=$(tracker create --type epic --title "abs208 AC2 restart" --label orchestrator-ready)
A=$(tracker create --type ticket --title "mid-flight child A" --parent "$E")
B=$(tracker create --type ticket --title "mid-flight child B" --parent "$E")
D=$(tracker create --type ticket --title "already-done child" --parent "$E")
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done"; do
    tracker transition "$D" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$(tracker get "$A")" "orchestrator-ready" "AC2: non-Done child A gains the missing label on the sweep"
assert_contains "$(tracker get "$B")" "orchestrator-ready" "AC2: non-Done child B gains the missing label on the sweep"
assert_not_contains "$(tracker get "$D")" "orchestrator-ready" "AC2: Done child is left untouched"
cleanup_env

# --- AC2 idempotency: a labelled child is never re-written (no LABEL-PROPAGATE)
new_env
E=$(tracker create --type epic --title "abs208 AC2 idempotent" --label orchestrator-ready)
A=$(tracker create --type ticket --title "already labelled child" --parent "$E" --label orchestrator-ready)
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT LABEL-PROPAGATE ticket=$A" "AC2: an already-labelled child is not re-propagated (idempotent)"
cleanup_env

# --- AC3: no label materializes on a parentless ticket or an unlabelled tree ---
new_env
E=$(tracker create --type epic --title "abs208 AC3 labelled epic" --label orchestrator-ready)
C=$(tracker create --type ticket --title "child of labelled epic" --parent "$E")
P=$(tracker create --type ticket --title "parentless ticket")
E2=$(tracker create --type epic --title "abs208 AC3 unlabelled epic")
C2=$(tracker create --type ticket --title "child of unlabelled epic" --parent "$E2")
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$(tracker get "$P")" "orchestrator-ready" "AC3: parentless ticket never gains a label from nowhere"
assert_not_contains "$(tracker get "$C2")" "orchestrator-ready" "AC3: child of an unlabelled epic gains no label"
assert_contains "$(tracker get "$C")" "orchestrator-ready" "AC3 control: child of the labelled epic still gets the label"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== ABS-255 / ADR-A-0024 handoff commit verification ===${NC}"
# =============================================================================
# Consumer-feedback item 14: a seat claimed a commit that NO ref ever contained,
# and the next seat echoed the claim. The runner now verifies every hash a
# handoff names on its `commits:` line BEFORE it accepts the handoff — existence
# (git cat-file -e) + reachability (git for-each-ref --contains). A claim that
# does not hold is a MIS-REPORT: the declared transition is refused, a
# self-transition is undone, and the ticket bounces back to the seat.
#
# The gate runs git against $ORCH_STATE_ROOT, so these scenarios point it at a
# throwaway git repo (ORCH_TARGET_REPO) carrying all three cases:
#   GOOD   — a real, ref-reachable commit
#   ORPHAN — a real commit object that NO ref contains (git commit-tree; models
#            a detached-HEAD / discarded-branch commit — the Befund's ground truth)
#   FAKE   — a well-formed hash that simply does not exist (a fabricated claim)
ABS255_REPO="$(mktemp -d /tmp/abs255-repo-XXXXXX)"
git -C "$ABS255_REPO" init -q 2>/dev/null
git -C "$ABS255_REPO" config user.email "test@example.com"
git -C "$ABS255_REPO" config user.name "Test"
echo "seed" > "$ABS255_REPO/seed.txt"
git -C "$ABS255_REPO" add seed.txt
git -C "$ABS255_REPO" commit -qm "seed"
ABS255_GOOD="$(git -C "$ABS255_REPO" rev-parse HEAD)"
ABS255_ORPHAN="$(git -C "$ABS255_REPO" commit-tree 'HEAD^{tree}' -m "orphan (no ref contains me)")"
ABS255_FAKE="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

# --- a VERIFIED commit claim is accepted: the handoff proceeds normally --------
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_GOOD"; export STUB_HANDOFF_COMMITS
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Honest commit claim" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "a verified commit claim is accepted — the declared transition is applied"
assert_not_contains "$(tracker get "$T")" "HANDOFF-MISREPORT" "a real, ref-reachable commit is never a mis-report"
unset STUB_HANDOFF_COMMITS STUB_HANDOFF_TO
cleanup_env

# --- a FABRICATED hash is refused: no transition, marker comment, ticket rests --
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_FAKE"; export STUB_HANDOFF_COMMITS
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Fabricated hash" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF-MISREPORT ticket=$T" "a fabricated hash emits a HANDOFF-MISREPORT intent"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Ready for Development" "a mis-reported handoff is REFUSED — the declared transition is not applied"
dump="$(tracker get "$T")"
assert_contains "$dump" "HANDOFF-MISREPORT status=Ready for Development" "the mis-report is recorded with the greppable marker"
assert_contains "$dump" "$ABS255_FAKE" "the gate-results comment names the failing hash"
assert_contains "$dump" "does not exist in the repository" "the comment names WHICH check failed (existence)"
unset STUB_HANDOFF_COMMITS STUB_HANDOFF_TO
cleanup_env

# --- an UNREACHABLE commit is refused (the Befund: "kein Ref enthielt sie je") --
# The commit object EXISTS (cat-file -e passes) but no ref contains it — the
# exact failure git log -S proved in the reference incident. Existence alone is
# NOT enough; reachability is what closes the Befund.
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_ORPHAN"; export STUB_HANDOFF_COMMITS
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Orphaned commit" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Ready for Development" "a commit no ref contains is refused, even though the object exists"
assert_contains "$(tracker get "$T")" "NO ref contains it" "the comment names WHICH check failed (reachability)"
unset STUB_HANDOFF_COMMITS STUB_HANDOFF_TO
cleanup_env

# --- a SELF-TRANSITION on a mis-report is UNDONE (d.2) -------------------------
# The seat moves the ticket itself AND lies about the commit. The runner must not
# let it profit from the false claim: the ticket is transitioned BACK to the spawn
# status (actor = the seat role, so rework_count() counts it natively — AC3).
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_FAKE"; export STUB_HANDOFF_COMMITS
STUB_TRANSITION_TO="In Progress"; export STUB_TRANSITION_TO
T=$(tracker create --type ticket --title "Lying self-transitioner" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Ready for Development" "a mis-reporting seat's own transition is UNDONE (back to the spawn status)"
dump="$(tracker get "$T")"
assert_contains "$dump" "Transition: In Progress -> Ready for Development" "the back-transition is a real, auditable backward move"
assert_contains "$dump" "actor: be-developer" "the back-transition is attributed to the seat (so rework_count counts it — AC3)"
unset STUB_HANDOFF_COMMITS STUB_TRANSITION_TO
cleanup_env

# --- repeated mis-reports escalate to Needs PO Decision (AC3, bounded bounce) ---
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_FAKE"; export STUB_HANDOFF_COMMITS
T=$(tracker create --type ticket --title "Serial mis-reporter" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RESPAWN_LIMIT=2 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Ready for Development" "first mis-report rests (no escalation yet)"
out=$(ORCH_RESPAWN_LIMIT=2 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>&1)
assert_contains "$out" "INTENT RESPAWN-LIMIT ticket=$T" "k consecutive mis-reports emit a RESPAWN-LIMIT intent"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Needs PO Decision" "k consecutive mis-reports escalate to Needs PO Decision (existing counter, no new machinery)"
unset STUB_HANDOFF_COMMITS
cleanup_env

# --- no claim -> the gate is inert (fail-open; regression guard) ---------------
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "No commit claim" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "a handoff that claims NO commits is untouched by the gate"
assert_not_contains "$(tracker get "$T")" "HANDOFF-MISREPORT" "no claim, no verdict (fail-open)"
unset STUB_HANDOFF_TO
cleanup_env

# --- (f) prose claims a commit but names NO hash -> ADVISORY, never blocking ----
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_PROSE="committed the fix and pushed it"; export STUB_HANDOFF_PROSE
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Claim without hash" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "a hash-less commit claim is ACCEPTED (advisory only — the prose regex has a known false-positive class)"
dump="$(tracker get "$T")"
assert_contains "$dump" "HANDOFF-CLAIM-NOHASH" "a hash-less commit claim lands the non-blocking advisory"
assert_not_contains "$dump" "HANDOFF-MISREPORT" "the advisory is NOT a mis-report and does not count"
unset STUB_HANDOFF_PROSE STUB_HANDOFF_TO
cleanup_env

# --- kill-switch: ORCH_VERIFY_COMMITS=0 restores the pre-ABS-255 behaviour ------
new_env
export ORCH_TARGET_REPO="$ABS255_REPO"
STUB_HANDOFF_COMMITS="$ABS255_FAKE"; export STUB_HANDOFF_COMMITS
STUB_HANDOFF_TO="In Progress"; export STUB_HANDOFF_TO
T=$(tracker create --type ticket --title "Gate off" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_VERIFY_COMMITS=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "In Progress" "ORCH_VERIFY_COMMITS=0 accepts even a fabricated claim (legacy behaviour)"
assert_not_contains "$(tracker get "$T")" "HANDOFF-MISREPORT" "ORCH_VERIFY_COMMITS=0 disables the gate entirely"
unset STUB_HANDOFF_COMMITS STUB_HANDOFF_TO
cleanup_env
unset ORCH_TARGET_REPO
rm -rf "$ABS255_REPO"

# =============================================================================
# ABS-199 / ADR-A-0018 — cross-visit same-blocker loop-breaker + escalation budget
# =============================================================================
# The loop-breaker's decision logic (blocker_class / blocker_class_seat_count /
# crossvisit_guard / escalation_note_stall / escalation_note_progress /
# followup_budget_exhausted / join_budget_deadlock) is pure or file-backed, so
# this section SOURCES scripts/orchestrator.sh (main is source-guarded) and
# exercises the functions directly with a stubbed adapter — mirroring
# tests/test-station-guard.sh. Kept LAST so redefining tracker()/helpers cannot
# affect the integration scenarios above.
echo -e "\n${CYAN}=== ABS-199 cross-visit loop-breaker (ADR-A-0018) ===${NC}\n"
source "$ORCH" >/dev/null 2>&1
# ABS-310 D1: `scripts/orchestrator.sh` runs `set -euo pipefail` on source, which
# leaks `pipefail` ON into the parent harness for the REST of the suite —
# including every ABS-215 per-story include sourced below. Combined with any
# pipe-into-grep-q shape (D2) that leak turns a PIPESTATUS=141 (SIGPIPE) into
# a false FAIL and aborts the run before its tally. This block needs the sourced
# functions in the parent scope, so a `( … )` subshell is not available; restore
# the option explicitly instead. `pipefail` MUST be OFF for the remainder.
set +o pipefail

MODE=live
ABS199_SB="$(mktemp -d /tmp/abs199-XXXXXX)"
STUBCALLS="$ABS199_SB/calls"; : > "$STUBCALLS"
STUBDUMP=""
STUB_IN_BLOCKED=1   # ticket_still_in "Blocked" -> return 1 (NOT in Blocked) so the park transition fires

tracker() {
    case "$1" in
        get)        printf '%s' "$STUBDUMP" ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUBCALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUBCALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { case "$2" in Blocked) return "$STUB_IN_BLOCKED" ;; *) return 0 ;; esac; }

# fresh per-scenario state dir (isolates the blocker-/escalation- marker files)
abs199_reset_state() {
    export ORCH_STATE_DIR="$ABS199_SB/state-$1"
    export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
    mkdir -p "$ORCH_STATE_DIR"
    : > "$STUBCALLS"
}
# run a loop-breaker fn, capturing stdout (intent lines) AND its exit code.
# The `if` form keeps `set -e` from aborting when the fn returns non-zero.
abs199_run() { if ABS199_OUT="$("$@" 2>/dev/null)"; then ABS199_RC=0; else ABS199_RC=$?; fi; }

# --- (§a) blocker_class — mechanical taxonomy, precedence, safe default -------
echo -e "${CYAN}blocker_class taxonomy (§a)${NC}"
assert_eq "$(blocker_class 'permission denied writing .claude/settings.json')" "environment-denial" "permission-denial diagnostic -> environment-denial"
assert_eq "$(blocker_class '.claude write-protection: operation not permitted')" "environment-denial" "write-protection denial -> environment-denial"
assert_eq "$(blocker_class 'non-zero exit (exit=7); stderr: stub-spawn: forced failure')" "transient" "generic non-zero-exit crash -> transient (safe default kept)"
assert_eq "$(blocker_class 'clean exit (exit=0) but no parseable handoff')" "transient" "empty-handoff crash -> transient"
assert_eq "$(blocker_class 'rate limit exceeded, connection reset')" "transient" "rate-limit/network -> transient"
assert_eq "$(blocker_class '')" "transient" "unmatched/empty diagnostic -> transient (safe default)"
assert_eq "$(blocker_class 'rework: AC not met, tests failed')" "logic" "rework/test-fail bounce -> logic"
assert_eq "$(blocker_class 'permission denied AND non-zero exit exit=7')" "environment-denial" "precedence: environment-denial beats transient on overlap"
# PILOT-65 AC3: a turn-cap abort is its OWN class, not a generic crash/transient.
assert_eq "$(blocker_class 'spawn ended at subtype=error_max_turns, no handoff')" "turn-cap" "PILOT-65 AC3: error_max_turns -> turn-cap (own class, not crash)"
assert_eq "$(blocker_class 'seat hit the turn ceiling mid-work')" "turn-cap" "PILOT-65 AC3: turn-ceiling diagnostic -> turn-cap"
assert_eq "$(blocker_class 'permission denied AND error_max_turns')" "environment-denial" "PILOT-65 AC3: env-denial still beats turn-cap on overlap (precedence)"
assert_eq "$(blocker_class 'rework: AC not met AND error_max_turns')" "turn-cap" "PILOT-65 AC4: a cap abort is NOT counted as a functional/logic bounce (turn-cap beats logic)"

# --- PILOT-65 — calibrated per-seat turn caps (this block SOURCES orchestrator.sh
# above, so builtin_role_max_turns / the config vars are in scope). AC1: each cap =
# ceil_to_10(observed_peak x 1.5) so it sits ABOVE the observed max, not on the median.
echo -e "\n${CYAN}PILOT-65 — calibrated per-seat turn caps${NC}"
assert_eq "$(builtin_role_max_turns qas)" "180" "PILOT-65 AC1: qas cap 180 (1.5x observed max 119; old 80 sat below it)"
assert_eq "$(builtin_role_max_turns tech-writer)" "80" "PILOT-65 AC1: tech-writer cap 80 (was 50, below median 53)"
assert_eq "$(builtin_role_max_turns system-architect)" "60" "PILOT-65 AC1: system-architect cap 60 (was 40 = median)"
# AC2: the four formerly-capless seats now carry an EXPLICIT built-in (50) instead
# of silently falling to the global default 25 (medians 30-32, 6 aborts in Pilot 5).
for _r in ui-ux-design qas-design data-provisioning-eng security-engineer; do
    assert_eq "$(builtin_role_max_turns "$_r")" "50" "PILOT-65 AC2: $_r has an explicit cap (50), no silent fall to 25"
done
# Unmeasured seats keep their existing explicit values (not the silent-25 problem).
assert_eq "$(builtin_role_max_turns po-agent)" "40" "po-agent keeps its explicit built-in (40)"

# --- ABS-605 — station-aware salvage cap + RTE built-in-cap recalibration ------
# (this block SOURCES orchestrator.sh above, so builtin_role_max_turns /
# builtin_role_salvage_max_turns / salvage_max_turns are in scope).
echo -e "\n${CYAN}ABS-605 — RTE cap recalibration + station-aware salvage cap${NC}"
# Part 2: rte died at error_max_turns num_turns=61 against cap 60 -> ceil_to_10(61x1.5)=100.
assert_eq "$(builtin_role_max_turns rte)" "100" "ABS-605: rte built-in cap raised 60->100 (ceil_to_10 of observed peak 61 x1.5)"
# Part 1: the salvage cap resolves per-role. rte gets a station-specific built-in
# (its exit is a full suite), every other seat falls to the default 5.
export ORCH_SALVAGE_MAX_TURNS=5
assert_eq "$(builtin_role_salvage_max_turns rte)" "30" "ABS-605: rte has a station-specific salvage budget (30, full-suite exit)"
assert_eq "$(builtin_role_salvage_max_turns be-developer)" "" "ABS-605: an ordinary seat has no station-specific salvage budget"
assert_eq "$(salvage_max_turns rte)" "30" "ABS-605: rte salvage resolves to the station-aware 30, not the default 5"
assert_eq "$(salvage_max_turns be-developer)" "5" "ABS-605: an ordinary seat salvage resolves to the default 5"
assert_eq "$(salvage_max_turns qas)" "5" "ABS-605: a non-rte measured seat still uses the default salvage 5"
# per-seat env override beats the built-in and the default (ABS-156/565 pattern).
assert_eq "$(ORCH_SALVAGE_MAX_TURNS_RTE=42 salvage_max_turns rte)" "42" "ABS-605: ORCH_SALVAGE_MAX_TURNS_<ROLE> env beats the built-in per-role value"
assert_eq "$(ORCH_SALVAGE_MAX_TURNS_BE_DEVELOPER=9 salvage_max_turns be-developer)" "9" "ABS-605: ORCH_SALVAGE_MAX_TURNS_<ROLE> env beats the default for an ordinary seat"
unset ORCH_SALVAGE_MAX_TURNS
# AC2: a role with NO measured built-in (bsa) yields empty here and the spawn
# resolver falls to the EXPLICIT ORCH_MAX_TURNS_DEFAULT_ROLE (50), never the lean 25.
assert_eq "$(builtin_role_max_turns bsa)" "" "bsa has no measured built-in (spawn resolver uses the explicit per-role default)"
assert_eq "${ORCH_MAX_TURNS_DEFAULT_ROLE}" "50" "PILOT-65 AC2: per-role default is an explicit 50 (> lean 25), so no role silently caps at 25"

# --- AC1: same (env-denial, seat) on the 2nd visit -> park to Blocked, one NOTIFY
echo -e "\n${CYAN}AC1 — 2nd same-blocker visit auto-parks (no re-spawn, NOTIFY once)${NC}"
abs199_reset_state ac1
abs199_run crossvisit_guard ABS-x "Enrichment" "issue-enrichment" "Write tool denied; .claude write-protection"
assert_eq "$ABS199_RC" "1" "1st environment-denial: guard returns 1 (fall through to per-visit path, no park)"
assert_not_contains "$(cat "$STUBCALLS")" "TRANSITION ABS-x Blocked" "1st occurrence does NOT park"
assert_eq "$(blocker_class_seat_count ABS-x environment-denial issue-enrichment)" "1" "1st occurrence recorded one (class,seat) line"
# 2nd occurrence — SAME class+seat, a DIFFERENT visit-status (the cross-visit case)
abs199_run crossvisit_guard ABS-x "Needs PO Decision" "issue-enrichment" "Write tool denied again; permission denied"
assert_eq "$ABS199_RC" "0" "2nd same (class,seat): guard returns 0 (parked, caller suppresses re-spawn)"
assert_contains "$(cat "$STUBCALLS")" "TRANSITION ABS-x Blocked" "2nd occurrence parks the ticket in Blocked"
assert_contains "$ABS199_OUT" "INTENT CROSSVISIT-PARK ticket=ABS-x" "auto-park emits the CROSSVISIT-PARK intent"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "1" "auto-park emits exactly one operator NOTIFY"
# 3rd occurrence — still parks, but NOTIFY is deduped (§e)
abs199_run crossvisit_guard ABS-x "Enrichment" "issue-enrichment" "permission denied yet again"
assert_eq "$ABS199_RC" "0" "3rd occurrence still parks"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "0" "3rd occurrence does NOT re-notify (dedup key class:seat)"

# --- AC2: distinct blocker classes / seats never auto-park (no false positive)
echo -e "\n${CYAN}AC2 — distinct classes/seats stay on the per-visit path (no false-positive)${NC}"
abs199_reset_state ac2
abs199_run crossvisit_guard ABS-y "Enrichment" "issue-enrichment" "rate limit exceeded"      # transient
assert_eq "$ABS199_RC" "1" "transient failure -> no park (per-visit ABS-118/ABS-74 path)"
abs199_run crossvisit_guard ABS-y "Enrichment" "issue-enrichment" "permission denied"          # env-denial, 1st of THIS class
assert_eq "$ABS199_RC" "1" "a DIFFERENT class next (env-denial 1st) -> still no park"
assert_not_contains "$(cat "$STUBCALLS")" "TRANSITION ABS-y Blocked" "two distinct classes in a row never auto-park"
# same class but a DIFFERENT seat also must not accumulate together
abs199_reset_state ac2b
abs199_run crossvisit_guard ABS-z "Enrichment" "seat-A" "permission denied"
abs199_run crossvisit_guard ABS-z "Enrichment" "seat-B" "permission denied"
assert_eq "$ABS199_RC" "1" "same class at a DIFFERENT seat -> no park (keyed on class+seat)"
assert_not_contains "$(cat "$STUBCALLS")" "TRANSITION ABS-z Blocked" "distinct seats do not share a cross-visit count"

# --- AC3: escalation budget — N rounds without progress -> NOTIFY once + Blocked; reset on progress
echo -e "\n${CYAN}AC3 — escalation budget (N stall rounds -> park; reset on forward progress)${NC}"
abs199_reset_state ac3
export ORCH_ESCALATION_BUDGET=3
abs199_run escalation_note_stall ABS-b "Enrichment" "bsa"
assert_eq "$ABS199_RC" "1" "stall round 1: below budget, no park"
abs199_run escalation_note_stall ABS-b "Needs PO Decision" "po-agent"
assert_eq "$ABS199_RC" "1" "stall round 2 (a bounce, different status): still below budget"
assert_eq "$(escalation_count ABS-b)" "2" "counter accrues across visits/bounces"
abs199_run escalation_note_stall ABS-b "Enrichment" "bsa"
assert_eq "$ABS199_RC" "0" "stall round 3: budget exhausted -> park"
assert_contains "$(cat "$STUBCALLS")" "TRANSITION ABS-b Blocked" "budget exhaustion parks in Blocked"
assert_contains "$ABS199_OUT" "INTENT ESCALATION-BUDGET ticket=ABS-b" "budget park emits the ESCALATION-BUDGET intent"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "1" "budget park emits exactly one operator NOTIFY"
abs199_run escalation_note_stall ABS-b "Enrichment" "bsa"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "0" "further stalls do NOT re-notify (dedup key escalation-budget)"
# reset ONLY on real forward progress (strictly greater chain_index high-water)
escalation_note_progress ABS-b "In Progress"   # chain_index 3 > high-water 0
assert_eq "$(escalation_count ABS-b)" "0" "real forward progress resets the counter to 0"
if [ -f "$(blocker_file ABS-b)" ]; then bf=present; else bf=absent; fi
assert_eq "$bf" "absent" "forward progress also clears the blocker marker (ADR §d)"
# a bounce (lower index) after reaching a high-water must NOT reset
abs199_reset_state ac3b
escalation_note_progress ABS-c "Story Acceptance"   # index 9 -> high-water 9
abs199_run escalation_note_stall ABS-c "Ready for Development" "be-developer"
assert_eq "$(escalation_count ABS-c)" "1" "a stall after high-water still counts"
escalation_note_progress ABS-c "Design"             # index 1 < high-water 9 -> NOT progress
assert_eq "$(escalation_count ABS-c)" "1" "a backward bounce does NOT reset the counter"

# --- AC4: exhausted budget blocking a JOIN -> naming one-shot escalation (no silent wait)
echo -e "\n${CYAN}AC4 — budget dead-end names itself once at the JOIN gate (no silent wait)${NC}"
abs199_reset_state ac4
export ORCH_FOLLOWUP_BUDGET=5
epic_followup_spawned_count() { echo 5; }        # budget fully consumed
epic_has_unprocessed_followups() { return 0; }   # follow-ups still pending
assert_eq "$(followup_budget_exhausted EP-1 && echo yes || echo no)" "yes" "budget fully consumed -> exhausted=true"
STUBDUMP="status: Stories In Flight"   # no dead-lock marker yet
abs199_run join_check_epic EP-1
assert_contains "$ABS199_OUT" "INTENT JOIN-WAIT ticket=EP-1" "JOIN emits a WAIT intent"
assert_contains "$ABS199_OUT" "followup-budget-exhausted" "the JOIN-WAIT intent NAMES the exhausted-budget state"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "1" "the budget dead-end emits exactly one naming NOTIFY"
assert_contains "$(cat "$STUBCALLS")" "JOIN-BUDGET-DEADLOCK (orchestrator)" "a dedup marker comment is recorded"
# second sweep with the marker present -> silent (deduped), no re-notify
STUBDUMP="status: Stories In Flight
JOIN-BUDGET-DEADLOCK (orchestrator): already flagged"
abs199_run join_check_epic EP-1
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "0" "an already-flagged dead-end does NOT re-notify"
# a healthy epic (budget NOT exhausted) keeps the ordinary WAIT, no dead-end NOTIFY
abs199_reset_state ac4b
epic_followup_spawned_count() { echo 1; }        # budget available
abs199_run join_check_epic EP-2
assert_contains "$ABS199_OUT" "unprocessed-followups" "budget-available epic keeps the ordinary JOIN-WAIT"
assert_eq "$(echo "$ABS199_OUT" | grep -c 'INTENT NOTIFY')" "0" "budget-available JOIN-WAIT does not notify"

rm -rf "$ABS199_SB"

# =============================================================================
# ABS-210 — JOIN exemption for deliberately-parked optional/external children
# =============================================================================
# join_check_epic is pure/adapter-backed, so (like the ABS-199 block above) this
# section reuses the already-sourced orchestrator.sh and drives the function
# directly with a per-id stubbed adapter. AC1: a not-Done child carrying a
# declared JOIN-EXEMPT (triage) marker is excluded so the epic JOINs and the log
# NAMES the exemption. AC2: a not-Done child WITHOUT the marker keeps the gate
# waiting and is NAMED once (never a silent hang).
echo -e "\n${CYAN}=== ABS-210 JOIN exemption (parked optional/external children) ===${NC}\n"

ABS210_SB="$(mktemp -d /tmp/abs210-XXXXXX)"
ABS210_CALLS="$ABS210_SB/calls"; : > "$ABS210_CALLS"
export ORCH_STATE_DIR="$ABS210_SB/state"; mkdir -p "$ORCH_STATE_DIR"
export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"

# Per-id adapter stub: `get <id>` -> $ABS210_SB/dump-<id>; `children <epic>` ->
# $ABS210_SB/children (id<TAB>[status]<TAB>title rows).
tracker() {
    case "$1" in
        get)        cat "$ABS210_SB/dump-$2" 2>/dev/null || true ;;
        children)   cat "$ABS210_SB/children" 2>/dev/null || true ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$ABS210_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$ABS210_CALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return 0; }                 # epic rests in Stories In Flight
epic_has_unprocessed_followups() { return 1; }  # quiescent (no pending follow-ups)
abs210_run() { if ABS210_OUT="$("$@" 2>/dev/null)"; then ABS210_RC=0; else ABS210_RC=$?; fi; }

# A canonical parked-child dump carrying the declared marker in a decision comment.
abs210_exempt_dump() {
    printf '%s\n' \
        "status: Blocked" \
        "" \
        "## Comments" \
        "" \
        "### 2026-07-11T00:00:00Z | kind: decision | actor: tdm" \
        "" \
        "TDM triage: external-dependency, parked on purpose. $(join_exempt_marker): optional child, excluded from the epic JOIN gate (ABS-210)."
}

# --- unit: child_join_exempt only trusts the marker in a decision-comment BODY
echo -e "${CYAN}child_join_exempt — declared marker in a decision comment${NC}"
abs210_exempt_dump > "$ABS210_SB/dump-C1"
assert_eq "$(child_join_exempt C1 && echo yes || echo no)" "yes" "marker in a kind: decision body -> exempt"
printf '%s\n' "status: Blocked" "" "### 2026-07-11T00:00:00Z | kind: decision | actor: tdm" "" "TDM triage: genuine blocker, still pending." > "$ABS210_SB/dump-C2"
assert_eq "$(child_join_exempt C2 && echo yes || echo no)" "no" "no marker -> not exempt"
# anti quote-disarm: the marker quoted in a NON-decision comment must NOT exempt
printf '%s\n' "status: Blocked" "" "### 2026-07-11T00:00:00Z | kind: handoff | actor: qas" "" "FYI quoting $(join_exempt_marker) in passing." > "$ABS210_SB/dump-C3"
assert_eq "$(child_join_exempt C3 && echo yes || echo no)" "no" "marker only in a non-decision comment -> NOT exempt"

# --- AC1: N Done children + 1 parked child WITH the marker -> JOIN fires, named
echo -e "\n${CYAN}AC1 — parked child WITH exemption signal -> JOIN fires and NAMES the exemption${NC}"
: > "$ABS210_CALLS"
printf '%s\t%s\t%s\n' "S1" "[Done]" "done story" "X1" "[Blocked]" "parked optional child" > "$ABS210_SB/children"
abs210_exempt_dump > "$ABS210_SB/dump-X1"
abs210_run join_check_epic EP-A
assert_contains "$ABS210_OUT" "INTENT JOIN-EXEMPT ticket=EP-A" "the log emits a JOIN-EXEMPT intent"
assert_contains "$ABS210_OUT" "exempt-children:X1" "the JOIN-EXEMPT intent NAMES the excluded child"
assert_contains "$ABS210_OUT" "INTENT JOIN ticket=EP-A role=- to=Epic Integration" "JOIN fires past the parked child"
assert_contains "$(cat "$ABS210_CALLS")" "TRANSITION EP-A Epic Integration" "epic transitions to Epic Integration"

# --- AC2: parked child WITHOUT the marker -> JOIN keeps waiting, NAMES it once
echo -e "\n${CYAN}AC2 — parked child WITHOUT signal -> JOIN waits and NAMES the pending child (no silent hang)${NC}"
: > "$ABS210_CALLS"
printf '%s\t%s\t%s\n' "S2" "[Done]" "done story" "Y1" "[Blocked]" "genuine blocker" > "$ABS210_SB/children"
printf '%s\n' "status: Blocked" "" "### 2026-07-11T00:00:00Z | kind: decision | actor: tdm" "" "TDM triage: genuine external blocker, NOT optional." > "$ABS210_SB/dump-Y1"
abs210_run join_check_epic EP-B
assert_contains "$ABS210_OUT" "INTENT JOIN-WAIT ticket=EP-B" "a real blocker keeps the gate waiting"
assert_contains "$ABS210_OUT" "pending-children:Y1" "the JOIN-WAIT intent NAMES the still-pending child (no silent hang)"
assert_not_contains "$ABS210_OUT" "INTENT JOIN ticket=EP-B role=- to=Epic Integration" "JOIN does NOT fire past a genuine blocker"
assert_not_contains "$(cat "$ABS210_CALLS")" "TRANSITION EP-B Epic Integration" "epic is NOT integrated while a real blocker remains"

# --- AC2 (mixed): a Done + an exempt + a genuine blocker -> still WAITS on the blocker
echo -e "\n${CYAN}AC2 (mixed) — an exemption does NOT mask a co-existing genuine blocker${NC}"
: > "$ABS210_CALLS"
printf '%s\t%s\t%s\n' "S3" "[Done]" "done story" "X3" "[Blocked]" "parked optional" "Y3" "[Blocked]" "genuine blocker" > "$ABS210_SB/children"
abs210_exempt_dump > "$ABS210_SB/dump-X3"
printf '%s\n' "status: Blocked" "" "### 2026-07-11T00:00:00Z | kind: decision | actor: tdm" "" "genuine blocker." > "$ABS210_SB/dump-Y3"
abs210_run join_check_epic EP-C
assert_contains "$ABS210_OUT" "pending-children:Y3" "the un-exempted blocker Y3 is named as pending"
assert_not_contains "$ABS210_OUT" "INTENT JOIN ticket=EP-C role=- to=Epic Integration" "JOIN stays put while a genuine blocker co-exists with an exemption"

rm -rf "$ABS210_SB"

# =============================================================================
# ABS-183 — stable per-run instance identity (spec §4.1)
# =============================================================================
echo -e "\n${CYAN}ABS-183 instance-id — mint + persist + override + restart-reuse (spec §4.1)${NC}"

# AC: a fresh run mints a non-empty id and writes work/.orchestrator/instance-id;
#     the id is logged once at startup.
new_env
id_file="$ORCH_STATE_DIR/instance-id"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 >/dev/null)
assert_contains "$out" "instance-id:" "ABS-183: resolved instance id logged once at startup"
assert_contains "$out" "source=minted" "ABS-183: fresh run reports source=minted"
if [ -s "$id_file" ]; then fstate=written; else fstate=missing; fi
assert_eq "$fstate" "written" "ABS-183: fresh run writes non-empty instance-id file"
minted="$(cat "$id_file")"
if [ -n "$minted" ]; then nonempty=yes; else nonempty=no; fi
assert_eq "$nonempty" "yes" "ABS-183: minted id is non-empty"

# AC: the id is stable for the lifetime of a run + DoR restart-reuse invariant —
#     a second run in the same checkout REUSES the persisted id verbatim (never
#     re-mints), so the runner recognizes its own pre-restart claims (no self-yield).
out2=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 >/dev/null)
reused="$(cat "$id_file")"
assert_eq "$reused" "$minted" "ABS-183: restart reuses persisted id verbatim (no re-mint)"
assert_contains "$out2" "source=reused" "ABS-183: restart reports source=reused"
assert_contains "$out2" "instance-id: $minted" "ABS-183: restart logs the pre-restart id"
cleanup_env

# AC: two runners on two machines produce different ids (random suffix).
new_env
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
id_a="$(cat "$ORCH_STATE_DIR/instance-id")"
cleanup_env
new_env
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1
id_b="$(cat "$ORCH_STATE_DIR/instance-id")"
if [ "$id_a" != "$id_b" ]; then idcmp=different; else idcmp=same; fi
assert_eq "$idcmp" "different" "ABS-183: two fresh runners mint different ids"
cleanup_env

# AC: an operator-set ORCH_INSTANCE_ID is used verbatim and not overwritten
#     (override skips minting — no persisted file is written over).
new_env
override="operator-fixed-id-123"
out3=$(ORCH_INSTANCE_ID="$override" ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1 >/dev/null)
assert_contains "$out3" "instance-id: $override" "ABS-183: operator override used verbatim"
assert_contains "$out3" "source=override" "ABS-183: override reports source=override"
if [ -e "$ORCH_STATE_DIR/instance-id" ]; then ostate=written; else ostate=absent; fi
assert_eq "$ostate" "absent" "ABS-183: override skips minting (no file written)"
cleanup_env

# =============================================================================
# Per-story test includes (ABS-215) — conflict-magnet fix
# -----------------------------------------------------------------------------
# NEW story tests must NOT be appended to the end of this monolith (that
# append-at-end spot is the recurring epic-integration merge-conflict magnet,
# no-hand-resolve #EXPORT_CRITICAL). Instead, drop a self-contained
# `tests/orchestrator.d/<TICKET>-<slug>.sh` file. Each file is `source`d into
# THIS shell just before the results tally, so it shares the whole harness:
# the assert_* helpers, the orch/new_env/cleanup_env functions, the
# PASS/FAIL/TOTAL counters, and every exported env var set at the top.
# Two concurrent stories add two different files → zero shared-file conflict.
# See docs/sop/TEST_SUITE_LAYOUT.md.
# =============================================================================
# Derive the tests dir from THIS file's own path, not the shared $SCRIPT_DIR —
# some helper sourced mid-suite reassigns SCRIPT_DIR (it points at scripts/ by
# the time we get here), so relying on it would look in the wrong directory.
# Use $_shard_self (captured at top-level BASH_SOURCE) rather than BASH_SOURCE
# here: under TEST_JOBS>1 this block runs inside a `source <(...)` slice where
# BASH_SOURCE[0] would resolve to the process-substitution fd, not this file.
_ORCH_TEST_D="$(cd "$(dirname "${_shard_self:-${BASH_SOURCE[0]}}")/.." && pwd)/orchestrator.d"
# ABS-370: several late body unit-blocks (ABS-199 line ~4638, ABS-210 line ~4777)
# override the SHARED `tracker`/`ticket_still_in`/`epic_has_unprocessed_followups`
# shell functions with local stubs — and bind them to temp dirs they later
# `rm -rf`. Those stubs must NOT leak into the story includes, which assume the
# canonical harness `tracker` (line ~220) and drive the real predicates via the
# `orch` subprocess. Restore the canonical function surface before the loop so
# an include never lands on a torn-down abs210/abs199 stub (a false-green source).
tracker() { bash "$TRACKER" "$@"; }
unset -f ticket_still_in epic_has_unprocessed_followups 2>/dev/null || true
# PILOT-50: staged runner sets SUITE_SKIP_STORY_INCLUDES=1 for the `orch-core`
# stage (scenario blocks only). The ~48 includes then run as the separate,
# parallel `stories` stage (SUITE_INCLUDE_ONLY, above), so no single gate call
# carries the whole ~7-min serial include loop. Unset => full inline loop (default).
# SUITE_* (not ORCH_*) so the ABS-286 top-of-file env scrub does not wipe it; the
# guard is inside the sharded body, so shard children inherit the flag correctly.
if [ -z "${SUITE_SKIP_STORY_INCLUDES:-}" ] && [ -d "$_ORCH_TEST_D" ]; then
    for _story_test in "$_ORCH_TEST_D"/*.sh; do
        [ -e "$_story_test" ] || continue   # tolerate an empty directory
        echo -e "\n${CYAN}=== Story tests: $(basename "$_story_test") ===${NC}"
        # ABS-370: isolate each include so one file's abort under `set -e` cannot
        # kill the loop and silently drop the rest. `|| true` keeps the parent's
        # errexit from acting on the wrapper's non-zero (abort) return — the abort
        # is already counted as a failure inside _run_d_include.
        _run_d_include "$_story_test" || true
    done
fi

#@SHARD-BODY-END@
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
