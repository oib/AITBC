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
#   chain-lock — on node2: provider-signed BOND_LOCK so the slash has an
#             on-chain `bond` row to hit (coordinator ProviderBond is local
#             state only — without this the BOND_SLASH drops at apply).
#   fail <job_id> — on hub (coordinator-local): POST /miners/{job}/fail with
#             X-Api-Key (coordinator MINER_API_KEYS env, :8203) + X-Miner-ID
#             -> fail_job -> BAD_RESULT slash -> BOND_SLASH seals on-chain.
#   verify <job_id> — BOND_SLASH sealed + bond amount/status moved.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

COORD="${STRESS_COORD_URL:-https://hub.aitbc.bubuit.net/c}"
PROVIDER_ADDR="${STRESS_PROVIDER_ADDR:-0x4A5b3bf95aa06072c568cfcb7392b4e86608b5d2}"
MODEL="${STRESS_MODEL:-stress-slush:no-such-model}"
PAYMENT="${STRESS_PAYMENT:-0.01}"
LEG="${PLAY_ARGS[0]:-submit}"
JOB_ID="${PLAY_ARGS[1]:-}"
STRESS_MINER_ID="${STRESS_MINER_ID:-aitbc-miner-1}"

coord_token() { # stored coordinator JWT (client preferred, admin fallback)
  python3 - <<'PY'
import json
try:
    d = json.load(open("/root/.aitbc/credentials.json"))
    print(d.get("default_client") or d.get("default_admin") or "")
except Exception:
    print("")
PY
}
COORD_JWT=""

job_field() { # job_field <field>
  [ -z "$COORD_JWT" ] && COORD_JWT=$(coord_token)
  curl -sf --max-time 15 -H "Authorization: Bearer $COORD_JWT" \
    "$COORD/v1/jobs/$JOB_ID" 2>/dev/null \
    | python3 -c "import json,sys;print(json.load(sys.stdin).get('$1',''))" 2>/dev/null || true
}

case "$LEG" in
  chain-lock)
    # provider-signed BOND_LOCK -> bond escrow; the on-chain `bond` row the
    # slash applies against. Must run on the provider host (node2: its
    # wallet is the slash target). bond_id defaults to the coordinator
    # bond id `bond-<miner>` so the slash payload names it.
    BOND_ID="${STRESS_BOND_ID:-bond-$STRESS_MINER_ID}"
    LOCK_AMT="${STRESS_BOND_AMOUNT:-36000000}"  # units
    resp=$(WFILE="${STRESS_PROVIDER_WALLET_PATH:-/var/lib/aitbc/wallets/default.json}" \
      BOND_ID="$BOND_ID" LOCK_AMT="$LOCK_AMT" CHAIN="$CHAIN" RPC="$RPC_URL" /opt/aitbc/venv/bin/python - <<'PY'
import json, os, urllib.request
from eth_keys import keys
from eth_utils import keccak
import sys, glob
sys.path.insert(0, "/opt/aitbc/apps/blockchain-node/src")
for d in glob.glob("/opt/aitbc/packages/py/*/src") + ["/opt/aitbc"]:
    sys.path.insert(0, d)
from aitbc_chain.state.state_transition import _bond_escrow_ait
from aitbc_chain.rpc.utils import sign_transaction_data
w = json.load(open(os.environ["WFILE"]))
sender = w["address"]
acct = json.load(urllib.request.urlopen(os.environ["RPC"] + "/rpc/account/" + sender, timeout=10))
tx = {"from": sender, "to": _bond_escrow_ait(), "amount": int(os.environ["LOCK_AMT"]),
      "fee": 360000, "nonce": acct["nonce"], "type": "BOND_LOCK", "chain_id": os.environ["CHAIN"],
      "payload": {"bond_id": os.environ["BOND_ID"], "provider": sender, "lock_days": 1,
                  "to": _bond_escrow_ait(), "amount": int(os.environ["LOCK_AMT"])}}
tx["signature"] = sign_transaction_data(tx, w["private_key"])
req = urllib.request.Request(os.environ["RPC"] + "/rpc/transaction",
    data=json.dumps(tx).encode(), headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(req, timeout=15).read().decode())
PY
    ) || fail lock "BOND_LOCK submit failed: $resp"
    txh=$(printf '%s' "$resp" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$txh" ] || fail lock "no tx hash in lock response: $resp"
    wait_seal "$txh" >/dev/null
    echo "BOND_LOCK sealed: $txh ($BOND_ID)"
    ok "$txh"
    ;;

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
      [ "$st" = "FAILED" ] && { echo "agent failed $JOB_ID organically (bad model) — run verify"; ok "$JOB_ID"; exit 0; }
      sleep 10
    done
    fail dispatch "job $JOB_ID stayed undispatched (state=${st:-?})"
    ;;

  fail)
    [ -n "$JOB_ID" ] || fail args "fail leg needs a job id"
    [ -r /etc/aitbc/aitbc-coordinator-api.env ] || fail env "fail leg must run on hub (coordinator env unreadable)"
    # miner JWT minted locally — the api-key path is not provisioned for
    # this flow; the coordinator's own JWT_SECRET signs a role=miner token
    # with sub = the assigned miner (same authority require_miner accepts).
    api_key=$(grep -E "^MINER_API_KEYS=" /etc/aitbc/aitbc-coordinator-api.env | head -1 | sed "s/^MINER_API_KEYS=//" | python3 -c "import json,sys
raw=sys.stdin.read().strip().strip(chr(39)).strip(chr(34))
try: keys=json.loads(raw)
except Exception: keys=[k.strip() for k in raw.split(\",\") if k.strip()]
print(keys[0] if keys else \"\")")
    [ -n "$api_key" ] || fail env "MINER_API_KEYS empty in coordinator env"
    # wait for assignment — fail needs job.assigned_miner_id to exist;
    # poll the (admin-authed) job record until the agent polls it into
    # RUNNING, then induce before it completes.
    for i in $(seq 1 180); do
      miner=$(job_field assigned_miner_id)
      [ -n "$miner" ] && [ "$miner" != "None" ] && break
      st=$(job_field state)
      [ "$st" = "COMPLETED" ] && skip_mature "agent completed $JOB_ID before fail leg — re-fire"
      sleep 1
    done
    [ -n "$miner" ] && [ "$miner" != "None" ] || fail lookup "job $JOB_ID never assigned"
    resp=$(curl -sf --max-time 15 -X POST "http://127.0.0.1:8203/v1/miners/$JOB_ID/fail" \
      -H "X-Api-Key: $api_key" -H "X-Miner-ID: $miner" -H 'Content-Type: application/json' \
      -d '{"error_code":"EXEC_FAILED","error_message":"stress-induced bonded failure #742"}' 2>&1) || fail fail "fail POST refused: $resp"
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
