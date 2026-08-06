#!/usr/bin/env bash
# =============================================================================
# Test: read-only ops-sweep sensors (PILOT-40 / twin ABS-549)
# =============================================================================
# scripts/ops-sweep-sensors.sh emits one stable line per finding
#   <class> <ticket-or-dash> <evidence> <suggestion>
# for the eight "Steckenbleiber" classes, deterministically and WITHOUT an LLM,
# so every detector is unit-testable against fixture repos (change-contract:
# work/improvement-proposals/2026-07-25-hourly-ops-sweep-janitor.md).
#
# Contract pinned here:
#   * null findings on an anomaly-free fixture (every finding = a falsification);
#   * each detector has a POSITIVE and a NEGATIVE fixture;
#   * exit 0 EVEN WITH findings (diagnosis, not a gate); exit 64 on bad input.
#
# Self-contained: builds throwaway git repos / state dirs / ticket dirs under a
# temp path. bash 3.2 + BSD/GNU tools. Run from repo root:
#   bash tests/test-ops-sweep-sensors.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SENSORS="$REPO_ROOT/scripts/ops-sweep-sensors.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_contains() {
    local out="$1" needle="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$needle" <<<"$out"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $needle)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -8 <<<"$out" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local out="$1" needle="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$needle" <<<"$out"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $needle)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -8 <<<"$out" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/ops-sweep-XXXXXX")"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

# git_init <dir> — a repo born on main with one commit, no gpg signing.
git_init() {
    local d="$1"
    git init -q "$d"
    git -C "$d" symbolic-ref HEAD refs/heads/main
    git -C "$d" config user.email t@t.dev; git -C "$d" config user.name t
    git -C "$d" config commit.gpgsign false 2>/dev/null || true
    echo seed > "$d/seed"; git -C "$d" add seed; git -C "$d" commit -q -m seed
}
# Run the sensors. Each detector's inputs are supplied explicitly by the caller
# as OPS_* prefix assignments; ambient ORCH_* is scrubbed so a seat's environment
# can never leak into a detector whose OPS_* equivalent is unset (ABS-285 spirit).
sensors() { env -u ORCH_STATE_DIR -u ORCH_LOCK_TTL bash "$SENSORS" "$@"; }

# =============================================================================
echo -e "${CYAN}=== ops-sweep sensors (PILOT-40) ===${NC}\n"
echo -e "${CYAN}0. anomaly-free fixture -> zero findings; usage errors fail closed${NC}"
# =============================================================================
CLEAN="$TMP/clean"; git_init "$CLEAN"
out="$(OPS_REPO="$CLEAN" OPS_STATE_DIR="$TMP/none" sensors)"
rc=$?
assert_eq "$rc" "0" "exit 0 on a clean fixture"
assert_eq "$(printf '%s' "$out" | grep -c . || true)" "0" "clean fixture yields ZERO finding lines"
rc=0; OPS_REPO="$CLEAN" sensors bogus-detector >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "64" "unknown detector -> exit 64 (fail closed)"
assert_contains "$(sensors --list)" "handoff-nomove-actionable" "--list names all detectors"

# =============================================================================
echo -e "\n${CYAN}1. worktree-hygiene — HEAD!=main (pos), orphaned worktree (pos), clean (neg)${NC}"
# =============================================================================
WH="$TMP/wh"; git_init "$WH"
git -C "$WH" checkout -q -b PILOT-9-auto           # main checkout parked on a story branch
out="$(OPS_REPO="$WH" sensors worktree-hygiene)"
assert_contains "$out" "worktree-hygiene - head=PILOT-9-auto,expected=main" "HEAD!=main flagged"
git -C "$WH" checkout -q main
out="$(OPS_REPO="$WH" sensors worktree-hygiene)"
assert_not_contains "$out" "worktree-hygiene" "back on main -> no finding (negative)"
# orphaned worktree: register one, then delete its directory on disk.
WT="$TMP/wh-wt"; git -C "$WH" worktree add -q -b side "$WT" >/dev/null 2>&1
rm -rf "$WT"
out="$(OPS_REPO="$WH" sensors worktree-hygiene)"
assert_contains "$out" "prune-orphaned-worktree" "vanished worktree dir flagged as orphaned"
git -C "$WH" worktree prune 2>/dev/null || true
out="$(OPS_REPO="$WH" sensors worktree-hygiene)"
assert_not_contains "$out" "prune-orphaned-worktree" "after prune -> no orphan finding (negative)"
# PILOT-75 AC3: a TRACKED, uncommitted change in the main checkout is a lost-work
# signature (the PILOT-44 Befund) -> flagged. Untracked files are ignored.
UM="$TMP/unclean-main"; git_init "$UM"          # git_init leaves it on main, clean
out="$(OPS_REPO="$UM" sensors worktree-hygiene)"
assert_not_contains "$out" "unclean-main-checkout" "clean main checkout -> no unclean finding (negative)"
echo "untracked scratch" > "$UM/scratch.tmp"    # untracked only -> still clean signal
out="$(OPS_REPO="$UM" sensors worktree-hygiene)"
assert_not_contains "$out" "unclean-main-checkout" "untracked files alone -> not flagged (--untracked-files=no)"
echo "uncommitted edit" >> "$UM/seed"           # modify a TRACKED file, leave it uncommitted
out="$(OPS_REPO="$UM" sensors worktree-hygiene)"
assert_contains "$out" "unclean-main-checkout" "tracked uncommitted change in main checkout -> flagged (PILOT-75 AC3)"
assert_contains "$out" "commit-and-push-or-discard-main-checkout-edits" "unclean-main finding carries the remediation suggestion"

