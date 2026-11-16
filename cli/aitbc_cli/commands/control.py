#!/usr/bin/env python3
"""Role-aware service control commands.

Provides ``aitbc start``, ``aitbc stop`` and ``aitbc restart`` that
act on the systemd units configured for the local node role (or an
explicitly requested role).
"""

import json
import os
import subprocess

import click

from ..utils import error, output, success
from ..utils.http_client import get_logger
from ..utils.error_handling import CLIError, abort

logger = get_logger(__name__)

HEALTH_CHECK_SCRIPT = "/opt/aitbc/scripts/monitoring/health_check.sh"


def _role_env(role: str | None) -> dict:
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


def _role_services(role: str | None) -> list:
    """Resolve the systemd units for the given or detected role."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {HEALTH_CHECK_SCRIPT} >/dev/null 2>&1 && printf "%s\\n" "${{ROLE_SERVICES[@]}}"',
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


def _partition_installed(services: list) -> tuple[list, list]:
    """Split role services into (installed, not-installed) on this host.

    The role lists in ``scripts/monitoring/health_check.sh`` are role-ideal
    manifests shared by every node of that role; a shop node legitimately
    lacks units that live on the hub (#1549). Acting on the full manifest
    makes ``--dry-run`` enumerate units systemd does not have and makes a
    real run fail on ``Unit not found``. ``systemctl is-enabled`` prints
    ``not-found`` for units with no unit file; anything else means the
    unit exists and start/stop/restart can act on it. The check is
    output-based and fails open, mirroring ``service_is_installed`` in
    health_check.sh, so a host without systemctl keeps the old behavior.
    """
    installed, missing = [], []
    for svc in services:
        try:
            res = subprocess.run(
                ["systemctl", "is-enabled", svc],
                capture_output=True,
                text=True,
                timeout=10,
            )
            state = res.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            state = ""
        if state == "not-found":
            missing.append(svc)
        else:
            installed.append(svc)
    return installed, missing


def _skipped_result(svc: str, action: str, human: bool) -> dict:
    """Result entry for a role-ideal unit this host does not have installed."""
    if human:
        click.echo(f"skipping {svc}: unit not installed on this host")
    return {
        "service": svc,
        "action": action,
        "status": "skipped",
        "message": "unit not installed on this host",
    }


def _run_service_action(prefix: list, action: str, svc: str, dry_run: bool, human: bool) -> tuple[dict, bool]:
    """Run ``systemctl <action> <svc>`` (or echo it under ``--dry-run``).

    Returns the result entry and whether the action succeeded. Per-service
    lines are human-facing only; in json/yaml mode stdout must stay a
    single output()/abort() document.
    """
    cmd = prefix + ["systemctl", action, svc]
    if dry_run:
        click.echo(f"would run: {' '.join(cmd)}")
        return {"service": svc, "action": action, "status": "dry-run"}, True

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    ok = res.returncode == 0
    if ok:
        if human:
            success(f"{action} {svc}: OK")
    else:
        err = res.stderr.strip() or res.stdout.strip()
        if human:
            # assignment keeps error() out of the AST-guard's
            # "trailing expression" shape; the abort below is what
            # actually sets the non-zero exit.
            _ = error(f"{action} {svc} failed: {err}")
    return (
        {
            "service": svc,
            "action": action,
            "status": "ok" if ok else "failed",
            "message": res.stderr.strip() if not ok else res.stdout.strip(),
        },
        ok,
    )


def _control_services(
    ctx,
    action: str,
    role: str | None,
    dry_run: bool,
):
    """Run ``systemctl <action>`` for each installed unit of the selected role."""
    try:
        services = _role_services(role)
    except RuntimeError as e:
        abort(None, str(e))
        return 1

    _, missing = _partition_installed(services)
    missing_set = set(missing)

    prefix = _systemctl_prefix()
    if not prefix:
        logger.debug("Running systemctl as root")
    else:
        logger.debug("Using %s for systemctl", " ".join(prefix))

    results = []
    overall_ok = True
    fmt = ctx.obj.get("output_format", "table") if ctx and ctx.obj else "table"
    human = fmt not in ("json", "yaml")

    for svc in services:
        if svc in missing_set:
            results.append(_skipped_result(svc, action, human))
            continue
        entry, ok = _run_service_action(prefix, action, svc, dry_run, human)
        results.append(entry)
        overall_ok = overall_ok and ok

    payload = {"role": role or "auto", "action": action, "services": results}

    if not overall_ok and not dry_run:
        _abort_failed_services(ctx, action, results, payload, fmt)

    output(
        payload,
        format=fmt,
        title=f"{action.title()} role services",
    )
    return 0


def _abort_failed_services(ctx, action: str, results: list, payload: dict, fmt: str) -> None:
    """Exit non-zero on failed units — after the results are visible.

    Machine-readable modes keep stdout a single document, so the
    per-service statuses ride inside the error document itself (abort()
    does not accept extra payload fields). Human formats emit the results
    doc first, then abort()'s error line ends the output.
    """
    failed = [r["service"] for r in results if r["status"] == "failed"]
    msg = f"{action} failed for services: {', '.join(failed)}"
    if fmt in ("json", "yaml"):
        doc = {"error": "CLIError", "message": msg, "exit_code": 1, **payload}
        if fmt == "yaml":
            try:
                import yaml

                click.echo(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False).rstrip("\n"))
            except ImportError:
                click.echo(json.dumps(doc, indent=2))
        else:
            click.echo(json.dumps(doc, indent=2))
        raise CLIError(msg)
    output(payload, format=fmt, title=f"{action.title()} role services")
    abort(ctx, msg)


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


@click.command(
    help="Start all AITBC services for the current (or selected) role",
    epilog="""Examples:

  aitbc start

  aitbc start --role hub

  aitbc start --dry-run""",
)
@_common_options
def start(ctx, role, dry_run):
    """Start all AITBC services for the current or selected role."""
    return _control_services(ctx, "start", role, dry_run)


@click.command(
    help="Stop all AITBC services for the current (or selected) role",
    epilog="""Examples:

  aitbc stop

  aitbc stop --role hub

  aitbc stop --dry-run""",
)
@_common_options
def stop(ctx, role, dry_run):
    """Stop all AITBC services for the current or selected role."""
    return _control_services(ctx, "stop", role, dry_run)


@click.command(
    help="Restart all AITBC services for the current (or selected) role",
    epilog="""Examples:

  aitbc restart

  aitbc restart --role hub

  aitbc restart --dry-run""",
)
@_common_options
def restart(ctx, role, dry_run):
    """Restart all AITBC services for the current or selected role."""
    return _control_services(ctx, "restart", role, dry_run)
