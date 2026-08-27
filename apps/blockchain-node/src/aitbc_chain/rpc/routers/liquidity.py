"""Liquidity pool RPC endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from aitbc.rate_limiting import rate_limit
from aitbc.utils import seconds_to_ait

from ...database import session_scope
from ...logger import get_logger
from ...models import Account, LiquidityPool, LiquidityStake
from ...state.liquidity import (
    _get_or_create_pool,
    _pending_rewards,
    _realize_fixed_apy,
    pool_main_address,
    pool_treasury_address,
)
from ..utils import get_chain_id

logger = get_logger(__name__)
router = APIRouter(prefix="/liquidity", tags=["liquidity"])


class BuildDepositRequest(BaseModel):
    address: str
    amount: int  # compute-seconds
    lock_days: int = 0
    pool_id: str = "main"
    fee: int = 3600  # 1 AIT default


class BuildClaimRequest(BaseModel):
    address: str
    stake_id: str
    pool_id: str = "main"
    fee: int = 3600


class BuildWithdrawRequest(BaseModel):
    address: str
    stake_id: str
    pool_id: str = "main"
    fee: int = 3600


def _resolve_chain_id(chain_id_arg: str | None) -> str:
    return get_chain_id(chain_id_arg)


@router.get("/pools", summary="List liquidity pools")
@rate_limit(rate=100, per=60)
async def list_pools(chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        pools = session.exec(select(LiquidityPool).where(LiquidityPool.chain_id == resolved)).all()
        return {
            "success": True,
            "chain_id": resolved,
            "pools": [
                {
                    "pool_id": p.pool_id,
                    "token": p.token,
                    "total_staked": p.total_staked,
                    "total_staked_ait": seconds_to_ait(p.total_staked),
                    "reward_per_share": str(p.reward_per_share),
                    "status": p.status,
                    "last_distribution_at": p.last_distribution_at.isoformat() if p.last_distribution_at else None,
                    "main_address": pool_main_address(),
                    "treasury_address": pool_treasury_address(),
                }
                for p in pools
            ],
        }


@router.get("/pools/{pool_id}", summary="Get a liquidity pool")
@rate_limit(rate=100, per=60)
async def get_pool(pool_id: str, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        pool = _get_or_create_pool(session, resolved, pool_id)
        return {
            "success": True,
            "chain_id": resolved,
            "pool_id": pool.pool_id,
            "token": pool.token,
            "total_staked": pool.total_staked,
            "total_staked_ait": seconds_to_ait(pool.total_staked),
            "reward_per_share": str(pool.reward_per_share),
            "status": pool.status,
            "main_address": pool_main_address(),
            "treasury_address": pool_treasury_address(),
        }


@router.get("/stakes/{address}", summary="List liquidity stakes for an address")
@rate_limit(rate=100, per=60)
async def list_stakes(address: str, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        stakes = session.exec(
            select(LiquidityStake).where(
                LiquidityStake.chain_id == resolved,
                LiquidityStake.address == address,
            )
        ).all()
        result = []
        for s in stakes:
            pool = _get_or_create_pool(session, resolved, s.pool_id)
            _realize_fixed_apy(session, resolved, pool, s)
            rewards = _pending_rewards(s, pool)
            locked_until = None
            if s.locked_until:
                locked_until = s.locked_until.isoformat()
            result.append(
                {
                    "stake_id": s.stake_id,
                    "pool_id": s.pool_id,
                    "address": s.address,
                    "amount": s.amount,
                    "amount_ait": seconds_to_ait(s.amount),
                    "lock_days": s.lock_days,
                    "locked_until": locked_until,
                    "reward_per_share_at_stake": str(s.reward_per_share_at_stake),
                    "rewards_claimed": s.rewards_claimed,
                    "rewards_pending": rewards,
                    "rewards_pending_ait": seconds_to_ait(rewards),
                    "status": s.status,
                    "created_at": s.created_at.isoformat(),
                }
            )
        return {
            "success": True,
            "chain_id": resolved,
            "address": address,
            "stakes": result,
        }


@router.get("/stakes/{stake_id}/rewards", summary="Get pending rewards for a stake")
@rate_limit(rate=100, per=60)
async def get_stake_rewards(stake_id: str, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        stake = session.get(LiquidityStake, (stake_id, resolved))
        if not stake:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        pool = _get_or_create_pool(session, resolved, stake.pool_id)
        _realize_fixed_apy(session, resolved, pool, stake)
        rewards = _pending_rewards(stake, pool)
        return {
            "success": True,
            "chain_id": resolved,
            "stake_id": stake_id,
            "address": stake.address,
            "rewards_pending": rewards,
            "rewards_pending_ait": seconds_to_ait(rewards),
        }


@router.post("/build-deposit", summary="Build an unsigned LIQUIDITY_DEPOSIT transaction")
@rate_limit(rate=50, per=60)
async def build_deposit(body: BuildDepositRequest, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        account = session.get(Account, (resolved, body.address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {body.address} not found")
        tx = {
            "type": "LIQUIDITY_DEPOSIT",
            "from": body.address,
            "to": pool_main_address(),
            "amount": body.amount,
            "value": body.amount,
            "fee": body.fee,
            "nonce": account.nonce,
            "chain_id": resolved,
            "payload": {
                "pool_id": body.pool_id,
                "lock_days": body.lock_days,
            },
        }
        return {"success": True, "chain_id": resolved, "transaction": tx}


@router.post("/build-claim", summary="Build an unsigned LIQUIDITY_CLAIM transaction")
@rate_limit(rate=50, per=60)
async def build_claim(body: BuildClaimRequest, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        stake = session.get(LiquidityStake, (body.stake_id, resolved))
        if not stake or stake.address != body.address:
            raise HTTPException(status_code=404, detail=f"Stake {body.stake_id} not found for address {body.address}")
        account = session.get(Account, (resolved, body.address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {body.address} not found")
        tx = {
            "type": "LIQUIDITY_CLAIM",
            "from": body.address,
            "to": body.address,
            "amount": 0,
            "value": 0,
            "fee": body.fee,
            "nonce": account.nonce,
            "chain_id": resolved,
            "payload": {
                "pool_id": body.pool_id,
                "stake_id": body.stake_id,
            },
        }
        return {"success": True, "chain_id": resolved, "transaction": tx}


@router.post("/build-withdraw", summary="Build an unsigned LIQUIDITY_WITHDRAW transaction")
@rate_limit(rate=50, per=60)
async def build_withdraw(body: BuildWithdrawRequest, chain_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_chain_id(chain_id)
    with session_scope(resolved) as session:
        stake = session.get(LiquidityStake, (body.stake_id, resolved))
        if not stake or stake.address != body.address:
            raise HTTPException(status_code=404, detail=f"Stake {body.stake_id} not found for address {body.address}")
        account = session.get(Account, (resolved, body.address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {body.address} not found")
        if stake.locked_until and stake.locked_until > datetime.now(UTC):
            raise HTTPException(status_code=400, detail=f"Stake still locked until {stake.locked_until.isoformat()}")
        tx = {
            "type": "LIQUIDITY_WITHDRAW",
            "from": body.address,
            "to": body.address,
            "amount": 0,
            "value": 0,
            "fee": body.fee,
            "nonce": account.nonce,
            "chain_id": resolved,
            "payload": {
                "pool_id": body.pool_id,
                "stake_id": body.stake_id,
            },
        }
        return {"success": True, "chain_id": resolved, "transaction": tx}
