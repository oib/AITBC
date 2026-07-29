#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Agentic-Backend Run.log / Telemetry Ingest Shipper (ABS-351, ABS-230 S6)
#   + Command execution: stop-run / abort-spawn (ABS-354, ABS-230 S10)
# =============================================================================
# Runs on the orchestrator machine as a local process. Reads run.log and the
# current day's spawn ledger from a PERSISTED CURSOR and POSTs run-ID-stamped
# telemetry event records to the backend ingest endpoint. It ALSO polls the
# per-instance command queue (ABS-348 / Story 9) and executes human-issued
# control commands LOCALLY — reusing the existing kill switch and spawn PIDs, no
# new stopping mechanism (ADR-A-0010). Outbound connections only — no listening
# socket, no bind() call.
#
# Command execution (ABS-354):
#   * stop-run     — creates the existing ORCH_STOP_FILE kill switch (the same
#                    file orchestrator.sh already acts on; NO new stop logic).
#   * abort-spawn  — resolves <ledger-id> to a PID in the local spawn PID ledger,
#                    validates it (recorded pid is a live process AND its live
#                    process-identity token still matches the one the ledger
#                    recorded at spawn — closes the PID-recycling window, ABS-387),
#                    and signals it. A stale/unknown/non-matching-identity entry
#                    is refused with a `failed` receipt (never signalled).
#   Every executed command POSTs a receipt; the backend audits each receipt as an
#   event with actor=human + the command id (ABS-348 recordReceipt). Execution is
#   idempotent: a re-delivered, already-executed command re-posts its receipt but
#   never re-signals.
#
# Env:
#   BACKEND_URL            backend base URL (default: http://localhost:8420)
#   BACKEND_TOKEN          orchestrator bearer token (REQUIRED)
#   TRACKER_PROJECT        project key (REQUIRED)
#   ORCH_RUN_LOG           path to run.log (default: $ORCH_STATE_DIR/run.log)
#   ORCH_STATE_DIR         orchestrator state dir (default: work/.orchestrator)
#   SHIPPER_CURSOR_FILE    cursor persistence path
#                          (default: $ORCH_STATE_DIR/shipper-cursor)
#   SHIPPER_FOLLOW         0=drain+exit, 1=follow indefinitely (default: 0)
#   SHIPPER_TAIL           follow mode only: 1=wake on new lines via `tail -F`
#                          (telemetry lands in ~1s), 0=legacy fixed sleep loop
#                          (default: 1). tail is ONLY the wake — the persisted
#                          cursor stays the truth for what was shipped, so a
#                          (re)start always drains from the cursor. Zero-dep:
#                          tail -F is POSIX and survives log rotation/truncation.
#   SHIPPER_COALESCE_INTERVAL  SHIPPER_TAIL=1 only: seconds to coalesce a line
#                          burst into one ship pass so a storm POSTs as batches
#                          (<= SHIPPER_BATCH_SIZE), not line-by-line (default: 1)
#   SHIPPER_POLL_INTERVAL  follow mode: max seconds between passes — the fixed
#                          sleep in legacy mode, and the wake read-timeout in
#                          tail mode (bounds command-poll + ledger-file discovery
#                          latency) (default: 5)
#   SHIPPER_BATCH_SIZE     max events per POST (default: 100)
#   BACKEND_CURL           curl binary override (default: curl)
#   --- command execution (ABS-354) ---
#   SHIPPER_COMMANDS       1=poll+execute the command queue, 0=off (default: 1)
#   ORCH_INSTANCE_ID       this orchestrator's instance id (the command queue
#                          :id / auth_token.label). Falls back to
#                          $ORCH_STATE_DIR/instance-id. When neither resolves, the
#                          command channel is disabled (telemetry still ships).
#   ORCH_STOP_FILE         kill-switch path — MUST match orchestrator.sh
#                          (default: $ORCH_STATE_ROOT/work/.orchestrator-stop,
#                          identical to orchestrator.sh:462; ORCH_STATE_ROOT
#                          defaults to $REPO_ROOT, so single-repo mode is
#                          unchanged and self-hosting agrees by default).
#   SHIPPER_PID_LEDGER     local spawn PID ledger read by abort-spawn. TAB-separated
#                          lines: <ledger_id>\t<pid>\t<ticket>\t<role>\t<identity>
#                          where <identity> is the process-identity token the
#                          producer captured at spawn: process start-time via
#                          `ps -o lstart=` (ABS-387) AND process cmdline via
#                          `ps -o command=` (ABS-405), combined+normalised into
#                          one token. abort-spawn re-derives the live pid's token
#                          and refuses to signal if EITHER factor mismatches.
#                          (default: $ORCH_STATE_DIR/spawn-pid-ledger).
#   SHIPPER_ABORT_SIGNAL   signal name for abort-spawn (default: TERM).
#   SHIPPER_EXECUTED_FILE  executed-command memory for idempotency
#                          (default: $ORCH_STATE_DIR/shipper-executed-commands).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND_URL="${BACKEND_URL:-http://localhost:8420}"
CURL_BIN="${BACKEND_CURL:-curl}"
ORCH_STATE_DIR="${ORCH_STATE_DIR:-$REPO_ROOT/work/.orchestrator}"
ORCH_RUN_LOG="${ORCH_RUN_LOG:-$ORCH_STATE_DIR/run.log}"
SHIPPER_CURSOR_FILE="${SHIPPER_CURSOR_FILE:-$ORCH_STATE_DIR/shipper-cursor}"
SHIPPER_FOLLOW="${SHIPPER_FOLLOW:-0}"
SHIPPER_TAIL="${SHIPPER_TAIL:-1}"
SHIPPER_COALESCE_INTERVAL="${SHIPPER_COALESCE_INTERVAL:-1}"
SHIPPER_POLL_INTERVAL="${SHIPPER_POLL_INTERVAL:-5}"
SHIPPER_BATCH_SIZE="${SHIPPER_BATCH_SIZE:-100}"

