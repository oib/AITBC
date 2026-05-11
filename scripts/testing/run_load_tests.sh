#!/bin/bash

# AITBC Load Test Runner
# Runs canonical load tests against marketplace and blockchain RPC endpoints
# Generates baseline reports for production readiness assessment

set -e

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
REPORT_DIR="${REPORT_DIR:-/var/log/aitbc/load-tests}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"

# Load test parameters (with defaults)
USERS="${LOAD_USERS:-100}"
SPAWN_RATE="${LOAD_SPAWN_RATE:-10}"
DURATION="${LOAD_DURATION:-5m}"
MARKETPLACE_HOST="${MARKETPLACE_HOST:-http://localhost:8102}"
BLOCKCHAIN_HOST="${BLOCKCHAIN_HOST:-http://localhost:8006}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create report directory
mkdir -p "$REPORT_DIR"

# Timestamp for reports
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_PREFIX="$REPORT_DIR/load-test-$TIMESTAMP"

log_info "=== AITBC Load Test Runner ==="
log_info "Timestamp: $TIMESTAMP"
log_info "Users: $USERS"
log_info "Spawn Rate: $SPAWN_RATE"
log_info "Duration: $DURATION"
log_info "Marketplace Host: $MARKETPLACE_HOST"
log_info "Blockchain Host: $BLOCKCHAIN_HOST"
log_info "Report Prefix: $REPORT_PREFIX"

# Check if locust is available
if [ -f "$VENV_DIR/bin/locust" ]; then
    LOCUST="$VENV_DIR/bin/locust"
elif command -v locust &> /dev/null; then
    LOCUST="locust"
else
    log_error "locust not found. Install with: pip install locust"
    exit 1
fi

log_info "Using locust: $LOCUST"

# Health check endpoints
log_info "Checking endpoint availability..."

check_endpoint() {
    local url="$1"
    local name="$2"
    
    if curl -sf -o /dev/null --max-time 5 "$url"; then
        log_success "$name endpoint is available"
        return 0
    else
        log_warn "$name endpoint is not available (will proceed with load test anyway)"
        return 1
    fi
}

check_endpoint "$MARKETPLACE_HOST/health" "Marketplace"
check_endpoint "$BLOCKCHAIN_HOST/health" "Blockchain"

# Set environment variables for hosts
export MARKETPLACE_HOST
export BLOCKCHAIN_HOST

# Run load test
log_info "Starting load test..."
log_info "This will run for $DURATION with $USERS users spawning at $SPAWN_RATE users/sec"

$LOCUST -f "$REPO_ROOT/tests/load/test_api_load.py" \
    --headless \
    -u "$USERS" \
    -r "$SPAWN_RATE" \
    -t "$DURATION" \
    --csv "$REPORT_PREFIX" \
    --html "$REPORT_PREFIX.html" \
    --only-summary \
    2>&1 | tee "$REPORT_PREFIX.log"

# Check exit code
LOCUST_EXIT=${PIPESTATUS[0]}

if [ $LOCUST_EXIT -eq 0 ]; then
    log_success "Load test completed successfully"
else
    log_error "Load test failed with exit code $LOCUST_EXIT"
fi

# Generate summary report
log_info "Generating summary report..."

cat > "$REPORT_PREFIX-summary.txt" << EOF
AITBC Load Test Summary
========================
Timestamp: $TIMESTAMP
Users: $USERS
Spawn Rate: $SPAWN_RATE
Duration: $DURATION
Marketplace Host: $MARKETPLACE_HOST
Blockchain Host: $BLOCKCHAIN_HOST

Results:
--------
$(tail -20 "$REPORT_PREFIX.log")

Reports:
--------
- Log: $REPORT_PREFIX.log
- CSV Stats: $REPORT_PREFIX_stats.csv
- CSV History: $REPORT_PREFIX_stats_history.csv
- CSV Failures: $REPORT_PREFIX_failures.csv
- HTML Report: $REPORT_PREFIX.html
- Summary: $REPORT_PREFIX-summary.txt
EOF

log_success "Summary report generated: $REPORT_PREFIX-summary.txt"
log_info "Full report available at: $REPORT_PREFIX.html"

exit $LOCUST_EXIT
