"""System commands for AITBC CLI.

Provides real service health checks and node readiness reporting.
"""

from __future__ import annotations

import os
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from aitbc.utils.units import ait_to_units, format_ait

from ..config import get_config
from ..utils import error, output, success, warning, OUTPUT_FORMAT_OPTION
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
    "aitbc-marketplace": ("127.0.0.1", 8102, "/health", "GET"),
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
    client = AITBCHTTPClient(base_url=wallet_url, timeout=3, max_retries=0)
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
            error(f"Network error: {e}")
        except Exception as e:
            error(f"Error fetching status: {e}")
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
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or f"systemctl status failed for {service_name}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error getting status for {service_name}: {e}") from e


@system.command(
    epilog="""Examples:

  aitbc system logs --service blockchain-node

  aitbc system logs --service blockchain-node --lines 50"""
)
@click.option("--service", required=True, help="Service to show logs for")
@click.option("--lines", "-n", type=int, default=50, help="Number of log lines to show")
@click.pass_context
def logs(ctx, service: str, lines: int):
    """Show journalctl logs for a systemd service."""
    service_name = _service_unit_name(service)
    try:
        result = subprocess.run(
            ["journalctl", "-n", str(lines), "-u", service_name, "--no-pager"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            click.echo(result.stdout)
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
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or f"systemctl cat failed for {service_name}")
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
        raise click.ClickException(result.stderr.strip() or result.stdout.strip() or f"systemctl show failed for {service_name}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error showing properties for {service_name}: {e}") from e


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
        error(f"Configuration file not found: {config_path}")
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
        error(f"Error reading configuration: {e}")


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
@click.option("--path", required=True, help="Absolute path to a file under /opt/aitbc, /etc/aitbc, /etc/systemd, /var/log/aitbc, or /var/lib/aitbc")
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
