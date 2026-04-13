#!/bin/bash

# AITBC Health Check Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local name=$1
    local url=$2
    local expected=${3:-200}
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected"; then
        echo -e "${GREEN}✓${NC} $name is healthy"
        return 0
    else
        echo -e "${RED}✗${NC} $name is unhealthy"
        return 1
    fi
}

echo "AITBC Service Health Check"
echo "========================"

# Core Services (8000-8009)
echo ""
echo "🔧 Core Services (8000-8009):"
check_service "Coordinator API" "http://localhost:8000/health"
check_service "Exchange API" "http://localhost:8001/api/health"
check_service "Marketplace API" "http://localhost:8007/health"
check_service "Wallet API" "http://localhost:8003/health"
check_service "Explorer" "http://localhost:8004/health"

# Check blockchain node and RPC
echo ""
echo "⛓️ Blockchain Services:"
if systemctl is-active --quiet aitbc-blockchain-node.service; then
    echo -e "${GREEN}✓${NC} Blockchain Node is running"
else
    echo -e "${RED}✗${NC} Blockchain Node is not running"
fi

if systemctl is-active --quiet aitbc-blockchain-rpc.service; then
    echo -e "${GREEN}✓${NC} Blockchain RPC (port 8006) is running"
else
    echo -e "${RED}✗${NC} Blockchain RPC (port 8006) is not running"
fi

# AI/Agent/GPU Services (8010-8019)
echo ""
echo "🚀 AI/Agent/GPU Services (8010-8019):"
check_service "GPU Service" "http://localhost:8010/health"
check_service "Learning Service" "http://localhost:8011/health"
check_service "Agent Coordinator" "http://localhost:8012/health"
check_service "Agent Registry" "http://localhost:8013/health"
check_service "OpenClaw Service" "http://localhost:8014/health"
check_service "AI Service" "http://localhost:8015/health"

# Other Services (8020-8029)
echo ""
echo "📊 Other Services (8020-8029):"
check_service "Multimodal Service" "http://localhost:8020/health"
check_service "Modality Optimization" "http://localhost:8021/health"

# Check process status
echo ""
echo "Process Status:"
ps aux | grep -E "simple_daemon|uvicorn|simple_exchange_api" | grep -v grep | while read line; do
    echo -e "${GREEN}✓${NC} $line"
done