# --- command execution (ABS-354) -------------------------------------------
SHIPPER_COMMANDS="${SHIPPER_COMMANDS:-1}"
# ORCH_STOP_FILE default mirrors orchestrator.sh:462 EXACTLY — derived from
# ORCH_STATE_ROOT, which defaults to the repo root in single-repo mode and to the
# operator-exported state root under self-hosting (ORCH_STATE_ROOT != REPO_ROOT).
# Reuse the SAME switch so a shipper-set stop is indistinguishable from an
# orchestrator-set one and both agree by default in either mode — no new stop
# mechanism (ADR-A-0010, ABS-388, AC#1).
ORCH_STATE_ROOT="${ORCH_STATE_ROOT:-$REPO_ROOT}"
# ABS-393 parity: honor the seat-scoped state redirection exactly like
# orchestrator.sh — a redirected seat must read ITS stop file, not the live one.
_orch_statedir_base="${_orch_seat_statedir_base:-$ORCH_STATE_ROOT}"
ORCH_STOP_FILE="${ORCH_STOP_FILE:-$_orch_statedir_base/work/.orchestrator-stop}"
SHIPPER_PID_LEDGER="${SHIPPER_PID_LEDGER:-$ORCH_STATE_DIR/spawn-pid-ledger}"
SHIPPER_ABORT_SIGNAL="${SHIPPER_ABORT_SIGNAL:-TERM}"
SHIPPER_EXECUTED_FILE="${SHIPPER_EXECUTED_FILE:-$ORCH_STATE_DIR/shipper-executed-commands}"
# S4/PILOT-30 Poll->Push (command long-poll). When the backend advertises the
# `commands-wait` capability, the follow-mode command poll HOLDS the request
# server-side up to the cap (?wait=<sec>) so stop-run/abort-spawn reach this
# machine in <1s instead of up to SHIPPER_POLL_INTERVAL. The long-poll runs in a
# SEPARATE background loop so the (up to ~cap-long) command hold never delays the
# telemetry cursor flush (AC6) — telemetry keeps its own tail -F / interval path.
#   ORCH_EVENTS_WAIT       1=use the long-poll when available (default), 0=kill
#                          switch, shared with the orchestrator: interval-poll only.
#   EVENT_WAIT_CAP_SECONDS the wait cap — ONE value, ONE source with the server and
#                          orchestrator (ADR-A-0029 §7, default 55, under the 60s
#                          proxy idle timeout). curl --max-time = cap + buffer.
#   ORCH_EVENTS_WAIT_BUFFER seconds added to the cap for curl --max-time.
ORCH_EVENTS_WAIT="${ORCH_EVENTS_WAIT:-1}"
EVENT_WAIT_CAP_SECONDS="${EVENT_WAIT_CAP_SECONDS:-55}"
ORCH_EVENTS_WAIT_BUFFER="${ORCH_EVENTS_WAIT_BUFFER:-10}"
# Set to 1 once the background command long-poll loop owns command polling, so the
# foreground telemetry pass stops polling commands (single owner, no receipt races).
COMMAND_WAIT_LOOP_OWNS=0
COMMAND_WAIT_PID=""
# Instance id: explicit env wins, else the orchestrator's minted instance-id file.
SHIPPER_INSTANCE_ID="${ORCH_INSTANCE_ID:-}"
if [ -z "$SHIPPER_INSTANCE_ID" ] && [ -f "$ORCH_STATE_DIR/instance-id" ]; then
    SHIPPER_INSTANCE_ID="$(head -n1 "$ORCH_STATE_DIR/instance-id" 2>/dev/null || true)"
fi

die() { echo "ERROR: $*" >&2; exit 1; }

require_env() {
    [ -n "${BACKEND_TOKEN:-}" ]   || die "BACKEND_TOKEN is required"
    [ -n "${TRACKER_PROJECT:-}" ] || die "TRACKER_PROJECT is required"
}

# ---------------------------------------------------------------------------
# Cursor helpers — a plain key=value file under the state dir.
# Keys:  run_log=<N>              lines already shipped from run.log
#        ledger_<YYYYMMDD>=<N>    lines already shipped from that day's ledger
# ---------------------------------------------------------------------------

cursor_get() {
    local key="$1" file="$SHIPPER_CURSOR_FILE"
    [ -f "$file" ] || { echo 0; return; }
    local val
    val="$(grep -m1 "^${key}=" "$file" 2>/dev/null | cut -d= -f2-)"
    echo "${val:-0}"
}

cursor_set() {
    local key="$1" val="$2" file="$SHIPPER_CURSOR_FILE" tmp
    mkdir -p "$(dirname "$file")"
    if [ ! -f "$file" ]; then
        printf '%s=%s\n' "$key" "$val" > "$file"
        return
    fi
    tmp="$(mktemp "$file.XXXXXX")"
    # rewrite file: update existing key or append new one
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed "s|^${key}=.*|${key}=${val}|" "$file" > "$tmp"
    else
        cp "$file" "$tmp"
        printf '%s=%s\n' "$key" "$val" >> "$tmp"
    fi
    mv "$tmp" "$file"
}

# ---------------------------------------------------------------------------
# JSON helpers — no jq dependency (mirrors backend-tracker.sh).
# ---------------------------------------------------------------------------

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '%s' "$s"
}

# build_event_json <run_id> <occurred_at> <kind> <ticket> <role> <to> <note> <source>
# emits a single JSON object string (no trailing comma).
build_event_json() {
    local run_id="$1" occurred_at="$2" kind="$3" ticket="$4" \
          role="$5" to="$6" note="$7" source="$8"
    printf '{"run_id":"%s","occurred_at":"%s","kind":"%s","ticket":"%s","role":"%s","to":"%s","note":"%s","source":"%s"}' \
        "$(json_escape "$run_id")" \
        "$(json_escape "$occurred_at")" \
        "$(json_escape "$kind")" \
        "$(json_escape "$ticket")" \
        "$(json_escape "$role")" \
        "$(json_escape "$to")" \
        "$(json_escape "$note")" \
        "$(json_escape "$source")"
}

# ---------------------------------------------------------------------------
# HTTP POST — identical token-in-config approach from backend-tracker.sh so
# the bearer never appears in `ps` output.
# ---------------------------------------------------------------------------

# post_events <json_array_body> — POST to the ingest endpoint.
# Returns 0 on 2xx, 1 otherwise.
post_events() {
    local body="$1"
    local url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT/telemetry/events"
    local cfg resp_body http_code err
    cfg="$(mktemp)"
    resp_body="$(mktemp)"
    err="$(mktemp)"
    printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"
    http_code="$("$CURL_BIN" -sS --config "$cfg" \
        -o "$resp_body" -w '%{http_code}' \
        -X POST -H "Content-Type: application/json" \
        --data-binary "$body" \
        "$url" 2>"$err")" || true
    local curl_exit=$?
    rm -f "$cfg" "$err"
    if [ "$curl_exit" -ne 0 ] || [ -z "$http_code" ]; then
        echo "shipper: curl error posting to $url" >&2
        rm -f "$resp_body"
        return 1
    fi
    local code="${http_code:-0}"
    rm -f "$resp_body"
    if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
        return 0
    fi
    echo "shipper: backend returned HTTP $code for $url" >&2
    return 1
}

