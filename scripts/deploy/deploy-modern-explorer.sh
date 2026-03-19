#!/bin/bash

# Deploy Modern Blockchain Explorer

set -e

echo "🚀 Deploying Modern Blockchain Explorer"
echo "======================================"

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

# Stop existing services
print_status "Stopping existing services..."
systemctl stop nginx 2>/dev/null || true

# Create directory
print_status "Creating explorer directory..."
rm -rf /opt/blockchain-explorer
mkdir -p /opt/blockchain-explorer/assets

# Copy files
print_status "Copying explorer files..."
cp -r /opt/blockchain-node-src/apps/blockchain-explorer/* /opt/blockchain-explorer/

# Update nginx configuration
print_status "Updating nginx configuration..."
cp /opt/blockchain-explorer/nginx.conf /etc/nginx/sites-available/blockchain-explorer
ln -sf /etc/nginx/sites-available/blockchain-explorer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and start nginx
print_status "Starting nginx..."
nginx -t
systemctl start nginx

print_success "✅ Modern explorer deployed!"
echo ""
echo "Access URLs:"
echo "  - Explorer: http://localhost:3000/"
echo "  - API: http://localhost:3000/api/v1/"
echo ""
echo "Standardized API Endpoints:"
echo "  - GET /api/v1/chain/head"
echo "  - GET /api/v1/chain/blocks?limit=N"
echo "  - GET /api/v1/chain/blocks/{height}"
