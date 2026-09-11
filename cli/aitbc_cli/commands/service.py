"""Service management commands for AITBC CLI.

Provides systemd unit hardening based on the canonical aitbc-hermes-agent
sandbox pattern.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import get_logger

logger = get_logger(__name__)


# Canonical sandbox directives from aitbc-hermes-agent.service.
# Any existing directive with the same key in [Service] is replaced so that
# the unit ends up with a single, consistent hardening block.
HARDENING_DIRECTIVES: dict[str, str] = {
    "PrivateTmp": "yes",
    "NoNewPrivileges": "yes",
    "ProtectHome": "read-only",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectControlGroups": "yes",
    "RestrictSUIDSGID": "yes",
    "RestrictRealtime": "yes",
    "RestrictNamespaces": "yes",
    "LockPersonality": "yes",
    "MemoryDenyWriteExecute": "no",
    "SystemCallArchitectures": "native",
    "SystemCallFilter": "@system-service",
    "ProtectSystem": "full",
}

# Paths that almost all AITBC Python services need for data, logs and runtime.
DEFAULT_READ_WRITE_PATHS = "/var/lib/aitbc /var/log/aitbc /run/aitbc"

# Services that are shell scripts or special enough that we won't touch them
# unless the operator explicitly names them with --service.
EXCLUDED_FROM_ALL = {
    "aitbc-hermes-agent",
    "aitbc-load-secrets",
    "aitbc-backup",
    "aitbc-recovery",
}


def _service_unit_path(service: str) -> str:
    """Return the expected systemd unit path for a named service.

    If an absolute path is passed, use it directly.
    """
    if service.startswith("/"):
        return service
    if "." in service:
        return f"/etc/systemd/system/{service}"
    return f"/etc/systemd/system/{service}.service"


def _discover_aitbc_services() -> list[str]:
    """List all aitbc-*.service unit file names in /etc/systemd/system."""
    paths = sorted(glob.glob("/etc/systemd/system/aitbc-*.service"))
    return [os.path.basename(p) for p in paths]


def _parse_section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    """Return the start (inclusive) and end (exclusive) line indices of a section.

    The end is the start of the next section or the end of the file.
    """
    pattern = re.compile(rf"^\[{re.escape(section)}\]\s*$")
    start = None
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            start = i
            break
    if start is None:
        return None

    end = len(lines)
    section_header = re.compile(r"^\[.*\]\s*$")
    for i in range(start + 1, len(lines)):
        if section_header.match(lines[i].strip()):
            end = i
            break
    return start, end


def _harden_unit(path: str, dry_run: bool, read_write_paths: str) -> dict[str, Any]:
    """Apply the hermes sandbox pattern to one unit file.

    Returns a summary of what changed.  In dry-run mode the file is not written.
    """
    with open(path) as f:
        lines = f.readlines()

    bounds = _parse_section_bounds(lines, "Service")
    if not bounds:
        return {"path": path, "changed": False, "error": "no [Service] section"}

    start, end = bounds
    section_lines = lines[start:end]

    # Remove existing hardening directives we are about to set, but preserve
    # an existing ReadWritePaths value if the operator already configured one.
    existing_rwp: str | None = None
    new_section_lines: list[str] = []
    directive_pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=")
    managed_keys = set(HARDENING_DIRECTIVES)
    managed_keys.add("ReadWritePaths")

    for line in section_lines:
        match = directive_pattern.match(line)
        if match:
            key = match.group(1)
            if key == "ReadWritePaths":
                existing_rwp = line.split("=", 1)[1].strip()
                # Keep this line; we want to preserve the configured value.
                new_section_lines.append(line)
                continue
            if key in managed_keys:
                # Drop the old value; we will insert the canonical one below.
                continue
        new_section_lines.append(line)

    # Trim trailing blank lines in the section so we can append a clean block.
    while new_section_lines and new_section_lines[-1].strip() == "":
        new_section_lines.pop()

    # Build the hardening block to append.
    block: list[str] = []
    block.append("# AITBC security hardening (v0.5.0)\n")
    for key, value in HARDENING_DIRECTIVES.items():
        block.append(f"{key}={value}\n")
    if existing_rwp is not None:
        block.append(f"ReadWritePaths={existing_rwp}\n")
    else:
        block.append(f"ReadWritePaths={read_write_paths}\n")
    block.append("# AITBC security hardening (v0.5.0)\n")
    block.append("# WatchdogSec=30 # Disabled - requires application-level sd_notify support\n")

    new_section = new_section_lines + ["\n"] + block
    new_lines = lines[:start] + new_section + lines[end:]

    changed = new_lines != lines
    if not changed:
        return {"path": path, "changed": False, "error": None}

    if dry_run:
        return {"path": path, "changed": True, "dry_run": True, "error": None}

    backup = f"{path}.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"  # noqa: UP017
    shutil.copy2(path, backup)

    with open(path, "w") as f:
        f.writelines(new_lines)

    return {"path": path, "changed": True, "backup": backup, "error": None}


def _daemon_reload() -> None:
    """Reload systemd daemon configuration."""
    subprocess.run(["systemctl", "daemon-reload"], check=True, text=True)


def _restart_services(services: list[str]) -> dict[str, Any]:
    """Restart the given systemd services."""
    try:
        subprocess.run(
            ["systemctl", "restart", *services],
            check=True,
            text=True,
            capture_output=True,
        )
        return {"restarted": services, "status": "ok"}
    except subprocess.CalledProcessError as exc:
        return {"restarted": [], "status": "error", "error": exc.stderr.strip()}


@click.group(
    epilog="""Examples:

  aitbc service harden --service aitbc-wallet

  aitbc service harden --all"""
)
def service():
    """Manage AITBC systemd services."""
    pass


@service.command(
    name="harden",
    epilog='''Examples:

  aitbc service harden --service aitbc-wallet

  aitbc service harden --all

  aitbc service harden --all --read-write-paths "/var/lib/aitbc/wallets /var/log/aitbc /run/aitbc"''',
)
@click.option("--service", "service_name", help="Single systemd service unit to harden.")
@click.option("--all", "all_services", is_flag=True, help="Harden all aitbc-*.service units except shell-script helpers.")
@click.option(
    "--read-write-paths",
    default=DEFAULT_READ_WRITE_PATHS,
    help="ReadWritePaths value for units that do not already have one.",
)
@click.option("--no-restart", is_flag=True, help="Do not reload systemd or restart affected services.")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing files.")
@click.pass_context
def harden(
    ctx: click.Context,
    service_name: str | None,
    all_services: bool,
    read_write_paths: str,
    no_restart: bool,
    dry_run: bool,
):
    """Apply the aitbc-hermes systemd sandbox pattern to AITBC services."""
    if not service_name and not all_services:
        abort(ctx, "Specify --service <unit> or --all")
    if service_name and all_services:
        abort(ctx, "Use either --service or --all, not both")

    if all_services:
        discovered = _discover_aitbc_services()
        targets = [s for s in discovered if os.path.splitext(s)[0] not in EXCLUDED_FROM_ALL]
    else:
        assert service_name is not None
        name = service_name
        targets = [name if name.endswith(".service") else f"{name}.service"]

    if not targets:
        abort(ctx, "No matching systemd unit files found in /etc/systemd/system")

    results: list[dict[str, Any]] = []
    changed_units: list[str] = []
    for unit in targets:
        path = _service_unit_path(unit)
        if not os.path.exists(path):
            results.append({"unit": unit, "path": path, "changed": False, "error": "unit file not found"})
            continue
        summary = _harden_unit(path, dry_run, read_write_paths)
        summary["unit"] = unit
        results.append(summary)
        if summary.get("changed") and not dry_run and not summary.get("error"):
            changed_units.append(unit)

    if dry_run:
        output({"dry_run": True, "results": results}, ctx.obj.get("output_format", "table"))
        return

    restart_summary: dict[str, Any] | None = None
    if not no_restart and changed_units:
        try:
            _daemon_reload()
            restart_summary = _restart_services([u.replace(".service", "") for u in changed_units])
        except subprocess.CalledProcessError as exc:
            restart_summary = {"status": "error", "error": str(exc)}

    output(
        {"results": results, "restart": restart_summary},
        ctx.obj.get("output_format", "table"),
        title="Service Hardening",
    )
