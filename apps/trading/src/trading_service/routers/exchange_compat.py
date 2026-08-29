"""Migrated exchange payment endpoints (compatibility layer)."""

import asyncio
import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc_agent_core import get_active_brand

from ..dependencies import get_session_dep, require_trading_api_key, require_webhook_signature
from ..domain import ExchangePayment
from ..storage import get_session

router = APIRouter(tags=["exchange"])
logger = get_logger(__name__)
_brand = get_active_brand()

ETHEREUM_CONFIG: dict[str, Any] = {
    "testnet": True,
    "main_address": "0x0000000000000000000000000000000000000000",
    "exchange_rate": 100000,
    "min_confirmations": 1,
    "payment_timeout": 3600,
}


class ExchangePaymentRequest(BaseModel):
    """Exchange payment request schema."""

    user_id: str
    aitbc_amount: Decimal
    eth_amount: Decimal


def _payment_dict(payment: ExchangePayment) -> dict[str, Any]:
    """Serialize an ``ExchangePayment`` to the historical response shape."""
    return {
        "payment_id": payment.payment_id,
        "user_id": payment.user_id,
        "aitbc_amount": str(payment.aitbc_amount),
        "eth_amount": str(payment.eth_amount),
        "payment_address": payment.payment_address,
        "status": payment.status,
        "created_at": payment.created_at,
        "expires_at": payment.expires_at,
        "confirmations": payment.confirmations,
        "tx_hash": payment.tx_hash,
    }


@router.post("/v1/exchange/create-payment", dependencies=[Depends(require_trading_api_key)])
async def create_exchange_payment(
    payment_request: ExchangePaymentRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> dict[str, Any]:
    """Create a new Ethereum payment request (migrated from Coordinator API).

    Supports idempotency via the ``Idempotency-Key`` header: if the same key
    is replayed, the original payment is returned instead of creating a duplicate.
    """
    if payment_request.aitbc_amount <= 0 or payment_request.eth_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    expected_eth = payment_request.aitbc_amount / ETHEREUM_CONFIG["exchange_rate"]
    if payment_request.eth_amount != expected_eth:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        existing = await session.scalar(select(ExchangePayment).where(ExchangePayment.idempotency_key == idempotency_key))
        if existing:
            return _payment_dict(existing)

    now = int(time.time())
    payment = ExchangePayment(
        user_id=payment_request.user_id,
        aitbc_amount=payment_request.aitbc_amount,
        eth_amount=payment_request.eth_amount,
        payment_address=ETHEREUM_CONFIG["main_address"],
        status="pending",
        idempotency_key=idempotency_key,
        created_at=now,
        expires_at=now + ETHEREUM_CONFIG["payment_timeout"],
        confirmations=0,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    logger.info("Created exchange payment %s for user %s", payment.payment_id, payment.user_id)
    background_tasks.add_task(_monitor_payment, payment.payment_id)
    return _payment_dict(payment)


@router.get("/v1/exchange/payment-status/{payment_id}", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_payment_status(
    payment_id: str,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> dict[str, Any]:
    """Get payment status (migrated from Coordinator API)."""
    payment = await session.get(ExchangePayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "pending" and time.time() > payment.expires_at:
        payment.status = "expired"
        session.add(payment)
        await session.commit()
    return _payment_dict(payment)


@router.post("/v1/exchange/confirm-payment/{payment_id}", dependencies=[Depends(require_webhook_signature)])
async def confirm_exchange_payment(
    payment_id: str,
    tx_hash: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> dict[str, Any]:
    """Confirm payment (webhook from payment processor, migrated from Coordinator API)."""
    payment = await session.get(ExchangePayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "pending":
        raise HTTPException(status_code=400, detail="Payment not in pending state")
    payment.status = "confirmed"
    payment.tx_hash = tx_hash
    payment.confirmed_at = int(time.time())
    session.add(payment)
    await session.commit()
    try:
        logger.info("Minting %s %s tokens for user %s", payment.aitbc_amount, _brand.token_symbol, payment.user_id)
    except Exception as e:
        logger.error("Error minting tokens: %s", e)
    logger.info("Confirmed exchange payment %s with tx_hash %s", payment_id, tx_hash)
    return {"status": "ok", "payment_id": payment_id, "aitbc_amount": str(payment.aitbc_amount)}


@router.get("/v1/exchange/rates", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_rates() -> dict[str, Any]:
    """Get current exchange rates (migrated from Coordinator API)."""
    return {
        "eth_to_aitbc": ETHEREUM_CONFIG["exchange_rate"],
        "aitbc_to_eth": 1.0 / ETHEREUM_CONFIG["exchange_rate"],
        "fee_percent": 0.5,
    }


@router.get("/v1/exchange/market-stats", dependencies=[Depends(require_trading_api_key)])
async def get_market_stats(session: Annotated[AsyncSession, Depends(get_session_dep)]) -> dict[str, Any]:
    """Get market statistics (migrated from Coordinator API)."""
    yesterday_time = int(time.time()) - 24 * 60 * 60
    result = await session.execute(
        select(ExchangePayment).where(
            ExchangePayment.status == "confirmed",
            ExchangePayment.confirmed_at > yesterday_time,
        )
    )
    confirmed_today: Sequence[ExchangePayment] = result.scalars().all()
    daily_volume = sum((p.aitbc_amount for p in confirmed_today), Decimal("0"))
    base_price = Decimal("1") / ETHEREUM_CONFIG["exchange_rate"]
    price_change_percent = 5.2
    total_stmt = select(ExchangePayment).where(ExchangePayment.status == "confirmed")
    total_result = await session.execute(total_stmt)
    pending_stmt = select(ExchangePayment).where(ExchangePayment.status == "pending")
    pending_result = await session.execute(pending_stmt)
    return {
        "price": str(base_price),
        "price_change_24h": price_change_percent,
        "daily_volume": str(daily_volume),
        "daily_volume_eth": str(daily_volume / ETHEREUM_CONFIG["exchange_rate"]),
        "total_payments": len(total_result.scalars().all()),
        "pending_payments": len(pending_result.scalars().all()),
    }


@router.get("/v1/exchange/wallet/balance", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_wallet_balance() -> dict[str, Any]:
    """Get Ethereum wallet balance (migrated from Coordinator API)."""
    return {"balance": 0.0, "unconfirmed_balance": 0.0, "address": ETHEREUM_CONFIG["main_address"]}


@router.get("/v1/exchange/wallet/info", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_wallet_info() -> dict[str, Any]:
    """Get comprehensive wallet information (migrated from Coordinator API)."""
    return {"address": ETHEREUM_CONFIG["main_address"], "network": "testnet", "balance": 0.0, "transactions": []}


async def _monitor_payment(payment_id: str) -> None:
    """Monitor payment for confirmation (background task, migrated from Coordinator API)."""
    async with get_session() as session:
        while True:
            payment = await session.get(ExchangePayment, payment_id)
            if payment is None:
                break
            if payment.status == "pending" and time.time() > payment.expires_at:
                payment.status = "expired"
                session.add(payment)
                await session.commit()
                logger.info("Payment %s expired", payment_id)
                break
            if payment.status != "pending":
                break
            await asyncio.sleep(30)
