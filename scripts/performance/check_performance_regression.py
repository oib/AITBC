#!/usr/bin/env python3
"""
Performance regression check script

Compares current load test results against baseline and fails if
performance degrades beyond acceptable thresholds.
"""

import json
import sys
from pathlib import Path


# Baseline performance metrics (from v0.5.0)
BASELINE_METRICS = {
    "job_submit_p95_ms": 200,
    "heartbeat_p95_ms": 50,
    "health_check_p95_ms": 100,
    "list_jobs_p95_ms": 150,
    "list_miners_p95_ms": 150,
}

# Acceptable degradation threshold (20%)
DEGRADATION_THRESHOLD = 0.20


def parse_locust_stats(stats_file: Path) -> dict[str, float]:
    """Parse locust stats file and extract p95 latencies."""
    if not stats_file.exists():
        print(f"Stats file not found: {stats_file}")
        return {}

    with open(stats_file) as f:
        stats = json.load(f)

    p95_metrics = {}
    for entry in stats.get("stats", []):
        name = entry.get("name", "")
        p95 = entry.get("response_times_percentiles", {}).get("95", 0)

        # Map endpoint names to baseline keys
        if "training/jobs" in name or "job" in name.lower():
            p95_metrics["job_submit_p95_ms"] = p95
        elif "heartbeat" in name.lower():
            p95_metrics["heartbeat_p95_ms"] = p95
        elif "health" in name.lower():
            p95_metrics["health_check_p95_ms"] = p95
        elif "list" in name.lower() and "job" in name.lower():
            p95_metrics["list_jobs_p95_ms"] = p95
        elif "list" in name.lower() and "miner" in name.lower():
            p95_metrics["list_miners_p95_ms"] = p95

    return p95_metrics


def check_regression(current_metrics: dict[str, float]) -> tuple[bool, list[str]]:
    """Check if current metrics exceed degradation threshold."""
    regressions = []

    for metric_name, baseline_value in BASELINE_METRICS.items():
        current_value = current_metrics.get(metric_name, 0)

        if current_value == 0:
            continue  # Skip if metric not found

        degradation = (current_value - baseline_value) / baseline_value

        if degradation > DEGRADATION_THRESHOLD:
            regressions.append(
                f"{metric_name}: {current_value:.0f}ms (baseline: {baseline_value}ms, degradation: {degradation:.1%})"
            )

    return len(regressions) == 0, regressions


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        stats_file = Path(sys.argv[1])
    else:
        # Try to find locust stats file
        stats_file = Path("tests/load/locust_stats.json")

    if not stats_file.exists():
        print(f"Stats file not found: {stats_file}")
        print("Usage: python check_performance_regression.py <locust_stats.json>")
        sys.exit(1)

    current_metrics = parse_locust_stats(stats_file)

    if not current_metrics:
        print("No metrics found in stats file")
        sys.exit(1)

    print("Current Performance Metrics:")
    for metric_name, value in current_metrics.items():
        baseline = BASELINE_METRICS.get(metric_name, 0)
        if baseline > 0:
            degradation = (value - baseline) / baseline
            print(f"  {metric_name}: {value:.0f}ms (baseline: {baseline}ms, degradation: {degradation:.1%})")
        else:
            print(f"  {metric_name}: {value:.0f}ms (no baseline)")

    passed, regressions = check_regression(current_metrics)

    if passed:
        print("\n✅ Performance regression check passed")
        sys.exit(0)
    else:
        print("\n❌ Performance regression check failed")
        print("Regressions detected:")
        for regression in regressions:
            print(f"  - {regression}")
        sys.exit(1)


if __name__ == "__main__":
    main()
