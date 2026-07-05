#!/bin/bash

# Deploy AITBC services to the aitbc server
# Uses the canonical systemd service files from the repo

set -e

SERVER="${AITBC_DEPLOY_SERVER:-root@127.0.0.1}"
PROJECT_DIR="/opt/aitbc"

echo "🚀 Deploying AITBC to Server"
echo "=========================="
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

# Copy project to server
print_status "Copying project to server..."
ssh $SERVER "rm -rf $PROJECT_DIR 2>/dev/null || true"
scp -r /opt/aitbc $SERVER:/opt/

# Setup Python environment
print_status "Setting up Python environment..."
ssh $SERVER "cd $PROJECT_DIR && python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip"

# Install dependencies
print_status "Installing dependencies..."
ssh $SERVER "cd $PROJECT_DIR/apps/coordinator-api && source ../../venv/bin/activate && pip install -e ."
ssh $SERVER "cd $PROJECT_DIR/apps/blockchain-node && source ../../venv/bin/activate && pip install -e ."
ssh $SERVER "cd $PROJECT_DIR/apps/marketplace && source ../../venv/bin/activate && pip install -e ."
ssh $SERVER "cd $PROJECT_DIR/apps/trading && source ../../venv/bin/activate && pip install -e ."
ssh $SERVER "cd $PROJECT_DIR/apps/wallet && source ../../venv/bin/activate && pip install -e ."

# Install systemd service files from the repo
print_status "Installing systemd services..."

# Copy all aitbc-*.service files from the repo to /etc/systemd/system/
ssh $SERVER "find $PROJECT_DIR/apps -name 'aitbc-*.service' -exec cp {} /etc/systemd/system/ \;"

# Install nginx if not installed
print_status "Installing nginx..."
ssh $SERVER "apt update && apt install -y nginx"

# Create nginx configuration
print_status "Configuring nginx..."
ssh $SERVER 'cat > /etc/nginx/sites-available/aitbc << EOF
server {
    listen 80;
    server_name aitbc.bubuit.net;

    # Coordinator API
    location /api/ {
        proxy_pass http://127.0.0.1:8203/v1/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Admin routes
    location /admin/ {
        proxy_pass http://127.0.0.1:8203/admin/;
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

    # Health endpoint
    location /health {
        proxy_pass http://127.0.0.1:8203/v1/health;
        proxy_set_header Host \$host;
    }

    # Default redirect
    location / {
        return 301 /marketplace/;
    }
}
EOF'

# Enable nginx site
ssh $SERVER "ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/"
ssh $SERVER "rm -f /etc/nginx/sites-enabled/default"

# Test and reload nginx
ssh $SERVER "nginx -t && systemctl reload nginx"

# Start services
print_status "Starting AITBC services..."
ssh $SERVER "systemctl daemon-reload"
ssh $SERVER "systemctl enable aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet"
ssh $SERVER "systemctl start aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet"

# Wait for services to start
print_status "Waiting for services to start..."
sleep 10

# Check service status
print_status "Checking service status..."
ssh $SERVER "systemctl status aitbc-coordinator-api --no-pager -l | head -10"
ssh $SERVER "systemctl status aitbc-exchange --no-pager -l | head -10"

# Test endpoints
print_status "Testing endpoints..."
ssh $SERVER "curl -s http://127.0.0.1:8203/v1/health | head -c 100"
echo ""
ssh $SERVER "curl -s http://127.0.0.1:8106/health | head -c 100"
echo ""

echo ""
print_status "✅ Deployment complete!"
echo ""
echo "📋 Service URLs:"
echo "  🌐 Server IP: 10.1.223.93"
echo "  💱 Exchange:        http://10.1.223.93/exchange/"
echo "  📊 Marketplace:     http://10.1.223.93/marketplace/"
echo "  🔗 API:             http://10.1.223.93/api/"
echo "  ⛓️  Blockchain RPC:  http://10.1.223.93/rpc/"
echo ""
echo "🔒 Domain URLs (with SSL):"
echo "  💱 Exchange:        https://aitbc.bubuit.net/exchange"
echo "  📊 Marketplace:     https://aitbc.bubuit.net/marketplace"
echo "  🔗 API:             https://aitbc.bubuit.net/api"
echo "  ⛓️  Blockchain RPC:  https://aitbc.bubuit.net/rpc"
echo ""
print_status "To manage services:"
echo "  ssh aitbc 'systemctl status aitbc-exchange'"
echo "  ssh aitbc 'journalctl -u aitbc-exchange -f'"
