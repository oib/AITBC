"""
Bitcoin Exchange Router for AITBC
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlmodel import Session
import uuid
import time
import json
import os

from ..deps import require_admin_key, require_client_key
from ..domain import Wallet
from ..schemas import ExchangePaymentRequest, ExchangePaymentResponse

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
    background_tasks: BackgroundTasks,
    api_key: str = require_client_key()
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

@router.get("/exchange/payment-status/{payment_id}")
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
    tx_hash: str,
    api_key: str = require_admin_key()
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
        await mint_tokens(payment['user_id'], payment['aitbc_amount'])
    except Exception as e:
        print(f"Error minting tokens: {e}")
        # In production, handle this error properly
    
    return {
        'status': 'ok',
        'payment_id': payment_id,
        'aitbc_amount': payment['aitbc_amount']
    }

@router.get("/exchange/rates")
async def get_exchange_rates() -> Dict[str, float]:
    """Get current exchange rates"""
    
    return {
        'btc_to_aitbc': BITCOIN_CONFIG['exchange_rate'],
        'aitbc_to_btc': 1.0 / BITCOIN_CONFIG['exchange_rate'],
        'fee_percent': 0.5
    }

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
