# =============================================================================
# ABS-298 — follow-up deadlocks: runtime-reloadable budget + marker-without-
#           decision repair. Both edits live in the same follow-up-watcher
#           region of orchestrator.sh (bundled per the spec's #PATH_DECISION).
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE TWO DEADLOCKS THIS PINS (retro ABS-279, Befund 4 — 2026-07-13)
#   Neither needed a runner restart (a restart orphans live seats — the cascade
#   observed that day). ABS-298 makes both recoverable in-flight:
#   (a) The per-epic follow-up budget is re-read each sweep from an optional
#       $ORCH_STATE_DIR/followup-budget state file. A raise takes effect on the
#       NEXT sweep with no restart; an epic already at overflow dispatches again.
#       Absent the file, ORCH_FOLLOWUP_BUDGET (default 5) governs exactly as
#       today.
#   (b) A FOLLOWUP-SPAWN marker whose bsa died BEFORE posting its
#       kind:bsa-decision is REPAIRED (the bsa is re-spawned for that ordinal)
#       once the marker is older than ORCH_FOLLOWUP_REPAIR_SECONDS and no live
#       seat lock holds the ticket — instead of being deduped away forever by
#       has_followup_marker() while the JOIN waits. 0 = off = today's behaviour.
#       The re-spawn routes through spawn_dispatch, so a repair that keeps dying
#       is bounded by ORCH_CRASH_LIMIT / ORCH_RESPAWN_LIMIT (no loop).
#
# AC coverage (spec §Acceptance Criteria):
#   AC1 — a higher budget in the state file raises the effective budget on the
#         NEXT sweep (no restart); an epic previously at overflow dispatches
#         again. FOLLOWUP-BUDGET-RELOAD audit line asserted.
#   AC2 — absent the state file, ORCH_FOLLOWUP_BUDGET governs exactly as today.
#   AC3 — repair: marker + no decision + no lock + age > threshold → re-spawn.
#   AC4 — no re-spawn while a live seat lock holds the ticket; no re-spawn once
#         a kind:bsa-decision reply exists (re-raise guard still holds).
#   AC5 — ORCH_FOLLOWUP_REPAIR_SECONDS=0 reproduces today's dedupe-forever.
#   AC6 — a repair re-spawn that dies again is capped by the crash limit.
# =============================================================================

echo -e "\n${CYAN}=== ABS-298 follow-up deadlock: budget reload + marker repair ===${NC}\n"

# ---------------------------------------------------------------------------
# AC1 — runtime budget raise via the state file takes effect on the NEXT sweep
#       (no restart) and re-dispatches an epic previously at overflow.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_FOLLOWUP_BUDGET=1
E=$(tracker create --type epic --title "ABS-298 reload epic")
A=$(tracker create --type ticket --title "ABS-298 reload story" --parent "$E")
baseline

# budget=1: follow-up #1 consumes the budget, #2 overflows → the epic escalates
# and #2 strands (unchanged ABS-75/ABS-293 control).
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
tracker comment "$A" --kind follow-up --actor qas --body "finding 2" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$E" \
    "ABS-298 AC1 setup: budget=1 overflows on follow-up #2 (epic escalates)"
assert_not_contains "$out" "INTENT SPAWN ticket=$A role=bsa" \
    "ABS-298 AC1 setup: follow-up #2 gets NO bsa spawn while the budget is exhausted"

# Operator raises the budget mid-run by dropping a value into the state file —
# no restart. The NEXT sweep must re-read it and dispatch the stranded follow-up.
mkdir -p "$ORCH_STATE_DIR"
echo 5 > "$ORCH_STATE_DIR/followup-budget"
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out2" "INTENT FOLLOWUP-BUDGET-RELOAD" \
    "ABS-298 AC1: the sweep re-reads the raised budget from the state file (no restart)"
assert_contains "$out2" "budget=5 (was 1" \
    "ABS-298 AC1: the reload audit line names the new and old effective budget"
