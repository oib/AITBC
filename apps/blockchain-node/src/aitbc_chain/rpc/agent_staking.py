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
from ..protocol_escrow import confirmed_lock_total, queue_protocol_transfer, stake_escrow_address
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
        # Only the stake record is written here. The debit is carried by the
        # STAKE_LOCK transfer and applied at block time; mutating the account
        # table outside block processing desynchronises it from every block
        # header. See ``protocol_escrow``.
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
        session.refresh(record)
        result = {
            "success": True,
            "stake_id": record.stake_id,
            "amount": record.amount,
            "status": record.status,
            "locked_until": record.locked_until.isoformat(),
        }

    tx_hash = queue_protocol_transfer(
        sender=staker,
        recipient=stake_escrow_address(),
        amount=amount,
        chain_id=chain_id,
        tx_type="STAKE_LOCK",
        payload={"agent_stake_id": str(stake_id)},
    )
    _logger.info("Agent stake lock queued: %s amount=%s staker=%s tx=%s", stake_id, amount, staker, tx_hash)
    result["transaction_hash"] = tx_hash
    result["message"] = "Stake lock submitted to mempool; the balance moves when the transaction is included in a block"
    return result


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
        # As in create_agent_stake: the record grows here, the balance moves in
        # a block. Each top-up queues its own STAKE_LOCK, and
        # complete_agent_stake requires the confirmed locks to cover the whole
        # principal before it releases anything.
        record.amount += additional
        record.updated_at = datetime.now(UTC)
        session.add(record)
        session.commit()
        session.refresh(record)
        total_amount = record.amount

    tx_hash = queue_protocol_transfer(
        sender=user,
        recipient=stake_escrow_address(),
        amount=additional,
        chain_id=chain_id,
        tx_type="STAKE_LOCK",
        payload={"agent_stake_id": str(stake_id)},
    )
    return {
        "success": True,
        "stake_id": str(stake_id),
        "amount": total_amount,
        "transaction_hash": tx_hash,
        "message": "Stake top-up submitted to mempool; the balance moves when the transaction is included in a block",
    }


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
        # The escrow is shared across all stakers, so the full principal must
        # be provably in it before any of it is released back.
        funded = confirmed_lock_total(session, chain_id, "STAKE_LOCK", "agent_stake_id", record.stake_id)
        if funded < record.amount:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Stake {record.stake_id} is not fully confirmed on-chain "
                    f"({funded} of {record.amount} locked); retry once the lock transactions are in a block"
                ),
            )
        amount = record.amount
        record.status = "completed"
        record.updated_at = now
        session.add(record)
        session.commit()

    tx_hash = queue_protocol_transfer(
        sender=stake_escrow_address(),
        recipient=user,
        amount=amount,
        chain_id=chain_id,
        tx_type="STAKE_RELEASE",
        payload={"agent_stake_id": str(stake_id)},
    )
    return {
        "success": True,
        "stake_id": str(stake_id),
        "status": "completed",
        "amount": amount,
        "transaction_hash": tx_hash,
        "message": "Stake release submitted to mempool; the balance moves when the transaction is included in a block",
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
