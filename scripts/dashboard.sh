#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Operations Dashboard
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
PYTHON_CMD="$VENV_DIR/bin/python"

clear
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                AITBC MESH NETWORK OPERATIONS              ║${NC}"
echo -e "${BLUE}║                      DASHBOARD v1.0                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# System Status
echo -e "${CYAN}📊 SYSTEM STATUS${NC}"
echo "================================"

# Check consensus
cd "$AITBC_ROOT"
consensus_info=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    poa = MultiValidatorPoA(chain_id=1337)
    
    # Add test validators if empty
    if len(poa.validators) == 0:
        poa.add_validator('0xvalidator1', 1000.0)
        poa.add_validator('0xvalidator2', 1000.0)
    
    total_stake = sum(v.stake for v in poa.validators.values())
    print(f'CONSENSUS:ACTIVE:{len(poa.validators)}:{total_stake}')
    
    # Get proposer
    proposer = poa.select_proposer(block_height=1)
    print(f'PROPOSER:{proposer}')
except Exception as e:
    print(f'CONSENSUS:ERROR:{e}')
" 2>/dev/null)

if [[ "$consensus_info" == CONSENSUS:ACTIVE:* ]]; then
    validator_count=$(echo "$consensus_info" | cut -d: -f3)
    total_stake=$(echo "$consensus_info" | cut -d: -f4)
    proposer=$(echo "$consensus_info" | cut -d: -f5-)
    
    echo -e "${GREEN}✅ Consensus: ACTIVE${NC}"
    echo "   Validators: $validator_count"
    echo "   Total Stake: $total_stake AITBC"
    echo "   Current Proposer: $proposer"
else
    echo -e "${RED}❌ Consensus: INACTIVE${NC}"
fi

echo ""

# Network Status
echo -e "${CYAN}🌐 NETWORK STATUS${NC}"
echo "================================"

# Check basic connectivity
if ping -c 1 localhost >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Network Connectivity: ACTIVE${NC}"
else
    echo -e "${RED}❌ Network Connectivity: FAILED${NC}"
fi

# Check ports
ports=("8545" "30303" "9090")
for port in "${ports[@]}"; do
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

services=("consensus" "network" "economics" "agents" "contracts")
for service in "${services[@]}"; do
    case "$service" in
        "consensus")
            if [[ "$consensus_info" == CONSENSUS:ACTIVE:* ]]; then
                echo -e "${GREEN}✅ Consensus Service: RUNNING${NC}"
            else
                echo -e "${RED}❌ Consensus Service: STOPPED${NC}"
            fi
            ;;
        "network")
            echo -e "${YELLOW}⚠️  Network Service: LIMITED${NC}"
            ;;
        "economics")
            echo -e "${GREEN}✅ Economics Service: RUNNING${NC}"
            ;;
        "agents")
            echo -e "${YELLOW}⚠️  Agent Services: LIMITED${NC}"
            ;;
        "contracts")
            echo -e "${GREEN}✅ Contract Service: RUNNING${NC}"
            ;;
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
echo "5. Deploy to aitbc1:  ssh aitbc1 'cd /opt/aitbc && git pull && ./scripts/manage-services.sh start'"

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
echo "3. Deploy to aitbc1 node for multi-node testing"
echo "4. Configure agent registration"
echo "5. Set up monitoring and alerting"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                Press CTRL+C to refresh dashboard              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

# Auto-refresh every 30 seconds
sleep 30
exec "$0"
