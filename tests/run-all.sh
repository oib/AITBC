#!/usr/bin/env bash
# =============================================================================
# Parallel test runner (test-runtime-diet)
# -----------------------------------------------------------------------------
# Runs the independent `tests/tooling/test-*.sh` files concurrently. Each file is
# already self-contained (its own `mktemp -d` state, no fixed paths/ports), so
# they parallelise cleanly. Exit codes are aggregated; a non-zero from ANY file
# fails the run, and every failing file's full output is reprinted at the end so
# nothing gets lost in the interleave.
#
#   TEST_JOBS   parallelism (default 4). TEST_JOBS=1 => strictly serial, in the
#               same lexical order as `tests/tooling/test-*.sh`, i.e. deterministic.
#
# Usage:
#   bash tests/run-all.sh                 # every tests/tooling/test-*.sh
#   bash tests/run-all.sh a.sh b.sh ...   # only the named test files
#
# NOTE: this is the developer/CI fast path. The QAS gate still runs the full
# suite (no file selection) — see tests/scoped-tests.sh header.
# =============================================================================
set -uo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"
# PILOT-60: portable per-suite watchdog timeout (bash-native; holds on stock
# macOS with no timeout(1)/gtimeout). A wedged suite is a NAMED fail, not a hang.
# shellcheck source=../scripts/lib/run-with-timeout.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/lib/run-with-timeout.sh"

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOBS="${TEST_JOBS:-4}"
case "$JOBS" in ''|*[!0-9]*) JOBS=4 ;; esac
[ "$JOBS" -lt 1 ] && JOBS=1

# Per-suite wall-clock budget (PILOT-60): a suite that overruns is killed (whole
# tree) and reported as a named FAIL (exit 124), never an unbounded hang.
# Generous enough for the ~8-min tentpole; override with RUN_ALL_SUITE_TIMEOUT.
SUITE_TIMEOUT="${RUN_ALL_SUITE_TIMEOUT:-900}"
case "$SUITE_TIMEOUT" in ''|*[!0-9]*) SUITE_TIMEOUT=900 ;; esac

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Resolve the list of test files (args = explicit selection, else all).
FILES=()
if [ "$#" -gt 0 ]; then
    for a in "$@"; do
        case "$a" in
            /*) f="$a" ;;
            tests/*) f="$TESTS_DIR/../$a" ;;
            *) f="$TESTS_DIR/tooling/$a" ;;
        esac
        [ -f "$f" ] && FILES+=("$f") || echo -e "${RED}skip (not found):${NC} $a" >&2
    done
else
    for f in "$TESTS_DIR"/tooling/test-*.sh; do FILES+=("$f"); done
fi

[ "${#FILES[@]}" -eq 0 ] && { echo "no test files to run"; exit 0; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/run-all-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo -e "${CYAN}=== run-all: ${#FILES[@]} files, TEST_JOBS=$JOBS ===${NC}"

# Runner for a single file: isolate TMPDIR, capture output + status.
run_one() {
    local file="$1" work="$2" inner="$3" private_tmp="${4:-1}"
    local base; base="$(basename "$file")"
    local out="$work/$base.out" rc="$work/$base.rc"
    # PILOT-60: every suite runs under the per-suite watchdog budget. run_with_timeout
    # returns 124 on overrun (tree-killed, no survivor); the aggregator names it.
    if [ "$private_tmp" = "1" ]; then
        # Per-file isolated TMPDIR (parallel phase-2 files must not collide).
        local td; td="$(mktemp -d "$work/t-XXXXXX")"
        TMPDIR="$td" TEST_JOBS="$inner" run_with_timeout "$SUITE_TIMEOUT" bash "$file" >"$out" 2>&1
        echo "$?" >"$rc"
        rm -rf "$td"
    else
        # Inherit ambient (short) TMPDIR. The self-sharding orchestrator suite
        # builds deep nested state dirs; a long TMPDIR prefix can blow past the
        # ~104-char UNIX-socket path limit in its watchdog tests. It runs alone
        # in phase 1, so it needs no private TMPDIR anyway.
        TEST_JOBS="$inner" run_with_timeout "$SUITE_TIMEOUT" bash "$file" >"$out" 2>&1
        echo "$?" >"$rc"
    fi
}
export -f run_one run_with_timeout _rwt_kill_tree
export SUITE_TIMEOUT

# Two phases, so peak process count never exceeds ~$JOBS:
#   Phase 1: the tentpole test-orchestrator.sh (~460s serial) runs ALONE with
#            its own internal shard parallelism ($JOBS shards). Sharing the box
#            with sibling files here starves its watchdog/timing tests, so it
#            gets the machine to itself.
#   Phase 2: every other file — each a single fast process — fans out via
#            xargs -P $JOBS, pinned to TEST_JOBS=1 (they don't self-shard).
TENTPOLE=""
POOL=()
for f in "${FILES[@]}"; do
    if [ "$(basename "$f")" = "test-orchestrator.sh" ]; then TENTPOLE="$f"; else POOL+=("$f"); fi
done

if [ -n "$TENTPOLE" ]; then
    echo -e "${CYAN}--- phase 1: test-orchestrator.sh ($JOBS shards) ---${NC}"
    run_one "$TENTPOLE" "$WORK" "$JOBS" 0
fi

if [ "${#POOL[@]}" -gt 0 ]; then
    echo -e "${CYAN}--- phase 2: ${#POOL[@]} files (TEST_JOBS x1 each) ---${NC}"
    printf '%s\0' "${POOL[@]}" \
        | xargs -0 -P "$JOBS" -I {} bash -c 'run_one "$1" "$2" 1' _ {} "$WORK"
fi

# Aggregate.
FAILED=()
total_files=0
for file in "${FILES[@]}"; do
    total_files=$((total_files + 1))
    base="$(basename "$file")"
    rc="$(cat "$WORK/$base.rc" 2>/dev/null || echo 1)"
    if [ "$rc" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $base"
    elif [ "$rc" = "124" ]; then
        echo -e "  ${RED}FAIL${NC} $base (TIMED OUT — exceeded ${SUITE_TIMEOUT}s budget)"
        FAILED+=("$base")
    else
        echo -e "  ${RED}FAIL${NC} $base (exit $rc)"
        FAILED+=("$base")
    fi
done

if [ "${#FAILED[@]}" -gt 0 ]; then
    echo -e "\n${RED}=== ${#FAILED[@]}/$total_files file(s) FAILED — full output below ===${NC}"
    for base in "${FAILED[@]}"; do
        echo -e "\n${CYAN}----- $base -----${NC}"
        cat "$WORK/$base.out"
    done
    echo -e "\n${RED}FAILED: ${FAILED[*]}${NC}"
    exit 1
fi

echo -e "\n${GREEN}=== ALL $total_files FILES PASSED ===${NC}"
exit 0
