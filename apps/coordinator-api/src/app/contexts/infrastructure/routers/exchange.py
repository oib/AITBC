"""
Bitcoin Exchange Router for AITBC

v0.5.1: Payment state migrated from module-global dict to RedisStateManager.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.contexts.infrastructure.services.redis_state import RedisStateManager
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ...wallet.services.bitcoin_wallet import get_wallet_balance, get_wallet_info
from ....schemas import (
    ExchangePaymentRequest,
    ExchangePaymentResponse,
    ExchangeRatesResponse,
    MarketStatsResponse,
    PaymentStatusResponse,
    WalletBalanceResponse,
    WalletInfoResponse,
)
from ....utils.cache import cached, get_cache_config

logger = get_logger(__name__)

router = APIRouter(tags=["exchange"])

# Redis-backed state (falls back to in-memory if Redis unavailable)
_state = RedisStateManager.get_instance_sync()
_NAMESPACE = "exchange"

# Bitcoin configuration
BITCOIN_CONFIG: dict[str, Any] = {
    "testnet": True,
    "main_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",  # Testnet address
    "exchange_rate": 100000,  # 1 BTC = 100,000 AITBC
    "min_confirmations": 1,
    "payment_timeout": 3600,  # 1 hour
}


@router.post("/exchange/create-payment", response_model=ExchangePaymentResponse)
@rate_limit(rate=20, per=60)
async def create_payment(
    request: Request, payment_request: ExchangePaymentRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Create a new Bitcoin payment request"""

    # Validate request
    if payment_request.aitbc_amount <= 0 or payment_request.btc_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Calculate expected BTC amount
    expected_btc = payment_request.aitbc_amount / BITCOIN_CONFIG["exchange_rate"]

    # Allow small difference for rounding
    if abs(payment_request.btc_amount - expected_btc) > 0.00000001:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    # Create payment record
    payment_id = str(uuid.uuid4())
    payment = {
        "payment_id": payment_id,
        "user_id": payment_request.user_id,
        "aitbc_amount": payment_request.aitbc_amount,
        "btc_amount": payment_request.btc_amount,
        "payment_address": BITCOIN_CONFIG["main_address"],
        "status": "pending",
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + BITCOIN_CONFIG["payment_timeout"],
        "confirmations": 0,
        "tx_hash": None,
    }

    # Store payment
    await _state.hset(_NAMESPACE, payment_id, payment)

    # Start payment monitoring in background
    background_tasks.add_task(monitor_payment, payment_id)

    return payment


