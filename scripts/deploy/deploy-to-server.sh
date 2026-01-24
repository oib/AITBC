#!/bin/bash

# Deploy AITBC services to the aitbc server (10.1.223.93)

set -e

SERVER="root@10.1.223.93"
PROJECT_DIR="/root/aitbc"

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
scp -r /home/oib/windsurf/aitbc $SERVER:/root/

# Setup Python environment
print_status "Setting up Python environment..."
ssh $SERVER "cd $PROJECT_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip"

# Install dependencies
print_status "Installing dependencies..."
ssh $SERVER "cd $PROJECT_DIR/apps/coordinator-api && source ../../.venv/bin/activate && pip install -e ."
ssh $SERVER "cd $PROJECT_DIR/apps/blockchain-node && source ../../.venv/bin/activate && pip install -e ."

# Create systemd service files
print_status "Creating systemd services..."

# Coordinator API service
ssh $SERVER 'cat > /etc/systemd/system/aitbc-coordinator.service << EOF
[Unit]
Description=AITBC Coordinator API
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/root/aitbc/apps/coordinator-api
Environment=PATH=/root/aitbc/.venv/bin
ExecStart=/root/aitbc/.venv/bin/python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF'

# Blockchain Node service
ssh $SERVER 'cat > /etc/systemd/system/aitbc-blockchain.service << EOF
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/root/aitbc/apps/blockchain-node
Environment=PATH=/root/aitbc/.venv/bin
ExecStart=/root/aitbc/.venv/bin/python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF'

# Marketplace UI service
ssh $SERVER 'cat > /etc/systemd/system/aitbc-marketplace.service << EOF
[Unit]
Description=AITBC Marketplace UI
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/root/aitbc/apps/marketplace-ui
Environment=PATH=/root/aitbc/.venv/bin
ExecStart=/root/aitbc/.venv/bin/python server.py --port 3001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF'

# Trade Exchange service
ssh $SERVER 'cat > /etc/systemd/system/aitbc-exchange.service << EOF
[Unit]
Description=AITBC Trade Exchange
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/root/aitbc/apps/trade-exchange
Environment=PATH=/root/aitbc/.venv/bin
ExecStart=/root/aitbc/.venv/bin/python server.py --port 3002
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF'

# Install nginx if not installed
print_status "Installing nginx..."
ssh $SERVER "apt update && apt install -y nginx"

# Create nginx configuration
print_status "Configuring nginx..."
ssh $SERVER 'cat > /etc/nginx/sites-available/aitbc << EOF
server {
    listen 80;
    server_name aitbc.bubuit.net;
    
    # API routes
    location /api/ {
        proxy_pass http://127.0.0.1:8000/v1/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Admin routes
    location /admin/ {
        proxy_pass http://127.0.0.1:8000/admin/;
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
    location /Marketplace {
        proxy_pass http://127.0.0.1:3001/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Trade Exchange
    location /Exchange {
        proxy_pass http://127.0.0.1:3002/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Health endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/v1/health;
        proxy_set_header Host \$host;
    }
    
    # Default redirect
    location / {
        return 301 /Marketplace;
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
ssh $SERVER "systemctl enable aitbc-coordinator aitbc-blockchain aitbc-marketplace aitbc-exchange"
ssh $SERVER "systemctl start aitbc-coordinator aitbc-blockchain aitbc-marketplace aitbc-exchange"

# Wait for services to start
print_status "Waiting for services to start..."
sleep 10

# Check service status
print_status "Checking service status..."
ssh $SERVER "systemctl status aitbc-coordinator --no-pager -l | head -10"
ssh $SERVER "systemctl status aitbc-blockchain --no-pager -l | head -10"

# Test endpoints
print_status "Testing endpoints..."
ssh $SERVER "curl -s http://127.0.0.1:8000/v1/health | head -c 100"
echo ""
ssh $SERVER "curl -s http://127.0.0.1:8000/v1/admin/stats -H 'X-Api-Key: REDACTED_ADMIN_KEY' | head -c 100"
echo ""

echo ""
print_status "✅ Deployment complete!"
echo ""
echo "📋 Service URLs:"
echo "  🌐 Server IP: 10.1.223.93"
echo "  📊 Marketplace: http://10.1.223.93/Marketplace"
echo "  💱 Trade Exchange: http://10.1.223.93/Exchange"
echo "  🔗 API: http://10.1.223.93/api"
echo "  ⛓️  Blockchain RPC: http://10.1.223.93/rpc"
echo ""
echo "🔒 Domain URLs (with SSL):"
echo "  📊 Marketplace: https://aitbc.bubuit.net/Marketplace"
echo "  💱 Trade Exchange: https://aitbc.bubuit.net/Exchange"
echo "  🔗 API: https://aitbc.bubuit.net/api"
echo "  ⛓️  Blockchain RPC: https://aitbc.bubuit.net/rpc"
echo ""
print_status "To manage services:"
echo "  ssh aitbc 'systemctl status aitbc-coordinator'"
echo "  ssh aitbc 'journalctl -u aitbc-coordinator -f'"
