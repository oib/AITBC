#!/bin/bash

# Deploy nginx reverse proxy for AITBC services
# This replaces firehol/iptables port forwarding with nginx reverse proxy

set -e

# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."


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

# Install nginx on host if not already installed
print_status "Checking nginx installation on host..."
ssh "$AITBC_SSH_TARGET" "which nginx > /dev/null || (apt-get update && apt-get install -y nginx)"

# Copy nginx configuration
print_status "Copying nginx configuration..."
scp infra/nginx/nginx-aitbc-reverse-proxy.conf ${AITBC_SSH_TARGET}:/tmp/aitbc-reverse-proxy.conf

# Backup existing nginx configuration
print_status "Backing up existing nginx configuration..."
ssh "$AITBC_SSH_TARGET" "mkdir -p /etc/nginx/backup && cp -r /etc/nginx/sites-available/* /etc/nginx/backup/ 2>/dev/null || true"

# Install the new configuration
print_status "Installing nginx reverse proxy configuration..."
ssh "$AITBC_SSH_TARGET" << 'EOF'
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

# TLS
#
# This script no longer obtains or installs a certificate. AITBC runs no ACME
# client: certificates belong to whoever operates the TLS terminator, which is
# outside this repository. See docs/deployment/NETWORK_POLICY.md and
# docs/deployment/ssl-tls-setup.md.
#
# If the vhost just installed references a certificate path, that certificate
# must already be present -- `nginx -t` above is what will tell you.

# Restart nginx
print_status "Restarting nginx..."
ssh "$AITBC_SSH_TARGET" "systemctl restart nginx && systemctl enable nginx"

# Remove old iptables rules (optional)
print_warning "Removing old iptables port forwarding rules (if they exist)..."
# These rules can only be deleted if we know what they pointed at, so this step
# needs AITBC_DNAT_TARGET. Without it there is nothing to match and the step is
# skipped rather than silently doing nothing. The heredoc is quoted, so the
# value reaches the remote shell through its environment.
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    ssh "$AITBC_SSH_TARGET" "AITBC_DNAT_TARGET='${AITBC_DNAT_TARGET}' bash -s" << 'EOF'
for port in 8000 8081 8202 9080 3000; do
    iptables -t nat -D PREROUTING -p tcp --dport "$port" -j DNAT \
        --to-destination "$AITBC_DNAT_TARGET:$port" 2>/dev/null || true
    iptables -t nat -D POSTROUTING -p tcp -d "$AITBC_DNAT_TARGET" --dport "$port" \
        -j MASQUERADE 2>/dev/null || true
done

iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
EOF
else
    echo "NOTE: AITBC_DNAT_TARGET is not set -- skipping removal of legacy DNAT" >&2
    echo "      rules, since there is no target to match them against." >&2
fi

# Wait for nginx to start
sleep 2

# Test the configuration
print_status "Testing reverse proxy configuration..."
echo ""

# Test main domain
if curl -s -o /dev/null -w "%{http_code}" https://${AITBC_PUBLIC_HOST}/health | grep -q "200"; then
    print_status "✅ Main domain (${AITBC_PUBLIC_HOST}) - OK"
else
    print_error "❌ Main domain (${AITBC_PUBLIC_HOST}) - FAILED"
fi

# Test API endpoint
if curl -s -o /dev/null -w "%{http_code}" https://${AITBC_PUBLIC_HOST}/api/health | grep -q "200"; then
    print_status "✅ API endpoint - OK"
else
    print_warning "⚠️  API endpoint - Not responding (service may not be running)"
fi

# Test RPC endpoint
if curl -s -o /dev/null -w "%{http_code}" https://${AITBC_PUBLIC_HOST}/rpc/head | grep -q "200"; then
    print_status "✅ RPC endpoint - OK"
else
    print_warning "⚠️  RPC endpoint - Not responding (blockchain node may not be running)"
fi

echo ""
print_status "🎉 Nginx reverse proxy deployment complete!"
echo ""
echo "Service URLs:"
echo "  • Blockchain Explorer: https://${AITBC_PUBLIC_HOST}"
echo "  • API: https://${AITBC_PUBLIC_HOST}/api/"
echo "  • RPC: https://${AITBC_PUBLIC_HOST}/rpc/"
echo "  • Exchange: https://${AITBC_PUBLIC_HOST}/exchange/"
echo ""
echo "Alternative URLs:"
echo "  • API-only: https://api.${AITBC_PUBLIC_HOST}"
echo "  • RPC-only: https://rpc.${AITBC_PUBLIC_HOST}"
echo ""
echo "Note: Make sure all services are running in the container:"
echo "  • blockchain-explorer.service (port 3000)"
echo "  • coordinator-api.service (port 8203)"
echo "  • blockchain-rpc.service (port 8202)"
echo "  • aitbc-exchange.service (port 9080)"
