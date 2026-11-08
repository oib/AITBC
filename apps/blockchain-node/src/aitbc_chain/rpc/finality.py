"""Finality annotations for RPC read surfaces (#1268 Phase 1, item 4).

A sealed block can still be replaced by fork resolution (`_resolve_fork` tip
race, `revert_losing_segment`), so a depth-0 ``confirmed`` row is not final.
This module adds *additive* fields — it never changes an existing field such
as ``status`` — that let a consumer with an external effect wait for depth:

* ``confirmations`` — blocks built on top of the sealing block
  (``head_height - block_height``; 0 = the sealing block is the tip),
* ``finalized`` — ``confirmations >= rpc_finality_depth`` (N=3, the same
  convention as ``BRIDGE_WITHDRAW_SEAL_DEPTH``),
* ``finalized_height`` on ``/head`` — ``head_height - N`` (floored at 0).

The whole feature sits behind ``rpc_finality_fields_enabled`` (default off):
with the flag off every response is byte-identical to the pre-#1268 surface.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import select

from ..config import settings
from ..models import Block


def finality_fields_enabled() -> bool:
    return bool(getattr(settings, "rpc_finality_fields_enabled", False))


def finality_depth() -> int:
    try:
        return max(0, int(getattr(settings, "rpc_finality_depth", 3)))
    except (TypeError, ValueError):
        return 3


def head_height_in_session(session: Any, chain_id: str) -> int | None:
    """Current head height read through an already-open session."""
    head: int | None = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).one()
    return head


def finality_view(height: int | None, head_height: int | None) -> dict[str, Any]:
    """Per-object finality fields for something sealed at ``height``.

    A pending object (no height) or an unreadable head is never finalized.
    """
    depth = finality_depth()
    if height is None or head_height is None:
        return {"confirmations": 0, "finalized": False, "finality_depth": depth}
    confirmations = max(0, int(head_height) - int(height))
    return {"confirmations": confirmations, "finalized": confirmations >= depth, "finality_depth": depth}


def head_finality(head_height: int) -> dict[str, Any]:
    """Chain-level fields for ``/head``."""
    depth = finality_depth()
    return {"finalized_height": max(0, int(head_height) - depth), "finality_depth": depth}
