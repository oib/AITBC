"""PBFT quorum sizing, split out of ``pbft.py`` for #1940 F3.

``pbft_required_messages`` is needed by both the consensus engine
(``PBFTConsensus``) and the strict certificate contract
(``pbft_certificate.validate_commit_certificate``). Keeping it in its own
module avoids a ``pbft`` <-> ``pbft_certificate`` import cycle; ``pbft.py``
re-exports the name so ``aitbc_chain.consensus.pbft.pbft_required_messages``
keeps working for existing callers.
"""

from __future__ import annotations


def pbft_required_messages(active_count: int) -> int:
    """The prepare/commit quorum for ``active_count`` validators (#1061).

    f = (n-1)//3 Byzantine tolerated, and the quorum is the smallest count
    where two disjoint quorums would intersect in more than f nodes:
    ceil((n+f+1)/2). Plain 2f+1 is only that value when n == 3f+1; at
    n = 3f or 3f+2 it lets two disjoint quorums form with no Byzantine
    node at all (n=6 -> 4, n=9 -> 6, not 3 and 5).
    """
    n = max(0, int(active_count))
    f = max(0, (n - 1) // 3)
    return max(1, (n + f + 1 + 1) // 2)
