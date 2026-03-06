#!/bin/bash

# Deploy Real AITBC Trade Exchange
echo "🚀 Deploying Real AITBC Trade Exchange..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Kill existing services
echo "🔄 Stopping existing services..."
pkill -f "server.py --port 3002" || true
pkill -f "exchange_api.py" || true

# Start the Exchange API server
echo "🔥 Starting Exchange API server on port 3003..."
nohup python3 exchange_api.py > exchange_api.log 2>&1 &
sleep 2

# Start the frontend with real trading
echo "🌐 Starting Exchange frontend with real trading..."
nohup python3 server.py --port 3002 > exchange_frontend.log 2>&1 &
sleep 2

# Check if services are running
echo "✅ Checking services..."
if pgrep -f "exchange_api.py" > /dev/null; then
    echo "✓ Exchange API is running on port 3003"
else
    echo "✗ Exchange API failed to start"
fi

if pgrep -f "server.py --port 3002" > /dev/null; then
    echo "✓ Exchange frontend is running on port 3002"
else
    echo "✗ Exchange frontend failed to start"
fi

echo ""
echo "🎉 Real Exchange Deployment Complete!"
echo ""
echo "📍 Access the exchange at:"
echo "   Frontend: https://aitbc.bubuit.net/Exchange"
echo "   API: http://localhost:3003"
echo ""
echo "📊 API Endpoints:"
echo "   GET /api/trades/recent - Get recent trades"
echo "   GET /api/orders/orderbook - Get order book"
echo "   POST /api/orders - Place new order"
echo "   GET /api/health - Health check"
echo ""
echo "📝 Logs:"
echo "   API: tail -f exchange_api.log"
echo "   Frontend: tail -f exchange_frontend.log"
