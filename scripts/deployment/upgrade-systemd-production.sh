#!/bin/bash

# ============================================================================
# Upgrade Existing SystemD Services to Production-Grade
# ============================================================================

set -euo pipefail


# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
NODE_ID="${AITBC_NODE_ID:-aitbc}"
NODE1_ID="${AITBC_NODE1_ID:-aitbc1}"

echo -e "${BLUE}🔧 UPGRADING EXISTING SYSTEMD SERVICES${NC}"
echo "=================================="
echo "Upgrading existing services to production-grade"
echo ""

# Step 1: Upgrade blockchain service
echo -e "${CYAN}⛓️  Step 1: Upgrade Blockchain Service${NC}"
echo "=================================="

# Backup original service
cp /opt/aitbc/systemd/aitbc-blockchain-node.service /opt/aitbc/systemd/aitbc-blockchain-node.service.backup

# Create production-grade blockchain service
cat > /opt/aitbc/systemd/aitbc-blockchain-node.service << EOF
[Unit]
Description=AITBC Production Blockchain Node
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=${NODE_ID}
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# Production execution
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/production/services/blockchain_simple.py
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=10

# Production reliability
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Production logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-blockchain-production

# Production security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data/blockchain /opt/aitbc/production/logs/blockchain

# Production performance
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=2G
CPUQuota=50%

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Blockchain service upgraded to production-grade"

# Step 2: Upgrade marketplace service
echo -e "${CYAN}🏪 Step 2: Upgrade Marketplace Service${NC}"
echo "===================================="

# Backup original service
cp /opt/aitbc/systemd/aitbc-marketplace.service /opt/aitbc/systemd/aitbc-marketplace.service.backup

# Create production-grade marketplace service
cat > /opt/aitbc/systemd/aitbc-marketplace.service << EOF
[Unit]
Description=AITBC Production Marketplace Service
After=network.target aitbc-blockchain-node.service postgresql.service redis.service
Wants=aitbc-blockchain-node.service postgresql.service redis.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=${NODE_ID}
Environment=MARKETPLACE_PORT=8102
Environment=WORKERS=4
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# Production execution
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/production/services/marketplace.py
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=10

# Production reliability
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Production logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-marketplace-production

# Production security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data/marketplace /opt/aitbc/production/logs/marketplace

# Production performance
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=1G
CPUQuota=25%

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Marketplace service upgraded to production-grade"

# Step 3: GPU service unified into marketplace service
echo -e "${CYAN}🖥️  Step 3: GPU Service${NC}"
echo "=============================="
echo "ℹ️  GPU service (port 8101) functionality unified into the AITBC marketplace service (port 8102)"
echo "✅ GPU service handling included in marketplace service upgrade"

# Step 4: Create production monitoring service
echo -e "${CYAN}📊 Step 4: Create Production Monitoring${NC}"
echo "======================================"

cat > /opt/aitbc/systemd/aitbc-production-monitor.service << EOF
[Unit]
Description=AITBC Production Monitoring Service
After=network.target aitbc-blockchain-node.service aitbc-marketplace.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=${NODE_ID}
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# Production monitoring
ExecStart=/opt/aitbc/venv/bin/python -c "
import time
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('production-monitor')

while True:
    try:
        # Monitor blockchain
        blockchain_file = Path('/opt/aitbc/production/data/blockchain/aitbc/blockchain.json')
        if blockchain_file.exists():
            with open(blockchain_file, 'r') as f:
                data = json.load(f)
                logger.info(f'Blockchain: {len(data.get(\"blocks\", []))} blocks')

        # Monitor marketplace
        marketplace_dir = Path('/opt/aitbc/production/data/marketplace')
        if marketplace_dir.exists():
            listings_file = marketplace_dir / 'gpu_listings.json'
            if listings_file.exists():
                with open(listings_file, 'r') as f:
                    listings = json.load(f)
                    logger.info(f'Marketplace: {len(listings)} GPU listings')

        # Monitor system resources
        import psutil
        cpu_percent = psutil.cpu_percent()
        memory_percent = psutil.virtual_memory().percent
        logger.info(f'System: CPU {cpu_percent}%, Memory {memory_percent}%')

        time.sleep(30)  # Monitor every 30 seconds

    except Exception as e:
        logger.error(f'Monitoring error: {e}')
        time.sleep(60)
"

# Production reliability
Restart=always
RestartSec=10

# Production logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-production-monitor

# Production security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data /opt/aitbc/production/logs

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Production monitoring service created"

# Step 5: Reload systemd and enable services
echo -e "${CYAN}🔄 Step 5: Reload SystemD and Enable${NC}"
echo "=================================="

# Reload systemd daemon
systemctl daemon-reload

# Enable production services
echo "Enabling production services..."
systemctl enable aitbc-blockchain-node.service
systemctl enable aitbc-marketplace.service
systemctl enable aitbc-production-monitor.service

echo "✅ SystemD services reloaded and enabled"

# Step 6: Test production services on localhost
echo -e "${CYAN}🧪 Step 6: Test Production Services${NC}"
echo "==============================="

