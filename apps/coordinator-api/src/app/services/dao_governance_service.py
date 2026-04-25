"""
DAO Governance Service

Service for managing multi-jurisdictional DAOs, regional councils, and global treasuries.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aitbc import get_logger
from fastapi import HTTPException
from sqlmodel import Session, select

from ..blockchain.contract_interactions import ContractInteractionService
from ..domain.dao_governance import DAOMember, DAOProposal, ProposalState, ProposalType, TreasuryAllocation, Vote
from ..schemas.dao_governance import AllocationCreate, MemberCreate, ProposalCreate, VoteCreate

logger = logging.getLogger(__name__)


class DAOGovernanceService:
    def __init__(self, session: Session, contract_service: ContractInteractionService):
        self.session = session
        self.contract_service = contract_service

    async def register_member(self, request: MemberCreate) -> DAOMember:
        existing = self.session.execute(select(DAOMember).where(DAOMember.wallet_address == request.wallet_address)).first()

        if existing:
            # Update stake
            existing.staked_amount += request.staked_amount
            existing.voting_power = existing.staked_amount  # 1:1 mapping for simplicity
            self.session.commit()
            self.session.refresh(existing)
            return existing

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

        if request.target_region and not (proposer.is_council_member and proposer.council_region == request.target_region):
            raise HTTPException(status_code=403, detail="Only regional council members can create regional proposals")

        start_time = datetime.utcnow()
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

        logger.info(f"Created proposal {proposal.id} by {request.proposer_address}")
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

        now = datetime.utcnow()
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
            # Regional proposals use 1-member-1-vote council weighting
            if not member.is_council_member or member.council_region != proposal.target_region:
                raise HTTPException(status_code=403, detail="Not a member of the target regional council")
            weight = 1.0

        vote = Vote(
            proposal_id=proposal.id, member_id=member.id, support=request.support, weight=weight, tx_hash="0x_mock_vote_tx"
        )

        if request.support:
            proposal.for_votes += weight
        else:
            proposal.against_votes += weight

        self.session.add(vote)
        self.session.commit()
        self.session.refresh(vote)

        logger.info(f"Vote cast on {proposal.id} by {member.wallet_address}")
        return vote

    async def execute_proposal(self, proposal_id: str) -> DAOProposal:
        proposal = self.session.get(DAOProposal, proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        if proposal.status != ProposalState.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Cannot execute proposal in state {proposal.status}")

        if datetime.utcnow() <= proposal.end_time:
            raise HTTPException(status_code=400, detail="Voting period has not ended yet")

        if proposal.for_votes > proposal.against_votes:
            proposal.status = ProposalState.EXECUTED
            logger.info(f"Proposal {proposal_id} SUCCEEDED and EXECUTED.")

            # Handle specific proposal types
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
            logger.info(f"Proposal {proposal_id} DEFEATED.")

        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    async def allocate_treasury(self, request: AllocationCreate) -> TreasuryAllocation:
        """Allocate funds from the global treasury"""
        allocation = TreasuryAllocation(
            proposal_id=request.proposal_id,
            amount=request.amount,
            token_symbol=request.token_symbol,
            recipient_address=request.recipient_address,
            purpose=request.purpose,
            tx_hash="0x_mock_treasury_tx",
        )

        self.session.add(allocation)
        self.session.commit()
        self.session.refresh(allocation)

        logger.info(f"Allocated {request.amount} {request.token_symbol} to {request.recipient_address}")
        return allocation
