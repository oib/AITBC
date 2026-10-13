#!/usr/bin/env python3
"""Dead-man heartbeat to the self-hosted ntfy server (SD-2).

Posts one whitelisted message to the ``aitbc-heartbeat`` topic so the
operator's phone keeps a quiet liveness signal that does not depend on hub:

- ``--kind hourly``: priority 1, message "all quiet" — silent on the phone;
  its *absence* is the signal (dead-man switch). Runs every hour.
- ``--kind daily``: priority 2, message "alive" — visible once a day so a
  missing beat is noticed while glancing at the topic.

The heartbeat replaces the earlier curl-in-cron approach: the bearer token
comes from the environment, so it never sits on a command line where `ps`
would show it. The token and the URL stay on the host (env file
0600 root:aitbc) and are never logged or printed.

Stdlib only (urllib), same as the other monitoring timers. Exits 1 when the
post cannot be delivered so systemd records the failure; exits 0 otherwise.

Usage:
    ntfy-heartbeat.py --kind hourly|daily [--dry-run]

Environment:
    AITBC_HEARTBEAT_URL        ntfy base URL; falls back to
                               AITBC_WATCH_NOTIFY_URL (first entry)
    AITBC_WATCH_NOTIFY_TOKEN   bearer token for the publish — the same
                               write-only `alerts-writer` token the host's
                               watcher uses, on hub and node0 alike
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request

_TOPIC = "aitbc-heartbeat"
_FLEET_HOSTS = {"hub", "hub1", "node0", "node1", "node2"}


def _host() -> str:
    """Fleet name only — the raw hostname is never published."""
    name = socket.gethostname().split(".", 1)[0]
    return name if name in _FLEET_HOSTS else "fleet"


def _post(url: str, kind: str, token: str) -> None:
    priority, message = (1, "all quiet") if kind == "hourly" else (2, "alive")
    payload = json.dumps(
        {
            "topic": _TOPIC,
            "title": f"aitbc heartbeat on {_host()}",
            "message": message,
            "priority": priority,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    # scheme checked by caller; the URL is operator-supplied env config
    urllib.request.urlopen(req, timeout=10).read()  # nosec B310


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=["hourly", "daily"], required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the body; post nothing")
    args = ap.parse_args(argv)

    # First URL only: the heartbeat is a single liveness signal, and posting
    # it to every watcher webhook would double-deliver.
    url = os.environ.get("AITBC_HEARTBEAT_URL", "").split() or os.environ.get("AITBC_WATCH_NOTIFY_URL", "").split()
    token = os.environ.get("AITBC_WATCH_NOTIFY_TOKEN", "")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "topic": _TOPIC,
                    "title": f"aitbc heartbeat on {_host()}",
                    "message": "all quiet" if args.kind == "hourly" else "alive",
                    "priority": 1 if args.kind == "hourly" else 2,
                },
                indent=2,
            )
        )
        return 0
    if not url:
        print("no AITBC_HEARTBEAT_URL or AITBC_WATCH_NOTIFY_URL; heartbeat skipped", file=sys.stderr)
        return 1
    if not url[0].lower().startswith(("http://", "https://")):
        print(f"refusing non-http(s) heartbeat url: {url[0][:40]}", file=sys.stderr)
        return 1
    if not token:
        print("AITBC_WATCH_NOTIFY_TOKEN is unset; heartbeat skipped", file=sys.stderr)
        return 1
    try:
        _post(url[0], args.kind, token)
    except Exception as exc:  # noqa: BLE001 -- any delivery failure alike
        # Strip query/fragment and redact the token so it can never reach the
        # journal even if embedded in the configured URL by mistake.
        detail = str(exc).replace(token, "***")
        print(f"heartbeat POST to {url[0].split('?', 1)[0]} failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
