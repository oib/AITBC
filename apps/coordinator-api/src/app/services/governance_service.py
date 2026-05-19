"""
Governance Service - On-chain proposal and voting system

Provides:
- Proposal creation
- Voting with stake-weighted power
- Proposal execution
- Governance parameters
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

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
    
    # Voting
    votes_for: int
    votes_against: int
    votes_abstain: int
    
    # Thresholds
    quorum: int
    threshold: float  # Percentage required to pass
    
    # Timeline
    created_at: datetime
    voting_start: datetime
    voting_end: datetime
    executed_at: Optional[datetime]
    
    # Execution
    call_data: Optional[Dict[str, Any]]
    execution_hash: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
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
                "total": self.votes_for + self.votes_against + self.votes_abstain
            },
            "threshold": {
                "quorum": self.quorum,
                "approval": self.threshold
            },
            "timeline": {
                "created": self.created_at.isoformat(),
                "voting_start": self.voting_start.isoformat(),
                "voting_end": self.voting_end.isoformat(),
                "executed": self.executed_at.isoformat() if self.executed_at else None
            },
            "execution": self.call_data
        }


@dataclass
class Vote:
    """Individual vote record"""
    proposal_id: str
    voter: str
    choice: str  # for, against, abstain
    power: int   # Stake-weighted voting power
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
    
    # Configuration
    MIN_PROPOSAL_STAKE = 10000  # Minimum stake to create proposal
    VOTING_PERIOD_DAYS = 7
    QUORUM_PERCENTAGE = 20  # 20% of total stake must vote
    APPROVAL_THRESHOLD = 50  # 50% approval required
    
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._proposals: Dict[str, Proposal] = {}
        self._votes: Dict[str, List[Vote]] = {}  # proposal_id -> votes
        self._proposal_counter = 0
    
    def create_proposal(
        self,
        title: str,
        description: str,
        proposer: str,
        proposal_type: str,
        call_data: Optional[Dict[str, Any]] = None
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
        # Verify proposer has minimum stake
        # In production, check against staking contract
        
        # Generate proposal ID
        self._proposal_counter += 1
        proposal_id = f"PROP-{self._proposal_counter:04d}"
        
        # Parse proposal type
        try:
            p_type = ProposalType(proposal_type)
        except ValueError:
            p_type = ProposalType.parameter_change
        
        # Set timeline
        now = datetime.now(timezone.utc)
        voting_start = now  # Immediate start
        voting_end = now + timedelta(days=self.VOTING_PERIOD_DAYS)
        
        # Create execution hash
        execution_hash = None
        if call_data:
            execution_hash = hashlib.sha256(
                json.dumps(call_data, sort_keys=True).encode()
            ).hexdigest()[:32]
        
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
            quorum=self.MIN_PROPOSAL_STAKE * 10,  # Placeholder
            threshold=self.APPROVAL_THRESHOLD,
            created_at=now,
            voting_start=voting_start,
            voting_end=voting_end,
            executed_at=None,
            call_data=call_data,
            execution_hash=execution_hash
        )
        
        self._proposals[proposal_id] = proposal
        self._votes[proposal_id] = []
        
        logger.info(f"Proposal created: {proposal_id} by {proposer}")
        
        return proposal
    
    def cast_vote(
        self,
        proposal_id: str,
        voter: str,
        choice: str,
        voting_power: int
    ) -> bool:
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
        
        now = datetime.now(timezone.utc)
        if now > proposal.voting_end:
            raise ValueError("Voting period has ended")
        
        # Check for duplicate vote
        for vote in self._votes[proposal_id]:
            if vote.voter == voter:
                raise ValueError("Already voted on this proposal")
        
        # Record vote
        vote = Vote(
            proposal_id=proposal_id,
            voter=voter,
            choice=choice,
            power=voting_power,
            timestamp=now
        )
        
        self._votes[proposal_id].append(vote)
        
        # Update tallies
        if choice == "for":
            proposal.votes_for += voting_power
        elif choice == "against":
            proposal.votes_against += voting_power
        elif choice == "abstain":
            proposal.votes_abstain += voting_power
        
        logger.info(f"Vote cast on {proposal_id}: {voter} voted {choice} ({voting_power} power)")
        
        # Check if proposal can be resolved
        self._check_proposal_resolution(proposal)
        
        return True
    
    def _check_proposal_resolution(self, proposal: Proposal):
        """Check if proposal meets resolution criteria"""
        total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
        
        # Check quorum
        if total_votes < proposal.quorum:
            return
        
        # Check voting period ended
        if datetime.now(timezone.utc) < proposal.voting_end:
            return
        
        # Calculate approval percentage
        total_for_against = proposal.votes_for + proposal.votes_against
        if total_for_against == 0:
            approval_pct = 0
        else:
            approval_pct = (proposal.votes_for / total_for_against) * 100
        
        # Determine outcome
        if approval_pct >= proposal.threshold:
            proposal.status = ProposalStatus.passed
            logger.info(f"Proposal {proposal.id} PASSED ({approval_pct:.1f}% approval)")
        else:
            proposal.status = ProposalStatus.rejected
            logger.info(f"Proposal {proposal.id} REJECTED ({approval_pct:.1f}% approval)")
    
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
        
        # Check execution window (48 hours after voting ends)
        execution_deadline = proposal.voting_end + timedelta(hours=48)
        if datetime.now(timezone.utc) > execution_deadline:
            proposal.status = ProposalStatus.canceled
            raise ValueError("Execution window has expired")
        
        # Execute call data
        # In production, this would make actual contract calls
        if proposal.call_data:
            logger.info(f"Executing proposal {proposal_id}: {proposal.call_data}")
            # Simulate execution
            pass
        
        proposal.status = ProposalStatus.executed
        proposal.executed_at = datetime.now(timezone.utc)
        
        logger.info(f"Proposal executed: {proposal_id} by {executor}")
        
        return True
    
    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """Get proposal by ID"""
        return self._proposals.get(proposal_id)
    
    def list_proposals(
        self,
        status: Optional[str] = None,
        proposer: Optional[str] = None
    ) -> List[Proposal]:
        """List proposals with optional filters"""
        result = list(self._proposals.values())
        
        if status:
            result = [p for p in result if p.status.value == status]
        
        if proposer:
            result = [p for p in result if p.proposer == proposer]
        
        # Sort by created date, newest first
        result.sort(key=lambda p: p.created_at, reverse=True)
        
        return result
    
    def get_votes(self, proposal_id: str) -> List[Vote]:
        """Get all votes for a proposal"""
        return self._votes.get(proposal_id, [])
    
    def get_voting_power(self, address: str) -> int:
        """Get stake-weighted voting power for an address"""
        # In production, query staking contract
        # For now, return placeholder
        return 1000
    
    def get_governance_params(self) -> Dict[str, Any]:
        """Get current governance parameters"""
        return {
            "min_proposal_stake": self.MIN_PROPOSAL_STAKE,
            "voting_period_days": self.VOTING_PERIOD_DAYS,
            "quorum_percentage": self.QUORUM_PERCENTAGE,
            "approval_threshold": self.APPROVAL_THRESHOLD,
            "total_proposals": len(self._proposals),
            "active_proposals": len([p for p in self._proposals.values() if p.status == ProposalStatus.active])
        }


# Global instance
_governance_service: Optional[GovernanceService] = None


def init_governance_service(session_factory) -> GovernanceService:
    """Initialize global governance service"""
    global _governance_service
    _governance_service = GovernanceService(session_factory)
    return _governance_service


def get_governance_service() -> Optional[GovernanceService]:
    """Get global governance service"""
    return _governance_service
