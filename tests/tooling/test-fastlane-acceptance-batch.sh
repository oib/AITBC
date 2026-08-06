#!/bin/bash
# =============================================================================
# Test: Async Fastlane PO-Acceptance daily batch (ABS-323, epic ABS-314 v3)
# =============================================================================
# Drives scripts/fastlane-acceptance-batch.sh against an isolated mock-tracker
# store and asserts the acceptance criteria of ABS-323:
#   AC1  fastlane tickets past the merge-queue (rest at Docs) accumulate into the
#        batch listing; a fastlane ticket NOT past the gate and a normal-lane Docs
#        ticket are NOT listed (batch is fastlane + past-merge-queue only)
#   AC2  accept/reject record a per-ticket `kind: decision` comment with reasoning
#   AC3  acceptance runs ONLY after the combined gate + merge-queue — a gate-less
#        fastlane ticket is not in the batch AND `accept` refuses it
#   AC4  reject increments the ABS-74 rework counter (backward po-agent transition
#        Docs -> Ready for Development) and routes back to development w/ defects
#   AC5  accept grants NO merge authority — no transition, ticket stays at Docs
#        (still awaiting the human merge gate)
# plus guardrails: unknown action / missing reason / normal-lane / double-decide.
#
# Run from repo root: bash tests/test-fastlane-acceptance-batch.sh
# bash 3.2 / BSD-tool safe.
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BATCH="$REPO_ROOT/scripts/fastlane-acceptance-batch.sh"
MOCK="$REPO_ROOT/scripts/mock-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/fastlane-accept-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$MOCK"

# the batch script writes draft files to work/scratch relative to CWD; isolate.
cd "$TEST_DIR" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}FAIL${NC} $1"; }
expect() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected '$2', got '$1')"; fi; }

mock()  { bash "$MOCK" "$@"; }
batch() { bash "$BATCH" "$@"; }
newid() { mock create "$@" | tail -1; }
status_of() { mock get "$1" | awk 'NR==1&&$0=="---"{f=1;next} f&&$0=="---"{exit} f' | grep -E '^status:' | head -1 | sed -E 's/^status:[[:space:]]*//'; }

# Drive a ticket through the legal v3 story chain to Docs (past the combined gate
# at In Review AND the merge-queue at Merging). Actors are illustrative.
drive_to_docs() {
    local id="$1"
    mock transition "$id" "Ready for Development" --actor po-agent  --reason "groomed"        >/dev/null
    mock transition "$id" "In Progress"           --actor be-developer --reason "start"       >/dev/null
    mock transition "$id" "In Review"             --actor be-developer --reason "combined gate">/dev/null
    mock transition "$id" "In Test"               --actor be-developer --reason "gate passed"  >/dev/null
    mock transition "$id" "Design Test"           --actor be-developer --reason "fold"         >/dev/null
    mock transition "$id" "Story Acceptance"      --actor be-developer --reason "fold"         >/dev/null
    mock transition "$id" "Merging"               --actor be-developer --reason "merge-queue"  >/dev/null
    mock transition "$id" "Docs"                  --actor rte          --reason "merged"       >/dev/null
}

echo -e "${CYAN}Async Fastlane PO-Acceptance daily batch (ABS-323)${NC}"

EPIC=$(newid --type epic --title "epic 314")

# --- AC1: fastlane tickets past the merge-queue accumulate into the batch -----
echo "AC1: batch lists fastlane tickets past the merge-queue"
T1=$(newid --type ticket --title "fastlane one"   --parent "$EPIC" --lane fastlane)
T2=$(newid --type ticket --title "fastlane two"   --parent "$EPIC" --lane fastlane)
drive_to_docs "$T1"; drive_to_docs "$T2"
# a normal-lane ticket also at Docs must NOT be in the batch
NRM=$(newid --type ticket --title "normal at docs" --parent "$EPIC")
drive_to_docs "$NRM"
# a fastlane ticket NOT past the gate (still In Progress) must NOT be in the batch
GATELESS=$(newid --type ticket --title "fastlane pre-gate" --parent "$EPIC" --lane fastlane)
mock transition "$GATELESS" "Ready for Development" --actor po-agent  --reason g >/dev/null
mock transition "$GATELESS" "In Progress"           --actor be-developer --reason w >/dev/null

