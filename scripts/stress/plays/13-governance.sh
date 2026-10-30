#!/usr/bin/env bash
# LANE: serial
# MODE: loop
# Governance lifecycle: PROPOSE → VOTE → EXECUTE (wallet-signed on-chain
# txs). Execute may legitimately refuse before tally/quorum — a refusal
# there is logged as expected_refusal, not a failure.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_acquire || exit 75

addr=$("$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"

# --- PROPOSE
title="stress-$(date +%s)"
out=$("$AITBC_BIN" --output=json governance propose --title "$title" --description "stress play $title" \
      --proposer-id "$WALLET" --proposer-address "$addr" 2>&1) || fail propose "governance propose failed: $out"
prop=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"(?:proposal[_-]?id[\"'\'':= ]+)([A-Za-z0-9_-]+)", sys.stdin.read(), re.I); print(m.group(1) if m else "")')
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] && { bh=$(wait_seal "$tx") || exit $?; echo "propose sealed: $tx h$bh"; }
[ -n "$prop" ] || { prop=$("$AITBC_BIN" --output=json governance list 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); ps=d if isinstance(d,list) else d.get("proposals",[]); print(next((p.get("proposal_id") or p.get("id") for p in ps if p.get("title")=="'"$title"'"),""))' 2>/dev/null || true); }
[ -n "$prop" ] || fail propose "no proposal id for $title"

# --- VOTE (for)
out=$("$AITBC_BIN" --output=json governance vote --proposal-id "$prop" --voter-id "$WALLET" --vote for \
      --voter-address "$addr" --wallet "$WALLET" 2>&1) || fail vote "governance vote failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] && { bh=$(wait_seal "$tx") || exit $?; echo "vote sealed: $tx h$bh"; }

# --- EXECUTE (refusal before tally/quorum is a legal lifecycle answer)
out=$("$AITBC_BIN" --output=json governance execute --proposal-id "$prop" --executor-address "$addr" \
      --wallet "$WALLET" 2>&1) && rc=0 || rc=$?
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
if [ $rc -eq 0 ] && [ -n "$tx" ]; then
  bh=$(wait_seal "$tx") || exit $?; echo "execute sealed: $tx h$bh"
elif [ $rc -ne 0 ]; then
  jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"execute refused pre-quorum\",\"proposal\":\"$prop\"}"
  echo "execute refused pre-quorum (expected): proposal $prop"
fi
ok "${tx:-}"
