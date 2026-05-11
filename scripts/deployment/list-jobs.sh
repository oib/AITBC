#!/bin/bash

# ============================================================================
# AITBC Mesh Network - List Jobs Script
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

echo -e "${BLUE}💼 AITBC Job Marketplace${NC}"
echo "======================"

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time

# Load job marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

print(f'Total Jobs: {marketplace[\"total_jobs\"]}')
print(f'Active Jobs: {marketplace[\"active_jobs\"]}')
print(f'Completed Jobs: {marketplace[\"completed_jobs\"]}')
print(f'Last Updated: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(marketplace[\"last_updated\"]))}')
print()

# Calculate total budget
total_budget = sum(job.get('budget', 0) for job in marketplace['jobs'].values())
print(f'Total Budget: {total_budget:.2f} AITBC')
print()

if marketplace['jobs']:
    print('Job Listings:')
    print('=' * 80)
    for i, (job_id, job) in enumerate(marketplace['jobs'].items(), 1):
        print(f'{i}. {job[\"title\"]}')
        print(f'   Job ID: {job_id}')
        print(f'   Client: {job[\"client\"]}')
        print(f'   Category: {job[\"category\"]}')
        print(f'   Budget: {job[\"budget\"]:.2f} AITBC')
        print(f'   Status: {job[\"status\"]}')
        print(f'   Applications: {len(job.get(\"applications\", []))}')
        print(f'   Selected Agent: {job.get(\"selected_agent\", \"None\")}')
        print(f'   Deadline: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(job[\"deadline\"]))}')
        print(f'   Created: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(job[\"created_at\"]))}')
        print()
else:
    print('No jobs posted yet.')
    print('Use: ./scripts/create-job.sh <title> <budget> to create jobs')
"
