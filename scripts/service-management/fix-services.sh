#!/usr/bin/env bash
set -euo pipefail

# Quick fix to start AITBC services in container
# Ports should match aitbc.constants:
# - COORDINATOR_API_PORT=8203
# - BLOCKCHAIN_RPC_PORT=8202
# - MARKETPLACE_PORT=8081
# - EXCHANGE_PORT=8001

echo "🔧 Starting AITBC Services in Container"
echo "====================================="

# Use environment variables or defaults from aitbc.constants
COORDINATOR_PORT=${COORDINATOR_API_PORT:-8203}
BLOCKCHAIN_PORT=${BLOCKCHAIN_RPC_PORT:-8202}
MARKETPLACE_PORT=${MARKETPLACE_PORT:-8081}
EXCHANGE_PORT=${EXCHANGE_PORT:-8001}

# First, let's manually start the services
echo "1. Starting Coordinator API..."
cd /home/oib/windsurf/aitbc/apps/coordinator-api || exit 1
source ../../.venv/bin/activate 2>/dev/null || source .venv/bin/activate
python -m uvicorn src.app.main:app --host 0.0.0.0 --port "$COORDINATOR_PORT" &
COORD_PID=$!

echo "2. Starting Blockchain Node..."
cd ../blockchain-node || exit 1
python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port "$BLOCKCHAIN_PORT" &
NODE_PID=$!

echo "3. Starting Marketplace UI..."
cd ../marketplace-ui || exit 1
python server.py --port "$MARKETPLACE_PORT" &
MARKET_PID=$!

echo "4. Starting Trade Exchange..."
cd ../trade-exchange || exit 1
python server.py --port "$EXCHANGE_PORT" &
EXCHANGE_PID=$!

echo ""
echo "✅ Services started!"
echo "Coordinator API: http://127.0.0.1:${COORDINATOR_PORT}"
echo "Blockchain: http://127.0.0.1:${BLOCKCHAIN_PORT}"
echo "Marketplace: http://127.0.0.1:${MARKETPLACE_PORT}"
echo "Exchange: http://127.0.0.1:${EXCHANGE_PORT}"
echo ""
echo "PIDs:"
echo "Coordinator: ${COORD_PID}"
echo "Blockchain: ${NODE_PID}"
echo "Marketplace: ${MARKET_PID}"
echo "Exchange: ${EXCHANGE_PID}"
echo ""
echo "To stop: kill ${COORD_PID} ${NODE_PID} ${MARKET_PID} ${EXCHANGE_PID}"

# Wait a bit for services to start
sleep 3

# Test endpoints
echo ""
echo "🧪 Testing endpoints:"
echo "API Health:"
curl -s http://127.0.0.1:"${COORDINATOR_PORT}"/v1/health | head -c 100

echo -e "\n\nAdmin Stats:"
curl -s http://127.0.0.1:"${COORDINATOR_PORT}"/v1/admin/stats -H "X-Api-Key: ${ADMIN_API_KEY}" | head -c 100

echo -e "\n\nMarketplace Offers:"
curl -s http://127.0.0.1:"${COORDINATOR_PORT}"/v1/marketplace/offers | head -c 100
