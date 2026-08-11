#!/usr/bin/env bash
# =============================================================================
# Test: backend-shipper.sh tail -F wake-driven follow (ABS-506 / PILOT-31, S6)
# =============================================================================
# Drives scripts/backend-shipper.sh with a STUBBED backend (BACKEND_CURL points
# at a fake curl that records every POST with a receive timestamp and answers the
# command poll with an empty queue). No Docker needed: the only acts under test
# are LOCAL file follow + cursor bookkeeping; the ingest POST is stubbed.
#
#   AC1: a new run.log line reaches an ingest POST in < 2s (wake, not 5s poll).
#   AC2: truncate/rotation of run.log → the fresh file ships from line 1 with no
#        lost and no duplicated events (cursor-reset belief).
#   AC3: a 500-line burst POSTs as batches (<= SHIPPER_BATCH_SIZE), not 500
#        single POSTs, and every one of the 500 events is shipped exactly once.
#   AC4: SHIPPER_TAIL=0 restores the legacy fixed sleep loop (still ships).
#   AC5: a spawn ledger file created mid-run (after the tail pipe is up) reaches
#        an ingest POST within the discovery latency (<= SHIPPER_POLL_INTERVAL),
#        with no loss of lines written before discovery.
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHIPPER="$REPO_ROOT/scripts/backend-shipper.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_le() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -le "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3 ($1 <= $2)"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected <= $2, got $1)"; FAIL=$((FAIL + 1)); fi
}
assert_ge() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -ge "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3 ($1 >= $2)"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected >= $2, got $1)"; FAIL=$((FAIL + 1)); fi
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/ship-tail-XXXXXX")"
BG_PID=""
cleanup() {
    [ -n "$BG_PID" ] && pkill -P "$BG_PID" 2>/dev/null
    [ -n "$BG_PID" ] && kill "$BG_PID" 2>/dev/null
    rm -rf "$TMP"
}
trap cleanup EXIT

# --- Fake curl: records POSTs (URL + body) to $FAKE_POST_LOG, answers GET. ----
FAKE_CURL="$TMP/fake-curl.sh"
cat > "$FAKE_CURL" <<'FAKE'
#!/usr/bin/env bash
out=""; is_post=0; url=""; data=""
args=("$@"); i=0
while [ "$i" -lt "${#args[@]}" ]; do
    a="${args[$i]}"
    case "$a" in
        -o)            i=$((i+1)); out="${args[$i]}" ;;
        -X)            i=$((i+1)); [ "${args[$i]}" = "POST" ] && is_post=1 ;;
        --data-binary) i=$((i+1)); data="${args[$i]}" ;;
        http://*|https://*) url="$a" ;;
    esac
    i=$((i+1))
done
if [ "$is_post" -eq 1 ]; then
    # One record per POST: URL <TAB> body. Line-atomic append.
    printf '%s\t%s\n' "$url" "$data" >> "$FAKE_POST_LOG"
    [ -n "$out" ] && printf '{"ok":true}' > "$out"
    printf '201'
else
    # GET command poll → empty queue.
    [ -n "$out" ] && printf '{"commands":[]}' > "$out"
    printf '200'
fi
FAKE
chmod +x "$FAKE_CURL"

POST_LOG=""   # set per-section by base_env (isolated so counts never accumulate)

# Count run.log telemetry events shipped so far (one "source":"run.log" per event).
count_runlog_events() { grep -o '"source":"run.log"' "$POST_LOG" 2>/dev/null | wc -l | tr -d ' '; }
# Count telemetry ingest POSTs (request count, not event count).
count_ingest_posts() { grep -c 'telemetry/events' "$POST_LOG" 2>/dev/null | head -1; }
# Count occurrences of a marker string anywhere in the POST bodies.
count_marker() { grep -o "$1" "$POST_LOG" 2>/dev/null | wc -l | tr -d ' '; }

base_env() {
    export BACKEND_URL="http://localhost:9"      # never contacted (curl is stubbed)
    export BACKEND_TOKEN="tok"
    export TRACKER_PROJECT="SHIP"
    export BACKEND_CURL="$FAKE_CURL"
    POST_LOG="$STATE/posts.log"; : > "$POST_LOG"   # isolated per section
    export FAKE_POST_LOG="$POST_LOG"
    export ORCH_STATE_DIR="$STATE"
    export ORCH_RUN_LOG="$STATE/run.log"
    export SHIPPER_CURSOR_FILE="$STATE/cursor"
    export SHIPPER_COMMANDS=0                     # no instance id → command channel off anyway
}

RUN_ID="20260725T000000-1234-1"

# ---------------------------------------------------------------------------
# AC1: a new run.log line reaches an ingest POST in < 2s.
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC1: new line → ingest POST < 2s (wake, not poll) ===${NC}"
STATE="$TMP/ac1"; mkdir -p "$STATE"; base_env
export SHIPPER_FOLLOW=1 SHIPPER_TAIL=1 SHIPPER_POLL_INTERVAL=5 SHIPPER_COALESCE_INTERVAL=1
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"

