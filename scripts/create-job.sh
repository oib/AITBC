#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Create Job Script
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
JOB_TITLE="$1"
BUDGET="$2"

if [[ -z "$JOB_TITLE" || -z "$BUDGET" ]]; then
    echo -e "${YELLOW}Usage: $0 <job_title> <budget>${NC}"
    echo ""
    echo "Example: $0 'Data Analysis Project' 500.0"
    exit 1
fi

# Validate budget is numeric
if ! [[ "$BUDGET" =~ ^[0-9]+\.?[0-9]*$ ]]; then
    echo -e "${RED}Error: Budget must be a numeric value${NC}"
    exit 1
fi

echo -e "${BLUE}💼 Creating New Job${NC}"
echo "=================="
echo "Title: $JOB_TITLE"
echo "Budget: $BUDGET AITBC"
echo ""

# Create job
cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import sys
import json
import time
import random

# Load job marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Generate unique job ID
job_id = marketplace['total_jobs'] + 1
job_address = f'job_{job_id:03d}'

# Create new job
new_job = {
    'id': job_address,
    'client': f'0xclient_{job_id:03d}',
    'title': '$JOB_TITLE',
    'description': f'This is job {job_id}: $JOB_TITLE',
    'category': random.choice(['content_creation', 'data_analysis', 'research', 'development']),
    'requirements': ['Python', 'AI/ML', 'Problem Solving'],
    'budget': float('$BUDGET'),
    'deadline': time.time() + (7 * 24 * 60 * 60),  # 7 days from now
    'status': 'open',
    'applications': [],
    'selected_agent': None,
    'created_at': time.time()
}

# Add job to marketplace
marketplace['jobs'][job_address] = new_job
marketplace['job_categories'][new_job['category']].append(job_address)
marketplace['total_jobs'] += 1
marketplace['active_jobs'] += 1
marketplace['last_updated'] = time.time()

# Save updated marketplace
with open('/opt/aitbc/data/job_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Job Created Successfully')
print(f'   Job ID: {new_job[\"id\"]}')
print(f'   Title: {new_job[\"title\"]}')
print(f'   Budget: {new_job[\"budget\"]:.2f} AITBC')
print(f'   Category: {new_job[\"category\"]}')
print(f'   Status: {new_job[\"status\"]}')
print(f'   Deadline: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.gmtime(new_job[\"deadline\"]))}')
"

echo ""
echo -e "${GREEN}🎉 Job '$JOB_TITLE' has been created on the AITBC marketplace!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. View all jobs: ./scripts/list-jobs.sh"
echo "2. View agent dashboard: ./scripts/agent-dashboard.sh"
echo "3. Add more agents: ./scripts/add-agent.sh <name> <capability>"
