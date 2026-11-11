"""Grant proposal service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


from sqlalchemy import case, select, update
from sqlmodel import Session, col

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


def _check_disburse_balance(grant: GrantProposal, disburse_amount: Decimal) -> None:
    """#1071: a disbursement can never exceed what the vote approved."""
    if grant.approved_amount - grant.disbursed_amount < disburse_amount:
        raise ValueError("disbursement exceeds the approved balance")


class GrantService:
    """CRUD, voting, and disbursement logic for DAO grants."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_grant(
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

    def get_grant(self, grant_id: str) -> GrantProposal | None:
        """Get a grant by ID."""
        return self.session.get(GrantProposal, grant_id)

    def list_grants(
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

    def create_milestone(
        self,
        grant_id: str,
        title: str,
        description: str,
        amount: Decimal | str | float,
        due_date: datetime | None = None,
    ) -> GrantMilestone:
        """Add a milestone to a grant."""
        grant = self.get_grant(grant_id)
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

    def get_milestones(self, grant_id: str) -> list[GrantMilestone]:
        """Get all milestones for a grant."""
        stmt = (
            select(GrantMilestone)
            .where(GrantMilestone.grant_id == grant_id)  # type: ignore[arg-type]
            .order_by(GrantMilestone.created_at)  # type: ignore[arg-type]
        )
        return list(self.session.execute(stmt).scalars().all())

    @staticmethod
    def _record_grant_voter(grant: GrantProposal, voter_id: str) -> None:
        """One vote per voter (#1071): voter ids ride in proposal_metadata so
        the uniqueness survives without a schema change."""
        voters = set((grant.proposal_metadata or {}).get("voters") or [])
        if voter_id in voters:
            raise ValueError("voter has already voted on this grant")
        voters.add(voter_id)
        metadata = dict(grant.proposal_metadata or {})
        metadata["voters"] = sorted(voters)
        grant.proposal_metadata = metadata

    def vote(self, grant_id: str, vote: str, voting_power: float, voter_id: str | None = None) -> GrantProposal:
        """Cast a vote on a grant and resolve if voting has ended."""
        grant = self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        if grant.status not in {GrantStatus.SUBMITTED, GrantStatus.UNDER_REVIEW, GrantStatus.ACTIVE}:
            raise ValueError("Grant is not open for voting")
        if voter_id is not None:
            self._record_grant_voter(grant, voter_id)
        now = _utc_now()
        voting_ends = _as_naive(grant.voting_ends)
        if voting_ends and now > voting_ends:
            raise ValueError("Voting period has ended")
        counter = {"for": "votes_for", "against": "votes_against", "abstain": "votes_abstain"}.get(vote)
        if counter is None:
            raise ValueError("Invalid vote type")
        # #1798: the voter-id metadata must be durable before the counter
        # UPDATE — a later refresh() would otherwise silently drop the
        # unflushed JSON change.
        self.session.flush()
        # #1798: atomic increment — votes_for/against/abstain are SQL-side
        # `col = col + power`, so concurrent votes cannot lose each other's
        # counts. The status predicate is the CAS: a grant that resolved
        # (or was cancelled) between the read and this write takes rowcount 0.
        claim = self.session.execute(
            update(GrantProposal)
            .where(
                col(GrantProposal.id) == grant_id,
                col(GrantProposal.status).in_([GrantStatus.SUBMITTED, GrantStatus.UNDER_REVIEW, GrantStatus.ACTIVE]),
            )
            .values(**{counter: getattr(GrantProposal, counter) + voting_power})
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) != 1:
            self.session.rollback()
            raise ValueError("Grant is not open for voting")
        self.session.refresh(grant)
        self._check_resolution(grant, now)
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    def process_grant(self, grant_id: str) -> GrantProposal:
        """Resolve a grant proposal after voting ends."""
        grant = self.get_grant(grant_id)
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

    def disburse(
        self,
        grant_id: str,
        milestone_id: str | None = None,
        amount: Decimal | str | float | None = None,
    ) -> GrantProposal:
        """Disburse funds for a grant or a specific milestone."""
        grant = self.get_grant(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        if grant.status not in {GrantStatus.APPROVED, GrantStatus.ACTIVE}:
            raise ValueError("Grant is not approved")
        if milestone_id:
            disburse_amount = self._claim_milestone_for_disburse(grant, milestone_id, amount)
        else:
            if amount is None:
                raise ValueError("Amount required when no milestone is specified")
            disburse_amount = _to_decimal(amount)
            _check_disburse_balance(grant, disburse_amount)
        self._cas_grant_disburse(grant_id, disburse_amount)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    def _claim_milestone_for_disburse(
        self,
        grant: GrantProposal,
        milestone_id: str,
        amount: Decimal | str | float | None,
    ) -> Decimal:
        """Validate and atomically claim a milestone for disbursement (#1798).

        Returns the amount to disburse. The PAID claim is a conditional
        UPDATE — two concurrent disburses of the same milestone cannot both
        mark it paid."""
        milestone = self.session.get(GrantMilestone, milestone_id)
        if not milestone or milestone.grant_id != grant.id:
            raise ValueError("Milestone not found")
        if milestone.status == MilestoneStatus.PAID:
            raise ValueError("Milestone already paid")
        if milestone.status != MilestoneStatus.APPROVED:
            raise ValueError("Milestone is not approved for disbursement")
        disburse_amount = _to_decimal(amount) if amount is not None else milestone.amount
        _check_disburse_balance(grant, disburse_amount)
        now = _utc_now()
        claim = self.session.execute(
            update(GrantMilestone)
            .where(
                col(GrantMilestone.id) == milestone_id,
                col(GrantMilestone.status) == MilestoneStatus.APPROVED,
            )
            .values(status=MilestoneStatus.PAID, completed_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) != 1:
            self.session.rollback()
            fresh = self.session.get(GrantMilestone, milestone_id)
            if fresh is not None and fresh.status == MilestoneStatus.PAID:
                raise ValueError("Milestone already paid")
            raise ValueError("Milestone is not approved for disbursement")
        return disburse_amount

    def _cas_grant_disburse(self, grant_id: str, disburse_amount: Decimal) -> None:
        """CAS the payout onto the grant row (#1798).

        The remaining-balance predicate lives in WHERE, so a concurrent
        disburse that already consumed the headroom makes rowcount 0 instead
        of silently overdrawing approved_amount. The status CASE keeps
        COMPLETED/ACTIVE truthful without a second read."""
        now = _utc_now()
        claim = self.session.execute(
            update(GrantProposal)
            .where(
                col(GrantProposal.id) == grant_id,
                col(GrantProposal.status).in_([GrantStatus.APPROVED, GrantStatus.ACTIVE]),
                col(GrantProposal.approved_amount) - col(GrantProposal.disbursed_amount) >= disburse_amount,
            )
            .values(
                disbursed_amount=col(GrantProposal.disbursed_amount) + disburse_amount,
                status=case(
                    (
                        col(GrantProposal.disbursed_amount) + disburse_amount >= col(GrantProposal.approved_amount),
                        GrantStatus.COMPLETED.name,
                    ),
                    else_=GrantStatus.ACTIVE.name,
                ),
                executed_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) != 1:
            self.session.rollback()
            fresh_grant = self.session.get(GrantProposal, grant_id)
            if fresh_grant is not None and fresh_grant.status not in {GrantStatus.APPROVED, GrantStatus.ACTIVE}:
                raise ValueError("Grant is not approved")
            raise ValueError("disbursement exceeds the approved balance")
