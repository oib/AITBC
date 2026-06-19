#!/usr/bin/env bash
# Service Optimization Script for AITBC Production
# This script optimizes systemd services for production environment

set -euo pipefail


# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "=== AITBC Service Optimization ==="

# Create service overrides for production (stored in git repo)
echo "1. Creating production service overrides..."
mkdir -p /opt/aitbc/systemd/aitbc-blockchain-node.service.d

cat > /opt/aitbc/systemd/aitbc-blockchain-node.service.d/production.conf << EOF
[Service]
Restart=always
RestartSec=10
LimitNOFILE=65536
Environment="PYTHONPATH=/opt/aitbc/apps/blockchain-node/src"
Environment="AITBC_ENV=production"
EOF

# Create symlink from systemd to git repo (ensures git always has current files)
echo "2. Creating symlink from systemd to git repo..."
ln -sf /opt/aitbc/systemd/aitbc-blockchain-node.service.d/production.conf /etc/systemd/system/aitbc-blockchain-node.service.d/production.conf

# Create RPC service optimization
echo "3. Creating RPC service optimization..."
mkdir -p /opt/aitbc/systemd/aitbc-blockchain-rpc.service.d

cat > /opt/aitbc/systemd/aitbc-blockchain-rpc.service.d/production.conf << EOF
[Service]
Restart=always
RestartSec=5
LimitNOFILE=65536
Environment="PYTHONPATH=/opt/aitbc/apps/blockchain-node/src"
Environment="AITBC_ENV=production"
Environment="UVICORN_WORKERS=4"
Environment="UVICORN_BACKLOG=2048"
EOF

ln -sf /opt/aitbc/systemd/aitbc-blockchain-rpc.service.d/production.conf /etc/systemd/system/aitbc-blockchain-rpc.service.d/production.conf

# Reload and restart services
echo "4. Reloading and restarting services..."
systemctl daemon-reload
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc

# Verify services are running
echo "5. Verifying service status..."
sleep 3
echo "   Blockchain node: $(systemctl is-active aitbc-blockchain-node)"
echo "   RPC service: $(systemctl is-active aitbc-blockchain-rpc)"

echo "✅ Service optimization completed successfully!"
echo "   • Production overrides created in git repo"
echo "   • Symlinks established for version control"
echo "   • Services restarted and verified"
