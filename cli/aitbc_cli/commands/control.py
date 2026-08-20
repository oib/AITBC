#!/usr/bin/env python3
"""Role-aware service control commands.

Provides ``aitbc start``, ``aitbc stop`` and ``aitbc restart`` that
act on the systemd units configured for the local node role (or an
explicitly requested role).
"""

import os
import subprocess
from typing import Optional

import click

from ..utils import error, output, success, warning
from ..utils.http_client import get_logger

logger = get_logger(__name__)

HEALTH_CHECK_SCRIPT = "/opt/aitbc/scripts/monitoring/health_check.sh"


def _role_env(role: Optional[str]) -> dict:
    """Build an environment that pins the requested role for health_check.sh.

    The script ``scripts/monitoring/health_check.sh`` treats process
    environment values as authoritative after sourcing the deployment files,
    so we can force a specific role by setting the right variables.
    """
    env = os.environ.copy()
    if not role:
        return env
    if role == "hub":
        env["BLOCKCHAIN_MODE"] = "hub"
        env.pop("MARKET_ROLE", None)
        env.pop("HARDWARE_PROFILE", None)
    elif role == "shop":
        env["BLOCKCHAIN_MODE"] = "shop"
        env["MARKET_ROLE"] = "shop"
        env["HARDWARE_PROFILE"] = "gpu"
    elif role == "customer":
        env["BLOCKCHAIN_MODE"] = "customer"
        env["MARKET_ROLE"] = "customer"
        env["HARDWARE_PROFILE"] = "nogpu"
    else:
        # follower: set non-hub, non-shop, non-customer values
        env["BLOCKCHAIN_MODE"] = "follower"
        env["MARKET_ROLE"] = "follower"
        env["HARDWARE_PROFILE"] = "nogpu"
    return env


def _role_services(role: Optional[str]) -> list:
    """Resolve the systemd units for the given or detected role."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {HEALTH_CHECK_SCRIPT} >/dev/null 2>&1 "
            '&& printf "%s\\n" "${ROLE_SERVICES[@]}"',
        ],
        capture_output=True,
        text=True,
        env=_role_env(role),
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to resolve role services: {result.stderr.strip()}")
    services = [s for s in result.stdout.splitlines() if s]
    if not services:
        raise RuntimeError("No role services found")
    return services


def _systemctl_prefix() -> list:
    """Return a sudo prefix when not already running as root."""
    if os.geteuid() == 0:
        return []
    return ["sudo", "-n"]


def _control_services(
    ctx,
    action: str,
    role: Optional[str],
    dry_run: bool,
):
    """Run ``systemctl <action>`` for each unit of the selected role."""
    try:
        services = _role_services(role)
    except RuntimeError as e:
        error(str(e))
        return 1

    prefix = _systemctl_prefix()
    if not prefix:
        logger.debug("Running systemctl as root")
    else:
        logger.debug("Using %s for systemctl", " ".join(prefix))

    results = []
    overall_ok = True

    for svc in services:
        cmd = prefix + ["systemctl", action, svc]
        if dry_run:
            click.echo(f"would run: {' '.join(cmd)}")
            results.append({"service": svc, "action": action, "status": "dry-run"})
            continue

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = res.returncode == 0
        if ok:
            success(f"{action} {svc}: OK")
        else:
            overall_ok = False
            err = res.stderr.strip() or res.stdout.strip()
            error(f"{action} {svc} failed: {err}")
        results.append({
            "service": svc,
            "action": action,
            "status": "ok" if ok else "failed",
            "message": res.stderr.strip() if not ok else res.stdout.strip(),
        })

    output(
        {"role": role or "auto", "action": action, "services": results},
        format=ctx.obj.get("output_format", "table"),
        title=f"{action.title()} role services",
    )

    if not overall_ok and not dry_run:
        return 1
    return 0


def _common_options(func):
    """Shared options for the three control commands."""
    func = click.option(
        "--role",
        type=click.Choice(["hub", "shop", "follower", "customer"]),
        help="Override the node role (default: auto-detect from /etc/aitbc)",
    )(func)
    func = click.option(
        "--dry-run",
        is_flag=True,
        help="Show which systemctl commands would run without running them",
    )(func)
    func = click.pass_context(func)
    return func


@click.command(help="Start all AITBC services for the current (or selected) role")
@_common_options
def start(ctx, role, dry_run):
    """Start role services."""
    return _control_services(ctx, "start", role, dry_run)


@click.command(help="Stop all AITBC services for the current (or selected) role")
@_common_options
def stop(ctx, role, dry_run):
    """Stop role services."""
    return _control_services(ctx, "stop", role, dry_run)


@click.command(help="Restart all AITBC services for the current (or selected) role")
@_common_options
def restart(ctx, role, dry_run):
    """Restart role services."""
    return _control_services(ctx, "restart", role, dry_run)
