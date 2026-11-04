#!/bin/bash

# Run AITBC services locally for domain access
# Uses systemd services (the canonical deployment method)

set -euo pipefail

# Service list and ports come from lib/services.sh so all of these scripts agree.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

echo "🚀 Starting AITBC Services for Domain Access"
echo "=========================================="

# Create logs directory
mkdir -p logs

echo ""
echo "📦 Starting Services via systemd..."

# Start all AITBC services via systemd, in the order lib/services.sh defines.
START_FAILED=()
step=1
for svc in "${AITBC_SERVICES[@]}"; do
    port="${AITBC_SERVICE_PORTS[$svc]:-}"
    if [ -n "$port" ]; then
        echo "$step. Starting $svc (port $port)..."
    else
        echo "$step. Starting $svc..."
    fi
    sudo -n systemctl start "$svc" || START_FAILED+=("$svc")
    step=$((step + 1))
done

# Wait for services to start
echo ""
echo "⏳ Waiting for services to initialize..."
sleep 5

# Test services
echo ""
echo "🧪 Testing Services..."

HEALTH_FAILED=()
check() {  # name port path
    echo -n "$1: "
    if curl -fsS "http://127.0.0.1:$2$3" > /dev/null 2>&1; then
        echo "✅ OK"
    else
        echo "❌ Failed"
        HEALTH_FAILED+=("$1")
    fi
}

check "Coordinator API Health" "${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}" /health
check "Blockchain RPC"         "${AITBC_SERVICE_PORTS[aitbc-blockchain-rpc]}" /rpc/head
check "Exchange"               "${AITBC_SERVICE_PORTS[aitbc-exchange]}" /health
check "Market"                 "${AITBC_SERVICE_PORTS[aitbc-market]}" /health
check "Trading"                "${AITBC_SERVICE_PORTS[aitbc-trading]}" /health
check "Wallet"                 "${AITBC_SERVICE_PORTS[aitbc-wallet]}" /health

echo ""
if [ "${#START_FAILED[@]}" -eq 0 ] && [ "${#HEALTH_FAILED[@]}" -eq 0 ]; then
    echo "✅ All services started!"
else
    [ "${#START_FAILED[@]}" -gt 0 ] && echo "❌ failed to start: ${START_FAILED[*]}"
    [ "${#HEALTH_FAILED[@]}" -gt 0 ] && echo "❌ failed health checks: ${HEALTH_FAILED[*]}"
fi
echo ""
echo "📋 Local URLs:"
echo "   Coordinator API: http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/v1"
echo "   Blockchain RPC:  http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-blockchain-rpc]}/rpc"
echo "   Exchange:        http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}"
echo "   Market:     http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-market]}"
echo "   Trading:         http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-trading]}"
echo "   Wallet:          http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-wallet]}"
echo ""
echo "🌐 Domain URLs (if nginx is configured):"
echo "   API:      https://aitbc.bubuit.net/api"
echo "   Admin:    https://aitbc.bubuit.net/admin"
echo "   RPC:      https://aitbc.bubuit.net/rpc"
echo "   Exchange: https://aitbc.bubuit.net/exchange"
echo ""
echo "📝 Logs: journalctl -u aitbc-exchange -f"
echo "🛑 Stop services: ./stop-services.sh"

[ "${#START_FAILED[@]}" -eq 0 ] && [ "${#HEALTH_FAILED[@]}" -eq 0 ] || exit 1
