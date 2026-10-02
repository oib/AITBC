"""Prometheus querying and alerting commands for AITBC CLI."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import socket
from typing import cast
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import httpx

from aitbc.aitbc_logging import configure_logging

from ..utils import error, output, success
from ..utils.http_client import get_logger

logger = get_logger(__name__)

DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"


def _prometheus_url(ctx: click.Context, url: str | None) -> str:
    """Resolve Prometheus URL from option, config, or default."""
    if url:
        return url.rstrip("/")
    config = ctx.obj.get("config")
    if config is not None:
        configured = getattr(config, "prometheus_url", None)
        if configured:
            return str(configured).rstrip("/")
    return DEFAULT_PROMETHEUS_URL


def _prometheus_get(url: str, path: str, params: dict[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
    """Issue a GET against the Prometheus expression/admin API."""
    try:
        response = httpx.get(f"{url}{path}", params=params, timeout=timeout)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
    except httpx.RequestError as e:
        error(f"Could not reach Prometheus at {url}: {e}")
        return {}
    except httpx.HTTPStatusError as e:
        error(f"Prometheus returned {e.response.status_code}: {e}")
        return {}


@click.group(
    epilog="""Examples:

  aitbc prometheus targets

  aitbc prometheus query --expr 'up'"""
)
def prometheus():
    """Query Prometheus, inspect targets, rules, alerts, and validate configuration."""
    pass


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus targets

  aitbc prometheus targets --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def targets(ctx: click.Context, prometheus_url: str | None):
    """Show the health of every Prometheus scrape target."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/targets")
    active = data.get("data", {}).get("activeTargets", [])
    dropped = data.get("data", {}).get("droppedTargets", [])

    result = {
        "targets": [
            {
                "job": t.get("labels", {}).get("job"),
                "instance": t.get("labels", {}).get("instance"),
                "health": t.get("health"),
                "last_error": t.get("lastError", ""),
            }
            for t in active
        ],
        "dropped_count": len(dropped),
    }
    output(result, ctx.obj["output_format"])


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus rules

  aitbc prometheus rules --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def rules(ctx: click.Context, prometheus_url: str | None):
    """List loaded Prometheus recording and alerting rules."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/rules")
    result = []
    for group in data.get("data", {}).get("groups", []):
        result.append(
            {
                "name": group.get("name"),
                "file": group.get("file"),
                "rules": [r.get("name") for r in group.get("rules", [])],
            }
        )
    output({"groups": result}, ctx.obj["output_format"])


ALERT_LOG_MAX_BYTES = 5 * 1024 * 1024
ALERT_LOG_BACKUPS = 5


def _alert_id(alert: dict[str, Any]) -> str:
    labels = alert.get("labels", {})
    return f"{labels.get('alertname')}{json.dumps(labels, sort_keys=True)}"


def _open_alert_log(path: str) -> logging.Logger | None:
    """A logger that writes bare alert-event lines, and nothing else, to ``path`` (rotated at 5 MiB, 5 backups).

    The service log of this watcher carries one httpx line per poll, so an alert event is easy to lose in it. This file
    is what an operator tails. An unwritable path degrades to the journal and the service log, with one warning.
    """
    try:
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=ALERT_LOG_MAX_BYTES, backupCount=ALERT_LOG_BACKUPS, encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("alert log %s is not writable (%s); alerts go to the journal and the service log only", path, exc)
        return None
    handler.setFormatter(logging.Formatter("%(message)s"))
    alert_logger = logging.getLogger("aitbc.alert-events")
    alert_logger.propagate = False
    alert_logger.setLevel(logging.INFO)
    alert_logger.handlers = [handler]
    return alert_logger


def _seconds_since(active_at: str | None) -> int | None:
    if not active_at:
        return None
    try:
        started = datetime.fromisoformat(active_at)
    except ValueError:
        return None
    return int((datetime.now(UTC) - started).total_seconds())


def _silence_expired(entry: dict[str, Any], now: datetime) -> bool:
    until = entry.get("until")
    if not until:
        return False
    try:
        expires = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
    except ValueError:
        # An unparseable "until" is a permanent silence rather than a broken one.
        return False
    return expires <= now


def _silence_for(alert: dict[str, Any], silences: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The first active silence entry matching this alert, if any.

    An entry needs a non-empty ``match`` -- alertname and/or a label subset -- so an
    accidental ``{"match": {}}`` cannot mute the whole fleet.
    """
    labels = alert.get("labels", {})
    for entry in silences:
        match = entry.get("match") or {}
        name = match.get("alertname")
        wanted = match.get("labels") or {}
        if not name and not wanted:
            continue
        if _silence_expired(entry, now):
            continue
        if name and name != labels.get("alertname"):
            continue
        if all(str(labels.get(key)) == str(value) for key, value in wanted.items()):
            return entry
    return None


