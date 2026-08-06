#!/usr/bin/env bash
# =============================================================================
# Test: backend-shipper.sh command execution — stop-run / abort-spawn (ABS-354)
# =============================================================================
# Drives scripts/backend-shipper.sh with a STUBBED backend (BACKEND_CURL points
# at a fake curl that serves a canned command-poll body and records receipts).
# No Docker needed: the acts under test are LOCAL (touch ORCH_STOP_FILE / signal
# a real PID); only the poll + receipt are HTTP, and those are stubbed.
#
#   AC1: stop-run creates ORCH_STOP_FILE and posts an executed receipt; the
#        orchestrator.sh diff is empty (no new stop path was added).
#   AC2: abort-spawn resolves the ledger PID, verifies its recorded identity token
#        matches the live process, signals it, posts an executed receipt.
#   AC3: abort-spawn with a stale/unknown ledger entry refuses to signal, posts a
#        failed receipt, and logs the refusal.
#   AC4: an executed command posts a receipt carrying the command id (the backend
#        audits it as actor=human + command id — command-routes.test.ts AC#4).
#   AC5: a re-delivered, already-executed command does not re-signal.
#
#   ABS-387 (PID identity binding) + ABS-405 (second factor = cmdline):
#   I1: the spawn PID ledger records a combined start-time+cmdline identity token
#       (field 5) alongside each PID at spawn time — the token carries BOTH factors.
#   I2: abort-spawn refuses to signal a live PID whose identity token does NOT
#       match the ledger (PID recycled to a different process) — no signal sent.
#   I3: abort-spawn refuses when the cmdline factor differs but the start-time
#       matches (same-second recycle simulation) — the ABS-405 residual close.
#   I4: identity capture (`ps -o lstart= -o command=`) is exercised on the host OS.
#   I5: an absent/partial (one-factor-only) ledger token still refuses (fail-safe).
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHIPPER="$REPO_ROOT/scripts/backend-shipper.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; echo "$1" | head -5 | sed 's/^/      /'; FAIL=$((FAIL + 1)); fi
}
assert_true()  { TOTAL=$((TOTAL + 1)); if eval "$1"; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1)); else echo -e "  ${RED}FAIL${NC} $2"; FAIL=$((FAIL + 1)); fi; }
assert_false() { TOTAL=$((TOTAL + 1)); if ! eval "$1"; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1)); else echo -e "  ${RED}FAIL${NC} $2"; FAIL=$((FAIL + 1)); fi; }

# pid_identity_token <pid> — MUST mirror backend-shipper.sh:pid_identity so a
# ledger the test writes (producer surrogate) carries the same combined
# start-time+cmdline token the shipper re-derives (ABS-387 + ABS-405).
pid_identity_token() {
    ps -o lstart= -o command= -p "$1" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//'
}

TMP="$(mktemp -d /tmp/ship-cmd-XXXXXX)"
cleanup() { rm -rf "$TMP"; [ -n "${BG_PID:-}" ] && kill "$BG_PID" 2>/dev/null || true; }
trap cleanup EXIT

# --- Fake curl: serves the poll body, records receipts. ----------------------
FAKE_CURL="$TMP/fake-curl.sh"
cat > "$FAKE_CURL" <<'FAKE'
#!/usr/bin/env bash
# Minimal curl stand-in for the shipper: honours -o <file> / -X POST /
# --data-binary <body> and the trailing URL. GET -> canned poll body; POST -> log.
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
    printf '%s\t%s\n' "$url" "$data" >> "$FAKE_RECEIPT_LOG"
    [ -n "$out" ] && printf '{"ok":true}' > "$out"
    printf '200'
else
    [ -n "$out" ] && cat "$FAKE_POLL_BODY" > "$out"
    printf '200'
fi
FAKE
chmod +x "$FAKE_CURL"

