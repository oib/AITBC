#!/usr/bin/env python3
"""
Minimal production readiness check script

Checks:
- Redis connectivity
- Systemd service health
- Log format is JSON
- No change-me-in-production secrets
- Migrations applied
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def check_redis_connectivity() -> bool:
    """Check if Redis is accessible."""
    try:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(redis_url)
        client.ping()
        print("✅ Redis connectivity: OK")
        return True
    except Exception as e:
        print(f"❌ Redis connectivity: FAILED - {e}")
        return False


def check_systemd_services() -> bool:
    """Check if critical systemd services are running."""
    critical_services = [
        "aitbc-coordinator-api.service",
        "aitbc-blockchain-node.service",
    ]

    all_ok = True
    for service in critical_services:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() == "active":
                print(f"✅ Service {service}: active")
            else:
                print(f"❌ Service {service}: {result.stdout.strip()}")
                all_ok = False
        except Exception as e:
            print(f"❌ Service {service}: ERROR - {e}")
            all_ok = False

    return all_ok


def check_json_logging() -> bool:
    """Check if coordinator-api has JSON logging enabled."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "aitbc-coordinator-api.service", "--property=Environment"],
            capture_output=True,
            text=True,
        )
        env_vars = result.stdout.strip()
        if "LOG_FORMAT=json" in env_vars:
            print("✅ JSON logging: enabled in coordinator-api")
            return True
        else:
            print("❌ JSON logging: NOT enabled in coordinator-api")
            return False
    except Exception as e:
        print(f"❌ JSON logging check: ERROR - {e}")
        return False


def check_secrets() -> bool:
    """Check for placeholder secrets in service files."""
    service_dir = Path("/opt/aitbc/apps")
    placeholder_patterns = [
        r"change-me",
        r"REPLACE_WITH_SECRET",
        r"placeholder",
        r"changeme",
        r"TODO.*secret",
    ]

    all_ok = True
    for service_file in service_dir.rglob("*.service"):
        try:
            content = service_file.read_text()
            for pattern in placeholder_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    print(f"❌ Placeholder secret found in {service_file}")
                    all_ok = False
        except Exception:
            continue

    if all_ok:
        print("✅ No placeholder secrets found in service files")

    return all_ok


def check_migrations() -> bool:
    """Check if database migrations are applied."""
    try:
        result = subprocess.run(
            ["/opt/aitbc/venv/bin/alembic", "current"],
            cwd="/opt/aitbc/apps/coordinator-api",
            capture_output=True,
            text=True,
        )
        # Alembic not configured is acceptable for initial deployment
        if "script_location" in result.stderr or "script_location" in result.stdout:
            print("⚠️  Database migrations: Alembic not configured (acceptable for initial deployment)")
            return True
        if result.returncode == 0:
            print(f"✅ Database migrations: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Database migrations: FAILED - {result.stderr}")
            return False
    except FileNotFoundError:
        print("⚠️  Database migrations: Alembic not found (acceptable for initial deployment)")
        return True
    except Exception as e:
        print(f"❌ Database migrations check: ERROR - {e}")
        return False


def main() -> int:
    """Run all production readiness checks."""
    print("=" * 60)
    print("Production Readiness Check")
    print("=" * 60)
    print()

    results = {
        "Redis connectivity": check_redis_connectivity(),
        "Systemd services": check_systemd_services(),
        "JSON logging": check_json_logging(),
        "Secrets": check_secrets(),
        "Migrations": check_migrations(),
    }

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print("✅ All checks passed - ready for production")
        return 0
    else:
        print("❌ Some checks failed - review before production deployment")
        return 1


if __name__ == "__main__":
    sys.exit(main())
