#!/bin/bash
# =============================================================================
# Test: SessionStart wrong-entry guard (ABS-92 stable-governs-dev, Phase 1)
# =============================================================================
# Exercises scripts/session-wrong-entry-guard.sh with temp dirs standing in for
# the dev repo and the stable checkout, each a fake git repo with a settable
# `origin` URL. The guard is copied into the fake dev repo's scripts/ so its
# self-location resolves to that dev repo.
#
# Cases:
#   - fires (exit 2) ONLY when all of (a) stable resolved & different dir,
#     (b) matching origin URL, (c) cwd == dev repo, (d) no spawn markers hold;
#   - H3b spawn-marker exemption (ORCH_ROLE / ORCH_PACKET_FILE set -> exit 0);
#   - consumer no-op (different origin URL -> exit 0);
#   - SAW_GUARD_DISABLE=1 -> exit 0;
#   - no stable checkout resolved -> exit 0 (silent);
#   - cwd not the dev repo -> exit 0.
#
# bash 3.2 + BSD tools only (no grep -P, no timeout).
# Run from repo root: bash tests/test-wrong-entry-guard.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD_SRC="$REPO_ROOT/scripts/session-wrong-entry-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -8 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

# --- Fixtures ----------------------------------------------------------------
# make_repo <origin-url> — a temp dir that is a real git repo with the given
# origin URL. Prints the repo path.
make_repo() {
    local url="$1" d
    d="$(mktemp -d /tmp/weguard-repo-XXXXXX)"
    git -C "$d" init -q
    git -C "$d" remote add origin "$url"
    echo "$d"
}

# make_dev_repo <origin-url> — a fake dev repo with the guard installed under its
# own scripts/ (so BASH_SOURCE resolution points at THIS repo). Prints the path.
make_dev_repo() {
    local url="$1" d
    d="$(make_repo "$url")"
    mkdir -p "$d/scripts"
    cp "$GUARD_SRC" "$d/scripts/session-wrong-entry-guard.sh"
    echo "$d"
}

# run_guard <dev-repo> <cwd> [env assignments...] — run the installed guard from
# the given cwd with the given env, capturing exit code. Prints "exit\noutput".
# HOME is pinned to an empty temp dir so a real ~/boilerplate-stable never leaks in.
# The ambient orchestrator markers (ORCH_ROLE / ORCH_PACKET_FILE / ORCH_HARNESS_HOME)
# are scrubbed with `env -u` so the test is hermetic when run inside an orchestrator
# seat or CI harness that exports them — otherwise a leaked ORCH_ROLE trips the
# spawn-marker exemption (exit 0) and a leaked ORCH_HARNESS_HOME overrides the stable
# root, defeating the positive-fire subtests. Any value passed in "$@" is applied
# AFTER the -u scrub, so per-case assignments (e.g. ORCH_ROLE=be-developer) still win.
run_guard() {
    local dev="$1" cwd="$2"; shift 2
    local emptyhome ec out
    emptyhome="$(mktemp -d /tmp/weguard-home-XXXXXX)"
    ec=0
    out=$(cd "$cwd" && env -u ORCH_ROLE -u ORCH_PACKET_FILE -u ORCH_HARNESS_HOME HOME="$emptyhome" "$@" bash "$dev/scripts/session-wrong-entry-guard.sh" 2>&1) || ec=$?
    rm -rf "$emptyhome"
    printf '%s\n%s' "$ec" "$out"
}

echo -e "${CYAN}=== Wrong-entry guard (ABS-92) ===${NC}\n"

URL="git@example.com:product/boilerplate.git"

# =============================================================================
echo -e "${CYAN}Fires (exit 2) only when all conditions hold${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
STABLE="$(make_repo "$URL")"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$STABLE")
ec="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_exit "$ec" "2" "all conditions hold (matching origin, cwd==dev, stable set, no markers) -> exit 2"
assert_contains "$out" "WRONG ENTRY" "failure message is loud"
assert_contains "$out" "dev-session.sh" "failure message names the interactive recipe"
DEV_PHYS="$(cd "$DEV" && pwd -P)"
assert_contains "$out" "ORCH_TARGET_REPO=$DEV_PHYS" "failure message names the orchestrator recipe"
rm -rf "$DEV" "$STABLE"

