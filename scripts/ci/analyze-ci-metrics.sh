#!/bin/bash
# CI Reliability Metrics Analyzer
# Analyzes CI logs from /opt/gitea-runner/logs/index.tsv to track success rates and failure patterns

# Set locale for consistent decimal formatting
export LC_ALL=C

LOG_INDEX="/opt/gitea-runner/logs/index.tsv"
METRICS_DIR="/opt/gitea-runner/metrics"
REPORT_FILE="$METRICS_DIR/ci-reliability-report-$(date +%Y%m%d).txt"
JSON_FILE="$METRICS_DIR/ci-reliability-$(date +%Y%m%d).json"

mkdir -p "$METRICS_DIR"

echo "=== CI Reliability Metrics Analysis ==="
echo "Analysis date: $(date)"
echo ""

# Initialize counters
declare -A workflow_total
declare -A workflow_success
declare -A workflow_failure
declare -A job_total
declare -A job_success
declare -A job_failure
declare -A failure_patterns

total_runs=0
total_success=0
total_failure=0

# Parse index.tsv and analyze each log file
echo "Analyzing CI logs..."
while IFS=$'\t' read -r timestamp run_id1 run_id2 attempt workflow job logfile; do
  if [[ -z "$logfile" ]]; then
    continue
  fi

  total_runs=$((total_runs + 1))
  workflow_total["$workflow"]=$((${workflow_total[$workflow]:-0} + 1))
  job_total["$job"]=$((${job_total[$job]:-0} + 1))

  # Check if log file exists
  if [[ ! -f "$logfile" ]]; then
    echo "Warning: Log file not found: $logfile"
    workflow_failure["$workflow"]=$((${workflow_failure[$workflow]:-0} + 1))
    job_failure["$job"]=$((${job_failure[$job]:-0} + 1))
    total_failure=$((total_failure + 1))
    continue
  fi

  # Determine success/failure based on log content
  if grep -q "exit status 0\|✅\|SUCCESS\|completed successfully" "$logfile" 2>/dev/null; then
    workflow_success["$workflow"]=$((${workflow_success[$workflow]:-0} + 1))
    job_success["$job"]=$((${job_success[$job]:-0} + 1))
    total_success=$((total_success + 1))
  else
    workflow_failure["$workflow"]=$((${workflow_failure[$workflow]:-0} + 1))
    job_failure["$job"]=$((${job_failure[$job]:-0} + 1))
    total_failure=$((total_failure + 1))

    # Extract failure patterns
    if grep -q "Error:" "$logfile" 2>/dev/null; then
      error_msg=$(grep "Error:" "$logfile" | head -1 | sed 's/.*Error: //;s/\[.*\].*//' | cut -d' ' -f1-5)
      failure_patterns["$error_msg"]=$((${failure_patterns[$error_msg]:-0} + 1))
    fi
  fi
done < <(tail -100 "$LOG_INDEX")

# Generate report
echo "Generating report..."
{
  echo "=== CI Reliability Metrics Report ==="
  echo "Generated: $(date)"
  echo "Data source: $LOG_INDEX (last 100 runs)"
  echo ""
  echo "=== Summary ==="
  echo "Total runs analyzed: $total_runs"
  echo "Total successful: $total_success"
  echo "Total failed: $total_failure"
  if [[ $total_runs -gt 0 ]]; then
    success_rate=$(echo "scale=2; ($total_success * 100) / $total_runs" | bc)
    echo "Overall success rate: ${success_rate}%"
  fi
  echo ""

  echo "=== Workflow Success Rates ==="
  for workflow in "${!workflow_total[@]}"; do
    total=${workflow_total[$workflow]}
    success=${workflow_success[$workflow]:-0}
    failure=${workflow_failure[$workflow]:-0}
    if [[ $total -gt 0 ]]; then
      rate=$(LC_ALL=C echo "scale=2; ($success * 100) / $total" | bc)
      printf "%-30s: %3d/%3d runs (%5.1f%%) | Success: %3d | Failed: %3d\n" \
        "$workflow" "$success" "$total" "$rate" "$success" "$failure"
    fi
  done | sort -k6 -nr
  echo ""

  echo "=== Job Success Rates ==="
  for job in "${!job_total[@]}"; do
    total=${job_total[$job]}
    success=${job_success[$job]:-0}
    failure=${job_failure[$job]:-0}
    if [[ $total -gt 0 ]]; then
      rate=$(LC_ALL=C echo "scale=2; ($success * 100) / $total" | bc)
      printf "%-35s: %3d/%3d runs (%5.1f%%) | Success: %3d | Failed: %3d\n" \
        "$job" "$success" "$total" "$rate" "$success" "$failure"
    fi
  done | sort -k6 -nr
  echo ""

  if [[ ${#failure_patterns[@]} -gt 0 ]]; then
    echo "=== Common Failure Patterns ==="
    for pattern in "${!failure_patterns[@]}"; do
      count=${failure_patterns[$pattern]}
      printf "%-60s: %3d occurrences\n" "$pattern" "$count"
    done | sort -k3 -nr
    echo ""
  fi
} > "$REPORT_FILE"

# Generate JSON output
{
  echo "{"
  echo "  \"generated\": \"$(date -Iseconds)\","
  echo "  \"total_runs\": $total_runs,"
  echo "  \"total_success\": $total_success,"
  echo "  "total_failure": $total_failure,"
  if [[ $total_runs -gt 0 ]]; then
    success_rate=$(echo "scale=2; ($total_success * 100) / $total_runs" | bc)
    echo "  \"success_rate\": $success_rate,"
  fi
  echo "  \"workflows\": {"
  first=true
  for workflow in "${!workflow_total[@]}"; do
    if [[ "$first" == "true" ]]; then
      first=false
    else
      echo ","
    fi
    total=${workflow_total[$workflow]}
    success=${workflow_success[$workflow]:-0}
    failure=${workflow_failure[$workflow]:-0}
    rate=$(echo "scale=2; ($success * 100) / $total" | bc)
    printf "    \"%s\": {\"total\": %d, \"success\": %d, \"failure\": %d, \"rate\": %s}" \
      "$workflow" "$total" "$success" "$failure" "$rate"
  done
  echo ""
  echo "  }"
  echo "}"
} > "$JSON_FILE"

echo "Report saved to: $REPORT_FILE"
echo "JSON metrics saved to: $JSON_FILE"
echo ""
echo "=== Summary ==="
cat "$REPORT_FILE" | head -20