# ---------------------------------------------------------------------------
# run.log parsing — TSV: <occurred_at> <KIND> <ticket> <role> <to> <note>
# The first RUN-START line sets current_run_id for all subsequent lines.
# Lines before the first RUN-START are skipped (no run_id, per AC#4).
# ---------------------------------------------------------------------------

# ship_run_log — read new lines from run.log from cursor, POST in batches.
# Returns total new lines consumed (even if some were skipped).
ship_run_log() {
    [ -f "$ORCH_RUN_LOG" ] || return 0

    local cursor
    cursor="$(cursor_get "run_log")"
    local total_lines
    total_lines="$(wc -l < "$ORCH_RUN_LOG" 2>/dev/null || echo 0)"
    total_lines="${total_lines// /}"

    # Rotation/truncation (AC2): the file shrank below the cursor, so it was
    # rotated or truncated out from under us and tail -F now follows the fresh
    # file. Reset the cursor to ship the new file from line 1 — no lost events,
    # and no duplicates because everything above the old cursor is gone.
    if [ "$cursor" -gt "$total_lines" ]; then
        cursor=0
    fi

    if [ "$cursor" -ge "$total_lines" ]; then
        return 0   # no new lines
    fi

    # Read every line that is new; carry the run_id across the batch.
    local current_run_id="" batch="" batch_count=0

    # Load the most recent run_id seen so far from saved cursor state so we
    # don't lose context across invocations.
    local saved_run_id
    saved_run_id="$(cursor_get "run_log_run_id")"
    current_run_id="$saved_run_id"

    local line_no=0
    while IFS= read -r raw_line; do
        line_no=$((line_no + 1))
        [ "$line_no" -gt "$cursor" ] || continue   # skip already-shipped lines

        # Parse TSV fields: occurred_at KIND ticket role to note
        local occurred_at kind ticket role to note
        IFS=$'\t' read -r occurred_at kind ticket role to note <<< "$raw_line" || true
        ticket="${ticket:--}"
        role="${role:--}"
        to="${to:--}"
        note="${note:-}"

        # Track run_id from RUN-START events.
        if [ "$kind" = "RUN-START" ]; then
            # Extract run_id=<value> from the note field.
            local extracted
            extracted="${note#*run_id=}"
            extracted="${extracted%% *}"   # stop at first space (in case of extra fields)
            [ -n "$extracted" ] && current_run_id="$extracted"
        fi

        # Skip lines with no run_id — they predate ABS-347 or run before RUN-START.
        [ -n "$current_run_id" ] || continue

        local event_json
        event_json="$(build_event_json "$current_run_id" "$occurred_at" "$kind" \
                        "$ticket" "$role" "$to" "$note" "run.log")"

        if [ -z "$batch" ]; then
            batch="$event_json"
        else
            batch="$batch,$event_json"
        fi
        batch_count=$((batch_count + 1))

        if [ "$batch_count" -ge "$SHIPPER_BATCH_SIZE" ]; then
            post_events "{\"events\":[$batch]}" || return 1
            batch=""
            batch_count=0
        fi
    done < "$ORCH_RUN_LOG"

    # Flush remainder.
    if [ "$batch_count" -gt 0 ]; then
        post_events "{\"events\":[$batch]}" || return 1
    fi

    # Advance cursor only after a successful flush.
    cursor_set "run_log" "$total_lines"
    [ -n "$current_run_id" ] && cursor_set "run_log_run_id" "$current_run_id"
}

# ---------------------------------------------------------------------------
# Spawn ledger parsing — space-separated:
#   <occurred_at> [run_id=<id>] <ticket> <role> <to_status>
# Ledger files are daily: <state_dir>/spawn-ledger-<YYYYMMDD>
# ---------------------------------------------------------------------------

# ship_ledger_file <file> <date_tag> — read new ledger lines from <file>.
ship_ledger_file() {
    local file="$1" date_tag="$2"
    [ -f "$file" ] || return 0

    local cursor_key="ledger_${date_tag}"
    local cursor
    cursor="$(cursor_get "$cursor_key")"
    local total_lines
    total_lines="$(wc -l < "$file" 2>/dev/null || echo 0)"
    total_lines="${total_lines// /}"

    # Rotation/truncation (AC2): shrank below cursor → reship from line 1.
    if [ "$cursor" -gt "$total_lines" ]; then
        cursor=0
    fi

    [ "$cursor" -lt "$total_lines" ] || return 0

    local batch="" batch_count=0 line_no=0

    while IFS= read -r raw_line; do
        line_no=$((line_no + 1))
        [ "$line_no" -gt "$cursor" ] || continue

        # Ledger line format (ABS-347):
        #   <timestamp> [run_id=<id>] <ticket> <role> <to_status>
        # Fields are space-separated; run_id field is optional (ORCH_RUN_ID_SEPARATION=0).
        local occurred_at run_id="" rest ticket role to_status
        read -r occurred_at rest <<< "$raw_line" || true

        # Extract run_id=<value> if present (second token starting with run_id=).
        local first_rest_tok
        first_rest_tok="${rest%% *}"
        case "$first_rest_tok" in
            run_id=*)
                run_id="${first_rest_tok#run_id=}"
                rest="${rest#* }"
                ;;
        esac

        # Skip ledger lines with no run_id.
        [ -n "$run_id" ] || continue

        # Remaining tokens: ticket role to_status (space-separated, may contain spaces in to_status).
        read -r ticket role to_status <<< "$rest" || true
        ticket="${ticket:--}"
        role="${role:--}"
        to_status="${to_status:--}"

        local event_json
        event_json="$(build_event_json "$run_id" "$occurred_at" "SPAWN-LEDGER" \
                        "$ticket" "$role" "$to_status" "" "ledger")"

        if [ -z "$batch" ]; then
            batch="$event_json"
        else
            batch="$batch,$event_json"
        fi
        batch_count=$((batch_count + 1))

        if [ "$batch_count" -ge "$SHIPPER_BATCH_SIZE" ]; then
            post_events "{\"events\":[$batch]}" || return 1
            batch=""
            batch_count=0
        fi
    done < "$file"

    if [ "$batch_count" -gt 0 ]; then
        post_events "{\"events\":[$batch]}" || return 1
    fi

    cursor_set "$cursor_key" "$total_lines"
}

# ship_ledgers — process today's (and yesterday's, in case of day-boundary) ledger files.
ship_ledgers() {
    local today yesterday
    today="$(date -u +%Y%m%d)"
    yesterday="$(date -u -d 'yesterday' +%Y%m%d 2>/dev/null || date -u -v-1d +%Y%m%d 2>/dev/null || echo "")"

    [ -n "$yesterday" ] && ship_ledger_file "$ORCH_STATE_DIR/spawn-ledger-$yesterday" "$yesterday"
    ship_ledger_file "$ORCH_STATE_DIR/spawn-ledger-$today" "$today"
}

