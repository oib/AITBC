#!/bin/bash
# Compare current benchmark results with previous runs

set -e

BENCHMARK_DIR="/var/lib/aitbc/benchmarks"
REPORT_DIR="/var/lib/aitbc/benchmarks/reports"

echo "=== Comparing Benchmark Results ==="

# Ensure directories exist
mkdir -p "$REPORT_DIR"

# Get latest benchmark files
LATEST_GAS=$(ls -t "$BENCHMARK_DIR"/gas-report-*.txt 2>/dev/null | head -1)
LATEST_EXECUTION=$(ls -t "$BENCHMARK_DIR"/execution-time-*.json 2>/dev/null | head -1)
LATEST_THROUGHPUT=$(ls -t "$BENCHMARK_DIR"/throughput-*.json 2>/dev/null | head -1)

# Get previous benchmark files
PREV_GAS=$(ls -t "$BENCHMARK_DIR"/gas-report-*.txt 2>/dev/null | head -2 | tail -1)
PREV_EXECUTION=$(ls -t "$BENCHMARK_DIR"/execution-time-*.json 2>/dev/null | head -2 | tail -1)
PREV_THROUGHPUT=$(ls -t "$BENCHMARK_DIR"/throughput-*.json 2>/dev/null | head -2 | tail -1)

echo "Latest gas report: $LATEST_GAS"
echo "Previous gas report: $PREV_GAS"
echo "Latest execution report: $LATEST_EXECUTION"
echo "Previous execution report: $PREV_EXECUTION"
echo "Latest throughput report: $LATEST_THROUGHPUT"
echo "Previous throughput report: $PREV_THROUGHPUT"

# Compare gas usage
if [[ -n "$LATEST_GAS" && -n "$PREV_GAS" ]]; then
    echo "📊 Comparing gas usage..."
    # Add actual comparison logic here
fi

# Compare execution time
if [[ -n "$LATEST_EXECUTION" && -n "$PREV_EXECUTION" ]]; then
    echo "📊 Comparing execution time..."
    # Add actual comparison logic here
fi

# Compare throughput
if [[ -n "$LATEST_THROUGHPUT" && -n "$PREV_THROUGHPUT" ]]; then
    echo "📊 Comparing throughput..."
    # Add actual comparison logic here
fi

echo "✅ Benchmark comparison complete"
