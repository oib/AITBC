#!/usr/bin/env python3
"""
Minimal production readiness check script

Checks:
- Redis connectivity
- Systemd service health
- No change-me-in-production secrets
- Migrations applied
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/opt/aitbc")
APPS_DIR = REPO_ROOT / "apps"
ALEMBIC_BIN = REPO_ROOT / "venv" / "bin" / "alembic"

# Service environment files. `run-migrations.sh` reads the same two names in the same
# order; the two must agree, or the check answers for a different database than the one
# the deploy migrates.
ETC_AITBC = Path("/etc/aitbc")


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


def _script_location(alembic_ini: Path) -> Path | None:
    """Resolve ``script_location`` from an alembic.ini to a directory.

    ``%(here)s`` is Alembic's own interpolation for the directory holding the ini file, and
    expanding it is not optional. Taken literally it builds
    ``apps/blockchain-node/%(here)s/migrations/versions``, which is not a directory, so
    ``_has_migrations`` returned False and blockchain-node — seven migrations, and the app
    whose deployed database was found with no ``alembic_version`` table at all (V23-49) —
    was dropped from this check without appearing in its output (V23-79).
    """
    try:
        config = alembic_ini.read_text()
    except OSError:
        return None
    for line in config.splitlines():
        if not line.strip().startswith("script_location"):
            continue
        _, _, value = line.partition("=")
        value = value.strip().replace("%(here)s", str(alembic_ini.parent))
        if not value:
            return None
        # Alembic resolves a relative script_location against the ini file's directory.
        return Path(value) if Path(value).is_absolute() else alembic_ini.parent / value
    return None


def _has_migrations(app_dir: Path) -> bool:
    """Return True if the app has an Alembic versions directory with scripts."""
    alembic_ini = app_dir / "alembic.ini"
    if not alembic_ini.exists():
        return False
    location = _script_location(alembic_ini)
    if location is None:
        return False
    versions_dir = location / "versions"
    return versions_dir.is_dir() and any(versions_dir.glob("*.py"))


# systemd's ``EnvironmentFile=`` grammar, not the shell's: these files are read by systemd,
# so its rules are the authoritative ones. Blank lines and `#` comments are skipped, an
# optional `export` prefix is tolerated, and a value may be wrapped in matching quotes.
# Parsing rather than sourcing also means nothing in these files is executed by this check.
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a service env file into a dict. Values are never printed — these hold secrets."""
    env: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return env
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ENV_ASSIGNMENT.match(line)
        if match is None:
            continue
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key] = value
    return env


def _service_env(app_name: str) -> tuple[dict[str, str], Path | None]:
    """Return the service's own environment, which is where its ``DATABASE_URL`` lives.

    Without it every ``env.py`` in the tree falls back to its own default target, and those
    defaults are not the deployed databases: coordinator-api's is a local SQLite file while
    the service runs on Postgres, and pool-hub's is a hardcoded ``localhost`` DSN. This
    check ran with no service environment at all, so it reported confidently on databases
    nothing uses (V23-79). ``run-migrations.sh`` reads the same two filenames in the same
    order — that is what makes the two agree on which database a service has.
    """
    for candidate in (ETC_AITBC / f"aitbc-{app_name}.env", ETC_AITBC / f"{app_name}.env"):
        if candidate.is_file():
            return _read_env_file(candidate), candidate
    return {}, None


def _alembic(app_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic in an app directory, under that service's own environment."""
    env = dict(os.environ)
    # An ambient DATABASE_URL belongs to whoever exported it, not to this service. Dropping
    # it first is the same precaution run-migrations.sh takes between services: one leaking
    # in points `current` at another service's database and the answer looks plausible.
    env.pop("DATABASE_URL", None)
    env.pop("SQLITE_URL", None)
    service_env, _ = _service_env(app_dir.name)
    env.update(service_env)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(REPO_ROOT), str(app_dir / "src"), os.environ.get("PYTHONPATH", "")) if p
    )
    return subprocess.run(
        [str(ALEMBIC_BIN), *args],
        cwd=str(app_dir),
        capture_output=True,
        text=True,
        env=env,
    )


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
    """Check that every Alembic-managed app's database is at head.

    Runs ``alembic current`` per app, in that app's own environment, and reports the head it
    was measured against. Three states fail: the command errors, the database has no
    ``alembic_version`` table at all, or it has one that is behind head.

    **The middle state used to pass.** ``alembic current`` against a database that has never
    been migrated exits 0 and prints nothing to stdout, and this reported that as "no
    revision applied (skipped)" while leaving the result untouched — so the worst state a
    database can be in was the one state treated as acceptable, and being a single revision
    behind was not. gpu, edge and pool-hub are all in that state on the hub today, which is
    why this check passed them while they had no schema under Alembic control at all
    (V23-79).
    """
    alembic_apps = sorted(p.parent for p in APPS_DIR.glob("*/alembic.ini") if _has_migrations(p.parent))
    if not alembic_apps:
        print("⚠️  Database migrations: no apps with alembic migrations found")
        return True

    if not ALEMBIC_BIN.exists():
        print(f"❌ Database migrations: alembic not found at {ALEMBIC_BIN}")
        return False

    all_ok = True
    for app_dir in alembic_apps:
        app_name = app_dir.name
        try:
            heads = _alembic(app_dir, "heads")
            expected = _revision_line(heads.stdout) if heads.returncode == 0 else None
            against = f" (head: {expected})" if expected else ""

            result = _alembic(app_dir, "current")
            combined = (result.stdout + result.stderr).strip()

            if result.returncode != 0:
                print(f"❌ Migrations [{app_name}]: FAILED - {combined}")
                all_ok = False
                continue

            rev = _revision_line(result.stdout)
            if rev is None:
                print(f"❌ Migrations [{app_name}]: never migrated — no alembic_version table{against}")
                all_ok = False
            elif "(head)" in rev:
                print(f"✅ Migrations [{app_name}]: {rev}")
            else:
                print(f"❌ Migrations [{app_name}]: behind head — {rev}{against}")
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
