"""Economic parameter proposal service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlmodel import Session

from ..domain.economic_proposal import EconomicParameterProposal, EconomicProposalStatus


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


class EconomicProposalService:
    """CRUD, voting, and execution logic for OpenClaw economic proposals."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def create_proposal(
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

    async def get_proposal(self, proposal_id: str) -> EconomicParameterProposal | None:
        """Get a proposal by ID."""
        return self.session.get(EconomicParameterProposal, proposal_id)

    async def list_proposals(
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
            stmt = stmt.where(EconomicParameterProposal.proposer_id == proposer_id)
        if parameter_name:
            stmt = stmt.where(EconomicParameterProposal.parameter_name == parameter_name)
        if status:
            stmt = stmt.where(EconomicParameterProposal.status == status)
        stmt = stmt.order_by(EconomicParameterProposal.created_at.desc()).offset(offset).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    async def vote(
        self,
        proposal_id: str,
        vote: str,
        voting_power: float = 0.0,
    ) -> EconomicParameterProposal:
        """Cast a vote on a proposal."""
        proposal = await self.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"proposal {proposal_id} not found")

        normalised = vote.strip().lower()
        if normalised == "for":
            proposal.votes_for += voting_power
        elif normalised == "against":
            proposal.votes_against += voting_power
        elif normalised == "abstain":
            proposal.votes_abstain += voting_power
        else:
            raise ValueError(f"invalid vote: {vote}")

        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    async def execute_proposal(self, proposal_id: str) -> EconomicParameterProposal:
        """Mark a passed proposal as executed and move proposed_value to current_value."""
        proposal = await self.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"proposal {proposal_id} not found")

        total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
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
