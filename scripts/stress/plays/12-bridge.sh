#!/usr/bin/env bash
# LANE: serial
# MODE: loop
# Bridge ledger legs — lock → (release|refund) via the ledger service.
# Serial: shares the nonce window with governance + island plays.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_acquire || exit 75

# Register a pending row in the shared ledger (dev-sized), verify the
# service round-trips it, then mark it refunded — the ledger write path
# is what the exercise stresses; real lock/release legs ride the same
# routes when a funded sender is configured.
led="${BRIDGE_LEDGER_URL:-https://hub.aitbc.bubuit.net}"
if [ -z "${BRIDGE_LEDGER_API_KEY:-}" ]; then
  BRIDGE_LEDGER_API_KEY=$(grep -h "^BRIDGE_LEDGER_API_KEY=" /etc/aitbc/*.env 2>/dev/null | head -1 | cut -d= -f2-)
fi
if [ -z "${BLOCKCHAIN_RPC_API_KEY:-}" ]; then
  BLOCKCHAIN_RPC_API_KEY=$(grep -h "^BLOCKCHAIN_RPC_API_KEY=" /etc/aitbc/*.env 2>/dev/null | head -1 | cut -d= -f2-)
fi
row="stress-$(date +%s)-$$"
body="{\"transfer_id\":\"$row\",\"source_chain\":\"$CHAIN\",\"target_chain\":\"bc-2-island-1\",\"sender\":\"0x00000000000000000000000000000000000000ff\",\"recipient\":\"0x00000000000000000000000000000000000000ee\",\"amount\":$AMOUNT,\"status\":\"pending\"}"
resp=$(curl -sf --max-time 15 -X POST -H 'Content-Type: application/json' -H "X-API-Key: ${BRIDGE_LEDGER_API_KEY:-$BLOCKCHAIN_RPC_API_KEY}" -d "$body" "$led/rpc/bridge/ledger/register" 2>&1) \
  || fail ledger-register "register failed: $resp"
pend=$(curl -sf --max-time 15 -H "X-API-Key: ${BRIDGE_LEDGER_API_KEY:-$BLOCKCHAIN_RPC_API_KEY}" "$led/rpc/bridge/ledger/pending?target_chain=bc-2-island-1" | grep -c "$row" || true)
[ "$pend" -ge 1 ] || fail ledger-pending "row $row not in pending worklist"
curl -sf --max-time 15 -X POST -H 'Content-Type: application/json' -H "X-API-Key: ${BRIDGE_LEDGER_API_KEY:-$BLOCKCHAIN_RPC_API_KEY}" \
  -d '{"status":"refunded"}' "$led/rpc/bridge/ledger/$row/status" >/dev/null || fail ledger-status "status writeback failed"
echo "ledger round-trip ok: $row registered+refunded"
ok ""
