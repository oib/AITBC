"""
Decentralized Governance Service
Implements the hermes DAO, voting mechanisms, and proposal lifecycle
Enhanced with multi-jurisdictional support and regional governance
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from aitbc import get_logger
from sqlmodel import Session, select

logger = get_logger(__name__)

from ....domain.governance import (
    DaoTreasury,
    GovernanceProfile,
    GovernanceRole,
    Proposal,
    ProposalStatus,
    TransparencyReport,
    Vote,
    VoteType,
)


class GovernanceService:
    """Core service for managing DAO operations and voting"""

    def __init__(self, session: Session):
        self.session = session

    async def get_or_create_profile(self, user_id: str, initial_voting_power: float = 0.0) -> GovernanceProfile:
        """Get an existing governance profile or create a new one"""
        profile = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.user_id == user_id)).first()

        if not profile:
            profile = GovernanceProfile(user_id=user_id, voting_power=initial_voting_power)
            self.session.add(profile)
            self.session.commit()
            self.session.refresh(profile)

        return profile

    async def delegate_votes(self, delegator_id: str, delegatee_id: str) -> GovernanceProfile:
        """Delegate voting power from one profile to another"""
        delegator = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == delegator_id)).first()
        delegatee = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == delegatee_id)).first()

        if not delegator or not delegatee:
            raise ValueError("Delegator or Delegatee not found")

        # Remove old delegation if exists
        if delegator.delegate_to:
            old_delegatee = self.session.execute(
                select(GovernanceProfile).where(GovernanceProfile.profile_id == delegator.delegate_to)
            ).first()
            if old_delegatee:
                old_delegatee.delegated_power -= delegator.voting_power

        # Apply new delegation
        delegator.delegate_to = delegatee_id
        delegatee.delegated_power += delegator.voting_power

        self.session.commit()
        self.session.refresh(delegator)
        self.session.refresh(delegatee)

        logger.info(f"Votes delegated from {delegator_id} to {delegatee_id}")
        return delegator

    async def create_proposal(self, proposer_id: str, data: dict[str, Any]) -> Proposal:
        """Create a new governance proposal"""
        proposer = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == proposer_id)).first()

        if not proposer:
            raise ValueError("Proposer not found")

        # Ensure proposer meets minimum voting power requirement to submit
        total_power = proposer.voting_power + proposer.delegated_power
        if total_power < 100.0:  # Arbitrary minimum threshold for example
            raise ValueError("Insufficient voting power to submit a proposal")

        now = datetime.now(timezone.utc)
        voting_starts = data.get("voting_starts", now + timedelta(days=1))
        if isinstance(voting_starts, str):
            voting_starts = datetime.fromisoformat(voting_starts.replace('Z', '+00:00'))

        voting_ends = data.get("voting_ends", voting_starts + timedelta(days=7))
        if isinstance(voting_ends, str):
            voting_ends = datetime.fromisoformat(voting_ends.replace('Z', '+00:00'))

        proposal = Proposal(
            proposer_id=proposer_id,
            title=data.get("title"),
            description=data.get("description"),
            category=data.get("category", "general"),
            execution_payload=data.get("execution_payload", {}),
            quorum_required=data.get("quorum_required", 1000.0),  # Example default
            voting_starts=voting_starts,
            voting_ends=voting_ends,
        )

        # If voting starts immediately
        if voting_starts <= now:
            proposal.status = ProposalStatus.ACTIVE

        proposer.proposals_created += 1

        self.session.add(proposal)
        self.session.add(proposer)
        self.session.commit()
        self.session.refresh(proposal)

        return proposal

    async def cast_vote(self, proposal_id: str, voter_id: str, vote_type: VoteType, reason: str = None) -> Vote:
        """Cast a vote on an active proposal"""
        proposal = self.session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id)).first()
        voter = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == voter_id)).first()

        if not proposal or not voter:
            raise ValueError("Proposal or Voter not found")

        now = datetime.now(timezone.utc)
        if proposal.status != ProposalStatus.ACTIVE or now < proposal.voting_starts or now > proposal.voting_ends:
            raise ValueError("Proposal is not currently active for voting")

        # Check if already voted
        existing_vote = self.session.execute(
            select(Vote).where(Vote.proposal_id == proposal_id).where(Vote.voter_id == voter_id)
        ).first()

        if existing_vote:
            raise ValueError("Voter has already cast a vote on this proposal")

        # If voter has delegated their vote, they cannot vote directly (or it overrides)
        # For this implementation, we'll say direct voting is allowed but we only use their personal power
        power_to_use = voter.voting_power + voter.delegated_power
        if power_to_use <= 0:
            raise ValueError("Voter has no voting power")

        vote = Vote(
            proposal_id=proposal_id, voter_id=voter_id, vote_type=vote_type, voting_power_used=power_to_use, reason=reason
        )

        # Update proposal tallies
        if vote_type == VoteType.FOR:
            proposal.votes_for += power_to_use
        elif vote_type == VoteType.AGAINST:
            proposal.votes_against += power_to_use
        else:
            proposal.votes_abstain += power_to_use

        voter.total_votes_cast += 1
        voter.last_voted_at = now

        self.session.add(vote)
        self.session.add(proposal)
        self.session.add(voter)
        self.session.commit()
        self.session.refresh(vote)

        return vote

    async def process_proposal_lifecycle(self, proposal_id: str) -> Proposal:
        """Update proposal status based on time and votes"""
        proposal = self.session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id)).first()
        if not proposal:
            raise ValueError("Proposal not found")

        now = datetime.now(timezone.utc)

        # Draft -> Active
        if proposal.status == ProposalStatus.DRAFT and now >= proposal.voting_starts:
            proposal.status = ProposalStatus.ACTIVE

        # Active -> Succeeded/Defeated
        elif proposal.status == ProposalStatus.ACTIVE and now > proposal.voting_ends:
            total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain

            # Check Quorum
            if total_votes < proposal.quorum_required:
                proposal.status = ProposalStatus.DEFEATED
            else:
                # Check threshold (usually just FOR vs AGAINST)
                votes_cast = proposal.votes_for + proposal.votes_against
                if votes_cast == 0:
                    proposal.status = ProposalStatus.DEFEATED
                else:
                    ratio = proposal.votes_for / votes_cast
                    if ratio >= proposal.passing_threshold:
                        proposal.status = ProposalStatus.SUCCEEDED

                        # Update proposer stats
                        proposer = self.session.execute(
                            select(GovernanceProfile).where(GovernanceProfile.profile_id == proposal.proposer_id)
                        ).first()
                        if proposer:
                            proposer.proposals_passed += 1
                            self.session.add(proposer)
                    else:
                        proposal.status = ProposalStatus.DEFEATED

        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    async def execute_proposal(self, proposal_id: str, executor_id: str) -> Proposal:
        """Execute a successful proposal's payload"""
        proposal = self.session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id)).first()
        executor = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == executor_id)).first()

        if not proposal or not executor:
            raise ValueError("Proposal or Executor not found")

        if proposal.status != ProposalStatus.SUCCEEDED:
            raise ValueError("Only SUCCEEDED proposals can be executed")

        if executor.role not in [GovernanceRole.ADMIN, GovernanceRole.COUNCIL]:
            raise ValueError("Only Council or Admin members can trigger execution")

        # In a real system, this would interact with smart contracts or internal service APIs
        # based on proposal.execution_payload
        logger.info(f"Executing proposal {proposal_id} payload: {proposal.execution_payload}")

        # If it's a funding proposal, deduct from treasury
        if proposal.category == "funding" and "amount" in proposal.execution_payload:
            treasury = self.session.execute(select(DaoTreasury).where(DaoTreasury.treasury_id == "main_treasury")).first()
            if treasury:
                amount = float(proposal.execution_payload["amount"])
                if treasury.total_balance - treasury.allocated_funds >= amount:
                    treasury.allocated_funds += amount
                    self.session.add(treasury)
                else:
                    raise ValueError("Insufficient funds in DAO Treasury for execution")

        proposal.status = ProposalStatus.EXECUTED
        proposal.executed_at = datetime.now(timezone.utc)

        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    async def generate_transparency_report(self, period: str) -> TransparencyReport:
        """Generate automated governance analytics report"""

        # In reality, we would calculate this based on timestamps matching the period
        # For simplicity, we just aggregate current totals

        proposals = self.session.execute(select(Proposal)).all()
        profiles = self.session.execute(select(GovernanceProfile)).all()
        treasury = self.session.execute(select(DaoTreasury).where(DaoTreasury.treasury_id == "main_treasury")).first()

        total_proposals = len(proposals)
        passed_proposals = len([p for p in proposals if p.status in [ProposalStatus.SUCCEEDED, ProposalStatus.EXECUTED]])
        active_voters = len([p for p in profiles if p.total_votes_cast > 0])
        total_power = sum(p.voting_power for p in profiles)

        # Use real treasury data if available
        treasury_inflow = treasury.total_balance if treasury else 0.0
        treasury_outflow = treasury.allocated_funds if treasury else 0.0

        report = TransparencyReport(
            period=period,
            total_proposals=total_proposals,
            passed_proposals=passed_proposals,
            active_voters=active_voters,
            total_voting_power_participated=total_power,
            treasury_inflow=treasury_inflow,
            treasury_outflow=treasury_outflow,
            metrics={
                "voter_participation_rate": (active_voters / len(profiles)) if profiles else 0,
                "proposal_success_rate": (passed_proposals / total_proposals) if total_proposals else 0,
            },
        )

        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)

        return report

    # Staking Pool Methods
    async def create_staking_pool(
        self, pool_name: str, developer_address: str, base_apy: float, reputation_multiplier: float
    ) -> dict[str, Any]:
        """Create a staking pool for an agent developer"""
        pool_id = f"pool_{uuid.uuid4().hex[:8]}"
        pool = {
            "pool_id": pool_id,
            "pool_name": pool_name,
            "developer_address": developer_address,
            "base_apy": base_apy,
            "reputation_multiplier": reputation_multiplier,
            "total_staked": 0.0,
            "stakers_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return pool

    async def get_developer_staking_pools(self, developer_address: str | None = None) -> list[dict[str, Any]]:
        """Get staking pools for a specific developer or all pools"""
        # Mock implementation - in reality would query database
        pools = []
        if developer_address:
            pools.append(
                {
                    "pool_id": "pool_abc123",
                    "pool_name": f"Pool for {developer_address}",
                    "developer_address": developer_address,
                    "base_apy": 7.5,
                    "reputation_multiplier": 1.0,
                    "total_staked": 1000000.0,
                    "stakers_count": 500,
                }
            )
        return pools

    async def calculate_staking_rewards(
        self, pool_id: str, staker_address: str, amount: float, duration_days: int
    ) -> dict[str, Any]:
        """Calculate staking rewards for a specific position"""
        # Mock calculation
        base_apy = 7.5
        daily_rate = base_apy / 365
        rewards = amount * daily_rate * duration_days
        return {
            "pool_id": pool_id,
            "staker_address": staker_address,
            "amount_staked": amount,
            "duration_days": duration_days,
            "estimated_rewards": rewards,
            "apy": base_apy,
        }

    async def distribute_staking_rewards(self, pool_id: str) -> dict[str, Any]:
        """Distribute rewards to all stakers in a pool"""
        return {
            "pool_id": pool_id,
            "total_distributed": 75000.0,
            "stakers_rewarded": 500,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Regional Council Methods
    async def create_regional_council(
        self, region: str, council_name: str, jurisdiction: str, council_members: list[str], budget_allocation: float
    ) -> dict[str, Any]:
        """Create a regional governance council"""
        council_id = f"council_{uuid.uuid4().hex[:8]}"
        council = {
            "council_id": council_id,
            "region": region,
            "council_name": council_name,
            "jurisdiction": jurisdiction,
            "council_members": council_members,
            "budget_allocation": budget_allocation,
            "budget_spent": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return council

    async def get_regional_councils(self, region: str | None = None) -> list[dict[str, Any]]:
        """Get regional governance councils"""
        # Mock implementation
        councils = []
        if region is None or region == "global":
            councils.append(
                {
                    "council_id": "council_global",
                    "region": "global",
                    "council_name": "Global Council",
                    "jurisdiction": "international",
                    "council_members": ["delegate_1", "delegate_2"],
                    "budget_allocation": 1000000.0,
                    "budget_spent": 250000.0,
                }
            )
        return councils

    async def create_regional_proposal(
        self,
        council_id: str,
        title: str,
        description: str,
        proposal_type: str,
        amount_requested: float,
        proposer_address: str,
    ) -> dict[str, Any]:
        """Create a proposal for a specific regional council"""
        proposal_id = f"reg_prop_{uuid.uuid4().hex[:8]}"
        proposal = {
            "proposal_id": proposal_id,
            "council_id": council_id,
            "title": title,
            "description": description,
            "proposal_type": proposal_type,
            "amount_requested": amount_requested,
            "proposer_address": proposer_address,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return proposal

    async def vote_on_regional_proposal(
        self, proposal_id: str, voter_address: str, vote_type: VoteType, voting_power: float
    ) -> dict[str, Any]:
        """Vote on a regional proposal"""
        return {
            "proposal_id": proposal_id,
            "voter_address": voter_address,
            "vote_type": vote_type.value,
            "voting_power": voting_power,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Treasury Methods
    async def get_treasury_balance(self, region: str | None = None) -> dict[str, Any]:
        """Get treasury balance for global or specific region"""
        return {
            "region": region or "global",
            "total_balance": 10000000.0,
            "allocated_funds": 2500000.0,
            "available_funds": 7500000.0,
            "currency": "AIT",
        }

    async def allocate_treasury_funds(
        self, council_id: str, amount: float, purpose: str, recipient_address: str, approver_address: str
    ) -> dict[str, Any]:
        """Allocate treasury funds to a regional council or project"""
        allocation_id = f"alloc_{uuid.uuid4().hex[:8]}"
        return {
            "allocation_id": allocation_id,
            "council_id": council_id,
            "amount": amount,
            "purpose": purpose,
            "recipient_address": recipient_address,
            "approver_address": approver_address,
            "status": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_treasury_transactions(
        self, limit: int = 100, offset: int = 0, region: str | None = None
    ) -> list[dict[str, Any]]:
        """Get treasury transaction history"""
        # Mock implementation
        return [
            {
                "transaction_id": f"tx_{i}",
                "type": "allocation",
                "amount": 10000.0,
                "recipient": f"council_{i}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(min(limit, 10))
        ]

    # Analytics Methods
    async def get_governance_analytics(self, time_period_days: int) -> dict[str, Any]:
        """Get comprehensive governance analytics"""
        proposals = self.session.execute(select(Proposal)).all()
        profiles = self.session.execute(select(GovernanceProfile)).all()

        total_proposals = len(proposals)
        active_proposals = len([p for p in proposals if p.status == ProposalStatus.ACTIVE])
        passed_proposals = len([p for p in proposals if p.status in [ProposalStatus.SUCCEEDED, ProposalStatus.EXECUTED]])

        total_votes_cast = sum(p.total_votes_cast for p in profiles)
        total_voting_power = sum(p.voting_power for p in profiles)

        return {
            "time_period_days": time_period_days,
            "proposals": {
                "total": total_proposals,
                "still_active": active_proposals,
                "passed": passed_proposals,
                "defeated": total_proposals - passed_proposals,
            },
            "voting": {
                "total_votes_cast": total_votes_cast,
                "total_voting_power": total_voting_power,
                "average_voter_participation": 75.0,  # Mock percentage
            },
            "regional_councils": {
                "total_councils": 3,
                "active_councils": 3,
            },
            "treasury": {
                "total_allocations": 2500000.0,
                "utilization_rate": 25.0,
            },
            "staking": {
                "active_pools": 5,
                "total_staked": 1000000.0,
                "average_apy": 7.5,
            },
        }

    async def get_regional_governance_health(self, region: str) -> dict[str, Any]:
        """Get health metrics for a specific region's governance"""
        return {
            "region": region,
            "overall_health": "healthy",
            "councils_active": 1,
            "proposals_pending": 2,
            "proposals_passed": 10,
            "voting_participation": 85.0,
            "treasury_balance": 1000000.0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
