#!/usr/bin/env bash
# =============================================================================
# Changed-scope test selection (test-runtime-diet)
# -----------------------------------------------------------------------------
# Runs ONLY the tests affected by the current change set, plus a small mandatory
# smoke, so an iterating developer/seat gets fast feedback instead of the full
# ~20-minute suite on every edit.
#
#   1. Collect changed files (default: `git diff --name-only origin/main...HEAD`
#      plus uncommitted working-tree + staged changes). Override by passing an
#      explicit file list as arguments.
#   2. Map each file to affected test files via tests/test-scope-map.txt.
#   3. Run the union of matched tests + the mandatory smoke, via run-all.sh.
#
# FAIL-OPEN: any changed path that matches NO glob in the scope map forces the
# FULL suite. We never silently test less than the change demands.
#
# >>> The FULL suite is still MANDATORY at the QAS gate. This script is a fast
# >>> inner-loop tool ONLY — it is NOT a substitute for the pre-merge full run.
# >>> Run the full suite with:  bash tests/run-all.sh   (or per-file directly).
#
#   TEST_JOBS   forwarded to run-all.sh (default 4).
#   BASE_REF    diff base (default: origin/main).
# =============================================================================
set -uo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
MAP="$TESTS_DIR/test-scope-map.txt"
BASE_REF="${BASE_REF:-origin/main}"

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

# Mandatory smoke: fast, foundational suites that touch the shared plumbing every
# change rides on. Always run, regardless of scope.
SMOKE=(test-mock-tracker.sh test-tracker-adapter-lint.sh)

# --- 1. Collect changed files ------------------------------------------------
changed=()
if [ "$#" -gt 0 ]; then
    changed=("$@")
else
    cd "$REPO_ROOT"
    # committed-vs-base, staged, and unstaged — union, deduped.
    while IFS= read -r line; do [ -n "$line" ] && changed+=("$line"); done < <(
        { git diff --name-only "$BASE_REF"...HEAD 2>/dev/null
          git diff --name-only HEAD 2>/dev/null
          git diff --name-only --cached 2>/dev/null
        } | sort -u
    )
fi

if [ "${#changed[@]}" -eq 0 ]; then
    echo -e "${YELLOW}No changed files detected (base: $BASE_REF). Running smoke only.${NC}"
    exec bash "$TESTS_DIR/run-all.sh" "${SMOKE[@]}"
fi

echo -e "${CYAN}Changed files (${#changed[@]}):${NC}"
printf '  %s\n' "${changed[@]}"

# --- 2. Map to test files ----------------------------------------------------
# Read the map into parallel arrays (glob, tests-string).
globs=(); tests_for=()
while IFS= read -r raw; do
    line="${raw%%#*}"                       # strip comments
    line="$(printf '%s' "$line" | sed 's/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    g="${line%%[[:space:]]*}"               # first token = glob
    t="${line#"$g"}"; t="$(printf '%s' "$t" | sed 's/^[[:space:]]*//')"
    globs+=("$g"); tests_for+=("$t")
done < "$MAP"

selected=""
full=0
unmatched=()
for file in "${changed[@]}"; do
    hit=0
    # A changed test file always (at least) runs itself — no map entry needed.
    case "$file" in
        tests/tooling/test-*.sh) selected+=" $(basename "$file")"; hit=1 ;;
    esac
    for i in "${!globs[@]}"; do
        # shellcheck disable=SC2254
        case "$file" in
            ${globs[$i]}) selected+=" ${tests_for[$i]}"; hit=1 ;;
        esac
    done
    if [ "$hit" -eq 0 ]; then full=1; unmatched+=("$file"); fi
done

# --- 3. Decide + run ---------------------------------------------------------
if [ "$full" -eq 1 ]; then
    echo -e "\n${YELLOW}Unmapped path(s) changed -> FAIL-OPEN to FULL suite:${NC}"
    printf '  %s\n' "${unmatched[@]}"
    exec bash "$TESTS_DIR/run-all.sh"
fi

# Union smoke + selected, dedupe, keep only existing files.
run_list=()
seen=" "
for t in "${SMOKE[@]}" $selected; do
    case "$seen" in *" $t "*) continue ;; esac
    [ -f "$TESTS_DIR/tooling/$t" ] || { echo -e "${YELLOW}map references missing test: $t${NC}" >&2; continue; }
    run_list+=("$t"); seen+="$t "
done

echo -e "\n${CYAN}Scoped test set (${#run_list[@]} files, incl. smoke):${NC}"
printf '  %s\n' "${run_list[@]}"
echo
exec bash "$TESTS_DIR/run-all.sh" "${run_list[@]}"
