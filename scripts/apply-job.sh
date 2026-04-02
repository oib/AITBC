#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Agent Job Application System
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
AGENT_ADDRESS="$1"
JOB_ID="$2"

if [[ -z "$AGENT_ADDRESS" || -z "$JOB_ID" ]]; then
    echo -e "${YELLOW}Usage: $0 <agent_address> <job_id>${NC}"
    echo ""
    echo "Example: $0 0xagent_001 job_001"
    echo ""
    echo "Available agents:"
    ./scripts/list-agents.sh | grep "Address:" | head -5
    echo ""
    echo "Available jobs:"
    ./scripts/list-jobs.sh | grep "Job ID:" | head -5
    exit 1
fi

echo -e "${BLUE}📝 Processing Agent Job Application${NC}"
echo "================================="
echo "Agent: $AGENT_ADDRESS"
echo "Job: $JOB_ID"
echo ""

# Process application
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

# Validate agent exists
if '$AGENT_ADDRESS' not in registry['agents']:
    print(f'❌ Error: Agent {\"$AGENT_ADDRESS\"} not found')
    exit(1)

# Validate job exists
if '$JOB_ID' not in marketplace['jobs']:
    print(f'❌ Error: Job {\"$JOB_ID\"} not found')
    exit(1)

# Get agent and job details
agent = registry['agents']['$AGENT_ADDRESS']
job = marketplace['jobs']['$JOB_ID']

# Check if job is still open
if job['status'] != 'open':
    print(f'❌ Error: Job {\"$JOB_ID\"} is not open for applications')
    exit(1)

# Check if agent has already applied
existing_applications = [app for app in job.get('applications', []) if app['agent_address'] == '$AGENT_ADDRESS']
if existing_applications:
    print(f'⚠️  Warning: Agent {\"$AGENT_ADDRESS\"} has already applied for this job')
    exit(1)

# Create application
application = {
    'agent_address': '$AGENT_ADDRESS',
    'agent_name': agent['name'],
    'agent_capability': agent['capabilities'],
    'agent_reputation': agent['reputation'],
    'proposed_price': job['budget'] * 0.9,  # 10% discount
    'cover_letter': f'I am {agent[\"name\"]} and I have the required {agent[\"capabilities\"]} skills to complete this job successfully.',
    'estimated_completion': time.time() + (3 * 24 * 60 * 60),  # 3 days from now
    'application_time': time.time(),
    'status': 'pending'
}

# Add application to job
if 'applications' not in job:
    job['applications'] = []
job['applications'].append(application)

# Update job
job['last_updated'] = time.time()

# Save updated marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Application Submitted Successfully')
print(f'   Agent: {agent[\"name\"]} ({agent[\"capabilities\"]})')
print(f'   Job: {job[\"title\"]}')
print(f'   Proposed Price: {application[\"proposed_price\"]:.2f} AITBC')
print(f'   Agent Reputation: {agent[\"reputation\"]}/5.0')
print(f'   Application Status: {application[\"status\"]}')
print(f'   Applied At: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(application[\"application_time\"]))}')
"

echo ""
echo -e "${GREEN}🎉 Agent application submitted successfully!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. View all applications: ./scripts/list-applications.sh"
echo "2. Select agent for job: ./scripts/select-agent.sh <job_id> <agent_address>"
echo "3. View agent dashboard: ./scripts/agent-dashboard.sh"
