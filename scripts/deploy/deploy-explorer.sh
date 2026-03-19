#!/bin/bash

# Deploy AITBC Explorer to the server

set -e

SERVER="root@10.1.223.93"
EXPLORER_DIR="/root/aitbc/apps/explorer-web"
NGINX_CONFIG="/etc/nginx/sites-available/aitbc"

echo "🚀 Deploying AITBC Explorer to Server"
echo "====================================="
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

# Build the explorer locally first
print_status "Building explorer locally..."
cd /home/oib/windsurf/aitbc/apps/explorer-web
npm run build

# Copy built files to server
print_status "Copying explorer build to server..."
scp -r dist $SERVER:$EXPLORER_DIR/

# Update nginx config to include explorer
print_status "Updating nginx configuration..."

# Backup current config
ssh $SERVER "cp $NGINX_CONFIG ${NGINX_CONFIG}.backup"

# Add explorer location to nginx config
ssh $SERVER "sed -i '/# Health endpoint/i\\
    # Explorer\\
    location /explorer/ {\\
        alias /root/aitbc/apps/explorer-web/dist/;\\
        try_files \$uri \$uri/ /explorer/index.html;\\
    }\\
\\
    # Explorer mock data\\
    location /explorer/mock/ {\\
        alias /root/aitbc/apps/explorer-web/public/mock/;\\
    }\\
' $NGINX_CONFIG"

# Test and reload nginx
print_status "Testing and reloading nginx..."
ssh $SERVER "nginx -t && systemctl reload nginx"

print_status "✅ Explorer deployment complete!"
echo ""
echo "📋 Explorer URL:"
echo "  🌐 Explorer: https://aitbc.bubuit.net/explorer/"
echo ""