# Shared shipper env for every case.
export BACKEND_URL="http://localhost:9" BACKEND_TOKEN="t" TRACKER_PROJECT="SHIP"
export ORCH_INSTANCE_ID="orch-1"
export BACKEND_CURL="$FAKE_CURL"
export SHIPPER_FOLLOW=0

# run_case <state_dir> — set per-case paths and run the shipper once (drain).
setup_case() {
    local sd="$1"
    export ORCH_STATE_DIR="$sd"
    export ORCH_RUN_LOG="$sd/run.log"                 # absent → telemetry no-op
    export SHIPPER_CURSOR_FILE="$sd/cursor"
    export ORCH_STOP_FILE="$sd/orchestrator-stop"
    export SHIPPER_PID_LEDGER="$sd/spawn-pid-ledger"
    export SHIPPER_EXECUTED_FILE="$sd/executed"
    export FAKE_POLL_BODY="$sd/poll.json"
    export FAKE_RECEIPT_LOG="$sd/receipts.log"
    mkdir -p "$sd"
    : > "$FAKE_RECEIPT_LOG"
}

# =============================================================================
echo -e "${CYAN}=== AC1: stop-run sets ORCH_STOP_FILE + posts executed receipt ===${NC}"
SD="$TMP/ac1"; setup_case "$SD"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-stop","instance":"orch-1","kind":"stop-run","ledgerId":null,"state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
assert_true  "[ -f '$ORCH_STOP_FILE' ]" "AC1: ORCH_STOP_FILE created at the reuse path"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" "/agent/v1/orchestrators/orch-1/commands/cmd-stop/receipt" "AC1: receipt posted to the command's receipt URL"
assert_contains "$receipts" '"state":"executed"' "AC1: receipt state=executed"

echo -e "${CYAN}=== AC1: orchestrator.sh diff is empty (no new stop path) ===${NC}"
orch_diff="$(cd "$REPO_ROOT" && git diff --stat HEAD -- scripts/orchestrator.sh)"
assert_eq "$orch_diff" "" "AC1: scripts/orchestrator.sh unchanged (stop switch reused, not re-added)"

# =============================================================================
echo -e "${CYAN}=== AC2: abort-spawn resolves ledger PID, verifies identity, signals it ===${NC}"
SD="$TMP/ac2"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
# ABS-387 (I1/I4): the ledger entry carries a process-identity token (field 5),
# captured on THIS host via `ps -o lstart=`.
IDENT="$(pid_identity_token "$BG_PID")"
printf 'led-1\t%s\tABS-9\tbe-developer\t%s\n' "$BG_PID" "$IDENT" > "$SHIPPER_PID_LEDGER"
assert_false "[ -z \"$IDENT\" ]" "I4: identity token captured on the host OS (ps -o lstart= -o command=)"
LEDGER_FIELD5="$(head -1 "$SHIPPER_PID_LEDGER" | cut -f5)"
assert_false "[ -z \"$LEDGER_FIELD5\" ]" "I1: ledger entry carries the identity token field"
# ABS-405: the token combines BOTH factors — the start-time (a 4-digit year) AND
# the cmdline (the 'sleep 300' the process runs) appear in the one field-5 token.
assert_contains "$LEDGER_FIELD5" "$(date +%Y)" "I1: identity token carries the start-time factor"
assert_contains "$LEDGER_FIELD5" "sleep 300" "I1: identity token carries the cmdline factor (ABS-405)"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-abort","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-1","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
assert_true "kill -0 $BG_PID 2>/dev/null" "AC2: target process is alive before abort"
bash "$SHIPPER" 2>"$SD/err.log"
for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$BG_PID" 2>/dev/null || break; sleep 0.2; done
assert_false "kill -0 $BG_PID 2>/dev/null" "AC2: matched identity → target process was signalled (no longer running)"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" "/commands/cmd-abort/receipt" "AC2: receipt posted for the abort command"
assert_contains "$receipts" '"state":"executed"' "AC2: abort receipt state=executed"
BG_PID=""

