# =============================================================================
# ABS-316 + ABS-597 — epic-integration branch-split guard (remote-only, content-aware)
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness): assert_eq /
# assert_contains / assert_not_contains, PASS/FAIL/TOTAL, $ORCH.
#
# ABS-316 made a duplicate epic branch mechanically visible at the JOIN (the
# ABS-217/ABS-220 off-canonical-merge strand). ABS-597 fixes two false-alarm
# defects that guard hit in Pilot 8, freezing a finished PILOT-71 for 2 h in
# Needs PO Decision:
#   AC1 — only branches ON THE ACTIVE PUSH REMOTE count. A local-only work trace
#         (the tech-writer's epic/PILOT-71-...-tw-docs-4568) is NOT a split.
#   AC2 — two candidates where one is an ANCESTOR of the other are a stale
#         pointer, not a divergence: auto-resolve to the descendant, log, and
#         let the ordinary JOIN fire — never escalate.
#   AC3 — a REAL split (commits diverging on both sides) still escalates, and the
#         intent NAMES the diverging commits per branch, not just branch names.
#
# The guard reads epic branches through active_remote_name (ADR-A-0030 pin), so
# in this hermetic repo — no remote configured — it resolves to "origin" and the
# pre-seeded refs/remotes/origin/epic/* refs are the source of truth.
# =============================================================================

echo -e "\n${CYAN}=== ABS-316/ABS-597 epic-branch-split guard ===${NC}\n"

# _split_run <scenario> [killswitch] — build a throwaway repo per scenario and
# run epic_branch_split_class + join_check_epic against it. Scenarios:
#   single      one remote epic branch                       -> SINGLE / JOIN
#   zero        no epic branch at all                        -> SINGLE / JOIN
#   localonly   one remote branch + a LOCAL-only second      -> SINGLE / JOIN (AC1)
#   ancestry    two remote branches, slug1 ancestor of slug2 -> ANCESTRY / JOIN (AC2)
#   divergence  two remote branches, commits on both sides   -> SPLIT / NPD (AC3)
_split_run() {
    local scenario="$1" killswitch="${2:-}"
    bash -c '
        set -u
        ORCH="$1"; scenario="$2"; killswitch="$3"
        repo="$(mktemp -d)"
        (
            cd "$repo"
            git init -q .
            git config user.email t@t; git config user.name t
            git commit -q --allow-empty -m base
            base="$(git rev-parse HEAD)"
            seed_remote() { git update-ref "refs/remotes/origin/epic/EPIC-1-$1" "$2"; }
            case "$scenario" in
                single)
                    seed_remote slug1 "$base" ;;
                zero)
                    : ;;
                localonly)
                    # Real remote epic branch + a LOCAL-only second branch that is
                    # fully contained in it. AC1: the local ref must be ignored.
                    seed_remote slug1 "$base"
                    git branch "epic/EPIC-1-tw-docs-4568" "$base" ;;
                ancestry)
                    # slug2 is one commit AHEAD of slug1 (slug1 fully contained in
                    # slug2). AC2: descendant slug2 wins, no escalation.
                    seed_remote slug1 "$base"
                    git checkout -q -b tmp2 "$base"
                    git commit -q --allow-empty -m "epic advance"
                    seed_remote slug2 "$(git rev-parse HEAD)"
                    git checkout -q "$base" 2>/dev/null; git branch -D tmp2 >/dev/null 2>&1 ;;
                divergence)
                    # slug1 and slug2 each carry a UNIQUE commit off base. AC3:
                    # real split -> escalate and name the diverging commits.
                    git checkout -q -b tmpA "$base"
                    git commit -q --allow-empty -m "only on slug1"
                    seed_remote slug1 "$(git rev-parse HEAD)"
                    git checkout -q -b tmpB "$base"
                    git commit -q --allow-empty -m "only on slug2"
                    seed_remote slug2 "$(git rev-parse HEAD)"
                    git checkout -q "$base" 2>/dev/null
                    git branch -D tmpA tmpB >/dev/null 2>&1 ;;
            esac
        ) >/dev/null 2>&1

        # ORCH_STATE_DIR / ORCH_RUN_LOG are frozen at source time via ${VAR:-...},
        # so set them BEFORE sourcing. ORCH_STATE_ROOT is OVERWRITTEN at source
        # time (ABS-205 worktree pin), so re-set it AFTER the source.
        export MODE=dry
        export ORCH_STATE_DIR="$repo/.state"; mkdir -p "$ORCH_STATE_DIR"
        export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
        [ -n "$killswitch" ] && export ORCH_EPIC_SPLIT_GUARD="$killswitch"
        source "$ORCH" >/dev/null 2>&1
        export ORCH_STATE_ROOT="$repo"

        # Tracker-side stubs: epic rests in Stories In Flight, one Done child, no
        # follow-ups, no exemptions -> join_check_epic reaches the branch guard.
        ticket_still_in() { return 0; }
        epic_has_unprocessed_followups() { return 1; }
        epic_children_rows() { printf "C1\t[Done]\t\n"; }
        child_join_exempt() { return 1; }

        printf "COUNT=%s\n" "$(epic_branch_names EPIC-1 | grep -c . || true)"
        printf "CLASS=%s\n" "$(epic_branch_split_class EPIC-1 | cut -f1)"
        join_check_epic EPIC-1
        rm -rf "$repo"
    ' _split "$ORCH" "$scenario" "$killswitch"
}

