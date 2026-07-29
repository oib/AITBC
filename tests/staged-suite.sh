#!/usr/bin/env bash
# =============================================================================
# Staged full-suite runner with a HEAD-bound completeness ledger (PILOT-50)
# -----------------------------------------------------------------------------
# WHY: a gate seat (rte/qas) cannot run the whole suite in one tool call — a
# single Bash-tool invocation is capped at 10 minutes, but the full suite takes
# ~15. The tentpole `test-orchestrator.sh` alone is ~642s at its proven-safe
# parallelism (TEST_JOBS=4), already over the cap, dominated by a ~428s SERIAL
# `tests/orchestrator.d/*.sh` include loop. Its scenario blocks cannot be
# re-partitioned finer without false reds (blocks share hidden state; TEST_JOBS=8
# aborts a shard), so we split at the one SAFE seam instead:
#
#   Stage `orch-core` : the scenario blocks only (SUITE_SKIP_STORY_INCLUDES=1).
#   Stage `stories`   : the ~48 orchestrator.d includes, fanned out
#                       one-process-per-file in parallel (SUITE_INCLUDE_ONLY).
#   Stage `pool`      : every OTHER tests/test-*.sh, via run-all.sh (parallel).
#
# The partition is fixed BY THIS SCRIPT — a seat never chooses which files run,
# so file-selection cannot be used to make a red suite look green (the integrity
# property from the run-all.sh header is preserved). orch-core ∪ stories = the
# whole tentpole exactly (no overlap, no gap); pool covers everything else.
#
# COMPLETENESS LEDGER: each stage appends `<HEAD-sha> <stage> <pass|fail> ...` to
# a scratch ledger. `--verify` accepts ONLY when EVERY stage in the plan has a
# `pass` record at the CURRENT HEAD on a CLEAN tree. A subset can never pass the
# gate (missing/failed/stale stage => non-zero); any new commit invalidates the
# ledger by construction (sha-keyed). Same mechanic the staged pre-release-check
# proposal (work/improvement-proposals/2026-07-24-staged-pre-release-check-resume.md)
# asks for — one helper shape, not two.
#
# Usage:
#   bash tests/staged-suite.sh --list            # print the stage plan
#   bash tests/staged-suite.sh --stage <id>      # run ONE stage, record result
#   bash tests/staged-suite.sh --all             # run every stage in sequence
#   bash tests/staged-suite.sh --verify          # GATE: all stages green @ HEAD?
#
#   TEST_JOBS / -j N   parallelism forwarded to each stage (default 4).
#   SUITE_LEDGER       ledger path (default work/.suite-stage-ledger).
# =============================================================================
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
JOBS="${TEST_JOBS:-4}"
case "$JOBS" in ''|*[!0-9]*) JOBS=4 ;; esac
[ "$JOBS" -lt 1 ] && JOBS=1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

LEDGER="${SUITE_LEDGER:-$REPO_ROOT/work/.suite-stage-ledger}"

# --- Stage plan (SCRIPT-determined; a seat cannot alter which files run) ------
# SUITE_SELFTEST=1 swaps in trivial no-op stages so the ledger/verify integrity
# logic can be exercised deterministically in milliseconds (see test-staged-suite.sh).
if [ -n "${SUITE_SELFTEST:-}" ]; then
    STAGES=(alpha beta gamma)
else
    STAGES=(orch-core stories pool)
fi

stage_desc() {
    case "$1" in
        orch-core) echo "test-orchestrator.sh scenario blocks (no story includes), TEST_JOBS=$JOBS" ;;
        stories)   echo "tests/orchestrator.d/*.sh includes, fanned out one-process-per-file (-P$JOBS)" ;;
        pool)      echo "every other tests/test-*.sh, via run-all.sh (-P$JOBS)" ;;
        alpha|beta|gamma) echo "selftest no-op stage" ;;
        *)         echo "unknown stage" ;;
    esac
}

is_stage() { local s; for s in "${STAGES[@]}"; do [ "$s" = "$1" ] && return 0; done; return 1; }

head_sha() { git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "NO-HEAD"; }
tree_dirty() { [ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]; }

# --- Stage runners ------------------------------------------------------------
run_orch_core() {
    env -u ORCH_STATE_DIR -u ORCH_TARGET_REPO \
        SUITE_SKIP_STORY_INCLUDES=1 TEST_JOBS="$JOBS" \
        bash "$TESTS_DIR/test-orchestrator.sh"
}

