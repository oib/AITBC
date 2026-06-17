"""Service for Hermes distributed decision making."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ....schemas.hermes_decision import (
    DecisionProposal,
    DecisionProposalResponse,
    DecisionResult,
    DecisionStatus,
    DecisionType,
    Vote,
    VoteOption,
    VoteResponse,
)

logger = get_logger(__name__)


class DecisionService:
    """Service for managing distributed agent decisions."""

    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, Any]] = {}
        self.votes: dict[str, list[dict[str, Any]]] = {}

    def propose_decision(self, proposal: DecisionProposal, session: Session) -> DecisionProposalResponse:
        """Create a new decision proposal for agent voting."""
        decision_id = str(uuid.uuid4())
        decision = {
            "decision_id": decision_id,
            "decision_type": proposal.decision_type,
            "title": proposal.title,
            "description": proposal.description,
            "proposed_by": proposal.proposed_by,
            "created_at": datetime.utcnow(),
            "voting_deadline": proposal.voting_deadline,
            "min_participation": proposal.min_participation,
            "required_approval": proposal.required_approval,
            "status": DecisionStatus.PENDING,
            "metadata": proposal.metadata or {},
        }
        self.decisions[decision_id] = decision
        self.votes[decision_id] = []
        logger.info("Decision proposal created: %s - %s", decision_id, proposal.title)
        return DecisionProposalResponse(
            decision_id=decision_id,
            status=DecisionStatus.PENDING,
            created_at=decision["created_at"],
            voting_deadline=decision["voting_deadline"],
            message="Decision proposal created successfully",
        )

    def submit_vote(self, vote: Vote, session: Session) -> VoteResponse:
        """Submit an agent vote on a decision."""
        if vote.decision_id not in self.decisions:
            return VoteResponse(vote_id="", decision_id=vote.decision_id, status="error", message="Decision not found")
        decision = self.decisions[vote.decision_id]
        now = datetime.utcnow()
        deadline = decision["voting_deadline"]
        if deadline.tzinfo is not None:
            now = datetime.now(deadline.tzinfo)
        if now > deadline:
            return VoteResponse(vote_id="", decision_id=vote.decision_id, status="error", message="Voting deadline has passed")
        for existing_vote in self.votes[vote.decision_id]:
            if existing_vote["agent_id"] == vote.agent_id:
                return VoteResponse(
                    vote_id="", decision_id=vote.decision_id, status="error", message="Agent has already voted"
                )
        vote_id = str(uuid.uuid4())
        vote_record = {
            "vote_id": vote_id,
            "agent_id": vote.agent_id,
            "vote": vote.vote,
            "weight": vote.weight,
            "reason": vote.reason,
            "voted_at": datetime.utcnow(),
        }
        self.votes[vote.decision_id].append(vote_record)
        decision["status"] = DecisionStatus.IN_PROGRESS
        logger.info("Vote submitted: %s by %s on %s", vote_id, vote.agent_id, vote.decision_id)
        return VoteResponse(
            vote_id=vote_id, decision_id=vote.decision_id, status="success", message="Vote submitted successfully"
        )

    def get_decision_result(self, decision_id: str, session: Session) -> DecisionResult | None:
        """Get the current result of a decision."""
        if decision_id not in self.decisions:
            return None
        decision = self.decisions[decision_id]
        votes = self.votes[decision_id]
        total_votes = len(votes)
        approve_votes = sum(1 for v in votes if v["vote"] == VoteOption.APPROVE)
        reject_votes = sum(1 for v in votes if v["vote"] == VoteOption.REJECT)
        abstain_votes = sum(1 for v in votes if v["vote"] == VoteOption.ABSTAIN)
        weighted_approve = sum(v["weight"] for v in votes if v["vote"] == VoteOption.APPROVE)
        weighted_reject = sum(v["weight"] for v in votes if v["vote"] == VoteOption.REJECT)
        weighted_abstain = sum(v["weight"] for v in votes if v["vote"] == VoteOption.ABSTAIN)
        total_weight = weighted_approve + weighted_reject + weighted_abstain
        participation_rate = total_weight / max(total_weight, 1.0)
        approval_rate = weighted_approve / max(weighted_approve + weighted_reject, 1.0)
        final_decision = None
        concluded_at = None
        now = datetime.utcnow()
        deadline = decision["voting_deadline"]
        if deadline.tzinfo is not None:
            now = datetime.now(deadline.tzinfo)
        if now > deadline:
            if participation_rate >= decision["min_participation"]:
                if approval_rate >= decision["required_approval"]:
                    final_decision = VoteOption.APPROVE
                    decision["status"] = DecisionStatus.APPROVED
                else:
                    final_decision = VoteOption.REJECT
                    decision["status"] = DecisionStatus.REJECTED
            else:
                decision["status"] = DecisionStatus.EXPIRED
            concluded_at = now
        return DecisionResult(
            decision_id=decision_id,
            status=decision["status"],
            total_votes=total_votes,
            approve_votes=approve_votes,
            reject_votes=reject_votes,
            abstain_votes=abstain_votes,
            weighted_approve=weighted_approve,
            weighted_reject=weighted_reject,
            weighted_abstain=weighted_abstain,
            participation_rate=participation_rate,
            approval_rate=approval_rate,
            final_decision=final_decision,
            concluded_at=concluded_at,
        )

    def list_decisions(
        self, session: Session, decision_type: DecisionType | None = None, status: DecisionStatus | None = None
    ) -> list[DecisionResult]:
        """List all decisions with optional filtering."""
        results = []
        for decision_id in self.decisions:
            result = self.get_decision_result(decision_id, session)
            if result:
                if decision_type and self.decisions[decision_id]["decision_type"] != decision_type:
                    continue
                if status and result.status != status:
                    continue
                results.append(result)
        return results


decision_service = DecisionService()
