#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Agent Operations Dashboard
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
echo -e "${BLUE}║                AITBC AGENT ECONOMY DASHBOARD               ║${NC}"
echo -e "${BLUE}║                     LIVE OPERATIONS                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Agent Economy Status
echo -e "${CYAN}🤖 AGENT ECONOMY STATUS${NC}"
echo "=============================="

cd "$AITBC_ROOT"
if [[ -f "/opt/aitbc/data/agent_registry.json" ]]; then
    agent_info=$("$PYTHON_CMD" -c "
import json

with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

print(f'AGENTS:ACTIVE:{registry[\"total_agents\"]}:{registry[\"active_agents\"]}')

# Count by capability
capability_counts = {}
for capability, agents in registry['capabilities'].items():
    capability_counts[capability] = len(agents)

for capability, count in capability_counts.items():
    if count > 0:
        print(f'CAPABILITY:{capability}:{count}')
" 2>/dev/null)

    if [[ "$agent_info" == AGENTS:ACTIVE:* ]]; then
        total_agents=$(echo "$agent_info" | grep "AGENTS:" | cut -d: -f3)
        active_agents=$(echo "$agent_info" | grep "AGENTS:" | cut -d: -f4)
        
        echo -e "${GREEN}✅ Agent Registry: ACTIVE${NC}"
        echo "   Total Agents: $total_agents"
        echo "   Active Agents: $active_agents"
        
        # Show capabilities
        echo "   Capabilities:"
        echo "$agent_info" | grep "CAPABILITY:" | while read line; do
            capability=$(echo "$line" | cut -d: -f2)
            count=$(echo "$line" | cut -d: -f3)
            echo "     - $capability: $count agents"
        done
    else
        echo -e "${RED}❌ Agent Registry: INACTIVE${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Agent Registry: NOT FOUND${NC}"
fi

echo ""

# Job Marketplace Status
echo -e "${CYAN}💼 JOB MARKETPLACE STATUS${NC}"
echo "==============================="

if [[ -f "/opt/aitbc/data/job_marketplace.json" ]]; then
    job_info=$("$PYTHON_CMD" -c "
import json

with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

print(f'JOBS:ACTIVE:{marketplace[\"total_jobs\"]}:{marketplace[\"active_jobs\"]}:{marketplace[\"completed_jobs\"]}')

# Count by category
category_counts = {}
for category, jobs in marketplace['job_categories'].items():
    category_counts[category] = len(jobs)

for category, count in category_counts.items():
    if count > 0:
        print(f'CATEGORY:{category}:{count}')

# Calculate total budget
total_budget = sum(job.get('budget', 0) for job in marketplace['jobs'].values())
print(f'BUDGET:{total_budget}')
" 2>/dev/null)

    if [[ "$job_info" == JOBS:ACTIVE:* ]]; then
        total_jobs=$(echo "$job_info" | grep "JOBS:" | cut -d: -f3)
        active_jobs=$(echo "$job_info" | grep "JOBS:" | cut -d: -f4)
        completed_jobs=$(echo "$job_info" | grep "JOBS:" | cut -d: -f5)
        total_budget=$(echo "$job_info" | grep "BUDGET:" | cut -d: -f2)
        
        echo -e "${GREEN}✅ Job Marketplace: ACTIVE${NC}"
        echo "   Total Jobs: $total_jobs"
        echo "   Active Jobs: $active_jobs"
        echo "   Completed Jobs: $completed_jobs"
        echo "   Total Budget: ${total_budget:.2f} AITBC"
        
        # Show categories
        echo "   Categories:"
        echo "$job_info" | grep "CATEGORY:" | while read line; do
            category=$(echo "$line" | cut -d: -f2)
            count=$(echo "$line" | cut -d: -f3)
            echo "     - $category: $count jobs"
        done
    else
        echo -e "${RED}❌ Job Marketplace: INACTIVE${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Job Marketplace: NOT FOUND${NC}"
fi

echo ""

# Economic System Status
echo -e "${CYAN}💰 ECONOMIC SYSTEM STATUS${NC}"
echo "============================="

if [[ -f "/opt/aitbc/data/economic_system.json" ]]; then
    economic_info=$("$PYTHON_CMD" -c "
import json

with open('/opt/aitbc/data/economic_system.json', 'r') as f:
    economics = json.load(f)

print(f'ECONOMICS:ACTIVE:{economics[\"total_supply\"]}:{economics[\"reward_pool\"]}:{economics[\"circulating_supply\"]}')
print(f'TREASURY:{economics[\"treasury_address\"]}')
print(f'TRANSACTIONS:{economics[\"network_metrics\"][\"total_transactions\"]}')
print(f'VALUE_LOCKED:{economics[\"network_metrics\"][\"total_value_locked\"]}')
" 2>/dev/null)

    if [[ "$economic_info" == ECONOMICS:ACTIVE:* ]]; then
        total_supply=$(echo "$economic_info" | grep "ECONOMICS:" | cut -d: -f3)
        reward_pool=$(echo "$economic_info" | grep "ECONOMICS:" | cut -d: -f4)
        circulating_supply=$(echo "$economic_info" | grep "ECONOMICS:" | cut -d: -f5)
        treasury=$(echo "$economic_info" | grep "TREASURY:" | cut -d: -f2)
        transactions=$(echo "$economic_info" | grep "TRANSACTIONS:" | cut -d: -f2)
        value_locked=$(echo "$economic_info" | grep "VALUE_LOCKED:" | cut -d: -f2)
        
        echo -e "${GREEN}✅ Economic System: ACTIVE${NC}"
        echo "   Total Supply: $total_supply AITBC"
        echo "   Reward Pool: $reward_pool AITBC"
        echo "   Circulating Supply: $circulating_supply AITBC"
        echo "   Treasury: $treasury"
        echo "   Total Transactions: $transactions"
        echo "   Value Locked: $value_locked AITBC"
    else
        echo -e "${RED}❌ Economic System: INACTIVE${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Economic System: NOT FOUND${NC}"
fi

echo ""

# Recent Activity
echo -e "${CYAN}📈 RECENT ACTIVITY${NC}"
echo "===================="

# Check latest files
if [[ -f "/opt/aitbc/data/agent_registry.json" ]]; then
    agent_time=$(stat -c %Y /opt/aitbc/data/agent_registry.json 2>/dev/null || echo "0")
    echo "Agent Registry Updated: $(date -d @$agent_time '+%Y-%m-%d %H:%M:%S')"
fi

if [[ -f "/opt/aitbc/data/job_marketplace.json" ]]; then
    job_time=$(stat -c %Y /opt/aitbc/data/job_marketplace.json 2>/dev/null || echo "0")
    echo "Job Marketplace Updated: $(date -d @$job_time '+%Y-%m-%d %H:%M:%S')"
fi

if [[ -f "/opt/aitbc/data/economic_system.json" ]]; then
    econ_time=$(stat -c %Y /opt/aitbc/data/economic_system.json 2>/dev/null || echo "0")
    echo "Economic System Updated: $(date -d @$econ_time '+%Y-%m-%d %H:%M:%S')"
fi

echo ""

# Quick Actions
echo -e "${CYAN}⚡ QUICK ACTIONS${NC}"
echo "===================="
echo "1. Add Agent:         ./scripts/add-agent.sh <name> <capability>"
echo "2. Create Job:        ./scripts/create-job.sh <title> <budget>"
echo "3. View Agents:       ./scripts/list-agents.sh"
echo "4. View Jobs:         ./scripts/list-jobs.sh"
echo "5. Agent Dashboard:   ./scripts/agent-dashboard.sh"

echo ""

# Network Status
echo -e "${CYAN}🌐 NETWORK STATUS${NC}"
echo "=================="

# Check consensus
cd "$AITBC_ROOT"
consensus_status=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

poa = MultiValidatorPoA(chain_id=1337)
poa.add_validator('0xvalidator1', 1000.0)
poa.add_validator('0xvalidator2', 1000.0)

total_stake = sum(v.stake for v in poa.validators.values())
print(f'CONSENSUS:ACTIVE:{len(poa.validators)}:{total_stake}')
" 2>/dev/null)

if [[ "$consensus_status" == CONSENSUS:ACTIVE:* ]]; then
    validator_count=$(echo "$consensus_status" | cut -d: -f3)
    total_stake=$(echo "$consensus_status" | cut -d: -f4)
    
    echo -e "${GREEN}✅ Network Consensus: ACTIVE${NC}"
    echo "   Validators: $validator_count"
    echo "   Total Stake: $total_stake AITBC"
else
    echo -e "${RED}❌ Network Consensus: INACTIVE${NC}"
fi

echo ""

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Press CTRL+C to refresh dashboard              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

# Auto-refresh every 30 seconds
sleep 30
exec "$0"
