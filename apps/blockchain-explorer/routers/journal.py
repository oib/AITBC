"""Recent service-journal entries for the alerts page.

``GET /api/journal/recent`` shells out to ``journalctl -o json`` and returns
warning-or-worse entries — the context behind an ``AITBCJournalErrors`` alert.

Exposure is deliberately bounded: only entries whose unit/syslog-identifier
starts with ``aitbc`` are ever returned, the optional ``unit`` filter must name
an ``aitbc-*`` unit, and message text is truncated. The explorer service runs
as aitbc with ``SupplementaryGroups=systemd-journal``; where that has not been
deployed the endpoint returns an empty list rather than an error.
"""

import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_UNIT_RE = re.compile(r"^aitbc[a-z0-9._@-]*\.(service|timer|scope|socket|mount|target)$")
_PRIORITIES = {"emerg", "alert", "crit", "err", "warning"}
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
_MESSAGE_LIMIT = 500


def _is_aitbc_unit(name: str) -> bool:
    return name.startswith("aitbc") or name.startswith("aitbc_")


def _entry_unit(record: dict[str, Any]) -> str:
    for field in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = record.get(field)
        if value:
            return str(value)
    return "unknown"


def _run_journalctl(priority: str, since_minutes: int, limit: int, unit: str | None) -> list[dict[str, Any]]:
    """journalctl -o json rows; raises HTTPException(503) when journald is unreachable."""
    args = [
        "journalctl",
        "-p",
        priority,
        "--since",
        f"-{since_minutes}min",
        "-n",
        str(limit),
        "-o",
        "json",
        "--no-pager",
        "-q",
    ]
    if unit:
        args += ["-u", unit]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=15)
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


def _present(record: dict[str, Any]) -> dict[str, Any]:
    try:
        unix_us = int(record.get("__REALTIME_TIMESTAMP", 0))
    except (TypeError, ValueError):
        unix_us = 0
    try:
        priority = int(record.get("PRIORITY", 6))
    except (TypeError, ValueError):
        priority = 6
    message = str(record.get("MESSAGE") or "")
    if len(message) > _MESSAGE_LIMIT:
        message = message[:_MESSAGE_LIMIT] + "…"
    return {
        "timestamp": datetime.fromtimestamp(unix_us / 1_000_000, UTC).isoformat() if unix_us else None,
        "timestamp_unix": unix_us // 1_000_000 if unix_us else None,
        "unit": _entry_unit(record),
        "priority": priority,
        "priority_name": _PRIORITY_NAMES.get(priority, str(priority)),
        "message": message,
    }


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
    if priority not in _PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {sorted(_PRIORITIES)}")
    unit_arg: str | None = None
    if unit:
        normalized = unit if "." in unit else f"{unit}.service"
        if not _UNIT_RE.match(normalized):
            raise HTTPException(status_code=400, detail="unit must name an aitbc-* unit")
        unit_arg = normalized

    records = _run_journalctl(priority, since_minutes, limit, unit_arg)
    entries = [_present(r) for r in records if _is_aitbc_unit(_entry_unit(r))]
    entries.reverse()  # journalctl -n returns newest last
    return {
        "entries": entries,
        "count": len(entries),
        "unit": unit_arg,
        "priority": priority,
        "journal_access": bool(entries) or _journald_reachable(),
    }


def _journald_reachable() -> bool:
    """False when journalctl cannot read the journal at all (missing group)."""
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
