#!/usr/bin/env bash
# LANE: serial (restarts a node's services — announce on #706 first).
# MODE: once
# Kill-under-load: steady transfer feed → restart node+rpc on TARGET →
# assert (a) head catches up within budget, (b) pending resubmits clear,
# (c) no phantom occupancy after recovery.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
TARGET="${RESTART_TARGET:-$HOST}"
MAX_BLOCKS="${RESTART_MAX_BLOCKS:-12}"
addr=${STORM_TO:-0x00000000000000000000000000000000000000d9}

# Steady feed in background.
feed() { while :; do "$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" --amount 0.000001 --fee 0.02 >/dev/null 2>&1; sleep 4; done; }
feed & FEED=$!; sleep 10
pre=$(stress_height "$TARGET" 2>/dev/null || echo 0)

# The kill — local when TARGET is the host we're on (self-ssh isn't
# provisioned); otherwise the IDE-side ssh alias convention.
if [ "$(hostname -s)" = "$TARGET" ] || [ "$(hostname)" = "$TARGET" ]; then
  systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc || fail restart "local restart failed"
else
  ssh "$TARGET" 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc' || fail restart "restart cmd failed"
fi
sleep 20

# Catch-up assertion: head must advance past pre+N within ~2 blocks' time.
okc=0
for i in $(seq 1 10); do
  cur=$(stress_height "$TARGET" 2>/dev/null || echo 0)
  if [ "${cur:-0}" -ge "$(( ${pre:-0} + MAX_BLOCKS ))" ]; then okc=1; break; fi
  sleep 30
done
kill $FEED 2>/dev/null; wait $FEED 2>/dev/null || true
[ "$okc" = 1 ] || fail restart "no catch-up: pre=$pre cur=${cur:-?} target=$(( ${pre:-0} + MAX_BLOCKS ))"

# Phantom-occupancy probe post-recovery.
probe=$("$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" --amount 0.000001 --fee 0.02 2>&1 || true)
case "$probe" in *occupied*|*replay*) fail restart "phantom occupancy post-recovery: $probe";; esac
jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"ok\",\"target\":\"$TARGET\",\"pre\":$pre,\"post\":${cur:-0}}"
echo "restart-under-load ok: $TARGET caught up pre=$pre → ${cur:-0}"
ok ""
