#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Operations Dashboard
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
PYTHON_CMD="$VENV_DIR/bin/python"

clear
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                AITBC MESH NETWORK OPERATIONS              ║${NC}"
echo -e "${BLUE}║                      DASHBOARD v1.0                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# #920: everything below reads the LIVE system — the local RPC for chain
# state, the env file for identity, systemctl for units. The previous
# version built a fresh in-process consensus object and added two
# invented validators, then printed that as status.

BLOCKCHAIN_ENV="${AITBC_BLOCKCHAIN_ENV:-/etc/aitbc/blockchain.env}"
RPC_PORT="${AITBC_RPC_PORT:-$(grep -iE '^rpc_bind_port=' "$BLOCKCHAIN_ENV" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \'"'"'"' || true)}"
RPC_PORT="${RPC_PORT:-8202}"
P2P_PORT="${AITBC_P2P_PORT:-$(grep -iE '^p2p_bind_port=' "$BLOCKCHAIN_ENV" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \'"'"'"' || true)}"
P2P_PORT="${P2P_PORT:-7070}"

# System Status
echo -e "${CYAN}📊 CHAIN STATUS${NC}"
echo "================================"

head_json=$(curl -sf --max-time 5 "http://localhost:${RPC_PORT}/rpc/head" 2>/dev/null || true)
if [ -n "$head_json" ]; then
    height=$(echo "$head_json" | "$PYTHON_CMD" -c 'import json,sys; print(json.load(sys.stdin).get("height","?"))' 2>/dev/null || echo "?")
    proposer=$(echo "$head_json" | "$PYTHON_CMD" -c 'import json,sys; print(json.load(sys.stdin).get("proposer","?"))' 2>/dev/null || echo "?")
    echo -e "${GREEN}✅ RPC head: height $height${NC}"
    echo "   Proposer: $proposer"
else
    echo -e "${RED}❌ RPC head: unreachable at localhost:${RPC_PORT}${NC}"
fi

if [ -r "$BLOCKCHAIN_ENV" ]; then
    chain_id=$(grep -iE '^chain_id=' "$BLOCKCHAIN_ENV" | head -1 | cut -d= -f2 | tr -d ' \'"'"'"' || true)
    vset=$(grep -iE '^validator_set=' "$BLOCKCHAIN_ENV" | head -1 | cut -d= -f2- | tr -d ' \'"'"'"' || true)
    [ -n "${chain_id:-}" ] && echo "   Chain: $chain_id"
    if [ -n "${vset:-}" ]; then
        vcount=$(echo "$vset" | tr ',' '\n' | grep -c . || true)
        echo "   Validators configured: $vcount"
    fi
fi

echo ""

# Network Status
echo -e "${CYAN}🌐 NETWORK STATUS${NC}"
echo "================================"

for port in "$RPC_PORT" "$P2P_PORT" 9090; do
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}✅ Port $port: OPEN${NC}"
    else
        echo -e "${YELLOW}⚠️  Port $port: CLOSED${NC}"
    fi
done

echo ""

# Service Status
echo -e "${CYAN}🔧 SERVICE STATUS${NC}"
echo "================================"

services=("aitbc-blockchain-node" "aitbc-blockchain-rpc" "aitbc-agent-coordinator")
for unit in "${services[@]}"; do
    state=$(systemctl is-active "$unit" 2>/dev/null || echo "unknown")
    case "$state" in
        active)   echo -e "${GREEN}✅ $unit: active${NC}" ;;
        inactive) echo -e "${RED}❌ $unit: inactive${NC}" ;;
        *)        echo -e "${YELLOW}⚠️  $unit: $state${NC}" ;;
    esac
done

echo ""

# Recent Activity
echo -e "${CYAN}📈 RECENT ACTIVITY${NC}"
echo "================================"

# Check deployment logs
if [[ -f "$AITBC_ROOT/logs/quick_deployment.log" ]]; then
    echo "Latest deployment: $(tail -n 1 "$AITBC_ROOT/logs/quick_deployment.log" | cut -d']' -f2-)"
fi

# Check git status
cd "$AITBC_ROOT"
if git status --porcelain | grep -q .; then
    echo -e "${YELLOW}⚠️  Uncommitted changes present${NC}"
else
    echo -e "${GREEN}✅ Repository clean${NC}"
fi

echo ""

# Quick Actions
echo -e "${CYAN}⚡ QUICK ACTIONS${NC}"
echo "================================"
echo "1. Add Validator:     ./scripts/manage-services.sh add-validator <address>"
echo "2. Check Status:      ./scripts/manage-services.sh status"
echo "3. Start Services:    ./scripts/manage-services.sh start"
echo "4. View Logs:         tail -f logs/quick_deployment.log"
echo "5. Deploy to ${NODE1_HOST}:  ssh ${NODE1_HOST} 'cd /opt/aitbc && git pull && ./scripts/manage-services.sh start'"

echo ""

# Environment Info
echo -e "${CYAN}🌍 ENVIRONMENT${NC}"
echo "================================"
echo "Current Environment: ${AITBC_ENV:-dev}"
echo "Working Directory: $AITBC_ROOT"
echo "Python Virtual Env: $VENV_DIR"
echo "Configuration: $AITBC_ROOT/config/${AITBC_ENV:-dev}/.env"

echo ""

# Next Steps
echo -e "${CYAN}🎯 RECOMMENDED NEXT STEPS${NC}"
echo "================================"
echo "1. Add more validators (target: 5+ for dev)"
echo "2. Test consensus with different block heights"
echo "3. Deploy to ${NODE1_HOST} node for multi-node testing"
echo "4. Configure agent registration"
echo "5. Set up monitoring and alerting"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                Press CTRL+C to refresh dashboard              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

# Auto-refresh every 30 seconds
sleep 30
exec "$0"