# =============================================================================
echo -e "${CYAN}=== AC3: stale/unknown ledger entry → refuse + failed receipt + log ===${NC}"
# (a) stale pid — a subshell that exits on its own, so its pid is now dead.
# (No kill/wait: a `wait` on a SIGTERM-killed job trips the bash EXIT-trap quirk.)
SD="$TMP/ac3a"; setup_case "$SD"
dead="$(bash -c 'echo $$')"
printf 'led-dead\t%s\tABS-9\tbe-developer\n' "$dead" > "$SHIPPER_PID_LEDGER"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-stale","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-dead","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" '"state":"failed"' "AC3(stale): failed receipt posted"
assert_contains "$receipts" 'stale pid' "AC3(stale): failure reason names the stale pid"
assert_contains "$(cat "$SD/err.log")" "refusing" "AC3(stale): refusal logged to stderr"

# (b) unknown ledger id — not present in the ledger at all.
SD="$TMP/ac3b"; setup_case "$SD"
printf 'led-other\t99999\tABS-9\tbe-developer\n' > "$SHIPPER_PID_LEDGER"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-missing","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-absent","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" '"state":"failed"' "AC3(unknown): failed receipt posted"
assert_contains "$receipts" 'unknown ledger id' "AC3(unknown): failure reason = unknown ledger id"

# =============================================================================
echo -e "${CYAN}=== I2: recycled/mismatched-identity PID → refuse + no signal (ABS-387) ===${NC}"
# A LIVE pid whose recorded identity token does NOT match its live start-time —
# simulates the OS recycling the ledger pid onto an unrelated same-user process.
# The pid is alive (kill -0 passes), so ONLY the identity check can save it.
SD="$TMP/i2"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
printf 'led-recycled\t%s\tABS-9\tbe-developer\tBOGUS-STALE-START-TIME\n' "$BG_PID" > "$SHIPPER_PID_LEDGER"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-recycled","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-recycled","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
assert_true "kill -0 $BG_PID 2>/dev/null" "I2: recycled-pid target is alive (only identity check can refuse)"
bash "$SHIPPER" 2>"$SD/err.log"
sleep 0.5
assert_true "kill -0 $BG_PID 2>/dev/null" "I2: mismatched identity → target was NOT signalled (survives)"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" '"state":"failed"' "I2: failed receipt posted on identity mismatch"
assert_contains "$receipts" 'identity mismatch' "I2: failure reason names the identity mismatch"
assert_contains "$(cat "$SD/err.log")" "refusing" "I2: refusal logged to stderr"
kill "$BG_PID" 2>/dev/null || true; BG_PID=""

# =============================================================================
echo -e "${CYAN}=== I3: same-second recycle — start-time matches, cmdline differs → refuse (ABS-405) ===${NC}"
# Build a ledger token that shares the live pid's EXACT start-time but a DIFFERENT
# cmdline — a process recycled onto this pid within the SAME wall-clock second.
# Start-time alone (ABS-387) would MATCH and wrongly signal; only the cmdline
# factor (ABS-405) refuses. This is the residual ABS-405 closes.
SD="$TMP/i3"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
SAMESEC_START="$(ps -o lstart= -p "$BG_PID" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//')"
printf 'led-samesec\t%s\tABS-9\tbe-developer\t%s recycled-other-command --x\n' "$BG_PID" "$SAMESEC_START" > "$SHIPPER_PID_LEDGER"
assert_contains "$(head -1 "$SHIPPER_PID_LEDGER" | cut -f5)" "$SAMESEC_START" "I3: ledger token shares the live pid's start-time (same-second setup)"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-samesec","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-samesec","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
assert_true "kill -0 $BG_PID 2>/dev/null" "I3: same-second target is alive before abort"
bash "$SHIPPER" 2>"$SD/err.log"
sleep 0.5
assert_true "kill -0 $BG_PID 2>/dev/null" "I3: cmdline factor differs → target NOT signalled (survives)"
receipts="$(cat "$FAKE_RECEIPT_LOG")"
assert_contains "$receipts" '"state":"failed"' "I3: failed receipt on same-second cmdline mismatch"
assert_contains "$receipts" 'identity mismatch' "I3: failure reason names the identity mismatch"
assert_contains "$(cat "$SD/err.log")" "refusing" "I3: refusal logged to stderr"
kill "$BG_PID" 2>/dev/null || true; BG_PID=""

