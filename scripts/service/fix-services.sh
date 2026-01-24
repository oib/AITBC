#!/bin/bash

# Quick fix to start AITBC services in container

echo "🔧 Starting AITBC Services in Container"
echo "====================================="

# First, let's manually start the services
echo "1. Starting Coordinator API..."
cd /home/oib/windsurf/aitbc/apps/coordinator-api
source ../../.venv/bin/activate 2>/dev/null || source .venv/bin/activate
python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 &
COORD_PID=$!

echo "2. Starting Blockchain Node..."
cd ../blockchain-node
python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080 &
NODE_PID=$!

echo "3. Starting Marketplace UI..."
cd ../marketplace-ui
python server.py --port 3001 &
MARKET_PID=$!

echo "4. Starting Trade Exchange..."
cd ../trade-exchange
python server.py --port 3002 &
EXCHANGE_PID=$!

echo ""
echo "✅ Services started!"
echo "Coordinator API: http://127.0.0.1:8000"
echo "Blockchain: http://127.0.0.1:9080"
echo "Marketplace: http://127.0.0.1:3001"
echo "Exchange: http://127.0.0.1:3002"
echo ""
echo "PIDs:"
echo "Coordinator: $COORD_PID"
echo "Blockchain: $NODE_PID"
echo "Marketplace: $MARKET_PID"
echo "Exchange: $EXCHANGE_PID"
echo ""
echo "To stop: kill $COORD_PID $NODE_PID $MARKET_PID $EXCHANGE_PID"

# Wait a bit for services to start
sleep 3

# Test endpoints
echo ""
echo "🧪 Testing endpoints:"
echo "API Health:"
curl -s http://127.0.0.1:8000/v1/health | head -c 100

echo -e "\n\nAdmin Stats:"
curl -s http://127.0.0.1:8000/v1/admin/stats -H "X-Api-Key: REDACTED_ADMIN_KEY" | head -c 100

echo -e "\n\nMarketplace Offers:"
curl -s http://127.0.0.1:8000/v1/marketplace/offers | head -c 100
