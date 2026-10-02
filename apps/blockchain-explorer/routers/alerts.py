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

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter()

_ALERT_EVENTS = ("prometheus_alert_firing", "prometheus_alert_resolved", "prometheus_alert_still_firing")
_WATCHER_STALE_SECONDS = 300.0


def _alert_log_path() -> Path:
    return Path(os.environ.get("AITBC_ALERT_LOG", "/var/log/aitbc/alerts.log"))


def _prometheus_url() -> str:
    return os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")


def _read_events() -> list[dict[str, Any]]:
    """Parse the watcher's JSON-lines log. Missing/unparseable lines are skipped."""
    path = _alert_log_path()
    events: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    events.append(record)
    except OSError:
        pass
    return events


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


@router.get("/api/alerts")
async def api_alerts() -> dict[str, Any]:
    """Live alert view: firing/pending alerts plus watcher health.

    Firing alerts come from Prometheus when it answers; silenced state is merged
    in from the event-log replay (Prometheus itself does not know watcher
    silences). With Prometheus down, the log replay is the live view.
    """
    events = _read_events()
    log_firing = _replay_firing(events)
    silenced_keys = {key for key, rec in log_firing.items() if rec.get("silenced")}

    data = await _prometheus_get("/api/v1/alerts")
    watcher = await _watcher_status() if data is not None else None

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
        return {
            "prometheus_ok": True,
            "source": "prometheus",
            "firing": firing,
            "pending": pending,
            "watcher": watcher,
            "log_available": bool(events),
            "checked_at": int(time.time()),
        }

    firing = sorted(
        (_present_firing(rec) for rec in log_firing.values()),
        key=lambda e: str(e.get("alertname") or ""),
    )
    return {
        "prometheus_ok": False,
        "source": "event_log",
        "firing": firing,
        "pending": [],
        "watcher": None,
        "log_available": bool(events),
        "checked_at": int(time.time()),
    }


@router.get("/api/alerts/history")
async def api_alerts_history(
    limit: int = 200,
    alertname: str | None = None,
    node: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Watcher event log, newest first. Filters match the CLI's alert-history."""
    if state is not None and state not in ("firing", "resolved", "silenced"):
        state = None
    events = _read_events()
    matched: list[dict[str, Any]] = []
    for record in reversed(events):
        if alertname and alertname not in str(record.get("alertname") or ""):
            continue
        if node:
            labels = record.get("labels") or {}
            if node not in (str(labels.get("node") or ""), str(labels.get("instance") or "")):
                continue
        if state == "silenced":
            if record.get("silenced") is not True:
                continue
        elif state and record.get("state") != state:
            continue
        matched.append(record)
        if len(matched) >= limit:
            break
    return {
        "events": matched,
        "matched_events": len(matched),
        "scanned_events": len(events),
        "log_available": _alert_log_path().exists(),
    }