# =============================================================================
echo -e "${CYAN}=== I5: absent / one-factor-only ledger token → refuse (fail-safe, ABS-405) ===${NC}"
# (a) empty identity token on a LIVE pid — absent token must refuse, never signal.
SD="$TMP/i5a"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
printf 'led-empty\t%s\tABS-9\tbe-developer\t\n' "$BG_PID" > "$SHIPPER_PID_LEDGER"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-empty","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-empty","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
sleep 0.5
assert_true "kill -0 $BG_PID 2>/dev/null" "I5(empty): absent identity token → live target NOT signalled"
assert_contains "$(cat "$FAKE_RECEIPT_LOG")" '"state":"failed"' "I5(empty): failed receipt on absent token"
kill "$BG_PID" 2>/dev/null || true; BG_PID=""

# (b) one-factor-only token (start-time, no cmdline) on a LIVE pid whose real token
# carries a cmdline → tokens differ byte-for-byte → refuse (partial token, fail-safe).
SD="$TMP/i5b"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
ONEFACTOR="$(ps -o lstart= -p "$BG_PID" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//')"
printf 'led-onefactor\t%s\tABS-9\tbe-developer\t%s\n' "$BG_PID" "$ONEFACTOR" > "$SHIPPER_PID_LEDGER"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-onefactor","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-onefactor","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
sleep 0.5
assert_true "kill -0 $BG_PID 2>/dev/null" "I5(partial): one-factor-only token → live target NOT signalled"
assert_contains "$(cat "$FAKE_RECEIPT_LOG")" '"state":"failed"' "I5(partial): failed receipt on one-factor-only token"
kill "$BG_PID" 2>/dev/null || true; BG_PID=""

# =============================================================================
echo -e "${CYAN}=== AC4: executed receipt carries the originating command id ===${NC}"
# The shipper's audit obligation is to POST a receipt naming the command id; the
# backend records actor=human + command_id on that receipt (command-routes.test.ts
# AC#4). AC1/AC2 above already assert the receipt URL embeds the command id.
SD="$TMP/ac4"; setup_case "$SD"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-audit","instance":"orch-1","kind":"stop-run","ledgerId":null,"state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
assert_contains "$(cat "$FAKE_RECEIPT_LOG")" "/commands/cmd-audit/receipt" "AC4: receipt POST names the originating command id"

# =============================================================================
echo -e "${CYAN}=== AC5: already-executed command does not re-signal ===${NC}"
# (a) stop-run: pre-mark executed; the stop file must NOT be re-created.
SD="$TMP/ac5a"; setup_case "$SD"
printf 'cmd-stop\n' > "$SHIPPER_EXECUTED_FILE"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-stop","instance":"orch-1","kind":"stop-run","ledgerId":null,"state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
assert_false "[ -f '$ORCH_STOP_FILE' ]" "AC5(stop): idempotent no-op did NOT re-create ORCH_STOP_FILE"
assert_contains "$(cat "$FAKE_RECEIPT_LOG")" '"state":"executed"' "AC5(stop): idempotent no-op still re-posts the receipt"

# (b) abort-spawn: pre-mark executed; a live target must survive (not re-signalled).
SD="$TMP/ac5b"; setup_case "$SD"
sleep 300 & BG_PID=$!; disown "$BG_PID" 2>/dev/null || true
printf 'led-1\t%s\tABS-9\tbe-developer\t%s\n' "$BG_PID" "$(pid_identity_token "$BG_PID")" > "$SHIPPER_PID_LEDGER"
printf 'cmd-abort\n' > "$SHIPPER_EXECUTED_FILE"
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-abort","instance":"orch-1","kind":"abort-spawn","ledgerId":"led-1","state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
sleep 0.5
assert_true "kill -0 $BG_PID 2>/dev/null" "AC5(abort): already-executed command did NOT re-signal the live target"
kill "$BG_PID" 2>/dev/null || true; BG_PID=""

