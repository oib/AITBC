#!/usr/bin/env python3
"""Count warning-and-worse journal messages per unit into a textfile.

Two signals are merged, because aitbc services log through stdout: journald
tags every such line PRIORITY=6 (info), so the true level only exists in the
message text as a leading ``[WARNING]``/``[ERROR]``/... token. Systemd's own
records (watchdog kills, failed units, coredumps) carry a real PRIORITY. So:

    pass 1: journalctl -p err                        -> real priorities emerg..err
    pass 2: journalctl _TRANSPORT=stdout -g '[LEVEL]' -> text levels our services emit

Every entry is counted per unit under ``aitbc_journal_error_messages``
(real priority <= 3, or text level ERROR/CRITICAL/FATAL) or
``aitbc_journal_warning_messages`` (real priority 4, or text WARNING/WARN).
Counts are gauges over a rolling window (default 15 min): a burst fires
AITBCJournalErrors while it is ongoing and clears when the window moves on.

Memory discipline: ``-g`` is an unindexed regex over every journal entry in
the window, so pass 2 pre-narrows with the indexed ``_TRANSPORT=stdout``
match — text-level tokens only ever appear in service stdout payloads, and
the real-priority cases are already covered by pass 1. Both passes request
only the fields the counter reads and are streamed line-by-line: the parent
never buffers the whole window and the journalctl child serializes far less.
Measured on hub's journal this halves the pass-2 byte stream; the child's
remaining RSS is journald file-mapping, which no query shaping removes.

Run by a systemd timer (aitbc-journal-errors.timer); stdlib only. The unit runs
as aitbc with SupplementaryGroups=systemd-journal, which is what lets
journalctl see the system journal.

Environment:
    AITBC_TEXTFILE_DIR    default /var/lib/prometheus/node-exporter
    AITBC_JOURNAL_WINDOW  journalctl --since argument, default "15 minutes ago"
"""

from __future__ import annotations

import itertools
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator

OUTPUT_NAME = "aitbc_journal.prom"

JOURNALCTL_TIMEOUT = 60
# Only the fields the counter reads -- full -o json rows carry a dozen extra
# trusted fields per entry and roughly doubled the serialized stream.
JOURNAL_FIELDS = ("__CURSOR", "PRIORITY", "MESSAGE", "_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM")

TEXT_ERROR_LEVELS = ("ERROR", "CRITICAL", "FATAL")
TEXT_WARNING_LEVELS = ("WARNING", "WARN")
TEXT_LEVEL_PATTERN = r"\[(WARNING|WARN|ERROR|CRITICAL|FATAL)\]"
TEXT_LEVEL_RE = re.compile("^" + TEXT_LEVEL_PATTERN)

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def entry_unit(record: dict) -> str:
    """Best available "unit" for a journal record."""
    for field in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = record.get(field)
        if value:
            return str(value)
    return "unknown"


def _iter_journalctl(extra: list[str], window: str, status: dict) -> Iterator[dict]:
    """Stream ``journalctl -o json`` rows for one query, parsed per line.

    The pipe is drained as the child writes it, so neither side ever holds
    the whole window: the old ``capture_output`` variant buffered ~13 MB of
    JSON text plus the parsed record list in the parent on a busy 15-minute
    window. ``status["rc"]`` records the child's exit code (``None`` when the
    query could not even be started) so callers can tell "journald empty"
    from "journalctl failed" without a sentinel row.
    """
    status["rc"] = None
    argv = [
        "journalctl",
        "--since",
        window,
        "-o",
        "json",
        "--output-fields=" + ",".join(JOURNAL_FIELDS),
        "--no-pager",
        "-q",
        *extra,
    ]
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
    except OSError:
        return
    assert proc.stdout is not None
    deadline = time.monotonic() + JOURNALCTL_TIMEOUT
    try:
        while True:
            # select() gives the readline a deadline: a wedged journalctl is
            # killed instead of blocking the oneshot past its budget.
            ready, _, _ = select.select([proc.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                proc.kill()
                proc.wait()
                return
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record
    finally:
        try:
            status["rc"] = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            status["rc"] = proc.wait()


def collect(window: str) -> tuple[Counter[tuple[int, str]], bool]:
    """{(is_error, unit): count} over the window, plus an all-queries-failed flag."""
    real_status: dict = {}
    text_status: dict = {}
    # Real priorities: emerg..err (systemd's own records, watchdog kills, etc.)
    real = _iter_journalctl(["-p", "err"], window, real_status)
    # Text levels our services emit at stdout priority 6. _TRANSPORT=stdout
    # is indexed, so the -g regex only runs over stdout payloads instead of
    # every entry in the window; the transport check is also semantically
    # exact here -- a [LEVEL] token is meaningful only in stdout text.
    text = _iter_journalctl(["_TRANSPORT=stdout", "-g", TEXT_LEVEL_PATTERN], window, text_status)
    counts: Counter[tuple[int, str]] = Counter()
    seen: set[str] = set()
    any_rows = False
    for record in itertools.chain(real, text):
        any_rows = True
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
    # success means a query actually returned rows or exited 0 — a reachable
    # journald with both queries failed is a blind scan, not a clean one.
    ok = real_status["rc"] == 0 or text_status["rc"] == 0 or any_rows
    return counts, ok


def render(counts: Counter[tuple[int, str]], now: float, ok: bool) -> str:
    lines = [
        "# HELP aitbc_journal_error_messages err-or-worse journal messages per unit in the last window.",
        "# TYPE aitbc_journal_error_messages gauge",
    ]
    emitted = False
    for (is_error, unit), count in sorted(counts.items()):
        if is_error:
            lines.append(f'aitbc_journal_error_messages{{unit="{unit}"}} {count}')
            emitted = True
    if not emitted:
        # Bare zero anchor: without it a quiet window leaves no
        # aitbc_journal_error_messages series at all and AITBCJournalErrors
        # cannot distinguish "no errors" from "exporter blind".
        lines.append("aitbc_journal_error_messages 0")
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
