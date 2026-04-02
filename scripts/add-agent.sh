#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Add Agent Script
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
PYTHON_CMD="$VENV_DIR/bin/python"

# Get arguments
AGENT_NAME="$1"
CAPABILITY="$2"

if [[ -z "$AGENT_NAME" || -z "$CAPABILITY" ]]; then
    echo -e "${YELLOW}Usage: $0 <agent_name> <capability>${NC}"
    echo ""
    echo "Available capabilities:"
    echo "  - text_generation"
    echo "  - data_analysis"
    echo "  - image_processing"
    echo "  - trading"
    echo "  - research"
    exit 1
fi

# Validate capability
VALID_CAPABILITIES=("text_generation" "data_analysis" "image_processing" "trading" "research")
if [[ ! " ${VALID_CAPABILITIES[@]} " =~ " ${CAPABILITY} " ]]; then
    echo -e "${RED}Error: Invalid capability '$CAPABILITY'${NC}"
    echo "Valid capabilities: ${VALID_CAPABILITIES[*]}"
    exit 1
fi

echo -e "${BLUE}🤖 Adding New Agent${NC}"
echo "=================="
echo "Name: $AGENT_NAME"
echo "Capability: $CAPABILITY"
echo ""

# Add agent
cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time
import random

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

# Generate unique agent address
agent_id = registry['total_agents'] + 1
agent_address = f'0xagent_{agent_id:03d}'

# Create new agent
new_agent = {
    'address': agent_address,
    'name': '$AGENT_NAME',
    'owner': f'0xowner_{agent_id:03d}',
    'capabilities': '$CAPABILITY',
    'reputation': 5.0,
    'total_earnings': 0.0,
    'jobs_completed': 0,
    'success_rate': 1.0,
    'stake': 1000.0,
    'status': 'active',
    'created_at': time.time()
}

# Add agent to registry
registry['agents'][agent_address] = new_agent
registry['capabilities']['$CAPABILITY'].append(agent_address)
registry['total_agents'] += 1
registry['active_agents'] += 1
registry['last_updated'] = time.time()

# Save updated registry
with open('/opt/aitbc/data/agent_registry.json', 'w') as f:
    json.dump(registry, f, indent=2)

print(f'✅ Agent Added Successfully')
print(f'   Address: {agent_address}')
print(f'   Name: {new_agent[\"name\"]}')
print(f'   Capability: {new_agent[\"capabilities\"]}')
print(f'   Reputation: {new_agent[\"reputation\"]}')
print(f'   Stake: {new_agent[\"stake\"]} AITBC')
print(f'   Status: {new_agent[\"status\"]}')
"

echo ""
echo -e "${GREEN}🎉 Agent '$AGENT_NAME' has been added to the AITBC network!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. View all agents: ./scripts/list-agents.sh"
echo "2. Create a job: ./scripts/create-job.sh <title> <budget>"
echo "3. View agent dashboard: ./scripts/agent-dashboard.sh"