# =============================================================================
# ABS-388: shipper ORCH_STOP_FILE default must derive from ORCH_STATE_ROOT so it
# matches orchestrator.sh:462 in BOTH single-repo and self-hosting modes.
# =============================================================================
echo -e "${CYAN}=== ABS-388 AC1: shipper & orchestrator ORCH_STOP_FILE defaults are identical ===${NC}"
# Byte-identical default expressions ⇒ identical derived path for ANY ORCH_STATE_ROOT
# (incl. a self-hosting root where ORCH_STATE_ROOT != REPO_ROOT).
ship_default="$(grep -m1 '^ORCH_STOP_FILE=' "$SHIPPER")"
orch_default="$(grep -m1 '^ORCH_STOP_FILE=' "$REPO_ROOT/scripts/orchestrator.sh")"
assert_eq "$ship_default" "$orch_default" "ABS-388 AC1: ORCH_STOP_FILE default derives from ORCH_STATE_ROOT in both scripts"
assert_contains "$(grep -m1 '^ORCH_STATE_ROOT=' "$SHIPPER")" 'ORCH_STATE_ROOT:-$REPO_ROOT' "ABS-388 AC4: ORCH_STATE_ROOT defaults to REPO_ROOT (single-repo mode unchanged)"

echo -e "${CYAN}=== ABS-388 AC2: self-hosting stop-run writes at \$ORCH_STATE_ROOT/work/.orchestrator-stop ===${NC}"
SHROOT="$TMP/selfhost-root"; SD="$TMP/ac388-2"; setup_case "$SD"
unset ORCH_STOP_FILE               # unset ⇒ shipper must derive the default
export ORCH_STATE_ROOT="$SHROOT"   # self-hosting: state root != repo root
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-stop","instance":"orch-1","kind":"stop-run","ledgerId":null,"state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
assert_true "[ -f '$SHROOT/work/.orchestrator-stop' ]" "ABS-388 AC2: stop file lands at the ORCH_STATE_ROOT-derived path orchestrator.sh watches"
assert_contains "$(cat "$FAKE_RECEIPT_LOG")" "$SHROOT/work/.orchestrator-stop" "ABS-388 AC2: executed receipt names the ORCH_STATE_ROOT-derived path"

echo -e "${CYAN}=== ABS-388 AC3: explicit ORCH_STOP_FILE overrides the ORCH_STATE_ROOT default ===${NC}"
SHROOT="$TMP/selfhost-root2"; SD="$TMP/ac388-3"; setup_case "$SD"
OVERRIDE="$SD/custom-stop"
export ORCH_STATE_ROOT="$SHROOT"
export ORCH_STOP_FILE="$OVERRIDE"  # explicit override must win
cat > "$FAKE_POLL_BODY" <<JSON
{"commands":[{"id":"cmd-stop","instance":"orch-1","kind":"stop-run","ledgerId":null,"state":"delivered","execCount":0,"result":null,"created":"2026-07-17T00:00:00Z"}]}
JSON
bash "$SHIPPER" 2>"$SD/err.log"
assert_true  "[ -f '$OVERRIDE' ]" "ABS-388 AC3: explicit ORCH_STOP_FILE override is written (backward-compatible)"
assert_false "[ -f '$SHROOT/work/.orchestrator-stop' ]" "ABS-388 AC3: ORCH_STATE_ROOT default NOT used when override is set"
unset ORCH_STATE_ROOT

# =============================================================================
echo ""
echo -e "${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$TOTAL tests passed"; exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$TOTAL tests failed"; exit 1
fi
