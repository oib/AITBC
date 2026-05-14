"""
Governance service for managing governance operations
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.governance import GovernanceProfile, Proposal, Vote, DaoTreasury


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
