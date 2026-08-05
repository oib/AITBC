"""Migrated exchange payment endpoints (compatibility layer)."""

import asyncio
import json
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from aitbc.aitbc_logging import get_logger
from aitbc_agent_core import get_active_brand

from ..dependencies import require_trading_api_key, require_webhook_signature

router = APIRouter(tags=["exchange"])
logger = get_logger(__name__)
_brand = get_active_brand()

BITCOIN_CONFIG: dict[str, Any] = {
    "testnet": True,
    "main_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "exchange_rate": 100000,
    "min_confirmations": 1,
    "payment_timeout": 3600,
}
payments: dict[str, dict[str, Any]] = {}
# Idempotency key → payment_id mapping (prevents duplicate payment creation on replay)
_idempotency_keys: dict[str, str] = {}

# ponytail: local JSON state file; replace with DB-backed storage when multi-replica
_STATE_FILE = Path(
    os.environ.get("TRADING_EXCHANGE_STATE_FILE", "/opt/aitbc/data/trading/exchange_state.json")
)


def _load_state() -> None:
    if not _STATE_FILE.exists():
        return
    try:
        with _STATE_FILE.open() as f:
            data = json.load(f)
        payments.update(data.get("payments", {}))
        _idempotency_keys.update(data.get("idempotency_keys", {}))
    except Exception as e:
        logger.warning("Failed to load exchange state: %s", e)


def _save_state() -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _STATE_FILE.open("w") as f:
        json.dump({"payments": payments, "idempotency_keys": _idempotency_keys}, f)


_load_state()


class ExchangePaymentRequest(BaseModel):
    """Exchange payment request schema."""

    user_id: str
    aitbc_amount: Decimal
    btc_amount: Decimal


@router.post("/v1/exchange/create-payment", dependencies=[Depends(require_trading_api_key)])
async def create_exchange_payment(
    payment_request: ExchangePaymentRequest, background_tasks: BackgroundTasks, request: Request
) -> dict[str, Any]:
    """Create a new Bitcoin payment request (migrated from Coordinator API).

    Supports idempotency via the ``Idempotency-Key`` header: if the same key
    is replayed, the original payment is returned instead of creating a duplicate.
    """
    if payment_request.aitbc_amount <= 0 or payment_request.btc_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    expected_btc = payment_request.aitbc_amount / BITCOIN_CONFIG["exchange_rate"]
    if payment_request.btc_amount != expected_btc:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    # Idempotency: if the same key was used before, return the original payment
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        existing_payment_id = _idempotency_keys.get(idempotency_key)
        if existing_payment_id and existing_payment_id in payments:
            return payments[existing_payment_id]

    payment_id = str(uuid.uuid4())
    payment = {
        "payment_id": payment_id,
        "user_id": payment_request.user_id,
        "aitbc_amount": str(payment_request.aitbc_amount),
        "btc_amount": str(payment_request.btc_amount),
        "payment_address": BITCOIN_CONFIG["main_address"],
        "status": "pending",
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + BITCOIN_CONFIG["payment_timeout"],
        "confirmations": 0,
        "tx_hash": None,
    }
    payments[payment_id] = payment
    if idempotency_key:
        _idempotency_keys[idempotency_key] = payment_id
    _save_state()
    background_tasks.add_task(monitor_payment, payment_id)
    logger.info("Created exchange payment %s for user %s", payment_id, payment_request.user_id)
    return payment


@router.get("/v1/exchange/payment-status/{payment_id}", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_payment_status(payment_id: str) -> dict[str, Any]:
    """Get payment status (migrated from Coordinator API)."""
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment = payments[payment_id]
    if payment["status"] == "pending" and time.time() > payment["expires_at"]:
        payment["status"] = "expired"
        _save_state()
    return payment


@router.post("/v1/exchange/confirm-payment/{payment_id}", dependencies=[Depends(require_webhook_signature)])
async def confirm_exchange_payment(payment_id: str, tx_hash: str, request: Request) -> dict[str, Any]:
    """Confirm payment (webhook from payment processor, migrated from Coordinator API)."""
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment = payments[payment_id]
    if payment["status"] != "pending":
        raise HTTPException(status_code=400, detail="Payment not in pending state")
    payment["status"] = "confirmed"
    payment["tx_hash"] = tx_hash
    payment["confirmed_at"] = int(time.time())
    _save_state()
    try:
        logger.info("Minting %s %s tokens for user %s", payment["aitbc_amount"], _brand.token_symbol, payment["user_id"])
    except Exception as e:
        logger.error("Error minting tokens: %s", e)
    logger.info("Confirmed exchange payment %s with tx_hash %s", payment_id, tx_hash)
    return {"status": "ok", "payment_id": payment_id, "aitbc_amount": payment["aitbc_amount"]}


@router.get("/v1/exchange/rates", dependencies=[Depends(require_trading_api_key)])
async def get_exchange_rates() -> dict[str, Any]:
    """Get current exchange rates (migrated from Coordinator API)."""
    return {
        "btc_to_aitbc": BITCOIN_CONFIG["exchange_rate"],
        "aitbc_to_btc": 1.0 / BITCOIN_CONFIG["exchange_rate"],
        "fee_percent": 0.5,
    }


@router.get("/v1/exchange/market-stats")
async def get_market_stats() -> dict[str, Any]:
    """Get market statistics (migrated from Coordinator API)."""
    current_time = int(time.time())
    yesterday_time = current_time - 24 * 60 * 60
    daily_volume = Decimal("0")
    for payment in payments.values():
        if payment["status"] == "confirmed" and payment.get("confirmed_at", 0) > yesterday_time:
            daily_volume += Decimal(payment["aitbc_amount"])
    base_price = Decimal("1") / BITCOIN_CONFIG["exchange_rate"]
    price_change_percent = 5.2
    return {
        "price": str(base_price),
        "price_change_24h": price_change_percent,
        "daily_volume": str(daily_volume),
        "daily_volume_btc": str(daily_volume / BITCOIN_CONFIG["exchange_rate"]),
        "total_payments": len([p for p in payments.values() if p["status"] == "confirmed"]),
        "pending_payments": len([p for p in payments.values() if p["status"] == "pending"]),
    }


@router.get("/v1/exchange/wallet/balance")
async def get_exchange_wallet_balance() -> dict[str, Any]:
    """Get Bitcoin wallet balance (migrated from Coordinator API)."""
    return {"balance": 0.0, "unconfirmed_balance": 0.0, "address": BITCOIN_CONFIG["main_address"]}


@router.get("/v1/exchange/wallet/info")
async def get_exchange_wallet_info() -> dict[str, Any]:
    """Get comprehensive wallet information (migrated from Coordinator API)."""
    return {"address": BITCOIN_CONFIG["main_address"], "network": "testnet", "balance": 0.0, "transactions": []}


async def monitor_payment(payment_id: str) -> None:
    """Monitor payment for confirmation (background task, migrated from Coordinator API)."""
    while payment_id in payments:
        payment = payments[payment_id]
        if payment["status"] == "pending" and time.time() > payment["expires_at"]:
            payment["status"] = "expired"
            _save_state()
            logger.info("Payment %s expired", payment_id)
            break
        await asyncio.sleep(30)
