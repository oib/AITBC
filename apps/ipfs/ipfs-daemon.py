#!/usr/bin/env python3
"""IPFS daemon wrapper that reformats Kubo go-log output to AITBC journal style.

The AITBC Python logger emits lines like:

    [INFO] [module] message

Kubo go-log emits lines like:

    2026-08-23T20:03:22.013+0200\tWARN\tdht/RtRefreshManager\tfile.go:123\tmessage\t{"k": "v"}

Some libp2p subsystems emit logfmt lines like:

    time=... level=INFO source=... msg=... k=v

This wrapper runs `ipfs daemon` as a child, parses every stdout/stderr line and
re-emits it in the AITBC style so all services share one journal format.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys


IPFS_BIN = os.environ.get("IPFS_BIN", "/usr/local/bin/ipfs")

# 2026-08-23T20:03:22.013+0200        WARN        dht/RtRefreshManager        rtrefresh/rt_refresh_manager.go:233        failed when refreshing routing table        {"error": "..."}
KUBO_LOG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:?\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<component>\S+)\s+"
    r"(?P<caller>\S+)\s+"
    r"(?P<message>.*?)\s*"
    r"(?P<attrs>\{.*\})?\s*$"
)

# time=2026-08-23T20:25:29.824+02:00 level=INFO source=... msg=... k=v
LOGFMT_RE = re.compile(r'([\w-]+)=("(?:\\.|[^"\\])*"|[^\s]+)')


def _component_from_source(source: str) -> str:
    """Derive a short logger name from a go source path.

    Examples:
        github.com/libp2p/go-libp2p@v0.49.0/p2p/net/swarm/swarm_dial.go:614 -> swarm/swarm_dial
        provider/provider.go:1864 -> provider/provider
    """
    parts = source.split("/")
    if len(parts) > 1 and "@" in parts[1]:
        parts[1] = parts[1].split("@")[0]
    if len(parts) >= 2:
        comp = "/".join(parts[-2:])
    else:
        comp = source
    return re.sub(r"\.go:\d+$", "", comp)


def _parse_logfmt(line: str) -> dict[str, str] | None:
    pairs: dict[str, str] = {}
    for key, value in LOGFMT_RE.findall(line):
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        pairs[key] = value
    if not pairs or "level" not in pairs or "msg" not in pairs:
        return None
    return pairs


def _reformat(line: str) -> str:
    line = line.rstrip()
    if not line:
        return ""

    # 1. Try the default Kubo go-log format.
    match = KUBO_LOG_RE.match(line)
    if match:
        level = match.group("level").upper()
        component = match.group("component")
        caller = match.group("caller")
        message = match.group("message").rstrip()
        attrs = match.group("attrs")

        if attrs:
            try:
                data = json.loads(attrs)
                extra = ", ".join(f"{k}={v!r}" for k, v in data.items())
                message = f"{message}: {extra}"
            except Exception:
                message = f"{message} {attrs}"

        if caller:
            message = f"{caller}: {message}"

        return f"[{level}] [{component}] {message}"

    # 2. Try the logfmt format used by some libp2p subsystems.
    logfmt = _parse_logfmt(line)
    if logfmt:
        level = logfmt.pop("level", "INFO").upper()
        source = logfmt.pop("source", "")
        message = logfmt.pop("msg", "")
        logfmt.pop("time", None)
        component = _component_from_source(source) if source else "ipfs"
        extras = ", ".join(f"{k}={v!r}" for k, v in logfmt.items())
        if extras:
            message = f"{message}: {extras}"
        if source:
            message = f"{source}: {message}"
        return f"[{level}] [{component}] {message}"

    # 3. Unknown lines (startup banners, etc.) become INFO/ipfs.
    return f"[INFO] [ipfs] {line}"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])

    # If the user only passes options, inject the `daemon` subcommand.
    if not argv or (argv and not argv[0].startswith("daemon")):
        argv.insert(0, "daemon")

    cmd = [IPFS_BIN] + argv

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
    )

    def _forward(signum: int, _frame: object) -> None:
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)

    try:
        for raw in proc.stdout or []:
            formatted = _reformat(raw)
            if formatted:
                print(formatted)
    finally:
        proc.wait()

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
