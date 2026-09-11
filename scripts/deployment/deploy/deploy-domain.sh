#!/bin/bash

# Deploy AITBC services to domain https://aitbc.bubuit.net
# Uses systemd services and nginx reverse proxy

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
sudo systemctl stop aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet 2>/dev/null || true
sudo systemctl stop aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p 2>/dev/null || true

# Deploy to container
print_status "Deploying to container..."
python /opt/aitbc/scripts/deployment/deploy/container-deploy.py

# Copy nginx config to container
print_status "Configuring nginx for domain..."
incus file push /opt/aitbc/nginx-aitbc.conf $CONTAINER/etc/nginx/sites-available/aitbc 2>/dev/null || {
    print_warning "nginx-aitbc.conf not found — using inline config"
    incus exec $CONTAINER -- tee /etc/nginx/sites-available/aitbc > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /api/ {
        proxy_pass http://127.0.0.1:8203/v1/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /rpc/ {
        proxy_pass http://127.0.0.1:8202/rpc/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /exchange/ {
        proxy_pass http://127.0.0.1:8106/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /marketplace/ {
        proxy_pass http://127.0.0.1:8102/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    # No default root. Nothing is served at /; a redirect here into a proxied
    # backend publishes that entire upstream service, which is how /marketplace/
    # previously exposed the Agent Coordinator.
}
EOF
}

# Enable site
incus exec $CONTAINER -- ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/
incus exec $CONTAINER -- rm -f /etc/nginx/sites-enabled/default

# Test nginx config
incus exec $CONTAINER -- nginx -t

# Reload nginx
incus exec $CONTAINER -- systemctl reload nginx

# Restart services
print_status "Restarting services..."
incus exec $CONTAINER -- systemctl restart aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p
incus exec $CONTAINER -- systemctl restart aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet

echo ""
print_status "✅ Deployment complete!"
echo ""
echo "📋 Service URLs:"
echo "  🌐 Domain: https://$DOMAIN"
echo "  💱 Exchange:        https://$DOMAIN/exchange/"
echo "  📊 Marketplace:     https://$DOMAIN/marketplace/"
echo "  🔗 API:             https://$DOMAIN/api/"
echo "  ⛓️  Blockchain RPC:  https://$DOMAIN/rpc/"
echo ""
echo "📝 Next Steps:"
echo "1. Point the TLS terminator at this container and forward 80/443 to it."
echo "   TLS is not terminated here -- this container serves cleartext and holds"
echo "   no certificate. See docs/deployment/NETWORK_POLICY.md."
echo "2. Test services at the URLs above"
