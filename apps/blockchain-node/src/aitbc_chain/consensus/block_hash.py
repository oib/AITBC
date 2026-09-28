"""Canonical block-hash formula — one definition shared by proposer and
attesters.

The block hash binds ``chain_id | height | parent_hash | timestamp |
sorted(tx_hashes) | proposer | state_root | bridge_state_root``. Attesters
recompute it over the transaction set they are asked to attest — a request
whose envelope list doesn't reproduce the signed hash is attestable proof
of a truncated or substituted tx set, so the proposer's formula and the
verifier's must live in one place.
"""

from __future__ import annotations

import hashlib
from datetime import datetime


def compute_block_hash(
    chain_id: str,
    height: int,
    parent_hash: str,
    timestamp: datetime | str,
    tx_hashes: list[str],
    proposer: str,
    state_root: str | None = None,
    bridge_state_root: str | None = None,
) -> str:
    ts = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
    payload = (
        f"{chain_id}|{height}|{parent_hash}|{ts}"
        f"|{'|'.join(sorted(tx_hashes))}"
        f"|{proposer}"
        f"|{state_root or ''}"
        f"|{bridge_state_root or ''}"
    ).encode()
    return "0x" + hashlib.sha256(payload).hexdigest()
