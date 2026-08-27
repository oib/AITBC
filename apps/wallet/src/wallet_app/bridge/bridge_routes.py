"""
ETH-AIT Bridge API Routes
REST API endpoints for bridge operations.
"""

from decimal import Decimal
from typing import Annotated, Any

from aitbc.utils.validation import validate_address_strict
from fastapi import APIRouter, Depends, HTTPException

from wallet_app.deps import require_admin_api_key

from .bridge_db import get_all_deposits, get_deposit_by_id, get_deposit_by_tx_hash, get_pending_deposits, update_deposit_status
from .price_api import calculate_ait_amount, get_exchange_rate

exchange_router = APIRouter(prefix="/v1/exchange", tags=["exchange"])
bridge_router = APIRouter(prefix="/v1/bridge", tags=["bridge"])
price_router = APIRouter(tags=["exchange"])

# Backward-compatible name for any in-module references
router = exchange_router


@router.get("/price")
async def get_price() -> dict[str, Any]:
    """
    Get current ETH-AIT exchange rate.
    """
    rate_info = await get_exchange_rate()

    if not rate_info["success"]:
        raise HTTPException(status_code=503, detail=rate_info["error"])

    return {
        "pair": "ETH-AIT",
        "eth_usd": rate_info["eth_usd"],
        "ait_usd": rate_info["ait_usd"],
        "exchange_rate": rate_info["eth_ait_rate_usd"],
        "timestamp": rate_info["timestamp"],
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

    return {"deposits": deposits, "count": len(deposits)}


@router.get("/deposits/{deposit_id}")
async def get_deposit(deposit_id: str) -> dict[str, Any]:
    """
    Get a specific deposit by ID.
    """
    deposit = get_deposit_by_id(deposit_id)
    if not deposit:
        deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    return deposit


@router.post("/deposits/{deposit_id}/verify")
async def verify_deposit(
    deposit_id: str,
    _admin: Annotated[None, Depends(require_admin_api_key)],
) -> dict[str, Any]:
    """
    Verify a deposit (admin operation).
    """
    deposit = get_deposit_by_id(deposit_id)
    if not deposit:
        deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Deposit already {deposit['status']}")

    success = update_deposit_status(deposit["id"], "verified")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update deposit status")

    return {"success": True, "message": "Deposit verified", "deposit_id": deposit["id"]}


@router.post("/deposits/{deposit_id}/complete")
async def complete_deposit(
    deposit_id: str,
    _admin: Annotated[None, Depends(require_admin_api_key)],
) -> dict[str, Any]:
    """
    Mark a deposit as completed after AIT minting (admin operation).
    """
    deposit = get_deposit_by_id(deposit_id)
    if not deposit:
        deposit = get_deposit_by_tx_hash(deposit_id)

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit["status"] != "verified":
        raise HTTPException(status_code=400, detail="Deposit must be verified first")

    success = update_deposit_status(deposit["id"], "completed")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update deposit status")

    return {"success": True, "message": "Deposit completed", "deposit_id": deposit["id"]}


@router.get("/calculate")
async def calculate_exchange(eth_amount: Decimal) -> dict[str, Any]:
    """
    Calculate AIT amount for a given ETH amount.

    Query parameters:
    - eth_amount: Amount of ETH to convert
    """
    if eth_amount <= 0:
        raise HTTPException(status_code=400, detail="ETH amount must be positive")

    ait_amount = await calculate_ait_amount(eth_amount)

    if ait_amount is None:
        raise HTTPException(status_code=503, detail="Failed to calculate exchange rate")

    return {"eth_amount": eth_amount, "ait_amount": ait_amount, "exchange_rate": ait_amount / eth_amount}


@router.get("/history")
async def get_price_history() -> dict[str, Any]:
    """
    Get price history and all-time averages.
    """
    from .bridge_db import get_all_time_average
    from .price_api import get_exchange_rate

    # Get current rates
    current_rates = await get_exchange_rate()

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
            "timestamp": current_rates["timestamp"],
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
            "count": averages["count"],
        },
        "change_vs_average": {"eth_usd_percent": change_usd, "eth_eur_percent": change_eur},
        "timestamp": current_rates["timestamp"],
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
        "poll_interval": int(os.getenv("BRIDGE_POLL_INTERVAL", "30")),
    }


