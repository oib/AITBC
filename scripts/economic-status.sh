#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Economic Status Script
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

echo -e "${BLUE}💰 AITBC Economic System Status${NC}"
echo "=============================="

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time

# Load economic system
with open('/opt/aitbc/data/economic_system.json', 'r') as f:
    economics = json.load(f)

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

# Load job marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

print(f'Treasury Address: {economics[\"treasury_address\"]}')
print(f'Total Supply: {economics[\"total_supply\"]:,.0f} AITBC')
print(f'Reward Pool: {economics[\"reward_pool\"]:,.0f} AITBC')
print(f'Circulating Supply: {economics[\"circulating_supply\"]:,.0f} AITBC')
print(f'Gas Fees Collected: {economics[\"gas_fees_collected\"]:,.2f} AITBC')
print()

print('Network Metrics:')
print(f'  Total Transactions: {economics[\"network_metrics\"][\"total_transactions\"]}')
print(f'  Total Jobs Completed: {economics[\"network_metrics\"][\"total_jobs_completed\"]}')
print(f'  Total Value Locked: {economics[\"network_metrics\"][\"total_value_locked\"]:,.2f} AITBC')
print()

# Calculate agent earnings
total_agent_earnings = sum(agent['total_earnings'] for agent in registry['agents'].values())
active_agents = len([agent for agent in registry['agents'].values() if agent['status'] == 'active'])

print('Agent Economy:')
print(f'  Total Agents: {registry[\"total_agents\"]}')
print(f'  Active Agents: {active_agents}')
print(f'  Total Agent Earnings: {total_agent_earnings:.2f} AITBC')
print(f'  Average Earnings per Agent: {total_agent_earnings/active_agents if active_agents > 0 else 0:.2f} AITBC')
print()

# Job marketplace stats
total_jobs = marketplace['total_jobs']
active_jobs = marketplace['active_jobs']
completed_jobs = marketplace['completed_jobs']
total_budget = sum(job.get('budget', 0) for job in marketplace['jobs'].values())

print('Job Marketplace:')
print(f'  Total Jobs: {total_jobs}')
print(f'  Active Jobs: {active_jobs}')
print(f'  Completed Jobs: {completed_jobs}')
print(f'  Total Budget: {total_budget:.2f} AITBC')
print(f'  Success Rate: {(completed_jobs/total_jobs*100) if total_jobs > 0 else 0:.1f}%')
print()

# Escrow contracts
escrow_contracts = economics.get('escrow_contracts', {})
active_escrows = len([e for e in escrow_contracts.values() if e['status'] == 'funded'])
completed_escrows = len([e for e in escrow_contracts.values() if e['status'] == 'completed'])

print('Escrow System:')
print(f'  Total Escrow Contracts: {len(escrow_contracts)}')
print(f'  Active Escrows: {active_escrows}')
print(f'  Completed Escrows: {completed_escrows}')
print(f'  Total Escrow Value: {sum(e[\"amount\"] for e in escrow_contracts.values()):.2f} AITBC')
print()

# Top earning agents
top_agents = sorted(registry['agents'].items(), key=lambda x: x[1]['total_earnings'], reverse=True)[:3]

if top_agents:
    print('Top Earning Agents:')
    for i, (address, agent) in enumerate(top_agents, 1):
        if agent['total_earnings'] > 0:
            print(f'  {i}. {agent[\"name\"]}: {agent[\"total_earnings\"]:.2f} AITBC ({agent[\"jobs_completed\"]} jobs)')
print()

print(f'Last Updated: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(economics[\"last_updated\"]))}')
"