# =============================================================================
echo -e "\n${CYAN}2. dep-release-due — dep merged (pos) vs. dep not merged / not blocked (neg)${NC}"
# =============================================================================
DR="$TMP/dep"; git_init "$DR"
# PILOT-29-auto merged into main (its head is an ancestor of main).
git -C "$DR" checkout -q -b PILOT-29-auto; echo x > "$DR/x"; git -C "$DR" add x; git -C "$DR" commit -q -m dep
git -C "$DR" checkout -q main; git -C "$DR" merge -q --no-ff PILOT-29-auto -m merge
# PILOT-31-auto NOT merged (diverges from main).
git -C "$DR" checkout -q -b PILOT-31-auto; echo y > "$DR/y"; git -C "$DR" add y; git -C "$DR" commit -q -m open
git -C "$DR" checkout -q main
TKD="$TMP/dep-tickets"; mkdir -p "$TKD"
cat > "$TKD/PILOT-30.md" <<'EOF'
---
id: PILOT-30
status: Blocked
depends_on: [PILOT-29]
---
Blocked on PILOT-29.
EOF
cat > "$TKD/PILOT-32.md" <<'EOF'
---
id: PILOT-32
status: Blocked
depends_on: [PILOT-31]
---
Blocked on PILOT-31 (still open).
EOF
cat > "$TKD/PILOT-33.md" <<'EOF'
---
id: PILOT-33
status: In Progress
depends_on: [PILOT-29]
---
Not blocked.
EOF
out="$(OPS_REPO="$DR" OPS_TICKETS_DIR="$TKD" sensors dep-release-due)"
assert_contains "$out" "dep-release-due PILOT-30 dep=PILOT-29" "blocked ticket whose merged dep is ancestor -> flagged"
assert_not_contains "$out" "PILOT-32" "blocked on an UNMERGED dep -> not flagged (evidence gate)"
assert_not_contains "$out" "PILOT-33" "non-Blocked ticket -> not flagged"

# =============================================================================
echo -e "\n${CYAN}3. handoff-nomove-actionable — verdict without later transition (pos) vs. moved (neg)${NC}"
# =============================================================================
HD="$TMP/handoff-tickets"; mkdir -p "$HD"
cat > "$HD/PILOT-29.md" <<'EOF'
---
id: PILOT-29
status: In Review
---
## Comments

### 2026-07-25T10:00:00Z | kind: handoff | actor: system-architect
VERDICT: APPROVED. Draft comment at work/scratch/PILOT-29-approve.md, exit: In Review.
EOF
cat > "$HD/PILOT-40.md" <<'EOF'
---
id: PILOT-40
status: In Progress
---
## Comments

### 2026-07-25T10:00:00Z | kind: handoff | actor: system-architect
VERDICT: APPROVED, exit: In Progress.

### 2026-07-25T10:05:00Z | kind: transition-reason | actor: system-architect
Applied the move.
EOF
out="$(OPS_REPO="$TMP/none" OPS_TICKETS_DIR="$HD" sensors handoff-nomove-actionable)"
assert_contains "$out" "handoff-nomove-actionable PILOT-29" "verdict handoff with no later transition -> flagged"
assert_contains "$out" "draft=missing" "reports the drafted comment path state as evidence"
assert_not_contains "$out" "PILOT-40" "a later transition comment -> not flagged (move happened)"

