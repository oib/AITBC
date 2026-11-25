"""Ownership boundary for market-created coordinator job rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MARKET_IPFS_ESCROW_RAIL_TYPE = "ipfs"
MARKET_IPFS_ESCROW_RAIL_SOURCE = "market_host"
MARKET_IPFS_ESCROW_RAIL_JOB_ID_FIELD = "market_job_id"


def is_market_ipfs_escrow_rail(payload: Mapping[str, Any] | None) -> bool:
    """Return true for the coordinator row that only carries market IPFS escrow state.

    ``aitbc market host`` creates a coordinator job solely so the payment /
    stuck-escrow machinery has a row and job id to key on. The paid hosting
    lifecycle belongs to the market service plus the provider-side
    ``ipfs_pinning_sweeper``; the generic production-miner executor must never
    treat the row as executable work or submit a result for it. Rows created
    before this boundary was explicit can be recognized by the stable marker
    triple written by ``market host``.
    """
    if not isinstance(payload, Mapping):
        return False
    return (
        payload.get("type") == MARKET_IPFS_ESCROW_RAIL_TYPE
        and payload.get("source") == MARKET_IPFS_ESCROW_RAIL_SOURCE
        and bool(payload.get(MARKET_IPFS_ESCROW_RAIL_JOB_ID_FIELD))
    )