echo "Starting production services..."
systemctl start aitbc-blockchain-node.service
sleep 2
systemctl start aitbc-marketplace.service
sleep 2
systemctl start aitbc-production-monitor.service

# Check service status
echo "Checking service status..."
systemctl status aitbc-blockchain-node.service --no-pager -l | head -10
systemctl status aitbc-marketplace.service --no-pager -l | head -10

# Test service endpoints
echo "Testing service endpoints..."
sleep 5
# Was 8002 until V23-99. 8002 is aitbc-monitoring; it answers /health 200, so this
# reported the marketplace ready whenever monitoring was up. Marketplace is 8102.
curl -fsS http://localhost:8102/health | head -5 || echo "Marketplace service not ready"
# GPU service
curl -s http://localhost:8101/health | head -5 || echo "GPU service endpoint not ready"

# Step 7: Deploy to ${NODE1_HOST}
echo -e "${CYAN}🚀 Step 7: Deploy to ${NODE1_HOST}${NC}"
echo "========================"

# Copy production services to ${NODE1_HOST}
echo "Copying production services to ${NODE1_ID}..."
scp -r /opt/aitbc/production ${NODE1_HOST}:/opt/aitbc/
scp /opt/aitbc/systemd/aitbc-blockchain-node.service ${NODE1_HOST}:/opt/aitbc/systemd/
scp /opt/aitbc/systemd/aitbc-marketplace.service ${NODE1_HOST}:/opt/aitbc/systemd/
scp /opt/aitbc/systemd/aitbc-production-monitor.service ${NODE1_HOST}:/opt/aitbc/systemd/

# Update services for ${NODE1_HOST} node
echo "Configuring services for ${NODE1_ID}..."
ssh ${NODE1_HOST} "sed -i 's/^NODE_ID=.*/NODE_ID=${NODE1_ID}/' /opt/aitbc/systemd/aitbc-blockchain-node.service"
ssh ${NODE1_HOST} "sed -i 's/^NODE_ID=.*/NODE_ID=${NODE1_ID}/' /opt/aitbc/systemd/aitbc-marketplace.service"
ssh ${NODE1_HOST} "sed -i 's/^NODE_ID=.*/NODE_ID=${NODE1_ID}/' /opt/aitbc/systemd/aitbc-production-monitor.service"


# Deploy and start services on ${NODE1_HOST}
echo "Starting services on ${NODE1_ID}..."
ssh ${NODE1_HOST} "systemctl daemon-reload"
ssh ${NODE1_HOST} "systemctl enable aitbc-blockchain-node.service aitbc-marketplace.service aitbc-production-monitor.service"
ssh ${NODE1_HOST} "systemctl start aitbc-blockchain-node.service"
sleep 3
ssh ${NODE1_HOST} "systemctl start aitbc-marketplace.service"
sleep 3
ssh ${NODE1_HOST} "systemctl start aitbc-production-monitor.service"

# Check ${NODE1_HOST} services
echo "Checking ${NODE1_HOST} services..."
ssh ${NODE1_HOST} "systemctl status aitbc-blockchain-node.service --no-pager -l | head -5"
ssh ${NODE1_HOST} "systemctl status aitbc-marketplace.service --no-pager -l | head -5"

# Test ${NODE1_HOST} endpoints
echo "Testing ${NODE1_HOST} endpoints..."
ssh ${NODE1_HOST} "curl -s http://localhost:8102/health | head -5" || echo "${NODE1_HOST} marketplace not ready"
# GPU service
ssh ${NODE1_HOST} "curl -s http://localhost:8101/health | head -5" || echo "${NODE1_HOST} GPU service endpoint not ready"

echo ""
echo -e "${GREEN}🎉 PRODUCTION SYSTEMD SERVICES UPGRADED!${NC}"
echo "======================================"
echo ""
echo "✅ Upgraded Services:"
echo "   • aitbc-blockchain-node.service (Production blockchain)"
echo "   • aitbc-marketplace.service (Production marketplace with GPU support)"
echo "   • aitbc-production-monitor.service (Production monitoring)"
echo ""
echo "✅ Production Features:"
echo "   • Real database persistence"
echo "   • Production logging and monitoring"
echo "   • Resource limits and security"
echo "   • Automatic restart and recovery"
echo "   • Multi-node deployment"
echo "   • GPU marketplace unified into marketplace service"
echo ""
echo "✅ Service Endpoints:"
echo "   • aitbc (localhost):"
echo "     - Blockchain: SystemD managed"
echo "     - Marketplace: http://localhost:8102"
echo "   • ${NODE1_HOST} (remote):"
echo "     - Blockchain: SystemD managed"
echo "     - Marketplace: http://${NODE1_HOST}:8102"
echo ""
echo "✅ Monitoring:"
echo "   • SystemD journal: journalctl -u aitbc-*"
echo "   • Production logs: /opt/aitbc/production/logs/"
echo "   • Service status: systemctl status aitbc-*"
echo ""
echo -e "${BLUE}🚀 Production SystemD services ready!${NC}"
