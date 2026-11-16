"""PBFT vote signature preimage helpers (#2102).

PBFT prepare/commit/pre-prepare signatures cover
``{message_type, sender, view_number, sequence_number, digest}`` — no
``chain_id`` — so a signature made on one chain verifies on any other chain
sharing the validator key: an equivocation pair recorded on chain X replays
as slashable evidence on armed chain Y.

New signatures add ``chain_id`` to the preimage. Verification tries the
chain-bound preimage first and falls back to the legacy preimage so
in-flight gossip and historical signatures still verify — signatures made
before this change are already chain-agnostic and cannot be re-bound; that
residual is inherent to the transition and ages out with the evidence TTL
/ intake windows. The vote ``digest`` itself stays ``sha256(block_hash:
seq:view)`` on purpose: it is the quorum/dedup key, and mixing chain-bound
and legacy digests would split quorums mid-transition.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aitbc.crypto.consensus_signing import verify_consensus_message
from aitbc.crypto.signature_recovery import SignatureMalformed

_VOTE_PREIMAGE_FIELDS = ("message_type", "sender", "view_number", "sequence_number", "digest")


def pbft_vote_preimage(record: Mapping[str, Any], chain_id: str | None = None) -> dict[str, Any]:
    """The signed preimage for a PBFT prepare/commit/pre-prepare vote.

    ``chain_id`` is included only when non-empty — ``None`` and ``""`` both
    reproduce the legacy pre-#2102 preimage byte-for-byte. ``settings.chain_id``
    defaults to ``""``, so an empty chain must sign exactly what the
    legacy-only verifier path checks, or the node cannot verify its own
    votes (#2102 respin).
    """
    data = {field: record.get(field) for field in _VOTE_PREIMAGE_FIELDS}
    if chain_id:
        data["chain_id"] = chain_id
    return data


def verify_pbft_vote_signature(
    record: Mapping[str, Any],
    signature: str,
    sender: str,
    chain_id: str | None = None,
) -> bool:
    """Verify a PBFT vote signature, chain-bound first then legacy.

    ``record`` carries the five signed fields (``message_type``, ``sender``,
    ``view_number``, ``sequence_number``, ``digest``). With ``chain_id`` the
    chain-bound preimage is tried first; the legacy preimage is always the
    fallback so pre-#2102 signatures keep verifying. Never raises on a
    malformed signature — returns False.
    """
    attempts: list[str | None] = [chain_id] if chain_id else []
    attempts.append(None)
    for cid in attempts:
        try:
            if verify_consensus_message(pbft_vote_preimage(record, cid), signature, sender):
                return True
        except SignatureMalformed:
            continue
    return False
