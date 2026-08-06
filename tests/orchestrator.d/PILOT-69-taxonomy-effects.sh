# =============================================================================
# PILOT-69 — Taxonomien ohne Wirkung: give the ADR-A-0018 transient class an EFFECT
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq, ORCH.
#
# AC1(a): the transient class is BUDGET-NEUTRAL for the rework counter — a backward
#         transition whose reason denotes a transient/infrastructure abort consumes
#         no rework unit (mirroring the iteration guard's ABS-555 exclusion), while
#         a genuine functional bounce AND a handoff mis-report still count.
# AC1(b): a demonstrably-finished ticket (reached the acceptance/merge tier) steers
#         a cap/rework park to Blocked, not Needs PO Decision, via reached_merge_tier
#         / escalation_park_target — so the merge path stays reachable.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-69 transient-class effect: rework_count budget-neutral ===${NC}\n"

# A ticket dump with three backward transitions at the same gate: one FUNCTIONAL
# reject (counts), one TRANSIENT/infra abort (does NOT count), one handoff
# MIS-REPORT (content fault — still counts, ADR-A-0024 e).
_pilot69_dump='---
id: T-69
status: In Review
---
## Comments

### 2026-07-26T00:01:00Z | kind: transition-reason | actor: be-developer

Transition: In Review -> Ready for Development. Reason: gate reject — AC#2 not met, tests failed

### 2026-07-26T00:02:00Z | kind: transition-reason | actor: be-developer

Transition: In Review -> Ready for Development. Reason: spawn crashed (error_max_turns); connection timeout

### 2026-07-26T00:03:00Z | kind: transition-reason | actor: be-developer

Transition: In Review -> Ready for Development. Reason: handoff mis-report: claimed commits do not verify; undoing the self-transition back to In Review'

_pilot69_rework() {
    bash -c '
        source "$1" >/dev/null 2>&1
        printf "%s" "$2" | { read -r _; :; }
        n="$(rework_count "$2")"
        printf "rework=%s\n" "$n"
    ' _p69 "$ORCH" "$_pilot69_dump"
}
_p69_o1="$(_pilot69_rework)"
# 3 backward moves total; the transient one is excluded → 2 counted.
assert_eq "$(printf '%s\n' "$_p69_o1" | grep -o 'rework=[0-9]*' | cut -d= -f2)" "2" \
    "PILOT-69 AC1: transient/infra abort is budget-neutral; functional bounce + mis-report still count"

echo -e "\n${CYAN}=== PILOT-69 AC1: knob off restores pre-PILOT-69 counting ===${NC}\n"
_pilot69_rework_off() {
    bash -c '
        source "$1" >/dev/null 2>&1
        ORCH_REWORK_INFRA_RE=""
        n="$(rework_count "$2")"
        printf "rework=%s\n" "$n"
    ' _p69 "$ORCH" "$_pilot69_dump"
}
_p69_o1b="$(_pilot69_rework_off)"
assert_eq "$(printf '%s\n' "$_p69_o1b" | grep -o 'rework=[0-9]*' | cut -d= -f2)" "3" \
    "PILOT-69 AC1: with the infra regex empty all three backward moves count (regression-safe knob)"

echo -e "\n${CYAN}=== PILOT-69 AC1: reached_merge_tier detects the acceptance/merge tier ===${NC}\n"

_pilot69_reached() {
    bash -c '
        source "$1" >/dev/null 2>&1
        # (a) a ticket that reached Merging → finished
        finished="---
id: A
status: In Review
---
## Comments
### t | kind: transition-reason | actor: rte
Transition: Story Acceptance -> Merging. Reason: approved, merging
### t | kind: transition-reason | actor: rte
Transition: Merging -> Ready for Development. Reason: rebase needed"
        # (b) a ticket that never left implementation → not finished
        early="---
id: B
status: In Review
---
## Comments
### t | kind: transition-reason | actor: be-developer
Transition: In Review -> Ready for Development. Reason: AC not met"
        reached_merge_tier "$finished" && a=yes || a=no
        reached_merge_tier "$early"    && b=yes || b=no
        printf "finished=%s early=%s\n" "$a" "$b"
    ' _p69 "$ORCH"
}
_p69_o2="$(_pilot69_reached)"
assert_contains "$_p69_o2" "finished=yes" \
    "PILOT-69 AC1: reached_merge_tier is TRUE once the ticket entered the acceptance/merge tier"
assert_contains "$_p69_o2" "early=no" \
    "PILOT-69 AC1: reached_merge_tier is FALSE for work that never left implementation"