assert_contains "$out2" "INTENT SPAWN ticket=$A role=bsa" \
    "ABS-298 AC1: the epic previously at overflow dispatches the stranded follow-up again"
# (Within a long-running runner process the global is updated once, so the RELOAD
# line dedupes across sweeps; each --once here is a fresh process re-reading the
# env, so cross-process dedupe is out of scope — the audit line is harmless.)
cleanup_env

# ---------------------------------------------------------------------------
# AC2 — absent the state file, ORCH_FOLLOWUP_BUDGET governs exactly as today.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_FOLLOWUP_BUDGET=1
E=$(tracker create --type epic --title "ABS-298 no-file epic")
A=$(tracker create --type ticket --title "ABS-298 no-file story" --parent "$E")
baseline

tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
tracker comment "$A" --kind follow-up --actor qas --body "finding 2" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT FOLLOWUP-BUDGET-RELOAD" \
    "ABS-298 AC2: no state file → no reload (env value stands, unchanged behaviour)"
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$E" \
    "ABS-298 AC2: env budget=1 escalates follow-up #2 exactly as today"
# A junk (non-numeric) state file must be ignored — the env value still governs.
mkdir -p "$ORCH_STATE_DIR"
echo "not-a-number" > "$ORCH_STATE_DIR/followup-budget"
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT FOLLOWUP-BUDGET-RELOAD" \
    "ABS-298 AC2: a non-numeric state file is ignored (env value untouched)"
cleanup_env

# ---------------------------------------------------------------------------
# AC3 — repair happy path: FOLLOWUP-SPAWN marker + no kind:bsa-decision + no
#       live lock + marker age > threshold → the watcher re-spawns the bsa.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "ABS-298 repair epic")
A=$(tracker create --type ticket --title "ABS-298 repair story" --parent "$E")
baseline

# One live sweep records a FOLLOWUP-SPAWN marker but no bsa-decision (the stub
# never posts one) — exactly the marker-without-decision state a died bsa leaves.
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
dump=$(tracker get "$A")
assert_contains "$dump" "FOLLOWUP-SPAWN n=1" \
    "ABS-298 AC3 setup: first sweep records the FOLLOWUP-SPAWN marker (no decision)"

# Age the marker past a 1-second threshold; no live lock is held (released after
# the synchronous spawn) → all repair conditions hold.
export ORCH_FOLLOWUP_REPAIR_SECONDS=1
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT FOLLOWUP-REPAIR ticket=$A" \
    "ABS-298 AC3: marker-without-decision past threshold → FOLLOWUP-REPAIR fires"
assert_contains "$out" "INTENT SPAWN ticket=$A role=bsa" \
    "ABS-298 AC3: the repair re-spawns the bsa for the stranded ordinal"

# Sub-case: a marker YOUNGER than the threshold is NOT repaired (the bsa spawned
# this sweep is given time to post its decision first).
export ORCH_FOLLOWUP_REPAIR_SECONDS=3600
export ORCH_NOW=$(( $(date -u +%s) + 5 ))
out_young=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_young" "INTENT FOLLOWUP-REPAIR ticket=$A" \
    "ABS-298 AC3: a marker younger than the threshold is not repaired"
cleanup_env

# ---------------------------------------------------------------------------
# AC4 — no re-spawn while a live seat lock holds the ticket; and no re-spawn
#       once a kind:bsa-decision reply exists (the re-raise guard still holds).
# ---------------------------------------------------------------------------

