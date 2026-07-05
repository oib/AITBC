#!/usr/bin/env bash
set -euo pipefail

# Quick fix to start AITBC services via systemd
# Ports match aitbc.constants:
# - COORDINATOR_API_PORT=8203
# - BLOCKCHAIN_RPC_PORT=8202
# - EXCHANGE_PORT=8106
# - MARKETPLACE_PORT=8107
# - TRADING_PORT=8201
# - WALLET_PORT=8108

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
echo "Coordinator API: http://127.0.0.1:8203"
echo "Blockchain RPC:  http://127.0.0.1:8202"
echo "Exchange:        http://127.0.0.1:8106"
echo "Marketplace:     http://127.0.0.1:8107"
echo "Trading:         http://127.0.0.1:8201"
echo "Wallet:          http://127.0.0.1:8108"
echo ""
echo "To check status: systemctl status aitbc-exchange"
echo "To stop:         systemctl stop aitbc-*"

# Wait a bit for services to start
sleep 3

# Test endpoints
echo ""
echo "🧪 Testing endpoints:"
echo "Coordinator API Health:"
curl -s http://127.0.0.1:8203/v1/health | head -c 100

echo -e "\n\nExchange Health:"
curl -s http://127.0.0.1:8106/health | head -c 100

echo -e "\n\nMarketplace Offers:"
curl -s http://127.0.0.1:8107/v1/marketplace/offers | head -c 100
