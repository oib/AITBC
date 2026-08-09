#!/bin/bash

# Deploy the block explorer to the server
#
# V23-22: this shared deploy-to-server.sh's root@127.0.0.1 default. It also built from a
# hardcoded /home/oib/windsurf/aitbc path, which exists on exactly one machine, so on any
# other the `cd` failed and `set -e` stopped the deploy -- the least bad outcome available,
# but not one to rely on.

set -euo pipefail

# No default. A deploy target is a decision, not a fallback.
SERVER="${AITBC_DEPLOY_SERVER:?set AITBC_DEPLOY_SERVER (e.g. root@10.1.223.93) — there is no default target}"
EXPLORER_DIR="${AITBC_EXPLORER_DIR:-/root/aitbc/apps/explorer-web}"
NGINX_CONFIG="/etc/nginx/sites-available/aitbc"

# Build from the checkout this script belongs to.
REPO_ROOT="${AITBC_DEPLOY_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
EXPLORER_SRC="$REPO_ROOT/apps/explorer-web"

echo "🚀 Deploying the block explorer to Server"
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
if [ ! -d "$EXPLORER_SRC" ]; then
    echo "❌ Explorer source not found at $EXPLORER_SRC" >&2
    echo "   Set AITBC_DEPLOY_SOURCE to the repository root if this script was moved." >&2
    exit 1
fi
cd "$EXPLORER_SRC"
npm run build

# Copy built files to server
print_status "Copying explorer build to server..."
scp -r dist "$SERVER:$EXPLORER_DIR/"

# Update nginx config to include explorer
print_status "Updating nginx configuration..."

# Backup current config
ssh "$SERVER" "cp $NGINX_CONFIG ${NGINX_CONFIG}.backup"

# Add explorer location to nginx config
ssh "$SERVER" "sed -i '/# Health endpoint/i\\
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
ssh "$SERVER" "nginx -t && systemctl reload nginx"

print_status "✅ Explorer deployment complete!"
echo ""
echo "📋 Explorer URL:"
echo "  🌐 Explorer: https://aitbc.bubuit.net/explorer/"
echo ""
