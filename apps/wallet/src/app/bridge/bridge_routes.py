"""
ETH-AIT Bridge API Routes
REST API endpoints for bridge operations.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from .bridge_db import get_pending_deposits, get_all_deposits, update_deposit_status, get_deposit_by_tx_hash
from .price_api import get_exchange_rate, calculate_ait_amount

router = APIRouter(prefix="/v1/exchange", tags=["exchange"])


@router.get("/price")
async def get_price():
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
        "exchange_rate": rate_info["eth_ait_rate"],
        "timestamp": rate_info["timestamp"]
    }


@router.get("/deposits")
async def list_deposits(status: Optional[str] = None, limit: int = 50, offset: int = 0):
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
async def get_deposit(deposit_id: str):
    """
    Get a specific deposit by ID.
    """
    # For MVP, we'll search by tx_hash since that's our unique key
    deposit = get_deposit_by_tx_hash(deposit_id)
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    return deposit


@router.post("/deposits/{deposit_id}/verify")
async def verify_deposit(deposit_id: str):
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
async def complete_deposit(deposit_id: str):
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
async def calculate_exchange(eth_amount: float):
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


@router.get("/status")
async def get_bridge_status():
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
