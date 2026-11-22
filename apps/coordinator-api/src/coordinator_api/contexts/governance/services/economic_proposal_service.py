"""Economic parameter proposal service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlmodel import Session

from ..domain.economic_proposal import EconomicParameterProposal, EconomicProposalStatus, EconomicProposalVote


def _to_decimal(value: Decimal | str | float | int | None) -> Decimal:
    """Normalize a monetary value to Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def _utc_now() -> datetime:
    """Return a naive UTC timestamp (SQLite-friendly)."""
    return datetime.now(UTC).replace(tzinfo=None)


class ProposalNotFoundError(ValueError):
    """The proposal id does not exist — a missing resource, not a bad request.

    Subclasses ``ValueError`` so existing ``except ValueError`` callers keep
    working; routers catch it first to answer 404 instead of 400 (#2449).
    """


class EconomicProposalService:
    """CRUD, voting, and execution logic for OpenClaw economic proposals."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_proposal(
        self,
        proposer_id: str,
        parameter_name: str,
        current_value: Decimal | str | float,
        proposed_value: Decimal | str | float,
        unit: str | None = None,
        voting_days: int = 7,
    ) -> EconomicParameterProposal:
        """Create a new economic parameter proposal."""
        now = _utc_now()
        proposal = EconomicParameterProposal(
            proposer_id=proposer_id,
            parameter_name=parameter_name,
            unit=unit,
            current_value=_to_decimal(current_value),
            proposed_value=_to_decimal(proposed_value),
            status=EconomicProposalStatus.SUBMITTED,
            voting_starts=now,
            voting_ends=now + timedelta(days=voting_days),
        )
        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def get_proposal(self, proposal_id: str) -> EconomicParameterProposal | None:
        """Get a proposal by ID."""
        return self.session.get(EconomicParameterProposal, proposal_id)

    def list_proposals(
        self,
        *,
        proposer_id: str | None = None,
        parameter_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EconomicParameterProposal]:
        """List economic parameter proposals with optional filters."""
        stmt = select(EconomicParameterProposal)
        if proposer_id:
            stmt = stmt.where(EconomicParameterProposal.proposer_id == proposer_id)  # type: ignore[arg-type]
        if parameter_name:
            stmt = stmt.where(EconomicParameterProposal.parameter_name == parameter_name)  # type: ignore[arg-type]
        if status:
            stmt = stmt.where(EconomicParameterProposal.status == status)  # type: ignore[arg-type]
        stmt = stmt.order_by(EconomicParameterProposal.created_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
        return list(self.session.execute(stmt).scalars().all())

    # #1360: lifecycle guards — tallies and execution are only meaningful
    # while voting is open / after it closes. Terminal and non-voting
    # statuses fail closed at the service layer regardless of router checks.
    _VOTABLE_STATUSES = {EconomicProposalStatus.SUBMITTED, EconomicProposalStatus.ACTIVE}
    _EXECUTABLE_STATUSES = {
        EconomicProposalStatus.SUBMITTED,
        EconomicProposalStatus.ACTIVE,
        EconomicProposalStatus.PASSED,
    }

    def vote(
        self,
        proposal_id: str,
        vote: str,
        voting_power: float = 0.0,
        *,
        voter_id: str,
    ) -> EconomicParameterProposal:
        """Cast a vote on a proposal — one vote per voter (#2494).

        ``voting_power`` is the caller's effective power snapshot at cast
        time; it is recorded on the vote row so the tally stays
        explainable. Delegation semantics are snapshot-based: delegating
        after voting does not re-weight the recorded vote, and the
        delegator's own stake stops counting toward their *future* votes
        via ``effective_voting_power`` — it cannot be voted twice going
        forward.
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"proposal {proposal_id} not found")
        if proposal.status not in self._VOTABLE_STATUSES:
            raise ValueError(f"proposal {proposal_id} is not open for voting (status={proposal.status})")
        if proposal.voting_ends is not None and _utc_now() > proposal.voting_ends:
            raise ValueError(f"voting window closed for proposal {proposal_id}")

        normalised = vote.strip().lower()
        if normalised not in {"for", "against", "abstain"}:
            raise ValueError(f"invalid vote: {vote}")

        existing = self.session.execute(
            select(EconomicProposalVote).where(
                EconomicProposalVote.proposal_id == proposal_id,  # type: ignore[arg-type]
                EconomicProposalVote.voter_id == voter_id,  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("voter has already voted on this proposal")

        if normalised == "for":
            proposal.votes_for += voting_power
        elif normalised == "against":
            proposal.votes_against += voting_power
        else:
            proposal.votes_abstain += voting_power

        self.session.add(
            EconomicProposalVote(
                proposal_id=proposal_id,
                voter_id=voter_id,
                vote=normalised,
                voting_power=voting_power,
            )
        )
        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def execute_proposal(self, proposal_id: str) -> EconomicParameterProposal:
        """Mark a passed proposal as executed and move proposed_value to current_value."""
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"proposal {proposal_id} not found")
        if proposal.status not in self._EXECUTABLE_STATUSES:
            raise ValueError(f"proposal {proposal_id} cannot be executed (status={proposal.status})")
        if proposal.voting_ends is not None and _utc_now() <= proposal.voting_ends:
            raise ValueError(f"voting window still open for proposal {proposal_id}")

        total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
        if total_votes <= 0:
            raise ValueError("no votes cast")
        if total_votes < proposal.quorum:
            raise ValueError("quorum not reached")

        if proposal.votes_for / total_votes < proposal.passing_threshold:
            proposal.status = EconomicProposalStatus.REJECTED
        else:
            proposal.current_value = proposal.proposed_value
            proposal.status = EconomicProposalStatus.EXECUTED
            proposal.executed_at = _utc_now()

        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal
