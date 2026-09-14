#!/usr/bin/env python3
"""IPFS daemon wrapper that routes Kubo go-log output into AITBC logging.

Runs `ipfs daemon` as a child and hands every stdout/stderr line to the logging
module. The journal line is unchanged from what this wrapper used to `print()` --

    [INFO] [module] message

-- and the same line now also reaches /var/log/aitbc/ipfs/ipfs.log, where a Kubo
ERROR can still be read after the journal has rotated it away.

`kubo_log` in this directory holds the parsing and the reasons the forwarding is
shaped the way it is; `island_ipfs_daemon.py` is the private-swarm counterpart and
forwards through the same module.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

# systemd runs this as a bare script with no PYTHONPATH, and `aitbc` is not
# installed into the venv, so the repo root has to go on the path before the
# imports below. Derived from __file__ rather than hardcoded, so a checkout
# somewhere other than the deployment path still works. The script's own
# directory is already sys.path[0] when this runs as a script, but not when it
# is loaded by path -- importlib.util.spec_from_file_location does not add it --
# so `kubo_log` gets an entry of its own rather than relying on that.
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))
sys.path.insert(0, str(_HERE.parent))

from aitbc.aitbc_logging import configure_logging  # noqa: E402
from kubo_log import forward_line  # noqa: E402

configure_logging(level="INFO", service_name="ipfs", to_file=True)

IPFS_BIN = os.environ.get("IPFS_BIN", "/usr/local/bin/ipfs")


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
            forward_line(raw)
    finally:
        proc.wait()

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
