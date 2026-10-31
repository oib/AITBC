#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# MESSAGE post — messaging send --confirm submits + signs; the record
# seals like any other tx. STRESS_MSG_BYTES=<n> pads the message to n
# bytes for max-payload / commit-path-pressure legs.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

msg="stress $(now)"
[ -n "${STRESS_MSG_BYTES:-}" ] && msg="$msg $(python3 -c "print('x'*max(0,$STRESS_MSG_BYTES-${#msg}-1))")"
out=$("$AITBC_BIN" --output=json messaging send --wallet "$WALLET" \
  --message "$msg" --topic stress --confirm 2>&1) || fail send "messaging send failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail send "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "message sealed: $tx h$bh"
ok "$tx"
