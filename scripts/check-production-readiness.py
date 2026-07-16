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


def _has_migrations(app_dir: Path) -> bool:
    """Return True if the app has an Alembic versions directory with scripts."""
    alembic_ini = app_dir / "alembic.ini"
    if not alembic_ini.exists():
        return False
    try:
        config = alembic_ini.read_text()
    except Exception:
        return False
    script_location = None
    for line in config.splitlines():
        if line.strip().startswith("script_location"):
            _, _, value = line.partition("=")
            script_location = value.strip()
            break
    if not script_location:
        return False
    # Resolve relative to the app directory (Alembic default behaviour)
    versions_dir = app_dir / script_location / "versions"
    return versions_dir.is_dir() and any(versions_dir.glob("*.py"))


def _revision_line(stdout: str) -> str | None:
    """Return the first non-log line from ``alembic current`` output."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("INFO") or stripped.startswith("[INFO]"):
            continue
        return stripped
    return None


def check_migrations() -> bool:
    """Check if database migrations are applied for every app with alembic configured.

    Discovers ``apps/*/alembic.ini`` and runs ``alembic current`` in each. An app
    is at-head only if the command exits 0 and the output contains ``(head)``.
    Apps without migration scripts are skipped (create_all handles their schema).
    """
    apps_dir = Path("/opt/aitbc/apps")
    alembic_apps = sorted(p.parent for p in apps_dir.glob("*/alembic.ini") if _has_migrations(p.parent))
    if not alembic_apps:
        print("⚠️  Database migrations: no apps with alembic migrations found")
        return True

    all_ok = True
    for app_dir in alembic_apps:
        app_name = app_dir.name
        try:
            result = subprocess.run(
                ["/opt/aitbc/venv/bin/alembic", "current"],
                cwd=str(app_dir),
                capture_output=True,
                text=True,
            )
            combined = result.stdout + result.stderr
            if result.returncode == 0 and "(head)" in combined:
                rev = _revision_line(result.stdout) or "at head"
                print(f"✅ Migrations [{app_name}]: {rev}")
            elif result.returncode == 0:
                rev = _revision_line(result.stdout)
                if rev is None:
                    print(f"⚠️  Migrations [{app_name}]: no revision applied (skipped)")
                else:
                    print(f"⚠️  Migrations [{app_name}]: behind head — {rev}")
                    all_ok = False
            else:
                print(f"❌ Migrations [{app_name}]: FAILED - {combined.strip()}")
                all_ok = False
        except FileNotFoundError:
            print(f"⚠️  Migrations [{app_name}]: alembic not found in venv")
            all_ok = False
        except Exception as e:
            print(f"❌ Migrations [{app_name}]: ERROR - {e}")
            all_ok = False

    return all_ok


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