# ---------------------------------------------------------------------------
# Seat heartbeat shipping (ABS-412 / ABS-410 S4)
#
# post_heartbeat <json_body>  — POST one heartbeat to the spawns/heartbeat
#   endpoint. Returns 0 on 2xx, 1 otherwise (non-fatal: a missed heartbeat
#   only delays staleness detection by one poll cycle).
#
# ship_heartbeats  — read new run.log lines using a SEPARATE cursor
#   (heartbeat_log, independent from the telemetry cursor run_log so the two
#   streams never interfere), extract the most-recent activity timestamp per
#   (run_id, ticket, role), and POST one heartbeat per active seat.
#
# Uses a temp file to collect (run_id, ticket, role, occurred_at) tuples;
# awk deduplicates to keep only the latest timestamp per key before POSTing.
# ---------------------------------------------------------------------------

post_heartbeat() {
    local body="$1"
    local url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT/spawns/heartbeat"
    local cfg resp_body http_code err
    cfg="$(mktemp)"
    resp_body="$(mktemp)"
    err="$(mktemp)"
    printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"
    http_code="$("$CURL_BIN" -sS --config "$cfg" \
        -o "$resp_body" -w '%{http_code}' \
        -X POST -H "Content-Type: application/json" \
        --data-binary "$body" \
        "$url" 2>"$err")" || true
    local curl_exit=$?
    rm -f "$cfg" "$err" "$resp_body"
    if [ "$curl_exit" -ne 0 ] || [ -z "$http_code" ]; then
        echo "shipper: curl error posting heartbeat to $url" >&2
        return 1
    fi
    local code="${http_code:-0}"
    if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
        return 0
    fi
    echo "shipper: backend returned HTTP $code for heartbeat POST $url" >&2
    return 1
}

# ship_heartbeats — post per-seat activity heartbeats derived from run.log.
#
# Uses a separate cursor key (heartbeat_log) so it advances independently
# of the telemetry cursor (run_log). Both read the same file; neither
# interferes with the other's cursor.
ship_heartbeats() {
    [ -f "$ORCH_RUN_LOG" ] || return 0
    [ -n "${BACKEND_TOKEN:-}" ] || return 0

    local cursor
    cursor="$(cursor_get "heartbeat_log")"
    local total_lines
    total_lines="$(wc -l < "$ORCH_RUN_LOG" 2>/dev/null || echo 0)"
    total_lines="${total_lines// /}"

    # Rotation/truncation (AC2): shrank below cursor → re-derive from line 1.
    if [ "$cursor" -gt "$total_lines" ]; then
        cursor=0
    fi

    [ "$cursor" -lt "$total_lines" ] || return 0

    # Carry the last-known run_id across calls (same saved key as ship_run_log).
    local current_run_id=""
    current_run_id="$(cursor_get "run_log_run_id")"

    # Collect activity tuples into a temp file (no bash associative arrays needed).
    local activity_file
    activity_file="$(mktemp)"

    local line_no=0
    while IFS= read -r raw_line; do
        line_no=$((line_no + 1))
        [ "$line_no" -gt "$cursor" ] || continue

        local occurred_at kind ticket role to note
        IFS=$'\t' read -r occurred_at kind ticket role to note <<< "$raw_line" || true
        ticket="${ticket:--}"
        role="${role:--}"

        # Track run_id from RUN-START events (same logic as ship_run_log).
        if [ "$kind" = "RUN-START" ]; then
            local extracted
            extracted="${note#*run_id=}"
            extracted="${extracted%% *}"
            [ -n "$extracted" ] && current_run_id="$extracted"
        fi

        [ -n "$current_run_id" ] || continue
        if [ "$ticket" = "-" ] || [ "$role" = "-" ]; then continue; fi

        # Append: last line for a given key wins in the awk step below.
        printf '%s\t%s\t%s\t%s\n' \
            "$current_run_id" "$ticket" "$role" "$occurred_at" >> "$activity_file"
    done < "$ORCH_RUN_LOG"

    # Deduplicate: keep LAST occurred_at per (run_id, ticket, role).
    # Lines are in chronological order (appended above in order); the last write
    # for each key is the most recent activity timestamp.
    local deduped
    deduped="$(awk -F'\t' '{
        key = $1 "\t" $2 "\t" $3
        latest[key] = $4
        r[key]=$1; ti[key]=$2; ro[key]=$3
    } END {
        for (k in latest) print r[k] "\t" ti[k] "\t" ro[k] "\t" latest[k]
    }' "$activity_file")"
    rm -f "$activity_file"

    local instance_id="${SHIPPER_INSTANCE_ID:-}"

    if [ -n "$deduped" ]; then
        while IFS=$'\t' read -r run_id ticket role activity_at; do
            [ -n "$run_id" ] || continue
            local body
            body="$(printf '{"run_id":"%s","instance_id":"%s","ticket_id":"%s","role":"%s","attempt":1,"activity_at":"%s"}' \
                "$(json_escape "$run_id")" \
                "$(json_escape "$instance_id")" \
                "$(json_escape "$ticket")" \
                "$(json_escape "$role")" \
                "$(json_escape "$activity_at")")"
            post_heartbeat "$body" || true  # non-fatal: missed heartbeat delays detection
        done <<< "$deduped"
    fi

    cursor_set "heartbeat_log" "$total_lines"
}

# ---------------------------------------------------------------------------
# Seat-spawn reconcile FALLBACK (PILOT-26)
#
# The PRIMARY Live-Spawns producer is the orchestrator itself: it POSTs the seat
# open/close upsert first-hand at spawn/reap (scripts/orchestrator.sh
# emit_seat_upsert). This reconcile pass is the REPAIR path only — it replays the
# `SEAT-SPAWN` run.log markers the runner writes alongside each first-hand POST,
# healing gaps left by a missed POST or a runner crash. The log-derived heuristic
# lives ONLY here (the primary path never parses logs, ADR-A-0010).
#
# post_spawn <spawn_id> <run_id> <ticket> <role> <attempt> <started_at> <completed_at> <exit> <diag>
#   completed_at / exit / diag empty => JSON null. Non-fatal (a missed replay is
#   retried next poll; the cursor only advances after the pass completes).
# ---------------------------------------------------------------------------

