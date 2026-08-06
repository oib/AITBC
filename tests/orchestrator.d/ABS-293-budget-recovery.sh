# =============================================================================
# ABS-293 — follow-up-budget exhaustion gets a RECOVERY PATH
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live on ABS-278, 2026-07-14)
# Budget exhaustion was a one-way door: the epic escalated ONCE
# (has_followup_budget_marker was a permanent latch), followup_budget_exhausted
# stayed true forever, so every LATER follow-up stranded with no bsa, no second
# escalation and no trace — and the epic's JOIN deadlocked permanently. The only
# way out (a PO posting `kind: bsa-decision` dispositions by hand) was
# documented nowhere and mechanized nowhere.
#
# WHAT ABS-293 ADDS
#   1. Visibility: a stranded follow-up gets a per-ordinal FOLLOWUP-STRANDED
#      marker on its ticket (no silent stranding).
#   2. Recovery A (documented + pinned here): a `kind: bsa-decision` reply
#      lowers the pending count — the de-facto path, now a contract.
#   3. Recovery B: FOLLOWUP-BUDGET-RESET (triage) in the BODY of a
#      `kind: decision` comment on the epic re-arms one further full budget —
#      a declarable triage act, no mid-run env change.
#   4. The re-raise guard becomes GENERATION-aware: one escalation per budget
#      generation (never a storm, but never a permanent latch either).
# =============================================================================

echo -e "\n${CYAN}=== ABS-293 follow-up-budget recovery ===${NC}\n"

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_FOLLOWUP_BUDGET=1
E=$(tracker create --type epic --title "ABS-293 budget-recovery epic")
A=$(tracker create --type ticket --title "ABS-293 story" --parent "$E")
baseline

# --- exhaustion: budget=1, follow-up #1 consumes it, #2 escalates + strands ---
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
tracker comment "$A" --kind follow-up --actor qas --body "finding 2" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$E" "ABS-293: budget exhaustion escalates the epic (unchanged ABS-75 control)"
assert_contains "$out" "INTENT FOLLOWUP-STRANDED ticket=$A" "ABS-293 AC1: the stranded follow-up is named in the intent stream"
dump=$(tracker get "$A")
assert_contains "$dump" "FOLLOWUP-STRANDED n=2" "ABS-293 AC1: stranding is VISIBLE on the ticket (per-ordinal marker)"
assert_contains "$dump" "kind: bsa-decision" "ABS-293 AC2: the stranded marker names the bsa-decision recovery path"
assert_contains "$dump" "FOLLOWUP-BUDGET-RESET" "ABS-293 AC2: the stranded marker names the budget re-arm recovery path"

# --- re-raise guard (AC3): the next sweep neither re-escalates nor re-marks ---
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT FOLLOWUP-BUDGET ticket=$E" "ABS-293 AC3: no escalation storm — one escalation per budget generation"
stranded_count=$(tracker get "$A" | grep -c "FOLLOWUP-STRANDED n=2" || true)
assert_eq "$stranded_count" "1" "ABS-293 AC3: exactly one stranded marker per follow-up (dedupe holds)"

# --- recovery A (AC2, pinned): a PO disposition lowers the pending count ------
# Both follow-ups are still undecided at this point (a bsa SPAWN is not an
# answer; only a kind:bsa-decision reply is), so pending = 2.
pending_before=$( ( source "$ORCH" >/dev/null 2>&1; followup_pending_count "$(tracker get "$A")" ) )
tracker comment "$A" --kind bsa-decision --actor po-agent \
    --body "Disposition: finding folded into ABS-999; no new story." >/dev/null
pending_after=$( ( source "$ORCH" >/dev/null 2>&1; followup_pending_count "$(tracker get "$A")" ) )
assert_eq "$pending_before" "2" "ABS-293 AC2: two follow-ups pending before the PO disposition"
assert_eq "$pending_after" "1" "ABS-293 AC2: a kind:bsa-decision reply LOWERS the pending count (the documented recovery path)"

# --- recovery B: a declared FOLLOWUP-BUDGET-RESET re-arms one full budget -----
exhausted_before=$( ( source "$ORCH" >/dev/null 2>&1; followup_budget_exhausted "$E" && echo yes || echo no ) )
tracker comment "$E" --kind decision --actor po-agent \
    --body "PO triage: dispositions cleared; re-arming the follow-up budget [FOLLOWUP-BUDGET-RESET (triage)] (ABS-293)." >/dev/null
exhausted_after=$( ( source "$ORCH" >/dev/null 2>&1; followup_budget_exhausted "$E" && echo yes || echo no ) )
assert_eq "$exhausted_before" "yes" "ABS-293: budget reads exhausted before the re-arm"
assert_eq "$exhausted_after" "no" "ABS-293: a declared FOLLOWUP-BUDGET-RESET re-arms the budget (no env change mid-run)"

# --- the re-armed budget SPAWNS again, and a SECOND exhaustion escalates again
# The formerly-stranded follow-up #2 is still unanswered (the disposition above
# answered ordinal #1) and unmarked — with the re-armed headroom of one, the
# next sweep now spawns bsa for it.
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out3" "INTENT SPAWN ticket=$A role=bsa" "ABS-293: after the re-arm the watcher spawns bsa again"
tracker comment "$A" --kind follow-up --actor qas --body "finding 3" >/dev/null
out4=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out4" "INTENT FOLLOWUP-BUDGET ticket=$E" "ABS-293: a second exhaustion escalates ONCE MORE (generation-aware guard, not a permanent latch)"
out5=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out5" "INTENT FOLLOWUP-BUDGET ticket=$E" "ABS-293 AC3: and the second generation's guard holds on the next sweep"

cleanup_env

# A quoted reset token OUTSIDE a kind:decision body must NOT re-arm (anchoring).
new_env
export ORCH_FOLLOWUP_BUDGET=1
E2=$(tracker create --type epic --title "ABS-293 anchoring epic")
baseline
tracker comment "$E2" --kind follow-up --actor qas \
    --body "mentions FOLLOWUP-BUDGET-RESET (triage) in prose — must not count" >/dev/null
resets=$( ( source "$ORCH" >/dev/null 2>&1; followup_budget_reset_count "$E2" ) )
assert_eq "$resets" "0" "ABS-293: the reset token only counts in the BODY of a kind:decision comment (quote-proof anchoring)"
cleanup_env
unset ORCH_FOLLOWUP_BUDGET
