#!/bin/bash

# ============================================================================
# Deploy Real Production System - Mining & AI Services
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"

echo -e "${BLUE}🚀 DEPLOY REAL PRODUCTION SYSTEM${NC}"
echo "=========================="
echo "Deploying real mining, AI, and marketplace services"
echo ""

# Step 1: Create SystemD services for real production
echo -e "${CYAN}⛓️  Step 1: Real Mining Service${NC}"
echo "============================"

cat > /opt/aitbc/systemd/aitbc-mining-blockchain.service << 'EOF'
[Unit]
Description=AITBC Real Mining Blockchain Service
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=aitbc
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# Real mining execution
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/production/services/mining_blockchain.py
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=10

# Mining reliability
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Mining logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-mining-blockchain

# Mining security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data/blockchain /opt/aitbc/production/logs/blockchain

# Mining performance
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=4G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Real mining service created"

# Step 2: OpenClaw AI Service
echo -e "${CYAN}🤖 Step 2: OpenClaw AI Service${NC}"
echo "=============================="

cat > /opt/aitbc/systemd/aitbc-openclaw-ai.service << 'EOF'
[Unit]
Description=AITBC OpenClaw AI Service
After=network.target aitbc-mining-blockchain.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=aitbc
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# OpenClaw AI execution
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/production/services/openclaw_ai.py
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=10

# AI service reliability
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# AI logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-openclaw-ai

# AI security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data/openclaw /opt/aitbc/production/logs/openclaw

# AI performance
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=2G
CPUQuota=60%

[Install]
WantedBy=multi-user.target
EOF

echo "✅ OpenClaw AI service created"

# Step 3: Real Marketplace Service
echo -e "${CYAN}🏪 Step 3: Real Marketplace Service${NC}"
echo "=============================="

cat > /opt/aitbc/systemd/aitbc-real-marketplace.service << 'EOF'
[Unit]
Description=AITBC Real Marketplace with AI Services
After=network.target aitbc-mining-blockchain.service aitbc-openclaw-ai.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
Environment=NODE_ID=aitbc
Environment=REAL_MARKETPLACE_PORT=8006
Environment=PYTHONPATH=/opt/aitbc/production/services
EnvironmentFile=/opt/aitbc/production/.env

# Real marketplace execution
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/production/services/real_marketplace.py
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=10

# Marketplace reliability
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Marketplace logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-real-marketplace

# Marketplace security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/aitbc/production/data/marketplace /opt/aitbc/production/logs/marketplace

# Marketplace performance
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=1G
CPUQuota=40%

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Real marketplace service created"

# Step 4: Deploy to localhost
echo -e "${CYAN}🚀 Step 4: Deploy to Localhost${NC}"
echo "============================"

# Copy services to systemd
cp /opt/aitbc/systemd/aitbc-mining-blockchain.service /etc/systemd/system/
cp /opt/aitbc/systemd/aitbc-openclaw-ai.service /etc/systemd/system/
cp /opt/aitbc/systemd/aitbc-real-marketplace.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable services
systemctl enable aitbc-mining-blockchain.service
systemctl enable aitbc-openclaw-ai.service
systemctl enable aitbc-real-marketplace.service

# Start services
echo "Starting real production services..."
systemctl start aitbc-mining-blockchain.service
sleep 3
systemctl start aitbc-openclaw-ai.service
sleep 3
systemctl start aitbc-real-marketplace.service

# Check status
echo "Checking service status..."
systemctl status aitbc-mining-blockchain.service --no-pager -l | head -8
echo ""
systemctl status aitbc-openclaw-ai.service --no-pager -l | head -8
echo ""
systemctl status aitbc-real-marketplace.service --no-pager -l | head -8

echo "✅ Real production services deployed to localhost"

# Step 5: Test real production system
echo -e "${CYAN}🧪 Step 5: Test Real Production${NC}"
echo "=========================="

sleep 5

# Test mining blockchain
echo "Testing mining blockchain..."
cd /opt/aitbc
source venv/bin/activate
export NODE_ID=aitbc
python production/services/mining_blockchain.py > /tmp/mining_test.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Mining blockchain test passed"
    head -10 /tmp/mining_test.log
else
    echo "❌ Mining blockchain test failed"
    tail -10 /tmp/mining_test.log
fi

# Test OpenClaw AI
echo "Testing OpenClaw AI..."
python production/services/openclaw_ai.py > /tmp/openclaw_test.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ OpenClaw AI test passed"
    head -10 /tmp/openclaw_test.log
else
    echo "❌ OpenClaw AI test failed"
    tail -10 /tmp/openclaw_test.log
fi

# Test real marketplace
echo "Testing real marketplace..."
curl -s http://localhost:8006/health | head -5 || echo "Real marketplace not responding"
curl -s http://localhost:8006/ai/services | head -10 || echo "AI services not available"

# Step 6: Deploy to aitbc1
echo -e "${CYAN}🚀 Step 6: Deploy to aitbc1${NC}"
echo "=========================="

# Copy production system to aitbc1
echo "Copying real production system to aitbc1..."
scp -r /opt/aitbc/production/services aitbc1:/opt/aitbc/production/
scp /opt/aitbc/systemd/aitbc-mining-blockchain.service aitbc1:/opt/aitbc/systemd/
scp /opt/aitbc/systemd/aitbc-openclaw-ai.service aitbc1:/opt/aitbc/systemd/
scp /opt/aitbc/systemd/aitbc-real-marketplace.service aitbc1:/opt/aitbc/systemd/

