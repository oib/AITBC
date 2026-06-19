"""Service for Hermes distributed decision making with database storage."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ...models.hermes import DecisionModel, VoteModel
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
    """Service for managing distributed agent decisions with database storage."""

    def __init__(self) -> None:
        pass

    def propose_decision(self, proposal: DecisionProposal, session: Session) -> DecisionProposalResponse:
        """Create a new decision proposal for agent voting."""
        decision_id = str(uuid.uuid4())
        decision = DecisionModel(
            id=decision_id,
            decision_type=proposal.decision_type,
            title=proposal.title,
            description=proposal.description,
            proposed_by=proposal.proposed_by,
            voting_deadline=proposal.voting_deadline,
            min_participation=proposal.min_participation,
            required_approval=proposal.required_approval,
            status=DecisionStatus.PENDING,
            meta_data=json.dumps(proposal.metadata or {}),
            created_at=datetime.now(UTC),
        )  # type: ignore[arg-type]
        session.add(decision)
        session.commit()
        logger.info("Decision proposed: %s - %s", decision_id, proposal.title)
        return DecisionProposalResponse(
            decision_id=decision_id,
            status=DecisionStatus.PENDING,
            created_at=decision.created_at,
            voting_deadline=decision.voting_deadline,
            message="Decision proposal created successfully",
        )

    def submit_vote(self, vote: Vote, session: Session) -> VoteResponse:
        """Submit an agent vote on a decision."""
        decision = session.query(DecisionModel).filter_by(id=vote.decision_id).first()
        if not decision:
            return VoteResponse(vote_id="", decision_id=vote.decision_id, status="error", message="Decision not found")
        now = datetime.now(UTC)
        deadline = decision.voting_deadline
        if deadline.tzinfo is not None:  # type: ignore[union-attr]
            now = datetime.now(deadline.tzinfo)  # type: ignore[union-attr]
        if now > deadline:  # type: ignore[operator]
            return VoteResponse(vote_id="", decision_id=vote.decision_id, status="error", message="Voting deadline has passed")
        existing_vote = session.query(VoteModel).filter_by(decision_id=vote.decision_id, agent_id=vote.agent_id).first()
        if existing_vote:
            return VoteResponse(vote_id="", decision_id=vote.decision_id, status="error", message="Agent has already voted")
        vote_id = str(uuid.uuid4())
        vote_record = VoteModel(
            id=vote_id,
            decision_id=vote.decision_id,
            agent_id=vote.agent_id,
            vote=vote.vote,
            weight=vote.weight,
            reason=vote.reason,
            created_at=datetime.now(UTC),
        )  # type: ignore[arg-type]
        session.add(vote_record)
        decision.status = DecisionStatus.IN_PROGRESS
        session.commit()
        logger.info("Vote submitted: %s by %s on %s", vote_id, vote.agent_id, vote.decision_id)
        return VoteResponse(
            vote_id=vote_id, decision_id=vote.decision_id, status="success", message="Vote submitted successfully"
        )

    def get_decision_result(self, decision_id: str, session: Session) -> DecisionResult | None:
        """Get the current result of a decision."""
        decision = session.query(DecisionModel).filter_by(id=decision_id).first()
        if not decision:
            return None
        votes = session.query(VoteModel).filter_by(decision_id=decision_id).all()
        total_votes = len(votes)
        approve_votes = sum(1 for v in votes if v.vote == VoteOption.APPROVE)
        reject_votes = sum(1 for v in votes if v.vote == VoteOption.REJECT)
        abstain_votes = sum(1 for v in votes if v.vote == VoteOption.ABSTAIN)
        weighted_approve = sum(v.weight for v in votes if v.vote == VoteOption.APPROVE)  # type: ignore[misc]
        weighted_reject = sum(v.weight for v in votes if v.vote == VoteOption.REJECT)  # type: ignore[misc]
        weighted_abstain = sum(v.weight for v in votes if v.vote == VoteOption.ABSTAIN)  # type: ignore[misc]
        total_weight = weighted_approve + weighted_reject + weighted_abstain
        total_weight = weighted_approve + weighted_reject + weighted_abstain
        participation_rate = total_weight / max(total_weight, 1.0)
        approval_rate = weighted_approve / max(weighted_approve + weighted_reject, 1.0)
        final_decision = None
        concluded_at = None
        now = datetime.now(UTC)
        deadline = decision.voting_deadline
        if deadline.tzinfo is not None:  # type: ignore[union-attr]
            now = datetime.now(deadline.tzinfo)  # type: ignore[union-attr]
        if now > deadline:  # type: ignore[operator]
            if participation_rate >= decision.min_participation:  # type: ignore[operator]
                if approval_rate >= decision.required_approval:  # type: ignore[operator]
                    final_decision = VoteOption.APPROVE
                    decision.status = DecisionStatus.APPROVED
                else:
                    final_decision = VoteOption.REJECT
                    decision.status = DecisionStatus.REJECTED
            else:
                decision.status = DecisionStatus.EXPIRED
            concluded_at = now
            session.commit()
        return DecisionResult(
            decision_id=decision_id,
            status=decision.status,
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
        query = session.query(DecisionModel)
        if decision_type:
            query = query.filter_by(decision_type=decision_type)
        if status:
            query = query.filter_by(status=status)
        decisions = query.all()
        results = []
        for decision in decisions:
            result = self.get_decision_result(str(decision.id), session)
            if result:
                results.append(result)
        return results


decision_service = DecisionService()
