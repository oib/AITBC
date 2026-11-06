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
from datetime import UTC, datetime


def _hash_timestamp(timestamp: datetime | str) -> str:
    """Render the timestamp term of the block-hash preimage.

    The proposer hashes ``datetime.now(UTC).isoformat()`` — tz-aware,
    ``+00:00``. Stored and served block timestamps are naive UTC (SQLite
    drops tzinfo), so a naive input is read as UTC and rendered with the
    offset; that rewrite is the only one — aware strings stay verbatim and
    unparseable strings pass through, keeping every historical preimage
    byte-identical. Without this a bulk-pulled v20+ block recomputes a
    different hash than the proposer signed (#1164).
    """
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.isoformat()
    ts = str(timestamp)
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return ts
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC).isoformat()
    return ts


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
    ts = _hash_timestamp(timestamp)
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
