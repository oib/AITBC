"""Dormant cross-view PBFT commit gate (#1940 F3-A / F3-B).

Views in this codebase are implicit timestamp-derived proposer rounds, not a
signed view-change protocol: a validator may legitimately prepare and commit
different block hashes at the same ``sequence_number`` (chain height) in
different ``view_number``s while an earlier view fails to seal. What is NOT
legal once armed is a validator COMMITting two *different* ``block_hash``
values for the same sequence across views — the commit vote is the
quorum/finality vote certificates count, so the pair is slashable
equivocation evidence (``slashing.PBFT_CROSS_VIEW_VOTE_EQUIVOCATION``).

``cross_view_commit_lock_active`` is the single settings-side gate, mirroring
``pbft_certificate.strict_certificate_active``: armed by
``ChainSettings.pbft_cross_view_commit_lock_height``, active iff a valid
non-negative int threshold is configured AND ``sequence`` is a valid
non-negative int at or above it. ``None``, bools, malformed values and
pre-threshold sequences all resolve False — every consumer then behaves
byte-identically to the pre-#1940-F3 code. Import-safe: reads ``settings``
only, no DB, no wall clock, no lazy heavy imports.

This tranche (F3-A) wires DETECTION/EVIDENCE only. Whether the same gate
also forbids *emitting* a conflicting local commit (the F3-B lock) is a
separate, still-unarmed decision — arming either gate before the
committed-but-unsealed liveness case is resolved can stall a height safely
but permanently (plan §7 of the #1940 F3 residual design).
"""

from __future__ import annotations

from typing import Any, TypeGuard

from ..config import settings


def _strict_int(value: Any) -> TypeGuard[int]:
    """Strictly ``int`` and not ``bool`` — JSON ``true`` must never pass as 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def cross_view_commit_lock_active(sequence: int | None) -> bool:
    """Whether the cross-view commit rules apply at ``sequence`` (#1940 F3-A).

    Active iff ``pbft_cross_view_commit_lock_height`` is a configured
    non-negative int AND ``sequence`` is a non-negative int at or above it.
    ``None``/unset/malformed threshold or sequence resolves False — callers
    must treat False as "pre-F3-A behavior, byte-identical".
    """
    threshold = getattr(settings, "pbft_cross_view_commit_lock_height", None)
    if not _strict_int(threshold):
        return False
    if threshold < 0:
        return False
    return _strict_int(sequence) and sequence >= threshold