post_spawn() {
    local spawn_id="$1" run_id="$2" ticket="$3" role="$4" attempt="$5" \
          started_at="$6" completed_at="$7" exit_code="$8" diag="$9"
    [ -n "$attempt" ] || attempt=1
    local completed_json="null" exit_json="null" diag_json="null"
    [ -n "$completed_at" ] && completed_json="\"$(json_escape "$completed_at")\""
    [ -n "$exit_code" ] && exit_json="$exit_code"
    [ -n "$diag" ] && diag_json="\"$(json_escape "$diag")\""
    local body
    body="$(printf '{"spawn_id":"%s","instance_id":"%s","run_id":"%s","ticket_id":"%s","role":"%s","attempt":%s,"started_at":"%s","completed_at":%s,"exit_code":%s,"diagnostic":%s}' \
        "$(json_escape "$spawn_id")" "$(json_escape "${SHIPPER_INSTANCE_ID:-}")" \
        "$(json_escape "$run_id")" "$(json_escape "$ticket")" "$(json_escape "$role")" \
        "$attempt" "$(json_escape "$started_at")" "$completed_json" "$exit_json" "$diag_json")"
    local url cfg out code
    url="$BACKEND_URL/agent/v1/projects/$TRACKER_PROJECT/spawns"
    cfg="$(mktemp)"; out="$(mktemp)"
    printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"
    code="$("$CURL_BIN" -sS --config "$cfg" -o "$out" -w '%{http_code}' \
        -X POST -H "Content-Type: application/json" --data-binary "$body" "$url" 2>/dev/null)" || true
    rm -f "$cfg" "$out"
    case "${code:-0}" in 2*) return 0 ;; *) echo "shipper: backend returned HTTP ${code:-0} for spawn reconcile POST $url" >&2; return 1 ;; esac
}

# ship_spawns — replay SEAT-SPAWN lifecycle markers from run.log (separate
# cursor spawn_log). Tracks run_id from RUN-START; awk parses each marker's
# key=val note and emits one POST-ready TSV record per event, INCLUDING a
# synthetic close when a new open supersedes a still-open predecessor of the same
# (ticket, role) — the "respawn implicitly closes the predecessor" heuristic.
ship_spawns() {
    [ -f "$ORCH_RUN_LOG" ] || return 0
    [ -n "${BACKEND_TOKEN:-}" ] || return 0

    local cursor total_lines
    cursor="$(cursor_get "spawn_log")"
    total_lines="$(wc -l < "$ORCH_RUN_LOG" 2>/dev/null || echo 0)"
    total_lines="${total_lines// /}"
    [ "$cursor" -lt "$total_lines" ] || return 0

    local current_run_id
    current_run_id="$(cursor_get "run_log_run_id")"

    # awk: seed run_id, then for lines past the cursor emit event records.
    # Output records: phase spawn_id run_id ticket role attempt started_at
    # completed_at exit diag — joined by the ASCII Unit Separator (\037), NOT a
    # tab. A tab is IFS-whitespace, so `IFS=$'\t' read` COLLAPSES a run of tabs
    # and drops an EMPTY middle field (the superseded-close has an empty `exit`
    # before a non-empty `diag`, which would otherwise shift diag into exit).
    # \037 is not whitespace, so empty fields survive intact.
    local records sep
    sep="$(printf '\037')"
    records="$(awk -F'\t' -v cursor="$cursor" -v seed_rid="$current_run_id" -v S="$sep" '
        function tok(note, key,   m) {
            # value of key=... in a space-separated note (stops at first space)
            if (match(note, key "=[^ ]+")) {
                m = substr(note, RSTART + length(key) + 1, RLENGTH - length(key) - 1)
                return m
            }
            return ""
        }
        BEGIN { rid = seed_rid; OFS = S }
        {
            if ($2 == "RUN-START") { v = tok($6, "run_id"); if (v != "") rid = v; }
            if (NR <= cursor) next
            if ($2 != "SEAT-SPAWN") next
            phase = tok($6, "phase"); if (phase == "") next
            sid   = tok($6, "spawn_id")
            att   = tok($6, "attempt"); if (att == "") att = "1"
            st    = tok($6, "started_at")
            ct    = tok($6, "completed_at")
            ex    = tok($6, "exit")
            ticket = $3; role = $4
            key = ticket SUBSEP role
            if (phase == "open") {
                # supersede: a live predecessor for this seat closes implicitly.
                if (key in open_sid && open_sid[key] != sid) {
                    print "close", open_sid[key], rid, ticket, role, open_att[key], \
                        open_st[key], $1, "", "reconcile: superseded by respawn"
                }
                open_sid[key] = sid; open_st[key] = st; open_att[key] = att
                print "open", sid, rid, ticket, role, att, st, "", "", ""
            } else if (phase == "close") {
                print "close", sid, rid, ticket, role, att, st, ct, ex, ""
                delete open_sid[key]; delete open_st[key]; delete open_att[key]
            }
        }
    ' "$ORCH_RUN_LOG")"

    if [ -n "$records" ]; then
        while IFS="$sep" read -r phase sid rid ticket role att st ct ex diag; do
            [ -n "$sid" ] || continue
            [ -n "$rid" ] || continue
            post_spawn "$sid" "$rid" "$ticket" "$role" "$att" "$st" "$ct" "$ex" "$diag" || true
        done <<< "$records"
    fi

    cursor_set "spawn_log" "$total_lines"
}

# ---------------------------------------------------------------------------
# Command execution — stop-run / abort-spawn (ABS-354, ABS-230 S10)
# The shipper polls the per-instance command queue (ABS-348), executes each
# command LOCALLY, and POSTs a receipt. No jq: the queue returns flat command
# objects, so a top-level string-field extractor is sufficient.
# ---------------------------------------------------------------------------

# json_str_field <object> <key> — first "key":"value" string value, or empty
# (a null/absent field yields empty). Command objects never nest, so this is safe.
json_str_field() {
    printf '%s' "$1" | sed -n 's/.*"'"$2"'":"\([^"]*\)".*/\1/p' | head -n1
}

# The per-instance command base URL (poll GET, receipt POST live under it).
commands_base() { printf '%s/agent/v1/orchestrators/%s/commands' "$BACKEND_URL" "$SHIPPER_INSTANCE_ID"; }

# backend_http <out_body_file> <curl-args...> — token-in-config request (bearer
# never in `ps`, mirrors post_events). Echoes the HTTP status code.
backend_http() {
    local out="$1"; shift
    local cfg http_code
    cfg="$(mktemp)"
    printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"
    http_code="$("$CURL_BIN" -sS --config "$cfg" -o "$out" -w '%{http_code}' "$@" 2>/dev/null)" || true
    rm -f "$cfg"
    printf '%s' "${http_code:-000}"
}

