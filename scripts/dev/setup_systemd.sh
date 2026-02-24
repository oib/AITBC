#!/bin/bash

# Setup AITBC Systemd Services
# Requirements: Python 3.11+, systemd, sudo access

echo "🔧 Setting up AITBC systemd services..."

# Validate Python version
echo "🐍 Checking Python version..."
if ! python3.11 --version >/dev/null 2>&1; then
    echo "❌ Error: Python 3.11+ is required but not found"
    echo "   Please install Python 3.11+ and try again"
    exit 1
fi

PYTHON_VERSION=$(python3.11 --version | cut -d' ' -f2)
echo "✅ Found Python $PYTHON_VERSION"

# Validate systemctl is available
if ! command -v systemctl >/dev/null 2>&1; then
    echo "❌ Error: systemctl not found. This script requires systemd."
    exit 1
fi

echo "✅ Systemd available"

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
