#!/bin/bash

# Run AITBC services locally for domain access

set -e

echo "🚀 Starting AITBC Services for Domain Access"
echo "=========================================="

# Kill any existing services
echo "Cleaning up existing services..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sudo fuser -k 9080/tcp 2>/dev/null || true
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true
pkill -f "uvicorn.*aitbc" 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true

# Wait for ports to be free
sleep 2

# Create logs directory
mkdir -p logs

echo ""
echo "📦 Starting Services..."

# Start Coordinator API
echo "1. Starting Coordinator API (port 8000)..."
cd apps/coordinator-api
source ../.venv/bin/activate 2>/dev/null || python -m venv ../.venv && source ../.venv/bin/activate
pip install -q -e . 2>/dev/null || true
nohup python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 > ../../logs/api.log 2>&1 &
API_PID=$!
echo "   PID: $API_PID"

# Start Blockchain Node
echo "2. Starting Blockchain Node (port 9080)..."
cd ../blockchain-node
nohup python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080 > ../../logs/blockchain.log 2>&1 &
NODE_PID=$!
echo "   PID: $NODE_PID"

# Start Marketplace UI
echo "3. Starting Marketplace UI (port 3001)..."
cd ../marketplace-ui
nohup python server.py --port 3001 > ../../logs/marketplace.log 2>&1 &
MARKET_PID=$!
echo "   PID: $MARKET_PID"

# Start Trade Exchange
echo "4. Starting Trade Exchange (port 3002)..."
cd ../trade-exchange
nohup python server.py --port 3002 > ../../logs/exchange.log 2>&1 &
EXCHANGE_PID=$!
echo "   PID: $EXCHANGE_PID"

# Save PIDs for cleanup
echo "$API_PID $NODE_PID $MARKET_PID $EXCHANGE_PID" > ../.service_pids

cd ..

# Wait for services to start
echo ""
echo "⏳ Waiting for services to initialize..."
sleep 5

# Test services
echo ""
echo "🧪 Testing Services..."

echo -n "API Health: "
if curl -s http://127.0.0.1:8000/v1/health > /dev/null; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Admin API: "
if curl -s http://127.0.0.1:8000/v1/admin/stats -H "X-Api-Key: ${ADMIN_API_KEY}" > /dev/null; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Blockchain: "
if curl -s http://127.0.0.1:9080/rpc/head > /dev/null; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Marketplace: "
if curl -s http://127.0.0.1:3001 > /dev/null; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo -n "Exchange: "
if curl -s http://127.0.0.1:3002 > /dev/null; then
    echo "✅ OK"
else
    echo "❌ Failed"
fi

echo ""
echo "✅ All services started!"
echo ""
echo "📋 Local URLs:"
echo "   API: http://127.0.0.1:8000/v1"
echo "   RPC: http://127.0.0.1:9080/rpc"
echo "   Marketplace: http://127.0.0.1:3001"
echo "   Exchange: http://127.0.0.1:3002"
echo ""
echo "🌐 Domain URLs (if nginx is configured):"
echo "   API: https://aitbc.bubuit.net/api"
echo "   Admin: https://aitbc.bubuit.net/admin"
echo "   RPC: https://aitbc.bubuit.net/rpc"
echo "   Marketplace: https://aitbc.bubuit.net/Marketplace"
echo "   Exchange: https://aitbc.bubuit.net/Exchange"
echo ""
echo "📝 Logs: ./logs/"
echo "🛑 Stop services: ./stop-services.sh"
echo ""
echo "Press Ctrl+C to stop monitoring (services will keep running)"

# Monitor logs
tail -f logs/*.log