"$FAKE_CURL" >/dev/null 2>&1  # warm the interpreter cache (negligible)
bash "$SHIPPER" >/dev/null 2>&1 &
BG_PID=$!

# Wait for the initial drain (RUN-START event shipped) → shipper now in follow loop.
for _ in $(seq 1 50); do [ "$(count_runlog_events)" -ge 1 ] && break; sleep 0.1; done
assert_ge "$(count_runlog_events)" 1 "AC1: initial drain shipped the RUN-START event"

start_ts="$(date +%s)"
printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=WAKEMARK1\n' "2026-07-25T00:00:10Z" >> "$ORCH_RUN_LOG"
found=0
for _ in $(seq 1 40); do  # up to 4s cap
    if [ "$(count_marker WAKEMARK1)" -ge 1 ]; then found=1; break; fi
    sleep 0.1
done
elapsed=$(( $(date +%s) - start_ts ))
assert_eq "$found" "1" "AC1: appended line was shipped"
assert_le "$elapsed" "2" "AC1: latency under 2s"

pkill -P "$BG_PID" 2>/dev/null; kill "$BG_PID" 2>/dev/null; wait "$BG_PID" 2>/dev/null; BG_PID=""

# ---------------------------------------------------------------------------
# AC5: a ledger file created MID-RUN reaches ingest within the poll interval.
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC5: mid-run new ledger file discovered within poll interval ===${NC}"
STATE="$TMP/ac5"; mkdir -p "$STATE"; base_env
export SHIPPER_FOLLOW=1 SHIPPER_TAIL=1 SHIPPER_POLL_INTERVAL=2 SHIPPER_COALESCE_INTERVAL=1
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
bash "$SHIPPER" >/dev/null 2>&1 &
BG_PID=$!
for _ in $(seq 1 50); do [ "$(count_runlog_events)" -ge 1 ] && break; sleep 0.1; done

# Ledger file does NOT exist when tail starts — create it mid-run.
TODAY="$(date -u +%Y%m%d)"
LEDGER="$STATE/spawn-ledger-$TODAY"
start_ts="$(date +%s)"
printf '%s run_id=%s ABS-506 be-developer LEDGERNEW\n' "2026-07-25T00:00:20Z" "$RUN_ID" > "$LEDGER"
found=0
for _ in $(seq 1 60); do  # up to 6s cap
    if [ "$(count_marker LEDGERNEW)" -ge 1 ]; then found=1; break; fi
    sleep 0.1
done
elapsed=$(( $(date +%s) - start_ts ))
assert_eq "$found" "1" "AC5: mid-run ledger line was discovered and shipped (no loss)"
assert_le "$elapsed" "4" "AC5: discovery latency within poll interval (2s) + slack"
assert_eq "$(count_marker LEDGERNEW)" "1" "AC5: ledger line shipped exactly once (no duplicate)"

pkill -P "$BG_PID" 2>/dev/null; kill "$BG_PID" 2>/dev/null; wait "$BG_PID" 2>/dev/null; BG_PID=""

# ---------------------------------------------------------------------------
# AC3: 500-line burst → batched POSTs (<= batch size), all 500 shipped once.
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC3: 500-line burst → batched POSTs, no line-by-line ===${NC}"
STATE="$TMP/ac3"; mkdir -p "$STATE"; base_env
export SHIPPER_FOLLOW=1 SHIPPER_TAIL=1 SHIPPER_POLL_INTERVAL=5 SHIPPER_COALESCE_INTERVAL=1 SHIPPER_BATCH_SIZE=100
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
bash "$SHIPPER" >/dev/null 2>&1 &
BG_PID=$!
for _ in $(seq 1 50); do [ "$(count_runlog_events)" -ge 1 ] && break; sleep 0.1; done

# Burst: 500 payload lines in one append (single writer, atomic-ish).
{
    for n in $(seq 1 500); do
        printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=burst%s\n' "2026-07-25T00:01:00Z" "$n"
    done
} >> "$ORCH_RUN_LOG"

# Wait until all 501 run.log events (1 RUN-START + 500) are shipped.
for _ in $(seq 1 100); do [ "$(count_runlog_events)" -ge 501 ] && break; sleep 0.1; done
assert_eq "$(count_runlog_events)" "501" "AC3: all 500 burst lines shipped exactly once (+RUN-START)"
posts="$(count_ingest_posts)"
# 501 events / batch 100 = 6 batches; plus the initial RUN-START POST = ~7.
# The point: FAR fewer than 500 individual POSTs.
assert_le "$posts" "20" "AC3: shipped as batches, not 500 single POSTs"
assert_ge "$posts" "2" "AC3: more than one POST (batching, initial drain + burst)"

pkill -P "$BG_PID" 2>/dev/null; kill "$BG_PID" 2>/dev/null; wait "$BG_PID" 2>/dev/null; BG_PID=""

