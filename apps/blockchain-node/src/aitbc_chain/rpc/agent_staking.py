"""Agent-economy staking RPC (V23-42). Distinct from consensus /rpc/staking/stake."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from aitbc.rate_limiting import rate_limit

from ..base_models import AgentStakeMemo, AgentStakeRecord, _to_ait_address
from ..database import session_scope
from ..logger import get_logger
from ..models import Account
from .agent_economics_auth import require_int, require_operator_signature
from .utils import get_chain_id, validate_chain_id

_logger = get_logger(__name__)
MAX_LOCK_DAYS = 3650


def _account(session: Session, chain_id: str, address: str) -> Account:
    account = session.get(Account, (chain_id, address))
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {address} not found")
    return account


def _get_stake(session: Session, chain_id: str, stake_id: str) -> AgentStakeRecord | None:
    return session.exec(
        select(AgentStakeRecord).where(AgentStakeRecord.chain_id == chain_id, AgentStakeRecord.stake_id == stake_id)
    ).first()


@rate_limit(rate=20, per=60)
async def create_agent_stake(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    if not validate_chain_id(chain_id):
        raise HTTPException(status_code=400, detail=f"Unsupported chain_id: {chain_id}")
    stake_id = payload.get("stake_id")
    staker = payload.get("user_address") or payload.get("staker_address")
    agent_wallet = payload.get("agent_wallet")
    if not stake_id or not staker or not agent_wallet:
        raise HTTPException(status_code=400, detail="stake_id, user_address and agent_wallet are required")
    staker = _to_ait_address(str(staker))
    agent_wallet = _to_ait_address(str(agent_wallet))
    amount = require_int(payload, "amount")
    lock_period = require_int(payload, "lock_period", minimum=1)
    if lock_period > MAX_LOCK_DAYS:
        raise HTTPException(status_code=400, detail=f"lock_period must be <= {MAX_LOCK_DAYS}")

    with session_scope() as session:
        existing = _get_stake(session, chain_id, str(stake_id))
        if existing:
            return {
                "success": True,
                "idempotent": True,
                "stake_id": existing.stake_id,
                "amount": existing.amount,
                "status": existing.status,
                "locked_until": existing.locked_until.isoformat(),
            }
        account = _account(session, chain_id, staker)
        if account.balance < amount:
            raise HTTPException(status_code=400, detail=f"Insufficient balance: {account.balance} < {amount}")
        account.balance -= amount
        session.add(account)
        locked_until = datetime.now(UTC) + timedelta(days=lock_period)
        record = AgentStakeRecord(
            chain_id=chain_id,
            stake_id=str(stake_id),
            staker_address=staker,
            agent_wallet=agent_wallet,
            amount=amount,
            lock_period=lock_period,
            locked_until=locked_until,
            status="active",
        )
        session.add(record)
        session.commit()
        _logger.info("Agent stake locked: %s amount=%s staker=%s", stake_id, amount, staker)
        return {
            "success": True,
            "stake_id": record.stake_id,
            "amount": record.amount,
            "status": record.status,
            "locked_until": record.locked_until.isoformat(),
            "remaining_balance": account.balance,
        }


@rate_limit(rate=20, per=60)
async def add_to_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    additional = require_int(payload, "additional_amount")
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        if record.staker_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        if record.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {record.status}")
        account = _account(session, chain_id, user)
        if account.balance < additional:
            raise HTTPException(status_code=400, detail=f"Insufficient balance: {account.balance} < {additional}")
        account.balance -= additional
        record.amount += additional
        record.updated_at = datetime.now(UTC)
        session.add(account)
        session.add(record)
        session.commit()
        return {"success": True, "stake_id": record.stake_id, "amount": record.amount, "remaining_balance": account.balance}


@rate_limit(rate=20, per=60)
async def unbond_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        if record.staker_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        if record.status == "unbonding":
            return {"success": True, "idempotent": True, "stake_id": record.stake_id, "status": record.status}
        if record.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {record.status}")
        now = datetime.now(UTC)
        locked_until = record.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if now < locked_until:
            raise HTTPException(status_code=400, detail=f"Lock period not expired. Locked until: {locked_until.isoformat()}")
        record.status = "unbonding"
        record.unbonding_at = now
        record.updated_at = now
        session.add(record)
        session.commit()
        return {"success": True, "stake_id": record.stake_id, "status": record.status}


@rate_limit(rate=20, per=60)
async def complete_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        if record.staker_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        if record.status == "completed":
            return {"success": True, "idempotent": True, "stake_id": record.stake_id, "status": record.status}
        if record.status != "unbonding":
            raise HTTPException(status_code=400, detail=f"Stake is not unbonding: {record.status}")
        now = datetime.now(UTC)
        locked_until = record.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if now < locked_until:
            raise HTTPException(status_code=400, detail="Lock period not expired")
        account = session.get(Account, (chain_id, user))
        if not account:
            account = Account(chain_id=chain_id, address=user, balance=0, nonce=0)
        account.balance += record.amount
        record.status = "completed"
        record.updated_at = now
        session.add(account)
        session.add(record)
        session.commit()
        return {
            "success": True,
            "stake_id": record.stake_id,
            "status": record.status,
            "amount": record.amount,
            "remaining_balance": account.balance,
        }


def _write_memo(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    external_id = str(payload.get("stake_id") or payload.get("agent_wallet") or "")
    with session_scope() as session:
        memo = AgentStakeMemo(chain_id=chain_id, kind=kind, external_id=external_id, payload=payload)
        session.add(memo)
        session.commit()
    return {"success": True, "kind": kind, "external_id": external_id}


@rate_limit(rate=20, per=60)
async def record_performance(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return _write_memo("performance", body)


@rate_limit(rate=20, per=60)
async def record_distribute(request: Request, agent_wallet: str, body: dict[str, Any]) -> dict[str, Any]:
    body = {**body, "agent_wallet": body.get("agent_wallet") or agent_wallet}
    return _write_memo("distribute", body)


@rate_limit(rate=20, per=60)
async def record_claim(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return _write_memo("claim", body)
