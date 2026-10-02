"""Recent service-journal entries for the alerts page.

``GET /api/journal/recent`` serves warning-or-worse journal entries — the
context behind an ``AITBCJournalErrors`` alert.

Two journald signals are merged per request, because aitbc services log
through stdout: journald tags every such line PRIORITY=6 (info), so the true
level only exists in the message text as a leading ``[WARNING]``/``[ERROR]``
token. Systemd's own records (watchdog kills, failed units) carry a real
PRIORITY. Pass 1 fetches ``-p <priority>``, pass 2 fetches a ``-g`` regex for
the equivalent text levels, and the results merge on the journal cursor.

Exposure is deliberately bounded: only entries whose unit/syslog-identifier
starts with ``aitbc`` are ever returned, the optional ``unit`` filter must
name an ``aitbc-*`` unit, and message text is truncated. The explorer service
runs as aitbc with ``SupplementaryGroups=systemd-journal``; where that has not
been deployed the endpoint returns an empty list with ``journal_access``
false.
"""

import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_UNIT_RE = re.compile(r"^aitbc[a-z0-9._@-]*\.(service|timer|scope|socket|mount|target)$")
_TEXT_LEVEL_RE = re.compile(r"^\[(WARNING|WARN|ERROR|CRITICAL|FATAL)\]")
_PRIORITY_NAMES = {
    0: "emerg",
    1: "alert",
    2: "crit",
    3: "err",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}
# Requested severity -> (journalctl -p arg, text levels to union in). Text
# levels are what aitbc stdout logging emits; real priorities catch systemd's
# own records (watchdog kills, unit failures).
_PASSES = {
    "warning": ("warning", "WARNING|WARN|ERROR|CRITICAL|FATAL"),
    "err": ("err", "ERROR|CRITICAL|FATAL"),
    "crit": ("crit", "CRITICAL|FATAL"),
    "alert": ("alert", "FATAL"),
    "emerg": ("emerg", None),
}
_MESSAGE_LIMIT = 500
_SCAN_LIMIT = 2000


def _is_aitbc_unit(name: str) -> bool:
    return name.startswith("aitbc")


def _entry_unit(record: dict[str, Any]) -> str:
    for field in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = record.get(field)
        if value:
            return str(value)
    return "unknown"


def _journalctl(extra: list[str], since_minutes: int, limit: int) -> list[dict[str, Any]]:
    try:
        out = subprocess.run(
            [
                "journalctl",
                "--since",
                f"-{since_minutes}min",
                "-n",
                str(limit),
                "-o",
                "json",
                "--no-pager",
                "-q",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail="journal unavailable on this host") from exc
    if out.returncode != 0:
        raise HTTPException(status_code=503, detail="journal unavailable on this host")
    records: list[dict[str, Any]] = []
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


def _run_journalctl(priority: str, since_minutes: int, limit: int, unit: str | None) -> list[dict[str, Any]]:
    """Union of the real-priority pass and the text-level pass, deduped."""
    prio_arg, text_levels = _PASSES[priority]
    unit_args = ["-u", unit] if unit else []
    records = _journalctl(["-p", prio_arg, *unit_args], since_minutes, limit)
    if text_levels:
        records += _journalctl(["-g", rf"\[({text_levels})\]", *unit_args], since_minutes, limit)
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for record in records:
        cursor = record.get("__CURSOR")
        if cursor is not None:
            if cursor in seen:
                continue
            seen.add(cursor)
        merged.append(record)
    return merged


def _priority_of(record: dict[str, Any]) -> tuple[int, str]:
    """(severity number, display name) — real PRIORITY overridden by a text level."""
    try:
        priority = int(record.get("PRIORITY", 6))
    except (TypeError, ValueError):
        priority = 6
    level = _TEXT_LEVEL_RE.match(str(record.get("MESSAGE") or ""))
    if level:
        name = level.group(1)
        mapped = {"ERROR": 3, "CRITICAL": 2, "FATAL": 0, "WARNING": 4, "WARN": 4}.get(name)
        if mapped is not None and mapped < priority:
            priority = mapped
    return priority, _PRIORITY_NAMES.get(priority, str(priority))


def _present(record: dict[str, Any]) -> dict[str, Any]:
    try:
        unix_us = int(record.get("__REALTIME_TIMESTAMP", 0))
    except (TypeError, ValueError):
        unix_us = 0
    priority, priority_name = _priority_of(record)
    message = str(record.get("MESSAGE") or "")
    if len(message) > _MESSAGE_LIMIT:
        message = message[:_MESSAGE_LIMIT] + "…"
    return {
        "timestamp": datetime.fromtimestamp(unix_us / 1_000_000, UTC).isoformat() if unix_us else None,
        "timestamp_unix": unix_us // 1_000_000 if unix_us else None,
        "unit": _entry_unit(record),
        "priority": priority,
        "priority_name": priority_name,
        "message": message,
    }


def _journald_reachable() -> bool:
    """False when journalctl cannot read the system journal (missing group)."""
    try:
        out = subprocess.run(
            ["journalctl", "--system", "-n", "1", "-o", "json", "--no-pager", "-q"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    # Without the systemd-journal group this still exits 0 but serves only the
    # caller's own (empty) journal — so presence of rows is the real check.
    return out.returncode == 0 and bool(out.stdout.strip())


@router.get("/api/journal/recent")
def api_journal_recent(
    unit: str | None = None,
    priority: str = "warning",
    limit: int = Query(default=50, le=200, ge=1),
    since_minutes: int = Query(default=1440, le=10080, ge=1),
) -> dict[str, Any]:
    """Recent warning-or-worse journal entries from aitbc-* units, newest first.

    ``unit`` narrows to one unit (``aitbc-blockchain-node.service`` or bare
    ``aitbc-blockchain-node``); any non-aitbc name is rejected. Non-aitbc
    entries are filtered out in code even if journalctl returns them, so the
    public page can never read e.g. sshd or kernel logs through this endpoint.
    """
    if priority not in _PASSES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {sorted(_PASSES)}")
    unit_arg: str | None = None
    if unit:
        normalized = unit if "." in unit else f"{unit}.service"
        if not _UNIT_RE.match(normalized):
            raise HTTPException(status_code=400, detail="unit must name an aitbc-* unit")
        unit_arg = normalized

    records = _run_journalctl(priority, since_minutes, _SCAN_LIMIT, unit_arg)
    entries = [_present(r) for r in records if _is_aitbc_unit(_entry_unit(r))]
    entries.sort(key=lambda e: e.get("timestamp_unix") or 0, reverse=True)
    return {
        "entries": entries[:limit],
        "count": len(entries[:limit]),
        "unit": unit_arg,
        "priority": priority,
        "journal_access": _journald_reachable(),
    }
