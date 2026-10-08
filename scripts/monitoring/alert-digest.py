#!/usr/bin/env python3
"""Daily digest of warning-severity alert events from the prometheus-watch
alert log (SD-2).

The watcher pushes alert events to AITBC_WATCH_NOTIFY_URL as they happen.
Operator policy: critical alerts push immediately (the watcher is configured
with AITBC_WATCH_NOTIFY_MIN_SEVERITY=critical once the ntfy destination is
set), warnings are collected here instead, and info stays in alerts.log.

This script is that digest: it reads the watcher's JSON-lines alert log,
collects the warning-severity firing/resolved events from the last window,
and POSTs one plain-text summary per notify URL — one message a day, not one
per event. With nothing to report it posts nothing; a dead digest is instead
caught by the weekly synthetic test alert, not by silence here.

Stdlib only (urllib), same as the other monitoring timers. Exits 1 when a
post fails so systemd records the failure; exits 0 otherwise.

Usage:
    alert-digest.py [--alert-log /var/log/aitbc/alerts.log] [--since-hours 24]
                    [--notify-url URL ...] [--dry-run]

Environment:
    AITBC_WATCH_NOTIFY_URL   space-separated fallback for --notify-url
    (the same env file the watcher reads, so the digest follows the same
    destination once the operator sets it)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

_DIGEST_EVENTS = ("prometheus_alert_firing", "prometheus_alert_resolved", "prometheus_alert_still_firing")


def _record_matches(record: dict, since_unix: float) -> bool:
    """True when a parsed log record is a warning-severity alert event in the window."""
    if record.get("event") not in _DIGEST_EVENTS:
        return False
    if record.get("severity") != "warning":
        return False
    ts = record.get("timestamp_unix")
    return isinstance(ts, (int, float)) and ts >= since_unix


def _accumulate(groups: dict[str, dict], record: dict) -> None:
    g = groups[record.get("alertname") or "unknown"]
    kind = {"prometheus_alert_firing": "firing", "prometheus_alert_resolved": "resolved"}.get(record["event"], "still_firing")
    g[kind] += 1
    instance = (record.get("labels") or {}).get("instance")
    if instance:
        g["instances"].add(instance)
    if record.get("summary"):
        g["summary"] = record["summary"]


def _collect(log_path: Path, since_unix: float) -> dict[str, dict]:
    """warning-severity alert events newer than since_unix, grouped by alertname."""
    groups: dict[str, dict] = defaultdict(
        lambda: {"firing": 0, "resolved": 0, "still_firing": 0, "instances": set(), "summary": None}
    )
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return groups
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if _record_matches(record, since_unix):
            _accumulate(groups, record)
    return groups


def _render(groups: dict[str, dict], since_hours: int, host: str) -> str:
    total_events = sum(g["firing"] + g["resolved"] + g["still_firing"] for g in groups.values())
    header = f"AITBC warning digest - {host} - last {since_hours}h: {total_events} events across {len(groups)} alerts"
    rows = []
    for name in sorted(groups):
        g = groups[name]
        parts = []
        if g["firing"]:
            parts.append(f"{g['firing']} firing")
        if g["still_firing"]:
            parts.append(f"{g['still_firing']} still-firing reminders")
        if g["resolved"]:
            parts.append(f"{g['resolved']} resolved")
        where = f" [{', '.join(sorted(g['instances']))}]" if g["instances"] else ""
        summary = f" - {g['summary']}" if g["summary"] else ""
        rows.append(f"{name}{where}: {', '.join(parts)}{summary}")
    return header + "\n" + "\n".join(rows)


def _post(urls: list[str], body: str) -> int:
    """One POST per URL, plain-text body (ntfy renders it as the message)."""
    failures = 0
    for url in urls:
        # The URL comes from operator env, but urlopen honours file: and custom
        # schemes too — restrict to http(s) so a malformed line cannot read files.
        if not url.lower().startswith(("http://", "https://")):
            print(f"refusing non-http(s) notify url: {url[:40]}", file=sys.stderr)
            failures += 1
            continue
        try:
            req = urllib.request.Request(url, data=body.encode(), headers={"Content-Type": "text/plain"})
            # scheme is checked against http/https above; the URL is operator-supplied config
            urllib.request.urlopen(req, timeout=10).read()  # nosec B310
        except Exception as exc:  # noqa: BLE001 -- any delivery failure alike
            failures += 1
            print(f"digest POST to {url} failed: {exc}", file=sys.stderr)
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alert-log", default="/var/log/aitbc/alerts.log", type=Path)
    ap.add_argument("--since-hours", type=int, default=24)
    ap.add_argument("--notify-url", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true", help="print the digest body; post nothing")
    args = ap.parse_args(argv)

    urls = list(args.notify_url)
    if not urls:
        urls = os.environ.get("AITBC_WATCH_NOTIFY_URL", "").split()

    groups = _collect(args.alert_log, time.time() - args.since_hours * 3600)
    if not groups:
        print(f"no warning-severity events in the last {args.since_hours}h; nothing to send")
        return 0

    body = _render(groups, args.since_hours, socket.gethostname())
    if args.dry_run:
        print(body)
        return 0
    if not urls:
        print("no --notify-url and AITBC_WATCH_NOTIFY_URL unset; digest stays local", file=sys.stderr)
        print(body)
        return 0
    return 1 if _post(urls, body) else 0


if __name__ == "__main__":
    sys.exit(main())
