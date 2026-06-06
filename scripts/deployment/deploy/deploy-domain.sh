#!/bin/bash

# Deploy AITBC services to domain https://aitbc.bubuit.net

set -e

DOMAIN="aitbc.bubuit.net"
CONTAINER="aitbc"

echo "🚀 Deploying AITBC services to https://$DOMAIN"
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

# Stop local services
print_status "Stopping local services..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sudo fuser -k 9080/tcp 2>/dev/null || true
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true

# Deploy to container
print_status "Deploying to container..."
python /home/oib/windsurf/aitbc/container-deploy.py

# Copy nginx config to container
print_status "Configuring nginx for domain..."
incus file push /home/oib/windsurf/aitbc/nginx-aitbc.conf $CONTAINER/etc/nginx/sites-available/aitbc

# Enable site
incus exec $CONTAINER -- ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/
incus exec $CONTAINER -- rm -f /etc/nginx/sites-enabled/default

# Test nginx config
incus exec $CONTAINER -- nginx -t

# Reload nginx
incus exec $CONTAINER -- systemctl reload nginx

# Install SSL certificate (Let's Encrypt)
print_warning "SSL Certificate Setup:"
echo "1. Ensure port 80/443 are forwarded to container IP (10.1.223.93)"
echo "2. Run certbot in container:"
echo "   incus exec $CONTAINER -- certbot --nginx -d $DOMAIN"
echo ""

# Update UIs to use correct API endpoints
print_status "Updating API endpoints..."

# Update marketplace API base URL
incus exec $CONTAINER -- sed -i "s|http://127.0.0.1:8000|https://$DOMAIN/api|g" /home/oib/aitbc/apps/marketplace-ui/index.html

# Update exchange API endpoints
incus exec $CONTAINER -- sed -i "s|http://127.0.0.1:8000|https://$DOMAIN/api|g" /home/oib/aitbc/apps/trade-exchange/index.html
incus exec $CONTAINER -- sed -i "s|http://127.0.0.1:9080|https://$DOMAIN/rpc|g" /home/oib/aitbc/apps/trade-exchange/index.html

# Restart services to apply changes
print_status "Restarting services..."
incus exec $CONTAINER -- pkill -f "server.py"
sleep 2
incus exec $CONTAINER -- /home/oib/start_aitbc.sh

echo ""
print_status "✅ Deployment complete!"
echo ""
echo "📋 Service URLs:"
echo "  🌐 Domain: https://$DOMAIN"
echo "  📊 Marketplace: https://$DOMAIN/Marketplace"
echo "  💱 Trade Exchange: https://$DOMAIN/Exchange"
echo "  🔗 API: https://$DOMAIN/api"
echo "  ⛓️  Blockchain RPC: https://$DOMAIN/rpc"
echo ""
echo "📝 Next Steps:"
echo "1. Forward ports 80/443 to container IP (10.1.223.93)"
echo "2. Install SSL certificate:"
echo "   incus exec $CONTAINER -- certbot --nginx -d $DOMAIN"
echo "3. Test services at the URLs above"
