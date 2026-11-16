"""Vote listing/persistence and vote creation for ``GovernanceService`` (#1860 Phase 6 split).

Pure-move split of the vote-side methods of
``governance_service.governance_service``: ``list_votes``,
``_persist_vote``, ``_assert_not_duplicate_vote`` and ``create_vote`` now
live on the ``_VotesMixin`` base class. ``governance_service.py`` composes
``GovernanceService`` from this mixin and the execution mixin, so the
method surface — including ``GovernanceService.<method>`` attribute access
used by tests — is unchanged. Moved code is byte-identical; shared module
names (``_OPS_ERRORS``, ``_parse_datetime``, ``_VOTE_UNIQUE_INDEX``) come
from ``governance_service_common``.

Import ``governance_service.governance_service`` (or
``governance_service.services``); this module is not meant to be imported
directly.
"""

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..config import settings
from ..domain.governance import ProposalStatus, Vote, VoteType
from .governance_service_common import _OPS_ERRORS, _VOTE_UNIQUE_INDEX, _parse_datetime

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from ..domain.governance import Proposal

logger = logging.getLogger(__name__)


class _VotesMixin:
    if TYPE_CHECKING:
        # Attributes and sibling methods supplied by ``GovernanceService``
        # (and the execution mixin) once the bases are composed — declared
        # here so mypy can check the moved bodies.
        session: AsyncSession

        async def get_proposal(self, proposal_id: str) -> Proposal | None: ...

        @staticmethod
        def _assert_voting_window(proposal_status: Proposal, vote_proposal_id: str) -> None: ...

        async def _ensure_governance_profile(self, user_id: str) -> None: ...

        async def _submit_vote_onchain(
            self, vote: Vote, vote_data: dict[str, Any], signed_tx: Any, voter_address: str
        ) -> None: ...

        async def calculate_voting_power(self, address: str) -> Decimal: ...

    async def list_votes(
        self,
        proposal_id: str | None = None,
        voter_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Vote]:
        """List votes.

        ``limit`` is opt-in: the duplicate-vote scan in ``create_vote`` and
        the ``aggregate-votes`` tally need every row, so ``None`` keeps the
        unbounded read; only the HTTP list endpoint passes a bound.
        """
        stmt = select(Vote)
        if proposal_id:
            stmt = stmt.where(Vote.proposal_id == proposal_id)
        if voter_id:
            stmt = stmt.where(Vote.voter_id == voter_id)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _persist_vote(self, vote: Vote, voter_id: str, vote_proposal_id: str) -> None:
        """Insert the vote, bump proposal counters, commit — mapping the
        unique-index IntegrityError to the sequential-path duplicate error."""
        try:
            self.session.add(vote)

            # Update proposal vote counters. The add above means the next
            # session.execute autoflushes the INSERT — the IntegrityError can
            # surface here or at commit(), so both sit inside this try.
            proposal = await self.get_proposal(vote.proposal_id)
            if proposal:
                if vote.vote_type == VoteType.FOR:
                    proposal.yes_votes += vote.voting_power_used
                    proposal.votes_for = proposal.yes_votes
                elif vote.vote_type == VoteType.AGAINST:
                    proposal.no_votes += vote.voting_power_used
                    proposal.votes_against = proposal.no_votes
                elif vote.vote_type == VoteType.ABSTAIN:
                    proposal.votes_abstain += vote.voting_power_used

            await self.session.commit()
        except IntegrityError as exc:
            # GOV-VOTE-RACE-1 (#1610): the duplicate-vote scan above is
            # check-then-insert; _VOTE_UNIQUE_INDEX is the DB backstop for a
            # racer that passed the same scan. Roll back (which also reverts
            # the proposal vote-counter bump) and surface the same "already
            # voted" error the sequential path raises. Matching on the index
            # name keeps unrelated integrity failures (FK, PK) visible.
            await self.session.rollback()
            if _VOTE_UNIQUE_INDEX in str(exc):
                raise ValueError(f"voter {voter_id} has already voted on proposal {vote_proposal_id}") from None
            raise

    async def _assert_not_duplicate_vote(self, vote_proposal_id: str, voter_id: str) -> None:
        """One vote per voter per proposal — repeats used to stack weight (#1091)."""
        for prior in await self.list_votes(proposal_id=vote_proposal_id):
            if str(prior.voter_id or "").lower() == voter_id.lower():
                raise ValueError(f"voter {voter_id} has already voted on proposal {vote_proposal_id}")

    async def create_vote(self, vote_data: dict[str, Any]) -> Vote:
        """Create a new vote.

        When on-chain submission is enabled, queries the voter's on-chain
        balance for voting power and submits a GOVERNANCE_VOTE transaction.
        The on-chain balance at the current block serves as the voting power
        snapshot.
        """
        for key in ("created_at",):
            if key in vote_data and vote_data[key] is not None:
                vote_data[key] = _parse_datetime(vote_data[key])

        # Client-signed on-chain submission (GAP-50) — not a Vote column.
        signed_tx = vote_data.pop("signed_tx", None)

        # Client-supplied weight fields are advisory at best and a forgery
        # vector at worst (#1091): power always comes from the server-side
        # snapshot below, never from the request.
        for key in ("voting_power", "voting_power_used", "power_at_snapshot", "delegated_power_at_snapshot", "vote_weight"):
            vote_data.pop(key, None)

        voter_id = vote_data.get("voter_id") or "anonymous"
        vote_proposal_id = str(vote_data.get("proposal_id") or "")

        # One vote per voter per proposal — repeats used to stack weight (#1091).
        proposal_status = await self.get_proposal(vote_proposal_id)
        if proposal_status is None:
            raise ValueError(f"Proposal not found: {vote_proposal_id}")
        if proposal_status.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal is not active (status: {proposal_status.status})")
        # The status stays ACTIVE until close_proposal runs, so without a
        # window check a vote cast after voting_ends still lands in the
        # tallies close_proposal reads — late weight can flip a decided
        # result (#v11 item 11). Mirror close_proposal's tz handling.
        self._assert_voting_window(proposal_status, vote_proposal_id)
        await self._assert_not_duplicate_vote(vote_proposal_id, voter_id)

        await self._ensure_governance_profile(voter_id)

        vote = Vote(**vote_data)
        # Match create_proposal: the service default wins over the model's
        # "ait-hub" fallback so chain queries hit the real chain database.
        vote.chain_id = settings.default_chain_id or vote.chain_id

        voter_address = vote_data.get("voter_address", "")
        if not voter_address:
            voter_address = voter_id

        await self._submit_vote_onchain(vote, vote_data, signed_tx, voter_address)

        # Off-chain voting power: derive from staked/held governance tokens when
        # on-chain submission is disabled or the chain query failed.
        if vote.voting_power is None or vote.voting_power == 0:
            try:
                vote.voting_power = await self.calculate_voting_power(voter_address)
                vote.power_at_snapshot = vote.voting_power
            except _OPS_ERRORS as e:
                logger.warning("Could not calculate off-chain voting power for %s: %s", voter_address, e)

        # Server-side voting power: do not let clients self-report unlimited weight.
        # Use the on-chain balance snapshot (or zero if the chain query failed) as
        # the authoritative voting_power_used.
        vote.voting_power_used = vote.voting_power

        await self._persist_vote(vote, voter_id, vote_proposal_id)
        await self.session.refresh(vote)
        return vote
