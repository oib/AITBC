#!/usr/bin/env python3
"""
Quality Metrics Tracking System
Tracks bug escape rate, test flakiness, and code review coverage
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click


class QualityMetricsTracker:
    """Track and report quality metrics"""

    def __init__(self, metrics_file: str = "/var/log/aitbc/quality_metrics.json"):
        self.metrics_file = Path(metrics_file)
        self.metrics = self._load_metrics()

    def _load_metrics(self) -> dict[str, Any]:
        """Load existing metrics from file"""
        if self.metrics_file.exists():
            with open(self.metrics_file) as f:
                return json.load(f)
        return {
            "bug_escape_rate": {"total_bugs": 0, "escaped_bugs": 0, "rate": 0.0},
            "test_flakiness": {"total_runs": 0, "flaky_runs": 0, "rate": 0.0},
            "code_review_coverage": {"total_prs": 0, "reviewed_prs": 0, "rate": 0.0},
            "last_updated": None
        }

    def _save_metrics(self):
        """Save metrics to file"""
        self.metrics["last_updated"] = datetime.now().isoformat()
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)

    def record_bug(self, escaped: bool = False):
        """Record a bug (escaped or caught in testing)"""
        self.metrics["bug_escape_rate"]["total_bugs"] += 1
        if escaped:
            self.metrics["bug_escape_rate"]["escaped_bugs"] += 1
        self._calculate_bug_escape_rate()
        self._save_metrics()

    def _calculate_bug_escape_rate(self):
        """Calculate bug escape rate"""
        total = self.metrics["bug_escape_rate"]["total_bugs"]
        escaped = self.metrics["bug_escape_rate"]["escaped_bugs"]
        if total > 0:
            self.metrics["bug_escape_rate"]["rate"] = (escaped / total) * 100

    def record_test_run(self, flaky: bool = False):
        """Record a test run (flaky or stable)"""
        self.metrics["test_flakiness"]["total_runs"] += 1
        if flaky:
            self.metrics["test_flakiness"]["flaky_runs"] += 1
        self._calculate_test_flakiness()
        self._save_metrics()

    def _calculate_test_flakiness(self):
        """Calculate test flakiness rate"""
        total = self.metrics["test_flakiness"]["total_runs"]
        flaky = self.metrics["test_flakiness"]["flaky_runs"]
        if total > 0:
            self.metrics["test_flakiness"]["rate"] = (flaky / total) * 100

    def record_pr(self, reviewed: bool = False):
        """Record a PR (reviewed or not reviewed)"""
        self.metrics["code_review_coverage"]["total_prs"] += 1
        if reviewed:
            self.metrics["code_review_coverage"]["reviewed_prs"] += 1
        self._calculate_code_review_coverage()
        self._save_metrics()

    def _calculate_code_review_coverage(self):
        """Calculate code review coverage rate"""
        total = self.metrics["code_review_coverage"]["total_prs"]
        reviewed = self.metrics["code_review_coverage"]["reviewed_prs"]
        if total > 0:
            self.metrics["code_review_coverage"]["rate"] = (reviewed / total) * 100

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics"""
        return self.metrics

    def print_report(self):
        """Print a formatted metrics report"""
        click.echo("=" * 60)
        click.echo("Quality Metrics Report")
        click.echo("=" * 60)
        click.echo(f"Last Updated: {self.metrics['last_updated']}")
        click.echo()
        click.echo("Bug Escape Rate:")
        click.echo(f"  Total Bugs: {self.metrics['bug_escape_rate']['total_bugs']}")
        click.echo(f"  Escaped Bugs: {self.metrics['bug_escape_rate']['escaped_bugs']}")
        click.echo(f"  Escape Rate: {self.metrics['bug_escape_rate']['rate']:.2f}%")
        click.echo()
        click.echo("Test Flakiness:")
        click.echo(f"  Total Runs: {self.metrics['test_flakiness']['total_runs']}")
        click.echo(f"  Flaky Runs: {self.metrics['test_flakiness']['flaky_runs']}")
        click.echo(f"  Flakiness Rate: {self.metrics['test_flakiness']['rate']:.2f}%")
        click.echo()
        click.echo("Code Review Coverage:")
        click.echo(f"  Total PRs: {self.metrics['code_review_coverage']['total_prs']}")
        click.echo(f"  Reviewed PRs: {self.metrics['code_review_coverage']['reviewed_prs']}")
        click.echo(f"  Review Coverage: {self.metrics['code_review_coverage']['rate']:.2f}%")
        click.echo("=" * 60)


def main():
    """Main function for CLI usage"""
    import sys

    tracker = QualityMetricsTracker()

    if len(sys.argv) < 2:
        tracker.print_report()
        return

    command = sys.argv[1]

    if command == "bug":
        escaped = "--escaped" in sys.argv
        tracker.record_bug(escaped=escaped)
        click.echo(f"Recorded bug (escaped={escaped})")

    elif command == "test":
        flaky = "--flaky" in sys.argv
        tracker.record_test_run(flaky=flaky)
        click.echo(f"Recorded test run (flaky={flaky})")

    elif command == "pr":
        reviewed = "--reviewed" in sys.argv
        tracker.record_pr(reviewed=reviewed)
        click.echo(f"Recorded PR (reviewed={reviewed})")

    elif command == "report":
        tracker.print_report()

    else:
        click.echo(f"Unknown command: {command}")
        click.echo("Available commands: bug, test, pr, report")


if __name__ == "__main__":
    main()
