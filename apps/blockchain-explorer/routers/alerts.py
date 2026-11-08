"""Alert endpoints: live firing alerts plus the watcher's event-log history.

Data sources (meaningful on the hub, which is where the public site runs):

- Prometheus on this host (``PROMETHEUS_URL``, default ``http://127.0.0.1:9090``).
  Hub's Prometheus sees the whole fleet because nodes remote-write their
  ``up``/alert series into its receiver, so firing alerts here are fleet-wide.
- The prometheus alert watcher's JSON-lines event log (``AITBC_ALERT_LOG``,
  default ``/var/log/aitbc/alerts.log``) written by ``aitbc prometheus alerts
  --watch --alert-log ...`` — history, silences, watcher start markers.

When Prometheus is unreachable the live view falls back to replaying the event
log, so the page still shows what the watcher last knew rather than going blank.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

from validation import clamp_page_limit

router = APIRouter()

_ALERT_EVENTS = ("prometheus_alert_firing", "prometheus_alert_resolved", "prometheus_alert_still_firing")
_WATCHER_STALE_SECONDS = 300.0
_TAIL_HISTORY_BYTES = 512 * 1024
_ALERTS_TTL_SECONDS = 5.0

# Parsed event log cache keyed by (mtime_ns, size).
_events_cache: tuple[int, int, list[dict[str, Any]]] | None = None
# Short-lived live-view cache when the log file is unchanged (Prometheus may still refresh).
_alerts_live_cache: tuple[float, int, int, dict[str, Any]] | None = None


def _alert_log_path() -> Path:
    return Path(os.environ.get("AITBC_ALERT_LOG", "/var/log/aitbc/alerts.log"))


def _prometheus_url() -> str:
    return os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")


def _parse_log_lines(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            events.append(record)
    return events


def _read_events() -> list[dict[str, Any]]:
    """Parse the watcher's JSON-lines log. Cached by (mtime_ns, size)."""
    global _events_cache
    path = _alert_log_path()
    try:
        st = path.stat()
    except OSError:
        return []
    key = (st.st_mtime_ns, st.st_size)
    if _events_cache is not None and _events_cache[0:2] == key:
        return _events_cache[2]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    events = _parse_log_lines(text.splitlines())
    _events_cache = (key[0], key[1], events)
    return events


def _read_events_tail() -> tuple[list[dict[str, Any]], int]:
    """Parse only the trailing slice of the log (newest lines). Returns (events, lines_scanned)."""
    path = _alert_log_path()
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0
    if size == 0:
        return [], 0
    nbytes = min(size, _TAIL_HISTORY_BYTES)
    try:
        with path.open("rb") as fh:
            fh.seek(size - nbytes)
            chunk = fh.read(nbytes)
    except OSError:
        return [], 0
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if nbytes < size and lines:
        lines = lines[1:]  # drop partial first line after seek
    events = _parse_log_lines(lines)
    return events, len(lines)


def _alert_key(record: dict[str, Any]) -> str:
    """Same identity key the CLI's alert-history replay uses."""
    return f"{record.get('alertname')}{json.dumps(record.get('labels') or {}, sort_keys=True)}"


