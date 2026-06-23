#!/usr/bin/env python3
"""Systematically harden all AITBC systemd service files for v0.5.0.

This script applies security hardening directives to all .service files
while preserving existing functionality. It creates .bak backups.
"""

import re
import shutil
from pathlib import Path

REPO_ROOT = Path("/opt/aitbc")

# Standard security directives to add (safe for most services)
SECURITY_DIRECTIVES = [
    ("PrivateTmp", "yes"),
    ("NoNewPrivileges", "yes"),
    ("ProtectHome", "yes"),
    ("ProtectKernelTunables", "yes"),
    ("ProtectKernelModules", "yes"),
    ("ProtectControlGroups", "yes"),
    ("RestrictSUIDSGID", "yes"),
    ("RestrictRealtime", "yes"),
    ("RestrictNamespaces", "yes"),
    ("LockPersonality", "yes"),
    ("MemoryDenyWriteExecute", "yes"),
    ("SystemCallArchitectures", "native"),
    ("SystemCallFilter", "@system-service"),
]

# Services that need write access to /opt/aitbc
SERVICES_NEEDING_WRITE_ACCESS = {
    "aitbc-coordinator-api.service",
    "aitbc-blockchain-node.service",
    "aitbc-agent-coordinator.service",
    "aitbc-marketplace.service",
    "aitbc-api-gateway.service",
    "aitbc-blockchain-event-bridge.service",
    "aitbc-blockchain-explorer.service",
    "aitbc-blockchain-rpc.service",
    "aitbc-blockchain-sync.service",
    "aitbc-exchange.service",
    "aitbc-gpu.service",
    "aitbc-hermes.service",
    "aitbc-miner.service",
    "aitbc-trading.service",
    "aitbc-wallet.service",
    "aitbc-ai.service",
    "aitbc-learning.service",
    "aitbc-modality-optimization.service",
    "aitbc-multimodal.service",
    "aitbc-agent-management.service",
    "aitbc-ffmpeg.service",
    "aitbc-whisper.service",
    "aitbc-edge.service",
    "aitbc-bridge-monitor.service",
    "aitbc-governance.service",
    "aitbc-recovery.service",
    "aitbc-monitoring.service",
}

# Services that are oneshot (no restart, no watchdog)
ONESHOT_SERVICES = {
    "aitbc-load-secrets.service",
    "aitbc-plugin.service",
}


def has_directive(content: str, key: str) -> bool:
    """Check if content already has a directive (not commented out)."""
    pattern = rf"^\s*{re.escape(key)}\s*=\s*"
    return bool(re.search(pattern, content, re.MULTILINE))


def insert_after_section_header(content: str, section_name: str, new_lines: list[str]) -> str:
    """Insert lines after the last directive in a systemd section."""
    if not new_lines:
        return content

    lines = content.splitlines()
    result = []
    in_target_section = False
    section_start_idx = -1
    last_directive_in_section = -1

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check if we're entering a section
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target_section:
                # We found the next section, insert before this line
                break
            if stripped == f"[{section_name}]":
                in_target_section = True
                section_start_idx = i
                result.append(line)
                continue

        if in_target_section:
            # Track directives and empty lines in this section
            if stripped == "":
                # Skip empty lines for now, we'll re-add them
                continue
            # This is a directive in our target section
            last_directive_in_section = len(result)
            result.append(line)
        else:
            result.append(line)

    if not in_target_section:
        return content

    # Insert new lines after the last directive in the section
    insert_pos = last_directive_in_section + 1 if last_directive_in_section >= 0 else section_start_idx + 1

    # Build insertion with proper formatting
    insertion = ["", "# Security hardening (v0.5.0)"]
    insertion.extend(new_lines)

    return "\n".join(result[:insert_pos] + insertion + result[insert_pos:])


def add_directives(content: str, directives: list[tuple[str, str]]) -> str:
    """Add directives to [Service] section if they don't already exist."""
    new_lines = []
    for key, value in directives:
        if not has_directive(content, key):
            new_lines.append(f"{key}={value}")
    return insert_after_section_header(content, "Service", new_lines)


