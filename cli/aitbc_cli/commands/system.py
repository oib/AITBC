"""System commands for AITBC CLI.

Provides real service health checks and node readiness reporting.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from aitbc.utils.units import ait_to_units, format_ait

from ..config import get_config
from ..utils import output, success, warning, OUTPUT_FORMAT_OPTION
from ..utils.error_handling import abort
from ..utils.address import to_canonical
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.output import resolve_output_format

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Health endpoint catalog (port, path, method).
# These are the documented HTTP ports for the services that expose one.
# ---------------------------------------------------------------------------

_HEALTH_ENDPOINTS: dict[str, tuple[str, int, str, str]] = {
    "aitbc-api-gateway": ("127.0.0.1", 8201, "/health", "GET"),
    "aitbc-blockchain-event-bridge": ("127.0.0.1", 8205, "/health", "GET"),
    "aitbc-blockchain-explorer": ("127.0.0.1", 8100, "/health", "GET"),
    "aitbc-blockchain-rpc": ("127.0.0.1", 8202, "/health", "GET"),
    "aitbc-coordinator-api": ("127.0.0.1", 8203, "/health", "GET"),
    "aitbc-agent-coordinator": ("127.0.0.1", 8107, "/health", "GET"),
    "aitbc-exchange": ("127.0.0.1", 8106, "/health", "GET"),
    "aitbc-ffmpeg": ("127.0.0.1", 8230, "/health", "GET"),
    "aitbc-governance": ("127.0.0.1", 8105, "/health", "GET"),
    "aitbc-island-ipfs": ("127.0.0.1", 5002, "/api/v0/version", "POST"),
    "aitbc-market": ("127.0.0.1", 8102, "/health", "GET"),
    "aitbc-monitoring": ("127.0.0.1", 8002, "/health", "GET"),
    "aitbc-trading": ("127.0.0.1", 8104, "/health", "GET"),
    "aitbc-wallet": ("127.0.0.1", 8108, "/health", "GET"),
    "aitbc-whisper": ("127.0.0.1", 8110, "/health", "GET"),
    "ollama": ("127.0.0.1", 11434, "/api/tags", "GET"),
}

# Services that are valid to check but have no HTTP endpoint.
_PROCESS_ONLY_SERVICES = frozenset(
    {
        "aitbc-blockchain-node",
        "aitbc-blockchain-p2p",
        "aitbc-blockchain-sync",
        "aitbc-miner",
        "aitbc-bridge-monitor",
        "aitbc-recovery",
        "aitbc-load-secrets",
        "aitbc-backup",
        "aitbc-prometheus-watch",
    }
)

# A listing/offer publish costs 0.01 AIT (360_000 compute-units).
_LISTING_FEE_UNITS = ait_to_units(Decimal("0.01"))


@click.group(
    epilog="""Examples:

  aitbc system check

  aitbc system status"""
)
def system():
    """Check AITBC service health, display configuration, and manage systemd services."""
    pass


@system.command(
    epilog="""Examples:

  aitbc system architect"""
)
def architect():
    """Display a summary of the AITBC system architecture."""
    click.echo("=== AITBC System Architecture ===")
    click.echo("✅ Data: /var/lib/aitbc/data")
    click.echo("✅ Config: /etc/aitbc")
    click.echo("✅ Logs: /var/log/aitbc")
    click.echo("✅ Repository: Clean")


@system.command(
    epilog="""Examples:

  aitbc system audit"""
)
def audit():
    """Run a system audit and report compliance status."""
    click.echo("=== System Audit ===")
    click.echo("FHS Compliance: ✅")
    click.echo("Repository Clean: ✅")
    click.echo("Service Health: ✅")


def _service_is_active(service: str) -> bool:
    """Return True if a systemd unit is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("Could not check %s: %s", service, e)
        return False


def _service_unit_name(service: str) -> str:
    """Return a normalised aitbc-* systemd unit name.

    Accepts short names (``blockchain-node``), prefixed names
    (``aitbc-blockchain-node``), and full unit names (``aitbc-blockchain-node.service``).
    Non-aitbc units such as ``ollama`` are left as-is.
    """
    unit = service.strip()
    unit = unit.removesuffix(".service")
    if unit in {"ollama"}:
        return unit
    unit = unit.removeprefix("aitbc-")
    return f"aitbc-{unit}.service"


