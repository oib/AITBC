#!/bin/bash

# AITBC Services Deployment to Incus Container
# This script deploys all AITBC services to the 'aitbc' container
# Uses the canonical systemd service files from the repo

set -e

CONTAINER_NAME="aitbc"
CONTAINER_IP="${AITBC_CONTAINER_IP:-127.0.0.1}"
PROJECT_DIR="/opt/aitbc"

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
sudo systemctl stop aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet 2>/dev/null || true
sudo systemctl stop aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p 2>/dev/null || true

# Copy project to container
print_status "Copying AITBC project to container..."
incus file push -r $PROJECT_DIR $CONTAINER_NAME/opt/

# Setup container environment
print_status "Setting up container environment..."
incus exec $CONTAINER_NAME -- bash -c "
cd /opt/aitbc
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
"

# Install dependencies for each service
print_status "Installing dependencies..."

# Coordinator API
print_status "Installing Coordinator API dependencies..."
incus exec $CONTAINER_NAME -- bash -c "
cd /opt/aitbc/apps/coordinator-api
source ../.venv/bin/activate
pip install -e .
pip install fastapi uvicorn
"

# Blockchain Node
print_status "Installing Blockchain Node dependencies..."
incus exec $CONTAINER_NAME -- bash -c "
cd /opt/aitbc/apps/blockchain-node
source ../.venv/bin/activate
pip install -e .
pip install fastapi uvicorn
"

# Exchange, Marketplace, Trading, Wallet
print_status "Installing Exchange, Marketplace, Trading, Wallet dependencies..."
incus exec $CONTAINER_NAME -- bash -c "
cd /opt/aitbc
source venv/bin/activate
pip install -e apps/marketplace apps/trading apps/wallet
"

# Install systemd service files from the repo
print_status "Installing systemd services..."
incus exec $CONTAINER_NAME -- bash -c "
find /opt/aitbc/apps -name 'aitbc-*.service' -exec cp {} /etc/systemd/system/ \;
systemctl daemon-reload
"

# Reload systemd and start services
print_status "Starting AITBC services..."
incus exec $CONTAINER_NAME -- systemctl enable aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p
incus exec $CONTAINER_NAME -- systemctl enable aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet

incus exec $CONTAINER_NAME -- systemctl start aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p
incus exec $CONTAINER_NAME -- systemctl start aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet

# Wait for services to start
print_status "Waiting for services to start..."
sleep 10

# Check service status
print_status "Checking service status..."
incus exec $CONTAINER_NAME -- systemctl status aitbc-coordinator-api --no-pager -l | head -10
incus exec $CONTAINER_NAME -- systemctl status aitbc-exchange --no-pager -l | head -10

# Create nginx configuration for reverse proxy
print_status "Setting up Nginx reverse proxy..."
incus exec $CONTAINER_NAME -- tee /etc/nginx/sites-available/aitbc > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    # Coordinator API
    location /api/ {
        proxy_pass http://127.0.0.1:8203/v1/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Blockchain RPC
    location /rpc/ {
        proxy_pass http://127.0.0.1:8202/rpc/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Exchange API
    location /exchange/ {
        proxy_pass http://127.0.0.1:8106/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Marketplace
    location /marketplace/ {
        proxy_pass http://127.0.0.1:8107/;
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
echo "  💱 Exchange:        http://$CONTAINER_IP/exchange/"
echo "  📊 Marketplace:     http://$CONTAINER_IP/marketplace/"
echo "  🔗 API:             http://$CONTAINER_IP/api/"
echo "  ⛓️  Blockchain RPC:  http://$CONTAINER_IP/rpc/"
echo ""
print_status "To check logs: incus exec $CONTAINER_NAME -- journalctl -u aitbc-exchange -f"
print_status "To restart services: incus exec $CONTAINER_NAME -- systemctl restart aitbc-*"
