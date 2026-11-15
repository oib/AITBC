#!/usr/bin/env python3
"""Persistent ntfy alert subscriber + bridge (ALERT-DELIVERY-1, #2122).

Long-polls the self-hosted ntfy JSON stream for ``aitbc-alerts`` and:

- appends every message to ``/var/log/aitbc/ntfy-alerts.jsonl`` (on-host
  forensic record — alerts are preserved even with zero subscribers);
- republishes each message to ``aitbc-alerts-bridge`` so a second
  subscription path exists for the operator/device or future consumers.

Reconnects with backoff on stream errors. Stdlib only. The publish token
comes from the environment (AITBC_WATCH_NOTIFY_TOKEN) — never logged.

Env:
    AITBC_HEARTBEAT_URL / AITBC_WATCH_NOTIFY_URL  ntfy base URL
    NTFY_BRIDGE_TOKEN                            read aitbc-alerts + write
                                                 aitbc-alerts-bridge bearer
    NTFY_ALERTS_TOPIC       (default aitbc-alerts)
    NTFY_BRIDGE_TOPIC       (default aitbc-alerts-bridge)
    NTFY_BRIDGE_LOG         (default /var/log/aitbc/ntfy-alerts.jsonl)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

TOPIC = os.environ.get("NTFY_ALERTS_TOPIC", "aitbc-alerts")
BRIDGE = os.environ.get("NTFY_BRIDGE_TOPIC", "aitbc-alerts-bridge")
LOG = os.environ.get("NTFY_BRIDGE_LOG", "/var/log/aitbc/ntfy-alerts.jsonl")


def _base() -> str:
    url = os.environ.get("AITBC_HEARTBEAT_URL") or os.environ.get("AITBC_WATCH_NOTIFY_URL", "")
    return url.split(",")[0].strip().rstrip("/")


def _token() -> str:
    return os.environ.get("NTFY_BRIDGE_TOKEN", "")


def _republish(event: dict) -> None:
    token = _token()
    if not token:
        return
    # Skip replayed cache entries on reconnect — only bridge fresh alerts.
    msg_time = event.get("time", 0)
    if isinstance(msg_time, (int, float)) and time.time() - msg_time > 600:
        return
    body = {
        "topic": BRIDGE,
        "message": event.get("message", ""),
        "title": event.get("title", "aitbc alert"),
        "priority": event.get("priority", 3),
        "tags": event.get("tags", []),
    }
    req = urllib.request.Request(
        f"{_base()}/{BRIDGE}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()  # nosec B310
    except Exception as exc:  # noqa: BLE001 - bridge must never die on republish failure
        print(f"bridge republish failed: {exc}", file=sys.stderr)


def main() -> int:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    backoff = 5
    while True:
        try:
            url = f"{_base()}/{TOPIC}/json?poll=1"
            headers = {"Accept": "application/x-ndjson"}
            token = _token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp, open(LOG, "a", buffering=1) as fh:  # nosec B310
                backoff = 5
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("event") not in ("message", "keepalive"):
                        continue
                    fh.write(json.dumps({"rx": time.time(), "event": event}) + "\n")
                    if event.get("event") == "message":
                        _republish(event)
        except Exception as exc:  # noqa: BLE001 - subscriber must survive any stream failure
            print(f"stream error: {exc}; retry in {backoff}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    sys.exit(main())