# =============================================================================
echo -e "\n${CYAN}4/5. missing-mr vs. branch-recoverable — partitioned on remote-ref presence${NC}"
# =============================================================================
MB="$TMP/mrbranch"; git_init "$MB"
git -C "$MB" checkout -q -b PILOT-19-auto; echo a > "$MB/a"; git -C "$MB" add a; git -C "$MB" commit -q -m ahead
PUSHED="$(git -C "$MB" rev-parse PILOT-19-auto)"
git -C "$MB" update-ref refs/remotes/origin/PILOT-19-auto "$PUSHED"      # PUSHED, unmerged
git -C "$MB" checkout -q -b PILOT-23-auto main; echo b > "$MB/b"; git -C "$MB" add b; git -C "$MB" commit -q -m local-only
# PILOT-23-auto has NO remote ref -> recoverable, not missing-mr.
git -C "$MB" checkout -q -b PILOT-50-auto main; echo c > "$MB/c"; git -C "$MB" add c; git -C "$MB" commit -q -m merged
git -C "$MB" checkout -q main; git -C "$MB" merge -q --no-ff PILOT-50-auto -m m50   # merged branch
git -C "$MB" update-ref refs/remotes/origin/PILOT-50-auto "$(git -C "$MB" rev-parse PILOT-50-auto)"
out="$(OPS_REPO="$MB" OPS_TARGET_REMOTE=origin sensors missing-mr branch-recoverable)"
assert_contains "$out" "missing-mr PILOT-19 branch=PILOT-19-auto,ahead=1" "pushed, unmerged, ahead -> missing-mr"
assert_contains "$out" "branch-recoverable PILOT-23 branch=PILOT-23-auto" "unpushed local-only branch -> recoverable"
assert_not_contains "$out" "PILOT-50" "merged branch -> neither missing-mr nor recoverable (negative)"
assert_not_contains "$out" "branch-recoverable PILOT-19" "pushed branch is NOT reported as recoverable"

# =============================================================================
echo -e "\n${CYAN}6. stale-lock — aged lock w/ no live seat (pos); fresh lock, merge-token,${NC}"
echo -e "${CYAN}   and dead-PID-in-lock + LIVE process in the worktree (neg)${NC}"
# =============================================================================
ST="$TMP/state6"; mkdir -p "$ST/locks/PILOT-99" "$ST/locks/PILOT-88" "$ST/locks/merge/PILOT-77"
touch -t 200001010000 "$ST/locks/PILOT-99"          # ancient -> stale
touch -t 200001010000 "$ST/locks/merge/PILOT-77"    # ancient but merge-token subtree (excluded)
# NO_SEATS: OPS_LIVE_CWDS_FILE points at an absent path -> "no live seats", so the
# liveness cross-check is deterministic (lsof is never consulted in the suite).
NO_SEATS="$TMP/no-such-live-cwds"
out="$(OPS_STATE_DIR="$ST" OPS_LIVE_CWDS_FILE="$NO_SEATS" sensors stale-lock)"
assert_contains "$out" "stale-lock PILOT-99 age=" "aged lock, no live seat -> flagged"
assert_contains "$out" "clear-stale-lock" "stale-lock carries the clear suggestion"
assert_not_contains "$out" "PILOT-88" "fresh lock (age ~0 < TTL) -> not flagged (negative)"
assert_not_contains "$out" "PILOT-77" "merge-token subtree -> excluded (holder-liveness, not TTL)"

# OPERATOR-MANDATED negative (2026-07-25, VERBINDLICH): a lock whose wrapper PID is
# dead/written-off but a LIVING process still has its cwd in the ticket's seat
# worktree must NOT be called stale — TTL/PID alone is a false criterion (the
# costliest misclass, else a downstream actuator double-dispatches onto live work).
ST2="$TMP/state6b"; mkdir -p "$ST2/locks/PILOT-50"
echo 28701 > "$ST2/locks/PILOT-50/pid"              # written-off PID (not consulted; liveness is cwd-based)
touch -t 200001010000 "$ST2/locks/PILOT-50"         # age AFTER writing pid (a later write bumps dir mtime)
LIVE="$TMP/live-cwds.txt"
printf '%s\n' "$TMP/tmp/PILOT-50-work/scripts" > "$LIVE"   # live claude cwd INSIDE the seat worktree
out="$(OPS_STATE_DIR="$ST2" OPS_LIVE_CWDS_FILE="$LIVE" sensors stale-lock)"
assert_not_contains "$out" "PILOT-50" "aged lock + LIVE process in the seat worktree -> NOT stale (operator neg)"
# Boundary: a live process in a DIFFERENT ticket's worktree must not suppress, and
# PILOT-5 liveness must not shadow PILOT-50 (path-component boundary).
printf '%s\n' "$TMP/tmp/PILOT-5-work" > "$LIVE"
out="$(OPS_STATE_DIR="$ST2" OPS_LIVE_CWDS_FILE="$LIVE" sensors stale-lock)"
assert_contains "$out" "stale-lock PILOT-50 age=" "live cwd for a different ticket -> aged lock still flagged (boundary)"

