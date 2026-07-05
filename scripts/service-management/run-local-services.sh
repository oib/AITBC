#!/bin/bash

# Run AITBC services locally for domain access
# Uses systemd services (the canonical deployment method)

set -e

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

# Start all AITBC services via systemd
echo "1. Starting Coordinator API (port 8203)..."
sudo systemctl start aitbc-coordinator-api

echo "2. Starting Blockchain RPC (port 8202)..."
sudo systemctl start aitbc-blockchain-rpc

echo "3. Starting Blockchain P2P..."
sudo systemctl start aitbc-blockchain-p2p

echo "4. Starting Exchange (port 8106)..."
sudo systemctl start aitbc-exchange

echo "5. Starting Marketplace (port 8107)..."
sudo systemctl start aitbc-marketplace

echo "6. Starting Trading (port 8201)..."
sudo systemctl start aitbc-trading

echo "7. Starting Wallet (port 8108)..."
sudo systemctl start aitbc-wallet

# Wait for services to start
echo ""
echo "⏳ Waiting for services to initialize..."
sleep 5

# Test services
echo ""
echo "🧪 Testing Services..."

echo -n "Coordinator API Health: "
if curl -s http://127.0.0.1:8203/v1/health > /dev/null 2>&1; then
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
if curl -s http://127.0.0.1:8106/health > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Marketplace: "
if curl -s http://127.0.0.1:8107/health > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Trading: "
if curl -s http://127.0.0.1:8201/health > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Wallet: "
if curl -s http://127.0.0.1:8108/health > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo ""
echo "✅ All services started!"
echo ""
echo "📋 Local URLs:"
echo "   Coordinator API: http://127.0.0.1:8203/v1"
echo "   Blockchain RPC:  http://127.0.0.1:8202/rpc"
echo "   Exchange:        http://127.0.0.1:8106"
echo "   Marketplace:     http://127.0.0.1:8107"
echo "   Trading:         http://127.0.0.1:8201"
echo "   Wallet:          http://127.0.0.1:8108"
echo ""
echo "🌐 Domain URLs (if nginx is configured):"
echo "   API:      https://aitbc.bubuit.net/api"
echo "   Admin:    https://aitbc.bubuit.net/admin"
echo "   RPC:      https://aitbc.bubuit.net/rpc"
echo "   Exchange: https://aitbc.bubuit.net/exchange"
echo ""
echo "📝 Logs: journalctl -u aitbc-exchange -f"
echo "🛑 Stop services: ./stop-services.sh"
