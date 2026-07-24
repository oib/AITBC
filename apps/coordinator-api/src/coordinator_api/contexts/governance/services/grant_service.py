"""Grant proposal service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


from sqlalchemy import select
from sqlmodel import Session

from ..domain.grant import GrantMilestone, GrantProposal, GrantStatus, MilestoneStatus


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


def _as_naive(value: datetime | None) -> datetime | None:
    """Strip timezone info from a stored timestamp for comparisons."""
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


class GrantService:
    """CRUD, voting, and disbursement logic for DAO grants."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def create_grant(
        self,
        developer_id: str,
        title: str,
        description: str,
        requested_amount: Decimal | str | float,
        voting_days: int = 7,
    ) -> GrantProposal:
        """Create a new grant proposal."""
        now = _utc_now()
        grant = GrantProposal(
            developer_id=developer_id,
            title=title,
            description=description,
            requested_amount=_to_decimal(requested_amount),
            status=GrantStatus.SUBMITTED,
            voting_starts=now,
            voting_ends=now + timedelta(days=voting_days),
        )
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    async def get_grant(self, grant_id: str) -> GrantProposal | None:
        """Get a grant by ID."""
        return self.session.get(GrantProposal, grant_id)

    async def list_grants(
        self,
        developer_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrantProposal]:
        """List grant proposals with optional filters."""
        stmt = select(GrantProposal)
        if developer_id:
            stmt = stmt.where(GrantProposal.developer_id == developer_id)  # type: ignore[arg-type]
        if status:
            stmt = stmt.where(GrantProposal.status == status)  # type: ignore[arg-type]
        stmt = stmt.order_by(GrantProposal.created_at.desc()).limit(limit).offset(offset)  # type: ignore[attr-defined]
        return list(self.session.execute(stmt).scalars().all())

    async def create_milestone(
        self,
        grant_id: str,
        title: str,
        description: str,
        amount: Decimal | str | float,
        due_date: datetime | None = None,
    ) -> GrantMilestone:
        """Add a milestone to a grant."""
        grant = await self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        milestone = GrantMilestone(
            grant_id=grant_id,
            title=title,
            description=description,
            amount=_to_decimal(amount),
            due_date=due_date,
        )
        self.session.add(milestone)
        self.session.commit()
        self.session.refresh(milestone)
        return milestone

    async def get_milestones(self, grant_id: str) -> list[GrantMilestone]:
        """Get all milestones for a grant."""
        stmt = (
            select(GrantMilestone)
            .where(GrantMilestone.grant_id == grant_id)  # type: ignore[arg-type]
            .order_by(GrantMilestone.created_at)  # type: ignore[arg-type]
        )
        return list(self.session.execute(stmt).scalars().all())

    async def vote(self, grant_id: str, vote: str, voting_power: float) -> GrantProposal:
        """Cast a vote on a grant and resolve if voting has ended."""
        grant = await self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        if grant.status not in {GrantStatus.SUBMITTED, GrantStatus.UNDER_REVIEW, GrantStatus.ACTIVE}:
            raise ValueError("Grant is not open for voting")
        now = _utc_now()
        voting_ends = _as_naive(grant.voting_ends)
        if voting_ends and now > voting_ends:
            raise ValueError("Voting period has ended")
        if vote == "for":
            grant.votes_for += voting_power
        elif vote == "against":
            grant.votes_against += voting_power
        elif vote == "abstain":
            grant.votes_abstain += voting_power
        else:
            raise ValueError("Invalid vote type")
        self._check_resolution(grant, now)
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    async def process_grant(self, grant_id: str) -> GrantProposal:
        """Resolve a grant proposal after voting ends."""
        grant = await self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        if grant.status not in {GrantStatus.SUBMITTED, GrantStatus.UNDER_REVIEW, GrantStatus.ACTIVE}:
            raise ValueError("Grant is not in a processable state")
        self._check_resolution(grant, _utc_now())
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    def _check_resolution(self, grant: GrantProposal, now: datetime) -> None:
        """Resolve the grant outcome once voting ends."""
        voting_ends = _as_naive(grant.voting_ends)
        if voting_ends and now < voting_ends:
            return
        total = grant.votes_for + grant.votes_against + grant.votes_abstain
        if total < grant.quorum:
            return
        for_against = grant.votes_for + grant.votes_against
        if for_against == 0:
            return
        if grant.votes_for / for_against >= grant.passing_threshold:
            if grant.status != GrantStatus.APPROVED:
                grant.status = GrantStatus.APPROVED
                grant.approved_amount = grant.requested_amount
        else:
            grant.status = GrantStatus.REJECTED

    async def disburse(
        self,
        grant_id: str,
        milestone_id: str | None = None,
        amount: Decimal | str | float | None = None,
    ) -> GrantProposal:
        """Disburse funds for a grant or a specific milestone."""
        grant = await self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        if grant.status not in {GrantStatus.APPROVED, GrantStatus.ACTIVE}:
            raise ValueError("Grant is not approved")
        if milestone_id:
            milestone = self.session.get(GrantMilestone, milestone_id)
            if not milestone or milestone.grant_id != grant_id:
                raise ValueError("Milestone not found")
            if milestone.status == MilestoneStatus.PAID:
                raise ValueError("Milestone already paid")
            if milestone.status != MilestoneStatus.APPROVED:
                raise ValueError("Milestone is not approved for disbursement")
            disburse_amount = _to_decimal(amount) if amount is not None else milestone.amount
            milestone.status = MilestoneStatus.PAID
            milestone.completed_at = _utc_now()
            grant.disbursed_amount += disburse_amount
            self.session.add(milestone)
        else:
            if amount is None:
                raise ValueError("Amount required when no milestone is specified")
            grant.disbursed_amount += _to_decimal(amount)
        if grant.disbursed_amount >= grant.approved_amount:
            grant.status = GrantStatus.COMPLETED
        else:
            grant.status = GrantStatus.ACTIVE
        grant.executed_at = _utc_now()
        grant.updated_at = _utc_now()
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant
