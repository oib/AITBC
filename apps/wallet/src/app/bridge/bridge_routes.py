"""
ETH-AIT Bridge API Routes
REST API endpoints for bridge operations.
"""


from typing import Any

from fastapi import APIRouter, HTTPException

from .bridge_db import get_all_deposits, get_deposit_by_tx_hash, get_pending_deposits, update_deposit_status
from .price_api import calculate_ait_amount, get_exchange_rate

router = APIRouter(prefix="/v1/exchange", tags=["exchange"])


@router.get("/price")
async def get_price() -> dict[str, Any]:
    """
    Get current ETH-AIT exchange rate.
    """
    rate_info = get_exchange_rate()

    if not rate_info["success"]:
        raise HTTPException(status_code=503, detail=rate_info["error"])

    return {
        "pair": "ETH-AIT",
        "eth_usd": rate_info["eth_usd"],
        "ait_usd": rate_info["ait_usd"],
        "exchange_rate": rate_info["eth_ait_rate_usd"],
        "timestamp": rate_info["timestamp"]
    }


@router.get("/deposits")
async def list_deposits(status: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """
    List ETH deposits.
    
    Query parameters:
    - status: Filter by status (pending, verified, completed, rejected)
    - limit: Maximum number of results (default: 50)
    - offset: Pagination offset (default: 0)
    """
    if status == "pending":
        deposits = get_pending_deposits()
    else:
        deposits = get_all_deposits(limit=limit, offset=offset)

    return {
        "deposits": deposits,
        "count": len(deposits)
    }


@router.get("/deposits/{deposit_id}")
async def get_deposit(deposit_id: str) -> dict[str, Any]:
    """
    Get a specific deposit by ID.
    """
    # For MVP, we'll search by tx_hash since that's our unique key
    deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    return deposit


@router.post("/deposits/{deposit_id}/verify")
async def verify_deposit(deposit_id: str) -> dict[str, Any]:
    """
    Verify a deposit (admin operation).
    """
    deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Deposit already {deposit['status']}")

    success = update_deposit_status(deposit_id, "verified")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update deposit status")

    return {
        "success": True,
        "message": "Deposit verified",
        "deposit_id": deposit_id
    }


@router.post("/deposits/{deposit_id}/complete")
async def complete_deposit(deposit_id: str) -> dict[str, Any]:
    """
    Mark a deposit as completed after AIT minting (admin operation).
    """
    deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit["status"] != "verified":
        raise HTTPException(status_code=400, detail="Deposit must be verified first")

    success = update_deposit_status(deposit_id, "completed")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update deposit status")

    return {
        "success": True,
        "message": "Deposit completed",
        "deposit_id": deposit_id
    }


@router.get("/calculate")
async def calculate_exchange(eth_amount: float) -> dict[str, Any]:
    """
    Calculate AIT amount for a given ETH amount.
    
    Query parameters:
    - eth_amount: Amount of ETH to convert
    """
    if eth_amount <= 0:
        raise HTTPException(status_code=400, detail="ETH amount must be positive")

    ait_amount = calculate_ait_amount(eth_amount)

    if ait_amount is None:
        raise HTTPException(status_code=503, detail="Failed to calculate exchange rate")

    return {
        "eth_amount": eth_amount,
        "ait_amount": ait_amount,
        "exchange_rate": ait_amount / eth_amount
    }


@router.get("/history")
async def get_price_history() -> dict[str, Any]:
    """
    Get price history and all-time averages.
    """
    from .bridge_db import get_all_time_average
    from .price_api import get_exchange_rate

    # Get current rates
    current_rates = get_exchange_rate()

    if not current_rates["success"]:
        return current_rates

    # Get all-time averages
    averages = get_all_time_average()

    if not averages:
        # No history yet, return current rates as averages
        return {
            "success": True,
            "current": current_rates,
            "averages": None,
            "change_vs_average": None,
            "timestamp": current_rates["timestamp"]
        }

    # Calculate change vs average
    change_usd = ((current_rates["eth_usd"] - averages["eth_usd_avg"]) / averages["eth_usd_avg"]) * 100
    change_eur = ((current_rates["eth_eur"] - averages["eth_eur_avg"]) / averages["eth_eur_avg"]) * 100

    return {
        "success": True,
        "current": current_rates,
        "averages": {
            "eth_usd": averages["eth_usd_avg"],
            "eth_eur": averages["eth_eur_avg"],
            "ait_usd": 1.0,  # Fixed
            "ait_eur": 1.0 * (averages["eth_eur_avg"] / averages["eth_usd_avg"]),
            "eth_ait_rate_usd": averages["eth_usd_avg"],
            "eth_ait_rate_eur": averages["eth_eur_avg"] / (1.0 * (averages["eth_eur_avg"] / averages["eth_usd_avg"])),
            "count": averages["count"]
        },
        "change_vs_average": {
            "eth_usd_percent": change_usd,
            "eth_eur_percent": change_eur
        },
        "timestamp": current_rates["timestamp"]
    }


@router.get("/status")
async def get_bridge_status() -> dict[str, Any]:
    """
    Get bridge service status.
    """
    import os

    return {
        "enabled": os.getenv("BRIDGE_ENABLED", "false").lower() == "true",
        "wallet_address": os.getenv("ETH_WALLET_ADDRESS", ""),
        "rpc_url": os.getenv("ETH_RPC_URL", ""),
        "poll_interval": int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))
    }
