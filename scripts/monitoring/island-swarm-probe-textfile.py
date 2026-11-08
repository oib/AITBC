#!/usr/bin/env python3
"""Probe island IPFS swarm peers and export results as a node_exporter textfile.

The island swarm is a libp2p private network: peers must complete the pnet
handshake before multistream, so unauthenticated TCP probes (blackbox_exporter
``tcp_ipfs_libp2p``) are accept-then-FIN rejected by design and can never
measure these endpoints (#1271). The meaningful probe is a real ``ipfs swarm
connect`` from a swarm-key holder — this script runs on an island member and
dials each *other* member's public multiaddr, which exercises transport +
pnet + multistream + backend peering end to end.

Each island member probes the others: ``ipfs swarm connect`` to self fails
with "dial to self attempted", so the peer list must exclude the local node.
Configure per host via ``AITBC_ISLAND_SWARM_PROBE_PEERS`` — space-separated
``name=<multiaddr>`` pairs. The shipped default covers the two-member bc-2
island from either side once the local entry is removed.

Writes, atomically, to ``<TEXTFILE_DIR>/aitbc_island_swarm_probe.prom``:

    aitbc_island_swarm_probe_success{peer=...,instance=...}             1/0
    aitbc_island_swarm_probe_duration_seconds{peer=...,instance=...}    connect wall time
    aitbc_island_swarm_probe_run_success                                1 when the run wrote results
    aitbc_island_swarm_probe_run_timestamp_seconds                      when this run finished
    aitbc_island_swarm_probe_peers                                      peers configured

A peer that cannot be parsed is skipped. A missing ipfs binary or repo makes
every connect fail — the run still writes success=0 series so
IncusProxyProbeFailed fires rather than the watch going silently absent
through a different path than the timer dying (absent() covers that case
separately).

Stdlib only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time

IPFS_BIN = os.environ.get("IPFS_BIN", "/usr/local/bin/ipfs")
IPFS_PATH = os.environ.get("AITBC_IPFS_PATH", "/var/lib/aitbc/data/ipfs-island/bc-2-island")
TEXTFILE_DIR = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
OUT_NAME = "aitbc_island_swarm_probe.prom"
CONNECT_TIMEOUT = int(os.environ.get("AITBC_ISLAND_SWARM_PROBE_TIMEOUT", "15"))

DEFAULT_PEERS = (
    "hub=/dns4/hub.aitbc.bubuit.net/tcp/4002"
    "/p2p/12D3KooWN1232befqb6QhQuQoyfCM7VR4TiJBUwdRu3NbccSyVyc "
    "hub1=/dns4/hub1.aitbc.bubuit.net/tcp/4002"
    "/p2p/12D3KooWSTvzDW58BH1FbHr583Mhb9MotpUf4xrDpK2SZqyuMAnT"
)

_INSTANCE_RE = re.compile(r"/dns4/([^/]+)/tcp/(\d+)|/ip4/([^/]+)/tcp/(\d+)")


def _parse_peers(raw: str) -> list[tuple[str, str]]:
    peers = []
    for item in raw.split():
        if "=" not in item:
            continue
        name, addr = item.split("=", 1)
        if name and addr.startswith("/"):
            peers.append((name, addr))
    return peers


def _instance(addr: str) -> str:
    m = _INSTANCE_RE.search(addr)
    if not m:
        return "unknown"
    host = m.group(1) or m.group(3)
    port = m.group(2) or m.group(4)
    return f"{host}:{port}"


def _esc(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _connect(addr: str) -> tuple[int, float]:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["timeout", str(CONNECT_TIMEOUT), IPFS_BIN, "swarm", "connect", addr],
            env={**os.environ, "IPFS_PATH": IPFS_PATH},
            capture_output=True,
            text=True,
            timeout=CONNECT_TIMEOUT + 10,
        )
        ok = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    return int(ok), time.monotonic() - start


def main() -> int:
    peers = _parse_peers(os.environ.get("AITBC_ISLAND_SWARM_PROBE_PEERS", DEFAULT_PEERS))
    lines = [
        "# HELP aitbc_island_swarm_probe_success Whether ipfs swarm connect to the peer succeeded (1) or failed (0).",
        "# TYPE aitbc_island_swarm_probe_success gauge",
        "# HELP aitbc_island_swarm_probe_duration_seconds Wall time of the ipfs swarm connect attempt.",
        "# TYPE aitbc_island_swarm_probe_duration_seconds gauge",
    ]
    for name, addr in peers:
        ok, dur = _connect(addr)
        labels = f'peer="{_esc(name)}",instance="{_esc(_instance(addr))}"'
        lines.append(f"aitbc_island_swarm_probe_success{{{labels}}} {ok}")
        lines.append(f"aitbc_island_swarm_probe_duration_seconds{{{labels}}} {dur:.3f}")

    run_ts = time.time()
    lines += [
        "# HELP aitbc_island_swarm_probe_run_success Whether this probe run completed and wrote results (always 1 on write; a crashed run leaves a stale file).",
        "# TYPE aitbc_island_swarm_probe_run_success gauge",
        "aitbc_island_swarm_probe_run_success 1",
        "# HELP aitbc_island_swarm_probe_run_timestamp_seconds Unix time of the last completed probe run.",
        "# TYPE aitbc_island_swarm_probe_run_timestamp_seconds gauge",
        f"aitbc_island_swarm_probe_run_timestamp_seconds {run_ts:.3f}",
        "# HELP aitbc_island_swarm_probe_peers Number of peers configured for probing.",
        "# TYPE aitbc_island_swarm_probe_peers gauge",
        f"aitbc_island_swarm_probe_peers {len(peers)}",
        "",
    ]

    os.makedirs(TEXTFILE_DIR, exist_ok=True)
    out_path = os.path.join(TEXTFILE_DIR, OUT_NAME)
    fd, tmp = tempfile.mkstemp(dir=TEXTFILE_DIR, prefix=".aitbc_island_swarm_probe.")
    # node-exporter scrapes as a different user — mkstemp's 0600 would
    # make the file unreadable (same fix as attestation-arrival-textfile.py).
    os.fchmod(fd, 0o644)
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        os.replace(tmp, out_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
