#!/usr/bin/env bash
# LANE: serial
# MODE: loop
# Island legs: bc-2-island-1 head parity across hub1/node1 (serial lane
# shares the nonce-sensitive island window with bridge plays).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_acquire || exit 75

h1=$(ssh hub1 'curl -sf --max-time 10 http://127.0.0.1:8203/rpc/status | python3 -c "import json,sys;print(json.load(sys.stdin).get(\"height\",-1))" 2>/dev/null || echo -1')
n1=$(ssh node1 'curl -sf --max-time 10 http://127.0.0.1:8203/rpc/status | python3 -c "import json,sys;print(json.load(sys.stdin).get(\"height\",-1))" 2>/dev/null || echo -1')
[ "$h1" -gt 0 ] || fail island-status "hub1 island rpc unreachable (h=$h1)"
[ "$n1" -gt 0 ] || fail island-status "node1 island rpc unreachable (h=$n1)"
diff=$(( h1 - n1 )); [ $diff -lt 0 ] && diff=$(( -diff ))
[ "$diff" -le 3 ] || fail island-parity "hub1=$h1 node1=$n1 gap=$diff"
echo "island parity ok: hub1=$h1 node1=$n1"
ok ""
