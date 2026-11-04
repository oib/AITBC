#!/usr/bin/env bash
set -euo pipefail

# Quick fix to start AITBC services via systemd
#
# Ports come from lib/services.sh (V23-99). This header used to spell them out inline and
# claim they matched aitbc.constants; they matched neither it nor reality -- market was
# listed on 8107, which is agent-coordinator, and trading on 8201, which is api-gateway.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

echo "🔧 Starting AITBC Services via systemd"
echo "====================================="

# Start services via systemd (canonical method)
FAILED=()
step=0
for svc in "${AITBC_SERVICES[@]}"; do
    step=$((step + 1))
    echo "$step. Starting $svc..."
    if ! sudo -n systemctl start "$svc" 2>/dev/null; then
        FAILED+=("$svc")
        echo "   FAILED: systemctl start $svc"
    fi
done

echo ""
if [ "${#FAILED[@]}" -eq 0 ]; then
    echo "✅ Services started!"
else
    echo "❌ ${#FAILED[@]} service(s) failed to start: ${FAILED[*]}"
fi
echo "Coordinator API: http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}"
echo "Blockchain RPC:  http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-blockchain-rpc]}"
echo "Exchange:        http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}"
echo "Market:     http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-market]}"
echo "Trading:         http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-trading]}"
echo "Wallet:          http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-wallet]}"
echo ""
echo "To check status: systemctl status aitbc-exchange"
echo "To stop:         systemctl stop aitbc-*"

# Wait a bit for services to start
sleep 3

# Test endpoints
echo ""
echo "🧪 Testing endpoints:"
echo "Coordinator API Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/health" | head -c 100 || echo "(no response)"

echo -e "\n\nExchange Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}/health" | head -c 100 || echo "(no response)"

echo -e "\n\nMarket Offers:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-market]}/v1/market/offers" | head -c 100 || echo "(no response)"

echo ""
[ "${#FAILED[@]}" -eq 0 ] || exit 1
