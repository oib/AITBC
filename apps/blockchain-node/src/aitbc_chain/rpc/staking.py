"""
Staking-related RPC endpoints.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Stake, AgentIdentity
from .utils import get_chain_id

_logger = get_logger(__name__)


@rate_limit(rate=20, per=60)
async def stake_tokens(
    request: Request,
    stake_data: dict
) -> dict[str, Any]:
    """
    Stake tokens for consensus participation.
    
    Locks tokens for a specified period. Staked tokens earn rewards
    and provide voting power in consensus.
    """
    chain_id = get_chain_id(stake_data.get("chain_id"))
    address = stake_data.get("address")
    amount = stake_data.get("amount", 0)
    lock_days = stake_data.get("lock_days", 30)

    if not address:
        raise HTTPException(status_code=400, detail="address is required")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address

    with session_scope() as session:
        # Get account
        account = session.get(Account, (chain_id, address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {address} not found")

        if account.balance < amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance: {account.balance} < {amount}"
            )

        # Lock tokens (deduct from balance)
        account.balance -= amount
        session.add(account)

        # Calculate lock period
        locked_until = datetime.now(UTC)
        locked_until = locked_until.replace(day=locked_until.day + lock_days)

        # Create stake record
        stake = Stake(
            chain_id=chain_id,
            address=address,
            amount=amount,
            locked_until=locked_until,
            status="active"
        )
        session.add(stake)
        session.commit()

        _logger.info(f"Tokens staked: {address} staked {amount} on {chain_id}")

        return {
            "success": True,
            "stake_id": stake.id,
            "address": address,
            "amount": amount,
            "chain_id": chain_id,
            "locked_until": locked_until.isoformat(),
            "status": "active",
            "remaining_balance": account.balance
        }


@rate_limit(rate=10, per=60)
async def unstake_tokens(
    request: Request,
    unstake_data: dict
) -> dict[str, Any]:
    """
    Unstake tokens after lock period expires.
    
    Returns staked tokens to account balance.
    """
    chain_id = get_chain_id(unstake_data.get("chain_id"))
    address = unstake_data.get("address")
    stake_id = unstake_data.get("stake_id")

    if not address or not stake_id:
        raise HTTPException(status_code=400, detail="address and stake_id are required")

    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address

    with session_scope() as session:
        # Get stake record
        stake = session.get(Stake, stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")

        if stake.address != address:
            raise HTTPException(status_code=403, detail="Not authorized to unstake")

        if stake.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {stake.status}")

        # Check if lock period expired
        now = datetime.now(UTC)
        if stake.locked_until and now < stake.locked_until:
            raise HTTPException(
                status_code=400,
                detail=f"Lock period not expired. Locked until: {stake.locked_until.isoformat()}"
            )

        # Return tokens to account
        account = session.get(Account, (chain_id, address))
        if not account:
            # Account was deleted, recreate
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)

        account.balance += stake.amount
        session.add(account)

        # Update stake status
        stake.status = "withdrawn"
        session.add(stake)
        session.commit()

        _logger.info(f"Tokens unstaked: {address} recovered {stake.amount} from stake {stake_id}")

        return {
            "success": True,
            "stake_id": stake_id,
            "address": address,
            "amount": stake.amount,
            "chain_id": chain_id,
            "new_balance": account.balance,
            "status": "withdrawn"
        }


@rate_limit(rate=100, per=60)
async def get_staking_info(
    request: Request,
    address: str,
    chain_id: str = None
) -> dict[str, Any]:
    """Get staking information for an address"""
    chain_id = get_chain_id(chain_id)
    address = address.lower().strip()

    with session_scope() as session:
        # Get all stakes for address
        statement = select(Stake).where(
            Stake.chain_id == chain_id,
            Stake.address == address
        )
        stakes = session.exec(statement).all()

        total_staked = sum(s.amount for s in stakes if s.status == "active")
        active_stakes = [
            {
                "stake_id": s.id,
                "amount": s.amount,
                "locked_until": s.locked_until.isoformat() if s.locked_until else None,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in stakes if s.status == "active"
        ]

        return {
            "success": True,
            "address": address,
            "chain_id": chain_id,
            "total_staked": total_staked,
            "active_stake_count": len(active_stakes),
            "active_stakes": active_stakes
        }


@rate_limit(rate=20, per=60)
async def register_agent_identity(
    request: Request,
    identity_data: dict
) -> dict[str, Any]:
    """
    Register an agent identity on the blockchain.
    
    Records agent metadata and verification status on-chain for cross-node verification.
    """
    chain_id = get_chain_id(identity_data.get("chain_id"))
    agent_id = identity_data.get("agent_id")
    agent_address = identity_data.get("agent_address")
    display_name = identity_data.get("display_name")
    agent_type = identity_data.get("agent_type", "general")
    capabilities = identity_data.get("capabilities", {})

    if not agent_id or not agent_address:
        raise HTTPException(status_code=400, detail="agent_id and agent_address are required")

    # Normalize address
    agent_address = agent_address.lower().strip()
    if not agent_address.startswith("0x"):
        agent_address = "0x" + agent_address

    with session_scope() as session:
        # Check if identity already exists
        existing = session.exec(
            select(AgentIdentity).where(
                AgentIdentity.chain_id == chain_id,
                AgentIdentity.agent_id == agent_id
            )
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail=f"Agent identity already exists: {agent_id}")

        # Create agent identity record
        identity = AgentIdentity(
            chain_id=chain_id,
            agent_id=agent_id,
            agent_address=agent_address,
            display_name=display_name,
            agent_type=agent_type,
            capabilities=capabilities,
            status="active",
            is_verified=False
        )
        session.add(identity)
        session.commit()
        session.refresh(identity)

        _logger.info(f"Agent identity registered on-chain: {agent_id} -> {agent_address}")

        return {
            "success": True,
            "identity_id": identity.id,
            "agent_id": agent_id,
            "agent_address": agent_address,
            "chain_id": chain_id,
            "status": identity.status,
            "is_verified": identity.is_verified
        }


@rate_limit(rate=50, per=60)
async def get_agent_identity(
    request: Request,
    agent_id: str,
    chain_id: str = None
) -> dict[str, Any]:
    """Get agent identity from blockchain"""
    chain_id = get_chain_id(chain_id)

    with session_scope() as session:
        identity = session.exec(
            select(AgentIdentity).where(
                AgentIdentity.chain_id == chain_id,
                AgentIdentity.agent_id == agent_id
            )
        ).first()

        if not identity:
            raise HTTPException(status_code=404, detail=f"Agent identity not found: {agent_id}")

        return {
            "success": True,
            "identity_id": identity.id,
            "agent_id": identity.agent_id,
            "agent_address": identity.agent_address,
            "display_name": identity.display_name,
            "agent_type": identity.agent_type,
            "capabilities": identity.capabilities,
            "status": identity.status,
            "is_verified": identity.is_verified,
            "verified_at": identity.verified_at.isoformat() if identity.verified_at else None,
            "created_at": identity.created_at.isoformat() if identity.created_at else None,
            "chain_id": chain_id
        }


@rate_limit(rate=50, per=60)
async def verify_agent_identity(
    request: Request,
    verification_data: dict
) -> dict[str, Any]:
    """
    Verify an agent identity on the blockchain.
    
    Marks an agent identity as verified after successful validation.
    """
    chain_id = get_chain_id(verification_data.get("chain_id"))
    agent_id = verification_data.get("agent_id")
    verifier_address = verification_data.get("verifier_address")

    if not agent_id or not verifier_address:
        raise HTTPException(status_code=400, detail="agent_id and verifier_address are required")

    with session_scope() as session:
        identity = session.exec(
            select(AgentIdentity).where(
                AgentIdentity.chain_id == chain_id,
                AgentIdentity.agent_id == agent_id
            )
        ).first()

        if not identity:
            raise HTTPException(status_code=404, detail=f"Agent identity not found: {agent_id}")

        # Update verification status
        identity.is_verified = True
        identity.verified_at = datetime.now(UTC)
        identity.verified_by = verifier_address
        session.add(identity)
        session.commit()

        _logger.info(f"Agent identity verified: {agent_id} by {verifier_address}")

        return {
            "success": True,
            "identity_id": identity.id,
            "agent_id": agent_id,
            "is_verified": True,
            "verified_at": identity.verified_at.isoformat(),
            "verified_by": verifier_address,
            "chain_id": chain_id
        }
