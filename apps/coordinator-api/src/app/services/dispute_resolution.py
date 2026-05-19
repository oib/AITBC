"""
Dispute Resolution Service - On-chain arbitration for marketplace conflicts

Provides:
- Dispute filing by clients or providers
- Evidence submission
- Arbitrator voting
- Automated resolution
- Appeal handling
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select
from aitbc.aitbc_logging import get_logger


logger = get_logger(__name__)


class DisputeStatus(Enum):
    """Status of a dispute"""
    pending = "pending"
    under_review = "under_review"
    evidence_phase = "evidence_phase"
    voting_phase = "voting_phase"
    resolved = "resolved"
    appealed = "appealed"
    closed = "closed"


class DisputeOutcome(Enum):
    """Possible outcomes of a dispute"""
    client_wins = "client_wins"
    provider_wins = "provider_wins"
    split = "split"
    canceled = "canceled"


@dataclass
class DisputeEvidence:
    """Evidence submitted for a dispute"""
    submitted_by: str
    evidence_type: str
    description: str
    ipfs_hash: Optional[str]
    timestamp: datetime
    tx_hash: Optional[str] = None


@dataclass
class ArbitratorVote:
    """Vote by an arbitrator"""
    arbitrator: str
    outcome: DisputeOutcome
    reasoning: str
    stake_amount: int
    timestamp: datetime


class DisputeCase:
    """A dispute case"""
    
    def __init__(
        self,
        dispute_id: str,
        job_id: str,
        client: str,
        provider: str,
        amount: int,
        reason: str,
        filed_by: str
    ):
        self.dispute_id = dispute_id
        self.job_id = job_id
        self.client = client
        self.provider = provider
        self.amount = amount
        self.reason = reason
        self.filed_by = filed_by
        
        self.status = DisputeStatus.pending
        self.outcome: Optional[DisputeOutcome] = None
        
        self.created_at = datetime.now(timezone.utc)
        self.evidence_deadline: Optional[datetime] = None
        self.voting_deadline: Optional[datetime] = None
        self.resolved_at: Optional[datetime] = None
        
        self.evidence: List[DisputeEvidence] = []
        self.votes: List[ArbitratorVote] = []
        
        self.refund_amount: int = 0
        self.payout_amount: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dispute_id": self.dispute_id,
            "job_id": self.job_id,
            "client": self.client,
            "provider": self.provider,
            "amount": self.amount,
            "reason": self.reason,
            "filed_by": self.filed_by,
            "status": self.status.value,
            "outcome": self.outcome.value if self.outcome else None,
            "created_at": self.created_at.isoformat(),
            "evidence_deadline": self.evidence_deadline.isoformat() if self.evidence_deadline else None,
            "voting_deadline": self.voting_deadline.isoformat() if self.voting_deadline else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "evidence_count": len(self.evidence),
            "vote_count": len(self.votes)
        }


class DisputeResolutionService:
    """
    Dispute resolution service for marketplace conflicts.
    
    Handles the full lifecycle of disputes:
    1. Filing - Client or provider opens a dispute
    2. Evidence - Both parties submit evidence
    3. Voting - Arbitrators review and vote
    4. Resolution - Outcome determined and executed
    5. Appeal - Optional second round if appealed
    """
    
    # Configuration
    EVIDENCE_PERIOD_HOURS = 48
    VOTING_PERIOD_HOURS = 24
    MIN_ARBITRATORS = 3
    MIN_STAKE_AMOUNT = 1000
    
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._disputes: Dict[str, DisputeCase] = {}
        self._arbitrators: set = set()
    
    def file_dispute(
        self,
        job_id: str,
        client: str,
        provider: str,
        amount: int,
        reason: str,
        filed_by: str,
        initial_evidence: Optional[str] = None
    ) -> DisputeCase:
        """
        File a new dispute.
        
        Args:
            job_id: The job being disputed
            client: Client address
            provider: Provider/miner address
            amount: Amount in dispute
            reason: Reason for dispute
            filed_by: Who filed (client or provider)
            initial_evidence: Optional initial evidence
        
        Returns:
            Created dispute case
        """
        # Generate dispute ID
        dispute_id = self._generate_dispute_id(job_id, filed_by)
        
        # Create dispute
        dispute = DisputeCase(
            dispute_id=dispute_id,
            job_id=job_id,
            client=client,
            provider=provider,
            amount=amount,
            reason=reason,
            filed_by=filed_by
        )
        
        # Set deadlines
        now = datetime.now(timezone.utc)
        dispute.evidence_deadline = now + timedelta(hours=self.EVIDENCE_PERIOD_HOURS)
        dispute.voting_deadline = dispute.evidence_deadline + timedelta(hours=self.VOTING_PERIOD_HOURS)
        dispute.status = DisputeStatus.evidence_phase
        
        # Add initial evidence if provided
        if initial_evidence:
            evidence = DisputeEvidence(
                submitted_by=filed_by,
                evidence_type="initial",
                description=initial_evidence,
                ipfs_hash=None,
                timestamp=now
            )
            dispute.evidence.append(evidence)
        
        self._disputes[dispute_id] = dispute
        
        logger.info(f"Dispute filed: {dispute_id} for job {job_id} by {filed_by}")
        
        return dispute
    
    def submit_evidence(
        self,
        dispute_id: str,
        submitted_by: str,
        evidence_type: str,
        description: str,
        ipfs_hash: Optional[str] = None
    ) -> bool:
        """Submit evidence for a dispute"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")
        
        if dispute.status != DisputeStatus.evidence_phase:
            raise ValueError(f"Cannot submit evidence, dispute is {dispute.status.value}")
        
        # Check deadline
        if datetime.now(timezone.utc) > dispute.evidence_deadline:
            raise ValueError("Evidence submission deadline has passed")
        
        # Verify submitter is involved
        if submitted_by not in [dispute.client, dispute.provider]:
            raise ValueError("Only involved parties can submit evidence")
        
        evidence = DisputeEvidence(
            submitted_by=submitted_by,
            evidence_type=evidence_type,
            description=description,
            ipfs_hash=ipfs_hash,
            timestamp=datetime.now(timezone.utc)
        )
        
        dispute.evidence.append(evidence)
        
        logger.info(f"Evidence submitted for dispute {dispute_id} by {submitted_by}")
        
        return True
    
    def cast_vote(
        self,
        dispute_id: str,
        arbitrator: str,
        outcome: str,
        reasoning: str,
        stake_amount: int
    ) -> bool:
        """
        Cast a vote as an arbitrator.
        
        Args:
            dispute_id: Dispute being voted on
            arbitrator: Arbitrator address
            outcome: "client_wins", "provider_wins", or "split"
            reasoning: Explanation for vote
            stake_amount: Amount staked on this vote
        """
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")
        
        # Check status
        if dispute.status not in [DisputeStatus.voting_phase, DisputeStatus.evidence_phase]:
            raise ValueError(f"Cannot vote, dispute is {dispute.status.value}")
        
        # Auto-advance to voting if evidence period ended
        if dispute.status == DisputeStatus.evidence_phase:
            if datetime.now(timezone.utc) >= dispute.evidence_deadline:
                dispute.status = DisputeStatus.voting_phase
        
        # Check voting deadline
        if datetime.now(timezone.utc) > dispute.voting_deadline:
            raise ValueError("Voting deadline has passed")
        
        # Verify arbitrator is valid
        if arbitrator not in self._arbitrators:
            raise ValueError("Not a registered arbitrator")
        
        # Check minimum stake
        if stake_amount < self.MIN_STAKE_AMOUNT:
            raise ValueError(f"Minimum stake is {self.MIN_STAKE_AMOUNT}")
        
        # Convert outcome
        try:
            outcome_enum = DisputeOutcome(outcome)
        except ValueError:
            raise ValueError(f"Invalid outcome: {outcome}")
        
        # Check for duplicate vote
        for vote in dispute.votes:
            if vote.arbitrator == arbitrator:
                raise ValueError("Arbitrator has already voted")
        
        vote = ArbitratorVote(
            arbitrator=arbitrator,
            outcome=outcome_enum,
            reasoning=reasoning,
            stake_amount=stake_amount,
            timestamp=datetime.now(timezone.utc)
        )
        
        dispute.votes.append(vote)
        
        logger.info(f"Vote cast for dispute {dispute_id} by {arbitrator}: {outcome}")
        
        # Check if we can resolve
        if len(dispute.votes) >= self.MIN_ARBITRATORS:
            self._resolve_dispute(dispute)
        
        return True
    
    def _resolve_dispute(self, dispute: DisputeCase):
        """Resolve dispute based on votes"""
        if not dispute.votes:
            return
        
        # Count votes by outcome
        votes_by_outcome: Dict[DisputeOutcome, int] = {}
        total_stake: Dict[DisputeOutcome, int] = {}
        
        for vote in dispute.votes:
            votes_by_outcome[vote.outcome] = votes_by_outcome.get(vote.outcome, 0) + 1
            total_stake[vote.outcome] = total_stake.get(vote.outcome, 0) + vote.stake_amount
        
        # Determine winner (weighted by stake)
        winner = max(total_stake.items(), key=lambda x: x[1])[0]
        
        dispute.outcome = winner
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.status = DisputeStatus.resolved
        
        # Calculate payouts
        if winner == DisputeOutcome.client_wins:
            dispute.refund_amount = dispute.amount
            dispute.payout_amount = 0
        elif winner == DisputeOutcome.provider_wins:
            dispute.refund_amount = 0
            dispute.payout_amount = dispute.amount
        elif winner == DisputeOutcome.split:
            split_amount = dispute.amount // 2
            dispute.refund_amount = split_amount
            dispute.payout_amount = split_amount
        
        logger.info(
            f"Dispute {dispute.dispute_id} resolved: {winner.value} "
            f"(refund: {dispute.refund_amount}, payout: {dispute.payout_amount})"
        )
    
    def get_dispute(self, dispute_id: str) -> Optional[DisputeCase]:
        """Get dispute by ID"""
        return self._disputes.get(dispute_id)
    
    def list_disputes(
        self,
        status: Optional[str] = None,
        party: Optional[str] = None
    ) -> List[DisputeCase]:
        """List disputes with optional filters"""
        result = list(self._disputes.values())
        
        if status:
            result = [d for d in result if d.status.value == status]
        
        if party:
            result = [
                d for d in result
                if d.client == party or d.provider == party
            ]
        
        return result
    
    def register_arbitrator(self, address: str) -> bool:
        """Register an arbitrator"""
        self._arbitrators.add(address)
        logger.info(f"Arbitrator registered: {address}")
        return True
    
    def is_arbitrator(self, address: str) -> bool:
        """Check if address is a registered arbitrator"""
        return address in self._arbitrators
    
    def _generate_dispute_id(self, job_id: str, filed_by: str) -> str:
        """Generate unique dispute ID"""
        data = f"{job_id}:{filed_by}:{datetime.now(timezone.utc).isoformat()}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()[:32]


# Global instance
_dispute_service: Optional[DisputeResolutionService] = None


def init_dispute_service(session_factory) -> DisputeResolutionService:
    """Initialize global dispute service"""
    global _dispute_service
    _dispute_service = DisputeResolutionService(session_factory)
    return _dispute_service


def get_dispute_service() -> Optional[DisputeResolutionService]:
    """Get global dispute service"""
    return _dispute_service
