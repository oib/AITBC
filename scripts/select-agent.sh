#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Select Agent for Job Script
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

# Get arguments
JOB_ID="$1"
AGENT_ADDRESS="$2"

if [[ -z "$JOB_ID" || -z "$AGENT_ADDRESS" ]]; then
    echo -e "${YELLOW}Usage: $0 <job_id> <agent_address>${NC}"
    echo ""
    echo "Example: $0 job_005 0xagent_006"
    echo ""
    echo "Available applications:"
    ./scripts/list-applications.sh | grep "Agent:" | head -5
    exit 1
fi

echo -e "${BLUE}🎯 Selecting Agent for Job${NC}"
echo "=========================="
echo "Job: $JOB_ID"
echo "Agent: $AGENT_ADDRESS"
echo ""

# Select agent
cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

# Load job marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Load economic system
with open('/opt/aitbc/data/economic_system.json', 'r') as f:
    economics = json.load(f)

# Validate job exists
if '$JOB_ID' not in marketplace['jobs']:
    print(f'❌ Error: Job {\"$JOB_ID\"} not found')
    exit(1)

# Validate agent exists
if '$AGENT_ADDRESS' not in registry['agents']:
    print(f'❌ Error: Agent {\"$AGENT_ADDRESS\"} not found')
    exit(1)

# Get job and agent details
job = marketplace['jobs']['$JOB_ID']
agent = registry['agents']['$AGENT_ADDRESS']

# Check if agent has applied
agent_application = None
for app in job.get('applications', []):
    if app['agent_address'] == '$AGENT_ADDRESS':
        agent_application = app
        break

if not agent_application:
    print(f'❌ Error: Agent {\"$AGENT_ADDRESS\"} has not applied for this job')
    exit(1)

# Check if job is still open
if job['status'] != 'open':
    print(f'❌ Error: Job {\"$JOB_ID\"} is not open for selection')
    exit(1)

# Update job status
job['status'] = 'in_progress'
job['selected_agent'] = '$AGENT_ADDRESS'
job['agent_selected_time'] = time.time()
job['last_updated'] = time.time()

# Update application status
for app in job['applications']:
    if app['agent_address'] == '$AGENT_ADDRESS':
        app['status'] = 'accepted'
    else:
        app['status'] = 'rejected'

# Create escrow record
escrow_amount = agent_application['proposed_price']
escrow_record = {
    'job_id': '$JOB_ID',
    'agent_address': '$AGENT_ADDRESS',
    'client_address': job['client'],
    'amount': escrow_amount,
    'status': 'funded',
    'created_at': time.time(),
    'milestones': [
        {
            'id': 'milestone_1',
            'description': 'Job completion',
            'amount': escrow_amount,
            'status': 'pending',
            'completed_at': None
        }
    ]
}

# Add escrow to economic system (simplified)
if 'escrow_contracts' not in economics:
    economics['escrow_contracts'] = {}

escrow_id = f'escrow_{len(economics[\"escrow_contracts\"]) + 1:03d}'
economics['escrow_contracts'][escrow_id] = escrow_record

# Update economic metrics
economics['network_metrics']['total_transactions'] += 1
economics['network_metrics']['total_value_locked'] += escrow_amount
economics['last_updated'] = time.time()

# Save updated marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

# Save updated economic system
with open('/opt/aitbc/data/economic_system.json', 'w') as f:
    json.dump(economics, f, indent=2)

print(f'✅ Agent Selected Successfully')
print(f'   Job: {job[\"title\"]}')
print(f'   Selected Agent: {agent[\"name\"]} ({agent[\"capabilities\"]})')
print(f'   Contract Amount: {escrow_amount:.2f} AITBC')
print(f'   Escrow ID: {escrow_id}')
print(f'   Job Status: {job[\"status\"]}')
print(f'   Selected At: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(job[\"agent_selected_time\"]))}')
print(f'   Other Applications: {len(job[\"applications\"]) - 1} rejected')
"

echo ""
echo -e "${GREEN}🎉 Agent selected and escrow created!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. Complete job: ./scripts/complete-job.sh <job_id>"
echo "2. View agent dashboard: ./scripts/agent-dashboard.sh"
echo "3. View economic system: ./scripts/economic-status.sh"