LIST="$(batch list)"
printf '%s\n' "$LIST" | grep -qF "$T1" && ok "AC1 fastlane T1 in batch" || bad "AC1 T1 missing from batch"
printf '%s\n' "$LIST" | grep -qF "$T2" && ok "AC1 fastlane T2 in batch" || bad "AC1 T2 missing from batch"
printf '%s\n' "$LIST" | grep -qF "$NRM"      && bad "AC1 normal-lane ticket wrongly in batch" || ok "AC1 normal-lane ticket excluded"
printf '%s\n' "$LIST" | grep -qF "$GATELESS" && bad "AC3 gate-less ticket wrongly in batch"   || ok "AC3 gate-less ticket excluded from batch (not past merge-queue)"

# --- AC2 + AC5: accept records a decision, grants NO merge -------------------
echo "AC2/AC5: accept records decision + no merge"
printf '%s\n' "AC1 met: endpoint returns filtered rows; AC2 met: Zod rejects bad input (see QA evidence)." > "$TEST_DIR/accept.md"
batch accept "$T1" --reason-file "$TEST_DIR/accept.md" >/dev/null
D1="$(mock get "$T1")"
printf '%s\n' "$D1" | grep -qE '^fastlane-acceptance:[[:space:]]*accept' && ok "AC2 accept decision recorded" || bad "AC2 accept decision missing"
printf '%s\n' "$D1" | grep -qF "kind: decision"  && ok "AC2 decision is a kind:decision comment" || bad "AC2 decision comment kind wrong"
printf '%s\n' "$D1" | grep -qF "actor: po-agent" && ok "AC2 decision by po-agent"                || bad "AC2 decision actor wrong"
expect "$(status_of "$T1")" "Docs" "AC5 accept did NOT transition (no merge; still awaits human merge gate)"

# accepted ticket drops out of the next batch (no double-listing)
printf '%s\n' "$(batch list)" | grep -qF "$T1" && bad "AC5 accepted ticket re-listed" || ok "AC5 accepted ticket excluded from next batch"

# --- AC2 + AC4: reject records defects + rework bounce ----------------------
echo "AC2/AC4: reject records defects + routes back to development (rework counter)"
printf '%s\n' "Defect: AC3 unmet — RLS context helper missing on the DELETE path." > "$TEST_DIR/reject.md"
batch reject "$T2" --reason-file "$TEST_DIR/reject.md" >/dev/null
D2="$(mock get "$T2")"
printf '%s\n' "$D2" | grep -qE '^fastlane-acceptance:[[:space:]]*reject' && ok "AC2 reject decision recorded" || bad "AC2 reject decision missing"
printf '%s\n' "$D2" | grep -qF "RLS context helper missing" && ok "AC2 defect list captured" || bad "AC2 defect list missing"
expect "$(status_of "$T2")" "Ready for Development" "AC4 rejected ticket routed back to development"
# AC4: the ABS-74 rework counter (rework_count in orchestrator.sh) derives from
# exactly this backward, non-human/non-orchestrator transition-reason line.
printf '%s\n' "$D2" | awk '/^### / && /actor: po-agent/{a=1;next} /^### /{a=0} a && /^Transition: Docs -> Ready for Development\./{found=1} END{exit !found}' \
    && ok "AC4 backward po-agent transition present (rework counter input)" \
    || bad "AC4 rework-counter transition line missing"

# --- AC3: accept REFUSES a gate-less fastlane ticket ------------------------
echo "AC3: acceptance refused before the combined gate"
printf '%s\n' "premature" > "$TEST_DIR/pre.md"
batch accept "$GATELESS" --reason-file "$TEST_DIR/pre.md" >/dev/null 2>&1; rc=$?
expect "$rc" "2" "AC3 accept refused (exit 2) for a ticket not past the gate"

# --- guardrails -------------------------------------------------------------
echo "guardrails: invalid input rejected"
batch bogus >/dev/null 2>&1;                          expect "$?" "2" "unknown action rejected (exit 2)"
batch accept "$T1" >/dev/null 2>&1;                   expect "$?" "2" "accept without a reason rejected (exit 2)"
# a normal-lane ticket cannot be accepted via the fastlane batch
batch accept "$NRM" --reason "x" >/dev/null 2>&1;     expect "$?" "2" "normal-lane ticket refused (exit 2)"
# double-decide is refused (T2 already rejected -> but it moved off Docs; use T1
# which is accepted and still at Docs)
batch reject "$T1" --reason "y" >/dev/null 2>&1;      expect "$?" "2" "double-decide on an already-decided ticket refused (exit 2)"

# --- summary ----------------------------------------------------------------
echo ""
echo -e "${CYAN}Results:${NC} $PASS/$TOTAL passed"
[ "$FAIL" -eq 0 ] || { echo -e "${RED}$FAIL failed${NC}"; exit 1; }
echo -e "${GREEN}All ABS-323 acceptance criteria verified.${NC}"
