#!/usr/bin/env python3
"""Export AITBC nightly-backup freshness as a node_exporter textfile.

MON-2: the nightly ``aitbc-backup.timer`` lands a generation under
``AITBC_BACKUP_BASE`` (~01:0x) on every host, but until now nothing noticed
when it stopped -- a silent failure would surface only when someone needed
the backup. This exporter runs every 15 minutes and makes the state
scrapable:

    aitbc_backup_last_generation_timestamp_seconds   mtime of the newest
                                                     YYYYMMDD_HHMMSS dir
    aitbc_backup_last_generation_bytes               summed file sizes in it
    aitbc_backup_generations_count                   name-matched dirs held
    aitbc_backup_last_run_success                    1 when the last
                                                     aitbc-backup.service
                                                     run ended Result=success
    aitbc_backup_scrape_success{source=...}          per-source read health
    aitbc_backup_exporter_timestamp_seconds          when this run finished

Read-only on the backup directory; only generation directory names are
consulted -- never file names inside them beyond sizes, never contents.
Writes, atomically, to ``<AITBC_TEXTFILE_DIR>/aitbc_backup.prom``. A run that
cannot read the backup base still writes a minimal failure file so the alert
sees blindness rather than stale health. Run by aitbc-backup-metrics.timer;
stdlib only.

Environment:
    AITBC_BACKUP_BASE    default /var/backups/aitbc
    AITBC_BACKUP_UNIT    systemd unit probed for Result (aitbc-backup.service)
    AITBC_TEXTFILE_DIR   default /var/lib/prometheus/node-exporter
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OUTPUT_NAME = "aitbc_backup.prom"
GENERATION_RE = re.compile(r"^20\d{6}_\d{6}$")


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def scan(base: Path) -> tuple[int, int, int]:
    """(newest generation mtime, its summed bytes, generation count)."""
    gens = [d for d in base.iterdir() if d.is_dir() and GENERATION_RE.match(d.name)]
    if not gens:
        raise FileNotFoundError(f"no generation dirs under {base}")
    newest = max(gens, key=lambda d: d.stat().st_mtime)
    total = sum(f.stat().st_size for f in newest.rglob("*") if f.is_file())
    return int(newest.stat().st_mtime), total, len(gens)


def last_run_success(unit: str) -> int:
    out = subprocess.run(
        ["systemctl", "show", unit, "-p", "Result", "--value"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if out.returncode != 0:
        raise RuntimeError(f"systemctl show {unit} rc={out.returncode}")
    return 1 if out.stdout.strip() == "success" else 0


def render(
    newest_ts: int | None,
    newest_bytes: int | None,
    gen_count: int | None,
    run_ok: int | None,
    now: float,
    failed: list[str],
) -> str:
    lines = [
        "# HELP aitbc_backup_last_generation_timestamp_seconds Mtime of the newest backup generation dir.",
        "# TYPE aitbc_backup_last_generation_timestamp_seconds gauge",
    ]
    if newest_ts is not None:
        lines.append(f"aitbc_backup_last_generation_timestamp_seconds {newest_ts}")
    lines += [
        "# HELP aitbc_backup_last_generation_bytes Summed file sizes of the newest backup generation.",
        "# TYPE aitbc_backup_last_generation_bytes gauge",
    ]
    if newest_bytes is not None:
        lines.append(f"aitbc_backup_last_generation_bytes {newest_bytes}")
    lines += [
        "# HELP aitbc_backup_generations_count Backup generation directories held.",
        "# TYPE aitbc_backup_generations_count gauge",
    ]
    if gen_count is not None:
        lines.append(f"aitbc_backup_generations_count {gen_count}")
    lines += [
        "# HELP aitbc_backup_last_run_success 1 when the last aitbc-backup.service run ended Result=success.",
        "# TYPE aitbc_backup_last_run_success gauge",
    ]
    if run_ok is not None:
        lines.append(f"aitbc_backup_last_run_success {run_ok}")
    for source in ("backups_dir", "unit_result"):
        lines += [f'aitbc_backup_scrape_success{{source="{_label(source)}"}} {0 if source in failed else 1}']
    lines += [
        "# HELP aitbc_backup_exporter_timestamp_seconds Unix time the last exporter run finished.",
        "# TYPE aitbc_backup_exporter_timestamp_seconds gauge",
        f"aitbc_backup_exporter_timestamp_seconds {int(now)}",
    ]
    return "\n".join(lines) + "\n"


def _failure_render(now: float) -> str:
    return (
        "# HELP aitbc_backup_scrape_success 1 when this source was readable.\n"
        "# TYPE aitbc_backup_scrape_success gauge\n"
        'aitbc_backup_scrape_success{source="exporter"} 0\n'
        "# HELP aitbc_backup_exporter_timestamp_seconds Unix time the last exporter run finished.\n"
        "# TYPE aitbc_backup_exporter_timestamp_seconds gauge\n"
        f"aitbc_backup_exporter_timestamp_seconds {int(now)}\n"
    )


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_backup.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    base = Path(os.environ.get("AITBC_BACKUP_BASE", "/var/backups/aitbc"))
    unit = os.environ.get("AITBC_BACKUP_UNIT", "aitbc-backup.service")
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    now = time.time()

    newest_ts = newest_bytes = gen_count = run_ok = None
    failed: list[str] = []
    try:
        newest_ts, newest_bytes, gen_count = scan(base)
    except Exception:  # noqa: BLE001 - collect probe — an unreadable source counts as failed
        failed.append("backups_dir")
    try:
        run_ok = last_run_success(unit)
    except Exception:  # noqa: BLE001 - collect probe — an unreadable unit result counts as failed
        failed.append("unit_result")

    try:
        write_atomic(directory, render(newest_ts, newest_bytes, gen_count, run_ok, now, failed))
    except OSError:
        try:
            write_atomic(directory, _failure_render(now))
        except OSError:
            pass
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