# =============================================================================
echo -e "\n${CYAN}(d/H3b) spawn-marker exemption — headless spawns are never blocked${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
STABLE="$(make_repo "$URL")"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$STABLE" ORCH_ROLE=be-developer)
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "ORCH_ROLE set (headless spawn) -> exit 0 (exempt)"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$STABLE" ORCH_PACKET_FILE=/tmp/packet.txt)
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "ORCH_PACKET_FILE set (headless spawn) -> exit 0 (exempt)"
rm -rf "$DEV" "$STABLE"

# =============================================================================
echo -e "\n${CYAN}(b) consumer no-op — a different-product stable is ignored${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
STABLE="$(make_repo "git@example.com:someone-else/other-product.git")"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$STABLE")
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "different origin URL (consumer project) -> exit 0 (silent no-op)"
rm -rf "$DEV" "$STABLE"

# =============================================================================
echo -e "\n${CYAN}Escape hatch — SAW_GUARD_DISABLE=1${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
STABLE="$(make_repo "$URL")"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$STABLE" SAW_GUARD_DISABLE=1)
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "SAW_GUARD_DISABLE=1 -> exit 0 (escape hatch)"
rm -rf "$DEV" "$STABLE"

# =============================================================================
echo -e "\n${CYAN}(a) no stable checkout resolved -> silent${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
# No ORCH_HARNESS_HOME, and HOME is pinned empty so ~/boilerplate-stable is absent.
res=$(run_guard "$DEV" "$DEV")
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "no stable root resolved (not self-hosting) -> exit 0 (silent)"
rm -rf "$DEV"

# =============================================================================
echo -e "\n${CYAN}(a) stable == dev (session already governed by stable) -> silent${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
res=$(run_guard "$DEV" "$DEV" ORCH_HARNESS_HOME="$DEV")
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "stable root == dev repo -> exit 0 (already governed)"
rm -rf "$DEV"

# =============================================================================
echo -e "\n${CYAN}(c) cwd is NOT the dev repo -> silent${NC}"
# =============================================================================
DEV="$(make_dev_repo "$URL")"
STABLE="$(make_repo "$URL")"
res=$(run_guard "$DEV" "$STABLE" ORCH_HARNESS_HOME="$STABLE")
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "cwd == stable (not dev repo) -> exit 0 (silent)"
OTHER="$(mktemp -d /tmp/weguard-other-XXXXXX)"
res=$(run_guard "$DEV" "$OTHER" ORCH_HARNESS_HOME="$STABLE")
ec="${res%%$'\n'*}"
assert_exit "$ec" "0" "cwd == unrelated dir -> exit 0 (silent)"
rm -rf "$DEV" "$STABLE" "$OTHER"

# =============================================================================
echo -e "\n${CYAN}~/boilerplate-stable convention resolves when present${NC}"
# =============================================================================
# With no ORCH_HARNESS_HOME, a ~/boilerplate-stable of the SAME product fires.
DEV="$(make_dev_repo "$URL")"
FAKEHOME="$(mktemp -d /tmp/weguard-fakehome-XXXXXX)"
STABLE="$FAKEHOME/boilerplate-stable"
git init -q "$STABLE"
git -C "$STABLE" remote add origin "$URL"
ec=0
# Scrub ambient orchestrator markers (see run_guard) so ORCH_HARNESS_HOME cannot
# override the ~/boilerplate-stable convention branch this subtest exercises.
out=$(cd "$DEV" && env -u ORCH_ROLE -u ORCH_PACKET_FILE -u ORCH_HARNESS_HOME HOME="$FAKEHOME" bash "$DEV/scripts/session-wrong-entry-guard.sh" 2>&1) || ec=$?
assert_exit "$ec" "2" "~/boilerplate-stable (same product) resolves -> exit 2"
rm -rf "$DEV" "$FAKEHOME"

# =============================================================================
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