@router.get("/exchange/payment-status/{payment_id}", response_model=PaymentStatusResponse)
@rate_limit(rate=200, per=60)
@cached(**get_cache_config("user_balance"))  # Cache payment status for 30 seconds
async def get_payment_status(request: Request, payment_id: str) -> dict[str, Any]:
    """Get payment status"""

    payment = await _state.hget(_NAMESPACE, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Check if expired
    if payment["status"] == "pending" and time.time() > payment["expires_at"]:
        payment["status"] = "expired"
        await _state.hset(_NAMESPACE, payment_id, payment)

    return payment


@router.post("/exchange/confirm-payment/{payment_id}")
@rate_limit(rate=50, per=60)
async def confirm_payment(request: Request, payment_id: str, tx_hash: str) -> dict[str, Any]:
    """Confirm payment (webhook from payment processor)"""

    payment = await _state.hget(_NAMESPACE, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment["status"] != "pending":
        raise HTTPException(status_code=400, detail="Payment not in pending state")

    # Verify transaction (in production, verify with blockchain API)
    # For demo, we'll accept any tx_hash

    payment["status"] = "confirmed"
    payment["tx_hash"] = tx_hash
    payment["confirmed_at"] = int(time.time())
    await _state.hset(_NAMESPACE, payment_id, payment)

    # Mint AITBC tokens to user's wallet
    try:
        from ...blockchain.services.blockchain import mint_tokens

        mint_tokens(payment["user_id"], payment["aitbc_amount"])  # type: ignore[unused-coroutine]
    except Exception as e:
        logger.error("Error minting tokens: %s", e)
        # In production, handle this error properly

    return {"status": "ok", "payment_id": payment_id, "aitbc_amount": payment["aitbc_amount"]}


@router.get("/exchange/rates", response_model=ExchangeRatesResponse)
@rate_limit(rate=500, per=60)
async def get_exchange_rates(request: Request) -> ExchangeRatesResponse:
    """Get current exchange rates"""

    return ExchangeRatesResponse(
        btc_to_aitbc=BITCOIN_CONFIG["exchange_rate"],
        aitbc_to_btc=1.0 / BITCOIN_CONFIG["exchange_rate"],
        fee_percent=0.5,
    )


@router.get("/exchange/market-stats", response_model=MarketStatsResponse)
@rate_limit(rate=500, per=60)
async def get_market_stats(request: Request) -> MarketStatsResponse:
    """Get market statistics"""

    # Calculate 24h volume from payments
    current_time = int(time.time())
    yesterday_time = current_time - 24 * 60 * 60  # 24 hours ago

    all_payments = (await _state.hgetall(_NAMESPACE)).values()

    daily_volume = 0
    for payment in all_payments:
        if payment["status"] == "confirmed" and payment.get("confirmed_at", 0) > yesterday_time:
            daily_volume += payment["aitbc_amount"]

    # Calculate price change (simulated)
    base_price = 1.0 / BITCOIN_CONFIG["exchange_rate"]
    price_change_percent = 5.2  # Simulated +5.2%

    return MarketStatsResponse(
        price=base_price,
        price_change_24h=price_change_percent,
        daily_volume=daily_volume,
        daily_volume_btc=daily_volume / BITCOIN_CONFIG["exchange_rate"],
        total_payments=len([p for p in all_payments if p["status"] == "confirmed"]),
        pending_payments=len([p for p in all_payments if p["status"] == "pending"]),
    )


@router.get("/exchange/wallet/balance", response_model=WalletBalanceResponse)
@rate_limit(rate=200, per=60)
async def get_wallet_balance_api(request: Request) -> WalletBalanceResponse:
    """Get Bitcoin wallet balance"""
    try:
        balance_data = get_wallet_balance()
        return WalletBalanceResponse(**balance_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/exchange/wallet/info", response_model=WalletInfoResponse)
@rate_limit(rate=200, per=60)
async def get_wallet_info_api(request: Request) -> WalletInfoResponse:
    """Get comprehensive wallet information"""
    try:
        wallet_data = get_wallet_info()
        return WalletInfoResponse(**wallet_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def monitor_payment(payment_id: str) -> None:
    """Monitor payment for confirmation (background task)"""

    import asyncio

    while True:
        payment = await _state.hget(_NAMESPACE, payment_id)
        if payment is None:
            break

        # Check if expired
        if payment["status"] == "pending" and time.time() > payment["expires_at"]:
            payment["status"] = "expired"
            await _state.hset(_NAMESPACE, payment_id, payment)
            break

        # In production, check blockchain for payment
        # For demo, we'll wait for manual confirmation

        await asyncio.sleep(30)  # Check every 30 seconds


# Agent endpoints temporarily added to exchange router
@router.get("/agents/test")
@rate_limit(rate=1000, per=60)
async def test_agent_endpoint(request: Request) -> dict[str, str]:
    """Test endpoint to verify agent routes are working"""
    return {"message": "Agent routes are working", "timestamp": datetime.now(UTC).isoformat()}


# NOTE: create_agent_network and get_execution_receipt endpoints removed
# These are now provided by agent_router at /v1/agents/networks and /v1/agents/executions/{execution_id}/receipt
# See /opt/aitbc/apps/coordinator-api/src/app/contexts/agent_coordination/routers/agent_router.py