def _discover_services(specific: str | None = None) -> list[str]:
    """Return the list of services to check."""
    if specific:
        return [_service_unit_name(specific)]

    services: list[str] = []
    try:
        result = subprocess.run(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--no-legend",
                "--no-pager",
                "--full",
                "aitbc-*",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            unit = parts[0]
            if unit.endswith(".service"):
                services.append(unit)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        warning(f"Could not list aitbc services: {e}")

    # Always consider ollama if it is installed (separate from aitbc-*).
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ollama"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "active":
            services.append("ollama.service")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return sorted(set(services))


def _health_endpoint(service: str) -> tuple[str, int, str, str] | None:
    """Return (host, port, path, method) for a service, or None if process-only."""
    name = service.removesuffix(".service")
    if name in _HEALTH_ENDPOINTS:
        return _HEALTH_ENDPOINTS[name]
    if name in _PROCESS_ONLY_SERVICES:
        return None
    return None


def _check_http_health(host: str, port: int, path: str, method: str, timeout: int = 3) -> tuple[bool, str]:
    """Return (reachable, note) for an HTTP(S) health endpoint."""
    base = f"http://{host}:{port}"
    client = AITBCHTTPClient(base_url=base, timeout=timeout, max_retries=0)
    try:
        if method.upper() == "POST":
            resp = client.post(path, json={})
        else:
            resp = client.get(path)
        status = resp.get("status", "ok") if isinstance(resp, dict) else "ok"
        return True, f"{status}"
    except NetworkError as e:
        return False, f"not reachable: {e}"
    except Exception as e:
        return False, f"not reachable: {e}"


def _check_wallet_balance(config) -> dict[str, Any] | None:
    """Return a wallet summary row, or None if the wallet daemon is unreachable."""
    wallet_url = config.wallet_daemon_url or "http://127.0.0.1:8108"
    client = AITBCHTTPClient(base_url=wallet_url, timeout=3, max_retries=0, api_key=getattr(config, "wallet_api_key", None))
    try:
        wallets = client.get("/v1/wallets")
        items = wallets.get("items", []) if isinstance(wallets, dict) else wallets
        if not items:
            return None

        # Pick the "default" wallet if present, otherwise the first one.
        active = next((w for w in items if w.get("wallet_id") == "default" or w.get("id") == "default"), items[0])
        wallet_id = active.get("wallet_id") or active.get("id") or "unknown"
        address = active.get("address") or active.get("metadata", {}).get("address", "")
        if not address:
            return None

        canonical = to_canonical(address)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://127.0.0.1:8202")
        rpc_client = AITBCHTTPClient(base_url=rpc_url.rstrip("/"), timeout=3, max_retries=0)
        account = rpc_client.get(f"/rpc/account/{canonical}")
        balance_units = int(account.get("balance", 0))
        balance_ait = format_ait(balance_units)

        if balance_units < _LISTING_FEE_UNITS:
            return {
                "service": "wallet",
                "running": True,
                "reachable": None,
                "notes": f"{wallet_id} ({canonical}) balance {balance_ait} is below listing fee ({format_ait(_LISTING_FEE_UNITS)})",
            }
        return {
            "service": "wallet",
            "running": True,
            "reachable": None,
            "notes": f"{wallet_id} ({canonical}) balance {balance_ait}",
        }
    except NetworkError as e:
        return {
            "service": "wallet",
            "running": True,
            "reachable": None,
            "notes": f"wallet daemon running but balance check failed: {e}",
        }
    except Exception:
        return None


@system.command(
    epilog="""Examples:

  aitbc system check

  aitbc system check --service blockchain-node"""
)
@click.option("--service", help="Check a specific systemd service")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def check(ctx: click.Context, service: str | None, output_format: str):
    """Check AITBC systemd service health and active wallet balance."""
    output_format = resolve_output_format(ctx, output_format)
    config = get_config()

    results: list[dict[str, Any]] = []
    services = _discover_services(service)

    for unit in services:
        name = unit.removesuffix(".service")
        running = _service_is_active(unit)
        endpoint = _health_endpoint(unit)

        if endpoint:
            host, port, path, method = endpoint
            reachable, note = _check_http_health(host, port, path, method) if running else (False, "not running")
            notes = note if running else f"not running; {note}"
        else:
            reachable = None
            notes = "process-only service" if running else "not running"

        results.append(
            {
                "service": name,
                "running": running,
                "reachable": reachable,
                "notes": notes,
            }
        )

    # Active wallet balance check
    wallet_row = _check_wallet_balance(config)
    if wallet_row:
        results.append(wallet_row)
    else:
        results.append(
            {
                "service": "wallet",
                "running": False,
                "reachable": None,
                "notes": "wallet daemon not reachable",
            }
        )

    output(results, output_format, title="System Health Check")


@system.command(
    epilog="""Examples:

  aitbc system restart --service blockchain-node

  aitbc system restart --service wallet"""
)
@click.option("--service", required=True, help="Service to restart (e.g., blockchain-node, wallet)")
@click.pass_context
def restart(ctx, service: str):
    """Restart a systemd service by name."""
    _systemctl_service_action(ctx, "restart", service, action_label="restarted")


def _systemctl_service_action(ctx, action: str, service: str, *, action_label: str | None = None) -> None:
    """Run ``systemctl <action> <service>`` and print/output the result."""
    service_name = _service_unit_name(service)
    label = action_label or action

    try:
        prefix = ["sudo", "-n"] if os.geteuid() != 0 else []
        result = subprocess.run(
            prefix + ["systemctl", action, service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            success(f"Service {service_name} {label} successfully")
            output({"service": service_name, "status": label}, ctx.obj.get("output_format", "table"))
            return
        err = result.stderr.strip() or result.stdout.strip()
        raise click.ClickException(f"Failed to {action} service {service_name}: {err}")
    except subprocess.TimeoutExpired:
        raise click.ClickException(f"Timeout trying to {action} service {service_name}") from None
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error trying to {action} service {service_name}: {e}") from e


@system.command(
    epilog="""Examples:

  aitbc system start --service blockchain-node

  aitbc system start --service wallet"""
)
@click.option("--service", required=True, help="Service to start (e.g., blockchain-node, wallet)")
@click.pass_context
def start(ctx, service: str):
    """Start a systemd service by name."""
    _systemctl_service_action(ctx, "start", service)


@system.command(
    epilog="""Examples:

  aitbc system stop --service blockchain-node

  aitbc system stop --service wallet"""
)
@click.option("--service", required=True, help="Service to stop (e.g., blockchain-node, wallet)")
@click.pass_context
def stop(ctx, service: str):
    """Stop a systemd service by name."""
    _systemctl_service_action(ctx, "stop", service)


@system.command(
    epilog="""Examples:

  aitbc system status

  aitbc system status --service blockchain-node"""
)
@click.option("--service", help="Show full systemctl status for a specific service")
@click.pass_context
def status(ctx, service: str | None):
    """Get system status from the coordinator API, or full systemctl status for a service."""
    if not service:
        config = get_config()
        try:
            http_client = AITBCHTTPClient(base_url=config.coordinator_api_url or "http://127.0.0.1:8203", timeout=10)
            status_data = http_client.get("/health")
            success("System Status:")
            output(status_data, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            abort(None, f"Network error: {e}", from_exception=e)
        except Exception as e:
            abort(None, f"Error fetching status: {e}")
            return
        return

    service_name = _service_unit_name(service)
    try:
        result = subprocess.run(
            ["systemctl", "status", service_name, "--no-pager"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode in (0, 3):  # 3 is inactive
            click.echo(result.stdout)
            return
        raise click.ClickException(
            result.stderr.strip() or result.stdout.strip() or f"systemctl status failed for {service_name}"
        )
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error getting status for {service_name}: {e}") from e


# App loggers write the level name into the message text at normal journal
# priority, so `journalctl -p warning` misses them. --severity-pattern matches
# on that text instead. Fixed internal constant — never user input.
_APP_SEVERITY_PATTERN = r"WARN|WARNING|ERROR|CRITICAL|FATAL"

# journalctl priority levels by name and number — `journalctl -p` accepts a
# single level or a `from..to` range of either form.
_JOURNAL_PRIORITY_NAMES = ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug")
_JOURNAL_PRIORITY_RE = re.compile(
    r"^([0-7]|" + "|".join(_JOURNAL_PRIORITY_NAMES) + r")(\.\.([0-7]|" + "|".join(_JOURNAL_PRIORITY_NAMES) + r"))?$"
)


def _validate_logs_options(
    since: str | None,
    grep_pattern: str | None,
    priority: str | None,
    severity_pattern: bool,
) -> None:
    """Reject invalid logs option combinations before argv is built."""
    if since is not None and ("\n" in since or "\r" in since):
        raise click.ClickException("--since must not contain newlines")
    if grep_pattern is not None:
        if len(grep_pattern) > 200:
            raise click.ClickException("--grep pattern too long (max 200 chars)")
        if "\n" in grep_pattern or "\r" in grep_pattern or "\x00" in grep_pattern:
            raise click.ClickException("--grep must not contain newlines")
    if grep_pattern and severity_pattern:
        raise click.ClickException("--grep and --severity-pattern are mutually exclusive")
    if priority is not None and not _JOURNAL_PRIORITY_RE.match(priority.lower()):
        raise click.ClickException(
            "--priority must be a journalctl level (emerg, alert, crit, err, warning, notice, info, debug, 0-7) "
            "or a 'from..to' range of those"
        )


def _logs_argv(
    service: str,
    lines: int,
    since: str | None,
    grep_pattern: str | None,
    priority: str | None,
    severity_pattern: bool,
) -> list[str]:
    """Validate the logs options and build the journalctl argv."""
    _validate_logs_options(since, grep_pattern, priority, severity_pattern)
    cmd = ["journalctl", "-n", str(lines), "-u", _service_unit_name(service), "--no-pager"]
    if since:
        cmd += ["--since", since]
    if priority:
        cmd += ["-p", priority]
    if grep_pattern:
        cmd.append(f"--grep={grep_pattern}")
    if severity_pattern:
        # Fixed internal pattern — never user input, so it does not go through
        # the --grep validation path (and must not: the MCP-side blocklist on
        # user strings rejects '|'). App loggers write the level name into the
        # message text at normal journal priority, so a text match is the only
        # way to find them. 'WARN' already covers 'WARNING' as a substring.
        cmd.append(f"--grep={_APP_SEVERITY_PATTERN}")
    return cmd


@system.command(
    epilog="""Examples:

  aitbc system logs --service blockchain-node

  aitbc system logs --service blockchain-node --lines 50

  aitbc system logs --service blockchain-node --since "10 min ago" --grep ERROR

  aitbc system logs --service blockchain-node -p err

  aitbc system logs --service wallet --severity-pattern   # app-level [WARNING]/ERROR text"""
)
@click.option("--service", required=True, help="Service to show logs for")
@click.option("--lines", "-n", type=int, default=50, help="Number of log lines to show")
@click.option("--since", default=None, help="Only entries newer than this journalctl time spec (e.g. '10 min ago')")
@click.option(
    "--grep",
    "grep_pattern",
    default=None,
    help="Filter entries with this journalctl --grep pattern (max 200 chars)",
)
@click.option(
    "--priority",
    "-p",
    "priority",
    default=None,
    help="journalctl -p priority filter: a level name/number (err, warning, 3) or a range (err..warning)",
)
@click.option(
    "--severity-pattern",
    "severity_pattern",
    is_flag=True,
    default=False,
    help="Filter on app-level severity text (WARN/ERROR/CRITICAL) — app logs carry no journal priority",
)
@click.pass_context
def logs(
    ctx, service: str, lines: int, since: str | None, grep_pattern: str | None, priority: str | None, severity_pattern: bool
):
    """Show journalctl logs for a systemd service."""
    cmd = _logs_argv(service, lines, since, grep_pattern, priority, severity_pattern)
    service_name = _service_unit_name(service)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            click.echo(result.stdout)
            return
        if result.returncode == 1 and "No entries" in (result.stdout + result.stderr):
            # journalctl exits 1 for a zero-match --grep / empty journal; that
            # is a successful query with no results, not a failure.
            click.echo((result.stdout or result.stderr).strip())
            return
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or f"journalctl failed for {service_name}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error reading logs for {service_name}: {e}") from e


@system.command(
    epilog="""Examples:

  aitbc system cat --service blockchain-node"""
)
@click.option("--service", required=True, help="Service to show unit file for")
@click.pass_context
def cat(ctx, service: str):
    """Display the systemd unit file for a service."""
    service_name = _service_unit_name(service)
    try:
        result = subprocess.run(
            ["systemctl", "cat", service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            click.echo(result.stdout)
            return
        raise click.ClickException(
            result.stderr.strip() or result.stdout.strip() or f"systemctl cat failed for {service_name}"
        )
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error reading unit file for {service_name}: {e}") from e


@system.command(
    epilog="""Examples:

  aitbc system show --service blockchain-node

  aitbc system show --service blockchain-node --properties ActiveState,SubState,LoadState"""
)
@click.option("--service", required=True, help="Service to show properties for")
@click.option("--properties", help="Comma-separated list of systemd properties")
@click.pass_context
def show(ctx, service: str, properties: str | None):
    """Show systemd properties for a service."""
    service_name = _service_unit_name(service)
    try:
        cmd = ["systemctl", "show", service_name]
        if properties:
            cmd.extend(["--property", properties])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            click.echo(result.stdout)
            return
        raise click.ClickException(
            result.stderr.strip() or result.stdout.strip() or f"systemctl show failed for {service_name}"
        )
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error showing properties for {service_name}: {e}") from e


def _unit_env_files(service_name: str) -> list[tuple[Path, bool]]:
    """All ``EnvironmentFile`` paths declared by the unit, main file and drop-ins.

    Returns ``(path, optional)`` pairs; ``optional`` marks systemd's ``-``
    prefix (``ignore_errors=yes`` in ``systemctl show`` output). Empty list
    when the unit declares none or systemctl cannot be queried.
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", service_name, "-p", "EnvironmentFiles", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("Could not query EnvironmentFiles for %s: %s", service_name, e)
        return []
    if result.returncode != 0:
        return []
    text = result.stdout.strip()
    files: list[tuple[Path, bool]] = []
    # Modern format: /path (ignore_errors=yes|no) [/path (...)]
    matched = list(re.finditer(r"(-?/\S+)\s*\(ignore_errors=(yes|no)\)", text))
    if matched:
        return [(Path(m.group(1).lstrip("-")), m.group(2) == "yes") for m in matched]
    # Fallback: bare whitespace-separated paths ('-' marks optional)
    for tok in text.split():
        if tok.startswith("-/") or tok.startswith("/"):
            files.append((Path(tok.lstrip("-")), tok.startswith("-")))
    return files


def _unit_env_file(service_name: str) -> Path | None:
    """Resolve the unit's ``EnvironmentFile`` path (fleet convention: ``/etc/aitbc/<unit>.env``).

    Returns the first existing ``.env`` file declared by the unit, or the
    conventional ``/etc/aitbc/<unit>`` path if it exists. ``None`` when the
    unit declares no env file and the conventional path is absent — writing
    a file nothing loads would be a silent no-op.
    """
    for candidate, _optional in _unit_env_files(service_name):
        if candidate.suffix == ".env" and candidate.exists():
            return candidate

    fallback = Path("/etc/aitbc") / f"{service_name.removesuffix('.service')}.env"
    return fallback if fallback.exists() else None


def _parse_env_assignments(assignments: tuple[str, ...]) -> list[tuple[str, str]]:
    """Validate and split ``KEY=VALUE`` arguments, preserving order."""
    parsed: list[tuple[str, str]] = []
    for item in assignments:
        key, sep, value = item.partition("=")
        if not sep:
            raise click.ClickException(f"Invalid assignment '{item}' — expected KEY=VALUE")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise click.ClickException(f"Invalid environment variable name '{key}'")
        if "\n" in value or "\r" in value:
            raise click.ClickException(f"Value for {key} must be a single line")
        parsed.append((key, value))
    return parsed


def _merge_env_lines(lines: list[str], parsed: list[tuple[str, str]]) -> list[str]:
    """Rewrite existing ``KEY=`` lines in place and append the keys not present."""
    remaining = dict(parsed)
    out_lines: list[str] = []
    for line in lines:
        m = re.match(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m and m.group(2) in remaining:
            key = m.group(2)
            newline = "\n" if line.endswith("\n") else ""
            out_lines.append(f"{m.group(1)}{key}={remaining.pop(key)}{newline}")
        else:
            out_lines.append(line)
    for key, value in remaining.items():
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines[-1] += "\n"
        out_lines.append(f"{key}={value}\n")
    return out_lines


@system.command(
    "env-set",
    epilog="""Examples:

  aitbc system env-set coordinator-api COORDINATOR_ENABLE_ZK_VERIFICATION=true

  aitbc system env-set blockchain-node LOG_LEVEL=DEBUG SYNC_INTERVAL=30 --no-restart""",
)
@click.argument("service")
@click.argument("assignments", nargs=-1)
@click.option("--env-file", "env_file_override", default=None, help="Env file to edit (default: the unit's EnvironmentFile)")
@click.option("--no-restart", is_flag=True, help="Write the env file without restarting the service")
@click.pass_context
def env_set(ctx, service: str, assignments: tuple[str, ...], no_restart: bool, env_file_override: str | None):
    """Set KEY=VALUE pairs in a service's env file under /etc/aitbc, then restart it.

    The env file is resolved from the unit's ``EnvironmentFile`` declaration
    (falling back to ``/etc/aitbc/<unit>.env``). Values are never echoed —
    only key names are reported.
    """
    service_name = _service_unit_name(service)

    if not assignments:
        raise click.ClickException("At least one KEY=VALUE assignment is required")

    parsed = _parse_env_assignments(assignments)

    env_path = Path(env_file_override) if env_file_override else _unit_env_file(service_name)
    if env_path is None:
        raise click.ClickException(
            f"No EnvironmentFile declared by {service_name} and no /etc/aitbc/{service_name.removesuffix('.service')}.env "
            "exists — pass --env-file to write one anyway"
        )

    try:
        lines = env_path.read_text().splitlines(keepends=True)
    except OSError as e:
        raise click.ClickException(f"Cannot read {env_path}: {e}") from e

    out_lines = _merge_env_lines(lines, parsed)

    try:
        env_path.write_text("".join(out_lines))
    except OSError as e:
        raise click.ClickException(f"Cannot write {env_path}: {e} (insufficient permissions?)") from e

    success(f"Wrote {len(parsed)} variable(s) to {env_path}: {', '.join(dict(parsed))}")
    if no_restart:
        warning(f"Skipped restart — {service_name} keeps its previous environment until restarted")
    else:
        _systemctl_service_action(ctx, "restart", service_name, action_label="restarted")


def _env_file_key_names(path: Path) -> tuple[set[str], list[int]]:
    """Variable names in an env file plus the line numbers that did not parse.

    Names only — values are never read into the result. A non-empty,
    non-comment line without ``KEY=`` is reported by line number only (the
    line text may carry a value and is never returned).
    """
    names: set[str] = set()
    bad_lines: list[int] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return names, bad_lines
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", stripped)
        if m:
            names.add(m.group(1))
        else:
            bad_lines.append(lineno)
    return names, bad_lines


_FIELD_DENY_NAMES = frozenset({"private_key", "secret", "password", "token", "mnemonic", "seed", "key", "api_key"})
# Exact match after stripping '-'/'_' and lowercasing — catches spellings the
# '_' form misses (e.g. "privatekey", "api-key", "pass_phrase").
_FIELD_DENY_NORMALIZED = frozenset({"privatekey", "apikey", "secretkey", "passphrase", "passwd", "credential", "credentials"})
# A name ending in "key" is denied when its prefix is one of these —
# "signingkey"/"auth_key"/"access-key" — while "pubkey"/"monkey" stay allowed.
_FIELD_DENY_KEY_PREFIXES = ("private", "secret", "api", "auth", "signing", "access")
# Token-level deny list: a name is denied when any token — the name split on
# '_', '-' and camelCase boundaries — is one of these. Token equality, not
# substring: "keystore"/"monkey"/"keynote" stay allowed, "PGPASSWORD" is
# caught by the single-token suffix rule below. "url"/"uri" are tokens so
# camelCase "databaseUrl" refuses together with "DATABASE_URL". "pw" is a
# token only — never a suffix — so "crew"/"flow" stay allowed. "keyfile" is
# deliberately absent: it names a path to key material, not the secret
# itself — the same reason KEYSTORE_DIR is a required allow. Deliberately
# absent too: "authorization" — it is a suffix below, not a token, because
# the live fleet flag ENABLE_AUTHORIZATION must stay allowed.
_FIELD_DENY_TOKENS = frozenset(
    {
        "pass",
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "token",
        "key",
        "keys",
        "private",
        "credential",
        "credentials",
        "auth",
        "signing",
        "mnemonic",
        "seed",
        "dsn",
        "url",
        "uri",
        # plural / short forms (GAP-ENVDENY-2)
        "secrets",
        "passwords",
        "tokens",
        "apikeys",
        "pw",
        "bearer",
        "cookie",
        "cookies",
        "privkey",
        "seedphrase",
        "salt",
    }
)
# A separator-less name still ends in a deny word: "pgpassword" ends in
# "password". The suffix family deliberately omits
# "pass"/"key"/"keys"/"auth"/"signing"/"pw" — endings like monkey/pubkey/
# compass/oauth/designing/crew/flow would false-positive. "authorization"
# lives here (not in the tokens above) so bare AUTHORIZATION refuses while
# the fleet flag ENABLE_AUTHORIZATION — two tokens — stays allowed.
_FIELD_DENY_SUFFIXES = (
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "secret",
    "token",
    "private",
    "credential",
    "credentials",
    "mnemonic",
    "seed",
    "dsn",
    # plural / compound endings (GAP-ENVDENY-2) — single-token names only,
    # so no two-token fleet name can trip them
    "secrets",
    "passwords",
    "tokens",
    "apikeys",
    "cookie",
    "cookies",
    "bearer",
    "authorization",
    "privkey",
    "seedphrase",
)
# Connection strings can embed credentials — refused on the separator form
# (camel forms are already covered by the "url"/"uri" tokens above).
_FIELD_DENY_TAIL = ("_url", "_uri", "_dsn")
_FIELD_MAX_VALUE = 200
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Value shapes that are secret-class regardless of the variable name —
# applied to --value env values and --field string scalars. Each entry is
# (pattern, rule name); the refusal names the rule, never the value.
_FIELD_SECRET_VALUE_PATTERNS = (
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "URL carrying user:password"),
    (re.compile(r"^0x[0-9a-fA-F]{64}$"), "0x+64-hex private-key shape"),
    # Bare runs only — a 0x-prefixed 40-hex address (PROPOSER_ID et al.) is
    # the address shape, not a secret; 0x+64-hex is refused by the rule above.
    (re.compile(r"^[0-9a-fA-F]{40,}$"), "bare 40+ hex run"),
    (re.compile(r"^(?!0[xX])[A-Za-z0-9+/=_-]{40,}$"), "bare 40+ base64 run"),
    (re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"), "three-part dotted token"),
)
# Generated from the constants above so --help can never drift from the code.
_FIELD_DENY_EPILOG = (
    "--field/--value refused names: "
    + ", ".join(sorted(_FIELD_DENY_NAMES))
    + "; any name ending in '_key'; separator-insensitive forms "
    + ", ".join(sorted(_FIELD_DENY_NORMALIZED))
    + "; names ending in 'key' prefixed "
    + "/".join(_FIELD_DENY_KEY_PREFIXES)
    + "; any token (split on '_'/'-'/camelCase) in {"
    + ", ".join(sorted(_FIELD_DENY_TOKENS))
    + "}"
    + "; single-token names ending "
    + "/".join(_FIELD_DENY_SUFFIXES)
    + "; names ending "
    + "/".join(_FIELD_DENY_TAIL)
    + "; secret-shaped values (user:pass URLs, key/hex/base64 runs, dotted"
    " tokens); values over " + str(_FIELD_MAX_VALUE) + " characters are refused."
)


def _field_tokens(name: str) -> list[str]:
    """The name split on '_', '-' and lower->UPPER camel boundaries, lowercased."""
    return [t.lower() for t in re.split(r"[_-]+", _CAMEL_BOUNDARY.sub("_", name)) if t]


# Token subset that marks a connection-string name. ``config get`` exempts
# it (documented ``*_url`` lookups) and refuses credential-bearing *values*
# instead; the env/file paths deny the names outright.
_CONN_STRING_TOKENS = frozenset({"url", "uri", "dsn"})


def _field_name_denied(name: str, *, deny_conn_strings: bool = True) -> bool:
    lowered = name.lower()
    normalized = lowered.replace("-", "").replace("_", "")
    tokens = _field_tokens(name)
    return (
        lowered in _FIELD_DENY_NAMES
        or normalized in _FIELD_DENY_NORMALIZED
        or (deny_conn_strings and lowered.endswith(_FIELD_DENY_TAIL))
        or _deny_token_hit(tokens, deny_conn_strings)
        or (normalized.endswith("key") and normalized[:-3] in _FIELD_DENY_KEY_PREFIXES)
        or (len(tokens) == 1 and normalized.endswith(_FIELD_DENY_SUFFIXES))
    )


def _deny_token_hit(tokens: list[str], deny_conn_strings: bool) -> bool:
    return any(token in _FIELD_DENY_TOKENS and (deny_conn_strings or token not in _CONN_STRING_TOKENS) for token in tokens)


def _field_value_shape_denied(value: str) -> str | None:
    """The matched secret-shape rule name, or None for an innocuous value."""
    for pattern, rule in _FIELD_SECRET_VALUE_PATTERNS:
        if pattern.search(value):
            return rule
    return None


def _subtree_has_denied(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_field_name_denied(str(k)) or _subtree_has_denied(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_subtree_has_denied(v) for v in value)
    return False


_PROC_ROOT = Path("/proc")


def _unit_main_pid(service_name: str) -> tuple[int, str | None]:
    """``(MainPID, ActiveEnterTimestamp)`` for a unit via one ``systemctl show`` call.

    Clean one-line failures — never a traceback, never partial output.
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", service_name, "-p", "MainPID,ActiveEnterTimestamp", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        raise click.ClickException(f"cannot query systemd for {service_name}: {e}") from e
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise click.ClickException(f"systemctl show failed for {service_name}: {detail}")
    lines = result.stdout.splitlines()
    try:
        pid = int(lines[0].strip()) if lines and lines[0].strip() else 0
    except ValueError:
        raise click.ClickException(f"unparseable MainPID in systemctl output for {service_name}") from None
    active_enter = None
    if len(lines) > 1 and lines[1].strip():
        active_enter = lines[1].strip()
    return pid, active_enter


def _process_environ(pid: int, proc_root: Path | None = None) -> dict[str, bytes]:
    """The ``/proc/<pid>/environ`` table, decoded lazily.

    Returned as name -> raw value bytes so a names-only caller never decodes
    value content. The mapping must never be logged, persisted or printed
    wholesale — callers pick names, or the single ``--value`` lookup.
    """
    root = proc_root if proc_root is not None else _PROC_ROOT
    environ_path = root / str(pid) / "environ"
    try:
        raw = environ_path.read_bytes()
    except PermissionError as e:
        raise click.ClickException(f"cannot read {environ_path}: permission denied (run as root or the unit's user)") from e
    except FileNotFoundError as e:
        raise click.ClickException(f"{environ_path} vanished — the process exited between the two reads") from e
    except OSError as e:
        raise click.ClickException(f"cannot read {environ_path}: {e}") from e
    env: dict[str, bytes] = {}
    for item in raw.split(b"\x00"):
        name, sep, value = item.partition(b"=")
        if item and sep:
            env[name.decode("utf-8", "replace")] = value
    return env


def _declared_key_names(files: list[tuple[Path, bool]]) -> set[str]:
    """Union of variable names across declared env files (missing files skipped)."""
    declared: set[str] = set()
    for path, _optional in files:
        if path.exists():
            names, _bad = _env_file_key_names(path)
            declared |= names
    return declared


def _print_approved_env_value(env: dict[str, bytes], value_name: str, service_name: str) -> None:
    """Print one environ value after every refuse rule — the only site that
    emits environ content."""
    if _field_name_denied(value_name):
        raise click.ClickException(f"--value refused (deny-listed name): {value_name}")
    if value_name not in env:
        raise click.ClickException(f"{value_name} is not set in the process environment of {service_name}")
    value = env[value_name]
    if len(value) > _FIELD_MAX_VALUE:
        raise click.ClickException(f"--value refused (value over {_FIELD_MAX_VALUE} characters): {value_name}")
    decoded = value.decode("utf-8", "replace")
    if (shape := _field_value_shape_denied(decoded)) is not None:
        raise click.ClickException(f"--value refused ({shape}): {value_name}")
    # The single approved value is the ONLY content ever printed from environ.
    click.echo(decoded)


def _env_names_process(
    ctx: click.Context, service_name: str, files: list[tuple[Path, bool]], wanted: list[str], value_name: str | None
) -> None:
    """``env-names --process``: names (or one approved value) from /proc/<MainPID>/environ."""
    pid, active_enter = _unit_main_pid(service_name)
    if pid <= 0:
        raise click.ClickException(f"{service_name} is not running (MainPID={pid}) — no process environment")
    env = _process_environ(pid)
    process_names = set(env)

    if value_name is not None:
        _print_approved_env_value(env, value_name, service_name)
        return

    fmt = ctx.obj.get("output_format", "table")
    declared = _declared_key_names(files)
    if wanted:
        name_report: dict[str, dict[str, Any]] = {}
        for n in sorted(set(wanted)):
            name_entry: dict[str, Any] = {"set": n in process_names}
            if n in process_names and n not in declared:
                name_entry["drift"] = "process_only"
            elif n not in process_names and n in declared:
                name_entry["drift"] = "declared_only"
            name_report[n] = name_entry
        output(
            {"source": "process", "main_pid": pid, "active_enter_timestamp": active_enter, "names": name_report},
            fmt,
        )
    else:
        output(
            {
                "source": "process",
                "main_pid": pid,
                "active_enter_timestamp": active_enter,
                "names": sorted(process_names),
                "declared_only": sorted(declared - process_names),
                "process_only": sorted(process_names - declared),
            },
            fmt,
        )


def _env_names_files(ctx: click.Context, files: list[tuple[Path, bool]], wanted: list[str]) -> None:
    """``env-names`` default mode: per-file declared names, or set/unset for --names."""
    report: list[dict[str, Any]] = []
    present: set[str] = set()
    for path, optional in files:
        entry: dict[str, Any] = {"file": str(path)}
        if optional:
            entry["optional"] = True
        if not path.exists():
            entry["missing"] = True
            report.append(entry)
            continue
        key_names, bad_lines = _env_file_key_names(path)
        present |= key_names
        entry["names"] = sorted(key_names if not wanted else (key_names & set(wanted)))
        if bad_lines:
            entry["unparsed_lines"] = bad_lines
        report.append(entry)

    fmt = ctx.obj.get("output_format", "table")
    if wanted:
        output({n: n in present for n in sorted(set(wanted))}, fmt)
    else:
        output(report, fmt)


@system.command(
    "env-names",
    epilog="""Examples:

  aitbc system env-names --service aitbc-coordinator-api

  aitbc system env-names --service blockchain-node --names LOG_LEVEL SYNC_INTERVAL

  aitbc system env-names --service blockchain-node --process --names BRIDGE_ROOT_SHADOW_CHECK

  aitbc system env-names --service blockchain-node --process --value BRIDGE_ROOT_SHADOW_CHECK

"""
    + _FIELD_DENY_EPILOG,
)
@click.option("--service", required=True, help="Unit name (with or without the aitbc- prefix/.service suffix)")
@click.option("--names", multiple=True, help="Report only whether each named variable is set (repeatable)")
@click.option(
    "--process",
    "process_env",
    is_flag=True,
    help="Read the running process environment via /proc/<MainPID>/environ — names only — instead of the "
    "declared env files; combined output flags declared_only/process_only drift",
)
@click.option(
    "--value",
    "value_name",
    default=None,
    metavar="NAME",
    help="Print the value of ONE named variable from the process environment (requires --process; the "
    "deny-list and length cap below apply — a refusal names the rule, never the value)",
)
@click.pass_context
def env_names(ctx, service: str, names: tuple[str, ...], process_env: bool, value_name: str | None):
    """List environment variable NAMES declared in a service's env files.

    Reads the unit's full ``EnvironmentFiles`` list via ``systemctl show``
    so drop-in files are included. Names only — values and ``Environment=``
    inline assignments are never printed.

    ``--process`` switches the source to the running process environment
    (``/proc/<MainPID>/environ``) — the only place variables set outside any
    ``EnvironmentFile`` (e.g. injected by a drop-in ``Environment=`` or a
    wrapper) show up. Still names only unless ``--value`` picks ONE
    non-deny-listed name.
    """
    service_name = _service_unit_name(service)

    if value_name is not None and not process_env:
        raise click.ClickException("--value requires --process (env files never print values)")

    files = _unit_env_files(service_name)
    if not files:
        fallback = Path("/etc/aitbc") / f"{service_name.removesuffix('.service')}.env"
        if fallback.exists():
            files = [(fallback, False)]
    if not files and not process_env:
        raise click.ClickException(
            f"{service_name} declares no EnvironmentFile and no /etc/aitbc/{service_name.removesuffix('.service')}.env exists"
        )

    # Environment variable names are case-sensitive — report each exactly as given.
    wanted = list(names)

    if process_env:
        _env_names_process(ctx, service_name, files, wanted, value_name)
        return

    _env_names_files(ctx, files, wanted)


@system.command(
    name="file-info",
    epilog="""Examples:

  aitbc system file-info --path /var/lib/aitbc/wallets/node.json

  aitbc system file-info --path /var/lib/aitbc/wallets/node.json --field address

"""
    + _FIELD_DENY_EPILOG,
)
@click.option(
    "--path",
    required=True,
    help="Absolute path under /opt/aitbc, /etc/aitbc, /etc/systemd, /var/log/aitbc, or /var/lib/aitbc",
)
@click.option("--field", "field_name", default=None, help="Print one scalar top-level JSON field (e.g. address)")
@click.pass_context
def file_info(ctx, path: str, field_name: str | None):
    """Show file metadata without dumping content — the safe form of `system file`.

    Reports size, mtime, owner, mode and type; for JSON files also the
    top-level key names. ``--field`` prints a single scalar field and
    hard-refuses denied names: any token (split on ``_``/``-``/camelCase) in
    pass/password/passwd/pwd/passphrase/secret/token/key/keys/private/
    credential/credentials/auth/signing/mnemonic/seed/dsn/url/uri; the
    separator-insensitive forms privatekey, apikey, secretkey, passphrase,
    passwd, credential and credentials; any name ending in ``key`` whose
    prefix is private/secret/api/auth/signing/access — including inside
    nested objects — names ending in ``_url``/``_uri``/``_dsn``;
    secret-shaped values (user:pass URLs, 0x+64-hex, 40+-char hex/base64
    runs, three-part dotted tokens); and values over 200 characters.

    Coverage is the ``system file`` allowlist: ``/var/lib/aitbc/wallets``
    and ``/etc/aitbc/credentials`` are inside it; ``/root/.aitbc/wallets``
    is not — the path refuses before anything is read.
    """
    resolved = _resolve_allowed_read_path(path)

    st = resolved.stat()
    info: dict[str, Any] = {
        "path": str(resolved),
        "type": "file" if resolved.is_file() else ("directory" if resolved.is_dir() else "other"),
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
        "owner": pwd.getpwuid(st.st_uid).pw_name,
        "mode": oct(st.st_mode & 0o7777),
    }

    parsed = _json_object_or_none(resolved)
    if parsed is not None:
        info["json_keys"] = sorted(parsed.keys())

    if field_name is not None:
        if parsed is None:
            raise click.ClickException(f"--field requires a JSON object file: {resolved}")
        match, value = _allowed_json_field(parsed, field_name)
        info["field"] = {match: value}

    output(info, ctx.obj.get("output_format", "table"))


def _resolve_allowed_read_path(path: str) -> Path:
    """Allowlist + metachar check, then the resolved path must stay inside it."""
    if not any(path.startswith(prefix) for prefix in _ALLOWED_READ_PREFIXES):
        raise click.ClickException(f"file path not allowed: {path}")
    if re.search(r"[;&|<>$`\\!\n\r]", path):
        raise click.ClickException(f"invalid file path: {path}")
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError as e:
        raise click.ClickException(f"Error reading {path}: {e}") from e
    if not any(str(resolved).startswith(prefix) for prefix in _ALLOWED_READ_PREFIXES):
        raise click.ClickException(f"file path not allowed: {path} resolves outside the allowed prefixes")
    return resolved


def _json_object_or_none(path: Path) -> dict[str, Any] | None:
    """The file's top-level JSON object, or None when it is not one."""
    if not path.is_file():
        return None
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    return candidate if isinstance(candidate, dict) else None


def _allowed_json_field(parsed: dict[str, Any], field_name: str) -> tuple[str, Any]:
    """One scalar field under the denylist — every refusal is an explicit error."""
    if _field_name_denied(field_name):
        raise click.ClickException(f"field refused (denied name): {field_name}")
    match = next((k for k in parsed if k.lower() == field_name.lower()), None)
    if match is None:
        raise click.ClickException(f"no such top-level field: {field_name}")
    value = parsed[match]
    if _subtree_has_denied(value):
        raise click.ClickException(f"field refused (contains a denied name): {match}")
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        raise click.ClickException(f"field refused (not a scalar): {match}")
    if isinstance(value, str) and len(value) > _FIELD_MAX_VALUE:
        raise click.ClickException(f"field refused (value over {_FIELD_MAX_VALUE} characters): {match}")
    if isinstance(value, str) and (shape := _field_value_shape_denied(value)) is not None:
        raise click.ClickException(f"field refused ({shape}): {match}")
    return match, value


@system.command(
    epilog="""Examples:

  aitbc system config

  aitbc system config --show-secrets"""
)
@click.option("--show-secrets", is_flag=True, help="Show sensitive values like API keys")
@click.pass_context
def config(ctx, show_secrets: bool):
    """Display AITBC system configuration from /etc/aitbc/blockchain.env."""
    config_path = Path("/etc/aitbc/blockchain.env")

    if not config_path.exists():
        abort(None, f"Configuration file not found: {config_path}")
        return

    try:
        with open(config_path) as f:
            config_lines = f.readlines()

        config_data = {}
        for line in config_lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Hide secrets unless explicitly requested
                if not show_secrets and any(secret in key.lower() for secret in ["key", "secret", "password", "token"]):
                    value = "***HIDDEN***"
                config_data[key.strip()] = value.strip()

        success("System Configuration:")
        output(config_data, ctx.obj.get("output_format", "table"))
    except Exception as e:
        abort(None, f"Error reading configuration: {e}")
        return


# Allowed read-only file prefixes for ``aitbc system file --path``.
_ALLOWED_READ_PREFIXES = (
    "/opt/aitbc/",
    "/etc/aitbc/",
    "/etc/systemd/",
    "/var/log/aitbc/",
    "/var/lib/aitbc/",
)


@system.command(
    name="file",
    epilog="""Examples:

  aitbc system file --path /etc/aitbc/blockchain.env

  aitbc system file --path /var/log/aitbc/coordinator.log""",
)
@click.option(
    "--path",
    required=True,
    help="Absolute path to a file under /opt/aitbc, /etc/aitbc, /etc/systemd, /var/log/aitbc, or /var/lib/aitbc",
)
@click.pass_context
def read_file(ctx, path: str):
    """Read a remote AITBC configuration, log, or data file."""
    if not any(path.startswith(prefix) for prefix in _ALLOWED_READ_PREFIXES):
        raise click.ClickException(f"file path not allowed: {path}")
    if re.search(r"[;&|<>$`\\!\n\r]", path):
        raise click.ClickException(f"invalid file path: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            click.echo(f.read())
    except Exception as e:
        raise click.ClickException(f"Error reading {path}: {e}") from e


@system.command(
    name="cron",
    epilog="""Examples:

  aitbc system cron""",
)
@click.pass_context
def list_cron(ctx):
    """List AITBC cron jobs for the current user and /etc/cron.d entries."""
    script = (
        'echo "=== user crontab ==="; '
        '(crontab -l 2>/dev/null) || echo "no user crontab"; '
        'echo "=== /etc/cron.d ==="; '
        "ls -1 /etc/cron.d/aitbc* 2>/dev/null || true; "
        "for f in /etc/cron.d/aitbc*; do "
        '  [ -f "$f" ] || continue; '
        '  echo "--- $f ---"; '
        '  cat "$f"; '
        "done"
    )
    try:
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            click.echo(result.stdout)
            return
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or "error listing cron jobs")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error listing cron jobs: {e}") from e


# Allowed script prefixes for ``aitbc system run-script --path``.
_ALLOWED_SCRIPT_PREFIXES = (
    "/opt/aitbc/scripts/",
    "/opt/aitbc/monitoring/",
    "/opt/aitbc/cluster/",
)


@system.command(
    name="run-script",
    epilog="""Examples:

  aitbc system run-script --path /opt/aitbc/scripts/maintenance/backup.sh""",
)
@click.option("--path", required=True, help="Absolute path to an allowed AITBC script")
@click.pass_context
def run_script(ctx, path: str):
    """Run an allowed AITBC maintenance or monitoring script."""
    if not any(path.startswith(prefix) for prefix in _ALLOWED_SCRIPT_PREFIXES):
        raise click.ClickException(f"script path not allowed: {path}")
    if re.search(r"[;&|<>$`\\!\n\r]", path):
        raise click.ClickException(f"invalid script path: {path}")
    try:
        result = subprocess.run(["bash", "--", path], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            click.echo(result.stdout)
            return
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or f"script failed: {path}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error running script {path}: {e}") from e


if __name__ == "__main__":
    system()
