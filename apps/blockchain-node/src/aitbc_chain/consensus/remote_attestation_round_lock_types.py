"""Round-lock record types (#1950 pure-move split)."""

from __future__ import annotations


class _RoundLockEntry:
    """One signed (height, round) -> block_hash record (#1242).

    ``signed_at``/``request_seen_at`` are monotonic for live entries; records
    restored from disk carry wall-clock-derived equivalents so the same U1/U2
    math applies after a restart.
    """

    __slots__ = (
        "block_hash",
        "proposer",
        "signed_at",
        "signed_wall",
        "request_seen_at",
        "request_seen_wall",
        "signature_domain",
    )

    def __init__(
        self,
        block_hash: str,
        proposer: str,
        signed_at: float,
        signed_wall: float,
        request_seen_at: float | None,
        request_seen_wall: float | None,
        signature_domain: str | None = None,
    ) -> None:
        self.block_hash = block_hash
        self.proposer = proposer
        self.signed_at = signed_at
        self.signed_wall = signed_wall
        self.request_seen_at = request_seen_at
        self.request_seen_wall = request_seen_wall
        # #1298: the domain preimage this signing was minted under (None =
        # legacy shared preimage). Part of the acceptance key so records of
        # different domains at the same (height, round) never merge.
        self.signature_domain = signature_domain


class _RoundLockVerdict:
    """Outcome of the shared (height, round) lock transition check."""

    __slots__ = ("permitted", "reason", "block_hash", "proposer")

    def __init__(self, permitted: bool, reason: str | None, block_hash: str = "", proposer: str = "") -> None:
        self.permitted = permitted
        self.reason = reason
        self.block_hash = block_hash
        self.proposer = proposer