def _load_silences(path: str | None, cache: dict[str, Any]) -> list[dict[str, Any]]:
    """Reload the silence file whenever its mtime changes.

    A missing file means "no silences"; a malformed one fails open -- silence
    problems must never mute alerts -- with one warning per broken state.
    """
    if not path:
        return []
    try:
        mtime: float | None = os.path.getmtime(path)
    except OSError:
        mtime = None
    if mtime is not None and mtime == cache.get("mtime"):
        return cast(list[dict[str, Any]], cache.get("entries") or [])
    cache["mtime"] = mtime
    entries: list[dict[str, Any]] = []
    if mtime is not None:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = [e for e in raw if isinstance(e, dict)]
        except (OSError, ValueError) as exc:
            if not cache.get("warned"):
                logger.warning("silence file %s unreadable (%s); alerts are unsilenced", path, exc)
                cache["warned"] = True
        else:
            cache["warned"] = False
    cache["entries"] = entries
    return entries


def _notify(urls: tuple[str, ...], record: dict[str, Any], stats: dict[str, Any]) -> None:
    """POST the event record to every notify URL, with one retry per URL.

    Delivery failure is counted and logged but never interrupts the watch loop --
    the alert is still on disk in the event log.
    """
    for notify_url in urls:
        for attempt in range(2):
            try:
                httpx.post(notify_url, json=record, timeout=5).raise_for_status()
                break
            except Exception as exc:  # noqa: BLE001 -- transport and HTTP failures are alike here
                if attempt == 1:
                    stats["notify_errors"] = stats.get("notify_errors", 0) + 1
                    logger.warning("notify POST to %s failed: %s", notify_url, exc)


def _write_metrics_file(path: str, gauges: dict[str, float], warn: dict[str, bool]) -> None:
    """Atomically write the watcher's own heartbeat as a node-exporter textfile.

    Written once per poll so ``time() - aitbc_prometheus_watch_poll_timestamp_seconds``
    exposes a dead watcher even while the events it would emit are absent.
    """
    lines = [
        "# HELP aitbc_prometheus_watch_poll_timestamp_seconds Unix time of the watcher's last poll attempt.",
        "# TYPE aitbc_prometheus_watch_poll_timestamp_seconds gauge",
        f"aitbc_prometheus_watch_poll_timestamp_seconds {gauges['poll_unix']}",
        "# HELP aitbc_prometheus_watch_prometheus_reachable Whether the last poll got an answer (1) or not (0).",
        "# TYPE aitbc_prometheus_watch_prometheus_reachable gauge",
        f"aitbc_prometheus_watch_prometheus_reachable {int(gauges['reachable'])}",
        "# HELP aitbc_prometheus_watch_firing Currently firing alerts, excluding silenced ones.",
        "# TYPE aitbc_prometheus_watch_firing gauge",
        f"aitbc_prometheus_watch_firing {int(gauges['firing'])}",
        "# HELP aitbc_prometheus_watch_silenced_firing Currently firing alerts suppressed by the silence file.",
        "# TYPE aitbc_prometheus_watch_silenced_firing gauge",
        f"aitbc_prometheus_watch_silenced_firing {int(gauges['silenced_firing'])}",
        "# HELP aitbc_prometheus_watch_notify_errors_total Cumulative failed webhook deliveries.",
        "# TYPE aitbc_prometheus_watch_notify_errors_total counter",
        f"aitbc_prometheus_watch_notify_errors_total {int(gauges['notify_errors'])}",
    ]
    try:
        fd, tmp = tempfile.mkstemp(dir=str(Path(path).parent), prefix=".watch-", suffix=".tmp")
        # mkstemp lands at 0600; node-exporter runs as the prometheus user and
        # must be able to read the finished file, so widen before the rename.
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        warn["failed"] = False
    except OSError as exc:
        if not warn.get("failed"):
            logger.warning("metrics file %s is not writable (%s); heartbeat metrics disabled", path, exc)
            warn["failed"] = True


