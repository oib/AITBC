#!/bin/bash

# ============================================================================
# AITBC Mesh Network - List Agents Script
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

echo -e "${BLUE}🤖 AITBC Agent Registry${NC}"
echo "======================"

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

print(f'Total Agents: {registry[\"total_agents\"]}')
print(f'Active Agents: {registry[\"active_agents\"]}')
print(f'Last Updated: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(registry[\"last_updated\"]))}')
print()

if registry['agents']:
    print('Agent Details:')
    print('=' * 80)
    for i, (address, agent) in enumerate(registry['agents'].items(), 1):
        print(f'{i}. {agent[\"name\"]}')
        print(f'   Address: {address}')
        print(f'   Capability: {agent[\"capabilities\"]}')
        print(f'   Reputation: {agent[\"reputation\"]}/5.0')
        print(f'   Jobs Completed: {agent[\"jobs_completed\"]}')
        print(f'   Total Earnings: {agent[\"total_earnings\"]:.2f} AITBC')
        print(f'   Stake: {agent[\"stake\"]:.2f} AITBC')
        print(f'   Status: {agent[\"status\"]}')
        print(f'   Created: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(agent[\"created_at\"]))}')
        print()
else:
    print('No agents registered yet.')
    print('Use: ./scripts/add-agent.sh <name> <capability> to add agents')
"