# post_receipt <cmd_id> <state> <result> — POST a terminal receipt (executed|
# failed). The backend audits it as an event with actor=human + command id
# (ABS-348). Returns 0 on 2xx.
post_receipt() {
    local cmd_id="$1" state="$2" result="$3"
    local url body out code
    url="$(commands_base)/$cmd_id/receipt"
    body="$(printf '{"state":"%s","result":"%s"}' "$state" "$(json_escape "$result")")"
    out="$(mktemp)"
    code="$(backend_http "$out" -X POST -H "Content-Type: application/json" --data-binary "$body" "$url")"
    rm -f "$out"
    [ "$code" -ge 200 ] && [ "$code" -lt 300 ]
}

# Idempotency memory — one command id per line. mark BEFORE the side effect so a
# redelivery of the same command never re-signals (at-most-once execution, AC#5).
already_executed() { grep -qxF -- "$1" "$SHIPPER_EXECUTED_FILE" 2>/dev/null; }
mark_executed() {
    mkdir -p "$(dirname "$SHIPPER_EXECUTED_FILE")"
    printf '%s\n' "$1" >> "$SHIPPER_EXECUTED_FILE"
}

# resolve_ledger_pid <ledger_id> — echo the recorded pid for that ledger entry;
# non-zero return when the ledger has no matching entry.
resolve_ledger_pid() {
    local ledger_id="$1"
    [ -f "$SHIPPER_PID_LEDGER" ] || return 1
    awk -F'\t' -v id="$ledger_id" '$1==id{print $2; found=1; exit} END{exit found?0:1}' \
        "$SHIPPER_PID_LEDGER"
}

# resolve_ledger_identity <ledger_id> — echo the recorded process-identity token
# (field 5) for that ledger entry; empty when the entry has no identity field.
# ABS-387: the token the producer captured at spawn, re-checked before signalling.
resolve_ledger_identity() {
    local ledger_id="$1"
    [ -f "$SHIPPER_PID_LEDGER" ] || return 0
    awk -F'\t' -v id="$ledger_id" '$1==id{print $5; exit}' "$SHIPPER_PID_LEDGER"
}

# pid_identity <pid> — echo a stable process-identity token for a LIVE pid,
# combining TWO factors: its process start-time (`ps -o lstart=`) AND its process
# cmdline (`ps -o command=`). Both keywords are portable across the supported
# hosts — BSD/macOS ps and Linux procps ps accept them (ABS-387 AC#4, ABS-405).
# The two factors are captured in one `ps` call and normalised together into a
# single token (the same `tr -s '[:space:]' ' '` / trim the caller compares
# byte-for-byte on the same host). The cmdline is the SECOND factor (ABS-405):
# it distinguishes a recycled pid that started within the SAME wall-clock second
# as the ledger's original process — which start-time alone (~1s granularity)
# cannot. Empty output => the pid is not live / exposes no identity.
pid_identity() {
    ps -o lstart= -o command= -p "$1" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//'
}

# exec_stop_run <cmd_id> — reuse the existing ORCH_STOP_FILE kill switch. This is
# the WHOLE mechanism: orchestrator.sh already finishes-and-stops on the file's
# existence (no new stop path, AC#1 diff gate).
exec_stop_run() {
    local cmd_id="$1"
    mkdir -p "$(dirname "$ORCH_STOP_FILE")"
    printf 'stop-run via command %s at %s\n' "$cmd_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        >> "$ORCH_STOP_FILE"
}

# refuse_abort <cmd_id> <reason> — log the refusal and post a failed receipt.
# The single refusal path for every abort-spawn validation miss (AC#3): the PID
# is NEVER signalled.
refuse_abort() {
    echo "shipper: abort-spawn $1: $2; refusing" >&2
    post_receipt "$1" failed "$2" || true
}

# exec_abort_spawn <cmd_id> <ledger_id> — resolve+validate the ledger PID, then
# signal it. Any validation miss refuses to signal and reports a failed receipt.
exec_abort_spawn() {
    local cmd_id="$1" ledger_id="$2" pid
    if [ -z "$ledger_id" ]; then
        refuse_abort "$cmd_id" "missing ledger id"; return
    fi
    if ! pid="$(resolve_ledger_pid "$ledger_id")" || [ -z "$pid" ]; then
        refuse_abort "$cmd_id" "unknown ledger id: $ledger_id"; return
    fi
    case "$pid" in
        ''|*[!0-9]*) refuse_abort "$cmd_id" "non-numeric pid for ledger id: $ledger_id"; return ;;
    esac
    # PID validation: the recorded pid must still be a running process. A stale or
    # recycled entry (process gone) is refused, never signalled (AC#3).
    if ! kill -0 "$pid" 2>/dev/null; then
        refuse_abort "$cmd_id" "stale pid $pid for ledger id: $ledger_id"; return
    fi
    # Identity binding (ABS-387 + ABS-405, #EXPORT_CRITICAL): the live pid must
    # still be the EXACT process the ledger recorded. Between spawn and abort the OS
    # may recycle the pid to an unrelated same-user process; `kill -0` only proves
    # liveness, not identity. Re-derive the live pid's combined start-time+cmdline
    # token and compare to the ledger. The cmdline factor closes the residual where
    # a recycled process starts within the SAME wall-clock second as the original
    # (start-time alone, ~1s granularity, cannot tell them apart). Fail-safe: EITHER
    # factor mismatching OR a missing recorded token refuses — never signal on doubt.
    local recorded_identity live_identity
    recorded_identity="$(resolve_ledger_identity "$ledger_id")"
    live_identity="$(pid_identity "$pid")"
    if [ -z "$recorded_identity" ] || [ "$recorded_identity" != "$live_identity" ]; then
        refuse_abort "$cmd_id" "identity mismatch for pid $pid (ledger id: $ledger_id) — pid recycled or token absent"; return
    fi
    # Mark BEFORE signalling so a redelivery cannot double-signal (AC#5).
    mark_executed "$cmd_id"
    # Reap the seat's forked children FIRST, then the seat wrapper itself (ABS-476).
    # A seat is a bash wrapper running e.g. a `claude` child that won't forward the
    # signal; signalling the wrapper alone orphans the child, which keeps holding its
    # lock dir (the 2026-07-19 stale-lock finding). Order matters: a child reparents
    # to init the instant its parent dies, so a pkill -P issued AFTER the parent kill
    # misses it (verified). `pkill -P` is the codebase's sanctioned PID-scoped group
    # kill (mirrors the orchestrator watchdog), safe across macOS+Linux; a childless
    # seat is a clean no-op.
    pkill -"$SHIPPER_ABORT_SIGNAL" -P "$pid" 2>/dev/null || true
    # executed = the seat was signalled, OR reaping its only child let the wrapper
    # exit on its own (kill then reports "no such process", which is still success).
    if kill -"$SHIPPER_ABORT_SIGNAL" "$pid" 2>/dev/null || ! kill -0 "$pid" 2>/dev/null; then
        post_receipt "$cmd_id" executed "signalled pid $pid ($SHIPPER_ABORT_SIGNAL) + children for ledger id: $ledger_id" || true
    else
        echo "shipper: abort-spawn $cmd_id: kill -$SHIPPER_ABORT_SIGNAL $pid failed" >&2
        post_receipt "$cmd_id" failed "signal $SHIPPER_ABORT_SIGNAL to pid $pid failed" || true
    fi
}

