#!/usr/bin/env bash
set -euo pipefail

# Quick fix to start AITBC services via systemd
#
# Ports come from lib/services.sh (V23-99). This header used to spell them out inline and
# claim they matched aitbc.constants; they matched neither it nor reality -- marketplace was
# listed on 8107, which is agent-coordinator, and trading on 8201, which is api-gateway.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

echo "🔧 Starting AITBC Services via systemd"
echo "====================================="

# Start services via systemd (canonical method)
echo "1. Starting Coordinator API..."
sudo systemctl start aitbc-coordinator-api 2>/dev/null || echo "   (already running or not installed)"

echo "2. Starting Blockchain RPC..."
sudo systemctl start aitbc-blockchain-rpc 2>/dev/null || echo "   (already running or not installed)"

echo "3. Starting Blockchain P2P..."
sudo systemctl start aitbc-blockchain-p2p 2>/dev/null || echo "   (already running or not installed)"

echo "4. Starting Exchange..."
sudo systemctl start aitbc-exchange 2>/dev/null || echo "   (already running or not installed)"

echo "5. Starting Marketplace..."
sudo systemctl start aitbc-marketplace 2>/dev/null || echo "   (already running or not installed)"

echo "6. Starting Trading..."
sudo systemctl start aitbc-trading 2>/dev/null || echo "   (already running or not installed)"

echo "7. Starting Wallet..."
sudo systemctl start aitbc-wallet 2>/dev/null || echo "   (already running or not installed)"

echo ""
echo "✅ Services started!"
echo "Coordinator API: http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}"
echo "Blockchain RPC:  http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-blockchain-rpc]}"
echo "Exchange:        http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}"
echo "Marketplace:     http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-marketplace]}"
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
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/health" | head -c 100

echo -e "\n\nExchange Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}/health" | head -c 100

echo -e "\n\nMarketplace Offers:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-marketplace]}/v1/marketplace/offers" | head -c 100
