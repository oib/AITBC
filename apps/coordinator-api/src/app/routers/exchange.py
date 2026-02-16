"""
Bitcoin Exchange Router for AITBC
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
import uuid
import time
import json
import os
import logging

logger = logging.getLogger(__name__)

from ..schemas import (
    ExchangePaymentRequest, 
    ExchangePaymentResponse,
    ExchangeRatesResponse,
    PaymentStatusResponse,
    MarketStatsResponse,
    WalletBalanceResponse,
    WalletInfoResponse
)
from ..services.bitcoin_wallet import get_wallet_balance, get_wallet_info

router = APIRouter(tags=["exchange"])

# In-memory storage for demo (use database in production)
payments: Dict[str, Dict] = {}

# Bitcoin configuration
BITCOIN_CONFIG = {
    'testnet': True,
    'main_address': 'tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',  # Testnet address
    'exchange_rate': 100000,  # 1 BTC = 100,000 AITBC
    'min_confirmations': 1,
    'payment_timeout': 3600  # 1 hour
}

@router.post("/exchange/create-payment", response_model=ExchangePaymentResponse)
async def create_payment(
    request: ExchangePaymentRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Create a new Bitcoin payment request"""
    
    # Validate request
    if request.aitbc_amount <= 0 or request.btc_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    # Calculate expected BTC amount
    expected_btc = request.aitbc_amount / BITCOIN_CONFIG['exchange_rate']
    
    # Allow small difference for rounding
    if abs(request.btc_amount - expected_btc) > 0.00000001:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    
    # Create payment record
    payment_id = str(uuid.uuid4())
    payment = {
        'payment_id': payment_id,
        'user_id': request.user_id,
        'aitbc_amount': request.aitbc_amount,
        'btc_amount': request.btc_amount,
        'payment_address': BITCOIN_CONFIG['main_address'],
        'status': 'pending',
        'created_at': int(time.time()),
        'expires_at': int(time.time()) + BITCOIN_CONFIG['payment_timeout'],
        'confirmations': 0,
        'tx_hash': None
    }
    
    # Store payment
    payments[payment_id] = payment
    
    # Start payment monitoring in background
    background_tasks.add_task(monitor_payment, payment_id)
    
    return payment


@router.get("/exchange/payment-status/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(payment_id: str) -> Dict[str, Any]:
    """Get payment status"""
    
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = payments[payment_id]
    
    # Check if expired
    if payment['status'] == 'pending' and time.time() > payment['expires_at']:
        payment['status'] = 'expired'
    
    return payment


@router.post("/exchange/confirm-payment/{payment_id}")
async def confirm_payment(
    payment_id: str,
    tx_hash: str
) -> Dict[str, Any]:
    """Confirm payment (webhook from payment processor)"""
    
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = payments[payment_id]
    
    if payment['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Payment not in pending state")
    
    # Verify transaction (in production, verify with blockchain API)
    # For demo, we'll accept any tx_hash
    
    payment['status'] = 'confirmed'
    payment['tx_hash'] = tx_hash
    payment['confirmed_at'] = int(time.time())
    
    # Mint AITBC tokens to user's wallet
    try:
        from ..services.blockchain import mint_tokens
        mint_tokens(payment['user_id'], payment['aitbc_amount'])
    except Exception as e:
        logger.error("Error minting tokens: %s", e)
        # In production, handle this error properly
    
    return {
        'status': 'ok',
        'payment_id': payment_id,
        'aitbc_amount': payment['aitbc_amount']
    }


@router.get("/exchange/rates", response_model=ExchangeRatesResponse)
async def get_exchange_rates() -> ExchangeRatesResponse:
    """Get current exchange rates"""
    
    return ExchangeRatesResponse(
        btc_to_aitbc=BITCOIN_CONFIG['exchange_rate'],
        aitbc_to_btc=1.0 / BITCOIN_CONFIG['exchange_rate'],
        fee_percent=0.5
    )


@router.get("/exchange/market-stats", response_model=MarketStatsResponse)
async def get_market_stats() -> MarketStatsResponse:
    """Get market statistics"""
    
    # Calculate 24h volume from payments
    current_time = int(time.time())
    yesterday_time = current_time - 24 * 60 * 60  # 24 hours ago
    
    daily_volume = 0
    for payment in payments.values():
        if payment['status'] == 'confirmed' and payment.get('confirmed_at', 0) > yesterday_time:
            daily_volume += payment['aitbc_amount']
    
    # Calculate price change (simulated)
    base_price = 1.0 / BITCOIN_CONFIG['exchange_rate']
    price_change_percent = 5.2  # Simulated +5.2%
    
    return MarketStatsResponse(
        price=base_price,
        price_change_24h=price_change_percent,
        daily_volume=daily_volume,
        daily_volume_btc=daily_volume / BITCOIN_CONFIG['exchange_rate'],
        total_payments=len([p for p in payments.values() if p['status'] == 'confirmed']),
        pending_payments=len([p for p in payments.values() if p['status'] == 'pending'])
    )


@router.get("/exchange/wallet/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance_api() -> WalletBalanceResponse:
    """Get Bitcoin wallet balance"""
    try:
        balance_data = get_wallet_balance()
        return WalletBalanceResponse(**balance_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exchange/wallet/info", response_model=WalletInfoResponse)
async def get_wallet_info_api() -> WalletInfoResponse:
    """Get comprehensive wallet information"""
    try:
        wallet_data = get_wallet_info()
        return WalletInfoResponse(**wallet_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def monitor_payment(payment_id: str):
    """Monitor payment for confirmation (background task)"""
    
    import asyncio
    
    while payment_id in payments:
        payment = payments[payment_id]
        
        # Check if expired
        if payment['status'] == 'pending' and time.time() > payment['expires_at']:
            payment['status'] = 'expired'
            break
        
        # In production, check blockchain for payment
        # For demo, we'll wait for manual confirmation
        
        await asyncio.sleep(30)  # Check every 30 seconds