# ---------------------------------------------------------------------------
# AC2: truncate/rotation → fresh file ships from line 1, no loss, no duplicate.
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC2: truncate → no lost, no duplicated events ===${NC}"
STATE="$TMP/ac2"; mkdir -p "$STATE"; base_env
export SHIPPER_FOLLOW=0 SHIPPER_TAIL=1   # drain mode: deterministic cursor check
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=OLDA\n' "2026-07-25T00:00:01Z" >> "$ORCH_RUN_LOG"
printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=OLDB\n' "2026-07-25T00:00:02Z" >> "$ORCH_RUN_LOG"
bash "$SHIPPER" >/dev/null 2>&1
assert_eq "$(count_runlog_events)" "3" "AC2: first drain shipped 3 events"

# Rotate/truncate: replace the file with a SHORTER fresh one (cursor was 3).
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:10:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=NEWX\n' "2026-07-25T00:10:01Z" >> "$ORCH_RUN_LOG"
bash "$SHIPPER" >/dev/null 2>&1

assert_eq "$(count_marker NEWX)" "1" "AC2: post-truncate line shipped (no loss)"
assert_eq "$(count_marker OLDA)" "1" "AC2: pre-truncate line not re-shipped (no duplicate)"
assert_eq "$(count_runlog_events)" "5" "AC2: total events = 3 (pre) + 2 (post-truncate), none lost/dup"

# ---------------------------------------------------------------------------
# AC4: SHIPPER_TAIL=0 restores the legacy fixed sleep loop (still ships).
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC4: SHIPPER_TAIL=0 legacy sleep loop still ships ===${NC}"
STATE="$TMP/ac4"; mkdir -p "$STATE"; base_env
export SHIPPER_FOLLOW=1 SHIPPER_TAIL=0 SHIPPER_POLL_INTERVAL=1
printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
bash "$SHIPPER" >/dev/null 2>&1 &
BG_PID=$!
for _ in $(seq 1 50); do [ "$(count_runlog_events)" -ge 1 ] && break; sleep 0.1; done
printf '%s\tTELEMETRY\tABS-506\tbe-developer\tIn Review\tnote=SLEEPMARK\n' "2026-07-25T00:00:10Z" >> "$ORCH_RUN_LOG"
found=0
for _ in $(seq 1 40); do  # <=4s: poll interval is 1s
    if [ "$(count_marker SLEEPMARK)" -ge 1 ]; then found=1; break; fi
    sleep 0.1
done
assert_eq "$found" "1" "AC4: SHIPPER_TAIL=0 sleep loop shipped the new line"
pkill -P "$BG_PID" 2>/dev/null; kill "$BG_PID" 2>/dev/null; wait "$BG_PID" 2>/dev/null; BG_PID=""

# ---------------------------------------------------------------------------
# AC6 (regression): a follow-mode shipper MUST die on SIGTERM, in BOTH modes.
# ---------------------------------------------------------------------------
# The signal traps used to be registered as `trap '<cleanup>' EXIT INT TERM` with
# no `exit` in the handler. Bash runs such a handler and then RESUMES the loop, so
# the daemon ignored SIGTERM entirely: the caller's `kill` was swallowed and its
# `wait` blocked forever. This suite is what hung — for 42 minutes inside a
# pre-release check that has no per-suite timeout, so it hung the whole release
# gate rather than failing it. Asserted here for both loops; anything that does not
# terminate within the grace window is a FAIL, never an indefinite wait.
echo ""
echo -e "${CYAN}=== AC6: follow-mode shipper terminates on SIGTERM (both modes) ===${NC}"
for tail_mode in 1 0; do
    STATE="$TMP/ac6-$tail_mode"; mkdir -p "$STATE"; base_env
    export SHIPPER_FOLLOW=1 SHIPPER_TAIL="$tail_mode" SHIPPER_POLL_INTERVAL=1
    printf '%s\tRUN-START\t-\t-\t-\trun_id=%s\n' "2026-07-25T00:00:00Z" "$RUN_ID" > "$ORCH_RUN_LOG"
    bash "$SHIPPER" >/dev/null 2>&1 &
    BG_PID=$!
    # Let it reach its loop (ship at least the RUN-START line) before signalling.
    for _ in $(seq 1 50); do [ "$(count_runlog_events)" -ge 1 ] && break; sleep 0.1; done
    kill "$BG_PID" 2>/dev/null
    gone=0
    for _ in $(seq 1 50); do   # <=5s grace
        kill -0 "$BG_PID" 2>/dev/null || { gone=1; break; }
        sleep 0.1
    done
    assert_eq "$gone" "1" "AC6: SHIPPER_TAIL=$tail_mode shipper exited within 5s of SIGTERM"
    # Never leave a survivor behind, even when the assertion just failed.
    pkill -P "$BG_PID" 2>/dev/null; kill -9 "$BG_PID" 2>/dev/null; wait "$BG_PID" 2>/dev/null; BG_PID=""
done

# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$TOTAL tests passed"
    exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$TOTAL tests failed"
    exit 1
fi
