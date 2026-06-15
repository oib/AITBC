"""
Atomic Swap Service

Service for managing trustless cross-chain atomic swaps between agents.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc import get_logger

from ..blockchain.contract_interactions import ContractInteractionService  # type: ignore[import-not-found]
from ..domain.atomic_swap import AtomicSwapOrder, SwapStatus
from ..schemas.atomic_swap import SwapActionRequest, SwapCompleteRequest, SwapCreateRequest

logger = get_logger(__name__)


class AtomicSwapService:
    def __init__(self, session: Session, contract_service: ContractInteractionService):
        self.session = session
        self.contract_service = contract_service

    async def create_swap_order(self, request: SwapCreateRequest) -> AtomicSwapOrder:
        """Create a new atomic swap order between two agents"""
        if request.source_timelock_hours <= request.target_timelock_hours:
            raise HTTPException(
                status_code=400,
                detail="Source timelock must be strictly greater than target timelock to ensure safety for initiator.",
            )
        secret = request.secret
        if not secret:
            secret = secrets.token_hex(32)
        hashlock = "0x" + hashlib.sha256(secret.encode()).hexdigest()
        now = datetime.now(UTC)
        source_timelock = int((now + timedelta(hours=request.source_timelock_hours)).timestamp())
        target_timelock = int((now + timedelta(hours=request.target_timelock_hours)).timestamp())
        order = AtomicSwapOrder(
            initiator_agent_id=request.initiator_agent_id,
            initiator_address=request.initiator_address,
            source_chain_id=request.source_chain_id,
            source_token=request.source_token,
            source_amount=request.source_amount,
            participant_agent_id=request.participant_agent_id,
            participant_address=request.participant_address,
            target_chain_id=request.target_chain_id,
            target_token=request.target_token,
            target_amount=request.target_amount,
            hashlock=hashlock,
            secret=secret,
            source_timelock=source_timelock,
            target_timelock=target_timelock,
            status=SwapStatus.CREATED,
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        logger.info("Created atomic swap order %s with hashlock %s", order.id, order.hashlock)
        return order

    async def get_swap_order(self, swap_id: str) -> AtomicSwapOrder | None:
        return self.session.get(AtomicSwapOrder, swap_id)

    async def get_agent_swaps(self, agent_id: str) -> list[AtomicSwapOrder]:
        """Get all swaps where the agent is either initiator or participant"""
        return list(
            self.session.scalars(
                select(AtomicSwapOrder).where(
                    (AtomicSwapOrder.initiator_agent_id == agent_id) | (AtomicSwapOrder.participant_agent_id == agent_id)
                )
            ).all()
        )

    async def mark_initiated(self, swap_id: str, request: SwapActionRequest) -> AtomicSwapOrder:
        """Mark that the initiator has locked funds on the source chain"""
        order = self.session.get(AtomicSwapOrder, swap_id)
        if not order:
            raise HTTPException(status_code=404, detail="Swap order not found")
        if order.status != SwapStatus.CREATED:
            raise HTTPException(status_code=400, detail="Swap is not in CREATED state")
        order.status = SwapStatus.INITIATED
        order.source_initiate_tx = request.tx_hash
        order.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(order)
        logger.info("Swap %s marked as INITIATED. Tx: %s", swap_id, request.tx_hash)
        return order

    async def mark_participating(self, swap_id: str, request: SwapActionRequest) -> AtomicSwapOrder:
        """Mark that the participant has locked funds on the target chain"""
        order = self.session.get(AtomicSwapOrder, swap_id)
        if not order:
            raise HTTPException(status_code=404, detail="Swap order not found")
        if order.status != SwapStatus.INITIATED:
            raise HTTPException(status_code=400, detail="Swap is not in INITIATED state")
        order.status = SwapStatus.PARTICIPATING
        order.target_participate_tx = request.tx_hash
        order.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(order)
        logger.info("Swap %s marked as PARTICIPATING. Tx: %s", swap_id, request.tx_hash)
        return order

    async def complete_swap(self, swap_id: str, request: SwapCompleteRequest) -> AtomicSwapOrder:
        """Initiator reveals secret to claim funds on target chain, Participant can then use secret on source chain"""
        order = self.session.get(AtomicSwapOrder, swap_id)
        if not order:
            raise HTTPException(status_code=404, detail="Swap order not found")
        if order.status != SwapStatus.PARTICIPATING:
            raise HTTPException(status_code=400, detail="Swap is not in PARTICIPATING state")
        test_hashlock = "0x" + hashlib.sha256(request.secret.encode()).hexdigest()
        if test_hashlock != order.hashlock:
            raise HTTPException(status_code=400, detail="Provided secret does not match hashlock")
        order.status = SwapStatus.COMPLETED
        order.target_complete_tx = request.tx_hash
        order.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(order)
        logger.info("Swap %s marked as COMPLETED. Secret revealed.", swap_id)
        return order

    async def refund_swap(self, swap_id: str, request: SwapActionRequest) -> AtomicSwapOrder:
        """Refund a swap whose timelock has expired"""
        order = self.session.get(AtomicSwapOrder, swap_id)
        if not order:
            raise HTTPException(status_code=404, detail="Swap order not found")
        now = int(datetime.now(UTC).timestamp())
        if order.status == SwapStatus.INITIATED and now < order.source_timelock:
            raise HTTPException(status_code=400, detail="Source timelock has not expired yet")
        if order.status == SwapStatus.PARTICIPATING and now < order.target_timelock:
            raise HTTPException(status_code=400, detail="Target timelock has not expired yet")
        order.status = SwapStatus.REFUNDED
        order.refund_tx = request.tx_hash
        order.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(order)
        logger.info("Swap %s marked as REFUNDED.", swap_id)
        return order