# execute_command <cmd_id> <kind> <ledger_id> — dispatch one queued command.
execute_command() {
    local cmd_id="$1" kind="$2" ledger_id="$3"
    # Idempotent no-op: a previously-executed command re-posts its receipt (to
    # settle the queue if an earlier receipt was lost) but is NEVER re-signalled.
    if already_executed "$cmd_id"; then
        post_receipt "$cmd_id" executed "already executed (idempotent no-op)" || true
        return
    fi
    case "$kind" in
        stop-run)
            mark_executed "$cmd_id"
            exec_stop_run "$cmd_id"
            post_receipt "$cmd_id" executed "ORCH_STOP_FILE set: $ORCH_STOP_FILE" || true
            ;;
        abort-spawn)
            exec_abort_spawn "$cmd_id" "$ledger_id"
            ;;
        *)
            echo "shipper: unknown command kind '$kind' ($cmd_id); refusing" >&2
            post_receipt "$cmd_id" failed "unknown command kind: $kind" || true
            ;;
    esac
}

# poll_commands [wait_sec] — GET the instance command queue and execute each
# returned (pending|delivered) command. No-op when the command channel is disabled.
# With wait_sec>0 (S4/PILOT-30) the request LONG-POLLS: the server holds it until a
# command is enqueued or the (re-capped) wait elapses, with curl --max-time =
# wait + buffer so a hung connection fails-fast (returns non-2xx -> 1) instead of
# blocking past the cap. wait_sec absent/0 is byte-identical to the pre-S4 read.
poll_commands() {
    [ "$SHIPPER_COMMANDS" = "1" ] || return 0
    # No instance id → command channel disabled (telemetry shipping is unaffected).
    [ -n "$SHIPPER_INSTANCE_ID" ] || return 0
    local wait="${1:-}"
    local out code body arr
    out="$(mktemp)"
    if [ -n "$wait" ] && [ "$wait" -gt 0 ] 2>/dev/null; then
        code="$(backend_http "$out" --max-time "$(( wait + ORCH_EVENTS_WAIT_BUFFER ))" "$(commands_base)?wait=$wait")"
    else
        code="$(backend_http "$out" "$(commands_base)")"
    fi
    if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
        echo "shipper: command poll returned HTTP $code" >&2
        rm -f "$out"
        return 1
    fi
    body="$(cat "$out")"; rm -f "$out"

    # Isolate the "commands":[ ... ] array, then peel flat objects at each "},{"
    # boundary with pure bash (portable: BSD sed won't emit a newline for "\n").
    arr="${body#*\"commands\":[}"
    arr="${arr%%]*}"
    [ -n "$arr" ] || return 0
    local rest="$arr" obj id kind ledger
    while [ -n "$rest" ]; do
        case "$rest" in
            *'},{'*) obj="${rest%%\},\{*}"; rest="${rest#*\},\{}" ;;
            *)       obj="$rest";           rest="" ;;
        esac
        [ -n "$obj" ] || continue
        id="$(json_str_field "$obj" id)"
        kind="$(json_str_field "$obj" kind)"
        ledger="$(json_str_field "$obj" ledgerId)"
        [ -n "$id" ] && [ -n "$kind" ] || continue
        execute_command "$id" "$kind" "$ledger"
    done
}

# ---------------------------------------------------------------------------
# Follow-mode wake driver (SHIPPER_TAIL, ABS-506 / PILOT-31)
# ---------------------------------------------------------------------------

# run_ship_pass — one full cursor-driven pass over every source. Idempotent: it
# ships only what advanced past each persisted cursor, so running it on a spurious
# wake is a cheap no-op. This is the SAME body the legacy sleep loop ran.
run_ship_pass() {
    ship_run_log || true
    ship_ledgers || true
    ship_heartbeats || true   # ABS-412: per-seat activity heartbeats
    ship_spawns || true       # PILOT-26: seat-lifecycle reconcile fallback
    # Command polling is skipped here when the decoupled long-poll loop owns it
    # (S4/PILOT-30) — otherwise a ~cap-long command hold would stall the telemetry
    # cursor flush (AC6). In interval mode the foreground pass keeps polling.
    [ "$COMMAND_WAIT_LOOP_OWNS" = "1" ] || poll_commands || true
}

# command_wait_available — probe /capabilities ONCE for the `commands-wait`
# long-poll (S4/PILOT-30). Off under the kill switch ORCH_EVENTS_WAIT=0 or when the
# backend does not advertise it (older backend / mock). Memoized in the global.
command_wait_available() {
    [ -n "${_SHIPPER_CMD_WAIT_RESOLVED:-}" ] && return "${_SHIPPER_CMD_WAIT_CODE:-1}"
    _SHIPPER_CMD_WAIT_RESOLVED=1
    _SHIPPER_CMD_WAIT_CODE=1
    [ "${ORCH_EVENTS_WAIT:-1}" = "1" ] || return 1
    local out; out="$(mktemp)"
    if [ "$(backend_http "$out" "$BACKEND_URL/capabilities")" = "200" ] \
       && grep -qx "commands-wait" "$out" 2>/dev/null; then
        _SHIPPER_CMD_WAIT_CODE=0
    fi
    rm -f "$out"
    return "$_SHIPPER_CMD_WAIT_CODE"
}

# command_wait_loop — the decoupled command long-poll (S4/PILOT-30). Blocks up to
# the cap per request so a stop-run/abort reaches this machine in <1s; a failed
# wait (timeout/net/proxy -> non-2xx) backs off to SHIPPER_POLL_INTERVAL so a
# persistent fault degrades to interval polling instead of busy-looping. Runs as a
# background child of main(); reaped by the follow-loop cleanup trap.
command_wait_loop() {
    while true; do
        poll_commands "$EVENT_WAIT_CAP_SECONDS" || sleep "$SHIPPER_POLL_INTERVAL"
    done
}

