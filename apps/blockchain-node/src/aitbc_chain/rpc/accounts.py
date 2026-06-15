"""
Account-related RPC endpoints.
"""

import hashlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import select

from aitbc.rate_limiting import rate_limit
from aitbc.redis_cache import RedisCache

from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Transaction
from .utils import get_chain_id

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_cache = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
ACCOUNT_CACHE_TTL = 30
_logger = get_logger(__name__)


@rate_limit(rate=200, per=60)
async def get_account(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information"""
    chain_id = get_chain_id(chain_id)
    cache_key = f"account_balance:{chain_id}:{address.lower()}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    with session_scope() as session:
        account = session.exec(select(Account).where(Account.address == address).where(Account.chain_id == chain_id)).first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        result = {"address": account.address, "balance": account.balance, "nonce": account.nonce, "chain_id": account.chain_id}
        _cache.set(cache_key, result, ttl=ACCOUNT_CACHE_TTL)
        return result


@rate_limit(rate=200, per=60)
async def get_account_alias(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account(request, address, chain_id)


@rate_limit(rate=200, per=60)
async def get_account_details(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """
    Get account details including balance and nonce.

    Args:
        address: The account address
        chain_id: Optional chain ID (defaults to node's chain)

    Returns:
        Account details or 404 if not found
    """
    chain_id = get_chain_id(chain_id)
    address = address.lower().strip()
    cache_key = f"account_details:{chain_id}:{address}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    with session_scope() as session:
        account = session.get(Account, (chain_id, address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {address} not found on chain {chain_id}")
        result = {
            "success": True,
            "address": account.address,
            "chain_id": account.chain_id,
            "balance": account.balance,
            "nonce": account.nonce,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }
        _cache.set(cache_key, result, ttl=ACCOUNT_CACHE_TTL)
        return result


@rate_limit(rate=100, per=60)
async def create_account(request: Request, account_data: dict[str, Any]) -> dict[str, Any]:
    """
    Create or register a new account on the blockchain.

    This endpoint allows wallets to register their public keys as accounts
    on the blockchain, enabling them to send and receive transactions.

    Args:
        account_data: Dictionary containing:
            - address: The account address/public key (hex string)
            - chain_id: Optional chain ID (defaults to node's chain)

    Returns:
        Dictionary with success status and account details
    """
    chain_id = get_chain_id(account_data.get("chain_id"))
    address = account_data.get("address")
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    if not all(c in "0123456789abcdef" for c in address[2:]):
        raise HTTPException(status_code=400, detail="address must be a valid hex string")
    with session_scope() as session:
        existing_account = session.get(Account, (chain_id, address))
        if existing_account:
            return {
                "success": True,
                "address": address,
                "chain_id": chain_id,
                "balance": existing_account.balance,
                "nonce": existing_account.nonce,
                "created": False,
                "message": "Account already exists",
            }
        new_account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
        session.add(new_account)
        session.commit()
        return {
            "success": True,
            "address": address,
            "chain_id": chain_id,
            "balance": 0,
            "nonce": 0,
            "created": True,
            "message": "Account created successfully",
        }


@rate_limit(rate=10, per=3600)
async def faucet_request(request: Request, faucet_data: dict[str, Any]) -> dict[str, Any]:
    """
    Request test tokens from the blockchain faucet.

    This endpoint allows newly created wallets to receive initial funds
    for testing and development purposes.

    Args:
        faucet_data: Dictionary containing:
            - address: The account address to fund
            - amount: Optional amount to request (default: 1000000)
            - chain_id: Optional chain ID (defaults to node's chain)

    Returns:
        Dictionary with success status and transaction details
    """
    chain_id = get_chain_id(faucet_data.get("chain_id"))
    address = faucet_data.get("address")
    amount = faucet_data.get("amount", 1000000)
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    if not all(c in "0123456789abcdef" for c in address[2:]):
        raise HTTPException(status_code=400, detail="address must be a valid hex string")
    if amount > 10000000:
        amount = 10000000
    with session_scope() as session:
        account = session.get(Account, (chain_id, address))
        if not account:
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)
            session.flush()
            _logger.info("Faucet auto-created account: %s", address)
        timestamp = datetime.now(UTC)
        tx_hash = hashlib.sha256(f"faucet:{address}:{amount}:{timestamp.isoformat()}:{uuid.uuid4()}".encode()).hexdigest()
        account.balance += amount
        session.add(account)
        faucet_tx = Transaction(
            chain_id=chain_id,
            tx_hash=tx_hash,
            sender="faucet",
            recipient=address,
            payload={"type": "FAUCET", "amount": amount, "reason": "test_funding"},
            value=amount,
            fee=0,
            nonce=0,
            timestamp=timestamp,
            block_height=None,
            status="confirmed",
            type="FAUCET",
        )
        session.add(faucet_tx)
        session.commit()
        return {
            "success": True,
            "address": address,
            "amount": amount,
            "tx_hash": tx_hash,
            "chain_id": chain_id,
            "message": "Faucet transaction completed",
        }


@rate_limit(rate=100, per=60)
async def get_balance_breakdown(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """
    Get detailed balance breakdown including:
    - Available balance
    - Staked amount
    - Bridge-locked amount
    - Total balance
    """
    try:
        from ..services.balance_tracker import get_balance_tracker

        tracker = get_balance_tracker()
        if not tracker:
            raise HTTPException(status_code=503, detail="Balance tracker not initialized")
        chain_id = get_chain_id(chain_id)
        address = address.lower().strip()
        breakdown = tracker.get_balance_breakdown(address, chain_id)
        return breakdown
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Failed to get balance breakdown: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}")


@rate_limit(rate=20, per=60)
async def reconcile_balance(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """
    Reconcile account balance against all recorded operations.

    Verifies that current balance matches expected balance
    based on all transactions, stakes, and bridge operations.
    """
    try:
        from ..services.balance_tracker import get_balance_tracker

        tracker = get_balance_tracker()
        if not tracker:
            raise HTTPException(status_code=503, detail="Balance tracker not initialized")
        chain_id = get_chain_id(chain_id)
        address = address.lower().strip()
        result = tracker.reconcile_balance(address, chain_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Balance reconciliation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")
