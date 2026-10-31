#!/usr/bin/env bash
# lib.sh — shared helpers for the stress harness (#706).
# Source from a play script:  . "$(dirname "$0")/../lib.sh"
set -euo pipefail

# ---------------------------------------------------------------- args/env
# Plays accept: --host <h> --chain <id> --wallet <name> --amount <units>
#   --rpc-url <url> --tag <label>
HOST="$(hostname -s)"; CHAIN="bc-2"; WALLET="${STRESS_WALLET:-default}"
# Operator-signed leaves (agent-staking/bounty) must sign with the
# AGENT_ECONOMICS_OPERATOR wallet, not the play wallet (Refs #709).
OPERATOR_WALLET="${STRESS_OPERATOR_WALLET:-agent-econ-operator}"
opw="STRESS_OPERATOR_WALLET_${HOST}"; OPERATOR_WALLET="${!opw:-$OPERATOR_WALLET}"
OPERATOR_WALLET_PATH="${STRESS_OPERATOR_WALLET_PATH:-/var/lib/aitbc/wallets/${OPERATOR_WALLET}.json}"
AMOUNT="100"; RPC_URL=""; TAG=""
while [ $# -gt 0 ]; do case "$1" in
  --host) HOST="$2"; shift 2;;
  --chain) CHAIN="$2"; shift 2;;
  --wallet) WALLET="$2"; shift 2;;
  --amount) AMOUNT="$2"; shift 2;;
  --rpc-url) RPC_URL="$2"; shift 2;;
  --tag) TAG="$2"; shift 2;;
  *) shift;;
esac; done
[ -n "$RPC_URL" ] || RPC_URL="http://127.0.0.1:8202"
AITBC_BIN="${AITBC_BIN:-/usr/local/bin/aitbc}"
if [ -z "${STRESS_STATE_DIR:-}" ]; then
  if [ -d /var/lib/aitbc ] && [ -w /var/lib/aitbc ]; then STATE_DIR=/var/lib/aitbc/stress-state
  else STATE_DIR="$HOME/.aitbc-stress-state"; fi
else STATE_DIR="$STRESS_STATE_DIR"; fi
RUN_LOG="${STRESS_RUN_LOG:-$STATE_DIR/stress-runs.jsonl}"
FINDINGS_LOG="${STRESS_FINDINGS_LOG:-$STATE_DIR/stress-findings.jsonl}"
SPEND_FILE="$STATE_DIR/spent-${WALLET}.units"
SPEND_CAP="${STRESS_SPEND_CAP:-100000}"
LOCK_DIR="$STATE_DIR/serial.lock"
mkdir -p "$STATE_DIR" 2>/dev/null || true

# ---------------------------------------------------------------- jsonl
jsonl() {  # jsonl <file> <json-object>  — append one record, flock-guarded
  local f="$1" j="$2"; mkdir -p "$(dirname "$f")" 2>/dev/null || true
  ( flock -w 10 9 || exit 1; printf '%s\n' "$j" >> "$f" ) 9>>"$f.lock"
}
now() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
_jq() { python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])))' "$1" 2>/dev/null; }

# ---------------------------------------------------------------- failures
fail() {  # fail <step> <reason> [tx_hash] — JSONL evidence, exit 1
  local step="$1" reason="$2" tx="${3:-null}"
  local esc; esc=$(printf '%s' "$reason" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')
  local jx; jx=$(journalctl -u 'aitbc-*' --since '2 min ago' -p warning --no-pager 2>/dev/null | tail -5 | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')
  jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"chain\":\"$CHAIN\",\"step\":\"$step\",\"status\":\"fail\",\"reason\":$esc,\"tx_hash\":$( [ "$tx" = null ] && echo null || echo "\"$tx\"" ),\"journal_excerpt\":$jx}"
  echo "FAIL [$step] $reason" >&2; exit 1
}
skip_mature() {  # maturity window not reached — exit 77, not a failure
  jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"skip_mature\",\"reason\":\"$1\"}"
  echo "SKIP_MATURE: $1"; exit 77
}
ok() { jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"chain\":\"$CHAIN\",\"status\":\"ok\",\"tx_hash\":$( [ "${1:-}" = "" ] && echo null || echo "\"$1\"" )}"; }

# ---------------------------------------------------------------- host map
# Fleet-reachable addresses: ssh aliases (hub/hub1/node0..2) exist only on
# the IDE/ops host. On any other host, rpc-level checks must go over the
# fleet URLs. Override per host with STRESS_RPC_<host> (dots → underscores).
stress_rpc_url() {  # stress_rpc_url <host> → rpc base URL
  local h="$1" var="STRESS_RPC_${h//./_}"
  echo "${!var:-https://${h}.aitbc.bubuit.net}"
}
stress_ssh() {  # stress_ssh <host> <cmd...> — local when we're on it
  local h="$1"; shift
  if [ "$(hostname -s)" = "$h" ] || [ "$(hostname)" = "$h" ]; then bash -c "$*";
  else ssh "$h" "$*"; fi
}