run_stories() {
    local dir="$TESTS_DIR/orchestrator.d"
    [ -d "$dir" ] || { echo "no orchestrator.d dir"; return 0; }
    local files=() f
    for f in "$dir"/*.sh; do [ -e "$f" ] && files+=("$(basename "$f")"); done
    [ "${#files[@]}" -eq 0 ] && { echo "no story includes"; return 0; }
    local work; work="$(mktemp -d "${TMPDIR:-/tmp}/stories-XXXXXX")"
    # One process per include (harness reloads, ~1s; SUITE_INCLUDE_ONLY runs just
    # that file and exits), fanned out -P$JOBS. Each writes its rc; we aggregate.
    printf '%s\0' "${files[@]}" | xargs -0 -P "$JOBS" -I {} bash -c '
        f="$1"; work="$2"; tests_dir="$3"
        td="$(mktemp -d "$work/t-XXXXXX")"
        env -u ORCH_STATE_DIR -u ORCH_TARGET_REPO \
            SUITE_INCLUDE_ONLY="$f" TMPDIR="$td" \
            bash "$tests_dir/test-orchestrator.sh" >"$work/$f.out" 2>&1
        echo "$?" >"$work/$f.rc"
        rm -rf "$td"
    ' _ {} "$work" "$TESTS_DIR"
    local failed=() f2 rc
    for f2 in "${files[@]}"; do
        rc="$(cat "$work/$f2.rc" 2>/dev/null || echo 1)"
        if [ "$rc" = "0" ]; then echo -e "  ${GREEN}PASS${NC} $f2"
        else echo -e "  ${RED}FAIL${NC} $f2 (exit $rc)"; failed+=("$f2"); fi
    done
    if [ "${#failed[@]}" -gt 0 ]; then
        echo -e "\n${RED}=== ${#failed[@]} include(s) FAILED — output below ===${NC}"
        for f2 in "${failed[@]}"; do echo -e "\n${CYAN}--- $f2 ---${NC}"; cat "$work/$f2.out"; done
        rm -rf "$work"; return 1
    fi
    echo -e "\n${GREEN}=== all ${#files[@]} story includes PASSED ===${NC}"
    rm -rf "$work"; return 0
}

run_pool() {
    local pool=() f
    for f in "$TESTS_DIR"/test-*.sh; do
        [ "$(basename "$f")" = "test-orchestrator.sh" ] && continue  # covered by orch-core + stories
        pool+=("$(basename "$f")")
    done
    TEST_JOBS="$JOBS" bash "$TESTS_DIR/run-all.sh" "${pool[@]}"
}

run_stage() {
    local id="$1"
    if [ -n "${SUITE_SELFTEST:-}" ]; then
        case ",${SUITE_SELFTEST_FAIL:-}," in *",$id,"*) return 1 ;; *) return 0 ;; esac
    fi
    case "$id" in
        orch-core) run_orch_core ;;
        stories)   run_stories ;;
        pool)      run_pool ;;
        *) echo "unknown stage: $id" >&2; return 2 ;;
    esac
}

record_result() {
    local id="$1" verdict="$2"
    mkdir -p "$(dirname "$LEDGER")"
    printf '%s %s %s %s %s\n' "$(head_sha)" "$id" "$verdict" "$(date +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LEDGER"
}

# Latest verdict for <stage> at <sha> in the ledger, or empty if none.
ledger_verdict() {
    local sha="$1" id="$2"
    [ -f "$LEDGER" ] || { echo ""; return; }
    awk -v s="$sha" -v st="$id" '$1==s && $2==st {v=$3} END{print v}' "$LEDGER"
}

do_stage() {
    local id="$1"
    is_stage "$id" || { echo "not a stage: $id (plan: ${STAGES[*]})" >&2; exit 2; }
    echo -e "${CYAN}=== stage: $id — $(stage_desc "$id") ===${NC}"
    local start; start=$(date +%s)
    if run_stage "$id"; then
        local el=$(( $(date +%s) - start ))
        record_result "$id" pass
        echo -e "${GREEN}stage $id PASSED${NC} (${el}s) — recorded at HEAD $(head_sha | cut -c1-12)"
        return 0
    else
        local rc=$? el=$(( $(date +%s) - start ))
        record_result "$id" fail
        echo -e "${RED}stage $id FAILED${NC} (rc=$rc, ${el}s) — recorded at HEAD $(head_sha | cut -c1-12)"
        return 1
    fi
}

do_all() {
    local id rc=0
    for id in "${STAGES[@]}"; do do_stage "$id" || rc=1; done
    echo
    do_verify || rc=1
    return "$rc"
}

do_list() {
    echo -e "${CYAN}Stage plan (HEAD $(head_sha | cut -c1-12)) — partition is fixed by this script:${NC}"
    local id; for id in "${STAGES[@]}"; do printf '  %-10s %s\n' "$id" "$(stage_desc "$id")"; done
    echo "Ledger: $LEDGER"
}

do_verify() {
    local sha; sha="$(head_sha)"
    echo -e "${CYAN}=== verify: all stages green at HEAD $(echo "$sha" | cut -c1-12)? ===${NC}"
    if [ -z "${SUITE_SELFTEST:-}" ] && tree_dirty; then
        echo -e "${RED}GATE RED${NC}: working tree is DIRTY — the completeness gate must run on a"
        echo "committed state (the ledger keys on HEAD only). Commit or clean, then re-run stages."
        return 1
    fi
    local id v missing=() failed=()
    for id in "${STAGES[@]}"; do
        v="$(ledger_verdict "$sha" "$id")"
        case "$v" in
            pass) echo -e "  ${GREEN}pass${NC}  $id" ;;
            fail) echo -e "  ${RED}fail${NC}  $id"; failed+=("$id") ;;
            *)    echo -e "  ${YELLOW}----${NC}  $id (no result at this HEAD)"; missing+=("$id") ;;
        esac
    done
    if [ "${#missing[@]}" -gt 0 ] || [ "${#failed[@]}" -gt 0 ]; then
        echo -e "${RED}GATE RED${NC}: suite is NOT proven green at this HEAD."
        [ "${#missing[@]}" -gt 0 ] && echo "  missing stages: ${missing[*]}  (run: staged-suite.sh --stage <id>)"
        [ "${#failed[@]}"  -gt 0 ] && echo "  failed stages:  ${failed[*]}"
        return 1
    fi
    echo -e "${GREEN}GATE GREEN${NC}: all ${#STAGES[@]} stages passed at this HEAD."
    return 0
}

# --- CLI ---------------------------------------------------------------------
CMD=""; ARG=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --list) CMD=list ;;
        --stage) CMD=stage; ARG="${2:-}"; shift ;;
        --all) CMD=all ;;
        --verify) CMD=verify ;;
        -j) JOBS="${2:-4}"; shift ;;
        -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

case "${CMD:-all}" in
    list)   do_list ;;
    stage)  do_stage "$ARG" ;;
    all)    do_all ;;
    verify) do_verify ;;
esac
