#!/bin/bash
#
# AITBC Nightly Health Check
# Runs master planning cleanup and reports docs/planning cleanliness.
#
set -e

PROJECT_ROOT="/opt/aitbc"
PLANNING_DIR="$PROJECT_ROOT/docs/10_plan"
DOCS_DIR="$PROJECT_ROOT/docs"
MASTER_WORKFLOW="$PROJECT_ROOT/scripts/run_master_planning_cleanup.sh"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $1"; }

log_info "Starting nightly health check..."

if [[ -x "$MASTER_WORKFLOW" ]]; then
  log_info "Running master planning cleanup workflow..."
  if ! "$MASTER_WORKFLOW"; then
    log_warn "Master workflow reported issues; continuing to collect stats."
  fi
else
  log_warn "Master workflow script not found or not executable: $MASTER_WORKFLOW"
fi

log_info "Collecting docs/planning stats..."
planning_files=$(find "$PLANNING_DIR" -name "*.md" | wc -l)
completed_files=$(find "$DOCS_DIR/completed" -name "*.md" | wc -l)
archive_files=$(find "$DOCS_DIR/archive" -name "*.md" | wc -l)
documented_files=$(find "$DOCS_DIR" -name "documented_*.md" | wc -l)
completion_markers=$(find "$PLANNING_DIR" -name "*.md" -exec grep -l "✅" {} \; | wc -l)

echo "--- Nightly Health Check Summary ---"
echo "Planning files (docs/10_plan): $planning_files"
echo "Completed files (docs/completed): $completed_files"
echo "Archive files (docs/archive): $archive_files"
echo "Documented files (docs/): $documented_files"
echo "Files with completion markers: $completion_markers"

if [[ $completion_markers -eq 0 ]]; then
  log_info "Planning cleanliness OK (0 completion markers)."
else
  log_warn "Completion markers remain in planning files ($completion_markers)."
fi

log_info "Nightly health check completed."