def _sd_notify_watchdog() -> None:
    """systemd watchdog ping; a no-op outside systemd (NOTIFY_SOCKET unset).

    Sent as a raw datagram from this process — a ``systemd-notify`` subprocess
    would send with the child's PID, which the unit's default
    ``NotifyAccess=main`` silently discards (seen live: watchdog killed the
    watcher every WatchdogSec on hub/node0).
    """
    sock_addr = os.environ.get("NOTIFY_SOCKET")
    if not sock_addr:
        return
    if sock_addr.startswith("@"):
        sock_addr = "\0" + sock_addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"WATCHDOG=1", sock_addr)
    except OSError:
        pass


_DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_since(value: str | None) -> float | None:
    """Cutoff epoch seconds for ``--since``: a duration like 24h/30m or an ISO timestamp."""
    if not value:
        return None
    match = _DURATION_RE.match(value.strip())
    if match:
        unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
        return time.time() - int(match.group(1)) * unit
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise click.BadParameter(f"--since must be a duration like 24h or an ISO timestamp, got {value!r}") from None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.timestamp()


def _event_epoch(record: dict[str, Any]) -> float | None:
    """Epoch seconds of an alert-log record -- timestamp_unix if present, else the ISO field."""
    unix_ts = record.get("timestamp_unix")
    if isinstance(unix_ts, int | float):
        return float(unix_ts)
    raw = record.get("timestamp")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.timestamp()


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus alerts

  aitbc prometheus alerts --watch --interval 15

  aitbc prometheus alerts --watch --alert-log /var/log/aitbc/alerts.log \\
      --notify-url https://ops.example/hook --silence-file /etc/aitbc/silences.json"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.option("--watch", is_flag=True, help="Poll continuously and emit firing and resolved alerts")
