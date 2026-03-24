#!/bin/bash

# AITBC Services Deployment to Incus Container
# This script deploys all AITBC services to the 'aitbc' container

set -e

CONTAINER_NAME="aitbc"
CONTAINER_IP="10.1.223.93"
PROJECT_DIR="/home/oib/windsurf/aitbc"

echo "🚀 Deploying AITBC services to container: $CONTAINER_NAME"
echo "Container IP: $CONTAINER_IP"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Stop local services
print_status "Stopping local AITBC services..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sudo fuser -k 9080/tcp 2>/dev/null || true
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true
pkill -f "aitbc_chain.app" 2>/dev/null || true
pkill -f "marketplace-ui" 2>/dev/null || true
pkill -f "trade-exchange" 2>/dev/null || true

# Copy project to container
print_status "Copying AITBC project to container..."
incus file push -r $PROJECT_DIR $CONTAINER_NAME/home/oib/

# Setup container environment
print_status "Setting up container environment..."
incus exec $CONTAINER_NAME -- bash -c "
cd /home/oib/aitbc
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
"

# Install dependencies for each service
print_status "Installing dependencies..."

# Coordinator API
print_status "Installing Coordinator API dependencies..."
incus exec $CONTAINER_NAME -- bash -c "
cd /home/oib/aitbc/apps/coordinator-api
source ../.venv/bin/activate
pip install -e .
pip install fastapi uvicorn
"

# Blockchain Node
print_status "Installing Blockchain Node dependencies..."
incus exec $CONTAINER_NAME -- bash -c "
cd /home/oib/aitbc/apps/blockchain-node
source ../.venv/bin/activate
pip install -e .
pip install fastapi uvicorn
"

# Create systemd service files
print_status "Creating systemd services..."

# Coordinator API service
incus exec $CONTAINER_NAME -- tee /etc/systemd/system/aitbc-coordinator.service > /dev/null <<EOF
[Unit]
Description=AITBC Coordinator API
After=network.target

[Service]
Type=exec
User=oib
Group=oib
WorkingDirectory=/home/oib/aitbc/apps/coordinator-api
Environment=PATH=/home/oib/aitbc/.venv/bin
ExecStart=/home/oib/aitbc/.venv/bin/python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Blockchain Node service
incus exec $CONTAINER_NAME -- tee /etc/systemd/system/aitbc-blockchain.service > /dev/null <<EOF
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=exec
User=oib
Group=oib
WorkingDirectory=/home/oib/aitbc/apps/blockchain-node
Environment=PATH=/home/oib/aitbc/.venv/bin
ExecStart=/home/oib/aitbc/.venv/bin/python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Marketplace UI service
incus exec $CONTAINER_NAME -- tee /etc/systemd/system/aitbc-marketplace.service > /dev/null <<EOF
[Unit]
Description=AITBC Marketplace UI
After=network.target

[Service]
Type=exec
User=oib
Group=oib
WorkingDirectory=/home/oib/aitbc/apps/marketplace-ui
Environment=PATH=/home/oib/aitbc/.venv/bin
ExecStart=/home/oib/aitbc/.venv/bin/python server.py --port 3001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Trade Exchange service
incus exec $CONTAINER_NAME -- tee /etc/systemd/system/aitbc-exchange.service > /dev/null <<EOF
[Unit]
Description=AITBC Trade Exchange
After=network.target

[Service]
Type=exec
User=oib
Group=oib
WorkingDirectory=/home/oib/aitbc/apps/trade-exchange
Environment=PATH=/home/oib/aitbc/.venv/bin
ExecStart=/home/oib/aitbc/.venv/bin/python server.py --port 3002
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start services
print_status "Starting AITBC services..."
incus exec $CONTAINER_NAME -- systemctl daemon-reload
incus exec $CONTAINER_NAME -- systemctl enable aitbc-coordinator
incus exec $CONTAINER_NAME -- systemctl enable aitbc-blockchain
incus exec $CONTAINER_NAME -- systemctl enable aitbc-marketplace
incus exec $CONTAINER_NAME -- systemctl enable aitbc-exchange

incus exec $CONTAINER_NAME -- systemctl start aitbc-coordinator
incus exec $CONTAINER_NAME -- systemctl start aitbc-blockchain
incus exec $CONTAINER_NAME -- systemctl start aitbc-marketplace
incus exec $CONTAINER_NAME -- systemctl start aitbc-exchange

# Wait for services to start
print_status "Waiting for services to start..."
sleep 10

# Check service status
print_status "Checking service status..."
incus exec $CONTAINER_NAME -- systemctl status aitbc-coordinator --no-pager -l
incus exec $CONTAINER_NAME -- systemctl status aitbc-blockchain --no-pager -l
incus exec $CONTAINER_NAME -- systemctl status aitbc-marketplace --no-pager -l
incus exec $CONTAINER_NAME -- systemctl status aitbc-exchange --no-pager -l

# Create nginx configuration for reverse proxy
print_status "Setting up Nginx reverse proxy..."
incus exec $CONTAINER_NAME -- tee /etc/nginx/sites-available/aitbc > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    # Coordinator API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/v1/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Blockchain RPC
    location /rpc/ {
        proxy_pass http://127.0.0.1:9080/rpc/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Marketplace UI
    location /marketplace/ {
        proxy_pass http://127.0.0.1:3001/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Trade Exchange
    location /exchange/ {
        proxy_pass http://127.0.0.1:3002/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Default redirect to marketplace
    location / {
        return 301 /marketplace/;
    }
}
EOF

# Enable nginx site
incus exec $CONTAINER_NAME -- ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/
incus exec $CONTAINER_NAME -- rm -f /etc/nginx/sites-enabled/default
incus exec $CONTAINER_NAME -- nginx -t && incus exec $CONTAINER_NAME -- systemctl reload nginx

# Print access information
echo ""
print_status "✅ AITBC services deployed successfully!"
echo ""
echo "📋 Service URLs:"
echo "  🌐 Public IP: $CONTAINER_IP"
echo "  📊 Marketplace: http://$CONTAINER_IP/marketplace/"
echo "  💱 Trade Exchange: http://$CONTAINER_IP/exchange/"
echo "  🔗 API: http://$CONTAINER_IP/api/"
echo "  ⛓️  Blockchain RPC: http://$CONTAINER_IP/rpc/"
echo ""
print_status "To check logs: incus exec $CONTAINER_NAME -- journalctl -u aitbc-coordinator -f"
print_status "To restart services: incus exec $CONTAINER_NAME -- systemctl restart aitbc-*"
