"""Cross-chain trading endpoints for the blockchain RPC.

These are intentionally lightweight: swaps and bridges are tracked in memory
for the current process. This is enough to exercise the ``aitbc crosschain``
CLI scenario end-to-end without introducing a new service dependency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["cross-chain"])

_swaps: dict[str, dict[str, Any]] = {}
_bridges: dict[str, dict[str, Any]] = {}

# Hard-coded demo rates and pools
_RATES: dict[str, float] = {
    "ait-hub::ait-devnet": 1.05,
    "ait-hub::ait-testnet": 1.10,
    "ait-devnet::ait-hub": 0.952381,
    "ait-devnet::ait-testnet": 1.047619,
    "ait-testnet::ait-hub": 0.909091,
    "ait-testnet::ait-devnet": 0.954545,
}

_POOLS: list[dict[str, Any]] = [
    {
        "pool_id": "pool-hub-dev",
        "token_a": "AIT",
        "token_b": "AIT",
        "chain_a": "ait-hub",
        "chain_b": "ait-devnet",
        "reserve_a": 10000.0,
        "reserve_b": 9523.81,
        "total_liquidity": 19523.81,
        "apr": 0.08,
    },
    {
        "pool_id": "pool-hub-test",
        "token_a": "AIT",
        "token_b": "AIT",
        "chain_a": "ait-hub",
        "chain_b": "ait-testnet",
        "reserve_a": 5000.0,
        "reserve_b": 4545.45,
        "total_liquidity": 9545.45,
        "apr": 0.075,
    },
]


def _pair_key(from_chain: str, to_chain: str) -> str:
    return f"{from_chain}::{to_chain}"


def _compute_rate(from_chain: str, to_chain: str) -> float:
    return _RATES.get(_pair_key(from_chain, to_chain), 1.0)


@router.get("/cross-chain/rates", summary="Get cross-chain exchange rates")
@rate_limit(rate=50, per=60)
async def get_cross_chain_rates(
    request: Request, from_chain: str | None = None, to_chain: str | None = None
) -> dict[str, Any]:
    """Return hard-coded cross-chain exchange rates."""
    if from_chain and to_chain:
        key = _pair_key(from_chain, to_chain)
        if key in _RATES:
            return {"rates": {key: _RATES[key]}}
        raise HTTPException(status_code=404, detail=f"No rate for {from_chain} -> {to_chain}")
    return {"rates": _RATES}


@router.post("/swap", summary="Create cross-chain swap")
@rate_limit(rate=20, per=60)
async def create_cross_chain_swap(request: Request, swap_data: dict[str, Any]) -> dict[str, Any]:
    """Create a cross-chain swap and return its details."""
    from_chain = swap_data.get("from_chain")
    to_chain = swap_data.get("to_chain")
    from_token = swap_data.get("from_token")
    to_token = swap_data.get("to_token")
    amount = Decimal(str(swap_data.get("amount", 0)))
    slippage = float(swap_data.get("slippage_tolerance", 0.01))
    user_address = swap_data.get("user_address", "0x" + uuid.uuid4().hex[:20])

    if not all([from_chain, to_chain, from_token, to_token]):
        raise HTTPException(status_code=400, detail="from_chain, to_chain, from_token and to_token are required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    rate = _compute_rate(str(from_chain), str(to_chain))
    bridge_fee = amount * Decimal("0.015")
    expected_amount = amount * Decimal(str(rate)) - bridge_fee
    min_amount = swap_data.get("min_amount")
    if min_amount:
        min_amount = Decimal(str(min_amount))
    else:
        min_amount = expected_amount * Decimal(1 - slippage)

    swap_id = f"swap_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    swap = {
        "swap_id": swap_id,
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "amount": str(amount),
        "expected_amount": str(expected_amount),
        "actual_amount": None,
        "min_amount": str(min_amount),
        "rate": rate,
        "total_fees": str(bridge_fee),
        "slippage_tolerance": slippage,
        "user_address": user_address,
        "status": "pending",
        "from_tx_hash": f"0xfrom{uuid.uuid4().hex[:16]}",
        "to_tx_hash": None,
        "created_at": now.isoformat(),
        "completed_at": None,
        "bridge_fee": str(bridge_fee),
    }
    _swaps[swap_id] = swap
    return swap


@router.get("/cross-chain/swap/{swap_id}", summary="Get cross-chain swap status")
@rate_limit(rate=100, per=60)
async def get_cross_chain_swap(swap_id: str) -> dict[str, Any]:
    """Return the status of a cross-chain swap."""
    swap = _swaps.get(swap_id)
    if not swap:
        raise HTTPException(status_code=404, detail=f"Swap not found: {swap_id}")
    return swap


@router.get("/cross-chain/swaps", summary="List cross-chain swaps")
@rate_limit(rate=50, per=60)
async def list_cross_chain_swaps(
    request: Request, user_address: str | None = None, status: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """List cross-chain swaps with optional filters."""
    results = list(_swaps.values())
    if user_address:
        results = [s for s in results if s.get("user_address") == user_address]
    if status:
        results = [s for s in results if s.get("status") == status]
    return {"swaps": results[:limit], "count": len(results[:limit])}


@router.post("/cross-chain/bridge", summary="Create cross-chain bridge transaction")
@rate_limit(rate=20, per=60)
async def create_cross_chain_bridge(request: Request, bridge_data: dict[str, Any]) -> dict[str, Any]:
    """Create a cross-chain bridge transaction."""
    source_chain = bridge_data.get("source_chain")
    target_chain = bridge_data.get("target_chain")
    token = bridge_data.get("token")
    amount = Decimal(str(bridge_data.get("amount", 0)))
    recipient = bridge_data.get("recipient_address")

    if not all([source_chain, target_chain, token, recipient]):
        raise HTTPException(status_code=400, detail="source_chain, target_chain, token and recipient_address are required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    bridge_fee = amount * Decimal("0.01")
    bridge_id = f"bridge_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    bridge = {
        "bridge_id": bridge_id,
        "source_chain": source_chain,
        "target_chain": target_chain,
        "token": token,
        "amount": str(amount),
        "bridge_fee": str(bridge_fee),
        "recipient_address": recipient,
        "status": "pending",
        "source_tx_hash": f"0xsrc{uuid.uuid4().hex[:16]}",
        "target_tx_hash": None,
        "created_at": now.isoformat(),
        "completed_at": None,
    }
    _bridges[bridge_id] = bridge
    return bridge


@router.get("/cross-chain/bridge/{bridge_id}", summary="Get cross-chain bridge status")
@rate_limit(rate=100, per=60)
async def get_cross_chain_bridge(bridge_id: str) -> dict[str, Any]:
    """Return the status of a cross-chain bridge transaction."""
    bridge = _bridges.get(bridge_id)
    if not bridge:
        raise HTTPException(status_code=404, detail=f"Bridge not found: {bridge_id}")
    return bridge


@router.get("/cross-chain/pools", summary="Show cross-chain liquidity pools")
@rate_limit(rate=50, per=60)
async def get_cross_chain_pools(request: Request) -> dict[str, Any]:
    """Return cross-chain liquidity pools."""
    return {"pools": _POOLS}


@router.get("/cross-chain/stats", summary="Show cross-chain trading statistics")
@rate_limit(rate=50, per=60)
async def get_cross_chain_stats(request: Request) -> dict[str, Any]:
    """Return aggregate cross-chain trading statistics."""
    total_volume = sum(Decimal(str(s.get("amount", 0))) for s in _swaps.values())
    bridge_volume = sum(Decimal(str(b.get("amount", 0))) for b in _bridges.values())
    return {
        "total_volume": str(total_volume + bridge_volume),
        "supported_chains": ["ait-hub", "ait-devnet", "ait-testnet"],
        "timestamp": datetime.now(UTC).isoformat(),
        "swap_stats": [
            {
                "status": "pending",
                "count": len([s for s in _swaps.values() if s["status"] == "pending"]),
                "volume": str(total_volume),
            },
            {"status": "completed", "count": 0, "volume": 0.0},
        ],
        "bridge_stats": [
            {"status": "pending", "count": len(_bridges), "volume": float(bridge_volume)},
            {"status": "completed", "count": 0, "volume": 0.0},
        ],
    }
