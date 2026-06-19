#!/usr/bin/env python3
"""
Production Readiness Check Script

This script performs comprehensive checks to verify that the AITBC system
is ready for production deployment. It checks secrets, dependencies,
service configuration, database connectivity, health endpoints, SSL/TLS,
monitoring setup, and backup configuration.

Usage:
    python scripts/check-production-readiness.py [--environment production|staging] [--verbose]

Exit codes:
    0: All checks passed
    1: Some checks failed
    2: Critical checks failed (cannot proceed)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


class ProductionReadinessChecker:
    """Comprehensive production readiness checker."""

    def __init__(self, environment: str = "production", verbose: bool = False):
        self.environment = environment
        self.verbose = verbose
        self.results: list[dict] = []
        self.project_root = Path(__file__).parent.parent
        self.errors = 0
        self.warnings = 0

    def log(self, message: str, level: str = "INFO"):
        """Log a message."""
        if self.verbose or level in ["ERROR", "WARN", "FAIL"]:
            print(f"[{level}] {message}")

    def add_result(self, category: str, check: str, passed: bool, message: str, critical: bool = False):
        """Add a check result."""
        self.results.append(
            {
                "category": category,
                "check": check,
                "passed": passed,
                "message": message,
                "critical": critical,
            }
        )
        if not passed:
            if critical:
                self.errors += 1
                self.log(f"CRITICAL: {check} - {message}", "FAIL")
            else:
                self.warnings += 1
                self.log(f"WARN: {check} - {message}", "WARN")
        else:
            self.log(f"PASS: {check} - {message}", "PASS")

    def check_secrets(self):
        """Check for secrets in code and configuration."""
        self.log("Checking secrets...", "INFO")

        # Check service files for plaintext secrets
        service_files = list(self.project_root.glob("apps/*/*.service"))
        found_secrets = False
        for service_file in service_files:
            # Skip miner service (not part of core services)
            if "miner" in service_file.name:
                continue
            content = service_file.read_text()
            if re.search(r'Environment=["\'].*(?:password|pass|secret|api_key|token)=', content, re.IGNORECASE):
                self.add_result(
                    "Secrets",
                    f"Service file {service_file.name}",
                    False,
                    "Contains plaintext secrets in Environment= lines",
                    critical=True,
                )
                found_secrets = True

        if not found_secrets:
            self.add_result("Secrets", "Service files", True, "No plaintext secrets in service files")

        # Check Python code for hardcoded defaults
        python_files = list(self.project_root.rglob("*.py"))
        found_defaults = False
        for py_file in python_files:
            # Skip test files, __pycache__, and venv directories
            if "test" in str(py_file) or "__pycache__" in str(py_file) or "venv" in str(py_file):
                continue
            content = py_file.read_text()
            if re.search(r'=["\'](?:training123|admin123|operator123|user123|password)["\']', content):
                self.add_result(
                    "Secrets",
                    f"Python file {py_file.relative_to(self.project_root)}",
                    False,
                    "Contains hardcoded default passwords",
                    critical=True,
                )
                found_defaults = True

        if not found_defaults:
            self.add_result("Secrets", "Python code", True, "No hardcoded default passwords")

        # Check .gitignore for .env files
        gitignore = self.project_root / ".gitignore"
        if gitignore.exists():
            gitignore_content = gitignore.read_text()
            if ".env" in gitignore_content:
                self.add_result("Secrets", ".gitignore", True, ".env files are ignored")
            else:
                self.add_result("Secrets", ".gitignore", False, ".env not in .gitignore", critical=True)
        else:
            self.add_result("Secrets", ".gitignore", False, ".gitignore not found", critical=True)

    def check_dependencies(self):
        """Check system and Python dependencies."""
        self.log("Checking dependencies...", "INFO")

        # Check Python version
        python_version = sys.version_info
        if python_version >= (3, 13):
            self.add_result("Dependencies", "Python version", True, f"Python {python_version.major}.{python_version.minor}")
        else:
            self.add_result(
                "Dependencies",
                "Python version",
                False,
                f"Python {python_version.major}.{python_version.minor} (requires 3.13+)",
                critical=True,
            )

        # Check for required system commands
        required_commands = ["git", "systemctl", "psql", "redis-cli"]
        for cmd in required_commands:
            try:
                subprocess.run(["which", cmd], check=True, capture_output=True, text=True)
                self.add_result("Dependencies", f"Command {cmd}", True, f"{cmd} is available")
            except subprocess.CalledProcessError:
                self.add_result("Dependencies", f"Command {cmd}", False, f"{cmd} not found in PATH", critical=True)

        # Check for pyproject.toml
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            self.add_result("Dependencies", "pyproject.toml", True, "pyproject.toml exists")
        else:
            self.add_result("Dependencies", "pyproject.toml", False, "pyproject.toml not found", critical=True)

    def check_service_configuration(self):
        """Check systemd service configuration."""
        self.log("Checking service configuration...", "INFO")

        service_files = [
            "apps/coordinator-api/aitbc-coordinator-api.service",
            "apps/agent-coordinator/aitbc-agent-coordinator.service",
            "apps/governance/aitbc-governance.service",
            "apps/blockchain-node/aitbc-blockchain-p2p.service",
        ]

        for service_path in service_files:
            service_file = self.project_root / service_path
            if service_file.exists():
                content = service_file.read_text()

                # Check for security directives
                has_security = any(
                    directive in content for directive in ["PrivateTmp", "NoNewPrivileges", "ProtectSystem", "ProtectHome"]
                )
                if has_security:
                    self.add_result("Services", f"{service_file.name} security", True, "Has security directives")
                else:
                    self.add_result(
                        "Services",
                        f"{service_file.name} security",
                        False,
                        "Missing security directives (PrivateTmp, NoNewPrivileges, etc.)",
                        critical=False,
                    )

                # Check for restart policy
                if "Restart=on-failure" in content:
                    self.add_result("Services", f"{service_file.name} restart policy", True, "Has Restart=on-failure")
                else:
                    self.add_result(
                        "Services", f"{service_file.name} restart policy", False, "Missing Restart=on-failure", critical=False
                    )
            else:
                self.add_result("Services", f"{service_file.name}", False, "Service file not found", critical=True)

    def check_database_connectivity(self):
        """Check database connectivity."""
        self.log("Checking database connectivity...", "INFO")

        # Check if PostgreSQL is running
        try:
            subprocess.run(["systemctl", "is-active", "postgresql"], check=True, capture_output=True, text=True)
            self.add_result("Database", "PostgreSQL service", True, "PostgreSQL is running")
        except subprocess.CalledProcessError:
            self.add_result("Database", "PostgreSQL service", False, "PostgreSQL is not running", critical=True)

        # Check if Redis is running
        try:
            subprocess.run(["systemctl", "is-active", "redis-server"], check=True, capture_output=True, text=True)
            self.add_result("Database", "Redis service", True, "Redis is running")
        except subprocess.CalledProcessError:
            self.add_result("Database", "Redis service", False, "Redis is not running", critical=True)

    def check_health_endpoints(self):
        """Check health endpoints."""
        self.log("Checking health endpoints...", "INFO")

        # Check if services are running
        services = [
            "aitbc-coordinator-api",
            "aitbc-agent-coordinator",
            "aitbc-governance",
            "aitbc-blockchain-p2p",
        ]

        for service in services:
            try:
                subprocess.run(["systemctl", "is-active", service], check=True, capture_output=True, text=True)
                self.add_result("Services", f"{service} status", True, f"{service} is running")
            except subprocess.CalledProcessError:
                # Only mark as critical if this is a production environment check
                critical = self.environment == "production"
                self.add_result("Services", f"{service} status", False, f"{service} is not running", critical=critical)

    def check_ssl_tls(self):
        """Check SSL/TLS configuration."""
        self.log("Checking SSL/TLS configuration...", "INFO")

        # Check for nginx
        try:
            subprocess.run(["which", "nginx"], check=True, capture_output=True, text=True)
            self.add_result("SSL/TLS", "nginx", True, "nginx is installed")

            # Check for SSL certificates
            cert_paths = ["/etc/ssl/certs/aitbc.crt", "/etc/letsencrypt/live/"]
            cert_found = False
            for cert_path in cert_paths:
                if os.path.exists(cert_path) or (os.path.isdir(cert_path) and os.listdir(cert_path)):
                    cert_found = True
                    break

            if cert_found:
                self.add_result("SSL/TLS", "SSL certificates", True, "SSL certificates found")
            else:
                # Only critical for production
                critical = self.environment == "production"
                self.add_result(
                    "SSL/TLS",
                    "SSL certificates",
                    False,
                    "No SSL certificates found (required for production)",
                    critical=critical,
                )
        except subprocess.CalledProcessError:
            self.add_result("SSL/TLS", "nginx", False, "nginx not installed", critical=True)

    def check_monitoring(self):
        """Check monitoring setup."""
        self.log("Checking monitoring setup...", "INFO")

        # Check for Prometheus
        try:
            subprocess.run(["which", "prometheus"], check=True, capture_output=True, text=True)
            self.add_result("Monitoring", "Prometheus", True, "Prometheus is installed")
        except subprocess.CalledProcessError:
            # Only critical for production
            critical = self.environment == "production"
            self.add_result("Monitoring", "Prometheus", False, "Prometheus not installed", critical=critical)

        # Check for Grafana
        try:
            subprocess.run(["which", "grafana-server"], check=True, capture_output=True, text=True)
            self.add_result("Monitoring", "Grafana", True, "Grafana is installed")
        except subprocess.CalledProcessError:
            # Only critical for production
            critical = self.environment == "production"
            self.add_result("Monitoring", "Grafana", False, "Grafana not installed", critical=critical)

        # Check for Prometheus metrics middleware in coordinator-api
        metrics_file = self.project_root / "aitbc/middleware/prometheus_metrics.py"
        if metrics_file.exists():
            self.add_result("Monitoring", "Prometheus metrics", True, "Prometheus metrics middleware exists")
        else:
            self.add_result(
                "Monitoring", "Prometheus metrics", False, "Prometheus metrics middleware not found", critical=False
            )

    def check_backups(self):
        """Check backup configuration."""
        self.log("Checking backup configuration...", "INFO")

        # Check for backup scripts
        backup_scripts = list(self.project_root.glob("scripts/*backup*"))
        if backup_scripts:
            self.add_result("Backups", "Backup scripts", True, f"Found {len(backup_scripts)} backup script(s)")
        else:
            # Only critical for production
            critical = self.environment == "production"
            self.add_result("Backups", "Backup scripts", False, "No backup scripts found", critical=critical)

        # Check for backup directory
        backup_dir = Path("/var/backups/aitbc")
        if backup_dir.exists():
            self.add_result("Backups", "Backup directory", True, f"Backup directory exists at {backup_dir}")
        else:
            # Only critical for production
            critical = self.environment == "production"
            self.add_result(
                "Backups", "Backup directory", False, f"Backup directory not found at {backup_dir}", critical=critical
            )

    def check_documentation(self):
        """Check documentation completeness."""
        self.log("Checking documentation...", "INFO")

        required_docs = [
            "docs/deployment/STAGING.md",
            "docs/deployment/DEPENDENCIES.md",
            "docs/operations/SECRETS.md",
            "docs/deployment/single-server.md",
        ]

        for doc_path in required_docs:
            doc_file = self.project_root / doc_path
            if doc_file.exists():
                self.add_result("Documentation", doc_path, True, "Documentation exists")
            else:
                self.add_result("Documentation", doc_path, False, "Documentation not found", critical=False)

    def run_all_checks(self):
        """Run all production readiness checks."""
        self.log(f"Starting production readiness checks for {self.environment} environment...", "INFO")
        self.log("=" * 60, "INFO")

        self.check_secrets()
        self.check_dependencies()
        self.check_service_configuration()
        self.check_database_connectivity()
        self.check_health_endpoints()
        self.check_ssl_tls()
        self.check_monitoring()
        self.check_backups()
        self.check_documentation()

        self.log("=" * 60, "INFO")
        self.log(f"Checks complete: {len(self.results)} total", "INFO")
        self.log(f"Errors: {self.errors}, Warnings: {self.warnings}", "INFO")

    def print_summary(self):
        """Print a summary of all checks."""
        print("\n" + "=" * 60)
        print("PRODUCTION READINESS SUMMARY")
        print("=" * 60)

        # Group by category
        categories = {}
        for result in self.results:
            category = result["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(result)

        for category, checks in categories.items():
            print(f"\n{category}:")
            for check in checks:
                status = "✓" if check["passed"] else ("✗" if check["critical"] else "⚠")
                print(f"  {status} {check['check']}: {check['message']}")

        print("\n" + "=" * 60)
        print(f"Total checks: {len(self.results)}")
        print(f"Passed: {len([r for r in self.results if r['passed']])}")
        print(f"Failed (critical): {self.errors}")
        print(f"Warnings: {self.warnings}")
        print("=" * 60)

        if self.errors > 0:
            print("\n❌ CRITICAL ISSUES FOUND - Cannot proceed to production")
            return 2
        elif self.warnings > 0:
            print("\n⚠️  WARNINGS FOUND - Review before production deployment")
            return 1
        else:
            print("\n✅ ALL CHECKS PASSED - Ready for production deployment")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Check production readiness for AITBC deployment")
    parser.add_argument(
        "--environment",
        choices=["production", "staging"],
        default="production",
        help="Target environment (default: production)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    checker = ProductionReadinessChecker(environment=args.environment, verbose=args.verbose)
    checker.run_all_checks()
    exit_code = checker.print_summary()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
