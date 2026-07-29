# =============================================================================
# ABS-295 — CRASH-REPAIR: reconcile sweep routes orphaned In Progress tickets
#           back to their origin station when the runner's own crash record
#           proves the seat is dead.
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# WHAT ABS-295 ADDS
#   A narrowly-gated CRASH-REPAIR edge in the reconcile sweep. Four conditions
#   must ALL hold for the repair to fire:
#     1. A runner-own SPAWN-CRASH gate-results comment exists (crash_marker_body
#        now embeds instance= so condition 4 can be verified).
#     2. No live seat lock, or lock is stale (age >= ORCH_LOCK_TTL).
#     3. Crash age >= ORCH_CRASH_REPAIR_SECONDS (0 = off = NOTIFY-only today).
#     4. Marker's instance= == own ORCH_INSTANCE_ID (two-runner safety).
#   Repair is idempotent (CRASH-REPAIR comment is the dedup key).
#   STUCK-DETECT NOTIFY (check_stuck) is UNCHANGED.
#
# AC coverage:
#   AC1 — happy path: all 4 conditions met → transition to origin status.
#   AC2 — one negative case for each failed condition (4 cases).
#   AC3 — ORCH_CRASH_REPAIR_SECONDS=0 → NOTIFY only, no transition.
#   AC4 — audit comment naming crash time, session id, origin status; and
#          CRASH-REPAIR intent line in stdout; both verified.
#   AC5 — idempotent: second sweep does not transition again.
# =============================================================================

echo -e "\n${CYAN}=== ABS-295 CRASH-REPAIR reconcile sweep ===${NC}\n"

# _crash_ts <ticket> — extract the server timestamp from the most recent
# orchestrator gate-results SPAWN-CRASH comment. Adapter-only awk.
_crash_ts() {
    tracker get "$1" | awk '
        /^### / {
            n = split($0, f, " ")
            cur = (n >= 2 ? f[2] : "")
            in_crash = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/)
            next
        }
        in_crash && /SPAWN-CRASH status=/ { print cur; in_crash = 0 }
    '
}

# _crash_epoch <ticket> — unix epoch of the most recent SPAWN-CRASH comment.
_crash_epoch() {
    local ts; ts="$(_crash_ts "$1")"
    [ -n "$ts" ] || { echo 0; return; }
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$ts" +%s 2>/dev/null \
        || date -u -d "$ts" +%s 2>/dev/null \
        || echo 0
}

# _drive_crash <ticket> — make the spawn fail twice so record_spawn_crash
# posts a SPAWN-CRASH marker with the current ORCH_INSTANCE_ID embedded.
_drive_crash() {
    local t="$1"
    export STUB_FAIL=1
    ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1 || true
    unset STUB_FAIL
}

# ---------------------------------------------------------------------------
# AC1: happy path — all 4 conditions met → transition to origin status
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-happy"

T=$(tracker create --type ticket --title "ABS-295 happy-path subject")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null

# Condition 1: drive SPAWN-CRASH marker (instance=test-instance-abs295-happy embedded).
_drive_crash "$T"

# Simulate seat having claimed In Progress before dying.
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

# Condition 3: advance ORCH_NOW so crash age >> threshold (1 s).
export ORCH_NOW=$(( $(_crash_epoch "$T") + 120 ))

# No lock (condition 2) and same instance (condition 4) are satisfied by default.
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC1: all 4 conditions met → CRASH-REPAIR intent in stdout"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" \
    "ABS-295 AC1: ticket routed back to origin status (Ready for Development)"
cleanup_env

# ---------------------------------------------------------------------------
# AC2-a: no crash marker → no repair
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-a"