@click.option(
    "--interval",
    type=int,
    default=15,
    envvar="AITBC_WATCH_INTERVAL",
    help="Poll interval in seconds (watch mode)",
)
@click.option(
    "--emit/--no-emit",
    default=True,
    help="Emit one structured log line per alert state change to stdout and the service log (watch mode)",
)
@click.option(
    "--alert-log",
    "alert_log_path",
    type=click.Path(dir_okay=False),
    default=None,
    envvar="AITBC_WATCH_ALERT_LOG",
    help="Also append every alert state change (firing, resolved) as one JSON line to this file, rotated at 5 MiB "
    "(watch mode)",
)
@click.option(
    "--notify-url",
    "notify_urls",
    multiple=True,
    envvar="AITBC_WATCH_NOTIFY_URL",
    help="POST every alert event as a JSON body to this webhook URL; repeatable (env: space-separated) (watch mode)",
)
@click.option(
    "--silence-file",
    "silence_file",
    type=click.Path(dir_okay=False),
    default=None,
    envvar="AITBC_WATCH_SILENCE_FILE",
    help='JSON silence list reloaded each poll, e.g. [{"match": {"alertname": "ServiceDown", "labels": {"instance": '
    '"x:9100"}}, "until": "2026-10-05T00:00:00Z", "reason": "maintenance"}]; silenced events are recorded but not '
    "notified (watch mode)",
)
@click.option(
    "--remind-interval",
    type=int,
    default=0,
    envvar="AITBC_WATCH_REMIND_INTERVAL",
    help="Re-emit and re-notify a still-firing alert every N seconds; 0 disables (watch mode)",
)
@click.option(
    "--metrics-file",
    "metrics_file",
    type=click.Path(dir_okay=False),
    default=None,
    envvar="AITBC_WATCH_METRICS_FILE",
    help="Write node-exporter textfile heartbeat metrics to this path every poll (watch mode)",
)
@click.pass_context
def alerts(
    ctx: click.Context,
    prometheus_url: str | None,
    watch: bool,
    interval: int,
    emit: bool,
    alert_log_path: str | None,
    notify_urls: tuple[str, ...],
    silence_file: str | None,
    remind_interval: int,
    metrics_file: str | None,
):
    """Show current Prometheus alerts and optionally watch for firing and resolved alerts."""
    url = _prometheus_url(ctx, prometheus_url)

    def _fetch() -> list[dict[str, Any]] | None:
        """The alerts Prometheus reports, or None when it did not answer (which is not the same as "no alerts")."""
        data = _prometheus_get(url, "/api/v1/alerts")
        if data.get("status") != "success":
            return None
        return cast(list[dict[str, Any]], data.get("data", {}).get("alerts", []))

    def _present(raw_alerts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "alerts": [
                {
                    "name": a.get("labels", {}).get("alertname"),
                    "state": a.get("state"),
                    "severity": a.get("labels", {}).get("severity"),
                    "summary": a.get("annotations", {}).get("summary"),
                    "description": a.get("annotations", {}).get("description"),
                    "active_at": a.get("activeAt"),
                    "labels": a.get("labels"),
                }
                for a in raw_alerts
            ],
            "firing": sum(1 for a in raw_alerts if a.get("state") == "firing"),
            "pending": sum(1 for a in raw_alerts if a.get("state") == "pending"),
            "checked_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        }

    if not watch:
        raw_now = _fetch()
        output(_present(raw_now or []), ctx.obj["output_format"])
        return

    # Watch mode is the one path in this CLI that runs as a long-lived service
    # (aitbc-prometheus-watch), so it is the one path that should hold open a
    # rotating file in the service log tree. Configuring it above this line would
    # make every one-shot `aitbc prometheus alerts` -- run by whoever is at the
    # keyboard -- try to create /var/log/aitbc/prometheus-watch as them.
    configure_logging(level="INFO", service_name="prometheus-watch", to_file=True)
    alert_log = _open_alert_log(alert_log_path) if alert_log_path else None

    stats: dict[str, Any] = {"notify_errors": 0}

    def _event(
        name: str,
        alert: dict[str, Any] | None,
        *,
        via: str,
        silenced: dict[str, Any] | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "event": name,
            "via": via,
            "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "timestamp_unix": int(time.time()),
        }
        if alert is not None:
            labels = alert.get("labels", {})
            record.update(
                {
                    "alertname": labels.get("alertname"),
                    "state": "resolved" if name == "prometheus_alert_resolved" else "firing",
                    "severity": labels.get("severity"),
                    "summary": alert.get("annotations", {}).get("summary"),
                    "description": alert.get("annotations", {}).get("description"),
                    "labels": labels,
                    "active_at": alert.get("activeAt"),
                }
            )
            if name == "prometheus_alert_resolved":
                record["duration_seconds"] = _seconds_since(alert.get("activeAt"))
        if silenced is not None:
            record["silenced"] = True
            if silenced.get("reason"):
                record["silence_reason"] = silenced["reason"]
        if extra:
            record.update(extra)
        line = json.dumps(record, sort_keys=True)
        if alert_log is not None:
            alert_log.info(line)
        if emit:
            # Structured line for journalctl / external watchers
            click.echo(line, file=sys.stdout)
            if name in ("prometheus_alert_firing", "prometheus_alert_still_firing") and silenced is None:
                logger.warning(line)
            else:
                logger.info(line)
        # A silence suppresses the push, not the record: the event still lands in
        # the alert log and the journal so "what happened" stays auditable.
        if silenced is None:
            _notify(notify_urls, record, stats)

    # Alert state is tracked across polls: an alert is reported when it starts firing (again, if it had resolved) and
    # when it stops. A poll Prometheus did not answer changes nothing -- it must not read as "everything resolved".
    # firing maps alert_id -> {"alert": ..., "silenced": bool, "last_notify": monotonic|None}.
    firing: dict[str, dict[str, Any]] = {}
    unreachable = False
    first_poll = True
    silence_cache: dict[str, Any] = {"mtime": None, "entries": [], "warned": False}
    metrics_warn: dict[str, bool] = {}
    try:
        while True:
            now_mono = time.monotonic()
            raw = _fetch()
            if raw is None:
                if not unreachable:
                    logger.warning("Prometheus did not answer; alert state is unknown until it does")
                unreachable = True
            else:
                if unreachable:
                    logger.info("Prometheus answers again")
                    # Restart the reminder clocks: an alert that survived an outage
                    # should not burst a reminder the moment Prometheus is back.
                    for tracked in firing.values():
                        tracked["last_notify"] = now_mono
                unreachable = False
                summary = _present(raw)
                if ctx.obj["output_format"] == "json":
                    output(summary, "json")
                now_wall = datetime.now(UTC)
                silences = _load_silences(silence_file, silence_cache)
                current = {_alert_id(a): a for a in raw if a.get("state") == "firing"}
                if first_poll:
                    _event(
                        "prometheus_watch_started",
                        None,
                        via="startup",
                        silenced=None,
                        extra={
                            "firing_count": len(current),
                            "firing_alertnames": sorted({a.get("labels", {}).get("alertname") for a in current.values()}),
                        },
                    )
                for alert_id, alert in current.items():
                    silence = _silence_for(alert, silences, now_wall)
                    state = firing.get(alert_id)
                    if state is None:
                        _event(
                            "prometheus_alert_firing",
                            alert,
                            via="startup" if first_poll else "transition",
                            silenced=silence,
                        )
                        firing[alert_id] = {
                            "alert": alert,
                            "silenced": silence is not None,
                            "last_notify": None if silence is not None else now_mono,
                        }
                        continue
                    state["alert"] = alert
                    if state["silenced"] and silence is None:
                        # The silence expired or was removed while the alert still
                        # fires: it becomes somebody's problem again.
                        _event("prometheus_alert_firing", alert, via="silence_expired", silenced=None)
                        state["last_notify"] = now_mono
                    elif (
                        silence is None
                        and remind_interval > 0
                        and state["last_notify"] is not None
                        and now_mono - state["last_notify"] >= remind_interval
                    ):
                        _event("prometheus_alert_still_firing", alert, via="reminder", silenced=None)
                        state["last_notify"] = now_mono
                    state["silenced"] = silence is not None
                for alert_id, prev in list(firing.items()):
                    if alert_id in current:
                        continue
                    # A resolve is silenced only if a silence still matches now --
                    # one that expired mid-flight already re-fired the alert.
                    silence = _silence_for(prev["alert"], silences, now_wall)
                    _event("prometheus_alert_resolved", prev["alert"], via="transition", silenced=silence)
                    firing.pop(alert_id)
                first_poll = False
            _sd_notify_watchdog()
            if metrics_file:
                _write_metrics_file(
                    metrics_file,
                    {
                        "poll_unix": float(time.time()),
                        "reachable": 0.0 if unreachable else 1.0,
                        "firing": float(sum(1 for s in firing.values() if not s["silenced"])),
                        "silenced_firing": float(sum(1 for s in firing.values() if s["silenced"])),
                        "notify_errors": float(stats.get("notify_errors", 0)),
                    },
                    metrics_warn,
                )
            time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("\nWatch stopped")


@prometheus.command(
    name="alert-history",
    epilog="""Examples:

  aitbc prometheus alert-history

  aitbc prometheus alert-history --since 24h --node node0

  aitbc prometheus alert-history --path /var/log/aitbc/alerts.log.1 --alertname ServiceDown""",
)
@click.option(
    "--path",
    "log_path",
    default="/var/log/aitbc/alerts.log",
    type=click.Path(dir_okay=False),
    help="Watcher alert log to read (default: the service's own log)",
)
@click.option(
    "--since",
    default=None,
    help="Only events newer than this: a duration like 30m/24h/7d or an ISO timestamp",
)
@click.option("--alertname", default=None, help="Substring match on the alert name")
@click.option(
    "--state",
    "state_filter",
    type=click.Choice(["firing", "resolved", "silenced"]),
    default=None,
    help="Only events in this state; 'silenced' selects events recorded under a silence",
)
@click.option(
    "--node",
    "node_filter",
    default=None,
    help="Only events whose labels.node (or labels.instance) matches this string",
)
@click.option("--last", "last_n", type=int, default=None, help="Keep only the newest N matching events")
@click.pass_context
def alert_history(
    ctx: click.Context,
    log_path: str,
    since: str | None,
    alertname: str | None,
    state_filter: str | None,
    node_filter: str | None,
    last_n: int | None,
):
    """Read the watcher's alert log: matching events plus the set still firing at end of log.

    A silenced event is recorded but never pushed, so this is the only place to see
    them. Rotated files can be read by passing them to --path.
    """
    path = Path(log_path)
    events: list[dict[str, Any]] = []
    if path.exists():
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
    cutoff = _parse_since(since)

    def _identity(record: dict[str, Any]) -> bool:
        """Filters that also scope the firing-now replay."""
        if alertname and alertname not in str(record.get("alertname") or ""):
            return False
        if node_filter:
            labels = record.get("labels") or {}
            if node_filter not in (str(labels.get("node") or ""), str(labels.get("instance") or "")):
                return False
        return True

    def _keep(record: dict[str, Any]) -> bool:
        if not _identity(record):
            return False
        if cutoff is not None:
            epoch = _event_epoch(record)
            if epoch is None or epoch < cutoff:
                return False
        if state_filter == "silenced":
            return record.get("silenced") is True
        if state_filter:
            return record.get("state") == state_filter
        return True

    matched = [e for e in events if _keep(e)]
    if last_n is not None:
        matched = matched[-last_n:]

    # firing-now replays the identity-filtered stream and deliberately ignores
    # --since/--state: a resolve outside the window still clears its firing.
    firing_now: dict[str, dict[str, Any]] = {}
    for record in events:
        if not _identity(record):
            continue
        name = record.get("event")
        if name not in ("prometheus_alert_firing", "prometheus_alert_resolved", "prometheus_alert_still_firing"):
            continue
        key = f"{record.get('alertname')}{json.dumps(record.get('labels') or {}, sort_keys=True)}"
        if name == "prometheus_alert_resolved":
            firing_now.pop(key, None)
        else:
            firing_now[key] = record

    output(
        {
            "path": str(path),
            "scanned_events": len(events),
            "matched_events": len(matched),
            "events": matched,
            "firing_now": [
                {
                    "alertname": record.get("alertname"),
                    "since": record.get("timestamp"),
                    "labels": record.get("labels"),
                    "silenced": bool(record.get("silenced")),
                }
                for record in firing_now.values()
            ],
        },
        ctx.obj["output_format"],
    )


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus query --expr 'up'

  aitbc prometheus query --expr 'up' --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--expr", "expr", required=True, help="The Expr.")
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.option("--time", default=None, help="Evaluation timestamp (RFC3339 or Unix)")
@click.option("--timeout", default=30, help="Query timeout in seconds")
@click.pass_context
def query(ctx: click.Context, expr: str, prometheus_url: str | None, time: str | None, timeout: int):
    """Run a PromQL query against Prometheus."""
    url = _prometheus_url(ctx, prometheus_url)
    params: dict[str, Any] = {"query": expr, "timeout": timeout}
    if time:
        params["time"] = time
    data = _prometheus_get(url, "/api/v1/query", params=params, timeout=timeout + 5)
    output(data.get("data", {}), ctx.obj["output_format"])


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus check

  aitbc prometheus check --config /etc/prometheus/prometheus.yml --rules /etc/prometheus/aitbc_rules.yml"""
)
@click.option("--config", "config_path", default="/etc/prometheus/prometheus.yml", help="Prometheus config file")
@click.option("--rules", "rules_path", default="/etc/prometheus/aitbc_rules.yml", help="Prometheus rules file")
@click.pass_context
def check(ctx: click.Context, config_path: str, rules_path: str):
    """Validate Prometheus config and rules with promtool."""
    config_file = Path(config_path)
    rules_file = Path(rules_path)
    results: dict[str, Any] = {"config": None, "rules": None}

    if config_file.exists():
        try:
            proc = subprocess.run(
                ["promtool", "check", "config", str(config_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results["config"] = {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            results["config"] = {"ok": False, "output": "promtool not found in PATH"}
        except subprocess.TimeoutExpired:
            results["config"] = {"ok": False, "output": "promtool timed out"}
    else:
        results["config"] = {"ok": False, "output": f"config not found: {config_file}"}

    if rules_file.exists():
        try:
            proc = subprocess.run(
                ["promtool", "check", "rules", str(rules_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results["rules"] = {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            results["rules"] = {"ok": False, "output": "promtool not found in PATH"}
        except subprocess.TimeoutExpired:
            results["rules"] = {"ok": False, "output": "promtool timed out"}
    else:
        results["rules"] = {"ok": False, "output": f"rules not found: {rules_file}"}

    all_ok = all(r["ok"] for r in results.values() if r is not None)
    output(results, ctx.obj["output_format"])
    if all_ok:
        success("Prometheus config and rules are valid")
    else:
        error("Prometheus config or rules validation failed")


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus series

  aitbc prometheus series --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def series(ctx: click.Context, prometheus_url: str | None):
    """Show the count of currently loaded metric series for cardinality."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/label/__name__/values")
    names = data.get("data", [])
    output({"metric_names": len(names)}, ctx.obj["output_format"])