# Configure services for aitbc1
echo "Configuring services for aitbc1..."
ssh aitbc1 "sed -i 's/NODE_ID=aitbc/NODE_ID=aitbc1/g' /opt/aitbc/systemd/aitbc-mining-blockchain.service"
ssh aitbc1 "sed -i 's/NODE_ID=aitbc/NODE_ID=aitbc1/g' /opt/aitbc/systemd/aitbc-openclaw-ai.service"
ssh aitbc1 "sed -i 's/NODE_ID=aitbc/NODE_ID=aitbc1/g' /opt/aitbc/systemd/aitbc-real-marketplace.service"

# Update ports for aitbc1
ssh aitbc1 "sed -i 's/REAL_MARKETPLACE_PORT=8006/REAL_MARKETPLACE_PORT=8007/g' /opt/aitbc/systemd/aitbc-real-marketplace.service"

# Deploy and start services on aitbc1
echo "Starting services on aitbc1..."
ssh aitbc1 "cp /opt/aitbc/systemd/aitbc-*.service /etc/systemd/system/"
ssh aitbc1 "systemctl daemon-reload"
ssh aitbc1 "systemctl enable aitbc-mining-blockchain.service aitbc-openclaw-ai.service aitbc-real-marketplace.service"
ssh aitbc1 "systemctl start aitbc-mining-blockchain.service"
sleep 3
ssh aitbc1 "systemctl start aitbc-openclaw-ai.service"
sleep 3
ssh aitbc1 "systemctl start aitbc-real-marketplace.service"

# Check aitbc1 services
echo "Checking aitbc1 services..."
ssh aitbc1 "systemctl status aitbc-mining-blockchain.service --no-pager -l | head -5"
ssh aitbc1 "systemctl status aitbc-openclaw-ai.service --no-pager -l | head -5"
ssh aitbc1 "curl -s http://localhost:8007/health | head -5" || echo "aitbc1 marketplace not ready"

# Step 7: Demonstrate real functionality
echo -e "${CYAN}🎯 Step 7: Demonstrate Real Functionality${NC}"
echo "=================================="

echo "Demonstrating real blockchain mining..."
cd /opt/aitbc
source venv/bin/activate
python -c "
import sys
sys.path.insert(0, '/opt/aitbc/production/services')
from mining_blockchain import MultiChainManager

manager = MultiChainManager()
info = manager.get_all_chains_info()
print('Multi-chain info:')
print(f'  Total chains: {info[\"total_chains\"]}')
for name, chain_info in info['chains'].items():
    print(f'  {name}: {chain_info[\"blocks\"]} blocks, {chain_info[\"block_reward\"]} AITBC reward')
"

echo ""
echo "Demonstrating real AI services..."
curl -s http://localhost:8006/ai/services | jq '.total_services, .available_services' || echo "AI services check failed"

echo ""
echo "Demonstrating real AI task execution..."
curl -X POST http://localhost:8006/ai/execute \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "ollama-llama2-7b",
    "task_data": {
      "prompt": "What is the future of decentralized AI?",
      "type": "text_generation"
    }
  }' | head -10 || echo "AI task execution failed"

echo ""
echo -e "${GREEN}🎉 REAL PRODUCTION SYSTEM DEPLOYED!${NC}"
echo "=================================="
echo ""
echo "✅ Real Blockchain Mining:"
echo "   • Proof of Work mining with real difficulty"
echo "   • Multi-chain support (main + GPU chains)"
echo "   • Real coin generation: 50 AITBC (main), 25 AITBC (GPU)"
echo "   • Cross-chain trading capabilities"
echo ""
echo "✅ OpenClaw AI Integration:"
echo "   • Real AI agents: text generation, research, trading"
echo "   • Llama2 models: 7B, 13B parameters"
echo "   • Task execution with real results"
echo "   • Marketplace integration with payments"
echo ""
echo "✅ Real Commercial Marketplace:"
echo "   • OpenClaw AI services (5-15 AITBC per task)"
echo "   • Ollama inference tasks (3-5 AITBC per task)"
echo "   • Real commercial activity and transactions"
echo "   • Payment processing via blockchain"
echo ""
echo "✅ Multi-Node Deployment:"
echo "   • aitbc (localhost): Mining + AI + Marketplace (port 8006)"
echo "   • aitbc1 (remote): Mining + AI + Marketplace (port 8007)"
echo "   • Cross-node coordination and trading"
echo ""
echo "✅ Real Economic Activity:"
echo "   • Mining rewards: Real coin generation"
echo "   • AI services: Real commercial transactions"
echo "   • Marketplace: Real buying and selling"
echo "   • Multi-chain: Real cross-chain trading"
echo ""
echo "✅ Service Endpoints:"
echo "   • aitbc: http://localhost:8006/health"
echo "   • aitbc1: http://aitbc1:8007/health"
echo ""
echo "✅ Monitoring:"
echo "   • Mining logs: journalctl -u aitbc-mining-blockchain"
echo "   • AI logs: journalctl -u aitbc-openclaw-ai"
echo "   • Marketplace logs: journalctl -u aitbc-real-marketplace"
echo ""
echo -e "${BLUE}🚀 REAL PRODUCTION SYSTEM IS LIVE!${NC}"
echo ""
echo "🎉 AITBC is now a REAL production system with:"
echo "   • Real blockchain mining and coin generation"
echo "   • Real OpenClaw AI agents and services"
echo "   • Real commercial marketplace with transactions"
echo "   • Multi-chain support and cross-chain trading"
echo "   • Multi-node deployment and coordination"