def _replay_firing(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Replay the event stream into the set still firing at end of log."""
    firing: dict[str, dict[str, Any]] = {}
    for record in events:
        name = record.get("event")
        if name not in _ALERT_EVENTS:
            continue
        key = _alert_key(record)
        if name == "prometheus_alert_resolved":
            firing.pop(key, None)
        else:
            firing[key] = record
    return firing


def _present_firing(record: dict[str, Any]) -> dict[str, Any]:
    labels = record.get("labels") or {}
    return {
        "alertname": record.get("alertname"),
        "severity": record.get("severity"),
        "node": labels.get("node") or labels.get("instance"),
        "labels": labels,
        "summary": record.get("summary"),
        "active_at": record.get("active_at") or record.get("timestamp"),
        "silenced": bool(record.get("silenced")),
        "silence_reason": record.get("silence_reason"),
    }


async def _prometheus_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any] | None:
    """GET a Prometheus API path; None on any failure (down, non-200, bad JSON)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{_prometheus_url()}{path}", params=params)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) and data.get("status") == "success" else None
    except (httpx.HTTPError, ValueError):
        return None


def _prom_labels(alert: dict[str, Any]) -> dict[str, Any]:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    return {
        "alertname": labels.get("alertname"),
        "severity": labels.get("severity"),
        "node": labels.get("node") or labels.get("instance"),
        "labels": labels,
        "summary": annotations.get("summary"),
        "description": annotations.get("description"),
        "active_at": alert.get("activeAt"),
        "silenced": False,
    }


async def _watcher_status() -> dict[str, Any] | None:
    """Age of the watcher's textfile heartbeat, when the metric exists."""
    data = await _prometheus_get(
        "/api/v1/query",
        {"query": "max(time() - aitbc_prometheus_watch_poll_timestamp_seconds)"},
    )
    if data is None:
        return None
    result = (data.get("data") or {}).get("result") or []
    if not result:
        return {"present": False, "last_poll_age_seconds": None, "stale": True}
    try:
        age = float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return {"present": False, "last_poll_age_seconds": None, "stale": True}
    return {"present": True, "last_poll_age_seconds": age, "stale": age > _WATCHER_STALE_SECONDS}


def _log_cache_key() -> tuple[int, int] | None:
    path = _alert_log_path()
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


@router.get("/api/alerts")
async def api_alerts() -> dict[str, Any]:
    """Live alert view: firing/pending alerts plus watcher health.

    Firing alerts come from Prometheus when it answers; silenced state is merged
    in from the event-log replay (Prometheus itself does not know watcher
    silences). With Prometheus down, the log replay is the live view.
    """
    global _alerts_live_cache
    log_key = _log_cache_key()
    now = time.time()
    if (
        log_key is not None
        and _alerts_live_cache is not None
        and _alerts_live_cache[1:3] == log_key
        and now - _alerts_live_cache[0] < _ALERTS_TTL_SECONDS
    ):
        out = dict(_alerts_live_cache[3])
        out["checked_at"] = int(now)
        return out

    events = _read_events()
    log_firing = _replay_firing(events)
    silenced_keys = {key for key, rec in log_firing.items() if rec.get("silenced")}

    data, watcher_probe = await asyncio.gather(_prometheus_get("/api/v1/alerts"), _watcher_status())
    watcher = watcher_probe if data is not None else None

    if data is not None:
        firing: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for alert in (data.get("data") or {}).get("alerts") or []:
            entry = _prom_labels(alert)
            if _alert_key({"alertname": entry["alertname"], "labels": entry["labels"]}) in silenced_keys:
                entry["silenced"] = True
            if alert.get("state") == "pending":
                pending.append(entry)
            else:
                firing.append(entry)
        firing.sort(key=lambda e: str(e.get("alertname") or ""))
        payload = {
            "prometheus_ok": True,
            "source": "prometheus",
            "firing": firing,
            "pending": pending,
            "watcher": watcher,
            "log_available": bool(events),
            "checked_at": int(now),
        }
        if log_key is not None:
            _alerts_live_cache = (now, log_key[0], log_key[1], payload)
        return payload

    firing = sorted(
        (_present_firing(rec) for rec in log_firing.values()),
        key=lambda e: str(e.get("alertname") or ""),
    )
    payload = {
        "prometheus_ok": False,
        "source": "event_log",
        "firing": firing,
        "pending": [],
        "watcher": None,
        "log_available": bool(events),
        "checked_at": int(now),
    }
    if log_key is not None:
        _alerts_live_cache = (now, log_key[0], log_key[1], payload)
    return payload


def _normalize_history_state(state: str | None) -> str | None:
    if state is not None and state not in ("firing", "resolved", "silenced"):
        return None
    return state


def _history_events(
    alertname: str | None,
    node: str | None,
    state: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Full log when any filter is set; tail slice otherwise (newest unfiltered view)."""
    if alertname or node or state:
        events = _read_events()
        return events, len(events)
    return _read_events_tail()


def _history_record_matches(
    record: dict[str, Any],
    alertname: str | None,
    node: str | None,
    state: str | None,
) -> bool:
    if alertname and alertname not in str(record.get("alertname") or ""):
        return False
    if node:
        labels = record.get("labels") or {}
        if node not in (str(labels.get("node") or ""), str(labels.get("instance") or "")):
            return False
    if state == "silenced":
        return record.get("silenced") is True
    if state:
        return record.get("state") == state
    return True


def _collect_history(
    events: list[dict[str, Any]],
    limit: int,
    alertname: str | None,
    node: str | None,
    state: str | None,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for record in reversed(events):
        if not _history_record_matches(record, alertname, node, state):
            continue
        matched.append(record)
        if len(matched) >= limit:
            break
    return matched


@router.get("/api/alerts/history")
def api_alerts_history(
    limit: int = 200,
    alertname: str | None = None,
    node: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Watcher event log, newest first. Filters match the CLI's alert-history."""
    limit = clamp_page_limit(limit)
    state = _normalize_history_state(state)
    events, scanned_events = _history_events(alertname, node, state)
    matched = _collect_history(events, limit, alertname, node, state)
    return {
        "events": matched,
        "matched_events": len(matched),
        "scanned_events": scanned_events,
        "log_available": _alert_log_path().exists(),
    }