T=$(tracker create --type ticket --title "ABS-295 no-marker")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
# No _drive_crash call — ticket goes directly to In Progress with no SPAWN-CRASH comment.
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed" >/dev/null
export ORCH_NOW=$(( $(date -u +%s) + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC2-a: no crash marker → no repair"
cleanup_env

# ---------------------------------------------------------------------------
# AC2-b: live lock held → no repair
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-b"

T=$(tracker create --type ticket --title "ABS-295 live-lock")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

# Hold a fresh lock: age 0 < ORCH_LOCK_TTL (4000 s) → condition 2 fails.
mkdir -p "$ORCH_STATE_DIR/locks/$T"

export ORCH_NOW=$(( $(_crash_epoch "$T") + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC2-b: live lock held → no repair (condition 2 fails)"
cleanup_env

# ---------------------------------------------------------------------------
# AC2-c: crash age < threshold → no repair
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=3600   # 1-hour threshold
export ORCH_INSTANCE_ID="test-instance-abs295-c"

T=$(tracker create --type ticket --title "ABS-295 too-young")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

# ORCH_NOW = crash epoch + 5 s, well below 3600 s threshold.
export ORCH_NOW=$(( $(_crash_epoch "$T") + 5 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC2-c: crash age < threshold → no repair (condition 3 fails)"
cleanup_env

# ---------------------------------------------------------------------------
# AC2-d: foreign instance id in the marker → no repair
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="instance-runner-A"

T=$(tracker create --type ticket --title "ABS-295 foreign-instance")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
# Drive crash with runner-A → marker embeds instance=instance-runner-A.
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

# Repair sweep runs as a DIFFERENT runner (condition 4 fails).
export ORCH_INSTANCE_ID="instance-runner-B"
export ORCH_NOW=$(( $(_crash_epoch "$T") + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC2-d: foreign instance id → no repair (two-runner safety, condition 4 fails)"
cleanup_env

# ---------------------------------------------------------------------------
# AC3: ORCH_CRASH_REPAIR_SECONDS=0 → NOTIFY-only behaviour (no repair)
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=0
export ORCH_STUCK_SWEEPS=1   # fire stuck-detect on first eligible sweep
export ORCH_INSTANCE_ID="test-instance-abs295-knob"

T=$(tracker create --type ticket --title "ABS-295 knob-off")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

export ORCH_NOW=$(( $(_crash_epoch "$T") + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC3: ORCH_CRASH_REPAIR_SECONDS=0 → no repair (knob off)"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: In Progress" \
    "ABS-295 AC3: ticket stays In Progress when repair knob is off"
cleanup_env

# ---------------------------------------------------------------------------
# AC4: repair posts audit comment naming crash time, session id, origin status;
#      and emits a CRASH-REPAIR runlog line — both asserted.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-audit"

T=$(tracker create --type ticket --title "ABS-295 audit-evidence")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

export ORCH_NOW=$(( $(_crash_epoch "$T") + 60 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)

# Audit comment checks (on the ticket dump).
dump=$(tracker get "$T")
assert_contains "$dump" "CRASH-REPAIR instance=" \
    "ABS-295 AC4: CRASH-REPAIR audit comment posted on ticket"
assert_contains "$dump" "crash-time=" \
    "ABS-295 AC4: audit comment names crash time"
assert_contains "$dump" "session=test-instance-abs295-audit" \
    "ABS-295 AC4: audit comment names session id"
assert_contains "$dump" "origin=Ready for Development" \
    "ABS-295 AC4: audit comment names origin status"

# CRASH-REPAIR intent asserted from stdout (captures the runlog-equivalent line
# the intent() helper emits to stdout for test assertions, ABS-295 §spec).
assert_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC4: CRASH-REPAIR intent line present in stdout (runlog line verified)"
cleanup_env

# ---------------------------------------------------------------------------
# AC5: idempotent — second sweep does not transition again
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-idem"

T=$(tracker create --type ticket --title "ABS-295 idempotency")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

export ORCH_NOW=$(( $(_crash_epoch "$T") + 60 ))

# First sweep: repair fires.
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1

# Verify repair happened.
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" \
    "ABS-295 AC5 setup: first sweep repaired the ticket"

# Push the ticket back to In Progress to test the idempotency guard directly:
# with the CRASH-REPAIR comment present, a second sweep must NOT transition again.
tracker transition "$T" "In Progress" --actor be-developer --reason "re-claim for idempotency test" >/dev/null

out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC5: CRASH-REPAIR comment present → second sweep is idempotent (no re-transition)"
cleanup_env

# ---------------------------------------------------------------------------
# AC-MULTI-1: two own markers (older + newer, different origins) → repair
#             routes to the NEWER marker's origin, not the stale oldest one.
# (Exercises CRITICAL-1 fix — last-wins in awk END block.)
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-multi"

T=$(tracker create --type ticket --title "ABS-295 multi-marker newest-wins")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null

# Post an OLDER crash marker recording a stale origin (Backlog — wrong station).
tracker comment "$T" --kind gate-results --actor orchestrator \
    --body "SPAWN-CRASH status=Backlog role=po-agent instance=test-instance-abs295-multi (orchestrator): spawn failed twice (non-zero exit or no parseable handoff, §6). Ticket rests in 'Backlog'; the reconciliation sweep re-derives the spawn." >/dev/null

# Drive a NEWER crash at the correct origin (Ready for Development).
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null

# Set ORCH_NOW far enough ahead that the age check passes for any marker.
export ORCH_NOW=$(( $(date -u +%s) + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC-MULTI-1: two own markers → CRASH-REPAIR fires"
status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$status" "status: Ready for Development" \
    "ABS-295 AC-MULTI-1: repair routes to NEWER marker's origin (Ready for Development, not stale Backlog)"
cleanup_env

# ---------------------------------------------------------------------------
# AC-MULTI-2: repair fires for episode 1; a NEW crash marker appears later ->
#             subsequent sweep repairs again; repeat sweep with no new marker
#             stays idempotent.
# (Exercises CRITICAL-2 fix -- episode-scoped dedup key per crash-time.)
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-recrash"
# Prevent HANDOFF-NOMOVE / crash-count escalations from confounding the
# repair assertion: two repair cycles cause 2 nomove markers on the ticket
# (the event loop dispatches the stub after each repair), which hits the
# default ORCH_RESPAWN_LIMIT=2 and escalates to NPD before the idempotency
# step can run. Pin both limits high to isolate the crash-repair logic.
export ORCH_RESPAWN_LIMIT=100
export ORCH_CRASH_LIMIT=100

T=$(tracker create --type ticket --title "ABS-295 repeat-crash re-repair")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null

# Episode 1: first crash -> marker 1 (crash_ts_1); repair fires.
_drive_crash "$T"
tracker transition "$T" "In Progress" --actor be-developer --reason "first seat claimed" >/dev/null
export ORCH_NOW=$(( $(date -u +%s) + 600 ))
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
ep1_status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$ep1_status" "status: Ready for Development" \
    "ABS-295 AC-MULTI-2 setup: episode-1 repair landed"

# Episode 2: post a NEW crash marker directly (crash_ts_2 is a fresh timestamp).
# The event-polling state already consumed the RfD event from episode-1's repair
# sweep (that sweep's event loop also dispatched the repaired ticket), so a second
# _drive_crash call would find no events to dispatch and produce no new marker.
# Posting manually gives us crash_ts_2 != crash_ts_1 -- the minimal condition
# needed to verify that the episode-scoped dedup key (crash-time=) does not block
# the second repair.
# sleep 1: mock-tracker timestamp() has 1-second (%S) resolution. Without it,
# crash_ts_2 == crash_ts_1 on any fast machine; the dedup grep in
# check_crash_repair matches episode-1's CRASH-REPAIR comment and blocks
# episode-2 repair. Root cause of AC-MULTI-2 flakiness (ABS-295 Stage 2).
sleep 1
tracker comment "$T" --kind gate-results --actor orchestrator \
    --body "SPAWN-CRASH status=Ready for Development role=be-developer instance=test-instance-abs295-recrash (orchestrator): spawn failed twice (non-zero exit or no parseable handoff, section 6). Ticket rests in 'Ready for Development'; the reconciliation sweep re-derives the spawn (ABS-74)." >/dev/null
# || true: ROOT CAUSE of ABS-370's ABS-295->296 false-green death. This "second
# seat claimed" transition assumes episode-1's repair (above) routed the ticket
# back to 'Ready for Development'. When that repair does NOT land (a flake), the
# ticket is still 'In Progress' and this becomes a same-status transition, which
# the mock tracker rejects non-zero (mock-tracker.sh) — aborting the whole suite
# under set -e before the tally prints. Guard it so a stale state produces a loud
# assertion failure below, never a silent suite death (same idiom as line ~372).
tracker transition "$T" "In Progress" --actor be-developer --reason "second seat claimed" >/dev/null || true
export ORCH_NOW=$(( $(date -u +%s) + 600 ))

# Repair sweep for episode 2: dedup key is crash-time=crash_ts_2 (new episode).
# The existing CRASH-REPAIR comment carries crash-time=crash_ts_1 -> no match -> fires.
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out2" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC-MULTI-2: new crash episode -> repair fires again (episode-scoped dedup)"
ep2_status=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$ep2_status" "status: Ready for Development" \
    "ABS-295 AC-MULTI-2: episode-2 repair routed ticket back to origin"

# Repeat sweep of same episode: crash_ts_2 CRASH-REPAIR comment now exists ->
# dedup key matches -> repair must NOT fire (idempotent).
# || true: same-status transition exits non-zero (mock tracker line 586).
# If episode-2 repair did not fire, the ticket sits at In Progress; the
# canonical runner's set -e kills the suite before the tally prints.
tracker transition "$T" "In Progress" --actor be-developer --reason "re-claim for idempotency test" >/dev/null || true
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out3" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC-MULTI-2: same crash episode -> repeat sweep is idempotent"
cleanup_env

# ---------------------------------------------------------------------------
# AC-MULTI-3: a FOREIGN runner's CRASH-REPAIR comment does NOT block own repair.
# (Exercises CRITICAL-2 fix — instance= scoping in the dedup grep.)
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-ours"

T=$(tracker create --type ticket --title "ABS-295 foreign-repair-block")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
_drive_crash "$T"
crash_ts=$(_crash_ts "$T")
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed" >/dev/null

# A FOREIGN runner posts its own CRASH-REPAIR comment (different instance=).
tracker comment "$T" --kind gate-results --actor orchestrator \
    --body "CRASH-REPAIR instance=foreign-runner crash-time=${crash_ts} session=foreign-runner origin=Ready for Development: foreign runner's own repair; should not block ours." >/dev/null

export ORCH_NOW=$(( $(date -u +%s) + 600 ))

# Our runner's repair must still fire — episode key differs (our instance != foreign-runner).
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC-MULTI-3: foreign CRASH-REPAIR comment does not block own repair (instance-scoped dedup)"
cleanup_env

# ---------------------------------------------------------------------------
# AC-MULTI-4: marker origin == current status → no transition, no comment.
# (Exercises MEDIUM-4 fix — same-status no-op guard.)
# A resume spawn on an orphaned In Progress ticket writes status=In Progress;
# transitioning In Progress → In Progress would be bogus and burn the dedup key.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_CRASH_REPAIR_SECONDS=1
export ORCH_INSTANCE_ID="test-instance-abs295-samestat"

T=$(tracker create --type ticket --title "ABS-295 same-status no-op")
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason "seat claimed" >/dev/null

# Post a crash marker whose origin == current status (resume spawn crashed while
# ticket was already In Progress — the same-status no-op scenario).
tracker comment "$T" --kind gate-results --actor orchestrator \
    --body "SPAWN-CRASH status=In Progress role=be-developer instance=test-instance-abs295-samestat (orchestrator): spawn failed twice (non-zero exit or no parseable handoff, §6). Ticket rests in 'In Progress'; the reconciliation sweep re-derives the spawn." >/dev/null

export ORCH_NOW=$(( $(date -u +%s) + 600 ))

out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT CRASH-REPAIR ticket=$T" \
    "ABS-295 AC-MULTI-4: marker origin == current status → no repair (same-status no-op guard)"
st=$(tracker get "$T" | grep '^status:' | head -1)
assert_eq "$st" "status: In Progress" \
    "ABS-295 AC-MULTI-4: ticket remains In Progress when origin == current status"
cleanup_env

# Tidy up helpers (they are shell functions, not commands).
unset -f _crash_ts _crash_epoch _drive_crash 2>/dev/null || true
