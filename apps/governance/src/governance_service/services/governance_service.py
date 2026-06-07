"""
Governance service for managing governance operations
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.governance import (
    DaoTreasury,
    Delegation,
    GovernanceProfile,
    GovernanceToken,
    Proposal,
    ProposalExecutionLog,
    TokenStake,
    Vote,
)


class GovernanceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_profiles(
        self,
        role: str | None = None,
        user_id: str | None = None,
    ) -> list[GovernanceProfile]:
        """List governance profiles"""
        stmt = select(GovernanceProfile)
        if role:
            stmt = stmt.where(GovernanceProfile.role == role)
        if user_id:
            stmt = stmt.where(GovernanceProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_profile(self, profile_id: str) -> GovernanceProfile | None:
        """Get a specific governance profile"""
        stmt = select(GovernanceProfile).where(GovernanceProfile.profile_id == profile_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_profile(self, profile_data: dict) -> GovernanceProfile:
        """Create a new governance profile"""
        profile = GovernanceProfile(**profile_data)
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def list_proposals(
        self,
        status: str | None = None,
        category: str | None = None,
        proposer_id: str | None = None,
    ) -> list[Proposal]:
        """List governance proposals"""
        stmt = select(Proposal)
        if status:
            stmt = stmt.where(Proposal.status == status)
        if category:
            stmt = stmt.where(Proposal.category == category)
        if proposer_id:
            stmt = stmt.where(Proposal.proposer_id == proposer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Get a specific proposal"""
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_proposal(self, proposal_data: dict) -> Proposal:
        """Create a new proposal"""
        proposal = Proposal(**proposal_data)
        self.session.add(proposal)
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def list_votes(
        self,
        proposal_id: str | None = None,
        voter_id: str | None = None,
    ) -> list[Vote]:
        """List votes"""
        stmt = select(Vote)
        if proposal_id:
            stmt = stmt.where(Vote.proposal_id == proposal_id)
        if voter_id:
            stmt = stmt.where(Vote.voter_id == voter_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_vote(self, vote_data: dict) -> Vote:
        """Create a new vote"""
        vote = Vote(**vote_data)
        self.session.add(vote)
        await self.session.commit()
        await self.session.refresh(vote)
        return vote

    async def get_treasury(self) -> DaoTreasury | None:
        """Get DAO treasury"""
        stmt = select(DaoTreasury).where(DaoTreasury.treasury_id == "main_treasury")
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_analytics(self, period: str = "monthly") -> dict[str, Any]:
        """Get governance analytics"""
        return {
            "period": period,
            "total_proposals": 0,
            "active_proposals": 0,
            "passed_proposals": 0,
            "total_votes": 0,
        }

    async def update_proposal_status(self, proposal_id: str, status: str) -> Proposal | None:
        """Update proposal status"""
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalars().first()
        
        if proposal:
            proposal.status = status
            await self.session.commit()
            await self.session.refresh(proposal)
        
        return proposal

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    # Token Staking Methods
    async def stake_tokens(self, staker_address: str, amount: int, lock_period_days: int) -> TokenStake:
        """Stake tokens for enhanced voting power"""
        stake = TokenStake(
            staker_address=staker_address,
            amount_staked=amount,
            lock_period_days=lock_period_days,
            unstakes_at=datetime.now(UTC) + timedelta(days=lock_period_days),
            is_active=True
        )
        self.session.add(stake)
        
        # Update governance token record
        token_record = await self._get_or_create_token_record(staker_address)
        token_record.staked_tokens += amount
        token_record.voting_power = await self.calculate_voting_power(staker_address)
        
        await self.session.commit()
        return stake

    async def calculate_voting_power(self, address: str) -> int:
        """Calculate total voting power for address"""
        token_record = await self._get_token_record(address)
        if not token_record:
            return 0
        
        # Formula: balance + (staked * 2)
        base_power = token_record.token_balance
        staking_bonus = token_record.staked_tokens * 2
        return int(base_power + staking_bonus)

    async def _get_or_create_token_record(self, address: str) -> GovernanceToken:
        """Get or create governance token record for address"""
        token_record = await self._get_token_record(address)
        if not token_record:
            token_record = GovernanceToken(
                holder_address=address,
                token_balance=0.0,
                staked_tokens=0.0,
                voting_power=0.0
            )
            self.session.add(token_record)
            await self.session.commit()
            await self.session.refresh(token_record)
        return token_record

    async def _get_token_record(self, address: str) -> GovernanceToken | None:
        """Get governance token record for address"""
        stmt = select(GovernanceToken).where(GovernanceToken.holder_address == address)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # Delegation Methods
    async def delegate_voting_power(self, delegator_address: str, delegate_address: str, amount: int) -> Delegation:
        """Delegate voting power to another address"""
        # Verify delegator has enough power
        delegator_power = await self.calculate_voting_power(delegator_address)
        if delegator_power < amount:
            raise ValueError(f"Insufficient voting power: {delegator_power} < {amount}")
        
        delegation = Delegation(
            delegator_address=delegator_address,
            delegate_address=delegate_address,
            voting_power=amount,
            is_active=True
        )
        self.session.add(delegation)
        await self.session.commit()
        return delegation

    # Proposal Execution Methods
    async def execute_proposal(self, proposal_id: str) -> Proposal | None:
        """Execute a passed proposal and log the steps"""
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            return None
        
        if proposal.status != "succeeded":
            raise ValueError(f"Proposal not in succeeded state: {proposal.status}")
        
        # Log execution start
        execution_log = ProposalExecutionLog(
            proposal_id=proposal_id,
            execution_step="start",
            status="pending",
            result={}
        )
        self.session.add(execution_log)
        
        try:
            # Update proposal status
            proposal.status = "executed"
            proposal.executed_at = datetime.now(UTC)
            
            # Log execution success
            execution_log.status = "completed"
            execution_log.result = {"executed_at": proposal.executed_at.isoformat()}
            
            await self.session.commit()
            await self.session.refresh(proposal)
            return proposal
        except Exception as e:
            # Log execution failure
            execution_log.status = "failed"
            execution_log.error_message = str(e)
            await self.session.commit()
            raise