# ---------------------------------------------------------------- rpc/cli
rpc_get() { curl -sf --max-time 15 "$RPC_URL$1"; }
rpc_post() { curl -sf --max-time 30 -X POST -H 'Content-Type: application/json' -d "$2" "$RPC_URL$1"; }
cli() {  # cli <args...> — aitbc with output json + rpc-url pinned
  "$AITBC_BIN" --output=json "$@" --rpc-url "$RPC_URL"
}
height() { rpc_get /rpc/status | python3 -c 'import json,sys; print(json.load(sys.stdin).get("height",0))'; }
wallet_addr() {  # wallet_addr — address of $WALLET; `wallet balance` has no --rpc-url so bypass cli()
  "$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" balance 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null
}
stress_height() {  # stress_height <host> — remote height via fleet URL
  curl -sf --max-time 15 "$(stress_rpc_url "$1")/rpc/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("height",0))' 2>/dev/null
}

# ---------------------------------------------------------------- seal wait
wait_seal() {  # wait_seal <tx_hash> [max_blocks] — poll until block_height
  local tx="$1" max="${2:-4}" h0; h0=$(height) || fail wait_seal "no height"
  local deadline=$(( h0 + max )) i
  for i in $(seq 1 $(( max * 30 ))); do
    local bh; bh=$(rpc_get "/rpc/transaction/$tx" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("block_height") or "")' 2>/dev/null || true)
    [ -n "$bh" ] && { jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"sealed\",\"tx\":\"$tx\",\"seal_blocks\":$(( bh - h0 )),\"at_height\":$bh}" 2>/dev/null || true; echo "$bh"; return 0; }
    [ "$(height)" -gt "$deadline" ] && { fail seal "tx $tx not sealed by height $deadline" "$tx"; }
    sleep 10
  done
  fail seal "tx $tx seal wait exhausted" "$tx"
}

# ---------------------------------------------------------------- spend cap
spend_guard() {  # spend_guard <units> — cumulative 100k cap per wallet
  local n="$1" cur; cur=$(cat "$SPEND_FILE" 2>/dev/null || echo 0)
  if [ $(( cur + n )) -gt "$SPEND_CAP" ]; then
    fail spend "cap exceeded: $cur + $n > $SPEND_CAP units for $WALLET"
  fi
  echo $(( cur + n )) > "$SPEND_FILE"
}

# ---------------------------------------------------------------- serial lane
serial_acquire() {  # mkdir-based lock on the local state dir (hub copy via ssh)
  local target="$LOCK_DIR"
  if [ "${STRESS_SERIAL_REMOTE:-}" = "hub" ]; then
    ssh hub "mkdir -p /var/lib/aitbc/stress-state && mkdir /var/lib/aitbc/stress-state/serial.lock 2>/dev/null" || {
      echo "SERIAL_WAIT: serial play in flight on hub"; return 75; }
    ssh hub "echo '{\"coder\":\"${CODER:-?}\",\"play\":\"${0##*/}\",\"ts\":\"$(now)\"}' > /var/lib/aitbc/stress-state/serial.lock/owner"
    return 0
  fi
  if ! mkdir "$target" 2>/dev/null; then
    if [ -f "$target/owner" ] && [ $(( $(date +%s) - $(date -r "$target/owner" +%s 2>/dev/null || echo 0) )) -gt 1800 ]; then
      rm -f "$target/owner"; rmdir "$target" 2>/dev/null || rm -rf "$target"; mkdir "$target" 2>/dev/null || { echo "SERIAL_WAIT"; return 75; }
    else echo "SERIAL_WAIT: serial play in flight ($(cat "$target/owner" 2>/dev/null))"; return 75; fi
  fi
  echo "{\"coder\":\"${CODER:-?}\",\"play\":\"${0##*/}\",\"ts\":\"$(now)\"}" > "$target/owner"
  return 0
}
serial_release() {
  if [ "${STRESS_SERIAL_REMOTE:-}" = "hub" ]; then
    ssh hub 'rm -f /var/lib/aitbc/stress-state/serial.lock/owner; rmdir /var/lib/aitbc/stress-state/serial.lock 2>/dev/null' || true
  else rm -f "$LOCK_DIR/owner" 2>/dev/null; rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"; fi
}
serial_check() {  # parallel scripts: nonzero if a serial play is in flight
  [ -d "$LOCK_DIR" ] && { echo "SERIAL_WAIT: serial play in flight ($(cat "$LOCK_DIR/owner" 2>/dev/null))"; return 75; }
  return 0
}
trap 'serial_release' EXIT
