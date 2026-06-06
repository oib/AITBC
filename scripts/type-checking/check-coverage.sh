#!/bin/bash
# Type checking coverage script for AITBC
# Measures and reports type checking coverage

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Main directory
AITBC_ROOT="/opt/aitbc"
cd "$AITBC_ROOT"

# Check if mypy is available
if ! command -v ./venv/bin/mypy &> /dev/null; then
    log_error "mypy not found. Please install with: pip install mypy"
    exit 1
fi

log_info "Running type checking coverage analysis..."

# Count total Python files
TOTAL_FILES=$(find apps/coordinator-api/src/app -name "*.py" | wc -l)
log_info "Total Python files: $TOTAL_FILES"

# Check core domain files (should pass)
CORE_DOMAIN_FILES=(
    "apps/coordinator-api/src/app/domain/job.py"
    "apps/coordinator-api/src/app/domain/miner.py"
    "apps/coordinator-api/src/app/domain/agent_portfolio.py"
)

CORE_PASSING=0
CORE_TOTAL=${#CORE_DOMAIN_FILES[@]}

for file in "${CORE_DOMAIN_FILES[@]}"; do
    if [ -f "$file" ]; then
        if ./venv/bin/mypy --ignore-missing-imports "$file" > /dev/null 2>&1; then
            ((CORE_PASSING++))
            log_success "✓ $file"
        else
            log_error "✗ $file"
        fi
    fi
done

# Check entire domain directory
DOMAIN_ERRORS=0
if ./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/ > /dev/null 2>&1; then
    log_success "Domain directory: PASSED"
else
    DOMAIN_ERRORS=$(./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/ 2>&1 | grep -c "error:" || echo "0")
    log_warning "Domain directory: $DOMAIN_ERRORS errors"
fi

# Calculate coverage percentages
CORE_COVERAGE=$((CORE_PASSING * 100 / CORE_TOTAL))
DOMAIN_COVERAGE=$(( (TOTAL_FILES - DOMAIN_ERRORS) * 100 / TOTAL_FILES ))

# Report results
echo ""
log_info "=== Type Checking Coverage Report ==="
echo "Core Domain Files: $CORE_PASSING/$CORE_TOTAL ($CORE_COVERAGE%)"
echo "Overall Coverage: $((TOTAL_FILES - DOMAIN_ERRORS))/$TOTAL_FILES ($DOMAIN_COVERAGE%)"
echo ""

# Set exit code based on coverage thresholds
THRESHOLD=80

if [ $CORE_COVERAGE -lt $THRESHOLD ]; then
    log_error "Core domain coverage below ${THRESHOLD}%: ${CORE_COVERAGE}%"
    exit 1
fi

if [ $DOMAIN_COVERAGE -lt $THRESHOLD ]; then
    log_warning "Overall coverage below ${THRESHOLD}%: ${DOMAIN_COVERAGE}%"
    exit 1
fi

log_success "Type checking coverage meets thresholds (≥${THRESHOLD}%)"
