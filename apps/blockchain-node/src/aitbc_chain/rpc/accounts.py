"""
Account-related RPC endpoints.
"""

import hashlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException, Request, status
from sqlmodel import select

from aitbc.rate_limiting import rate_limit
from aitbc.redis_cache import RedisCache

from ..config import settings
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Block, Transaction
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
    with session_scope(chain_id) as session:
        account = session.exec(select(Account).where(Account.address == address).where(Account.chain_id == chain_id)).first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        result = {"address": account.address, "balance": account.balance, "nonce": account.nonce, "chain_id": account.chain_id}
        _cache.set(cache_key, result, ttl=ACCOUNT_CACHE_TTL)
        return result


@rate_limit(rate=200, per=60)
async def get_account_alias(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information (alias endpoint)"""
    return cast(dict[str, Any], await get_account(request, address, chain_id))


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
    with session_scope(chain_id) as session:
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
    with session_scope(chain_id) as session:
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
    amount = faucet_data.get("amount", 3600000000)
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    if not all(c in "0123456789abcdef" for c in address[2:]):
        raise HTTPException(status_code=400, detail="address must be a valid hex string")
    if amount > 36000000000:
        amount = 36000000000
    with session_scope(chain_id) as session:
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
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}") from e


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
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}") from e


async def get_state_snapshot(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Return all accounts for a chain — used by followers to sync state.

    Returns the full account set (address, balance, nonce) so followers
    can reconcile their local state with the hub's state root.
    """
    chain_id = get_chain_id(chain_id)
    with session_scope(chain_id) as session:
        accounts = session.exec(select(Account).where(Account.chain_id == chain_id)).all()
        from ..state.merkle_patricia_trie import StateManager

        state_manager = StateManager()
        account_dict = {acc.address: acc for acc in accounts}
        state_root = state_manager.compute_state_root(account_dict)
        return {
            "chain_id": chain_id,
            "account_count": len(accounts),
            "state_root": f"0x{state_root.hex()}",
            "accounts": [
                {
                    "address": acc.address,
                    "balance": acc.balance,
                    "nonce": acc.nonce,
                }
                for acc in accounts
            ],
        }


async def get_state_delta(request: Request, from_height: int, to_height: int, chain_id: str | None = None) -> dict[str, Any]:
    """Return state delta (changed accounts) between two block heights.

    Used by followers for delta sync — only changed accounts are transferred
    instead of the full state snapshot. Falls back gracefully when historical
    state is not available.
    """
    import base64

    chain_id = get_chain_id(chain_id)

    # Validate gap
    max_blocks = getattr(settings, "sync_delta_max_blocks", 100)
    if to_height <= from_height:
        return {"error": "to_height must be greater than from_height"}
    if to_height - from_height > max_blocks:
        return {
            "error": f"Gap too large ({to_height - from_height} > {max_blocks})",
            "fallback": "full_sync",
        }

    with session_scope(chain_id) as session:
        # Get state roots at from_height and to_height
        from_block = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == from_height)).first()
        to_block = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == to_height)).first()

        if not to_block:
            return {"error": f"Block at height {to_height} not found"}

        from_state_root = (from_block.state_root if from_block else "") or ""
        to_state_root = to_block.state_root or ""

        # Find touched addresses by looking at transactions in the height range
        touched_addresses: set[str] = set()
        txs = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.block_height > from_height,  # type: ignore[operator]
                Transaction.block_height <= to_height,  # type: ignore[operator]
            )
        ).all()
        for tx in txs:
            if tx.sender:
                touched_addresses.add(tx.sender)
            if tx.recipient:
                touched_addresses.add(tx.recipient)

        # If no touched addresses found (no transactions), fall back to returning
        # all accounts as the diff (caller will check is_too_large)
        if not touched_addresses:
            accounts = session.exec(select(Account).where(Account.chain_id == chain_id)).all()
        else:
            accounts = session.exec(
                select(Account).where(
                    Account.chain_id == chain_id,
                    Account.address.in_(touched_addresses),  # type: ignore[attr-defined]
                )
            ).all()

        # We don't have historical account state, so treat all touched accounts
        # as new (old_balance=0, old_nonce=0). The caller applies the new values.
        old_accounts: dict[str, tuple[int, int]] = {}
        new_accounts: dict[str, tuple[int, int]] = {acc.address: (acc.balance, acc.nonce) for acc in accounts}

        from aitbc.sync import compute_state_diff, encode_state_diff

        diff = compute_state_diff(
            old_accounts=old_accounts,
            new_accounts=new_accounts,
            from_height=from_height,
            to_height=to_height,
            from_state_root=from_state_root,
            to_state_root=to_state_root,
            chain_id=chain_id,
        )

        encoded = encode_state_diff(diff)
        encoded_b64 = base64.b64encode(encoded).decode("ascii")

        return {
            "diff": encoded_b64,
            "from_height": from_height,
            "to_height": to_height,
            "from_state_root": from_state_root,
            "to_state_root": to_state_root,
            "account_count": len(diff.changes),
        }
