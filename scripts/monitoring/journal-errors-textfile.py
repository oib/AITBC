#!/usr/bin/env python3
"""Count warning-and-worse journal messages per unit into a textfile.

Two signals are merged, because aitbc services log through stdout: journald
tags every such line PRIORITY=6 (info), so the true level only exists in the
message text as a leading ``[WARNING]``/``[ERROR]``/... token. Systemd's own
records (watchdog kills, failed units, coredumps) carry a real PRIORITY. So:

    pass 1: journalctl -p err            -> real priorities emerg..err
    pass 2: journalctl -g '[LEVEL]'      -> text levels our services emit

Every entry is counted per unit under ``aitbc_journal_error_messages``
(real priority <= 3, or text level ERROR/CRITICAL/FATAL) or
``aitbc_journal_warning_messages`` (real priority 4, or text WARNING/WARN).
Counts are gauges over a rolling window (default 15 min): a burst fires
AITBCJournalErrors while it is ongoing and clears when the window moves on.

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

TEXT_ERROR_LEVELS = ("ERROR", "CRITICAL", "FATAL")
TEXT_WARNING_LEVELS = ("WARNING", "WARN")
TEXT_LEVEL_RE = re.compile(r"^\[(WARNING|WARN|ERROR|CRITICAL|FATAL)\]")

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def entry_unit(record: dict) -> str:
    """Best available "unit" for a journal record."""
    for field in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = record.get(field)
        if value:
            return str(value)
    return "unknown"


def _journalctl(extra: list[str], window: str) -> list[dict]:
    """Parsed journalctl -o json rows for one query; [] on any failure."""
    try:
        out = subprocess.run(
            ["journalctl", "--since", window, "-o", "json", "--no-pager", "-q", *extra],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    records = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def collect(window: str) -> tuple[Counter[tuple[int, str]], bool]:
    """{(is_error, unit): count} over the window, plus an all-queries-failed flag."""
    # Real priorities: emerg..err (systemd's own records, watchdog kills, etc.)
    real = _journalctl(["-p", "err"], window)
    # Text levels our services emit at stdout priority 6.
    text = _journalctl(["-g", r"\[(WARNING|WARN|ERROR|CRITICAL|FATAL)\]"], window)
    counts: Counter[tuple[int, str]] = Counter()
    seen: set[str] = set()
    for record in real + text:
        cursor = record.get("__CURSOR")
        if cursor is not None:
            if cursor in seen:
                continue
            seen.add(cursor)
        try:
            priority = int(record.get("PRIORITY", 6))
        except (TypeError, ValueError):
            priority = 6
        level = TEXT_LEVEL_RE.match(str(record.get("MESSAGE") or ""))
        level_name = level.group(1) if level else None
        is_error = priority <= 3 or level_name in TEXT_ERROR_LEVELS
        is_warning = priority == 4 or level_name in TEXT_WARNING_LEVELS
        if not (is_error or is_warning):
            continue
        unit = _LABEL_SAFE.sub("_", entry_unit(record))[:80]
        counts[(1 if is_error else 0, unit)] += 1
    ok = bool(real) or bool(text) or _journald_reachable()
    return counts, ok


def _journald_reachable() -> bool:
    """True when journalctl can read the system journal (empty is still fine)."""
    try:
        out = subprocess.run(
            ["journalctl", "--system", "-n", "1", "-o", "json", "--no-pager", "-q"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


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
    counts, ok = collect(window)
    try:
        write_atomic(directory, render(counts, time.time(), ok))
    except OSError as exc:
        print(f"journal-errors: cannot write textfile: {exc}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