def standardize_restart(content: str, service_name: str) -> tuple[str, list[str]]:
    """Standardize restart settings."""
    changes = []
    if service_name in ONESHOT_SERVICES:
        return content, changes

    # Check current Restart setting
    restart_match = re.search(r"^Restart\s*=\s*(\w+)", content, re.MULTILINE)
    if restart_match:
        current = restart_match.group(1)
        if current == "always":
            content = re.sub(
                r"^Restart\s*=\s*always",
                "Restart=on-failure",
                content,
                flags=re.MULTILINE,
            )
            changes.append("Restart=on-failure")

    # Standardize RestartSec
    restartsec_match = re.search(r"^RestartSec\s*=\s*(\d+)", content, re.MULTILINE)
    if restartsec_match:
        current = restartsec_match.group(1)
        if current != "5":
            content = re.sub(
                r"^RestartSec\s*=\s*\d+",
                "RestartSec=5",
                content,
                flags=re.MULTILINE,
            )
            changes.append("RestartSec=5")
    else:
        content = add_directives(content, [("RestartSec", "5")])
        changes.append("RestartSec=5")

    # Add Restart if missing
    if not restart_match:
        content = add_directives(content, [("Restart", "on-failure")])
        changes.append("Restart=on-failure")

    return content, changes


def add_watchdog(content: str, service_name: str) -> tuple[str, list[str]]:
    """Add watchdog support for non-oneshot services."""
    changes = []
    if service_name in ONESHOT_SERVICES:
        return content, changes

    directives = []
    if not has_directive(content, "WatchdogSec"):
        directives.append(("WatchdogSec", "30"))
        changes.append("WatchdogSec=30")
    if not has_directive(content, "NotifyAccess"):
        directives.append(("NotifyAccess", "all"))
        changes.append("NotifyAccess=all")

    if directives:
        content = add_directives(content, directives)

    return content, changes


def add_protect_system(content: str, service_name: str) -> tuple[str, list[str]]:
    """Add ProtectSystem based on service needs."""
    changes = []
    if has_directive(content, "ProtectSystem"):
        return content, changes

    if service_name in SERVICES_NEEDING_WRITE_ACCESS:
        directives = [
            ("ProtectSystem", "full"),
            ("ReadWritePaths", "/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc"),
        ]
        changes.append("ProtectSystem=full")
        changes.append("ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc")
    else:
        directives = [("ProtectSystem", "strict")]
        changes.append("ProtectSystem=strict")

    content = add_directives(content, directives)
    return content, changes


def harden_service_file(path: Path) -> dict[str, any]:
    """Harden a single service file. Returns change report."""
    service_name = path.name
    original = path.read_text()

    # Backup
    backup_path = path.with_suffix(".service.bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)

    modified = original
    changes = []

    # Add standard security directives
    new_directives = []
    for key, value in SECURITY_DIRECTIVES:
        if not has_directive(modified, key):
            new_directives.append((key, value))
            changes.append(f"+ {key}={value}")

    if new_directives:
        modified = add_directives(modified, new_directives)

    # Add ProtectSystem
    modified, ps_changes = add_protect_system(modified, service_name)
    changes.extend([f"+ {c}" for c in ps_changes])

    # Standardize restart
    modified, restart_changes = standardize_restart(modified, service_name)
    changes.extend([f"{'~' if c in ('Restart=on-failure',) else '+'} {c}" for c in restart_changes])

    # Add watchdog
    modified, wd_changes = add_watchdog(modified, service_name)
    changes.extend([f"+ {c}" for c in wd_changes])

    if changes:
        path.write_text(modified)

    return {
        "service": service_name,
        "path": str(path),
        "changes": changes,
        "modified": bool(changes),
    }


def main():
    repo = Path("/opt/aitbc")
    service_files = sorted(repo.rglob("*.service"))

    print(f"Found {len(service_files)} service files to harden")
    print("=" * 60)

    reports = []
    modified_count = 0

    for path in service_files:
        report = harden_service_file(path)
        reports.append(report)
        if report["modified"]:
            modified_count += 1
            print(f"\n{report['service']}:")
            for change in report["changes"]:
                print(f"  {change}")
        else:
            print(f"\n{report['service']}: (no changes needed)")

    print("\n" + "=" * 60)
    print(f"Summary: {modified_count}/{len(service_files)} files modified")
    print("Backups saved as .service.bak")

    # Generate summary file
    summary_path = repo / "docs/releases/v0.5.0/systemd-hardening-report.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_path, "w") as f:
        f.write("# Systemd Hardening Report (v0.5.0)\n\n")
        f.write("Date: 2026-06-19\n")
        f.write(f"Files modified: {modified_count}/{len(service_files)}\n\n")
        f.write("## Changes per Service\n\n")
        for report in reports:
            f.write(f"### {report['service']}\n")
            f.write(f"Path: `{report['path']}`\n")
            if report["changes"]:
                f.write("Changes:\n")
                for change in report["changes"]:
                    f.write(f"- {change}\n")
            else:
                f.write("No changes needed (already hardened)\n")
            f.write("\n")

    print(f"\nReport written to: {summary_path}")


if __name__ == "__main__":
    main()