# =============================================================================
echo -e "\n${CYAN}7. outage-marker-stale — old outage marker (pos), fresh marker (neg)${NC}"
# =============================================================================
SO="$TMP/state7"; mkdir -p "$SO"
printf '%s\t0\t%s\n' 100 200 > "$SO/outage"; touch -t 200001010000 "$SO/outage"   # ancient
printf '0\n' > "$SO/probe-inflight"                                               # fresh
out="$(OPS_STATE_DIR="$SO" sensors outage-marker-stale)"
assert_contains "$out" "outage-marker-stale - marker=outage,age=" "stale outage marker -> flagged"
assert_not_contains "$out" "marker=probe-inflight" "fresh probe-inflight marker -> not flagged (negative)"

# =============================================================================
echo -e "\n${CYAN}8. backend-junk-rows — off-pattern instance (pos), on-pattern only (neg)${NC}"
# =============================================================================
ROWS="$TMP/rows.tsv"
printf 'pilot-main\t5\nleaked-test-xyz\t1000\n#comment\t9\n' > "$ROWS"
out="$(OPS_BACKEND_ROWS="$ROWS" OPS_INSTANCE_PATTERN='^pilot-' sensors backend-junk-rows)"
assert_contains "$out" "backend-junk-rows - instance=leaked-test-xyz,rows=1000" "off-pattern instance_id -> flagged"
assert_not_contains "$out" "pilot-main" "on-pattern instance_id -> not flagged (negative)"
assert_not_contains "$out" "#comment" "comment line -> ignored"
ROWS2="$TMP/rows2.tsv"; printf 'pilot-main\t5\npilot-2\t3\n' > "$ROWS2"
out="$(OPS_BACKEND_ROWS="$ROWS2" OPS_INSTANCE_PATTERN='^pilot-' sensors backend-junk-rows)"
assert_eq "$(printf '%s' "$out" | grep -c . || true)" "0" "all-on-pattern rows -> zero findings (negative)"

# =============================================================================
echo -e "\n${CYAN}8b. epic-handoff-missing (ABS-588) — epic at 'Ready for Epic Acceptance'${NC}"
echo -e "${CYAN}    without the handoff artifact marker (pos) vs. with it / other status (neg)${NC}"
# =============================================================================
EH="$TMP/epic-handoff-tickets"; mkdir -p "$EH"
# PILOT-58: released to the human gate but NO handoff artifact -> flagged (the Pilot-7 gap).
cat > "$EH/PILOT-58.md" <<'EOF'
---
id: PILOT-58
status: Ready for Epic Acceptance
---
Epic released; branch epic/PILOT-58-foo is 65 commits ahead of main.
EOF
# PILOT-59: released WITH the artifact marker present -> not flagged.
cat > "$EH/PILOT-59.md" <<'EOF'
---
id: PILOT-59
status: Ready for Epic Acceptance
---
## Comments

### 2026-07-26T10:00:00Z | kind: gate-results | actor: rte
## Epic Integration — PILOT-59
EPIC-HANDOFF-READY
- **Stories** (all Done): PILOT-60 PILOT-61
EOF
# PILOT-62: not at the human gate (still integrating) -> never flagged regardless of marker.
cat > "$EH/PILOT-62.md" <<'EOF'
---
id: PILOT-62
status: Epic Integration
---
No artifact yet, but not at the human gate.
EOF
out="$(OPS_TICKETS_DIR="$EH" sensors epic-handoff-missing)"
assert_contains "$out" "epic-handoff-missing PILOT-58 status=Ready-for-Epic-Acceptance,artifact=absent" \
    "epic at Ready for Epic Acceptance with no artifact marker -> flagged (AC4)"
assert_contains "$out" "post-epic-handoff-artifact" "epic-handoff-missing carries the remediation suggestion"
assert_not_contains "$out" "PILOT-59" "artifact marker present -> not flagged (negative)"
assert_not_contains "$out" "PILOT-62" "status != Ready for Epic Acceptance -> not flagged (negative)"

# =============================================================================
echo -e "\n${CYAN}9. exit 0 EVEN WITH findings (diagnosis, not a gate)${NC}"
# =============================================================================
rc=0; OPS_STATE_DIR="$ST" OPS_LIVE_CWDS_FILE="$NO_SEATS" sensors stale-lock >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "findings present -> still exit 0"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
