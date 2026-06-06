#!/bin/bash

# Deploy nginx reverse proxy for AITBC services
# This replaces firehol/iptables port forwarding with nginx reverse proxy

set -e

echo "🚀 Deploying Nginx Reverse Proxy for AITBC"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're on the host server
if ! grep -q "ns3-root" ~/.ssh/config 2>/dev/null; then
    print_error "ns3-root SSH configuration not found. Please add it to ~/.ssh/config"
    exit 1
fi

# Install nginx on host if not already installed
print_status "Checking nginx installation on host..."
ssh ns3-root "which nginx > /dev/null || (apt-get update && apt-get install -y nginx)"

# Install certbot for SSL certificates
print_status "Checking certbot installation..."
ssh ns3-root "which certbot > /dev/null || (apt-get update && apt-get install -y certbot python3-certbot-nginx)"

# Copy nginx configuration
print_status "Copying nginx configuration..."
scp infra/nginx/nginx-aitbc-reverse-proxy.conf ns3-root:/tmp/aitbc-reverse-proxy.conf

# Backup existing nginx configuration
print_status "Backing up existing nginx configuration..."
ssh ns3-root "mkdir -p /etc/nginx/backup && cp -r /etc/nginx/sites-available/* /etc/nginx/backup/ 2>/dev/null || true"

# Install the new configuration
print_status "Installing nginx reverse proxy configuration..."
ssh ns3-root << 'EOF'
# Remove existing configurations
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-available/aitbc*

# Copy new configuration
cp /tmp/aitbc-reverse-proxy.conf /etc/nginx/sites-available/aitbc-reverse-proxy.conf

# Create symbolic link
ln -sf /etc/nginx/sites-available/aitbc-reverse-proxy.conf /etc/nginx/sites-enabled/

# Test nginx configuration
nginx -t
EOF

# Check if SSL certificate exists
print_status "Checking SSL certificate..."
if ! ssh ns3-root "test -f /etc/letsencrypt/live/aitbc.keisanki.net/fullchain.pem"; then
    print_warning "SSL certificate not found. Obtaining Let's Encrypt certificate..."
    
    # Obtain SSL certificate
    ssh ns3-root << 'EOF'
# Stop nginx temporarily
systemctl stop nginx 2>/dev/null || true

# Obtain certificate
certbot certonly --standalone -d aitbc.keisanki.net -d api.aitbc.keisanki.net -d rpc.aitbc.keisanki.net --email admin@keisanki.net --agree-tos --non-interactive

# Start nginx
systemctl start nginx
EOF
    
    if [ $? -ne 0 ]; then
        print_error "Failed to obtain SSL certificate. Please run certbot manually:"
        echo "certbot certonly --standalone -d aitbc.keisanki.net -d api.aitbc.keisanki.net -d rpc.aitbc.keisanki.net"
        exit 1
    fi
fi

# Restart nginx
print_status "Restarting nginx..."
ssh ns3-root "systemctl restart nginx && systemctl enable nginx"

# Remove old iptables rules (optional)
print_warning "Removing old iptables port forwarding rules (if they exist)..."
ssh ns3-root << 'EOF'
# Flush existing NAT rules for AITBC ports
iptables -t nat -D PREROUTING -p tcp --dport 8000 -j DNAT --to-destination 192.168.100.10:8000 2>/dev/null || true
iptables -t nat -D POSTROUTING -p tcp -d 192.168.100.10 --dport 8000 -j MASQUERADE 2>/dev/null || true
iptables -t nat -D PREROUTING -p tcp --dport 8081 -j DNAT --to-destination 192.168.100.10:8081 2>/dev/null || true
iptables -t nat -D POSTROUTING -p tcp -d 192.168.100.10 --dport 8081 -j MASQUERADE 2>/dev/null || true
iptables -t nat -D PREROUTING -p tcp --dport 8082 -j DNAT --to-destination 192.168.100.10:8082 2>/dev/null || true
iptables -t nat -D POSTROUTING -p tcp -d 192.168.100.10 --dport 8082 -j MASQUERADE 2>/dev/null || true
iptables -t nat -D PREROUTING -p tcp --dport 9080 -j DNAT --to-destination 192.168.100.10:9080 2>/dev/null || true
iptables -t nat -D POSTROUTING -p tcp -d 192.168.100.10 --dport 9080 -j MASQUERADE 2>/dev/null || true
iptables -t nat -D PREROUTING -p tcp --dport 3000 -j DNAT --to-destination 192.168.100.10:3000 2>/dev/null || true
iptables -t nat -D POSTROUTING -p tcp -d 192.168.100.10 --dport 3000 -j MASQUERADE 2>/dev/null || true

# Save iptables rules
iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
EOF

# Wait for nginx to start
sleep 2

# Test the configuration
print_status "Testing reverse proxy configuration..."
echo ""

# Test main domain
if curl -s -o /dev/null -w "%{http_code}" https://aitbc.keisanki.net/health | grep -q "200"; then
    print_status "✅ Main domain (aitbc.keisanki.net) - OK"
else
    print_error "❌ Main domain (aitbc.keisanki.net) - FAILED"
fi

# Test API endpoint
if curl -s -o /dev/null -w "%{http_code}" https://aitbc.keisanki.net/api/health | grep -q "200"; then
    print_status "✅ API endpoint - OK"
else
    print_warning "⚠️  API endpoint - Not responding (service may not be running)"
fi

# Test RPC endpoint
if curl -s -o /dev/null -w "%{http_code}" https://aitbc.keisanki.net/rpc/head | grep -q "200"; then
    print_status "✅ RPC endpoint - OK"
else
    print_warning "⚠️  RPC endpoint - Not responding (blockchain node may not be running)"
fi

echo ""
print_status "🎉 Nginx reverse proxy deployment complete!"
echo ""
echo "Service URLs:"
echo "  • Blockchain Explorer: https://aitbc.keisanki.net"
echo "  • API: https://aitbc.keisanki.net/api/"
echo "  • RPC: https://aitbc.keisanki.net/rpc/"
echo "  • Exchange: https://aitbc.keisanki.net/exchange/"
echo ""
echo "Alternative URLs:"
echo "  • API-only: https://api.aitbc.keisanki.net"
echo "  • RPC-only: https://rpc.aitbc.keisanki.net"
echo ""
echo "Note: Make sure all services are running in the container:"
echo "  • blockchain-explorer.service (port 3000)"
echo "  • coordinator-api.service (port 8000)"
echo "  • blockchain-rpc.service (port 8082)"
echo "  • aitbc-exchange.service (port 9080)"
