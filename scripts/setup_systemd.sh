#!/bin/bash

# Setup AITBC Systemd Services
echo "🔧 Setting up AITBC systemd services..."

# Copy service files
echo "📁 Copying service files..."
sudo cp systemd/aitbc-*.service /etc/systemd/system/

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Stop existing processes
echo "⏹️ Stopping existing processes..."
pkill -f "coordinator-api" || true
pkill -f "simple_exchange_api.py" || true
pkill -f "server.py --port 3002" || true
pkill -f "wallet_daemon" || true
pkill -f "node.main" || true

# Enable services
echo "✅ Enabling services..."
sudo systemctl enable aitbc-coordinator-api.service
sudo systemctl enable aitbc-exchange-api.service
sudo systemctl enable aitbc-exchange-frontend.service
sudo systemctl enable aitbc-wallet.service
sudo systemctl enable aitbc-node.service

# Start services
echo "🚀 Starting services..."
sudo systemctl start aitbc-coordinator-api.service
sudo systemctl start aitbc-exchange-api.service
sudo systemctl start aitbc-exchange-frontend.service
sudo systemctl start aitbc-wallet.service
sudo systemctl start aitbc-node.service

# Check status
echo ""
echo "📊 Service Status:"
for service in aitbc-coordinator-api aitbc-exchange-api aitbc-exchange-frontend aitbc-wallet aitbc-node; do
    status=$(sudo systemctl is-active $service)
    echo "  $service: $status"
done

echo ""
echo "📝 To view logs: sudo journalctl -u <service-name> -f"
echo "📝 To restart: sudo systemctl restart <service-name>"
echo "📝 To stop: sudo systemctl stop <service-name>"
