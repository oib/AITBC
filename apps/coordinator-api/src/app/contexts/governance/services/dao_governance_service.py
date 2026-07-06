"""
DAO Governance Service

Service for managing multi-jurisdictional DAOs, regional councils, and global treasuries.
Submits governance votes and treasury allocations to the blockchain node RPC.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL as _DEFAULT_RPC_URL

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..domain.dao_governance import DAOMember, DAOProposal, ProposalState, ProposalType, TreasuryAllocation, Vote
from ..schemas.dao_governance import AllocationCreate, MemberCreate, ProposalCreate, VoteCreate

logger = get_logger(__name__)

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", _DEFAULT_RPC_URL)


async def _submit_governance_vote_to_chain(
    proposal_id: str,
    voter_address: str,
    vote_type: str,
    voting_power: float,
    reason: str | None = None,
) -> str:
    """Submit a governance vote to the blockchain node RPC.

    Returns the on-chain vote ID as the tx_hash.
    Raises HTTPException if the blockchain node rejects the vote.
    """
    import httpx

    payload: dict[str, Any] = {
        "proposal_id": proposal_id,
        "voter_address": voter_address,
        "vote_type": vote_type,
        "voting_power": int(voting_power),
    }
    if reason:
        payload["reason"] = reason

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{BLOCKCHAIN_RPC_URL}/governance/vote", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("vote_id", ""))
            else:
                detail = (
                    resp.json().get("detail", resp.text)
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else resp.text
                )
                raise HTTPException(status_code=resp.status_code, detail=f"Blockchain rejected vote: {detail}")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain node unavailable: {e}") from e


async def _submit_treasury_allocation_to_chain(
    proposal_id: str,
    amount: float,
    recipient_address: str,
    token_symbol: str,
    purpose: str,
) -> str:
    """Submit a treasury allocation to the blockchain node RPC as a transfer transaction.

    Returns the on-chain tx hash.
    Raises HTTPException if the blockchain node rejects the transaction.
    """
    import httpx

    payload = {
        "from": "treasury",
        "to": recipient_address,
        "amount": int(amount * 3600),  # convert AIT to compute-seconds
        "type": "GOVERNANCE_TRANSFER",
        "metadata": {
            "proposal_id": proposal_id,
            "purpose": purpose,
            "token_symbol": token_symbol,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{BLOCKCHAIN_RPC_URL}/rpc/sendTransaction", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("tx_hash", ""))
            else:
                detail = (
                    resp.json().get("detail", resp.text)
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else resp.text
                )
                raise HTTPException(status_code=resp.status_code, detail=f"Blockchain rejected treasury allocation: {detail}")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain node unavailable: {e}") from e


class DAOGovernanceService:
    def __init__(self, session: Session):
        self.session = session

    async def register_member(self, request: MemberCreate) -> DAOMember:
        existing = self.session.execute(select(DAOMember).where(DAOMember.wallet_address == request.wallet_address)).first()
        if existing:
            existing.staked_amount += request.staked_amount
            existing.voting_power = existing.staked_amount
            self.session.commit()
            self.session.refresh(existing)
            return existing  # type: ignore[return-value]
        member = DAOMember(
            wallet_address=request.wallet_address, staked_amount=request.staked_amount, voting_power=request.staked_amount
        )
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    async def create_proposal(self, request: ProposalCreate) -> DAOProposal:
        proposer = self.session.execute(select(DAOMember).where(DAOMember.wallet_address == request.proposer_address)).first()
        if not proposer:
            raise HTTPException(status_code=404, detail="Proposer not found")
        if request.target_region and (not (proposer.is_council_member and proposer.council_region == request.target_region)):
            raise HTTPException(status_code=403, detail="Only regional council members can create regional proposals")
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(days=request.voting_period_days)
        proposal = DAOProposal(
            proposer_address=request.proposer_address,
            title=request.title,
            description=request.description,
            proposal_type=request.proposal_type,
            target_region=request.target_region,
            execution_payload=request.execution_payload,
            start_time=start_time,
            end_time=end_time,
            status=ProposalState.ACTIVE,
        )
        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        logger.info("Created proposal %s by %s", proposal.id, request.proposer_address)
        return proposal

    async def cast_vote(self, request: VoteCreate) -> Vote:
        member = self.session.execute(select(DAOMember).where(DAOMember.wallet_address == request.member_address)).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")
        proposal = self.session.get(DAOProposal, request.proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")
        if proposal.status != ProposalState.ACTIVE:
            raise HTTPException(status_code=400, detail="Proposal is not active")
        now = datetime.now(UTC)
        if now < proposal.start_time or now > proposal.end_time:
            proposal.status = ProposalState.EXPIRED
            self.session.commit()
            raise HTTPException(status_code=400, detail="Voting period has ended")
        existing_vote = self.session.execute(
            select(Vote).where(Vote.proposal_id == request.proposal_id, Vote.member_id == member.id)
        ).first()
        if existing_vote:
            raise HTTPException(status_code=400, detail="Member has already voted on this proposal")
        weight = member.voting_power
        if proposal.target_region:
            if not member.is_council_member or member.council_region != proposal.target_region:
                raise HTTPException(status_code=403, detail="Not a member of the target regional council")
            weight = 1.0
        vote = Vote(proposal_id=proposal.id, member_id=member.id, support=request.support, weight=weight, tx_hash="")
        # Submit the vote to the blockchain and store the real tx hash
        vote_type = "for" if request.support else "against"
        tx_hash = await _submit_governance_vote_to_chain(
            proposal_id=str(proposal.id),
            voter_address=member.wallet_address,
            vote_type=vote_type,
            voting_power=weight,
        )
        vote.tx_hash = tx_hash
        if request.support:
            proposal.for_votes += weight
        else:
            proposal.against_votes += weight
        self.session.add(vote)
        self.session.commit()
        self.session.refresh(vote)
        logger.info("Vote cast on %s by %s", proposal.id, member.wallet_address)
        return vote

    async def execute_proposal(self, proposal_id: str) -> DAOProposal:
        proposal = self.session.get(DAOProposal, proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")
        if proposal.status != ProposalState.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Cannot execute proposal in state {proposal.status}")
        if datetime.now(UTC) <= proposal.end_time:
            raise HTTPException(status_code=400, detail="Voting period has not ended yet")
        if proposal.for_votes > proposal.against_votes:
            proposal.status = ProposalState.EXECUTED
            logger.info("Proposal %s SUCCEEDED and EXECUTED.", proposal_id)
            if proposal.proposal_type == ProposalType.GRANT:
                amount = float(proposal.execution_payload.get("amount", 0))
                recipient = proposal.execution_payload.get("recipient_address")
                if amount > 0 and recipient:
                    await self.allocate_treasury(
                        AllocationCreate(
                            proposal_id=proposal.id,
                            amount=amount,
                            recipient_address=recipient,
                            purpose=f"Grant for proposal {proposal.title}",
                        )
                    )
        else:
            proposal.status = ProposalState.DEFEATED
            logger.info("Proposal %s DEFEATED.", proposal_id)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    async def allocate_treasury(self, request: AllocationCreate) -> TreasuryAllocation:
        """Allocate funds from the global treasury"""
        # Submit the allocation to the blockchain and store the real tx hash
        tx_hash = await _submit_treasury_allocation_to_chain(
            proposal_id=str(request.proposal_id),
            amount=request.amount,
            recipient_address=request.recipient_address,
            token_symbol=request.token_symbol,
            purpose=request.purpose,
        )
        allocation = TreasuryAllocation(
            proposal_id=request.proposal_id,
            amount=request.amount,
            token_symbol=request.token_symbol,
            recipient_address=request.recipient_address,
            purpose=request.purpose,
            tx_hash=tx_hash,
        )
        self.session.add(allocation)
        self.session.commit()
        self.session.refresh(allocation)
        logger.info("Allocated %s %s to %s", request.amount, request.token_symbol, request.recipient_address)
        return allocation
