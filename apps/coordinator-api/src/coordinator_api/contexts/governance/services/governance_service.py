"""
Governance Service - On-chain proposal and voting system

Provides:
- Proposal creation
- Voting with stake-weighted power
- Proposal execution
- Governance parameters
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    """Return a naive UTC timestamp (SQLite-friendly)."""
    return datetime.now(UTC).replace(tzinfo=None)


class GovernanceService:
    """
    On-chain governance system backed by SQLModel persistence.

    Implements:
    - Proposal lifecycle
    - Stake-weighted voting
    - Quorum and threshold checks
    - Proposal execution
    """

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # SQLModel-based async methods for the governance.py router
    # ------------------------------------------------------------------

    def get_or_create_profile(self, user_id: str, initial_voting_power: float = 0.0) -> Any:
        """Get or create a GovernanceProfile by user_id."""
        from ..domain.governance import GovernanceProfile, GovernanceRole
        from sqlmodel import select as sm_select

        stmt = sm_select(GovernanceProfile).where(GovernanceProfile.user_id == user_id)
        result = self._session_factory.execute(stmt).scalars().first()
        if result:
            return result
        profile = GovernanceProfile(
            user_id=user_id,
            role=GovernanceRole.MEMBER,
            voting_power=initial_voting_power,
        )
        self._session_factory.add(profile)
        self._session_factory.commit()
        self._session_factory.refresh(profile)
        return profile

    def delegate_votes(self, delegator_id: str, delegatee_id: str) -> Any:
        """Delegate voting power from delegator to delegatee."""
        from ..domain.governance import GovernanceProfile
        from sqlmodel import select as sm_select

        delegator = (
            self._session_factory.execute(sm_select(GovernanceProfile).where(GovernanceProfile.profile_id == delegator_id))
            .scalars()
            .first()
        )
        if not delegator:
            raise ValueError(f"Profile {delegator_id} not found")
        delegatee = (
            self._session_factory.execute(sm_select(GovernanceProfile).where(GovernanceProfile.profile_id == delegatee_id))
            .scalars()
            .first()
        )
        if not delegatee:
            raise ValueError(f"Profile {delegatee_id} not found")
        power = delegator.voting_power or 0.0
        previous_delegate_to = delegator.delegate_to
        if previous_delegate_to != delegatee_id:
            if previous_delegate_to:
                previous = (
                    self._session_factory.execute(
                        sm_select(GovernanceProfile).where(GovernanceProfile.profile_id == previous_delegate_to)
                    )
                    .scalars()
                    .first()
                )
                if previous:
                    previous.delegated_power = max(0.0, (previous.delegated_power or 0.0) - power)
            delegatee.delegated_power = (delegatee.delegated_power or 0.0) + power
            delegator.delegate_to = delegatee_id
        self._session_factory.commit()
        self._session_factory.refresh(delegator)
        return delegator

    def create_governance_proposal(self, proposer_id: str, proposal_data: dict[str, Any]) -> Any:
        """Create a SQLModel Proposal from a router request dict."""
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus
        from datetime import datetime as _dt

        now = datetime.now(UTC)
        voting_starts = _dt.fromisoformat(proposal_data["voting_starts"]) if proposal_data.get("voting_starts") else now
        voting_ends = (
            _dt.fromisoformat(proposal_data["voting_ends"]) if proposal_data.get("voting_ends") else now + timedelta(days=7)
        )
        proposal = DomainProposal(
            proposer_id=proposer_id,
            title=proposal_data.get("title", ""),
            description=proposal_data.get("description", ""),
            category=proposal_data.get("category", "general"),
            execution_payload=proposal_data.get("execution_payload", {}),
            status=ProposalStatus.ACTIVE,
            quorum_required=proposal_data.get("quorum_required", 1000.0),
            voting_starts=voting_starts,
            voting_ends=voting_ends,
        )
        self._session_factory.add(proposal)
        self._session_factory.commit()
        self._session_factory.refresh(proposal)
        return proposal

    def cast_governance_vote(self, proposal_id: str, voter_id: str, vote_type: Any, reason: str | None = None) -> Any:
        """Cast a vote using SQLModel domain models."""
        from ..domain.governance import (
            GovernanceProfile,
            Proposal as DomainProposal,
            Vote as DomainVote,
            effective_voting_power,
        )
        from sqlmodel import select as sm_select

        proposal = (
            self._session_factory.execute(sm_select(DomainProposal).where(DomainProposal.proposal_id == proposal_id))
            .scalars()
            .first()
        )
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        voter = (
            self._session_factory.execute(sm_select(GovernanceProfile).where(GovernanceProfile.profile_id == voter_id))
            .scalars()
            .first()
        )
        power = effective_voting_power(voter) if voter else 0.0
        existing = (
            self._session_factory.execute(
                sm_select(DomainVote).where(DomainVote.proposal_id == proposal_id, DomainVote.voter_id == voter_id)
            )
            .scalars()
            .first()
        )
        if existing:
            raise ValueError("voter has already voted on this proposal")  # #1071: one vote per voter
        vote = DomainVote(
            proposal_id=proposal_id,
            voter_id=voter_id,
            vote_type=vote_type,
            voting_power_used=power,
            reason=reason,
        )
        self._session_factory.add(vote)
        if str(vote_type) == "for":
            proposal.votes_for += power
        elif str(vote_type) == "against":
            proposal.votes_against += power
        else:
            proposal.votes_abstain += power
        if voter:
            voter.total_votes_cast += 1
            voter.last_voted_at = datetime.now(UTC)
        self._session_factory.commit()
        self._session_factory.refresh(vote)
        return vote

    def process_proposal_lifecycle(self, proposal_id: str) -> Any:
        """Check and update proposal status based on voting results."""
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus
        from sqlmodel import select as sm_select

        proposal = (
            self._session_factory.execute(sm_select(DomainProposal).where(DomainProposal.proposal_id == proposal_id))
            .scalars()
            .first()
        )
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.ACTIVE:
            return proposal
        voting_ends = proposal.voting_ends
        if voting_ends.tzinfo is not None:
            voting_ends = voting_ends.replace(tzinfo=None)
        if _utc_now() < voting_ends:
            return proposal
        total = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
        if total < proposal.quorum_required:
            proposal.status = ProposalStatus.DEFEATED
        elif proposal.votes_for > proposal.votes_against:
            proposal.status = ProposalStatus.SUCCEEDED
        else:
            proposal.status = ProposalStatus.DEFEATED
        self._session_factory.commit()
        self._session_factory.refresh(proposal)
        return proposal

    def execute_governance_proposal(self, proposal_id: str, executor_id: str) -> Any:
        """Execute a succeeded proposal."""
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus
        from sqlmodel import select as sm_select

        proposal = (
            self._session_factory.execute(sm_select(DomainProposal).where(DomainProposal.proposal_id == proposal_id))
            .scalars()
            .first()
        )
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.SUCCEEDED:
            raise ValueError(f"Cannot execute proposal with status: {proposal.status}")
        proposal.status = ProposalStatus.EXECUTED
        proposal.executed_at = datetime.now(UTC)
        self._session_factory.commit()
        self._session_factory.refresh(proposal)
        return proposal

    def generate_transparency_report(self, period: str) -> Any:
        """Generate a transparency report for a given period."""
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus, TransparencyReport, Vote as DomainVote
        from sqlmodel import select as sm_select

        proposals = self._session_factory.execute(sm_select(DomainProposal)).scalars().all()
        votes = self._session_factory.execute(sm_select(DomainVote)).scalars().all()
        passed = [p for p in proposals if p.status == ProposalStatus.SUCCEEDED or p.status == ProposalStatus.EXECUTED]
        report = TransparencyReport(
            period=period,
            total_proposals=len(proposals),
            passed_proposals=len(passed),
            active_voters=len({v.voter_id for v in votes}),
            total_voting_power_participated=sum(v.voting_power_used for v in votes),
            treasury_inflow=0.0,
            treasury_outflow=0.0,
        )
        self._session_factory.add(report)
        self._session_factory.commit()
        self._session_factory.refresh(report)
        return report

    # ------------------------------------------------------------------
    # Enhanced governance methods (in-memory, return dicts)
    # ------------------------------------------------------------------

    def create_regional_council(
        self,
        region: str,
        council_name: str,
        jurisdiction: str,
        council_members: list[str],
        budget_allocation: Decimal,
    ) -> dict[str, Any]:
        from ..domain.governance import RegionalCouncil

        council = RegionalCouncil(
            region=region,
            council_name=council_name,
            jurisdiction=jurisdiction,
            members=council_members,
            budget_allocation=Decimal(str(budget_allocation)),
        )
        self._session_factory.add(council)
        self._session_factory.commit()
        self._session_factory.refresh(council)
        return {
            "council_id": council.council_id,
            "region": council.region,
            "council_name": council.council_name,
            "jurisdiction": council.jurisdiction,
            "members": council.members,
            "budget_allocation": str(council.budget_allocation),
            "created_at": council.created_at.isoformat(),
        }

    def get_regional_councils(self, region: str | None = None) -> list[dict[str, Any]]:
        from ..domain.governance import RegionalCouncil
        from sqlmodel import select as sm_select

        stmt = sm_select(RegionalCouncil)
        if region:
            stmt = stmt.where(RegionalCouncil.region == region)
        rows = self._session_factory.execute(stmt).scalars().all()
        return [
            {
                "council_id": c.council_id,
                "region": c.region,
                "council_name": c.council_name,
                "jurisdiction": c.jurisdiction,
                "members": c.members,
                "budget_allocation": str(c.budget_allocation),
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]

    def create_regional_proposal(
        self,
        council_id: str,
        title: str,
        description: str,
        proposal_type: str,
        amount_requested: Decimal,
        proposer_address: str,
    ) -> dict[str, Any]:
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus, RegionalCouncil
        from sqlmodel import select as sm_select

        council = self._session_factory.execute(
            sm_select(RegionalCouncil).where(RegionalCouncil.council_id == council_id)
        ).scalar_one_or_none()
        if not council:
            raise ValueError(f"Council {council_id} not found")
        proposer = self.get_or_create_profile(proposer_address)
        proposal_id = f"rprop_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        proposal = DomainProposal(
            proposal_id=proposal_id,
            proposer_id=proposer.profile_id,
            council_id=council_id,
            title=title,
            description=description,
            category=proposal_type,
            execution_payload={"amount_requested": str(amount_requested)},
            status=ProposalStatus.ACTIVE,
            voting_starts=now,
            voting_ends=now + timedelta(days=7),
        )
        self._session_factory.add(proposal)
        self._session_factory.commit()
        self._session_factory.refresh(proposal)
        return {
            "proposal_id": proposal.proposal_id,
            "council_id": proposal.council_id,
            "title": proposal.title,
            "description": proposal.description,
            "proposal_type": proposal.category,
            "amount_requested": str(amount_requested),
            "proposer_address": proposer_address,
            "status": proposal.status.value,
            "created_at": proposal.created_at.isoformat(),
        }

    def vote_on_regional_proposal(self, proposal_id: str, voter_address: str, vote_type: Any) -> dict[str, Any]:
        """Cast a vote on a regional proposal.

        #1847: voting power is derived from the voter's stored profile
        (own + delegated) — never from the request — and one vote per
        voter per proposal is enforced, matching cast_governance_vote.
        """
        from ..domain.governance import (
            Proposal as DomainProposal,
            ProposalStatus,
            Vote as DomainVote,
            VoteType,
            effective_voting_power,
        )
        from sqlmodel import select as sm_select

        proposal = self._session_factory.execute(
            sm_select(DomainProposal).where(DomainProposal.proposal_id == proposal_id)
        ).scalar_one_or_none()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal is not active: {proposal.status.value}")
        voter = self.get_or_create_profile(voter_address)
        existing = self._session_factory.execute(
            sm_select(DomainVote).where(DomainVote.proposal_id == proposal_id, DomainVote.voter_id == voter.profile_id)
        ).scalar_one_or_none()
        if existing:
            raise ValueError("voter has already voted on this proposal")
        voting_power = effective_voting_power(voter)
        vote = DomainVote(
            proposal_id=proposal_id,
            voter_id=voter.profile_id,
            vote_type=vote_type,
            voting_power_used=voting_power,
        )
        self._session_factory.add(vote)
        if vote_type == VoteType.FOR:
            proposal.votes_for += voting_power
        elif vote_type == VoteType.AGAINST:
            proposal.votes_against += voting_power
        else:
            proposal.votes_abstain += voting_power
        self._session_factory.commit()
        self._session_factory.refresh(vote)
        return {
            "proposal_id": proposal_id,
            "voter_address": voter_address,
            "vote_type": str(vote_type),
            "voting_power": voting_power,
            "timestamp": vote.created_at.isoformat(),
        }

    # Treasury and staking read/write methods were removed in #2170: they
    # returned fabricated data (zero balances, empty lists, a hardcoded 5%
    # APY) with no on-chain backing. The corresponding router endpoints are
    # honest 501 stubs; re-add real implementations backed by chain state.

    def get_governance_analytics(self, time_period_days: int = 30) -> dict[str, Any]:
        from ..domain.governance import (
            GovernanceProfile,
            Proposal as DomainProposal,
            ProposalStatus,
            RegionalCouncil,
            Vote as DomainVote,
        )
        from sqlmodel import func, select as sm_select

        total = self._session_factory.execute(sm_select(func.count(DomainProposal.proposal_id))).scalar() or 0  # type: ignore[arg-type]
        active = (
            self._session_factory.execute(
                sm_select(func.count(DomainProposal.proposal_id)).where(DomainProposal.status == ProposalStatus.ACTIVE)  # type: ignore[arg-type]
            ).scalar()
            or 0
        )
        passed = (
            self._session_factory.execute(
                sm_select(func.count(DomainProposal.proposal_id)).where(DomainProposal.status == ProposalStatus.SUCCEEDED)  # type: ignore[arg-type]
            ).scalar()
            or 0
        )
        total_votes = self._session_factory.execute(sm_select(func.count(DomainVote.vote_id))).scalar() or 0  # type: ignore[arg-type]
        total_councils = self._session_factory.execute(sm_select(func.count(RegionalCouncil.council_id))).scalar() or 0  # type: ignore[arg-type]
        council_regions = self._session_factory.execute(sm_select(RegionalCouncil.region).distinct()).scalars().all()
        total_profiles = self._session_factory.execute(sm_select(func.count(GovernanceProfile.profile_id))).scalar() or 0  # type: ignore[arg-type]
        distinct_voters = (
            self._session_factory.execute(sm_select(func.count(func.distinct(DomainVote.voter_id)))).scalar() or 0
        )
        participation_rate = round(distinct_voters / total_profiles * 100, 2) if total_profiles else 0.0
        return {
            "time_period_days": time_period_days,
            "proposals": {
                "total": total,
                "still_active": active,
                "passed": passed,
                "total_votes": total_votes,
                "participation_rate": participation_rate,
            },
            "regional_councils": {"total_councils": total_councils, "regions": len(council_regions)},
            # No on-chain treasury exists — these are placeholders, not a
            # live balance. Marked so consumers do not read them as real.
            "treasury": {
                "total_allocations": 0.0,
                "total_balance": 0.0,
                "simulated": True,
            },  # not-money: ratio, threshold or configuration default — not an amount of money
            # No on-chain staking pools exist — same placeholder treatment.
            "staking": {"active_pools": 0, "total_staked": 0.0, "simulated": True},
        }
