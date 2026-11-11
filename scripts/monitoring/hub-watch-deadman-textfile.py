#!/usr/bin/env python3
"""Export hub-side prometheus-watch dead-man state for Prometheus (hub1 only).

Hub cannot page for its own watcher: when hub's aitbc-prometheus-watch dies,
PrometheusWatchStale fires on hub's Prometheus, but the watcher IS the
notification path — nothing pushes the alert (SELF-WATCH-DEADMAN-1, #1820).
hub1's failover scrape of hub's /prom-metrics sees scrape health (ServiceDown)
but NOT alert state: Prometheus does not export ALERTS/ALERTS_FOR_STATE on
/metrics. This exporter closes that gap by querying hub's alert API through
nginx /prom-api-query (same IP allowlist + bearer token as /prom-write) and
writing the result into hub1's node_exporter textfile, where aitbc_hub1_rules.yml
turns it into a critical alert on hub1's own watcher.

Emits:

    aitbc_hub_watch_deadman                1 while hub's
                                           PrometheusWatchStale alert is
                                           firing, else 0
    aitbc_hub_watch_api_up                 1 when the query round-trip
                                           succeeded, else 0
    aitbc_hub_watch_probe_timestamp_seconds  unix time this run finished

A failed probe still writes all three metrics (api_up=0, deadman=0,
timestamp=now): HubPromApiUnreachable warns on a blind spot while
HubWatchProbeStale stays quiet, so "cannot check" never masquerades as
"watch is fine". Run by aitbc-hub-watch-deadman.timer; stdlib only.

Environment:
    AITBC_HUB_PROM_QUERY_URL   full URL of the instant-query endpoint
                               (default https://hub.aitbc.bubuit.net/prom-api-query)
    AITBC_HUB_PROM_TOKEN_FILE  bearer token file, one token per file
                               (default /etc/prometheus/hub-remote-write.token)
    AITBC_HUB_WATCH_ALERT      alertname to watch
                               (default PrometheusWatchStale)
    AITBC_TEXTFILE_DIR         default /var/lib/prometheus/node-exporter
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUTPUT_NAME = "aitbc_hub_watch_deadman.prom"

DEFAULT_QUERY_URL = "https://hub.aitbc.bubuit.net/prom-api-query"
DEFAULT_TOKEN_FILE = "/etc/prometheus/hub-remote-write.token"
DEFAULT_ALERT = "PrometheusWatchStale"
TIMEOUT_SECONDS = 10.0


def _promql(alertname: str) -> str:
    # node="" selects hub's OWN alert series: hub has no `node` external
    # label, while every remote host's ALERTS arrive via remote_write with
    # node=<host> attached — without the matcher a remote watcher's dead-man
    # would false-positive as "hub watch dead".
    return f'ALERTS{{alertname="{alertname}",alertstate="firing",node=""}}'


def fetch_firing(query_url: str, token: str, alertname: str) -> bool:
    """Return True when the watched alert has firing series on hub.

    Raises on any transport/HTTP/parse failure — the caller turns that into
    api_up=0 rather than guessing.
    """
    # The URL comes from operator env, but urlopen honours file: and custom
    # schemes too — restrict to http(s) so a malformed value cannot read files.
    if not query_url.lower().startswith(("http://", "https://")):
        raise ValueError(f"refusing non-http(s) query url: {query_url[:40]}")
    sep = "&" if "?" in query_url else "?"
    url = f"{query_url}{sep}{urllib.parse.urlencode({'query': _promql(alertname)})}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    # scheme is checked against http/https above; the URL is operator-supplied config
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise ValueError(f"prometheus query status={payload.get('status')!r}")
    return bool(payload.get("data", {}).get("result"))


def render(deadman: int, api_up: int, now: float) -> str:
    return (
        "# HELP aitbc_hub_watch_deadman 1 while hub's PrometheusWatchStale alert is firing.\n"
        "# TYPE aitbc_hub_watch_deadman gauge\n"
        f"aitbc_hub_watch_deadman {deadman}\n"
        "# HELP aitbc_hub_watch_api_up 1 when the hub alert-API probe succeeded.\n"
        "# TYPE aitbc_hub_watch_api_up gauge\n"
        f"aitbc_hub_watch_api_up {api_up}\n"
        "# HELP aitbc_hub_watch_probe_timestamp_seconds Unix time the last probe run finished.\n"
        "# TYPE aitbc_hub_watch_probe_timestamp_seconds gauge\n"
        f"aitbc_hub_watch_probe_timestamp_seconds {int(now)}\n"
    )


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_hub_watch.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    query_url = os.environ.get("AITBC_HUB_PROM_QUERY_URL", DEFAULT_QUERY_URL)
    token_file = os.environ.get("AITBC_HUB_PROM_TOKEN_FILE", DEFAULT_TOKEN_FILE)
    alertname = os.environ.get("AITBC_HUB_WATCH_ALERT", DEFAULT_ALERT)
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    now = time.time()

    api_up = 0
    deadman = 0
    try:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        if token:
            deadman = int(fetch_firing(query_url, token, alertname))
            api_up = 1
    except (OSError, ValueError) as e:
        # URLError/HTTPError are OSError subclasses; JSONDecodeError is a
        # ValueError. Any probe failure is api_up=0, never a skipped write.
        print(f"aitbc-hub-watch-deadman: probe failed: {e}", file=sys.stderr)

    try:
        write_atomic(directory, render(deadman, api_up, now))
    except OSError as e:
        print(f"aitbc-hub-watch-deadman: cannot write {directory}/{OUTPUT_NAME}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