# tail_target_files — populate TAIL_FILES[] with the EXISTING telemetry files to
# follow: run.log plus today's and yesterday's spawn ledgers (exactly the set
# ship_ledgers processes). Files that do not yet exist are omitted; they are
# picked up when the periodic re-scan (<= SHIPPER_POLL_INTERVAL) restarts tail,
# and the cursor covers any lines written before that discovery (AC5).
tail_target_files() {
    TAIL_FILES=()
    local today yesterday f
    today="$(date -u +%Y%m%d)"
    yesterday="$(date -u -d 'yesterday' +%Y%m%d 2>/dev/null || date -u -v-1d +%Y%m%d 2>/dev/null || echo "")"
    for f in "$ORCH_RUN_LOG" \
             "$ORCH_STATE_DIR/spawn-ledger-$today" \
             "$ORCH_STATE_DIR/spawn-ledger-$yesterday"; do
        [ -n "$f" ] && [ -f "$f" ] && TAIL_FILES+=("$f")
    done
    return 0   # never let a missing (non-existent) ledger fail the fn under set -e
}

# follow_tail — wake-driven follow (SHIPPER_TAIL=1). A background `tail -F` on the
# telemetry files writes into a FIFO; the loop wakes on the FIRST new line,
# coalesces the burst, then runs run_ship_pass. On a read timeout
# (SHIPPER_POLL_INTERVAL) the pass runs anyway so command polling (HTTP, not
# file-driven) and new-ledger-file discovery keep their <=5s cadence. The FIFO is
# opened read-write on fd 9 so it never blocks on open and never signals EOF when
# tail is restarted. tail is the wake only — the persisted cursor is the truth.
follow_tail() {
    local fifo tail_pid="" cur_sig=""
    fifo="$(mktemp -u "${TMPDIR:-/tmp}/shipper-tail.XXXXXX")"
    mkfifo "$fifo" || die "cannot create tail FIFO"
    exec 9<>"$fifo"          # read-write: open never blocks, read never EOFs
    rm -f "$fifo"            # unlink now; fd 9 keeps it alive until we exit

    _stop_tail() { [ -n "$tail_pid" ] && kill "$tail_pid" 2>/dev/null; tail_pid=""; return 0; }
    # sync_tail — (re)start the background tail IFF the target file set changed
    # since last call (adopting newly-created / rotated ledger files). Cheap
    # no-op when nothing changed. tail writes to fd 9; the loop reads it as wakes.
    sync_tail() {
        tail_target_files
        local sig=""
        [ "${#TAIL_FILES[@]}" -gt 0 ] && sig="$(printf '%s\n' "${TAIL_FILES[@]}")"
        [ "$sig" = "$cur_sig" ] && [ -n "$tail_pid" ] && return 0
        _stop_tail
        cur_sig="$sig"
        if [ "${#TAIL_FILES[@]}" -gt 0 ]; then
            tail -n 0 -F "${TAIL_FILES[@]}" >&9 2>/dev/null &
            tail_pid=$!
        fi
        return 0
    }
    # Reap the decoupled command long-poll child too, if one was started (S4/PILOT-30).
    # INT/TERM MUST exit: a signal trap that only cleans up and returns lets bash
    # resume the follow loop, which made this daemon unkillable by SIGTERM (the
    # caller's `kill` was swallowed and its `wait` blocked forever). Exit 0 —
    # a requested stop is not a failure, and the runner must not read it as a crash.
    trap '_stop_tail; [ -n "$COMMAND_WAIT_PID" ] && kill "$COMMAND_WAIT_PID" 2>/dev/null; exec 9<&- 2>/dev/null || true' EXIT
    trap '_stop_tail; [ -n "$COMMAND_WAIT_PID" ] && kill "$COMMAND_WAIT_PID" 2>/dev/null; exec 9<&- 2>/dev/null; exit 0' INT TERM

    echo "shipper: following $ORCH_RUN_LOG (SHIPPER_TAIL=1, tail -F wake, <=${SHIPPER_POLL_INTERVAL}s latency)" >&2

    sync_tail
    run_ship_pass   # initial drain from cursor (covers everything already on disk)

    local line
    while true; do
        if IFS= read -r -t "$SHIPPER_POLL_INTERVAL" -u 9 line; then
            # Woken by a new line — drain the burst so a line-storm ships as
            # batches (<= SHIPPER_BATCH_SIZE, AC3), not one pass per line.
            # shellcheck disable=SC2034  # drained lines are wake tokens; only read's status matters
            while IFS= read -r -t "$SHIPPER_COALESCE_INTERVAL" -u 9 line; do :; done
        fi
        run_ship_pass
        sync_tail   # re-scan: adopt newly-created / rotated ledger files
    done
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

# maybe_start_command_wait_loop — start the decoupled command long-poll as a
# background child when the backend supports it and the channel is enabled
# (S4/PILOT-30). Sets COMMAND_WAIT_LOOP_OWNS so the foreground telemetry pass stops
# polling commands (single owner). The follow-loop cleanup traps reap COMMAND_WAIT_PID.
maybe_start_command_wait_loop() {
    [ "$SHIPPER_COMMANDS" = "1" ] && [ -n "$SHIPPER_INSTANCE_ID" ] || return 0
    command_wait_available || return 0
    COMMAND_WAIT_LOOP_OWNS=1
    command_wait_loop &
    COMMAND_WAIT_PID=$!
    echo "shipper: command long-poll active (?wait=${EVENT_WAIT_CAP_SECONDS}s, decoupled from telemetry) (S4/PILOT-30)" >&2
}

main() {
    require_env

    if [ "$SHIPPER_FOLLOW" = "1" ]; then
        maybe_start_command_wait_loop
        if [ "$SHIPPER_TAIL" = "1" ]; then
            follow_tail
        else
            # Same rule as the tail loop above: INT/TERM must exit, or bash
            # resumes the `while true` below and the daemon ignores SIGTERM.
            trap '[ -n "$COMMAND_WAIT_PID" ] && kill "$COMMAND_WAIT_PID" 2>/dev/null || true' EXIT
            trap '[ -n "$COMMAND_WAIT_PID" ] && kill "$COMMAND_WAIT_PID" 2>/dev/null; exit 0' INT TERM
            echo "shipper: following $ORCH_RUN_LOG (SHIPPER_TAIL=0 sleep loop, poll every ${SHIPPER_POLL_INTERVAL}s)" >&2
            while true; do
                run_ship_pass
                sleep "$SHIPPER_POLL_INTERVAL"
            done
        fi
    else
        ship_run_log
        ship_ledgers
        ship_heartbeats || true   # ABS-412: per-seat activity heartbeats
        ship_spawns || true       # PILOT-26: seat-lifecycle reconcile fallback
        poll_commands || true
    fi
}

# Run the loop only when executed directly; when sourced (unit tests, e.g.
# tests/test-poll-push-consumer.sh) the functions load without starting main.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
