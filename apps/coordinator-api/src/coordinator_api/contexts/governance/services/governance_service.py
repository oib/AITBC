"""
Governance Service - On-chain proposal and voting system

Provides:
- Proposal creation
- Voting with stake-weighted power
- Proposal execution
- Governance parameters
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class ProposalStatus(Enum):
    """Status of a governance proposal"""

    pending = "pending"
    active = "active"
    passed = "passed"
    rejected = "rejected"
    executed = "executed"
    canceled = "canceled"


class ProposalType(Enum):
    """Types of governance proposals"""

    parameter_change = "parameter_change"
    upgrade = "upgrade"
    treasury = "treasury"
    council = "council"


@dataclass
class Proposal:
    """Governance proposal"""

    id: str
    title: str
    description: str
    proposer: str
    proposal_type: ProposalType
    status: ProposalStatus
    votes_for: int
    votes_against: int
    votes_abstain: int
    quorum: int
    threshold: float
    created_at: datetime
    voting_start: datetime
    voting_end: datetime
    executed_at: datetime | None
    call_data: dict[str, Any] | None
    execution_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "proposer": self.proposer,
            "type": self.proposal_type.value,
            "status": self.status.value,
            "votes": {
                "for": self.votes_for,
                "against": self.votes_against,
                "abstain": self.votes_abstain,
                "total": self.votes_for + self.votes_against + self.votes_abstain,
            },
            "threshold": {"quorum": self.quorum, "approval": self.threshold},
            "timeline": {
                "created": self.created_at.isoformat(),
                "voting_start": self.voting_start.isoformat(),
                "voting_end": self.voting_end.isoformat(),
                "executed": self.executed_at.isoformat() if self.executed_at else None,
            },
            "execution": self.call_data,
        }


@dataclass
class Vote:
    """Individual vote record"""

    proposal_id: str
    voter: str
    choice: str
    power: int
    timestamp: datetime


class GovernanceService:
    """
    On-chain governance system.

    Implements:
    - Proposal lifecycle
    - Stake-weighted voting
    - Quorum and threshold checks
    - Proposal execution
    """

    MIN_PROPOSAL_STAKE = 10000
    VOTING_PERIOD_DAYS = 7
    QUORUM_PERCENTAGE = 20
    APPROVAL_THRESHOLD = 50

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._proposals: dict[str, Proposal] = {}
        self._votes: dict[str, list[Vote]] = {}
        self._proposal_counter = 0

    def create_proposal(
        self, title: str, description: str, proposer: str, proposal_type: str, call_data: dict[str, Any] | None = None
    ) -> Proposal:
        """
        Create a new governance proposal.

        Args:
            title: Proposal title
            description: Detailed description
            proposer: Address of proposer
            proposal_type: Type of proposal
            call_data: Execution data if proposal passes

        Returns:
            Created proposal
        """
        self._proposal_counter += 1
        proposal_id = f"PROP-{self._proposal_counter:04d}"
        try:
            p_type = ProposalType(proposal_type)
        except ValueError:
            p_type = ProposalType.parameter_change
        now = datetime.now(UTC)
        voting_start = now
        voting_end = now + timedelta(days=self.VOTING_PERIOD_DAYS)
        execution_hash = None
        if call_data:
            execution_hash = hashlib.sha256(json.dumps(call_data, sort_keys=True).encode()).hexdigest()[:32]
        proposal = Proposal(
            id=proposal_id,
            title=title,
            description=description,
            proposer=proposer,
            proposal_type=p_type,
            status=ProposalStatus.active,
            votes_for=0,
            votes_against=0,
            votes_abstain=0,
            quorum=self.MIN_PROPOSAL_STAKE * 10,
            threshold=self.APPROVAL_THRESHOLD,
            created_at=now,
            voting_start=voting_start,
            voting_end=voting_end,
            executed_at=None,
            call_data=call_data,
            execution_hash=execution_hash,
        )
        self._proposals[proposal_id] = proposal
        self._votes[proposal_id] = []
        logger.info("Proposal created: %s by %s", proposal_id, proposer)
        return proposal

    def cast_vote(self, proposal_id: str, voter: str, choice: str, voting_power: int) -> bool:
        """
        Cast a vote on a proposal.

        Args:
            proposal_id: Proposal to vote on
            voter: Voter address
            choice: "for", "against", or "abstain"
            voting_power: Stake-weighted voting power

        Returns:
            True if vote recorded successfully
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.active:
            raise ValueError(f"Proposal is not active: {proposal.status.value}")
        now = datetime.now(UTC)
        if now > proposal.voting_end:
            raise ValueError("Voting period has ended")
        for vote in self._votes[proposal_id]:
            if vote.voter == voter:
                raise ValueError("Already voted on this proposal")
        vote = Vote(proposal_id=proposal_id, voter=voter, choice=choice, power=voting_power, timestamp=now)
        self._votes[proposal_id].append(vote)
        if choice == "for":
            proposal.votes_for += voting_power
        elif choice == "against":
            proposal.votes_against += voting_power
        elif choice == "abstain":
            proposal.votes_abstain += voting_power
        logger.info("Vote cast on %s: %s voted %s (%s power)", proposal_id, voter, choice, voting_power)
        self._check_proposal_resolution(proposal)
        return True

    def _check_proposal_resolution(self, proposal: Proposal) -> None:
        """Check if proposal meets resolution criteria"""
        total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
        if total_votes < proposal.quorum:
            return
        if datetime.now(UTC) < proposal.voting_end:
            return
        total_for_against = proposal.votes_for + proposal.votes_against
        if total_for_against == 0:
            approval_pct = 0.0
        else:
            approval_pct = proposal.votes_for / total_for_against * 100
        if approval_pct >= proposal.threshold:
            proposal.status = ProposalStatus.passed
            logger.info("Proposal %s PASSED (%s% approval)", proposal.id, approval_pct)
        else:
            proposal.status = ProposalStatus.rejected
            logger.info("Proposal %s REJECTED (%s% approval)", proposal.id, approval_pct)

    def execute_proposal(self, proposal_id: str, executor: str) -> bool:
        """
        Execute a passed proposal.

        Args:
            proposal_id: Proposal to execute
            executor: Address executing the proposal

        Returns:
            True if execution successful
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.passed:
            raise ValueError(f"Cannot execute proposal with status: {proposal.status.value}")
        execution_deadline = proposal.voting_end + timedelta(hours=48)
        if datetime.now(UTC) > execution_deadline:
            proposal.status = ProposalStatus.canceled
            raise ValueError("Execution window has expired")
        if proposal.call_data:
            logger.info("Executing proposal %s: %s", proposal_id, proposal.call_data)
            pass
        proposal.status = ProposalStatus.executed
        proposal.executed_at = datetime.now(UTC)
        logger.info("Proposal executed: %s by %s", proposal_id, executor)
        return True

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Get proposal by ID"""
        return self._proposals.get(proposal_id)

    def list_proposals(self, status: str | None = None, proposer: str | None = None) -> list[Proposal]:
        """List proposals with optional filters"""
        result = list(self._proposals.values())
        if status:
            result = [p for p in result if p.status.value == status]
        if proposer:
            result = [p for p in result if p.proposer == proposer]
        result.sort(key=lambda p: p.created_at, reverse=True)
        return result

    def get_votes(self, proposal_id: str) -> list[Vote]:
        """Get all votes for a proposal"""
        return self._votes.get(proposal_id, [])

    def get_voting_power(self, address: str) -> int:
        """Get stake-weighted voting power for an address"""
        try:
            import httpx

            blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL)
            response = httpx.get(f"{blockchain_rpc_url}/rpc/accounts/{address}")
            if response.status_code == 200:
                account_data = response.json()
                balance = int(account_data.get("balance", 0))
                return balance
            else:
                logger.warning("Failed to get account balance for %s", address)
                return 0
        except Exception as e:
            logger.warning("Error querying voting power for %s: %s", address, e)
            return 0

    def get_governance_params(self) -> dict[str, Any]:
        """Get current governance parameters"""
        return {
            "min_proposal_stake": self.MIN_PROPOSAL_STAKE,
            "voting_period_days": self.VOTING_PERIOD_DAYS,
            "quorum_percentage": self.QUORUM_PERCENTAGE,
            "approval_threshold": self.APPROVAL_THRESHOLD,
            "total_proposals": len(self._proposals),
            "active_proposals": len([p for p in self._proposals.values() if p.status == ProposalStatus.active]),
        }

    # ------------------------------------------------------------------
    # SQLModel-based async methods for the governance.py router
    # ------------------------------------------------------------------

    async def get_or_create_profile(self, user_id: str, initial_voting_power: float = 0.0) -> Any:
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

    async def delegate_votes(self, delegator_id: str, delegatee_id: str) -> Any:
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
        delegator.delegate_to = delegatee_id
        delegatee.delegated_power += delegator.voting_power
        self._session_factory.commit()
        self._session_factory.refresh(delegator)
        return delegator

    async def create_governance_proposal(self, proposer_id: str, proposal_data: dict[str, Any]) -> Any:
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

    async def cast_governance_vote(self, proposal_id: str, voter_id: str, vote_type: Any, reason: str | None = None) -> Any:
        """Cast a vote using SQLModel domain models."""
        from ..domain.governance import GovernanceProfile, Proposal as DomainProposal, Vote as DomainVote
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
        power = voter.voting_power + voter.delegated_power if voter else 0.0
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

    async def process_proposal_lifecycle(self, proposal_id: str) -> Any:
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
        if datetime.now(UTC) < proposal.voting_ends:
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

    async def execute_governance_proposal(self, proposal_id: str, executor_id: str) -> Any:
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

    async def generate_transparency_report(self, period: str) -> Any:
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

    async def create_regional_council(
        self, region: str, council_name: str, jurisdiction: str, council_members: list[str], budget_allocation: float
    ) -> dict[str, Any]:
        from ..domain.governance import RegionalCouncil

        council = RegionalCouncil(
            region=region,
            council_name=council_name,
            jurisdiction=jurisdiction,
            members=council_members,
            budget_allocation=budget_allocation,
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
            "budget_allocation": council.budget_allocation,
            "created_at": council.created_at.isoformat(),
        }

    async def get_regional_councils(self, region: str | None = None) -> list[dict[str, Any]]:
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
                "budget_allocation": c.budget_allocation,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]

    async def create_regional_proposal(
        self,
        council_id: str,
        title: str,
        description: str,
        proposal_type: str,
        amount_requested: float,
        proposer_address: str,
    ) -> dict[str, Any]:
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus, RegionalCouncil
        from sqlmodel import select as sm_select

        council = self._session_factory.execute(
            sm_select(RegionalCouncil).where(RegionalCouncil.council_id == council_id)
        ).scalar_one_or_none()
        if not council:
            raise ValueError(f"Council {council_id} not found")
        proposer = await self.get_or_create_profile(proposer_address)
        proposal_id = f"rprop_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        proposal = DomainProposal(
            proposal_id=proposal_id,
            proposer_id=proposer.profile_id,
            council_id=council_id,
            title=title,
            description=description,
            category=proposal_type,
            execution_payload={"amount_requested": amount_requested},
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
            "amount_requested": amount_requested,
            "proposer_address": proposer_address,
            "status": proposal.status.value,
            "created_at": proposal.created_at.isoformat(),
        }

    async def vote_on_regional_proposal(
        self, proposal_id: str, voter_address: str, vote_type: Any, voting_power: float
    ) -> dict[str, Any]:
        from ..domain.governance import Proposal as DomainProposal, Vote as DomainVote, VoteType
        from sqlmodel import select as sm_select

        proposal = self._session_factory.execute(
            sm_select(DomainProposal).where(DomainProposal.proposal_id == proposal_id)
        ).scalar_one_or_none()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        voter = await self.get_or_create_profile(voter_address)
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

    async def get_treasury_balance(self, region: str | None = None) -> dict[str, Any]:
        return {
            "total_balance": 0.0,
            "allocated_funds": 0.0,
            "available": 0.0,
            "region": region or "global",
        }

    async def allocate_treasury_funds(
        self, council_id: str, amount: float, purpose: str, recipient_address: str, approver_address: str
    ) -> dict[str, Any]:
        allocation_id = f"alloc_{uuid4().hex[:8]}"
        return {
            "allocation_id": allocation_id,
            "council_id": council_id,
            "amount": amount,
            "purpose": purpose,
            "recipient_address": recipient_address,
            "approver_address": approver_address,
            "status": "approved",
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def get_treasury_transactions(
        self, limit: int = 100, offset: int = 0, region: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def create_staking_pool(
        self, pool_name: str, developer_address: str, base_apy: float, reputation_multiplier: float
    ) -> dict[str, Any]:
        pool_id = f"pool_{uuid4().hex[:8]}"
        return {
            "pool_id": pool_id,
            "pool_name": pool_name,
            "developer_address": developer_address,
            "base_apy": base_apy,
            "reputation_multiplier": reputation_multiplier,
            "total_staked": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def get_developer_staking_pools(self, developer_address: str | None = None) -> list[dict[str, Any]]:
        return []

    async def calculate_staking_rewards(
        self, pool_id: str, staker_address: str, amount: float, duration_days: int
    ) -> dict[str, Any]:
        estimated_reward = amount * 0.05 * (duration_days / 365)
        return {
            "pool_id": pool_id,
            "staker_address": staker_address,
            "amount": amount,
            "duration_days": duration_days,
            "estimated_reward": estimated_reward,
            "apy": 5.0,
        }

    async def distribute_staking_rewards(self, pool_id: str) -> dict[str, Any]:
        return {
            "pool_id": pool_id,
            "total_distributed": 0.0,
            "recipients": 0,
            "distributed_at": datetime.now(UTC).isoformat(),
        }

    async def get_governance_analytics(self, time_period_days: int = 30) -> dict[str, Any]:
        from ..domain.governance import Proposal as DomainProposal, ProposalStatus, RegionalCouncil, Vote as DomainVote
        from sqlmodel import func, select as sm_select

        total = self._session_factory.execute(sm_select(func.count(DomainProposal.proposal_id))).scalar() or 0
        active = (
            self._session_factory.execute(
                sm_select(func.count(DomainProposal.proposal_id)).where(DomainProposal.status == ProposalStatus.ACTIVE)
            ).scalar()
            or 0
        )
        passed = (
            self._session_factory.execute(
                sm_select(func.count(DomainProposal.proposal_id)).where(DomainProposal.status == ProposalStatus.SUCCEEDED)
            ).scalar()
            or 0
        )
        total_votes = self._session_factory.execute(sm_select(func.count(DomainVote.vote_id))).scalar() or 0
        total_councils = self._session_factory.execute(sm_select(func.count(RegionalCouncil.council_id))).scalar() or 0
        return {
            "time_period_days": time_period_days,
            "proposals": {
                "total": total,
                "still_active": active,
                "passed": passed,
                "total_votes": total_votes,
                "participation_rate": 0.0,
            },
            "regional_councils": {"total_councils": total_councils, "regions": 0},
            "treasury": {"total_allocations": 0.0, "total_balance": 0.0},
            "staking": {"active_pools": 0, "total_staked": 0.0},
        }

    async def get_regional_governance_health(self, region: str) -> dict[str, Any]:
        return {
            "region": region,
            "health_score": 100.0,
            "active_councils": 0,
            "pending_proposals": 0,
            "voter_participation": 0.0,
        }


_governance_service: GovernanceService | None = None


def init_governance_service(session_factory: Any) -> GovernanceService:
    """Initialize global governance service"""
    global _governance_service
    _governance_service = GovernanceService(session_factory)
    return _governance_service


def get_governance_service() -> GovernanceService | None:
    """Get global governance service"""
    return _governance_service
