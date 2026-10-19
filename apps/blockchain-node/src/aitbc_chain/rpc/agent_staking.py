"""Agent-economy staking RPC (V23-42). Distinct from consensus /rpc/staking/stake."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from aitbc.rate_limiting import rate_limit

from .retired import raise_for_retired
from ..base_models import AgentStakeMemo
from ..database import session_scope
from ..logger import get_logger
from .agent_economics_auth import require_operator_signature
from .utils import get_chain_id

_logger = get_logger(__name__)


@rate_limit(rate=20, per=60)
async def create_agent_stake(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Agent staking (stake)")


@rate_limit(rate=20, per=60)
async def add_to_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Agent staking (top-up)")


@rate_limit(rate=20, per=60)
async def unbond_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Agent staking (unbond)")


@rate_limit(rate=20, per=60)
async def complete_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Agent staking (complete)")


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
