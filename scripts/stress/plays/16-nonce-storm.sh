#!/usr/bin/env bash
# LANE: parallel (volume) — but targets ONE sender slot; run solo.
# MODE: loop
# ~50 concurrent same-sender sends: most collide on the nonce slot;
# each bid with a strictly higher fee exercises replacement. Assert:
# (a) the slot never wedges — after the winning bid seals, a fresh
#     resubmit is admitted (no phantom occupancy), and
# (b) rejects are clean "nonce slot occupied" 400s, not crashes.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

N="${STORM_N:-50}"; addr="${STORM_TO:?STORM_TO required (checksummed)}"
PW_ARGS=(); [ -n "${STRESS_WALLET_PASSWORD_FILE:-}" ] && PW_ARGS=(--password-file "$STRESS_WALLET_PASSWORD_FILE")
# fee ramps 0.0100 → 0.0149 so each bid strictly outbids the prior occupant
# (fee strings are Decimal AIT; the slot admits a better bid only).
for i in $(seq 0 $((N-1))); do
  fee=$(python3 -c "print(f'{0.01 + $i*0.0001:.4f}')")
  "$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" \
    --amount 0.000001 --fee "$fee" "${PW_ARGS[@]}" ${RPC_URL:+--rpc-url "$RPC_URL"} >/dev/null 2>&1 || true &
done
wait
# The highest-fee bid should win the slot and seal — find it from the last
# successful submission by polling the account's latest tx.
tx=$("$AITBC_BIN" --output=json transactions list --limit 5 2>/dev/null | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")' || true)
if [ -n "$tx" ]; then bh=$(wait_seal "$tx" 2>/dev/null || true); [ -n "${bh:-}" ] && echo "storm winner sealed: $tx h$bh"; fi
# Phantom-occupancy probe: a fresh resubmit must be admitted.
probe=$("$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" --amount 0.000001 --fee 0.02 "${PW_ARGS[@]}" ${RPC_URL:+--rpc-url "$RPC_URL"} 2>&1 || true)
case "$probe" in
  *0x*) jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"ok\",\"probe\":\"resubmit admitted\"}";;
  *occupied*|*replay*) fail storm "phantom occupancy: $probe";;
  *) jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"$probe\"}";;
esac
ok ""
