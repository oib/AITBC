#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Complete Job Script
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

if [[ -z "$JOB_ID" ]]; then
    echo -e "${YELLOW}Usage: $0 <job_id>${NC}"
    echo ""
    echo "Example: $0 job_006"
    echo ""
    echo "Available in-progress jobs:"
    ./scripts/list-jobs.sh | grep "Status: in_progress" | head -3
    exit 1
fi

echo -e "${BLUE}✅ Completing Job${NC}"
echo "=================="
echo "Job: $JOB_ID"
echo ""

# Complete job
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

# Get job details
job = marketplace['jobs']['$JOB_ID']

# Check if job is in progress
if job['status'] != 'in_progress':
    print(f'❌ Error: Job {\"$JOB_ID\"} is not in progress')
    print(f'   Current status: {job[\"status\"]}')
    exit(1)

# Get selected agent
if not job.get('selected_agent'):
    print(f'❌ Error: No agent selected for job {\"$JOB_ID\"}')
    exit(1)

agent_address = job['selected_agent']
agent = registry['agents'][agent_address]

# Find escrow record
escrow_record = None
escrow_id = None
for eid, escrow in economics.get('escrow_contracts', {}).items():
    if escrow['job_id'] == '$JOB_ID':
        escrow_record = escrow
        escrow_id = eid
        break

if not escrow_record:
    print(f'❌ Error: No escrow record found for job {\"$JOB_ID\"}')
    exit(1)

# Update job status
job['status'] = 'completed'
job['completed_at'] = time.time()
job['last_updated'] = time.time()

# Update agent stats
agent['jobs_completed'] += 1
agent['total_earnings'] += escrow_record['amount']
agent['success_rate'] = 1.0  # Perfect for completed jobs

# Update escrow - release funds
escrow_record['status'] = 'completed'
for milestone in escrow_record['milestones']:
    if milestone['status'] == 'pending':
        milestone['status'] = 'completed'
        milestone['completed_at'] = time.time()

# Update economic system
economics['network_metrics']['total_jobs_completed'] += 1
economics['network_metrics']['total_value_locked'] -= escrow_record['amount']
economics['last_updated'] = time.time()

# Update marketplace counters
marketplace['active_jobs'] -= 1
marketplace['completed_jobs'] += 1
marketplace['last_updated'] = time.time()

# Save all updated files
with open('/opt/aitbc/data/job_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

with open('/opt/aitbc/data/agent_registry.json', 'w') as f:
    json.dump(registry, f, indent=2)

with open('/opt/aitbc/data/economic_system.json', 'w') as f:
    json.dump(economics, f, indent=2)

print(f'✅ Job Completed Successfully')
print(f'   Job: {job[\"title\"]}')
print(f'   Agent: {agent[\"name\"]}')
print(f'   Amount Paid: {escrow_record[\"amount\"]:.2f} AITBC')
print(f'   Escrow ID: {escrow_id}')
print(f'   Job Status: {job[\"status\"]}')
print(f'   Completed At: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(job[\"completed_at\"]))}')
print(f'   Agent Total Jobs: {agent[\"jobs_completed\"]}')
print(f'   Agent Total Earnings: {agent[\"total_earnings\"]:.2f} AITBC')
"

echo ""
echo -e "${GREEN}🎉 Job completed and agent paid!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. View completed jobs: ./scripts/list-jobs.sh"
echo "2. View agent stats: ./scripts/list-agents.sh"
echo "3. View economic activity: ./scripts/economic-status.sh"