@bridge_router.get("/status")
async def get_bridge_v1_status() -> dict[str, Any]:
    """Get bridge service status."""
    import os

    return {
        "status": "ready",
        "message": "Bridge active",
        "deposit_address": os.getenv("ETH_WALLET_ADDRESS", ""),
        "enabled": os.getenv("BRIDGE_ENABLED", "false").lower() == "true",
        "network": os.getenv("ETH_NETWORK", "sepolia"),
        "rpc_url": os.getenv("ETH_RPC_URL", ""),
        "poll_interval": int(os.getenv("BRIDGE_POLL_INTERVAL", "30")),
        "fee_rate": float(os.getenv("BRIDGE_FEE_RATE", "0.005")),
        "min_deposit": os.getenv("MIN_ETH_DEPOSIT", "0.001"),
    }


@bridge_router.get("/price")
async def get_bridge_price() -> dict[str, Any]:
    """Get bridge exchange price."""
    rate_info = await get_exchange_rate()
    if not rate_info["success"]:
        raise HTTPException(status_code=503, detail=rate_info["error"])
    return {
        "eth_usd": rate_info["eth_usd"],
        "ait_usd": rate_info["ait_usd"],
        "eth_eur": rate_info.get("eth_eur"),
        "ait_eur": rate_info.get("ait_eur"),
        "exchange_rate": rate_info["eth_ait_rate_usd"],
        "timestamp": rate_info["timestamp"],
    }