# --- Case 1: single canonical remote branch -> ordinary JOIN fires ----------
out="$(_split_run single)"
assert_contains "$out" "COUNT=1" "ABS-597: one remote epic branch -> distinct count 1"
assert_contains "$out" "CLASS=SINGLE" "ABS-597: one branch -> SINGLE"
assert_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597: single branch -> ordinary JOIN fires"
assert_not_contains "$out" "JOIN-SPLIT" "ABS-597: single branch -> no split escalation"

# --- Case 2: zero epic branches -> guard no-ops, JOIN fires -----------------
out="$(_split_run zero)"
assert_contains "$out" "COUNT=0" "ABS-597: zero epic branches -> distinct count 0"
assert_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597: zero branches -> guard no-ops, JOIN fires"

# --- Case 3 (AC1): local-only second branch is IGNORED ----------------------
out="$(_split_run localonly)"
assert_contains "$out" "COUNT=1" "ABS-597 AC1: local-only second branch does NOT inflate the remote count"
assert_contains "$out" "CLASS=SINGLE" "ABS-597 AC1: local-only branch -> SINGLE (no split)"
assert_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597 AC1: local-only trace -> JOIN fires (the frozen-PILOT-71 fix)"
assert_not_contains "$out" "JOIN-SPLIT ticket=EPIC-1" "ABS-597 AC1: local-only trace -> no false escalation"

# --- Case 4 (AC2): remote ancestry auto-resolves to the descendant ----------
out="$(_split_run ancestry)"
assert_contains "$out" "COUNT=2" "ABS-597 AC2: two remote branches present"
assert_contains "$out" "CLASS=ANCESTRY" "ABS-597 AC2: one contains the other -> ANCESTRY"
assert_contains "$out" "INTENT JOIN-SPLIT-RESOLVED ticket=EPIC-1" "ABS-597 AC2: ancestry auto-resolved (logged), not escalated"
assert_contains "$out" "descendant:epic/EPIC-1-slug2" "ABS-597 AC2: the descendant wins"
assert_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597 AC2: JOIN still fires after auto-resolve"
assert_not_contains "$out" "to=Needs PO Decision" "ABS-597 AC2: ancestry does NOT escalate to Needs PO Decision"

# --- Case 5 (AC3): genuine divergence escalates AND names commits -----------
out="$(_split_run divergence)"
assert_contains "$out" "COUNT=2" "ABS-597 AC3: two divergent remote branches"
assert_contains "$out" "CLASS=SPLIT" "ABS-597 AC3: divergent commits both sides -> SPLIT"
assert_contains "$out" "INTENT JOIN-SPLIT ticket=EPIC-1 role=- to=Needs PO Decision" "ABS-597 AC3: real split -> Needs PO Decision"
assert_contains "$out" "epic-branches:epic/EPIC-1-slug1,epic/EPIC-1-slug2" "ABS-597 AC3: split intent names both branches"
assert_contains "$out" "diverging:epic/EPIC-1-slug1[" "ABS-597 AC3: split intent names the diverging commits, not only branch names"
assert_not_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597 AC3: split does NOT fire the ordinary JOIN"

# --- Case 6: kill switch off -> guard bypassed, ordinary JOIN fires ----------
out="$(_split_run divergence 0)"
assert_contains "$out" "INTENT JOIN ticket=EPIC-1 role=- to=Epic Integration" "ABS-597: ORCH_EPIC_SPLIT_GUARD=0 restores JOIN even with a real split"
assert_not_contains "$out" "JOIN-SPLIT ticket=EPIC-1" "ABS-597: kill switch suppresses the split escalation"
