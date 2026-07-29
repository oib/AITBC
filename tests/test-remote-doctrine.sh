#!/usr/bin/env bash
# =============================================================================
# Test: Remote doctrine — GitLab live, Bitbucket = release mirror (PILOT-25 / ABS-539)
# =============================================================================
# Pins the two mechanical contracts of the remote doctrine:
#
#   AC1 (scripts/release-mirror-push.sh): after the GitLab tag, `main` + tag are
#        pushed to the mirror remote (Bitbucket `origin`); with the mirror remote
#        UNREACHABLE the script WARNs and still exits 0 — Bitbucket availability
#        never gates the release.
#   AC2 (scripts/active-remote-guard.sh): with the active-remote pin set, a seat
#        push/MR-open targeting `origin` is REFUSED (exit 1 + intent line); the
#        pinned remote is ALLOWED; no pin -> guard inert (analogous to the
#        merge-target-guard suite).
#
# Self-contained: builds a throwaway git repo + bare mirror in a tmp dir. No fixed
# paths, no network. bash 3.2 + BSD tools. Run from repo root:
#   bash tests/test-remote-doctrine.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/active-remote-guard.sh"
MIRROR="$REPO_ROOT/scripts/release-mirror-push.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc')"; FAIL=$((FAIL + 1)); fi
}

# Assert the command's stdout matches a grep -E pattern.
assert_out() {
    local pattern="$1" label="$2"; shift 2
    local out; out="$("$@" 2>/dev/null || true)"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$out" | grep -qE "$pattern"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (no match /$pattern/; got: $out)"; FAIL=$((FAIL + 1)); fi
}

echo -e "${CYAN}=== Remote doctrine (PILOT-25) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}A. AC2 — active-remote guard: pin=gitlab refuses origin, allows gitlab${NC}"
# =============================================================================
assert_rc 1 "pin=gitlab, target origin -> REFUSE (exit 1)" \
    env ORCH_MAIN_REMOTE=gitlab bash "$GUARD" check origin
assert_out 'ACTIVE-REMOTE-GUARD-REFUSE target=origin pin=gitlab action=retarget-active-remote' \
    "target origin -> prints ACTIVE-REMOTE-GUARD-REFUSE intent line" \
    env ORCH_MAIN_REMOTE=gitlab bash "$GUARD" check origin
assert_rc 0 "pin=gitlab, target gitlab -> ALLOW (exit 0)" \
    env ORCH_MAIN_REMOTE=gitlab bash "$GUARD" check gitlab
# "remote/branch" form normalises to the remote name.
assert_rc 1 "pin=gitlab, target origin/main -> REFUSE (normalised, exit 1)" \
    env ORCH_MAIN_REMOTE=gitlab bash "$GUARD" check origin/main
assert_rc 0 "pin=gitlab, target gitlab/PILOT-25-auto -> ALLOW (normalised, exit 0)" \
    env ORCH_MAIN_REMOTE=gitlab bash "$GUARD" check gitlab/PILOT-25-auto

# =============================================================================
echo -e "\n${CYAN}B. AC2 — pin inert when unset (legacy single-remote), bad input${NC}"
# =============================================================================
assert_rc 0 "no pin (ORCH_MAIN_REMOTE unset), target origin -> ALLOW (exit 0)" \
    env -u ORCH_MAIN_REMOTE bash "$GUARD" check origin
assert_rc 0 "no pin (ORCH_MAIN_REMOTE empty), target origin -> ALLOW (exit 0)" \
    env ORCH_MAIN_REMOTE= bash "$GUARD" check origin
assert_rc 64 "missing target -> exit 64 (usage, fails closed)" \
    bash "$GUARD" check
assert_rc 64 "unknown subcommand -> exit 64" \
    bash "$GUARD" bogus

# =============================================================================
echo -e "\n${CYAN}C. AC1 — release-mirror-push: usage + dry-run${NC}"
# =============================================================================
assert_rc 64 "no tag -> exit 64 (usage)" \
    bash "$MIRROR"
assert_rc 64 "non-semver tag -> exit 64 (usage)" \
    bash "$MIRROR" not-a-version

# --- Build a scratch repo + bare mirror for the end-to-end push -------------
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/remote-doctrine.XXXXXX")" || { echo "no tmp"; exit 1; }
cleanup() { rm -rf "$SCRATCH"; }
trap cleanup EXIT

WORK="$SCRATCH/work"
BARE="$SCRATCH/mirror.git"
git init -q "$WORK"
git -C "$WORK" config user.email t@t; git -C "$WORK" config user.name t
git -C "$WORK" checkout -q -b main
echo hello > "$WORK/f.txt"; git -C "$WORK" add f.txt; git -C "$WORK" commit -q -m init
git -C "$WORK" tag -a v9.9.9 -m 'test tag'
git init -q --bare "$BARE"
git -C "$WORK" remote add origin "$BARE"

# Dry-run: nothing is pushed, prints DRY-RUN OK, exit 0.
assert_rc 0 "dry-run -> exit 0" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9 --dry-run"
assert_out 'DRY-RUN OK' "dry-run -> prints DRY-RUN OK" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9 --dry-run"
# Dry-run pushed nothing: bare mirror has no main branch yet.
assert_rc 1 "dry-run pushed nothing (mirror has no 'main' ref)" \
    git -C "$BARE" rev-parse --verify --quiet refs/heads/main

# Real push: main + tag land on the mirror, exit 0.
assert_rc 0 "real push to reachable mirror -> exit 0" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9"
assert_rc 0 "mirror now has refs/heads/main" \
    git -C "$BARE" rev-parse --verify --quiet refs/heads/main
assert_rc 0 "mirror now has the release tag v9.9.9" \
    git -C "$BARE" rev-parse --verify --quiet refs/tags/v9.9.9

# =============================================================================
echo -e "\n${CYAN}D. AC1 — unreachable mirror WARNs but does NOT gate the release${NC}"
# =============================================================================
# Point origin at a non-existent path -> push fails -> WARN + exit 0.
git -C "$WORK" remote set-url origin "$SCRATCH/does-not-exist.git"
assert_rc 0 "unreachable mirror -> exit 0 (release NOT gated)" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9"
assert_out 'WARN.*(FAILED|does not|availability)' "unreachable mirror -> prints WARN" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9 2>&1"
# Mirror remote absent entirely -> WARN + exit 0.
git -C "$WORK" remote remove origin
assert_rc 0 "mirror remote absent -> exit 0 (release NOT gated)" \
    bash -c "cd '$WORK' && bash '$MIRROR' v9.9.9"

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All remote-doctrine tests passed.${NC}"
