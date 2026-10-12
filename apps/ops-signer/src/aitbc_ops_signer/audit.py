"""Append-only audit trail: tx hashes and addresses only.

One line per request -- approved or refused -- holding time, memo,
recipient, amount, result and tx hash. Never a key, a password, or a
request body. This file is the single answer to "did the agent ever
send X to Y".
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from pathlib import Path

_lock = threading.Lock()


def audit_line(
    path: str | Path,
    *,
    memo: str,
    to: str,
    amount_units: int,
    result: str,
    reason: str = "-",
    tx_hash: str = "-",
    peer_uid: int | None = None,
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).isoformat()
    uid = "-" if peer_uid is None else str(peer_uid)
    line = (
        f"{ts} op=sign_payment memo={memo} to={to} amount_units={amount_units} "
        f"result={result} reason={reason} tx={tx_hash} peer_uid={uid}\n"
    )
    with _lock:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
