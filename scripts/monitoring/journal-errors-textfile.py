#!/usr/bin/env python3
"""Count warning-and-worse journal messages per unit into a textfile.

journalctl is asked for a rolling window (default 15 min) at priority
``warning``; every entry is counted by unit under either
``aitbc_journal_error_messages`` (priorities emerg..err) or
``aitbc_journal_warning_messages`` (priority warning). The counts are gauges:
a burst fires the AITBCJournalErrors rule while it is ongoing and clears when
the window moves past it.

Run by a systemd timer (aitbc-journal-errors.timer); stdlib only. The unit runs
as aitbc with SupplementaryGroups=systemd-journal, which is what lets
journalctl see the system journal.

Environment:
    AITBC_TEXTFILE_DIR    default /var/lib/prometheus/node-exporter
    AITBC_JOURNAL_WINDOW  journalctl --since argument, default "15 minutes ago"
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter

OUTPUT_NAME = "aitbc_journal.prom"
PRIORITY_ERROR_MAX = 3  # emerg(0) alert(1) crit(2) err(3); warning is 4

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def entry_unit(record: dict) -> str:
    """Best available "unit" for a journal record."""
    for field in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = record.get(field)
        if value:
            return str(value)
    return "unknown"


def collect(window: str) -> Counter[tuple[int, str]]:
    """{(is_error, unit): count} over the window; empty when journalctl fails."""
    counts: Counter[tuple[int, str]] = Counter()
    try:
        out = subprocess.run(
            [
                "journalctl",
                "-p",
                "warning",
                "--since",
                window,
                "-o",
                "json",
                "--no-pager",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return counts
    if out.returncode != 0:
        return counts
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        try:
            priority = int(record.get("PRIORITY", 6))
        except (TypeError, ValueError):
            continue
        if priority > 4:
            continue  # -p warning already bounds this; belt and braces
        unit = _LABEL_SAFE.sub("_", entry_unit(record))[:80]
        counts[(1 if priority <= PRIORITY_ERROR_MAX else 0, unit)] += 1
    return counts


def render(counts: Counter[tuple[int, str]], now: float, ok: bool) -> str:
    lines = [
        "# HELP aitbc_journal_error_messages err-or-worse journal messages per unit in the last window.",
        "# TYPE aitbc_journal_error_messages gauge",
    ]
    for (is_error, unit), count in sorted(counts.items()):
        if is_error:
            lines.append(f'aitbc_journal_error_messages{{unit="{unit}"}} {count}')
    lines += [
        "# HELP aitbc_journal_warning_messages warning journal messages per unit in the last window.",
        "# TYPE aitbc_journal_warning_messages gauge",
    ]
    for (is_error, unit), count in sorted(counts.items()):
        if not is_error:
            lines.append(f'aitbc_journal_warning_messages{{unit="{unit}"}} {count}')
    lines += [
        "# HELP aitbc_journal_scan_success Whether the journal scan completed (1) or failed (0).",
        "# TYPE aitbc_journal_scan_success gauge",
        f"aitbc_journal_scan_success {int(ok)}",
        "# HELP aitbc_journal_scan_timestamp_seconds Unix time the last scan finished.",
        "# TYPE aitbc_journal_scan_timestamp_seconds gauge",
        f"aitbc_journal_scan_timestamp_seconds {int(now)}",
    ]
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_journal.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    window = os.environ.get("AITBC_JOURNAL_WINDOW", "15 minutes ago")
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    counts = collect(window)
    ok = True
    if not counts:
        # Distinguish "quiet journal" from "journalctl failed" with a probe scan.
        probe = subprocess.run(
            ["journalctl", "-n", "1", "-o", "json", "--no-pager", "-q"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = probe.returncode == 0
    try:
        write_atomic(directory, render(counts, time.time(), ok))
    except OSError as exc:
        print(f"journal-errors: cannot write textfile: {exc}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
