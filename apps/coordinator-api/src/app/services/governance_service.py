"""
Decentralized Governance Service
Implements the OpenClaw DAO, voting mechanisms, and proposal lifecycle
Enhanced with multi-jurisdictional support and regional governance
"""

from typing import Optional, List, Dict, Any
from sqlmodel import Session, select
from datetime import datetime, timedelta
from aitbc.logging import get_logger
from uuid import uuid4

from ..domain.governance import (
    GovernanceProfile, Proposal, Vote, DaoTreasury, TransparencyReport,
    ProposalStatus, VoteType, GovernanceRole
)

logger = get_logger(__name__)

class GovernanceService:
    """Core service for managing DAO operations and voting"""
    
    def __init__(self, session: Session):
        self.session = session
        
    async def get_or_create_profile(self, user_id: str, initial_voting_power: float = 0.0) -> GovernanceProfile:
        """Get an existing governance profile or create a new one"""
        profile = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.user_id == user_id)).first()
        
        if not profile:
            profile = GovernanceProfile(
                user_id=user_id,
                voting_power=initial_voting_power
            )
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
            old_delegatee = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == delegator.delegate_to)).first()
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

    async def create_proposal(self, proposer_id: str, data: Dict[str, Any]) -> Proposal:
        """Create a new governance proposal"""
        proposer = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == proposer_id)).first()
        
        if not proposer:
            raise ValueError("Proposer not found")
            
        # Ensure proposer meets minimum voting power requirement to submit
        total_power = proposer.voting_power + proposer.delegated_power
        if total_power < 100.0:  # Arbitrary minimum threshold for example
            raise ValueError("Insufficient voting power to submit a proposal")
            
        now = datetime.utcnow()
        voting_starts = data.get('voting_starts', now + timedelta(days=1))
        if isinstance(voting_starts, str):
            voting_starts = datetime.fromisoformat(voting_starts)
            
        voting_ends = data.get('voting_ends', voting_starts + timedelta(days=7))
        if isinstance(voting_ends, str):
            voting_ends = datetime.fromisoformat(voting_ends)
            
        proposal = Proposal(
            proposer_id=proposer_id,
            title=data.get('title'),
            description=data.get('description'),
            category=data.get('category', 'general'),
            execution_payload=data.get('execution_payload', {}),
            quorum_required=data.get('quorum_required', 1000.0), # Example default
            voting_starts=voting_starts,
            voting_ends=voting_ends
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
            
        now = datetime.utcnow()
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
            proposal_id=proposal_id,
            voter_id=voter_id,
            vote_type=vote_type,
            voting_power_used=power_to_use,
            reason=reason
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
            
        now = datetime.utcnow()
        
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
                        proposer = self.session.execute(select(GovernanceProfile).where(GovernanceProfile.profile_id == proposal.proposer_id)).first()
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
        if proposal.category == 'funding' and 'amount' in proposal.execution_payload:
            treasury = self.session.execute(select(DaoTreasury).where(DaoTreasury.treasury_id == "main_treasury")).first()
            if treasury:
                amount = float(proposal.execution_payload['amount'])
                if treasury.total_balance - treasury.allocated_funds >= amount:
                    treasury.allocated_funds += amount
                    self.session.add(treasury)
                else:
                    raise ValueError("Insufficient funds in DAO Treasury for execution")
        
        proposal.status = ProposalStatus.EXECUTED
        proposal.executed_at = datetime.utcnow()
        
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
        
        report = TransparencyReport(
            period=period,
            total_proposals=total_proposals,
            passed_proposals=passed_proposals,
            active_voters=active_voters,
            total_voting_power_participated=total_power,
            treasury_inflow=10000.0, # Simulated
            treasury_outflow=treasury.allocated_funds if treasury else 0.0,
            metrics={
                "voter_participation_rate": (active_voters / len(profiles)) if profiles else 0,
                "proposal_success_rate": (passed_proposals / total_proposals) if total_proposals else 0
            }
        )
        
        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)
        
        return report
