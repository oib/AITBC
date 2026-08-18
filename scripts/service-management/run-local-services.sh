#!/bin/bash

# Run AITBC services locally for domain access
# Uses systemd services (the canonical deployment method)

set -euo pipefail

# Service list and ports come from lib/services.sh so all of these scripts agree.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

echo "🚀 Starting AITBC Services for Domain Access"
echo "=========================================="

# Kill any existing manually-started services (legacy port cleanup)
echo "Cleaning up existing manual processes..."
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true

# Create logs directory
mkdir -p logs

echo ""
echo "📦 Starting Services via systemd..."

# Start all AITBC services via systemd, in the order lib/services.sh defines.
step=1
for svc in "${AITBC_SERVICES[@]}"; do
    port="${AITBC_SERVICE_PORTS[$svc]:-}"
    if [ -n "$port" ]; then
        echo "$step. Starting $svc (port $port)..."
    else
        echo "$step. Starting $svc..."
    fi
    sudo systemctl start "$svc"
    step=$((step + 1))
done

# Wait for services to start
echo ""
echo "⏳ Waiting for services to initialize..."
sleep 5

# Test services
echo ""
echo "🧪 Testing Services..."

echo -n "Coordinator API Health: "
if curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/health" > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Blockchain RPC: "
if curl -s http://127.0.0.1:8202/rpc/head > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Exchange: "
if curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}/health" > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Marketplace: "
if curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-marketplace]}/health" > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Trading: "
if curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-trading]}/health" > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Wallet: "
if curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-wallet]}/health" > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo ""
echo "✅ All services started!"
echo ""
echo "📋 Local URLs:"
echo "   Coordinator API: http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/v1"
echo "   Blockchain RPC:  http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-blockchain-rpc]}/rpc"
echo "   Exchange:        http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}"
echo "   Marketplace:     http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-marketplace]}"
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