# AC4-a: live lock held → no repair.
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "ABS-298 lock epic")
A=$(tracker create --type ticket --title "ABS-298 lock story" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1

# Hold a FRESH lock (age 0 < ORCH_LOCK_TTL) → a still-live bsa may yet post its
# decision; the repair guard must refuse.
mkdir -p "$ORCH_STATE_DIR/locks/$A"
export ORCH_FOLLOWUP_REPAIR_SECONDS=1
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT FOLLOWUP-REPAIR ticket=$A" \
    "ABS-298 AC4: no repair while a live seat lock holds the ticket"
cleanup_env

# AC4-b: a kind:bsa-decision reply exists → no repair (re-raise guard holds).
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "ABS-298 decided epic")
A=$(tracker create --type ticket --title "ABS-298 decided story" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
# The bsa posts its disposition — the marker is now answered.
tracker comment "$A" --kind bsa-decision --actor bsa \
    --body "Disposition: folded into ABS-999; no new story." >/dev/null
export ORCH_FOLLOWUP_REPAIR_SECONDS=1
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT FOLLOWUP-REPAIR ticket=$A" \
    "ABS-298 AC4: no repair once a kind:bsa-decision reply exists (re-raise guard holds)"
assert_not_contains "$out" "INTENT SPAWN ticket=$A role=bsa" \
    "ABS-298 AC4: an answered follow-up is not re-spawned"
cleanup_env

# ---------------------------------------------------------------------------
# AC5 — ORCH_FOLLOWUP_REPAIR_SECONDS=0 reproduces today's dedupe-forever
#       behaviour (a marker-without-decision is skipped, never re-spawned).
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "ABS-298 knob-off epic")
A=$(tracker create --type ticket --title "ABS-298 knob-off story" --parent "$E")
baseline
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1

export ORCH_FOLLOWUP_REPAIR_SECONDS=0
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT FOLLOWUP-REPAIR ticket=$A" \
    "ABS-298 AC5: ORCH_FOLLOWUP_REPAIR_SECONDS=0 → no repair (knob off)"
assert_not_contains "$out" "INTENT SPAWN ticket=$A role=bsa" \
    "ABS-298 AC5: with the knob off the marker dedupes the ordinal forever (today's behaviour)"
cleanup_env

# ---------------------------------------------------------------------------
# AC6 — a repair re-spawn that keeps dying is bounded by ORCH_CRASH_LIMIT
#       (the crash cap escalates instead of looping forever).
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_LIMIT=2
export ORCH_FOLLOWUP_REPAIR_SECONDS=1
A=$(tracker create --type ticket --title "ABS-298 bounded-repair story")
baseline

# First sweep (stub succeeds) records the FOLLOWUP-SPAWN marker cleanly.
tracker comment "$A" --kind follow-up --actor qas --body "finding 1" >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
assert_contains "$(tracker get "$A")" "FOLLOWUP-SPAWN n=1" \
    "ABS-298 AC6 setup: initial spawn records the marker"

# Now every repair re-spawn crashes. Run several sweeps; the crash cap must
# escalate and then quiesce (halt) the ticket rather than re-spawn every sweep.
STUB_RECORD_FILE="$TEST_DIR/rec_bounded.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
export STUB_FAIL=1
crash_out=""
for _ in 1 2 3 4 5 6; do
    export ORCH_NOW=$(( $(date -u +%s) + 600 ))
    crash_out="$crash_out
$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)"
done
assert_contains "$crash_out" "INTENT CRASH-LIMIT ticket=$A" \
    "ABS-298 AC6: repeated repair crashes hit ORCH_CRASH_LIMIT (the cap fires — no infinite loop)"

# Prove quiescence: after the cap has fired, ONE further crash sweep records NO
# new spawn attempt (the ticket is halted). A genuinely unbounded loop would
# re-spawn on this sweep too.
before=$(grep -c "	$A" "$STUB_RECORD_FILE" 2>/dev/null || echo 0)
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1 || true
after=$(grep -c "	$A" "$STUB_RECORD_FILE" 2>/dev/null || echo 0)
unset STUB_FAIL
assert_eq "$after" "$before" \
    "ABS-298 AC6: after the cap fires the repair re-spawn is bounded — a further sweep spawns nothing ($before → $after)"
cleanup_env
unset ORCH_FOLLOWUP_BUDGET ORCH_FOLLOWUP_REPAIR_SECONDS