@bridge_router.post("/deposit")
async def bridge_deposit(body: dict[str, Any]) -> dict[str, Any]:
    """Calculate bridge deposit instructions and estimate."""
    try:
        eth_amount = Decimal(str(body.get("eth_amount", 0)))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="eth_amount must be a number") from exc

    if eth_amount <= 0:
        raise HTTPException(status_code=400, detail="eth_amount must be positive")

    ait_address = body.get("ait_address") or ""
    if not ait_address:
        raise HTTPException(status_code=400, detail="ait_address is required")
    try:
        ait_address = validate_address_strict(ait_address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ait_address: {exc}") from exc

    import os

    bridge_eth_address = os.getenv("ETH_WALLET_ADDRESS", "")
    if not bridge_eth_address:
        raise HTTPException(status_code=503, detail="Bridge ETH address not configured")

    min_deposit = Decimal(os.getenv("MIN_ETH_DEPOSIT", "0.001"))
    if eth_amount < min_deposit:
        raise HTTPException(status_code=400, detail=f"Minimum deposit is {min_deposit} ETH")

    ait_amount = await calculate_ait_amount(eth_amount)
    if ait_amount is None:
        raise HTTPException(status_code=503, detail="Failed to calculate AIT amount")

    rate_info = await get_exchange_rate()
    eth_usd_price = str(rate_info["eth_usd"]) if rate_info.get("success") else None
    ait_usd_price = str(rate_info["ait_usd"]) if rate_info.get("success") else None

    fee_rate = Decimal(os.getenv("BRIDGE_FEE_RATE", "0.005"))
    fee_eth = eth_amount * fee_rate
    net_eth = eth_amount - fee_eth

    transaction_data_hex = "0x" + ait_address.encode("utf-8").hex()

    return {
        "status": "ready",
        "message": "Send ETH to the bridge address with your AIT address in transaction data",
        "instructions": {
            "send_eth_to": bridge_eth_address,
            "network": os.getenv("ETH_NETWORK", "sepolia"),
            "amount_eth": str(eth_amount),
            "transaction_data": ait_address,
            "transaction_data_hex": transaction_data_hex,
            "min_deposit": str(min_deposit),
        },
        "estimate": {
            "eth_amount": str(eth_amount),
            "fee_eth": str(round(fee_eth, 8)),
            "net_eth": str(round(net_eth, 8)),
            "estimated_ait_amount": str(round(ait_amount, 6)),
            "eth_usd_price": eth_usd_price,
            "ait_usd_price": ait_usd_price,
            "ait_recipient": ait_address,
        },
    }


@bridge_router.get("/deposits")
async def bridge_list_deposits(status: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List bridge deposits."""
    if status == "pending":
        deposits = get_pending_deposits()
    else:
        deposits = get_all_deposits(limit=limit, offset=offset)
    return {
        "deposits": _normalize_deposits(deposits),
        "count": len(deposits),
        "total": len(deposits),
        "limit": limit,
        "offset": offset,
    }


@bridge_router.get("/deposit/{tx_hash}")
async def bridge_get_deposit(tx_hash: str) -> dict[str, Any]:
    """Get a single bridge deposit by ETH transaction hash."""
    deposit = get_deposit_by_tx_hash(tx_hash)
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    return _normalize_deposit(deposit)


def _normalize_deposit(deposit: dict[str, Any]) -> dict[str, Any]:
    """Normalize wallet-bridge deposit to the shape the website expects."""
    return {
        "id": deposit.get("id"),
        "eth_tx_hash": deposit.get("tx_hash"),
        "eth_from_address": deposit.get("from_address"),
        "eth_amount": str(deposit.get("amount_eth", "")),
        "ait_amount": str(deposit.get("amount_ait", "")),
        "ait_recipient": deposit.get("recipient") or "",
        "status": deposit.get("status"),
        "ait_tx_hash": deposit.get("ait_tx_hash"),
        "created_at": deposit.get("created_at"),
        "processed_at": deposit.get("completed_at") or deposit.get("created_at"),
    }


def _normalize_deposits(deposits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_deposit(d) for d in deposits]


@bridge_router.get("/estimate")
async def bridge_estimate(eth_amount: Decimal, ait_address: str) -> dict[str, Any]:
    """Estimate AIT for a given ETH amount."""
    if eth_amount <= 0:
        raise HTTPException(status_code=400, detail="eth_amount must be positive")
    if not ait_address:
        raise HTTPException(status_code=400, detail="ait_address is required")
    try:
        ait_address = validate_address_strict(ait_address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ait_address: {exc}") from exc

    ait_amount = await calculate_ait_amount(eth_amount)
    if ait_amount is None:
        raise HTTPException(status_code=503, detail="Failed to calculate AIT amount")

    import os

    fee_rate = Decimal(os.getenv("BRIDGE_FEE_RATE", "0.005"))
    fee_eth = eth_amount * fee_rate
    net_eth = eth_amount - fee_eth

    return {
        "eth_amount": str(eth_amount),
        "ait_amount": str(ait_amount),
        "fee_eth": str(round(fee_eth, 8)),
        "net_eth": str(round(net_eth, 8)),
        "ait_recipient": ait_address,
    }


@price_router.get("/exchange/price.json")
async def exchange_price_json() -> dict[str, Any]:
    """Price ticker JSON used by the website."""
    rate_info = await get_exchange_rate()
    if not rate_info["success"]:
        return {"error": rate_info.get("error", "Price unavailable")}
    return {
        "price_usd": str(rate_info["ait_usd"]),
        "price_eur": str(rate_info.get("ait_eur", "0.25")),
        "price_eth": str(rate_info.get("eth_ait_rate_usd") and 1 / rate_info["eth_ait_rate_usd"] or 0),
        "eth_eur": str(rate_info.get("eth_eur", "0")),
        "currency": "USD",
        "timestamp": rate_info["timestamp"],
        "source": "derived",
    }


# Root router that combines exchange + bridge + price endpoints
from fastapi import APIRouter as _APIRouter

root_router = _APIRouter()
root_router.include_router(exchange_router)
root_router.include_router(bridge_router)
root_router.include_router(price_router)


# Public name used by wallet_app.main
router = root_router
