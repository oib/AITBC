#!/bin/bash

# Deploy Simple Real AITBC Trade Exchange
echo "🚀 Deploying Simple Real AITBC Trade Exchange..."

cd /opt/aitbc/apps/exchange

# Kill existing services
echo "🔄 Stopping existing services..."
pkill -f "server.py --port 3002" || true
pkill -f "exchange_api.py" || true
pkill -f "apps.exchange.simple_exchange.server" || true

# Start the Simple Exchange API server
echo "🔥 Starting Simple Exchange API server on port 3003..."
PYTHONPATH=/opt/aitbc nohup python3 -m apps.exchange.simple_exchange.server --port 3003 > simple_exchange_api.log 2>&1 &
sleep 2

# Replace the frontend with real trading version
echo "🌐 Updating frontend to use real trading..."
cp index.real.html index.html

# Start the frontend
echo "🌐 Starting Exchange frontend..."
nohup python3 server.py --port 3002 > exchange_frontend.log 2>&1 &
sleep 2

# Check if services are running
echo "✅ Checking services..."
if pgrep -f "apps.exchange.simple_exchange.server" > /dev/null; then
    echo "✓ Simple Exchange API is running on port 3003"
else
    echo "✗ Simple Exchange API failed to start"
    echo "  Check log: tail -f simple_exchange_api.log"
fi

if pgrep -f "server.py --port 3002" > /dev/null; then
    echo "✓ Exchange frontend is running on port 3002"
else
    echo "✗ Exchange frontend failed to start"
fi

echo ""
echo "🎉 Simple Real Exchange Deployment Complete!"
echo ""
echo "📍 Access the exchange at:"
echo "   https://aitbc.bubuit.net/Exchange"
echo ""
echo "📊 The exchange now shows REAL trades from the database!"
echo "   - Recent trades are loaded from the database"
echo "   - Order book shows live orders"
echo "   - You can place real buy/sell orders"
echo ""
echo "📝 Logs:"
echo "   API: tail -f simple_exchange_api.log"
echo "   Frontend: tail -f exchange_frontend.log"
