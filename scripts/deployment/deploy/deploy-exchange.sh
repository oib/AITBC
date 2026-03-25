#!/bin/bash

# Deploy AITBC Trade Exchange to the server

set -e

SERVER="root@10.1.223.93"
EXCHANGE_DIR="/root/aitbc/apps/trade-exchange"

echo "🚀 Deploying AITBC Trade Exchange"
echo "=================================="
echo "Server: $SERVER"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test SSH connection
print_status "Testing SSH connection..."
ssh $SERVER "hostname && ip a show eth0 | grep inet"

# Copy updated files
print_status "Copying updated Exchange files..."
scp /home/oib/windsurf/aitbc/apps/trade-exchange/index.html $SERVER:$EXCHANGE_DIR/
scp /home/oib/windsurf/aitbc/apps/trade-exchange/server.py $SERVER:$EXCHANGE_DIR/

# Ensure assets are available
print_status "Ensuring assets directory exists..."
ssh $SERVER "mkdir -p /var/www/aitbc.bubuit.net/assets"
ssh $SERVER "mkdir -p /var/www/aitbc.bubuit.net/assets/css"
ssh $SERVER "mkdir -p /var/www/aitbc.bubuit.net/assets/js"

# Copy assets if they don't exist
print_status "Copying assets if needed..."
if ! ssh $SERVER "test -f /var/www/aitbc.bubuit.net/assets/css/aitbc.css"; then
    scp -r /home/oib/windsurf/aitbc/assets/* $SERVER:/var/www/aitbc.bubuit.net/assets/
fi

# Restart the exchange service
print_status "Restarting Trade Exchange service..."
ssh $SERVER "systemctl restart aitbc-exchange"

# Wait for service to start
print_status "Waiting for service to start..."
sleep 5

# Check service status
print_status "Checking service status..."
ssh $SERVER "systemctl status aitbc-exchange --no-pager -l | head -10"

# Test the endpoint
print_status "Testing Exchange endpoint..."
ssh $SERVER "curl -s http://127.0.0.1:3002/ | head -c 100"
echo ""

echo ""
print_status "✅ Exchange deployment complete!"
echo ""
echo "📋 URLs:"
echo "  🌐 IP: http://10.1.223.93/Exchange"
echo "  🔒 Domain: https://aitbc.bubuit.net/Exchange"
echo ""
echo "🔍 To check logs:"
echo "  ssh $SERVER 'journalctl -u aitbc-exchange -f'"
