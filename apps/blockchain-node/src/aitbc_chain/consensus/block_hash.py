"""Canonical block-hash formula — one definition shared by proposer and
attesters.

The block hash binds ``chain_id | height | parent_hash | timestamp |
sorted(tx_hashes) | proposer | state_root | bridge_state_root``. Attesters
recompute it over the transaction set they are asked to attest — a request
whose envelope list doesn't reproduce the signed hash is attestable proof
of a truncated or substituted tx set, so the proposer's formula and the
verifier's must live in one place.

v14 (V-3, shared ACT-1 activation): ``aux_state_root`` — the 13-table
side-table root fingerprint — is appended as a ninth term only when set.
A ``None``/empty aux produces the byte-identical pre-v14 preimage, so every
block below the activation height hashes exactly as before.
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
    aux_state_root: str | None = None,
) -> str:
    ts = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
    preimage = (
        f"{chain_id}|{height}|{parent_hash}|{ts}"
        f"|{'|'.join(sorted(tx_hashes))}"
        f"|{proposer}"
        f"|{state_root or ''}"
        f"|{bridge_state_root or ''}"
    )
    if aux_state_root:
        preimage += f"|{aux_state_root}"
    return "0x" + hashlib.sha256(preimage.encode()).hexdigest()
