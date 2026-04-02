#!/bin/bash

# ============================================================================
# AITBC Mesh Network - List Applications Script
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

echo -e "${BLUE}📝 AITBC Job Applications${NC}"
echo "======================"

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time

# Load job marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Count total applications
total_applications = 0
pending_applications = 0
accepted_applications = 0

for job in marketplace['jobs'].values():
    applications = job.get('applications', [])
    total_applications += len(applications)
    for app in applications:
        if app['status'] == 'pending':
            pending_applications += 1
        elif app['status'] == 'accepted':
            accepted_applications += 1

print(f'Total Applications: {total_applications}')
print(f'Pending Applications: {pending_applications}')
print(f'Accepted Applications: {accepted_applications}')
print()

if total_applications > 0:
    print('Application Details:')
    print('=' * 80)
    
    app_counter = 1
    for job_id, job in marketplace['jobs'].items():
        applications = job.get('applications', [])
        if applications:
            print(f'Job: {job[\"title\"]} (ID: {job_id})')
            print(f'Budget: {job[\"budget\"]:.2f} AITBC | Status: {job[\"status\"]}')
            print('-' * 60)
            
            for app in applications:
                print(f'{app_counter}. Application for {job[\"title\"]}')
                print(f'   Agent: {app[\"agent_name\"]} ({app[\"agent_address\"]})')
                print(f'   Capability: {app[\"agent_capability\"]}')
                print(f'   Reputation: {app[\"agent_reputation\"]}/5.0')
                print(f'   Proposed Price: {app[\"proposed_price\"]:.2f} AITBC')
                print(f'   Application Status: {app[\"status\"]}')
                print(f'   Applied At: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(app[\"application_time\"]))}')
                print(f'   Cover Letter: {app[\"cover_letter\"]}')
                print()
                app_counter += 1
else:
    print('No job applications yet.')
    print('Use: ./scripts/apply-job.sh <agent_address> <job_id> to submit applications')
"
