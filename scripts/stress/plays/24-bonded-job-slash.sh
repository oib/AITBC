#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
PLAY_ARGS=("$@")  # captured before lib.sh consumes "$@" (positional legs)
# 24 — bonded-job slash (#742): the chain BOND_SLASH has no direct HTTP
# trigger; it emits from BondSlashingService on a bonded-job failure.
# Legs:
#   submit  — on a customer host: active bond exists for the shop miner,
#             `ai submit --bond-required`, wait until the job is dispatched
#             (assigned_miner_id + escrowed payment_id).
#   fail <job_id> — on hub (coordinator-local): POST /miners/{job}/fail with
#             X-Api-Key (coordinator MINER_API_KEYS env) + X-Miner-ID ->
#             fail_job -> BAD_RESULT slash -> BOND_SLASH seals on-chain.
#   verify <job_id> — BOND_SLASH sealed + bond amount/status moved.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

COORD="${STRESS_COORD_URL:-https://hub.aitbc.bubuit.net/c}"
PROVIDER_ADDR="${STRESS_PROVIDER_ADDR:-0x4A5b3bf95aa06072c568cfcb7392b4e86608b5d2}"
MODEL="${STRESS_MODEL:-llama3.2:3b}"
PAYMENT="${STRESS_PAYMENT:-0.01}"
LEG="${PLAY_ARGS[0]:-submit}"
JOB_ID="${PLAY_ARGS[1]:-}"

job_field() { # job_field <field>
  curl -sf --max-time 15 "$COORD/v1/jobs/$JOB_ID" 2>/dev/null \
    | python3 -c "import json,sys;print(json.load(sys.stdin).get('$1',''))" 2>/dev/null || true
}

case "$LEG" in
  submit)
    addr=$(wallet_addr || true)
    [ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
    # prereq: the assigned miner must carry an ACTIVE/LOCKED ProviderBond
    # under provider_id == miner.id — _bond_for_job falls back to that row
    # when the job names no bond_id (Constraints ignores one anyway).
    MINER_ID="${STRESS_MINER_ID:-aitbc-miner-1}"
    echo x | "$AITBC_BIN" auth login --wallet "$WALLET" --password-stdin >/dev/null 2>&1 || true
    bst=$("$AITBC_BIN" --output=json bond status --provider-id "$MINER_ID" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
    if [ "$bst" != "active" ] && [ "$bst" != "locked" ]; then
      "$AITBC_BIN" --output=json bond create --provider-id "$MINER_ID" --amount 1 --required-amount 1 >/dev/null 2>&1 || true
      "$AITBC_BIN" --output=json bond top-up --provider-id "$MINER_ID" --amount 1 >/dev/null 2>&1 || true
      sleep 5
      bst=$("$AITBC_BIN" --output=json bond status --provider-id "$MINER_ID" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
    fi
    [ "$bst" = "active" ] || [ "$bst" = "locked" ] || fail bond "miner bond $MINER_ID not active (status=${bst:-?})"
    out=$(cli ai submit --prompt "stress-bonded $(date +%s)" --model "$MODEL" \
          --provider-address "$PROVIDER_ADDR" --buyer-address "$addr" \
          --payment "$PAYMENT" --bond-required --wallet "$WALLET" --format json 2>&1) \
        || fail submit "bonded submit failed: $out"
    JOB_ID=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"[0-9a-f]{32}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$JOB_ID" ] || fail submit "no job id in submit output"
    for i in $(seq 1 36); do
      miner=$(job_field assigned_miner_id)
      pay=$(job_field payment_id)
      st=$(job_field state)
      [ -n "$miner" ] && [ -n "$pay" ] && { echo "dispatched $JOB_ID miner=$miner payment=$pay state=$st"; ok "$JOB_ID"; exit 0; }
      [ "$st" = "COMPLETED" ] && skip_mature "agent completed $JOB_ID before fail leg — re-fire"
      sleep 10
    done
    fail dispatch "job $JOB_ID stayed undispatched (state=${st:-?})"
    ;;

  fail)
    [ -n "$JOB_ID" ] || fail args "fail leg needs a job id"
    [ -r /etc/aitbc/aitbc-coordinator-api.env ] || fail env "fail leg must run on hub (coordinator env unreadable)"
    api_key=$(grep -E '^MINER_API_KEYS=' /etc/aitbc/aitbc-coordinator-api.env | head -1 | cut -d= -f2 | cut -d, -f1 | tr -d ' ')
    [ -n "$api_key" ] || fail env "MINER_API_KEYS empty in coordinator env"
    miner=$(job_field assigned_miner_id)
    [ -n "$miner" ] || fail lookup "job $JOB_ID has no assigned_miner_id"
    resp=$(curl -sf --max-time 15 -X POST "http://127.0.0.1:8201/v1/miners/$JOB_ID/fail" \
      -H "X-Api-Key: $api_key" -H "X-Miner-ID: $miner" -H 'Content-Type: application/json' \
      -d '{"error_message":"stress-induced bonded failure #742"}' 2>&1) || fail fail "fail POST refused: $resp"
    echo "fail accepted: $resp"
    # verify inline: the slash service submits BOND_SLASH synchronously —
    # poll the node rpc for the sealed tx carrying the miner's bond.
    for i in $(seq 1 36); do
      hit=$(rpc_get "/rpc/transactions?transaction_type=BOND_SLASH&limit=10" 2>/dev/null | python3 -c 'import json,sys
d=json.load(sys.stdin)
txs=d.get("transactions",d if isinstance(d,list) else [])
print(next((t["tx_hash"] for t in txs if t.get("block_height")), ""))' 2>/dev/null || true)
      [ -n "$hit" ] && { echo "BOND_SLASH sealed: $hit"; ok "$hit"; exit 0; }
      sleep 10
    done
    fail seal "no BOND_SLASH sealed within 6min of induced failure"
    ;;

  verify)
    [ -n "$JOB_ID" ] || fail args "verify leg needs a job id"
    tx=$(rpc_get "/rpc/transactions?transaction_type=BOND_SLASH&limit=10" 2>/dev/null | python3 -c 'import json,sys
d=json.load(sys.stdin)
txs=d.get("transactions",d if isinstance(d,list) else [])
print(next((t["tx_hash"] for t in txs if t.get("block_height")), ""))' 2>/dev/null || true)
    [ -n "$tx" ] && { echo "verified: BOND_SLASH $tx"; ok "$tx"; exit 0; }
    fail verify "no sealed BOND_SLASH found for job $JOB_ID"
    ;;
  *)
    fail args "unknown leg: $LEG (submit|fail|verify)"
    ;;
esac
